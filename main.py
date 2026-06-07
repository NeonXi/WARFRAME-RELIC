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
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject, pyqtSignal, QThread
from PIL import Image

from core.overlay import Overlay
from core.management_panel import ManagementPanel
from core.splash_screen import SplashScreen
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
from core.trigger_manager import TriggerManager
from core.mode_handlers import (
    handle_check_status, handle_query_parts, handle_translate,
    handle_query_price_v2, strip_refinement,
)

from recognizers.relic_name import RelicNameRecognizer
from recognizers.item_name import ItemNameRecognizer
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
        # ★ 深拷贝 frame：dxcam 的 frame 是共享内存，跨线程访问可能在 COM 释放后崩溃
        self._frame = frame.copy() if frame is not None else None

    def run(self):
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
            k32.SetThreadPriority.restype = ctypes.c_int
            k32.SetThreadPriority(k32.GetCurrentThread(), 0x00004000)
        except Exception:
            pass
        print(f"[诊断-OCR] OCRWorker.run 开始, frame shape={self._frame.shape if self._frame is not None else 'None'}", flush=True)
        try:
            results = self._recognizer.recognize_all_with_boxes(self._frame)
            print(f"[诊断-OCR] OCRWorker.run 完成, results={len(results)} 条", flush=True)
            self.finished.emit(results)
        except Exception as e:
            print(f"[诊断-OCR] OCRWorker.run 异常: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.finished.emit([])


# ============================================================
# 应用核心控制器
# ============================================================

class AppCore:
    """截图、OCR、标注、热键等所有业务逻辑的中心控制器。"""

    def __init__(self, app: QApplication):
        self._app = app

        # UI 层（轻量，必须同步初始化）
        self._overlay = Overlay()
        self._overlay.show()
        self._management_panel = ManagementPanel()

        # 触发器引擎（轻量创建，启动推迟到后台加载完成后）
        self._trigger_manager = TriggerManager(log_func=self._log)
        self._management_panel._trigger_manager = self._trigger_manager
        # 注册 UI 焦点检查：操作管理面板/悬浮窗时跳过触发器，防止误触发
        self._trigger_manager.set_ui_focus_check(
            lambda: self._overlay.isActiveWindow()
                    or self._management_panel.isActiveWindow()
        )

        # 识别层（延迟初始化：界面显示后后台静默加载）
        self._relic_ocr: 'RelicNameRecognizer | None' = None
        self._item_ocr: 'ItemNameRecognizer | None' = None
        self._relic_db = RelicDB()  # 对象创建很快，load() 延迟到后台
        # 硬件层（延迟初始化）
        self._camera = None

        # 就绪标志（守卫竞态条件）
        self._ocr_ready = False
        self._camera_ready = False

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
        self._pending_mode = None  # ★ 用户在 OCR 运行时点击的模式，OCR 完成后自动执行

        # ---- 热键管理器 ----
        self._hotkey_mgr = HotkeyManager(self._bridge, self._log, app)

    # ================================================================
    # 启动 & 清理
    # ================================================================

    def run(self):
        self._bind_events()
        self._hotkey_mgr.register_initial()
        self._app.aboutToQuit.connect(self._shutdown)

        # ★ 先显示面板（用户立即看到界面）
        QTimer.singleShot(100, self._show_panel_on_start)

        # ★ 面板显示后打印启动日志 + 后台加载重型组件
        QTimer.singleShot(300, self._print_startup_info)
        QTimer.singleShot(500, self._lazy_init_background)

        self._app.exec()

    def _shutdown(self):
        """清理所有运行缓存和资源。"""
        # 停止触发器引擎
        if hasattr(self, '_trigger_manager') and self._trigger_manager:
            self._trigger_manager.stop()

        self._kill_ocr_thread()
        self._clear_results()
        self._overlay.clear_annotations()
        self._overlay.close()
        if self._relic_db:
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
        """延迟到后台加载（_lazy_init_background 中调用）。"""
        pass

    def _lazy_init_background(self):
        """后台线程静默加载所有重型组件：摄像头、OCR 模型、数据库。"""
        import threading

        def _load():
            try:
                # ── 1. 摄像头 ──
                self._log("正在初始化摄像头 (dxcam)...", "info", "_lazy_init")
                self._camera = self._create_camera_with_retry()
                self._camera_ready = True
                self._log("[ok] 摄像头初始化完成", "ok", "_lazy_init")

                # ── 2. 遗物 OCR ──
                self._log("正在加载遗物 OCR 模型...", "info", "_lazy_init")
                self._relic_ocr = RelicNameRecognizer()

                # ── 3. 物品 OCR ──
                self._log("正在加载物品 OCR 模型...", "info", "_lazy_init")
                self._item_ocr = ItemNameRecognizer()
                self._ocr_ready = True
                self._log("[ok] OCR 引擎初始化完成 (遗物 + 物品)", "ok", "_lazy_init")

                # ── 4. 遗物数据库 ──
                self._log("正在加载数据库...", "info", "_lazy_init")
                if not self._relic_db.load():
                    self._log("数据库未加载，请在管理面板中更新数据", "warn", "_lazy_init")
                else:
                    stats = self._relic_db.stats()
                    self._log(f"[ok] 数据库已就绪 -- {stats['total_relics']} 个遗物 | "
                              f"出库 {stats['available']} | 入库 {stats['vaulted']}", "ok", "_lazy_init")

                # ── 5. 触发器引擎 ──
                self._log("正在启动触发器引擎...", "info", "_lazy_init")
                self._trigger_manager.start()
                self._log("[ok] 触发器引擎已就绪", "ok", "_lazy_init")

                # ── 全部完成 ──
                self._log("=== 所有组件加载完成，程序就绪 ===", "ok", "_lazy_init")

            except Exception as e:
                self._log(f"[x] 后台组件初始化失败: {e}", "error", "_lazy_init")

        t = threading.Thread(target=_load, daemon=True, name="LazyInitWorker")
        t.start()

    def reload_db(self, db_path: str):
        self._log("数据库已更新，重新加载...", source="reload_db")
        self._relic_db.invalidate()
        if self._relic_db.load():
            stats = self._relic_db.stats()
            self._log(f"重新加载完成 -- {stats['total_relics']} 个遗物 | "
                      f"出库 {stats['available']} | 入库 {stats['vaulted']}", "ok", "reload_db")
        else:
            self._log("数据库重新加载失败", "error", "reload_db")

    # ---- 日志 ----

    def _log(self, msg: str, log_type: str = "info", source: str = ""):
        self._management_panel.add_log(log_type, msg, source)
        prefix = {"info": " ", "warn": "[!]", "error": "[x]", "ok": "[ok]"}.get(log_type, " ")
        src = f"[{source}] " if source else ""
        print(f"[{time.strftime('%H:%M:%S')}] {src}{prefix} {msg}", flush=True)

    # ---- 面板 ----

    def _show_panel_on_start(self):
        panel = self._management_panel
        panel._fix_initial_size()          # 先定尺寸 + 背景图
        panel._first_show = False          # 阻止 showEvent 再次触发
        panel._update_panel.enable_auto_show()
        panel.show()
        panel.raise_()
        panel.activateWindow()

        # 启动动画
        self._splash = SplashScreen(panel)
        self._splash.show()

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
        """所有快捷键的统一入口（防重入 + 就绪守卫）。"""
        now = time.time()

        if now - self._hotkey_mgr.last_action_time < 0.5:
            print(f"[快捷键] 忽略重复触发: {action} (间隔 {now - self._hotkey_mgr.last_action_time:.2f}s)", flush=True)
            return
        self._hotkey_mgr.last_action_time = now

        # ★ 就绪守卫：摄像头/OCR 还在后台加载中
        if not self._camera_ready:
            self._log("摄像头正在初始化，请稍候...", "warn", "_on_hotkey")
            return
        if action in ('select', 'fullscreen') and not self._ocr_ready:
            self._log("OCR 引擎正在初始化，请稍候...", "warn", "_on_hotkey")
            return

        print(f"[快捷键] OK 触发: {action} | 线程安全={self._hotkey_mgr.health_check()}", flush=True)

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
            # ★ 在后台线程执行价格查询，避免阻塞 Qt 事件循环
            import threading
            threading.Thread(target=self._do_price_query, daemon=True).start()

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
            self._log("  OK OCR 线程已终止", "info", "_on_reset")
        except Exception as e:
            errors.append(f"终止 OCR 线程: {e}")

        # 2. 清空缓存
        try:
            self._clear_results()
            self._log("  OK 缓存数据已清空", "info", "_on_reset")
        except Exception as e:
            errors.append(f"清空缓存: {e}")

        # 3. 清除 Overlay 视觉元素
        try:
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            if hasattr(self._overlay, '_preview_label'):
                self._overlay._preview_label.hide()
            self._log("  OK Overlay 视觉元素已清除", "info", "_on_reset")
        except Exception as e:
            errors.append(f"清除 Overlay: {e}")

        # 4. 退出框选模式
        try:
            if self._overlay._region_selector.is_active:
                self._overlay.end_selection()
                self._log("  OK 已退出框选模式", "info", "_on_reset")
        except Exception as e:
            errors.append(f"退出框选: {e}")

        # 5. 恢复鼠标穿透
        try:
            self._overlay._apply_mouse_passthrough(True)
            self._log("  OK 鼠标穿透已恢复", "info", "_on_reset")
        except Exception as e:
            errors.append(f"鼠标穿透: {e}")

        # 6. 强制重置快捷键
        try:
            self._hotkey_mgr.force_reset()
            self._log("  OK 快捷键已用默认值重新注册", "info", "_on_reset")
        except Exception as e:
            errors.append(f"注册快捷键: {e}")

        # 7. 重置配置文件
        try:
            save_hotkeys({})
            self._log("  OK hotkeys.json 已重置", "info", "_on_reset")
        except Exception as e:
            errors.append(f"保存 hotkeys.json: {e}")

        # 8. 摄像头健康检查
        try:
            if self._camera is None:
                self._camera = self._create_camera_with_retry()
                self._log("  OK 摄像头已重新初始化", "info", "_on_reset")
            else:
                self._log("  OK 摄像头正常", "info", "_on_reset")
        except Exception as e:
            errors.append(f"摄像头: {e}")

        # 9. 同步管理面板
        try:
            self._management_panel._hotkeys = dict(DEFAULT_HOTKEYS)
            self._management_panel._refresh_hotkey_ui()
            self._log("  OK 管理面板快捷键显示已同步", "info", "_on_reset")
        except Exception as e:
            errors.append(f"同步面板 UI: {e}")

        # 10. 健康诊断
        health_ok = self._hotkey_mgr.health_check()
        health_status = "OK" if health_ok else "ERROR"

        if errors:
            self._log(f"排障完成但有 {len(errors)} 个警告: {'; '.join(errors)}", "warn", "_on_reset")
        else:
            self._log(S("log_msg", "reset_done"), "ok", "_on_reset")
        self._log(f"快捷键健康状态: {health_status} | 已注册 {len(self._hotkey_mgr.registered)} 个热键",
                  "ok" if health_ok else "error", "_on_reset")

    # ---- 启动信息 ----

    def _print_startup_info(self):
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
        
        try:
            if self._relic_db._loaded:
                db_stats = self._relic_db.stats()
                self._log(S.format("log_msg", "startup_db_info",
                    total=db_stats['total_relics'], available=db_stats['available'],
                    vaulted=db_stats['vaulted']), "ok", "_print_startup_info")
            else:
                self._log("数据库后台加载中...", "info", "_print_startup_info")
        except Exception:
            self._log("数据库未加载，请在管理面板中更新数据", "warn", "_print_startup_info")

    # ============================================================
    # 核心链路：框选截图
    # ============================================================

    def _on_selection_done(self):
        """框选完成回调。打断一切，从头开始。"""
        # ★ 摄像头就绪守卫
        if not self._camera_ready or self._camera is None:
            self._overlay.display("摄像头正在初始化，请稍候...", auto_hide_ms=2000)
            return

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
        # ★ 摄像头就绪守卫
        if not self._camera_ready or self._camera is None:
            self._overlay.display("摄像头正在初始化，请稍候...", auto_hide_ms=2000)
            return

        if self._overlay.is_showing_content():
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()

        self._log("全屏截图 -- 开始识别", source="do_fullscreen")

        dpi = self._overlay._dpi_scale
        self._log(f"[诊断] 1/5 获取摄像头尺寸: {self._camera.width}x{self._camera.height}", source="do_fullscreen")
        full_phys = (0, 0, self._camera.width, self._camera.height)
        full_logical = (0, 0, int(self._camera.width / dpi), int(self._camera.height / dpi))

        self._log("[诊断] 2/5 调用 camera.grab() 截图...", source="do_fullscreen")
        frame = self._camera.grab(region=full_phys)
        self._log(f"[诊断] 3/5 截图完成: frame={'None' if frame is None else f'{frame.shape}'}", source="do_fullscreen")
        if frame is None:
            self._overlay.display(S("overlay", "fullscreen_failed"), auto_hide_ms=3000)
            return

        self._overlay.display(
            S.format("overlay", "fullscreen_info", w=self._camera.width, h=self._camera.height),
            auto_hide_ms=2000)
        self._log("[诊断] 4/5 进入 _after_screenshot...", source="do_fullscreen")
        self._after_screenshot(frame, full_logical)
        self._log("[诊断] 5/5 全屏截图流程完成", source="do_fullscreen")

    # ============================================================
    # 价格查询快捷键（4等分截图+识别）
    # ============================================================

    def _on_item_region_select(self, slot: str):
        """管理面板请求设置物品区域（指定槽位）。"""
        self._pending_region_slot = slot
        self._overlay._region_selector.set_callback(
            callback=self._on_item_region_selected,
            on_cancelled=self._on_item_region_cancelled,
        )
        self._overlay.start_selection()

    def _on_item_region_selected(self, region_info: dict):
        phys_xywh = region_info['physical_xywh']
        slot = getattr(self, '_pending_region_slot', '1')
        if save_item_region(phys_xywh, slot):
            self._overlay.display(
                f"区域 {slot} 已保存！(x={phys_xywh['x']}, y={phys_xywh['y']}, "
                f"w={phys_xywh['w']}, h={phys_xywh['h']}) 将横向4等分",
                auto_hide_ms=4000)
            self._log(f"物品区域 {slot} 已保存: {phys_xywh}", "ok", "_on_item_region_selected")
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
        # ★ 就绪守卫
        if not self._camera_ready or self._camera is None:
            self._overlay.display("摄像头正在初始化，请稍候...", auto_hide_ms=2000)
            return
        if not self._ocr_ready:
            self._overlay.display("OCR 引擎正在初始化，请稍候...", auto_hide_ms=2000)
            return
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
        print(f"[价格查询-调试] 4等分区域: {split_regions}", flush=True)
        print(f"[价格查询-调试] 屏幕尺寸(物理): {screen_w}x{screen_h}, DPI: {self._overlay._dpi_scale}", flush=True)
        self._overlay.display(S("overlay", "price_query_scanning"), auto_hide_ms=99999)

        # ★ 关键修改：先截图（屏幕上没有分割框），再显示分割框
        self._do_price_query_capture(x, y, w, h, screen_w, screen_h, split_regions)

    def _do_price_query_capture(self, x, y, w, h, screen_w, screen_h, split_regions):
        """价格查询的截图+识别+标注阶段。对4个格子分别截取+OCR+搜索。
        
        ★ 先截图（屏幕干净），再显示分割框（给用户看）
        ★ 优化：直接对每个格子做独立OCR，然后把该格子所有识别文本拼起来搜索
        """
        import numpy as np
        from data.market_items import fuzzy_search, query_prices_batch

        print(f"\n{'='*60}", flush=True)
        print(f"[价格查询] 开始截图+识别 (区域: {x},{y},{w},{h})", flush=True)
        print(f"{'='*60}", flush=True)

        # 截图完整区域
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

        # 截图成功后，显示分割框
        self._overlay.show_split_regions(split_regions, duration_ms=99999)

        dpi = self._overlay._dpi_scale

        # ============================================================
        # 对每个格子独立截取 + OCR + 搜索
        # ============================================================
        self._overlay.display(">> 正在识别物品...", auto_hide_ms=3000)

        matched_items = []
        url_names_to_query = []

        for idx, (rx, ry, rw, rh, label) in enumerate(split_regions):
            print(f"\n{'-'*60}", flush=True)
            print(f"[价格查询] 处理格子{idx+1}: ({rx},{ry}) {rw}x{rh}", flush=True)

            # 从完整截图中截取当前格子
            # 计算相对坐标：当前格子在完整截图中的位置
            crop_x = rx - full_rx
            crop_y = ry - full_ry
            crop_w = rw
            crop_h = rh

            if crop_x < 0 or crop_y < 0 or crop_x + crop_w > full_frame.shape[1] or crop_y + crop_h > full_frame.shape[0]:
                print(f"[价格查询] 格子{idx+1} 超出完整截图范围，跳过", flush=True)
                continue

            # 截取格子
            grid_frame = full_frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]

            # 识别该格子的所有文本（只识别，不分组）
            print(f"[价格查询] 格子{idx+1} OCR中...", flush=True)
            raw_lines = self._item_ocr.recognize_all_lines(grid_frame)
            print(f"[价格查询] 格子{idx+1} 识别到 {len(raw_lines)} 行: {raw_lines}", flush=True)

            if not raw_lines:
                print(f"[价格查询] 格子{idx+1} 无识别结果，跳过", flush=True)
                continue

            # 把所有文本拼起来（不做任何过滤，直接拼接）
            search_text = ' '.join(raw_lines)
            print(f"[价格查询] 格子{idx+1} 拼接搜索文本: \"{search_text}\"", flush=True)

            # 模糊搜索
            results = fuzzy_search(search_text, limit=5)
            if not results:
                print(f"[价格查询] 格子{idx+1} 搜索无结果，跳过", flush=True)
                continue

            best = results[0]
            print(f"[价格查询] 格子{idx+1} 最佳匹配: \"{best['zh_name']}\" ({best['en_name']}) "
                  f"距离={best['distance']} url={best['url_name']}", flush=True)

            # 构建全局坐标的box
            box = [
                [rx, ry],
                [rx + rw, ry],
                [rx + rw, ry + rh],
                [rx, ry + rh],
            ]

            matched_items.append({
                "ocr_text": search_text,
                "box": box,
                "en_name": best["en_name"],
                "zh_name": best["zh_name"],
                "url_name": best["url_name"],
                "distance": best["distance"],
                "source_relics": best.get("source_relics", []),
                "source_rarity": best.get("source_rarity", ""),
            })
            url_names_to_query.append(best["url_name"])

        print(f"\n{'-'*60}", flush=True)
        print(f"[价格查询] 匹配完成: {len(matched_items)} 个物品", flush=True)

        if not matched_items:
            print(f"[价格查询] 无匹配结果，结束", flush=True)
            self._overlay._clear_split_regions()
            self._overlay.display("未能识别到任何物品", auto_hide_ms=3000)
            return

        # ============================================================
        # 批量查询 WM API 价格
        # ============================================================
        print(f"\n{'='*60}", flush=True)
        print(f"[价格查询] 开始查询 {len(url_names_to_query)} 个物品的实时价格...", flush=True)
        print(f"{'='*60}", flush=True)
        self._overlay.display(f">> 正在查询 {len(url_names_to_query)} 个物品的实时价格...", auto_hide_ms=5000)

        prices = query_prices_batch(url_names_to_query, max_workers=4)

        # 合并价格数据
        with_price = 0
        for item in matched_items:
            url = item.get("url_name", "")
            if url and url in prices:
                item["price"] = prices[url]
                item["match_quality"] = "exact"
                with_price += 1
                p = prices[url]
                top10_prices = [str(o["platinum"]) for o in p["top10"]]
                print(f"[价格查询] {item['zh_name']}: {' / '.join(top10_prices)} 卖家={p['total_ingame']}", flush=True)
            elif url:
                item["match_quality"] = "no_price"
                print(f"[价格查询] {item['zh_name']}: 无价格数据", flush=True)
            else:
                item["match_quality"] = "none"
                print(f"[价格查询] {item['ocr_text']}: 未匹配", flush=True)

        # 渲染标注
        from core.mode_handlers import render_price_annotations_v2
        print(f"\n[价格查询] 渲染 {len(matched_items)} 条标注...", flush=True)
        render_price_annotations_v2(matched_items, (x, y, w, h), dpi, self._overlay)

        # 价格标注渲染完毕后清除区域框
        self._overlay._clear_split_regions()

        print(f"\n[价格查询] 完成: {len(matched_items)} 个物品, {with_price} 个有价格", flush=True)

    # ============================================================
    # 截图后：保存 + 显示功能按钮
    # ============================================================

    def _after_screenshot(self, frame, region):
        """截图成功后的统一处理。"""
        # ★ 仅调试模式保存截图到磁盘
        if int(os.getenv('WR_DEBUG', '0')):
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
            # ★ 预加载 OCR：截图后立即启动遗物 OCR（隐藏等待时间）
            self._start_eager_ocr(enabled_modes)
        else:
            self._overlay.display(S("overlay", "screenshot_done"), auto_hide_ms=3000)

    def _start_eager_ocr(self, enabled_modes):
        """截图后立即启动 OCR，让用户点击按钮时结果已就绪。"""
        import re
        relic_modes = [m for m in enabled_modes if re.match(r'check_status|query_parts', m)]
        item_modes = [m for m in enabled_modes if re.match(r'query_price|translate', m)]

        self._log(f"[诊断] _start_eager_ocr: relic_modes={relic_modes}, item_modes={item_modes}", source="eager_ocr")

        if relic_modes:
            self._log("[诊断] 启动遗物 OCR...", source="eager_ocr")
            self._start_ocr('relic', lambda results: None)
        elif item_modes:
            self._log("[诊断] 启动物品 OCR...", source="eager_ocr")
            self._start_ocr('item', lambda results: None)

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
        # ★ OCR 就绪守卫
        if not self._ocr_ready:
            self._log("OCR 引擎正在初始化，请稍候...", "warn", "_start_ocr")
            return

        # ★ 防止 OCR 线程重入：上一次还没完成则跳过
        if self._ocr_thread is not None and self._ocr_thread.isRunning():
            self._log(f"OCR 线程忙，跳过 {ocr_type}", "warn", "_start_ocr")
            return

        if ocr_type == 'relic':
            recognizer = self._relic_ocr
        elif ocr_type in ('item', 'text'):
            recognizer = self._item_ocr
        else:
            self._log(f"未知 OCR 类型: {ocr_type}", "error", "_start_ocr")
            return

        self._log(f"启动 OCR: {ocr_type}", source="_start_ocr")

        def _delayed_ocr():
            # 再次检查，防止 80ms 内状态变化
            if self._ocr_thread is not None and self._ocr_thread.isRunning():
                return
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
        import threading
        print(f"[诊断-OCR完成] ocr_type={ocr_type}, results={len(results) if results else 0}, "
              f"last_frame={'有' if self._last_frame is not None else 'None'}, "
              f"pending_mode={self._pending_mode}, "
              f"thread={threading.current_thread().name}", flush=True)
        try:
            if self._last_frame is None:
                print("[诊断-OCR完成] last_frame is None, 跳过", flush=True)
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

            # ★ 检查 pending_mode：用户在 OCR 运行时点击了功能按钮
            pending = self._pending_mode
            if pending:
                self._pending_mode = None
                print(f"[诊断-OCR完成] 执行 pending_mode={pending}", flush=True)
                self._execute_mode(pending)

        except Exception as e:
            print(f"[诊断-OCR完成] 异常: {e}", flush=True)
            import traceback
            traceback.print_exc()

    # ============================================================
    # 功能模式处理
    # ============================================================

    def _on_mode_selected(self, mode: str):
        """用户点击功能按钮。"""
        ocr_type = FEATURE_TOGGLE_REQUIRES.get(mode)
        print(f"[诊断-模式选择] mode={mode}, ocr_type={ocr_type}, "
              f"last_frame={'有' if self._last_frame is not None else 'None'}, "
              f"last_relics={len(self._last_relics) if self._last_relics else 0}, "
              f"last_items={len(self._last_items) if self._last_items else 0}, "
              f"last_texts={len(self._last_texts) if self._last_texts else 0}", flush=True)

        if self._last_frame is None:
            self._overlay.display(S("overlay", "please_screenshot_first"), auto_hide_ms=3000)
            return

        # 已有 OCR 结果 → 直接执行
        if ocr_type == 'relic' and self._last_relics:
            print(f"[诊断-模式选择] 已有 relic 结果，直接执行 {mode}", flush=True)
            self._execute_mode(mode)
            return
        if ocr_type == 'item' and self._last_items:
            print(f"[诊断-模式选择] 已有 item 结果，直接执行 {mode}", flush=True)
            self._execute_mode(mode)
            return
        if ocr_type == 'text' and self._last_texts:
            print(f"[诊断-模式选择] 已有 text 结果，直接执行 {mode}", flush=True)
            self._execute_mode(mode)
            return

        # ★ OCR 正在运行 → 存储 pending mode，OCR 完成后自动执行
        if self._ocr_thread is not None and self._ocr_thread.isRunning():
            print(f"[诊断-模式选择] OCR 正在运行，存储 pending_mode={mode}", flush=True)
            self._pending_mode = mode
            self._overlay.display(S("overlay", "ocr_recognizing"), auto_hide_ms=5000)
            return

        # 需要 OCR
        print(f"[诊断-模式选择] 无缓存结果，启动 OCR: {ocr_type}", flush=True)
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
        print(f"[诊断-执行模式] mode={mode}, relics={len(self._last_relics)}, items={len(self._last_items)}", flush=True)
        dpi = self._overlay._dpi_scale
        region = self._last_region
        overlay = self._overlay

        if mode == "check_status":
            self._log("出入库查询 -- 开始标注", source="_handle_check_status")
            handle_check_status(self._last_relics, self._relic_db, region, dpi, overlay)

        elif mode == "query_parts":
            self._log("遗物内容查询 -- 开始匹配", source="_handle_query_parts")
            matched, total, unmatched_names = handle_query_parts(
                self._last_relics, self._relic_db, region, dpi, overlay)
            self._log(f"匹配: {matched}/{total}", source="_handle_query_parts")
            if unmatched_names:
                self._log(f"未匹配: {', '.join(unmatched_names)}", "warn", "_handle_query_parts")

        elif mode == "query_price":
            self._log("价格查询V2 -- 开始标注", source="_handle_query_price_v2")
            total, with_price = handle_query_price_v2(
                self._last_items, region, dpi, overlay)
            self._log(f"价格查询V2: {total}个识别 | {with_price}个有价格", source="_handle_query_price_v2")

        elif mode == "translate":
            self._log("翻译 -- 开始处理", source="_handle_translate")
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
