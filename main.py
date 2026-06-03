"""
WARFRAME-RELIC 主程序
- 截图识别 Warframe 遗物选择界面
- 出入库状态查询 + 遗物内容查询
- 通过快捷键操作，覆盖层显示结果

核心逻辑链路：
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
    DXCAM_MAX_RETRIES, DXCAM_RETRY_BASE_SLEEP,
)
from core.price_service import clear_price_cache
from core.hotkey_manager import HotkeyManager
from core.mode_handlers import (
    handle_check_status, handle_query_parts, handle_translate,
    handle_query_price, strip_refinement,
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
        self._last_frame = None
        self._last_region = None
        self._last_relics = []
        self._last_items = []
        self._last_texts = []

        # ---- OCR 线程 ----
        self._ocr_thread = None
        self._ocr_worker = None
        self._ocr_lock = threading.Lock()

        # ---- 热键管理器 ----
        self._hotkey_mgr = HotkeyManager(self._bridge, self._log)

    # ================================================================
    # 启动 & 清理
    # ================================================================

    def run(self):
        self._init_db()
        self._bind_events()
        self._hotkey_mgr.register_initial()
        self._print_startup_info()
        self._app.aboutToQuit.connect(self._shutdown)
        QTimer.singleShot(100, self._show_panel_on_start)

        # 快捷键健康心跳：每 30 秒检查一次
        self._hotkey_health_timer = QTimer()
        self._hotkey_health_timer.timeout.connect(self._hotkey_mgr.auto_recover)
        self._hotkey_health_timer.start(30000)

        self._app.exec()

    def _shutdown(self):
        """清理所有运行缓存和资源。"""
        self._kill_ocr_thread()
        self._clear_results()
        self._overlay.clear_annotations()
        self._overlay.close()
        self._relic_db.close()
        self._hotkey_mgr.clear()
        self._camera = None
        clear_price_cache()
        print("[退出] 所有运行缓存已清理，程序退出")

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
        panel = self._management_panel
        self._position_panel_on_screen()
        panel._fix_initial_size()          # 先定尺寸 + 背景图
        panel._first_show = False          # 阻止 showEvent 再次触发
        panel._update_panel.enable_auto_show()
        panel.show()
        panel.raise_()
        panel.activateWindow()

    # ---- 事件绑定 ----

    def _bind_events(self):
        self._restore_default_selection_callback()
        self._overlay.on_selection_done = self._on_selection_done
        self._overlay.mode_selected.connect(self._on_mode_selected)
        self._bridge.fired.connect(self._on_hotkey)
        self._management_panel.db_updated.connect(self.reload_db)
        self._management_panel.hotkeys_changed.connect(self._hotkey_mgr.on_config_changed)
        self._management_panel.theme_changed.connect(self._on_theme_changed)
        self._management_panel.reset_requested.connect(self._on_reset)
        self._management_panel.feature_toggles_changed.connect(self._on_feature_toggles_changed)
        self._management_panel.item_region_select_requested.connect(self._on_item_region_select)

    # ---- 热键触发 ----

    def _on_hotkey(self, action):
        """所有快捷键的统一入口（防重入）。"""
        now = time.time()

        if now - self._hotkey_mgr.last_action_time < 0.5:
            print(f"[快捷键] 忽略重复触发: {action} (间隔 {now - self._hotkey_mgr.last_action_time:.2f}s)", flush=True)
            return
        self._hotkey_mgr.last_action_time = now

        print(f"[快捷键] ✓ 触发: {action} | 线程安全={self._hotkey_mgr.health_check()}", flush=True)

        if action == 'select':
            self._overlay.start_selection()
        elif action == 'fullscreen':
            self._kill_ocr_thread()
            self._clear_results()
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            self._do_fullscreen_screenshot()
        elif action == 'query_price':
            self._kill_ocr_thread()
            self._clear_results()
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            self._do_price_query()

    # ---- 回调处理 ----

    def _on_theme_changed(self):
        self._overlay.refresh_theme()

    def _on_feature_toggles_changed(self, toggles: dict):
        self._feature_toggles = toggles
        self._log(f"功能开关已更新: {toggles}", "ok", "_on_feature_toggles_changed")

    def _on_reset(self):
        """紧急排障：从根本解决一切可能的异常状态。"""
        self._log(S("log_msg", "reset_start"), "info", "_on_reset")
        errors = []

        # 1. 终止 OCR 线程
        try:
            self._kill_ocr_thread()
            self._log("  ✓ OCR 线程已终止", "info", "_on_reset")
        except Exception as e:
            errors.append(f"终止 OCR 线程: {e}")

        # 2. 清空缓存
        try:
            self._clear_results()
            self._log("  ✓ 缓存数据已清空", "info", "_on_reset")
        except Exception as e:
            errors.append(f"清空缓存: {e}")

        # 3. 清除 Overlay 视觉元素
        try:
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            if hasattr(self._overlay, '_preview_label'):
                self._overlay._preview_label.hide()
            self._log("  ✓ Overlay 视觉元素已清除", "info", "_on_reset")
        except Exception as e:
            errors.append(f"清除 Overlay: {e}")

        # 4. 退出框选模式
        try:
            if self._overlay._region_selector.is_active:
                self._overlay.end_selection()
                self._log("  ✓ 已退出框选模式", "info", "_on_reset")
        except Exception as e:
            errors.append(f"退出框选: {e}")

        # 5. 恢复鼠标穿透
        try:
            self._overlay._apply_mouse_passthrough(True)
            self._log("  ✓ 鼠标穿透已恢复", "info", "_on_reset")
        except Exception as e:
            errors.append(f"鼠标穿透: {e}")

        # 6. 强制重置快捷键
        try:
            self._hotkey_mgr.force_reset()
            self._log("  ✓ 快捷键已用默认值重新注册", "info", "_on_reset")
        except Exception as e:
            errors.append(f"注册快捷键: {e}")

        # 7. 重置配置文件
        try:
            save_hotkeys({})
            self._log("  ✓ hotkeys.json 已重置", "info", "_on_reset")
        except Exception as e:
            errors.append(f"保存 hotkeys.json: {e}")

        # 8. 摄像头健康检查
        try:
            if self._camera is None:
                self._camera = self._create_camera_with_retry()
                self._log("  ✓ 摄像头已重新初始化", "info", "_on_reset")
            else:
                self._log("  ✓ 摄像头正常", "info", "_on_reset")
        except Exception as e:
            errors.append(f"摄像头: {e}")

        # 9. 同步管理面板
        try:
            self._management_panel._hotkeys = dict(DEFAULT_HOTKEYS)
            self._management_panel._refresh_hotkey_ui()
            self._log("  ✓ 管理面板快捷键显示已同步", "info", "_on_reset")
        except Exception as e:
            errors.append(f"同步面板 UI: {e}")

        # 10. 健康诊断
        health_ok = self._hotkey_mgr.health_check()
        health_status = "✓ 健康" if health_ok else "✘ 异常"

        if errors:
            self._log(f"排障完成但有 {len(errors)} 个警告: {'; '.join(errors)}", "warn", "_on_reset")
        else:
            self._log(S("log_msg", "reset_done"), "ok", "_on_reset")
        self._log(f"快捷键健康状态: {health_status} | 已注册 {len(self._hotkey_mgr.registered)} 个热键",
                  "ok" if health_ok else "error", "_on_reset")

    # ---- 启动信息 ----

    def _print_startup_info(self):
        db_stats = self._relic_db.stats()
        hotkeys_config = load_hotkeys()
        self._log(S("log_msg", "startup"), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_select", hk=hotkeys_config['select']), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_fullscreen", hk=hotkeys_config['fullscreen']), source="_print_startup_info")
        self._log(S.format("log_msg", "startup_query_price", hk=hotkeys_config.get('query_price', 'ctrl+t')), source="_print_startup_info")
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

    def _on_selection_done(self):
        """框选完成回调。打断一切，从头开始。"""
        self._kill_ocr_thread()
        self._clear_results()
        self._overlay.clear_annotations()
        self._overlay._hide_mode_buttons()
        self._overlay.label.clear()

        region_info = self._overlay._region_selector.last_region
        if region_info is None:
            self._overlay.display(S("overlay", "please_select_first"), auto_hide_ms=3000)
            return

        logical = region_info['logical']
        phys = region_info['physical']
        phys_region = phys
        frame = self._camera.grab(region=phys_region)
        if frame is None:
            self._overlay.display(S("overlay", "screenshot_failed"), auto_hide_ms=3000)
            return

        self._after_screenshot(frame, logical)

    # ============================================================
    # 核心链路：全屏截图
    # ============================================================

    def _do_fullscreen_screenshot(self):
        """全屏截图。"""
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
        """管理面板请求设置物品区域。"""
        self._overlay._region_selector.set_callback(
            callback=self._on_item_region_selected,
            on_cancelled=self._on_item_region_cancelled,
        )
        self._overlay.start_selection()

    def _on_item_region_selected(self, region_info: dict):
        phys_xywh = region_info['physical_xywh']
        if save_item_region(phys_xywh):
            self._overlay.display(
                f"物品区域已保存！(x={phys_xywh['x']}, y={phys_xywh['y']}, "
                f"w={phys_xywh['w']}, h={phys_xywh['h']}) 将横向4等分",
                auto_hide_ms=4000)
            self._log(f"物品区域已保存: {phys_xywh}", "ok", "_on_item_region_selected")
        else:
            self._overlay.display("保存物品区域失败！", auto_hide_ms=3000)
            self._log("保存物品区域失败", "error", "_on_item_region_selected")
        self._restore_default_selection_callback()
        self._management_panel._refresh_item_region_status()

    def _on_item_region_cancelled(self):
        self._overlay.display("框选取消，区域未设置", auto_hide_ms=3000)
        self._restore_default_selection_callback()
        self._management_panel._refresh_item_region_status()

    def _restore_default_selection_callback(self):
        self._overlay._region_selector.set_callback(
            callback=self._on_region_selection_for_screenshot,
        )

    def _on_region_selection_for_screenshot(self, region_info: dict):
        self._on_selection_done()

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
        item_w = w // 4

        self._log(f"价格查询：区域=({x},{y},{w},{h}) 4等分每份宽={item_w}", source="_do_price_query")

        import ctypes
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)

        split_regions = []
        for i in range(4):
            ix = x + i * item_w
            rx = max(0, ix)
            ry = max(0, y)
            rw = min(item_w, screen_w - rx)
            rh = min(h, screen_h - ry)
            if rw > 0 and rh > 0:
                split_regions.append((rx, ry, rw, rh, f"子图{i+1}"))
        self._overlay.show_split_regions(split_regions, duration_ms=99999)
        self._overlay.display(S("overlay", "price_query_scanning"), auto_hide_ms=99999)

        self._do_price_query_capture(x, y, w, h, item_w, screen_w, screen_h)

    def _do_price_query_capture(self, x, y, w, h, item_w, screen_w, screen_h):
        """价格查询的截图+识别+标注阶段。一次截图 + numpy 切片。"""
        import numpy as np

        print(f"\n{'='*60}", flush=True)
        print(f"[价格查询] 开始截图+识别 (区域: {x},{y},{w},{h}, 4等分每份={item_w})", flush=True)
        print(f"{'='*60}", flush=True)

        full_rx = max(0, x)
        full_ry = max(0, y)
        full_rw = min(w, screen_w - full_rx)
        full_rh = min(h, screen_h - full_ry)
        if full_rw <= 0 or full_rh <= 0:
            self._overlay._clear_split_regions()
            self._overlay.display("物品区域超出屏幕范围", auto_hide_ms=3000)
            self._log("价格查询失败：物品区域超出屏幕范围", "warn", "_do_price_query")
            return

        dxcam_region = (full_rx, full_ry, full_rx + full_rw, full_ry + full_rh)
        print(f"\n[价格查询] 截取完整区域: ({full_rx},{full_ry}) {full_rw}x{full_rh}", flush=True)
        full_frame = self._camera.grab(region=dxcam_region)
        if full_frame is None:
            self._overlay._clear_split_regions()
            self._overlay.display("截图失败，请重试", auto_hide_ms=3000)
            self._log("价格查询截图失败（dxcam 返回 None）", "error", "_do_price_query")
            return

        print(f"[价格查询] 完整截图成功: {full_frame.shape[1]}x{full_frame.shape[0]}", flush=True)

        offset_x = full_rx - x
        offset_y = full_ry - y

        dpi = self._overlay._dpi_scale
        all_items = []
        for i in range(4):
            self._overlay.display(f"⟐ 正在识别第 {i+1}/4 个物品...", auto_hide_ms=2000)

            sub_x = i * item_w - offset_x
            sub_w = item_w
            sub_x = max(0, sub_x)
            sub_w = min(sub_w, full_rw - sub_x)
            if sub_w <= 0:
                self._log(f"第{i+1}个物品区域超出截图范围，跳过", "warn", "_do_price_query")
                continue

            sub_y = -offset_y
            sub_y = max(0, sub_y)
            sub_h = full_rh - sub_y
            if sub_h <= 0:
                self._log(f"第{i+1}个物品区域高度无效，跳过", "warn", "_do_price_query")
                continue

            sub_frame = full_frame[sub_y:sub_y + sub_h, sub_x:sub_x + sub_w]

            rx = full_rx + sub_x
            ry = full_ry + sub_y
            rw_actual = sub_w
            rh_actual = sub_h

            print(f"\n[价格查询] 子图{i+1}/4: 切片 ({sub_x},{sub_y}) {rw_actual}x{rh_actual} → 屏幕 ({rx},{ry})", flush=True)

            results = self._item_ocr.recognize_all_with_boxes(sub_frame)
            if results:
                for r_name, r_box, r_variants in results:
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

        print(f"\n{'='*60}", flush=True)
        print(f"[价格查询] 开始匹配+查价 (共 {len(all_items)} 个)", flush=True)
        print(f"{'='*60}", flush=True)
        self._last_items = all_items

        self._overlay.display(f"⟐ 正在查询 {len(all_items)} 个物品的价格...", auto_hide_ms=5000)
        QApplication.processEvents()

        matched = match_and_price(all_items)
        self._overlay._clear_split_regions()
        if matched:
            print(f"\n[价格查询] 匹配+查价完成: {len(matched)} 个", flush=True)
            for m in matched:
                price_info = ""
                if m.get('price') and m['price'].get('sell_weighted') is not None:
                    price_info = f" → {m['price']['sell_weighted']}p"
                print(f"  [{m['match_quality']}] \"{m.get('en_name','?')}\" ({m.get('zh_name','')}){price_info}", flush=True)
            from core.mode_handlers import render_price_annotations
            render_price_annotations(matched, None, dpi, self._overlay)
            total = len(matched)
            with_price = sum(1 for m in matched if m.get('price') and m['price'].get('sell_weighted') is not None)
            self._overlay.display(
                S.format("overlay", "price_query_summary", total=total, with_price=with_price),
                auto_hide_ms=8000)
        else:
            print(f"[价格查询] 匹配+查价: 无结果", flush=True)
            self._overlay.display("未能匹配到任何价格信息", auto_hide_ms=3000)

    # ============================================================
    # 截图后：保存 + 显示功能按钮
    # ============================================================

    def _after_screenshot(self, frame, region):
        """截图成功后的统一处理。"""
        img = Image.fromarray(frame[:, :, ::-1])
        save_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
        os.makedirs(save_dir, exist_ok=True)
        img.save(os.path.join(save_dir, 'last_capture.png'))

        self._last_frame = frame
        self._last_region = region
        self._last_relics = []
        self._last_items = []
        self._last_texts = []

        enabled_modes = [k for k, v in self._feature_toggles.items() if v]
        if enabled_modes:
            self._overlay.show_mode_buttons(enabled_modes)
        else:
            self._overlay.display(S("overlay", "screenshot_done"), auto_hide_ms=3000)

    # ============================================================
    # 清除方法
    # ============================================================

    def _clear_results(self):
        self._last_frame = None
        self._last_region = None
        self._last_relics = []
        self._last_items = []
        self._last_texts = []
        clear_price_cache()

    def _kill_ocr_thread(self):
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
    # OCR 线程
    # ============================================================

    def _start_ocr(self, ocr_type: str, callback):
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
        with self._ocr_lock:
            if self._ocr_thread:
                self._ocr_thread.deleteLater()
                self._ocr_thread = None
                self._ocr_worker = None

    def _on_ocr_done(self, results, ocr_type, callback):
        if self._last_frame is None:
            return

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

        # 已有 OCR 结果 → 直接执行
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
        """根据模式分发到对应的处理器（现在在 mode_handlers 中）。"""
        dpi = self._overlay._dpi_scale
        region = self._last_region
        overlay = self._overlay

        if mode == "check_status":
            self._log("出入库查询 — 开始标注", source="_handle_check_status")
            handle_check_status(self._last_relics, self._relic_db, region, dpi, overlay)

        elif mode == "query_parts":
            self._log("遗物内容查询 — 开始匹配", source="_handle_query_parts")
            matched, total, unmatched_names = handle_query_parts(
                self._last_relics, self._relic_db, region, dpi, overlay)
            self._log(f"匹配: {matched}/{total}", source="_handle_query_parts")
            if unmatched_names:
                self._log(f"未匹配: {', '.join(unmatched_names)}", "warn", "_handle_query_parts")

        elif mode == "query_price":
            self._log("价格查询 — 开始标注", source="_handle_query_price")
            result = handle_query_price(self._last_items, region, dpi, overlay)
            if result:
                total, with_price, realtime_count = result
                self._log(f"价格查询: {total}个识别 | {with_price}个有价格 | 实时 {realtime_count}", source="_handle_query_price")

        elif mode == "translate":
            self._log("翻译 — 开始处理", source="_handle_translate")
            result = handle_translate(self._last_items, region, dpi, overlay)
            if result:
                total, matched = result
                self._log(f"翻译: {total}个候选 | 匹配 {matched}个", source="_handle_translate")

        else:
            self._log(f"未知模式: {mode}", "warn", "_execute_mode")


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    from core.bootstrap import main
    main()
