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


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭管理面板不影响主程序
    camera = dxcam.create(output_color="BGR")
    overlay = Overlay()
    overlay.show()

    bridge = TriggerBridge()
    relic_ocr = RelicNameRecognizer()

    # ====== 真实数据接入（Phase 3）======
    relic_db = RelicDB()
    if not relic_db.load():
        # 数据加载失败时程序仍可运行（功能A不受影响），功能B会降级提示
        print("[警告] 遗物数据库加载失败，遗物内容查询将不可用")

    # ====== 管理面板（Ctrl+Shift+G 唤起）======
    management_panel = ManagementPanel()

    def reload_db(db_path: str):
        """管理面板更新数据库后，重新加载 RelicDB"""
        nonlocal relic_db
        log("[管理面板] 数据库已更新，重新加载...")
        relic_db.close()
        relic_db = RelicDB()
        if relic_db.load():
            stats = relic_db.stats()
            vt_str = f" | 虚空商人 {stats.get('voidtrader', 0)}" if stats.get('voidtrader', 0) > 0 else ""
            log(f"  重新加载完成: {stats['total_relics']} 个遗物 | "
                f"入库 {stats['available']} | 出库 {stats['vaulted']}{vt_str}", "ok")
        else:
            log("[警告] 数据库重新加载失败", "error")

    management_panel.db_updated.connect(reload_db)

    # ====== 日志辅助：同时输出到 cmd 和管理面板 ======
    def log(msg: str, log_type: str = "info"):
        print(msg)
        management_panel.add_log(log_type, msg)

    # ====== 共享状态（截图后保留，供各功能模块使用）======
    _last_frame = None          # 最后一次截图的 numpy 数组 (BGR)
    _last_region = None         # 最后一次截图的区域 (left,top,right,bottom)
    _last_relics = []           # 最后一次 OCR 识别结果 [(name, box), ...]
    _ocr_done = False           # OCR 是否已完成
    _ocr_thread = None          # 后台 OCR 线程
    _ocr_worker = None          # OCR worker 引用
    _pending_mode = None        # 用户在 OCR 完成前选择的模式（等待 OCR 完成后执行）
    _screenshot_busy = False    # 防重复触发：正在处理截图时忽略新请求

    def _start_ocr_async(frame, region):
        """启动后台 OCR 线程（不阻塞 UI）"""
        nonlocal _ocr_done, _ocr_thread, _ocr_worker, _last_frame, _last_region

        # 安全退出可能还在运行的旧线程
        if _ocr_thread is not None and _ocr_thread.isRunning():
            _ocr_thread.quit()
            _ocr_thread.wait(500)  # 等待最多 500ms

        _ocr_done = False
        _last_frame = frame
        _last_region = region

        _ocr_thread = QThread()
        _ocr_worker = OCRWorker(relic_ocr, frame)
        _ocr_worker.moveToThread(_ocr_thread)

        def on_ocr_finished(relics):
            nonlocal _last_relics, _ocr_done, _pending_mode, _screenshot_busy
            _last_relics = relics
            _ocr_done = True
            _ocr_thread.quit()
            _screenshot_busy = False  # 释放防重复锁

            if relics:
                relic_names = ' | '.join(n for n, _ in relics)
                log(f"[识别] {relic_names}")
                # 更新按钮提示文本（屏幕上方居中）
                overlay.label.setText(f"识别到 {len(relics)} 个遗物 — 请选择操作：")
                overlay.label.adjustSize()
                overlay.label.move((overlay.width() - overlay.label.width()) // 2, 20)
                overlay.label.show()
            else:
                # OCR 没识别到，隐藏按钮
                overlay._hide_mode_buttons()
                overlay.display("未识别到遗物", auto_hide_ms=3000)

            # 如果用户在 OCR 完成前就选了模式，现在执行
            if _pending_mode:
                mode = _pending_mode
                _pending_mode = None
                if relics:
                    on_mode_selected(mode)
                else:
                    overlay.display("没有可用的识别结果，请重新截图", auto_hide_ms=3000)

        _ocr_worker.finished.connect(on_ocr_finished)
        _ocr_thread.started.connect(_ocr_worker.run)
        _ocr_thread.start()

    def _process_frame(frame, region):
        """截图后：保存调试图 → 立即显示按钮 → 后台 OCR"""
        nonlocal _last_relics

        # 保存调试截图
        img = Image.fromarray(frame[:, :, ::-1])
        save_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
        os.makedirs(save_dir, exist_ok=True)
        img.save(os.path.join(save_dir, 'last_capture.png'))

        # ★ 立即显示功能按钮（不等 OCR）
        _last_relics = []  # 清空旧结果
        overlay.show_mode_buttons()  # 不传 relic_count，显示通用文案

        # ★ 后台线程跑 OCR
        _start_ocr_async(frame, region)

    def do_screenshot():
        """步骤1：框选区域截图 → 立即显示按钮 → 后台 OCR"""
        nonlocal _screenshot_busy
        if _screenshot_busy:
            return  # 上一次截图/OCR 尚未完成，忽略重复触发
        _screenshot_busy = True

        region = overlay.get_region()
        if region is None:
            overlay.display("请先按 Ctrl+G 框选截图区域", auto_hide_ms=3000)
            _screenshot_busy = False
            return

        frame = camera.grab(region=region)
        if frame is None:
            overlay.display("截图失败", auto_hide_ms=3000)
            _screenshot_busy = False
            return

        _process_frame(frame, region)

    def do_screenshot_fullscreen():
        """Ctrl+H：全屏截图 → 立即显示按钮 → 后台 OCR"""
        nonlocal _screenshot_busy
        if _screenshot_busy:
            return  # 上一次截图/OCR 尚未完成，忽略重复触发
        _screenshot_busy = True

        log("=== 全屏截图模式 ===")
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry()
        full_region = (0, 0, screen_geo.width(), screen_geo.height())

        frame = camera.grab(region=full_region)
        if frame is None:
            overlay.display("全屏截图失败", auto_hide_ms=3000)
            _screenshot_busy = False
            return

        overlay.display(f"全屏截图 ({screen_geo.width()}x{screen_geo.height()})", auto_hide_ms=2000)
        _process_frame(frame, full_region)

    # ====== 功能模式处理（用户点击按钮后触发）======

    def on_mode_selected(mode: str):
        """步骤2：用户点击功能按钮 → 等待 OCR 完成（如需要）→ 执行处理"""
        nonlocal _last_relics, _ocr_done, _pending_mode

        if not _ocr_done:
            # OCR 还在跑，挂起等待
            _pending_mode = mode
            overlay.display("正在识别中，请稍候...", auto_hide_ms=5000)
            log(f"[等待] 用户选择了 {mode}，等待 OCR 完成...")
            return

        if not _last_relics:
            overlay.display("没有可用的识别结果，请重新截图", auto_hide_ms=3000)
            return

        if mode == "check_status":
            handle_check_status(_last_relics, _last_region)
        elif mode == "query_parts":
            handle_query_parts(_last_relics, _last_region)
        else:
            overlay.display(f"未知功能模式: {mode}", auto_hide_ms=3000)

    def handle_check_status(relics, region):
        """功能A：出入库查询 —— 逐条流式显示遗物状态

        颜色规则：
          - vaulted=1 (有掉落途径)  → 出库，亮绿色 #33FF66
          - vaulted=0 (无掉落途径)  → 入库，暖红色 #FF6B6B
          - vaulted=2 (虚空商人)    → 蓝色 #448AFF
          - 未匹配到数据库          → 灰色 #AAAAAA
        """
        log("=== 出入库查询模式 ===")
        annotations = []
        dpi_scale = overlay._dpi_scale
        for name, box in relics:
            sx = int((region[0] + int(box[0][0])) / dpi_scale)
            sy = int((region[1] + int(box[0][1]) - 28) / dpi_scale)

            # 查询数据库获取 vaulted 状态
            relic_info = relic_db.find(name)
            if relic_info:
                vaulted = relic_info.get('vaulted', False)
                if vaulted == 2:
                    color = "#448AFF"   # 蓝色 - 虚空商人
                    name_display = f"{name} [虚空商人]"
                elif vaulted == 1:
                    color = "#33FF66"   # 亮绿 - 出库
                    name_display = f"{name} [出库]"
                else:
                    color = "#FF6B6B"   # 暖红 - 入库
                    name_display = f"{name} [入库]"
            else:
                color = "#AAAAAA"      # 灰色 - 未匹配
                name_display = f"{name} [?]"

            annotations.append((name_display, sx, sy, 8000, color))

        # ★ 流式标注：逐条出现，每条间隔 30ms，每批 2 条
        overlay.show_annotations_stream(annotations, auto_hide_ms=8000, interval_ms=30, batch_size=2)
        overlay.display(f"已显示 {len(annotations)} 个遗物（右键清除）", auto_hide_ms=5000)

    def handle_query_parts(relics, region):
        """
        功能B：遗物内容查询 —— 显示出入库状态 + 遗物内 Prime 部件列表

        标注格式（每个部件独立一行）：
          第1行:  遗物名称 [出库 / 入库 / 虚空商人]  ← 状态颜色（外框）
          第2行+:    ★ 部件名  ← 金色
                     ◆ 部件名  ← 银色
                     · 部件名  ← 铜色
        """
        log("=== 遗物内容查询 ===")

        STATUS_COLOR_OUT = "#33FF66"     # 出库 - 亮绿
        STATUS_COLOR_IN = "#FF6B6B"      # 入库 - 暖红
        STATUS_COLOR_VT = "#448AFF"      # 虚空商人 - 蓝色
        FALLBACK_COLOR = "#AAAAAA"       # 未匹配 - 灰色

        # 部件颜色：按概率分档（同一遗物内比较）
        COLOR_GOLD = "#FFD700"     # 金色 - 概率最低
        COLOR_SILVER = "#C0C0C0"   # 银色 - 概率中等
        COLOR_COPPER = "#CD7F32"   # 铜色 - 概率最高

        annotations = []
        matched = 0
        unmatched_names = []
        dpi_scale = overlay._dpi_scale

        for name, box in relics:
            sx = int((region[0] + int(box[0][0])) / dpi_scale)
            sy = int((region[1] + int(box[0][1]) - 28) / dpi_scale)

            relic_info = relic_db.find(name)

            if relic_info:
                matched += 1
                parts = relic_info.get('parts', [])
                vaulted = relic_info.get('vaulted', False)

                # === 第1行：遗物名 + 出入库状态 ===
                if vaulted == 2:
                    status = "虚空商人"
                    status_color = STATUS_COLOR_VT
                elif vaulted == 1:
                    status = "出库"
                    status_color = STATUS_COLOR_OUT
                else:
                    status = "入库"
                    status_color = STATUS_COLOR_IN
                lines = [f"{name} [{status}]"]
                line_colors = [status_color]  # 第1行用出入库颜色

                # 按概率从小到大排序（概率低 = 稀有 = 金）
                sorted_parts = sorted(parts, key=lambda p: p.get('chance', 0))

                # 提取概率值，分三档映射颜色
                chances = sorted(set(p.get('chance', 0) for p in sorted_parts))
                if len(chances) >= 3:
                    chance_to_color = {
                        chances[0]: COLOR_GOLD,    # 概率最小 → 金
                        chances[1]: COLOR_SILVER,  # 概率中等 → 银
                        chances[2]: COLOR_COPPER,  # 概率最大 → 铜
                    }
                elif len(chances) == 2:
                    chance_to_color = {
                        chances[0]: COLOR_GOLD,
                        chances[1]: COLOR_COPPER,
                    }
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

                # 6元组: (text, x, y, expire_ms, 第1行颜色, [每行颜色列表])
                annotations.append((label, sx, sy, 10000, status_color, line_colors))
            else:
                unmatched_names.append(name)
                label = f"{name}\n  (未找到部件信息)"
                annotations.append((label, sx, sy, 10000, FALLBACK_COLOR))

        # ★ 流式标注：逐条出现
        overlay.show_annotations_stream(annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

        # 状态摘要
        total = len(relics)
        summary = f"遗物内容查询: {total}个 | 匹配 {matched}个"
        if unmatched_names:
            summary += f" | 未匹配: {', '.join(unmatched_names)}"
        summary += "\n(★金=稀有  ◆银=罕见  ·铜=常见  绿=出库  红=入库  蓝=虚空商人)"
        overlay.display(summary, auto_hide_ms=6000)

        log(f"  匹配: {matched}/{total}")
        if unmatched_names:
            log(f"  未匹配: {', '.join(unmatched_names)}", "warn")

    # ====== 事件绑定 ======

    # 框选完成后 → 截图+OCR → 显示按钮
    overlay.on_selection_done = do_screenshot

    # 用户点击功能按钮 → 按模式分流处理
    overlay.mode_selected.connect(on_mode_selected)

    # 热键
    def handle_trigger(action):
        if action == 'select':
            overlay.start_selection()
        elif action == 'panel':
            _toggle_panel()
        elif action == 'fullscreen':
            do_screenshot_fullscreen()

    def _toggle_panel():
        """切换管理面板显示/隐藏"""
        if management_panel.isVisible():
            management_panel.hide()
        else:
            # 每次显示前调整尺寸，防止首次打开被压缩
            management_panel.adjustSize()
            management_panel.show()
            management_panel.raise_()
            management_panel.activateWindow()

    bridge.fired.connect(handle_trigger)

    # 热键注册管理
    _registered_hotkeys = {}  # hotkey_str → 清理函数

    def _register_hotkeys(hotkeys: dict):
        """根据配置注册热键（先清理旧的再注册新的）"""
        nonlocal _registered_hotkeys

        # 清除旧热键
        for hk in _registered_hotkeys.values():
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        _registered_hotkeys.clear()

        # 注册新热键
        action_map = {
            "select": "select",
            "fullscreen": "fullscreen",
            "panel": "panel",
        }
        for action, action_name in action_map.items():
            hk_str = hotkeys.get(action, DEFAULT_HOTKEYS[action])
            try:
                hk_id = keyboard.add_hotkey(hk_str, lambda a=action_name: bridge.fired.emit(a))
                _registered_hotkeys[hk_str] = hk_id
            except Exception as e:
                print(f"[警告] 注册热键失败 {hk_str}: {e}")

    # 初始加载
    hotkeys_config = load_hotkeys()
    _register_hotkeys(hotkeys_config)

    # 管理面板修改热键后自动重新绑定
    def _on_hotkeys_changed(new_hotkeys: dict):
        print(f"[热键] 快捷键已更新: {new_hotkeys}")
        _register_hotkeys(new_hotkeys)

    management_panel.hotkeys_changed.connect(_on_hotkeys_changed)

    # 定时器
    hide_timer = QTimer()
    hide_timer.timeout.connect(overlay._check_auto_hide)
    hide_timer.start(100)

    # 启动信息
    db_stats = relic_db.stats()
    vt_str = f" | 虚空商人 {db_stats.get('voidtrader', 0)}" if db_stats.get('voidtrader', 0) > 0 else ""
    print("程序已启动")
    print(f"  {hotkeys_config['select']:<16}→ 框选区域截图识别（松手自动识别）")
    print(f"  {hotkeys_config['fullscreen']:<16}→ 全屏截图识别（跳过框选，直接识别）")
    print(f"  {hotkeys_config['panel']:<16}→ 打开管理面板（更新数据库/查看状态）")
    print("  右键          → 取消框选 / 清除标注 / 关闭功能选择")
    print("")
    print("  识别后会弹出功能选择按钮：")
    print("    📋 出入库查询  — 标注遗物名称（绿=出库 红=入库 金=虚空商人）")
    print("    🔍 遗物内容查询  — 匹配遗物对应的 Prime 部件（带颜色）")
    print("")
    print(f"  [WFInfo 数据库] 总计 {db_stats['total_relics']} 个遗物"
          f" | 入库 {db_stats['available']} | 出库 {db_stats['vaulted']}{vt_str}")

    app.exec()


if __name__ == "__main__":
    main()
