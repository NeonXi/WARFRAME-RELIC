"""
WARFRAME-RELIC 主程序入口
- 截图识别 Warframe 遗物选择界面
- 出入库状态查询 + 遗物内容查询
- 通过快捷键操作，覆盖层显示结果

核心逻辑链路（简单直接）：
  快捷键触发 → 清除所有（OCR线程 + 缓存 + 标注）→ 截图 → 显示功能按钮 → 用户选功能 → 执行
  中途再按快捷键 → 打断一切，从头开始
"""
import sys
import os
import time
import threading

# ---- 性能优化：限制 ONNX Runtime CPU 线程数 ----
_OCR_THREADS = max(2, min(4, os.cpu_count() // 2 if os.cpu_count() else 4))
os.environ["OMP_NUM_THREADS"] = str(_OCR_THREADS)
os.environ["ORT_NUM_THREADS"] = str(_OCR_THREADS)
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"

# 必须在 PyQt6 导入前设置
os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=0"
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*.warning=false"

import dxcam
import keyboard
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject, pyqtSignal, QThread
from PIL import Image

from core.overlay import Overlay
from core.management_panel import ManagementPanel
from core.hotkey_config import (
    load_hotkeys, save_hotkeys, DEFAULT_HOTKEYS,
    load_feature_toggles, FEATURE_TOGGLE_REQUIRES,
    load_item_region, save_item_region,
)
from core.constants import (
    COLOR_VAULTED, COLOR_AVAILABLE, COLOR_UNKNOWN,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER, FALLBACK_COLOR,
    DXCAM_MAX_RETRIES, DXCAM_RETRY_BASE_SLEEP,
)
from core.price_service import (
    price_to_color, build_display_name, format_price_annotation,
    clear_price_cache,
)
from recognizers.relic_name import RelicNameRecognizer
from recognizers.item_name import ItemNameRecognizer, match_and_price
from data.wfinfo_relics import RelicDB
from data.ui_strings import S


# ============================================================
# 信号桥接 & OCR 后台线程
# ============================================================

class TriggerBridge(QObject):
    """键盘热键 → Qt 信号桥接。"""
    fired = pyqtSignal(str)


class OCRWorker(QObject):
    """后台线程：执行 OCR 识别，完成后发射信号。"""
    finished = pyqtSignal(list)

    def __init__(self, recognizer, frame):
        super().__init__()
        self._recognizer = recognizer
        self._frame = frame

    def run(self):
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadPriority(
                ctypes.windll.kernel32.GetCurrentThread(), 0x00004000)
        except Exception:
            pass
        results = self._recognizer.recognize_all_with_boxes(self._frame)
        self.finished.emit(results)


# ============================================================
# 应用核心控制器
# ============================================================

class AppCore:
    """截图、OCR、标注、热键等所有业务逻辑的中心控制器。"""

    def __init__(self, app: QApplication):
        self._app = app

        # 硬件层
        self._camera = self._create_camera_with_retry()

        # UI 层
        self._overlay = Overlay()
        self._overlay.show()
        self._management_panel = ManagementPanel()

        # 识别层
        self._relic_ocr = RelicNameRecognizer()
        self._relic_db = RelicDB()
        self._item_ocr = ItemNameRecognizer()

        # 信号桥接
        self._bridge = TriggerBridge()

        # 功能开关
        self._feature_toggles = load_feature_toggles()

        # ---- 核心数据 ----
        self._last_frame = None       # 最近一次截图帧
        self._last_region = None      # 最近一次截图区域（逻辑坐标）
        self._last_relics = []        # OCR 结果缓存：遗物
        self._last_items = []         # OCR 结果缓存：物品
        self._last_texts = []         # OCR 结果缓存：文本

        # ---- OCR 线程 ----
        self._ocr_thread = None
        self._ocr_worker = None
        self._ocr_lock = threading.Lock()  # 保护 OCR 线程的启停

        # ---- 注册的热键句柄 ----
        self._registered_hotkeys = {}

    # ================================================================
    # 启动 & 清理
    # ================================================================

    def run(self):
        self._init_db()
        self._bind_events()
        self._register_initial_hotkeys()
        self._print_startup_info()
        self._app.aboutToQuit.connect(self._shutdown)
        QTimer.singleShot(100, self._show_panel_on_start)

        # ★ 快捷键健康心跳：每 30 秒检查一次热键是否仍然有效
        self._hotkey_health_timer = QTimer()
        self._hotkey_health_timer.timeout.connect(self._hotkey_health_check)
        self._hotkey_health_timer.start(30000)  # 30 秒

        self._app.exec()

    def _shutdown(self):
        self._kill_ocr_thread()
        self._relic_db.close()
        for hk_id in self._registered_hotkeys.values():
            try:
                keyboard.remove_hotkey(hk_id)
            except Exception:
                pass
        self._registered_hotkeys.clear()
        self._camera = None
        print("[退出] 资源已清理")

    # ---- 摄像头 ----

    @staticmethod
    def _create_camera_with_retry(max_retries=DXCAM_MAX_RETRIES):
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                return dxcam.create(output_idx=0, output_color="BGR")
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    wait = DXCAM_RETRY_BASE_SLEEP * attempt
                    print(f"[摄像头] 初始化失败 (第 {attempt}/{max_retries} 次): {e}")
                    print(f"          {wait:.1f}s 后重试...")
                    if attempt == 2:
                        print("          提示: 请关闭其他使用摄像头的程序后重试")
                    time.sleep(wait)
        raise RuntimeError(
            f"无法初始化 dxcam 摄像头（已重试 {max_retries} 次）: {last_err}")

    # ---- 数据库 ----

    def _init_db(self):
        if not self._relic_db.load():
            print("[警告] 遗物数据库加载失败，遗物内容查询将不可用")

    def reload_db(self, db_path: str):
        self._log("数据库已更新，重新加载...", source="reload_db")
        self._relic_db.invalidate()
        if self._relic_db.load():
            stats = self._relic_db.stats()
            self._log(f"重新加载完成 — {stats['total_relics']} 个遗物 | "
                      f"入库 {stats['available']} | 出库 {stats['vaulted']}", "ok", "reload_db")
        else:
            self._log("数据库重新加载失败", "error", "reload_db")

    # ---- 日志 ----

    def _log(self, msg: str, log_type: str = "info", source: str = ""):
        self._management_panel.add_log(log_type, msg, source)
        prefix = {"info": " ", "warn": "▲", "error": "✘", "ok": "✔"}.get(log_type, " ")
        src = f"[{source}] " if source else ""
        print(f"[{time.strftime('%H:%M:%S')}] {src}{prefix} {msg}", flush=True)

    # ---- 面板 ----

    def _position_panel_on_screen(self):
        screens = QApplication.screens()
        target_screen = screens[-1] if len(screens) > 1 else screens[0]
        self._management_panel.move(target_screen.geometry().topLeft())

    def _show_panel_on_start(self):
        self._position_panel_on_screen()
        self._management_panel.show()
        self._management_panel.raise_()
        self._management_panel.activateWindow()
        self._management_panel.adjustSize()
        self._management_panel.resize(580, 840)

    def _toggle_panel(self):
        if self._management_panel.isVisible():
            self._management_panel.hide()
        else:
            self._position_panel_on_screen()
            self._management_panel.adjustSize()
            self._management_panel.show()
            self._management_panel.raise_()
            self._management_panel.activateWindow()

    # ---- 事件绑定 ----

    def _bind_events(self):
        self._overlay.on_selection_done = self._on_selection_done
        self._overlay.mode_selected.connect(self._on_mode_selected)
        self._bridge.fired.connect(self._on_hotkey)
        self._management_panel.db_updated.connect(self.reload_db)
        self._management_panel.hotkeys_changed.connect(self._on_hotkeys_changed)
        self._management_panel.theme_changed.connect(self._on_theme_changed)
        self._management_panel.reset_requested.connect(self._on_reset)
        self._management_panel.feature_toggles_changed.connect(self._on_feature_toggles_changed)
        self._management_panel.item_region_select_requested.connect(self._on_item_region_select)

    # ---- 热键 ----

    # 防重入：防止快速连续按键导致状态混乱
    _hotkey_busy = False
    _hotkey_last_action_time = 0

    def _on_hotkey(self, action):
        """所有快捷键的统一入口（防重入 + 诊断）。"""
        now = time.time()

        # 防重入：同一 action 在 500ms 内只能触发一次
        if now - self._hotkey_last_action_time < 0.5:
            print(f"[快捷键] 忽略重复触发: {action} (间隔 {now - self._hotkey_last_action_time:.2f}s)", flush=True)
            return
        self._hotkey_last_action_time = now

        print(f"[快捷键] ✓ 触发: {action} | 线程安全={self._verify_hotkey_health()}", flush=True)

        if action == 'select':
            self._overlay.start_selection()
        elif action == 'panel':
            self._toggle_panel()
        elif action == 'fullscreen':
            # 全屏截图：打断一切，从头开始
            self._kill_ocr_thread()
            self._clear_results()
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            self._do_fullscreen_screenshot()
        elif action == 'query_price':
            # 价格查询：自动4等分截图+识别+标注
            self._kill_ocr_thread()
            self._clear_results()
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            self._do_price_query()

    def _verify_hotkey_health(self) -> bool:
        """诊断快捷键健康状态。返回 True 表示一切正常。"""
        if not self._registered_hotkeys:
            print("[快捷键诊断] ✘ 警告：没有任何已注册的热键！", flush=True)
            return False

        expected_actions = ["select", "fullscreen", "panel", "query_price"]
        all_ok = True
        for action in expected_actions:
            hk_str = load_hotkeys().get(action, DEFAULT_HOTKEYS[action])
            if hk_str not in self._registered_hotkeys:
                print(f"[快捷键诊断] ✘ 缺失: {action} ({hk_str}) 未注册！", flush=True)
                all_ok = False

        if all_ok:
            print(f"[快捷键诊断] ✓ 所有热键正常 (已注册 {len(self._registered_hotkeys)} 个)", flush=True)
        return all_ok

    def _hotkey_health_check(self):
        """定期心跳：检查热键是否仍然有效，失效则自动恢复。"""
        if not self._verify_hotkey_health():
            self._log("检测到快捷键异常，自动尝试恢复...", "warn", "health_check")
            # 自动重新注册
            self._register_hotkeys(load_hotkeys())
            if self._verify_hotkey_health():
                self._log("快捷键自动恢复成功", "ok", "health_check")
            else:
                self._log("快捷键自动恢复失败！请手动点击管理面板的「紧急重置」按钮", "error", "health_check")

    def _register_hotkeys(self, hotkeys: dict):
        """注册热键（增强版：逐键清除、失败重试、健康诊断）。"""
        # 权限检查：keyboard 库在 Windows 上需要管理员权限
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() if hasattr(ctypes, 'windll') else True
        if not is_admin:
            print("[热键] ⚠ 未以管理员身份运行！keyboard 库注册全局热键需要管理员权限。", flush=True)
            self._log("未以管理员身份运行，快捷键可能无法生效。请右键 → 以管理员身份运行。", "warn", "hotkeys")

        print(f"[热键] ===== 开始注册热键: {hotkeys} =====", flush=True)

        # 第一步：逐个清除旧热键（而不是 unhook_all，避免影响其他程序）
        old_keys = list(self._registered_hotkeys.keys())
        for hk_str, hk_id in list(self._registered_hotkeys.items()):
            try:
                keyboard.remove_hotkey(hk_id)
                print(f"[热键] 已清除: {hk_str}", flush=True)
            except Exception as e:
                print(f"[热键] 清除失败 {hk_str}: {e}", flush=True)
        self._registered_hotkeys.clear()

        # 第二步：如果清除后仍有残留，用 unhook_all 兜底
        if old_keys:
            try:
                keyboard.unhook_all()
                print("[热键] unhook_all 兜底完成", flush=True)
            except Exception as e:
                print(f"[热键] unhook_all 异常: {e}", flush=True)

        # 第三步：注册新热键
        action_map = {
            "select": "select", "fullscreen": "fullscreen", "panel": "panel",
            "query_price": "query_price",
        }

        success_count = 0
        for action, action_name in action_map.items():
            hk_str = hotkeys.get(action, DEFAULT_HOTKEYS[action])

            # 验证热键字符串合法性
            if not hk_str or '+' not in hk_str:
                print(f"[热键] ✘ 跳过非法热键: {action} → '{hk_str}'", flush=True)
                self._log(f"快捷键 {action} 格式非法，使用默认值", "warn", "hotkeys")
                hk_str = DEFAULT_HOTKEYS[action]

            registered = False
            for attempt in range(3):  # 最多重试 3 次
                try:
                    # 先尝试移除可能存在的旧 hook（用字符串匹配）
                    try:
                        keyboard.remove_hotkey(hk_str)
                    except Exception:
                        pass

                    hk_id = keyboard.add_hotkey(
                        hk_str,
                        lambda a=action_name: self._bridge.fired.emit(a)
                    )
                    self._registered_hotkeys[hk_str] = hk_id
                    print(f"[热键] ✓ {hk_str} 注册成功 ({action_name}) [第{attempt + 1}次]", flush=True)
                    registered = True
                    success_count += 1
                    break
                except Exception as e:
                    print(f"[热键] ⚠ {hk_str} 注册失败 (第{attempt + 1}/3次): {e}", flush=True)
                    if attempt < 2:
                        time.sleep(0.05)

            if not registered:
                self._log(f"✘ 快捷键 {hk_str} ({action_name}) 注册失败，请检查是否有其他程序占用了该快捷键",
                         "error", "hotkeys")
                # 失败时回退到默认快捷键
                fallback = DEFAULT_HOTKEYS[action]
                try:
                    hk_id = keyboard.add_hotkey(
                        fallback,
                        lambda a=action_name: self._bridge.fired.emit(a)
                    )
                    self._registered_hotkeys[fallback] = hk_id
                    print(f"[热键] ↻ 回退默认: {fallback} ({action_name})", flush=True)
                    success_count += 1
                except Exception as e2:
                    print(f"[热键] ✘ 回退也失败: {fallback} - {e2}", flush=True)

        print(f"[热键] ===== 注册完成: {success_count}/{len(action_map)} 成功 =====", flush=True)

        # 如果有任何快捷键注册失败，弹窗提示用户
        if success_count < len(action_map):
            self._overlay.display(
                f"⚠ 快捷键注册失败 ({success_count}/{len(action_map)})！\n"
                "请以管理员身份运行程序，或检查快捷键是否被其他程序占用。",
                auto_hide_ms=10000)

        # 第四步：如果全部失败，尝试用默认热键紧急恢复
        if success_count == 0:
            print("[热键] 🆘 所有热键注册失败！尝试用默认热键紧急恢复...", flush=True)
            self._log("所有快捷键注册失败，使用默认值紧急恢复", "error", "hotkeys")
            for action, action_name in action_map.items():
                hk_str = DEFAULT_HOTKEYS[action]
                try:
                    hk_id = keyboard.add_hotkey(
                        hk_str,
                        lambda a=action_name: self._bridge.fired.emit(a)
                    )
                    self._registered_hotkeys[hk_str] = hk_id
                    print(f"[热键] ✓ 紧急恢复: {hk_str} ({action_name})", flush=True)
                    success_count += 1
                except Exception as e:
                    print(f"[热键] ✘ 紧急恢复失败: {hk_str} - {e}", flush=True)

        # 第五步：健康检查
        self._verify_hotkey_health()

    def _register_initial_hotkeys(self):
        self._register_hotkeys(load_hotkeys())

    def _on_hotkeys_changed(self, new_hotkeys):
        print(f"[热键] 快捷键已更新: {new_hotkeys}", flush=True)
        self._register_hotkeys(new_hotkeys)

    def _on_theme_changed(self):
        self._overlay.refresh_theme()

    def _on_feature_toggles_changed(self, toggles: dict):
        self._feature_toggles = toggles
        self._log(f"功能开关已更新: {toggles}", "ok", "_on_feature_toggles_changed")

    def _on_reset(self):
        """管理面板的紧急排障按钮（从根本解决一切可能的异常状态）。

        执行顺序（由浅入深，确保每层都恢复）：
          1. 终止所有后台线程（OCR + 实时价格）
          2. 清空所有缓存数据（帧、识别结果）
          3. 清除 Overlay 所有视觉元素（标注、按钮、标签、预览）
          4. 退出框选模式（防止 UI 卡死在框选状态）
          5. 恢复鼠标穿透（防止 Overlay 阻挡操作）
          6. 强制注销并重新注册所有快捷键（使用硬编码默认值）
          7. 重置快捷键配置文件
          8. 摄像头健康检查
          9. 同步更新管理面板快捷键显示
          10. 健康诊断 + 日志报告
        """
        self._log(S("log_msg", "reset_start"), "info", "_on_reset")
        errors = []

        # ── 1. 终止所有后台线程 ──
        try:
            self._kill_ocr_thread()
            self._log("  ✓ OCR 线程已终止", "info", "_on_reset")
        except Exception as e:
            errors.append(f"终止 OCR 线程: {e}")

        # ── 2. 清空所有缓存 ──
        try:
            self._clear_results()
            self._log("  ✓ 缓存数据已清空", "info", "_on_reset")
        except Exception as e:
            errors.append(f"清空缓存: {e}")

        # ── 3. 清除 Overlay 所有视觉元素 ──
        try:
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            if hasattr(self._overlay, '_preview_label'):
                self._overlay._preview_label.hide()
            self._log("  ✓ Overlay 视觉元素已清除", "info", "_on_reset")
        except Exception as e:
            errors.append(f"清除 Overlay: {e}")

        # ── 4. 退出框选模式（关键！否则 Overlay 可能卡在框选状态） ──
        try:
            if self._overlay._selecting:
                self._overlay.end_selection()
                self._log("  ✓ 已退出框选模式", "info", "_on_reset")
        except Exception as e:
            errors.append(f"退出框选: {e}")

        # ── 5. 恢复鼠标穿透 ──
        try:
            self._overlay._apply_mouse_passthrough(True)
            self._log("  ✓ 鼠标穿透已恢复", "info", "_on_reset")
        except Exception as e:
            errors.append(f"鼠标穿透: {e}")

        # ── 6. 强制重新注册快捷键（硬编码默认值，不依赖任何文件） ──
        try:
            self._register_hotkeys(dict(DEFAULT_HOTKEYS))
            self._log("  ✓ 快捷键已用默认值重新注册", "info", "_on_reset")
        except Exception as e:
            errors.append(f"注册快捷键: {e}")

        # ── 7. 重置快捷键配置文件 ──
        try:
            save_hotkeys({})
            self._log("  ✓ hotkeys.json 已重置", "info", "_on_reset")
        except Exception as e:
            errors.append(f"保存 hotkeys.json: {e}")

        # ── 8. 摄像头健康检查 ──
        try:
            if self._camera is None:
                self._camera = self._create_camera_with_retry()
                self._log("  ✓ 摄像头已重新初始化", "info", "_on_reset")
            else:
                self._log("  ✓ 摄像头正常", "info", "_on_reset")
        except Exception as e:
            errors.append(f"摄像头: {e}")

        # ── 9. 通知管理面板同步快捷键显示 ──
        try:
            self._management_panel._hotkeys = dict(DEFAULT_HOTKEYS)
            self._management_panel._refresh_hotkey_ui()
            self._log("  ✓ 管理面板快捷键显示已同步", "info", "_on_reset")
        except Exception as e:
            errors.append(f"同步面板 UI: {e}")

        # ── 10. 最终健康诊断 ──
        health_ok = self._verify_hotkey_health()
        health_status = "✓ 健康" if health_ok else "✘ 异常"

        # ── 汇总报告 ──
        if errors:
            self._log(f"排障完成但有 {len(errors)} 个警告: {'; '.join(errors)}", "warn", "_on_reset")
        else:
            self._log(S("log_msg", "reset_done"), "ok", "_on_reset")
        self._log(f"快捷键健康状态: {health_status} | 已注册 {len(self._registered_hotkeys)} 个热键",
                  "ok" if health_ok else "error", "_on_reset")

    # ---- 启动信息 ----

    def _print_startup_info(self):
        db_stats = self._relic_db.stats()
        hotkeys_config = load_hotkeys()
        self._log(S("log_msg", "startup"), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_select", hk=hotkeys_config['select']), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_fullscreen", hk=hotkeys_config['fullscreen']), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_panel", hk=hotkeys_config['panel']), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_query_price", hk=hotkeys_config.get('query_price', 'ctrl+shift+p')), source="_print_startup_info")
        self._log(S("log_msg", "startup_right_click"), source="_print_startup_info")
        self._log(S("log_msg", "startup_mode_hint"), source="_print_startup_info")
        self._log(S("log_msg", "startup_mode_check"), source="_print_startup_info")
        self._log(S("log_msg", "startup_mode_query"), source="_print_startup_info")
        self._log(S("log_msg", "startup_mode_price"), source="_print_startup_info")
        self._log(S("log_msg", "startup_mode_translate"), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_db_info",
            total=db_stats['total_relics'], available=db_stats['available'],
            vaulted=db_stats['vaulted']), "ok", "_print_startup_info")

    # ============================================================
    # 核心链路：框选截图
    # ============================================================
    # _on_hotkey('select') → overlay.start_selection()
    #   → 用户框选完成 → overlay._finish_selection()
    #   → overlay.on_selection_done() → _on_selection_done()
    #   → 清除旧数据 → 截图 → 显示功能按钮
    # ============================================================

    def _on_selection_done(self):
        """框选完成回调。打断一切，从头开始。"""
        self._kill_ocr_thread()
        self._clear_results()
        self._overlay.clear_annotations()
        self._overlay._hide_mode_buttons()
        self._overlay.label.clear()

        region = self._overlay.get_region()
        if region is None:
            self._overlay.display(S("overlay", "please_select_first"), auto_hide_ms=3000)
            return

        dpi = self._overlay._dpi_scale
        phys_region = (
            int(region[0] * dpi), int(region[1] * dpi),
            int(region[2] * dpi), int(region[3] * dpi),
        )
        frame = self._camera.grab(region=phys_region)
        if frame is None:
            self._overlay.display(S("overlay", "screenshot_failed"), auto_hide_ms=3000)
            return

        self._after_screenshot(frame, region)

    # ============================================================
    # 核心链路：全屏截图
    # ============================================================
    # _on_hotkey('fullscreen') → 清除 → _do_fullscreen_screenshot()
    # ============================================================

    def _do_fullscreen_screenshot(self):
        """全屏截图。调用前已由 _on_hotkey 完成清除。"""
        if self._overlay.is_showing_content():
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()

        self._log("全屏截图 — 开始识别", source="do_fullscreen")

        dpi = self._overlay._dpi_scale
        full_phys = (0, 0, self._camera.width, self._camera.height)
        full_logical = (0, 0, int(self._camera.width / dpi), int(self._camera.height / dpi))

        frame = self._camera.grab(region=full_phys)
        if frame is None:
            self._overlay.display(S("overlay", "fullscreen_failed"), auto_hide_ms=3000)
            return

        self._overlay.display(
            S.format("overlay", "fullscreen_info", w=self._camera.width, h=self._camera.height),
            auto_hide_ms=2000)
        self._after_screenshot(frame, full_logical)

    # ============================================================
    # 价格查询快捷键（4等分截图+识别）
    # ============================================================

    def _on_item_region_select(self):
        """管理面板请求设置物品区域：启动物品区域框选模式。"""
        self._overlay.start_selection()
        # 覆盖 on_selection_done 为物品区域保存逻辑
        self._overlay.on_selection_done = self._on_item_region_selection_done

    def _on_item_region_selection_done(self):
        """物品区域框选完成：保存区域到配置文件。"""
        region = self._overlay.get_region()
        if region is None:
            self._overlay.display("框选取消，区域未设置", auto_hide_ms=3000)
        else:
            # region 格式为 (left, top, right, bottom)，需要转为 (x, y, w, h)
            dpi = self._overlay._dpi_scale
            left, top, right, bottom = region
            phys_region = {
                'x': int(left * dpi),
                'y': int(top * dpi),
                'w': int((right - left) * dpi),
                'h': int((bottom - top) * dpi),
            }
            if save_item_region(phys_region):
                self._overlay.display(
                    f"物品区域已保存！(x={phys_region['x']}, y={phys_region['y']}, "
                    f"w={phys_region['w']}, h={phys_region['h']}) 将横向4等分",
                    auto_hide_ms=4000)
                self._log(f"物品区域已保存: {phys_region}", "ok", "_on_item_region_selection_done")
            else:
                self._overlay.display("保存物品区域失败！", auto_hide_ms=3000)
                self._log("保存物品区域失败", "error", "_on_item_region_selection_done")

        # 恢复正常的框选回调
        self._overlay.on_selection_done = self._on_selection_done
        # 刷新管理面板状态
        self._management_panel._refresh_item_region_status()

    def _do_price_query(self):
        """价格查询快捷键：加载物品区域 → 显示4等分框线 → 截4图 → 逐份识别 → 查价格 → 标注。"""
        region_cfg = load_item_region()
        if region_cfg is None:
            self._overlay.display(
                "未设置物品区域！请先在管理面板 → 价格数据 → 设置物品区域",
                auto_hide_ms=5000)
            self._log("价格查询失败：未设置物品区域", "warn", "_do_price_query")
            return

        x, y, w, h = region_cfg['x'], region_cfg['y'], region_cfg['w'], region_cfg['h']
        item_w = w // 4  # 横向4等分

        self._log(f"价格查询：区域=({x},{y},{w},{h}) 4等分每份宽={item_w}", source="_do_price_query")

        import ctypes
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)

        # ★ 显示4等分区域框线，持续到价格标注显示出来为止（不设自动过期）
        split_regions = []
        for i in range(4):
            ix = x + i * item_w
            rx = max(0, ix)
            ry = max(0, y)
            rw = min(item_w, screen_w - rx)
            rh = min(h, screen_h - ry)
            if rw > 0 and rh > 0:
                split_regions.append((rx, ry, rw, rh, f"子图{i+1}"))
        self._overlay.show_split_regions(split_regions, duration_ms=99999)  # 持续显示，等标注完成后手动清除
        self._overlay.display(S("overlay", "price_query_scanning"), auto_hide_ms=99999)

        # ★ 立即开始截图+识别（不延迟，框线持续显示）
        self._do_price_query_capture(x, y, w, h, item_w, screen_w, screen_h)

    def _do_price_query_capture(self, x, y, w, h, item_w, screen_w, screen_h):
        """价格查询的截图+识别+标注阶段（在框线消失后执行）。"""
        print(f"\n{'='*60}", flush=True)
        print(f"[价格查询] 开始截图+识别 (区域: {x},{y},{w},{h}, 4等分每份={item_w})", flush=True)
        print(f"{'='*60}", flush=True)

        dpi = self._overlay._dpi_scale
        all_items = []
        for i in range(4):
            # ★ 进度反馈：OCR 阶段
            self._overlay.display(f"⟐ 正在识别第 {i+1}/4 个物品...", auto_hide_ms=2000)

            # 截取第 i 个物品卡片
            ix = x + i * item_w
            # 裁剪区域使其不超出屏幕边界，避免 dxcam 报 Invalid Region
            rx = max(0, ix)
            ry = max(0, y)
            rw = min(item_w, screen_w - rx)
            rh = min(h, screen_h - ry)
            if rw <= 0 or rh <= 0:
                self._log(f"第{i+1}个物品区域超出屏幕范围，跳过", "warn", "_do_price_query")
                continue
            # dxcam region 格式为 (left, top, right, bottom)
            dxcam_region = (rx, ry, rx + rw, ry + rh)
            print(f"\n[价格查询] 截取子图{i+1}/4: ({rx},{ry}) {rw}x{rh}", flush=True)
            frame = self._camera.grab(region=dxcam_region)
            if frame is None:
                print(f"[价格查询] 子图{i+1}/4 截图返回 None!", flush=True)
                self._log(f"第{i+1}个物品截图失败", "warn", "_do_price_query")
                continue

            print(f"[价格查询] 子图{i+1}/4 截图成功: {frame.shape[1]}x{frame.shape[0]}", flush=True)

            # OCR 识别（同步，因为4张图很快）
            results = self._item_ocr.recognize_all_with_boxes(frame)
            if results:
                # results: [(name, box, variants), ...]
                for r_name, r_box, r_variants in results:
                    # 转换坐标为全局坐标（使用裁剪后的实际截图起点 rx, ry）
                    global_box = [
                        [r_box[0][0] + rx, r_box[0][1] + ry],
                        [r_box[1][0] + rx, r_box[1][1] + ry],
                        [r_box[2][0] + rx, r_box[2][1] + ry],
                        [r_box[3][0] + rx, r_box[3][1] + ry],
                    ]
                    all_items.append((r_name, global_box, r_variants))
                print(f"[价格查询] 子图{i+1}/4 识别完成: {[(r[0], r[2]) for r in results]}", flush=True)
                self._log(f"第{i+1}个物品: {[r[0] for r in results]}", source="_do_price_query")
            else:
                print(f"[价格查询] 子图{i+1}/4 未识别到物品", flush=True)
                self._log(f"第{i+1}个物品: 未识别到", "warn", "_do_price_query")

        print(f"\n[价格查询] 截图+识别阶段完成，共 {len(all_items)} 个物品", flush=True)

        if not all_items:
            print(f"[价格查询] 无识别结果，结束", flush=True)
            self._overlay._clear_split_regions()
            self._overlay.display("未能识别到任何物品", auto_hide_ms=3000)
            return

        # 查价格 + 标注
        print(f"\n{'='*60}", flush=True)
        print(f"[价格查询] 开始匹配+查价 (共 {len(all_items)} 个)", flush=True)
        print(f"{'='*60}", flush=True)
        self._last_items = all_items

        # ★ 进度反馈：匹配+查价阶段
        self._overlay.display(f"⟐ 正在查询 {len(all_items)} 个物品的价格...", auto_hide_ms=5000)
        # 强制刷新 overlay 显示
        QApplication.processEvents()

        matched = match_and_price(all_items)
        # ★ 清除框线（价格标注即将显示，框线不再需要）
        self._overlay._clear_split_regions()
        if matched:
            print(f"\n[价格查询] 匹配+查价完成: {len(matched)} 个", flush=True)
            for m in matched:
                price_info = ""
                if m.get('price') and m['price'].get('sell_weighted') is not None:
                    price_info = f" → {m['price']['sell_weighted']}p"
                print(f"  [{m['match_quality']}] \"{m.get('en_name','?')}\" ({m.get('zh_name','')}){price_info}", flush=True)
            # 直接渲染：box 已经是屏幕物理坐标，不需要 DPI 转换
            self._render_price_direct(matched)
            total = len(matched)
            with_price = sum(1 for m in matched if m.get('price') and m['price'].get('sell_weighted') is not None)
            self._overlay.display(
                S.format("overlay", "price_query_summary", total=total, with_price=with_price),
                auto_hide_ms=8000)
        else:
            print(f"[价格查询] 匹配+查价: 无结果", flush=True)
            self._overlay.display("未能匹配到任何价格信息", auto_hide_ms=3000)

    def _render_price_direct(self, matched):
        """直接渲染价格标注（box 为屏幕物理坐标，不需要 DPI 转换）。"""
        annotations = []
        dpi = self._overlay._dpi_scale

        for item in matched:
            box = item['box']
            # box 是物理坐标，直接除以 dpi 转逻辑坐标
            sx = int(box[0][0] / dpi)
            sy = int(box[0][1] / dpi - 28)

            quality = item['match_quality']
            price = item.get('price')
            color = price_to_color(price, quality)
            label = format_price_annotation(item)

            annotations.append((label, sx, sy, 15000, color))

        # ★ 加速流式动画：一次显示全部，15ms 极短延迟
        self._overlay.show_annotations_stream(
            annotations, auto_hide_ms=15000, interval_ms=15, batch_size=len(annotations))

    # ============================================================
    # 截图后：保存 + 显示功能按钮
    # ============================================================

    def _after_screenshot(self, frame, region):
        """截图成功后的统一处理。"""
        # 保存调试截图
        img = Image.fromarray(frame[:, :, ::-1])
        save_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
        os.makedirs(save_dir, exist_ok=True)
        img.save(os.path.join(save_dir, 'last_capture.png'))

        # 保存帧引用，清空旧 OCR 结果
        self._last_frame = frame
        self._last_region = region
        self._last_relics = []
        self._last_items = []
        self._last_texts = []

        # 显示功能按钮（query_price 已从开关移除，不再显示按钮）
        enabled_modes = [k for k, v in self._feature_toggles.items() if v]
        if enabled_modes:
            self._overlay.show_mode_buttons(enabled_modes)
        else:
            self._overlay.display(S("overlay", "screenshot_done"), auto_hide_ms=3000)

    # ============================================================
    # 清除方法
    # ============================================================

    def _clear_results(self):
        """清空所有缓存数据。"""
        self._last_frame = None
        self._last_region = None
        self._last_relics = []
        self._last_items = []
        self._last_texts = []
        clear_price_cache()  # 清价格缓存

    def _kill_ocr_thread(self):
        """强制终止 OCR 线程（不关心结果）。"""
        with self._ocr_lock:
            thread = self._ocr_thread
            self._ocr_thread = None
            self._ocr_worker = None

        if thread is None:
            return

        if thread.isRunning():
            thread.quit()
            if not thread.wait(2000):
                thread.terminate()
                thread.wait()

        thread.deleteLater()

    # ============================================================
    # OCR 线程（按需启动）
    # ============================================================

    def _start_ocr(self, ocr_type: str, callback):
        """启动 OCR 线程。
        
        仅在 _on_mode_selected 中调用，前提是 _last_frame 存在且该类型结果未缓存。
        """
        # 选识别器
        if ocr_type == 'relic':
            recognizer = self._relic_ocr
        elif ocr_type in ('item', 'text'):
            recognizer = self._item_ocr
        else:
            self._log(f"未知 OCR 类型: {ocr_type}", "error", "_start_ocr")
            return

        self._log(f"启动 OCR: {ocr_type}", source="_start_ocr")

        def _delayed_ocr():
            self._ocr_thread = QThread()
            self._ocr_worker = OCRWorker(recognizer, self._last_frame)
            self._ocr_worker.moveToThread(self._ocr_thread)
            self._ocr_worker.finished.connect(
                lambda results: self._on_ocr_done(results, ocr_type, callback))
            self._ocr_thread.started.connect(self._ocr_worker.run)
            self._ocr_thread.finished.connect(self._on_thread_finished)
            self._ocr_thread.start()

        QTimer.singleShot(80, _delayed_ocr)

    def _on_thread_finished(self):
        """QThread.finished 信号：清理线程对象。"""
        with self._ocr_lock:
            if self._ocr_thread:
                self._ocr_thread.deleteLater()
                self._ocr_thread = None
                self._ocr_worker = None

    def _on_ocr_done(self, results, ocr_type, callback):
        """OCR 完成（在主线程）。"""
        # 如果 OCR 结果到达时帧已被清除（用户又按了快捷键），直接丢弃
        if self._last_frame is None:
            return

        # 保存结果
        if ocr_type == 'relic':
            self._last_relics = results
            if results:
                names = ' | '.join(n for n, _ in results)
                self._log(f"[遗物识别] {len(results)} 个: {names}", source="_on_ocr_done")
            else:
                self._log("[遗物识别] 未找到候选", source="_on_ocr_done")
        elif ocr_type == 'item':
            self._last_items = results
            if results:
                names = ' | '.join(t[0] for t in results[:8])
                self._log(f"[物品识别] {len(results)} 个: {names}{'...' if len(results) > 8 else ''}", source="_on_ocr_done")
            else:
                self._log("[物品识别] 未找到候选", source="_on_ocr_done")
        elif ocr_type == 'text':
            self._last_texts = results
            if results:
                self._log(f"[文本识别] {len(results)} 行", source="_on_ocr_done")
            else:
                self._log("[文本识别] 未找到文本", source="_on_ocr_done")

        callback(results)

    # ============================================================
    # 功能模式处理
    # ============================================================

    def _on_mode_selected(self, mode: str):
        """用户点击功能按钮。"""
        ocr_type = FEATURE_TOGGLE_REQUIRES.get(mode)

        if self._last_frame is None:
            self._overlay.display(S("overlay", "please_screenshot_first"), auto_hide_ms=3000)
            return

        # 已有该类型 OCR 结果 → 直接执行
        if ocr_type == 'relic' and self._last_relics:
            self._execute_mode(mode)
            return
        if ocr_type == 'item' and self._last_items:
            self._execute_mode(mode)
            return
        if ocr_type == 'text' and self._last_texts:
            self._execute_mode(mode)
            return

        # 需要 OCR
        self._overlay.display(S("overlay", "ocr_recognizing"), auto_hide_ms=5000)

        def _callback(results):
            if not results:
                no_result_msgs = {
                    'relic': "no_relics_detected",
                    'item': "no_items_detected",
                    'text': "no_text_detected",
                }
                msg_key = no_result_msgs.get(ocr_type, "no_items_detected")
                self._overlay.display(S("overlay", msg_key), auto_hide_ms=3000)
                return
            self._execute_mode(mode)

        self._start_ocr(ocr_type, _callback)

    def _execute_mode(self, mode: str):
        handlers = {
            "check_status": self._handle_check_status,
            "query_parts": self._handle_query_parts,
            "query_price": self._handle_query_price,
            "translate": self._handle_translate,
        }
        handler = handlers.get(mode)
        if handler:
            handler()
        else:
            self._log(f"未知模式: {mode}", "warn", "_execute_mode")

    # ---- 出入库查询 ----

    def _handle_check_status(self):
        self._log("出入库查询 — 开始标注", source="_handle_check_status")
        annotations = []
        dpi = self._overlay._dpi_scale
        region = self._last_region

        for name, box in self._last_relics:
            sx = int(region[0] + box[0][0] / dpi)
            sy = int(region[1] + box[0][1] / dpi - 28)
            info = self._relic_db.find(name)
            if info:
                if info.get('vaulted', False):
                    color, label = COLOR_VAULTED, f"{name} [{S('overlay', 'relic_vaulted')}]"
                else:
                    color, label = COLOR_AVAILABLE, f"{name} [{S('overlay', 'relic_available')}]"
            else:
                color, label = COLOR_UNKNOWN, f"{name} [?]"
            annotations.append((label, sx, sy, 8000, color))

        self._overlay.show_annotations_stream(
            annotations, auto_hide_ms=8000, interval_ms=30, batch_size=2)
        self._overlay.display(
            S.format("overlay", "annotations_shown", count=len(annotations)), auto_hide_ms=5000)

    # ---- 遗物内容查询 ----

    def _handle_query_parts(self):
        self._log("遗物内容查询 — 开始匹配", source="_handle_query_parts")
        annotations = []
        matched = 0
        unmatched_names = []
        dpi = self._overlay._dpi_scale
        region = self._last_region

        for name, box in self._last_relics:
            sx = int(region[0] + box[0][0] / dpi)
            sy = int(region[1] + box[0][1] / dpi - 28)
            info = self._relic_db.find(name)
            if not info:
                unmatched_names.append(name)
                annotations.append(
                    (S.format("overlay", "relic_no_parts_info", name=name), sx, sy, 10000, FALLBACK_COLOR))
                continue

            matched += 1
            parts = info.get('parts', [])
            vaulted = info.get('vaulted', False)
            status_color = COLOR_VAULTED if vaulted else COLOR_AVAILABLE
            status = S("overlay", "relic_vaulted") if vaulted else S("overlay", "relic_available")

            lines = [f"{name} [{status}]"]
            line_colors = [status_color]
            sorted_parts = sorted(parts, key=lambda p: p.get('chance', 0))
            chances = sorted(set(p.get('chance', 0) for p in sorted_parts))
            extra_lines, extra_colors = self._map_rarity_colors(chances, sorted_parts)
            lines.extend(extra_lines)
            line_colors.extend(extra_colors)
            label = "\n".join(lines)
            annotations.append((label, sx, sy, 10000, status_color, line_colors))

        self._overlay.show_annotations_stream(
            annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

        total = len(self._last_relics)
        if unmatched_names:
            summary = S.format("overlay", "query_summary_fmt",
                total=total, matched=matched, unmatched=', '.join(unmatched_names))
        else:
            summary = S.format("overlay", "query_summary", total=total, matched=matched)
        summary += S("overlay", "query_legend")
        self._overlay.display(summary, auto_hide_ms=6000)

        self._log(f"匹配: {matched}/{total}", source="_handle_query_parts")
        if unmatched_names:
            self._log(f"未匹配: {', '.join(unmatched_names)}", "warn", "_handle_query_parts")

    @staticmethod
    def _map_rarity_colors(chances, sorted_parts):
        if len(chances) >= 3:
            chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_SILVER, chances[2]: COLOR_COPPER}
        elif len(chances) == 2:
            chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_COPPER}
        else:
            chance_to_color = {chances[0]: COLOR_SILVER}

        lines, colors = [], []
        for p in sorted_parts:
            ch = p.get('chance', 0)
            clr = chance_to_color.get(ch, COLOR_SILVER)
            prefix = "●" if ch == chances[0] else ("◦" if len(chances) > 1 and ch == chances[-1] else "◈")
            lines.append(f"  {prefix} {p['name']}")
            colors.append(clr)
        return lines, colors

    # ---- 翻译 ----

    def _handle_translate(self):
        self._log("翻译 — 开始处理", source="_handle_translate")
        if not self._last_items:
            self._overlay.display(S("overlay", "no_text_detected"), auto_hide_ms=3000)
            return

        from recognizers.item_name import match_and_translate
        translated = match_and_translate(self._last_items)
        if not translated:
            self._overlay.display(S("overlay", "translate_failed"), auto_hide_ms=3000)
            return

        annotations = []
        dpi = self._overlay._dpi_scale
        region = self._last_region

        print(f"[显示-翻译] ===== 渲染 {len(translated)} 条翻译标注 =====", flush=True)
        for item in translated:
            en_name = item.get('en_name', item.get('ocr_text', ''))
            zh_name = item.get('zh_name', '')
            quality = item.get('match_quality', 'none')
            box = item['box']
            sx = int(region[0] + box[0][0] / dpi)
            sy = int(region[1] + box[0][1] / dpi - 28)

            if quality == 'exact':
                color = COLOR_AVAILABLE
            elif quality in ('prefix', 'contains'):
                color = COLOR_VAULTED
            else:
                color = COLOR_UNKNOWN

            label = S.format("overlay", "translate_label_fmt", zh_name=zh_name, en_name=en_name) if (zh_name and zh_name != en_name) else en_name

            # ★ 日志
            print(f"[显示-翻译] OCR=\"{item.get('ocr_text')}\" | 匹配=\"{en_name}\" | zh=\"{zh_name}\" | "
                  f"quality={quality} | 坐标=({sx},{sy}) | 显示文字=\"{label}\"", flush=True)

            annotations.append((label, sx, sy, 10000, color))

        self._overlay.show_annotations_stream(
            annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

        matched = sum(1 for t in translated if t.get('match_quality', 'none') != 'none')
        self._overlay.display(
            S.format("overlay", "translate_summary", total=len(translated), matched=matched),
            auto_hide_ms=6000)
        self._log(f"翻译: {len(translated)}个候选 | 匹配 {matched}个", source="_handle_translate")

    # ---- 价格查询 ----

    def _handle_query_price(self):
        """价格查询：OCR → 匹配数据库 → 查价格 → 渲染覆盖层。"""
        if not self._last_items:
            print("[价格查询] self._last_items 为空！", flush=True)
            return

        # 匹配本地数据库 + 查询价格（含缓存）
        matched = match_and_price(self._last_items)
        if not matched:
            self._overlay.display(S("overlay", "no_items_detected"), auto_hide_ms=3000)
            return

        # 渲染到 overlay
        self._render_price_annotations(matched)

    def _render_price_annotations(self, matched):
        """渲染价格标注到 overlay。"""
        annotations = []
        dpi = self._overlay._dpi_scale
        region = self._last_region

        print(f"[显示-价格] ===== 渲染 {len(matched)} 条价格标注 =====", flush=True)
        for item in matched:
            box = item['box']
            sx = int(region[0] + box[0][0] / dpi)
            sy = int(region[1] + box[0][1] / dpi - 28)

            quality = item['match_quality']
            price = item.get('price')

            # 使用统一的价格颜色映射
            color = price_to_color(price, quality)

            # 使用统一的标注格式化
            label = format_price_annotation(item)

            # ★ 日志：每条标注的详细信息
            if price and price.get('sell_weighted') is not None:
                price_str = f'sell_weighted={price["sell_weighted"]}'
            else:
                price_str = str(price)
            display_name = build_display_name(item)
            print(f"[显示-价格] OCR=\"{item['ocr_text']}\" | 匹配=\"{item.get('matched_name', '')}\" | "
                  f"显示=\"{display_name}\" | quality={quality} | price={price_str} | "
                  f"坐标=({sx},{sy}) | 标注=\"{label}\"", flush=True)

            annotations.append((label, sx, sy, 15000, color))

        self._overlay.show_annotations_stream(
            annotations, auto_hide_ms=15000, interval_ms=40, batch_size=1)

        total = len(matched)
        with_price = sum(1 for m in matched if m.get('price') and m['price'].get('sell_weighted') is not None)
        realtime_count = sum(1 for m in matched if m.get('_price_source') == 'realtime')
        msg = S.format("overlay", "price_query_summary", total=total, with_price=with_price)
        if realtime_count > 0:
            msg += f" (实时 {realtime_count})"
        self._overlay.display(msg, auto_hide_ms=8000)
        self._log(f"价格查询: {total}个识别 | {with_price}个有价格 | 实时 {realtime_count}", source="_handle_query_price")


# ============================================================
# 入口
# ============================================================

import traceback
import atexit
from datetime import datetime

_CRASH_LOG_PATH = os.path.join(
    os.getenv('APPDATA', os.path.expanduser('~')),
    'WARFRAME-RELIC', 'crash_log.txt'
)


def _log_exception(exc_type, exc_value, exc_tb):
    """全局异常钩子：记录未捕获异常到 crash log。"""
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
        with open(_CRASH_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"崩溃时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"类型: {exc_type.__name__}: {exc_value}\n")
            f.write(f"堆栈:\n{error_msg}\n")
            f.write(f"{'=' * 60}\n")
        print(f"\n[崩溃] 异常已记录到: {_CRASH_LOG_PATH}", flush=True)
        print(error_msg, flush=True)
    except Exception:
        print(f"\n[崩溃] 无法写入日志文件:\n{error_msg}", flush=True)

    # 调用默认处理（打印到 stderr）
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _on_exit():
    """进程退出时的清理记录。"""
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
        with open(_CRASH_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"--- 进程退出: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except Exception:
        pass


def main():
    # ★ 安装全局异常钩子
    sys.excepthook = _log_exception
    atexit.register(_on_exit)

    # 确保日志目录存在
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    core = AppCore(app)
    core.run()


if __name__ == "__main__":
    main()
