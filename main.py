"""
WARFRAME-RELIC 主程序入口
- 截图识别 Warframe 遗物选择界面
- 出入库状态查询 + 遗物内容查询
- 通过快捷键操作，覆盖层显示结果
"""
import sys
import os

# 必须在 PyQt6 导入前设置
os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=0"
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*.warning=false"

import threading
import dxcam
import keyboard
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject, pyqtSignal, QThread
from PIL import Image

from core.overlay import Overlay
from core.management_panel import ManagementPanel
from core.hotkey_config import load_hotkeys, DEFAULT_HOTKEYS
from core.constants import (
    COLOR_VAULTED, COLOR_AVAILABLE, COLOR_UNKNOWN,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER, FALLBACK_COLOR,
    DXCAM_MAX_RETRIES, DXCAM_RETRY_BASE_SLEEP,
)
from recognizers.relic_name import RelicNameRecognizer
from data.wfinfo_relics import RelicDB


# ============================================================
# 信号桥接 & OCR 后台线程
# ============================================================

class TriggerBridge(QObject):
    """键盘热键 → Qt 信号桥接。"""
    fired = pyqtSignal(str)


class OCRWorker(QObject):
    """后台线程：执行 OCR 识别，完成后发射信号。"""
    finished = pyqtSignal(list)  # [(name, box), ...]

    def __init__(self, recognizer: RelicNameRecognizer, frame):
        super().__init__()
        self._recognizer = recognizer
        self._frame = frame

    def run(self):
        relics = self._recognizer.recognize_all_with_boxes(self._frame)
        self.finished.emit(relics)


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

        # 信号桥接
        self._bridge = TriggerBridge()

        # 状态
        self._last_frame = None
        self._last_region = None
        self._last_relics = []
        self._ocr_done = False
        self._ocr_thread = None
        self._ocr_worker = None
        self._pending_mode = None
        self._screenshot_busy = False
        self._screenshot_lock = threading.Lock()  # 保护截图竞态
        self._registered_hotkeys = {}

    # ---- 启动 ----

    def run(self):
        self._init_db()
        self._bind_events()
        self._register_initial_hotkeys()
        self._start_timers()
        self._print_startup_info()

        # 注册退出清理
        self._app.aboutToQuit.connect(self._shutdown)

        # 自动打开管理面板
        from PyQt6.QtCore import QTimer as QtTimer
        QtTimer.singleShot(100, self._show_panel_on_start)
        self._app.exec()

    def _shutdown(self):
        """程序退出时的资源清理。"""
        # 1. 清理 OCR 线程
        self._cleanup_ocr_thread()
        # 2. 关闭数据库
        self._relic_db.close()
        # 3. 反注册所有键盘热键
        for hk_id in self._registered_hotkeys.values():
            try:
                keyboard.remove_hotkey(hk_id)
            except Exception:
                pass
        self._registered_hotkeys.clear()
        # 4. 释放摄像头（dxcam 在进程退出时自动释放，此处显式清理引用）
        self._camera = None
        print("[退出] 资源已清理")

    def _show_panel_on_start(self):
        self._management_panel.show()
        self._management_panel.raise_()
        self._management_panel.activateWindow()
        self._management_panel.adjustSize()
        self._management_panel.resize(580, 840)

    # ---- 摄像头 ----

    @staticmethod
    def _create_camera_with_retry(max_retries=DXCAM_MAX_RETRIES):
        import time as _time
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
                    _time.sleep(wait)
        raise RuntimeError(
            f"无法初始化 dxcam 摄像头（已重试 {max_retries} 次）: {last_err}\n"
            f"请检查:\n"
            f"  - 是否有其他程序正在使用摄像头（如 OBS、SteamVR 等）\n"
            f"  - 显卡驱动是否正常\n"
            f"  - 是否安装了 DirectX 运行时")

    # ---- 数据库 ----

    def _init_db(self):
        if not self._relic_db.load():
            print("[警告] 遗物数据库加载失败，遗物内容查询将不可用")

    def reload_db(self, db_path: str):
        self._log("管理面板 数据库已更新，重新加载...")
        self._relic_db.invalidate()  # 线程安全地关闭旧连接
        if self._relic_db.load():
            stats = self._relic_db.stats()
            self._log(f"  重新加载完成: {stats['total_relics']} 个遗物 | "
                      f"入库 {stats['available']} | 出库 {stats['vaulted']}", "ok")
        else:
            self._log("[警告] 数据库重新加载失败", "error")

    # ---- 日志 ----

    def _log(self, msg: str, log_type: str = "info"):
        """写入管理面板日志。参数顺序：(消息, 类型)。"""
        self._management_panel.add_log(log_type, msg)

    # ---- 事件绑定 ----

    def _bind_events(self):
        self._overlay.on_selection_done = self.do_screenshot
        self._overlay.mode_selected.connect(self.on_mode_selected)
        self._bridge.fired.connect(self._handle_trigger)
        self._management_panel.db_updated.connect(self.reload_db)
        self._management_panel.hotkeys_changed.connect(self._on_hotkeys_changed)
        self._management_panel.theme_changed.connect(self._on_theme_changed)

    # ---- 热键 ----

    def _handle_trigger(self, action):
        if action == 'select':
            self._overlay.start_selection()
        elif action == 'panel':
            self._toggle_panel()
        elif action == 'fullscreen':
            self.do_screenshot_fullscreen()

    def _toggle_panel(self):
        if self._management_panel.isVisible():
            self._management_panel.hide()
        else:
            self._management_panel.adjustSize()
            self._management_panel.show()
            self._management_panel.raise_()
            self._management_panel.activateWindow()

    def _register_hotkeys(self, hotkeys: dict):
        for hk in self._registered_hotkeys.values():
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self._registered_hotkeys.clear()

        action_map = {
            "select": "select", "fullscreen": "fullscreen", "panel": "panel",
        }
        for action, action_name in action_map.items():
            hk_str = hotkeys.get(action, DEFAULT_HOTKEYS[action])
            try:
                hk_id = keyboard.add_hotkey(
                    hk_str, lambda a=action_name: self._bridge.fired.emit(a))
                self._registered_hotkeys[hk_str] = hk_id
            except Exception as e:
                print(f"[警告] 注册热键失败 {hk_str}: {e}")

    def _register_initial_hotkeys(self):
        self._register_hotkeys(load_hotkeys())

    def _on_hotkeys_changed(self, new_hotkeys):
        print(f"[热键] 快捷键已更新: {new_hotkeys}")
        self._register_hotkeys(new_hotkeys)

    def _on_theme_changed(self):
        """主题变更时刷新 Overlay 缓存的样式（管理面板自身已刷新）。"""
        self._overlay.refresh_theme()

    # ---- 定时器 ----

    def _start_timers(self):
        hide_timer = QTimer()
        hide_timer.timeout.connect(self._overlay._check_auto_hide)
        hide_timer.start(100)

    # ---- 启动信息 ----

    def _print_startup_info(self):
        db_stats = self._relic_db.stats()
        hotkeys_config = load_hotkeys()

        self._log("程序已启动")
        self._log(f"  {hotkeys_config['select']:<16}→ 框选区域截图识别（松手自动识别）")
        self._log(f"  {hotkeys_config['fullscreen']:<16}→ 全屏截图识别（跳过框选，直接识别）")
        self._log(f"  {hotkeys_config['panel']:<16}→ 打开管理面板（更新数据库/查看状态）")
        self._log("  右键          → 取消框选 / 清除标注 / 关闭功能选择")
        self._log("  识别后会弹出功能选择按钮：")
        self._log("    [出入库查询]  — 标注遗物名称（绿=出库 红=入库）")
        self._log("    [遗物内容查询] — 匹配遗物对应的 Prime 部件（带颜色）")
        self._log(f"  [WFInfo 数据库] 总计 {db_stats['total_relics']} 个遗物"
                  f" | 入库 {db_stats['available']} | 出库 {db_stats['vaulted']}")

    # ============================================================
    # 截图 & OCR
    # ============================================================

    def do_screenshot(self):
        """框选区域截图 → 后台 OCR（线程安全）。"""
        with self._screenshot_lock:
            if self._screenshot_busy:
                return
            self._screenshot_busy = True

        region = self._overlay.get_region()
        if region is None:
            self._overlay.display("请先按 Ctrl+G 框选截图区域", auto_hide_ms=3000)
            with self._screenshot_lock:
                self._screenshot_busy = False
            return

        dpi = self._overlay._dpi_scale
        phys_region = (
            int(region[0] * dpi), int(region[1] * dpi),
            int(region[2] * dpi), int(region[3] * dpi),
        )
        frame = self._camera.grab(region=phys_region)
        if frame is None:
            self._overlay.display("截图失败", auto_hide_ms=3000)
            with self._screenshot_lock:
                self._screenshot_busy = False
            return

        self._process_frame(frame, region)

    def do_screenshot_fullscreen(self):
        """全屏截图 → 后台 OCR（线程安全）。"""
        with self._screenshot_lock:
            if self._screenshot_busy:
                return
            self._screenshot_busy = True

        # 全屏截图前自动清除旧标注，避免覆盖层内容被截入
        if self._overlay.is_showing_content():
            self._overlay.clear_annotations()
            self._overlay._hide_mode_buttons()
            self._overlay.label.clear()
            self._log("[全屏截图] 自动清除旧标注和按钮", "info")

        self._log("=== 全屏截图模式 ===")

        dpi = self._overlay._dpi_scale
        full_phys = (0, 0, self._camera.width, self._camera.height)
        full_logical = (0, 0, int(self._camera.width / dpi), int(self._camera.height / dpi))

        frame = self._camera.grab(region=full_phys)
        if frame is None:
            self._overlay.display("全屏截图失败", auto_hide_ms=3000)
            with self._screenshot_lock:
                self._screenshot_busy = False
            return

        self._overlay.display(
            f"全屏截图 ({self._camera.width}x{self._camera.height})", auto_hide_ms=2000)
        self._process_frame(frame, full_logical)

    def _process_frame(self, frame, region):
        """截图后：保存调试图 → 显示按钮 → 启动 OCR 后台线程。"""
        # 保存调试截图
        img = Image.fromarray(frame[:, :, ::-1])
        save_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
        os.makedirs(save_dir, exist_ok=True)
        img.save(os.path.join(save_dir, 'last_capture.png'))

        self._last_relics = []
        self._overlay.show_mode_buttons()
        self._start_ocr_async(frame, region)

    def _start_ocr_async(self, frame, region):
        """启动后台 OCR 线程。"""
        self._cleanup_ocr_thread()
        self._ocr_done = False
        self._last_frame = frame
        self._last_region = region

        self._ocr_thread = QThread()
        self._ocr_worker = OCRWorker(self._relic_ocr, frame)
        self._ocr_worker.moveToThread(self._ocr_thread)
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_thread.started.connect(self._ocr_worker.run)
        # 线程结束后自动触发清理
        self._ocr_thread.finished.connect(self._on_ocr_thread_done)
        self._ocr_thread.start()

    def _on_ocr_thread_done(self):
        """OCR 线程自然结束后的清理回调。"""
        if self._ocr_thread:
            self._ocr_thread.deleteLater()
            self._ocr_thread = None
            self._ocr_worker = None
        with self._screenshot_lock:
            self._screenshot_busy = False

    def _cleanup_ocr_thread(self):
        """安全退出上一轮 OCR 线程（如仍在运行则强制中断）。"""
        thread = self._ocr_thread
        worker = self._ocr_worker
        self._ocr_thread = None
        self._ocr_worker = None

        if thread is None:
            return
        if thread.isRunning():
            thread.quit()
            if not thread.wait(2000):  # 最多等 2 秒
                thread.terminate()
                thread.wait()
        # 断开所有信号防止野回调
        try:
            thread.started.disconnect()
        except Exception:
            pass
        try:
            thread.finished.disconnect()
        except Exception:
            pass
        if worker:
            try:
                worker.finished.disconnect()
            except Exception:
                pass
        thread.deleteLater()

    def _on_ocr_finished(self, relics):
        """OCR 完成回调。"""
        self._last_relics = relics
        self._ocr_done = True
        with self._screenshot_lock:
            self._screenshot_busy = False

        if relics:
            relic_names = ' | '.join(n for n, _ in relics)
            self._log(f"[识别] {relic_names}")
            self._overlay.label.setText(f"识别到 {len(relics)} 个遗物 — 请选择操作：")
            self._overlay.label.adjustSize()
            self._overlay.label.move(
                (self._overlay.width() - self._overlay.label.width()) // 2, 20)
            self._overlay.label.show()
        else:
            self._overlay._hide_mode_buttons()
            self._overlay.display("未识别到遗物", auto_hide_ms=3000)

        # 用户在 OCR 完成前就选了模式 → 立即执行
        if self._pending_mode:
            mode = self._pending_mode
            self._pending_mode = None
            if relics:
                self.on_mode_selected(mode)
            else:
                self._overlay.display("没有可用的识别结果，请重新截图", auto_hide_ms=3000)

    # ============================================================
    # 功能模式处理
    # ============================================================

    def on_mode_selected(self, mode: str):
        """用户点击功能按钮 → 等待 OCR 完成（如需要）→ 执行。"""
        if not self._ocr_done:
            self._pending_mode = mode
            self._overlay.display("正在识别中，请稍候...", auto_hide_ms=5000)
            self._log(f"[等待] 用户选择了 {mode}，等待 OCR 完成...")
            return
        if not self._last_relics:
            self._overlay.display("没有可用的识别结果，请重新截图", auto_hide_ms=3000)
            return

        if mode == "check_status":
            self._handle_check_status()
        elif mode == "query_parts":
            self._handle_query_parts()

    # ---- 出入库查询 ----

    def _handle_check_status(self):
        self._log("=== 出入库查询模式 ===")
        annotations = []
        dpi = self._overlay._dpi_scale
        region = self._last_region

        for name, box in self._last_relics:
            sx = int(region[0] + box[0][0] / dpi)
            sy = int(region[1] + box[0][1] / dpi - 28)

            info = self._relic_db.find(name)
            if info:
                if info.get('vaulted', False):
                    color, label = COLOR_VAULTED, f"{name} [出库]"
                else:
                    color, label = COLOR_AVAILABLE, f"{name} [入库]"
            else:
                color, label = COLOR_UNKNOWN, f"{name} [?]"
            annotations.append((label, sx, sy, 8000, color))

        self._overlay.show_annotations_stream(
            annotations, auto_hide_ms=8000, interval_ms=30, batch_size=2)
        self._overlay.display(f"已显示 {len(annotations)} 个遗物（右键清除）", auto_hide_ms=5000)

    # ---- 遗物内容查询 ----

    def _handle_query_parts(self):
        self._log("=== 遗物内容查询 ===")
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
                    (f"{name}\n  (未找到部件信息)", sx, sy, 10000, FALLBACK_COLOR))
                continue

            matched += 1
            parts = info.get('parts', [])
            vaulted = info.get('vaulted', False)
            status_color = COLOR_VAULTED if vaulted else COLOR_AVAILABLE
            status = "出库" if vaulted else "入库"

            lines = [f"{name} [{status}]"]
            line_colors = [status_color]

            sorted_parts = sorted(parts, key=lambda p: p.get('chance', 0))
            chances = sorted(set(p.get('chance', 0) for p in sorted_parts))
            self._map_rarity_colors(chances, sorted_parts, lines, line_colors)

            label = "\n".join(lines)
            annotations.append((label, sx, sy, 10000, status_color, line_colors))

        self._overlay.show_annotations_stream(
            annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

        total = len(self._last_relics)
        summary = f"遗物内容查询: {total}个 | 匹配 {matched}个"
        if unmatched_names:
            summary += f" | 未匹配: {', '.join(unmatched_names)}"
        summary += "\n(★金=稀有  ◆银=罕见  ·铜=常见  绿=出库  红=入库)"
        self._overlay.display(summary, auto_hide_ms=6000)

        self._log(f"  匹配: {matched}/{total}")
        if unmatched_names:
            self._log(f"  未匹配: {', '.join(unmatched_names)}", "warn")

    @staticmethod
    def _map_rarity_colors(chances, sorted_parts, lines, line_colors):
        """将稀有度映射到颜色：金/银/铜。"""
        if len(chances) >= 3:
            chance_to_color = {
                chances[0]: COLOR_GOLD, chances[1]: COLOR_SILVER, chances[2]: COLOR_COPPER}
        elif len(chances) == 2:
            chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_COPPER}
        else:
            chance_to_color = {chances[0]: COLOR_SILVER}

        for p in sorted_parts:
            ch = p.get('chance', 0)
            clr = chance_to_color.get(ch, COLOR_SILVER)
            if ch == chances[0]:
                prefix = "★"
            elif len(chances) > 1 and ch == chances[-1]:
                prefix = "·"
            else:
                prefix = "◆"
            lines.append(f"  {prefix} {p['name']}")
            line_colors.append(clr)


# ============================================================
# 入口
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    core = AppCore(app)
    core.run()


if __name__ == "__main__":
    main()
