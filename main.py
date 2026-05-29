import sys
import os

# 必须在 PyQt6 导入前设置，解决 Windows DPI 感知报错
os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=0"
# 抑制 Qt 的 qWarning/qDebug 日志（仅保留 qCritical/qFatal）
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*.warning=false"

import dxcam
import keyboard
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject, pyqtSignal, QThread
from PIL import Image
from core.overlay import Overlay
from core.management_panel import ManagementPanel
from core.hotkey_config import load_hotkeys, DEFAULT_HOTKEYS
from recognizers.relic_name import RelicNameRecognizer
from data.wfinfo_relics import RelicDB


class TriggerBridge(QObject):
    fired = pyqtSignal(str)


class OCRWorker(QObject):
    """后台线程：执行 OCR 识别，完成后发射信号"""
    finished = pyqtSignal(list)   # 发射 [(name, box), ...]

    def __init__(self, recognizer, frame):
        super().__init__()
        self._recognizer = recognizer
        self._frame = frame

    def run(self):
        relics = self._recognizer.recognize_all_with_boxes(self._frame)
        self.finished.emit(relics)


class AppCore:
    """应用核心控制器，管理截图、OCR、标注、热键等所有业务逻辑。"""

    def __init__(self, app: QApplication):
        self._app = app
        self._camera = self._create_camera_with_retry()
        self._overlay = Overlay()
        self._overlay.show()

        self._bridge = TriggerBridge()
        self._relic_ocr = RelicNameRecognizer()
        self._relic_db = RelicDB()
        self._management_panel = ManagementPanel()

        # ---- 共享状态 ----
        self._last_frame = None          # 最后一次截图的 numpy 数组 (BGR)
        self._last_region = None         # 最后一次截图的区域 (left,top,right,bottom)
        self._last_relics = []           # 最后一次 OCR 识别结果 [(name, box), ...]
        self._ocr_done = False           # OCR 是否已完成
        self._ocr_thread = None          # 后台 OCR 线程
        self._ocr_worker = None          # OCR worker 引用
        self._pending_mode = None        # 用户在 OCR 完成前选择的模式
        self._screenshot_busy = False    # 防重复触发
        self._registered_hotkeys = {}    # hotkey_str → 清理函数

    @staticmethod
    def _create_camera_with_retry(max_retries: int = 5):
        """创建 dxcam 摄像头，带重试机制。
        
        dxcam 依赖 DXGI DuplicateOutput，在某些环境下（如刚启动、GPU 繁忙）
        可能暂时不可用。这里加入重试和短暂等待。
        """
        import time as _time
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                return dxcam.create(output_idx=0, output_color="BGR")
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    _time.sleep(0.5 * attempt)  # 递增等待：0.5s, 1s, 1.5s...
        raise RuntimeError(
            f"无法初始化 dxcam 摄像头（已重试 {max_retries} 次）: {last_err}"
        )

    def run(self):
        """启动应用主循环。"""
        self._init_db()
        self._bind_events()
        self._register_initial_hotkeys()
        self._start_timers()
        self._print_startup_info()
        # 自动打开管理面板（作为程序主窗口）
        self._management_panel.show()
        self._app.exec()

    # ========== 数据库 ==========

    def _init_db(self):
        if not self._relic_db.load():
            print("[警告] 遗物数据库加载失败，遗物内容查询将不可用")

    def reload_db(self, db_path: str):
        """管理面板更新数据库后，重新加载 RelicDB"""
        self._log("管理面板 数据库已更新，重新加载...")
        self._relic_db.close()
        self._relic_db = RelicDB()
        if self._relic_db.load():
            stats = self._relic_db.stats()
            self._log(f"  重新加载完成: {stats['total_relics']} 个遗物 | "
                      f"入库 {stats['available']} | 出库 {stats['vaulted']}", "ok")
        else:
            self._log("[警告] 数据库重新加载失败", "error")

    # ========== 日志 ==========

    def _log(self, msg: str, log_type: str = "info"):
        self._management_panel.add_log(log_type, msg)

    # ========== 截图 & OCR ==========

    def _start_ocr_async(self, frame, region):
        """启动后台 OCR 线程（不阻塞 UI）"""
        # 安全退出可能还在运行的旧线程
        if self._ocr_thread is not None and self._ocr_thread.isRunning():
            self._ocr_thread.quit()
            self._ocr_thread.wait(500)

        self._ocr_done = False
        self._last_frame = frame
        self._last_region = region

        self._ocr_thread = QThread()
        self._ocr_worker = OCRWorker(self._relic_ocr, frame)
        self._ocr_worker.moveToThread(self._ocr_thread)

        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_thread.started.connect(self._ocr_worker.run)
        self._ocr_thread.start()

    def _on_ocr_finished(self, relics):
        self._last_relics = relics
        self._ocr_done = True
        self._ocr_thread.quit()
        self._screenshot_busy = False

        if relics:
            relic_names = ' | '.join(n for n, _ in relics)
            self._log(f"[识别] {relic_names}")
            self._overlay.label.setText(f"识别到 {len(relics)} 个遗物 — 请选择操作：")
            self._overlay.label.adjustSize()
            self._overlay.label.move((self._overlay.width() - self._overlay.label.width()) // 2, 20)
            self._overlay.label.show()
        else:
            self._overlay._hide_mode_buttons()
            self._overlay.display("未识别到遗物", auto_hide_ms=3000)

        # 如果用户在 OCR 完成前就选了模式，现在执行
        if self._pending_mode:
            mode = self._pending_mode
            self._pending_mode = None
            if relics:
                self.on_mode_selected(mode)
            else:
                self._overlay.display("没有可用的识别结果，请重新截图", auto_hide_ms=3000)

    def _process_frame(self, frame, region):
        """截图后：保存调试图 → 立即显示按钮 → 后台 OCR"""
        # 保存调试截图
        img = Image.fromarray(frame[:, :, ::-1])
        save_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
        os.makedirs(save_dir, exist_ok=True)
        img.save(os.path.join(save_dir, 'last_capture.png'))

        # 立即显示功能按钮（不等 OCR）
        self._last_relics = []
        self._overlay.show_mode_buttons()

        # 后台线程跑 OCR
        self._start_ocr_async(frame, region)

    def do_screenshot(self):
        """步骤1：框选区域截图 → 立即显示按钮 → 后台 OCR"""
        if self._screenshot_busy:
            return
        self._screenshot_busy = True

        region = self._overlay.get_region()
        if region is None:
            self._overlay.display("请先按 Ctrl+G 框选截图区域", auto_hide_ms=3000)
            self._screenshot_busy = False
            return

        # dxcam 使用物理像素，需要把 Qt 逻辑坐标转为物理像素
        dpi = self._overlay._dpi_scale
        phys_region = (
            int(region[0] * dpi), int(region[1] * dpi),
            int(region[2] * dpi), int(region[3] * dpi),
        )
        frame = self._camera.grab(region=phys_region)
        if frame is None:
            self._overlay.display("截图失败", auto_hide_ms=3000)
            self._screenshot_busy = False
            return

        self._process_frame(frame, region)

    def do_screenshot_fullscreen(self):
        """Ctrl+H：全屏截图 → 立即显示按钮 → 后台 OCR"""
        if self._screenshot_busy:
            return

        # 防止覆盖层内容（标注/按钮/label）被截入图片
        if self._overlay.is_showing_content():
            self._overlay.display("请先右键清除标注或关闭功能按钮，再使用全屏截图", auto_hide_ms=3000)
            self._log("[拒绝] 全屏截图：覆盖层有内容正在显示，请先右键清除", "warn")
            return

        self._screenshot_busy = True

        self._log("=== 全屏截图模式 ===")
        # dxcam 使用物理像素，camera.width/height 来自 DXGI
        full_phys = (0, 0, self._camera.width, self._camera.height)
        dpi = self._overlay._dpi_scale
        full_logical = (0, 0, int(self._camera.width / dpi), int(self._camera.height / dpi))

        frame = self._camera.grab(region=full_phys)
        if frame is None:
            self._overlay.display("全屏截图失败", auto_hide_ms=3000)
            self._screenshot_busy = False
            return

        self._overlay.display(f"全屏截图 ({self._camera.width}x{self._camera.height})", auto_hide_ms=2000)
        self._process_frame(frame, full_logical)

    # ========== 功能模式处理 ==========

    def on_mode_selected(self, mode: str):
        """步骤2：用户点击功能按钮 → 等待 OCR 完成（如需要）→ 执行处理"""
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
        else:
            self._overlay.display(f"未知功能模式: {mode}", auto_hide_ms=3000)

    def _handle_check_status(self):
        """功能A：出入库查询 —— 逐条流式显示遗物状态"""
        self._log("=== 出入库查询模式 ===")
        annotations = []
        dpi_scale = self._overlay._dpi_scale
        region = self._last_region

        for name, box in self._last_relics:
            sx = int(region[0] + box[0][0] / dpi_scale)
            sy = int(region[1] + box[0][1] / dpi_scale - 28)

            relic_info = self._relic_db.find(name)
            if relic_info:
                vaulted = relic_info.get('vaulted', False)
                if vaulted == 1:
                    color = "#33FF66"
                    name_display = f"{name} [出库]"
                else:
                    color = "#FF6B6B"
                    name_display = f"{name} [入库]"
            else:
                color = "#AAAAAA"
                name_display = f"{name} [?]"

            annotations.append((name_display, sx, sy, 8000, color))

        self._overlay.show_annotations_stream(annotations, auto_hide_ms=8000, interval_ms=30, batch_size=2)
        self._overlay.display(f"已显示 {len(annotations)} 个遗物（右键清除）", auto_hide_ms=5000)

    def _handle_query_parts(self):
        """功能B：遗物内容查询 —— 显示出入库状态 + 遗物内 Prime 部件列表"""
        self._log("=== 遗物内容查询 ===")

        STATUS_COLOR_OUT = "#33FF66"
        STATUS_COLOR_IN = "#FF6B6B"
        FALLBACK_COLOR = "#AAAAAA"
        COLOR_GOLD = "#FFD700"
        COLOR_SILVER = "#C0C0C0"
        COLOR_COPPER = "#CD7F32"

        annotations = []
        matched = 0
        unmatched_names = []
        dpi_scale = self._overlay._dpi_scale
        region = self._last_region

        for name, box in self._last_relics:
            sx = int(region[0] + box[0][0] / dpi_scale)
            sy = int(region[1] + box[0][1] / dpi_scale - 28)

            relic_info = self._relic_db.find(name)

            if relic_info:
                matched += 1
                parts = relic_info.get('parts', [])
                vaulted = relic_info.get('vaulted', False)

                if vaulted == 1:
                    status_color = STATUS_COLOR_OUT
                    status = "出库"
                else:
                    status_color = STATUS_COLOR_IN
                    status = "入库"
                lines = [f"{name} [{status}]"]
                line_colors = [status_color]

                sorted_parts = sorted(parts, key=lambda p: p.get('chance', 0))
                chances = sorted(set(p.get('chance', 0) for p in sorted_parts))
                if len(chances) >= 3:
                    chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_SILVER, chances[2]: COLOR_COPPER}
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

                    part_name = p['name']
                    lines.append(f"  {prefix} {part_name}")
                    line_colors.append(clr)

                label = "\n".join(lines)
                annotations.append((label, sx, sy, 10000, status_color, line_colors))
            else:
                unmatched_names.append(name)
                label = f"{name}\n  (未找到部件信息)"
                annotations.append((label, sx, sy, 10000, FALLBACK_COLOR))

        self._overlay.show_annotations_stream(annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

        total = len(self._last_relics)
        summary = f"遗物内容查询: {total}个 | 匹配 {matched}个"
        if unmatched_names:
            summary += f" | 未匹配: {', '.join(unmatched_names)}"
        summary += "\n(★金=稀有  ◆银=罕见  ·铜=常见  绿=出库  红=入库)"
        self._overlay.display(summary, auto_hide_ms=6000)

        self._log(f"  匹配: {matched}/{total}")
        if unmatched_names:
            self._log(f"  未匹配: {', '.join(unmatched_names)}", "warn")

    # ========== 事件绑定 ==========

    def _bind_events(self):
        self._overlay.on_selection_done = self.do_screenshot
        self._overlay.mode_selected.connect(self.on_mode_selected)
        self._bridge.fired.connect(self._handle_trigger)
        self._management_panel.db_updated.connect(self.reload_db)
        self._management_panel.hotkeys_changed.connect(self._on_hotkeys_changed)

    # ========== 热键 ==========

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
        """根据配置注册热键（先清理旧的再注册新的）"""
        for hk in self._registered_hotkeys.values():
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self._registered_hotkeys.clear()

        action_map = {
            "select": "select",
            "fullscreen": "fullscreen",
            "panel": "panel",
        }
        for action, action_name in action_map.items():
            hk_str = hotkeys.get(action, DEFAULT_HOTKEYS[action])
            try:
                hk_id = keyboard.add_hotkey(hk_str, lambda a=action_name: self._bridge.fired.emit(a))
                self._registered_hotkeys[hk_str] = hk_id
            except Exception as e:
                print(f"[警告] 注册热键失败 {hk_str}: {e}")

    def _register_initial_hotkeys(self):
        hotkeys_config = load_hotkeys()
        self._register_hotkeys(hotkeys_config)

    def _on_hotkeys_changed(self, new_hotkeys: dict):
        print(f"[热键] 快捷键已更新: {new_hotkeys}")
        self._register_hotkeys(new_hotkeys)

    # ========== 定时器 ==========

    def _start_timers(self):
        hide_timer = QTimer()
        hide_timer.timeout.connect(self._overlay._check_auto_hide)
        hide_timer.start(100)

    # ========== 启动信息 ==========

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


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    core = AppCore(app)
    core.run()


if __name__ == "__main__":
    main()
