import time
import json
import os
import ctypes
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QPushButton
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QCursor


# ========== Win32 鼠标穿透 ==========
_WS_EX_TRANSPARENT = 0x00000020
_GWL_EXSTYLE = -20
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_FRAMECHANGED = 0x0020
_VK_RBUTTON = 0x02


def _get_dpi_scale() -> float:
    """获取主显示器（1号屏）的 DPI 缩放比例。
    
    dxcam 返回的是物理像素坐标，而 Qt 在 dpiawareness=0 时使用逻辑坐标。
    缩放比例 = 物理DPI / 96，例如 125% → 1.25。
    使用主屏幕的 DPI（而非桌面整体），确保与 dxcam output_idx=0 一致。
    """
    try:
        screen = QApplication.primaryScreen()
        if screen:
            dpi = screen.logicalDotsPerInch()
            return dpi / 96.0
    except Exception:
        pass
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi_x / 96.0
    except Exception:
        return 1.0


def _win32_set_mouse_passthrough(hwnd: int, enabled: bool):
    style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    if enabled:
        style |= _WS_EX_TRANSPARENT
    else:
        style &= ~_WS_EX_TRANSPARENT
    ctypes.windll.user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
    ctypes.windll.user32.SetWindowPos(
        hwnd, 0, 0, 0, 0, 0,
        _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORDER | _SWP_FRAMECHANGED
    )


class Overlay(QWidget):
    # ★ 新增：功能按钮点击信号，携带 mode 名称
    mode_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # ★ DPI 缩放比例：dxcam 物理像素 → Qt 逻辑坐标
        self._dpi_scale = _get_dpi_scale()
        self._setup_window()
        self._setup_label()
        self._setup_buttons()       # ★ 功能选择按钮
        self._hide_at = 0
        self._selecting = False
        self._start_pos = None
        self._current_pos = None
        self._saved_region = None
        self._track_timer = None
        self._left_was_down = False
        self._status = ""
        self._annotations = []
        self.on_selection_done = None
        self._right_was_down = False

        # ★ 流式标注：逐条显示的队列和定时器
        self._stream_queue = []          # 待显示的标注队列
        self._stream_timer = QTimer()
        self._stream_timer.timeout.connect(self._stream_tick)
        self._stream_batch_size = 2      # 每次弹出几条

        self._hide_timer = QTimer()
        self._hide_timer.timeout.connect(self._check_auto_hide)
        self._hide_timer.start(100)

        self._load_region()

    # ========== 鼠标穿透 ==========

    def _apply_mouse_passthrough(self, enabled: bool):
        # Qt 属性级穿透：窗口本身 + label + preview_label → 穿透
        # 按钮明确不设穿透（保持可点击）
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        for btn in self._mode_buttons.values():
            btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)  # ★ 按钮永远不穿透
        if hasattr(self, '_preview_label'):
            self._preview_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        # 不再调用 Win32 WS_EX_TRANSPARENT（窗口级穿透会导致按钮无法点击）

    def showEvent(self, event):
        super().showEvent(event)
        if not self._selecting:
            self._apply_mouse_passthrough(True)

    # ========== 按键检测 ==========

    @staticmethod
    def _is_left_down():
        return (ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000) != 0

    @staticmethod
    def _is_esc_down():
        return (ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000) != 0

    @staticmethod
    def _is_right_down():
        return (ctypes.windll.user32.GetAsyncKeyState(_VK_RBUTTON) & 0x8000) != 0

    # ========== 配置持久化 ==========

    def _config_path(self):
        appdata = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC')
        os.makedirs(appdata, exist_ok=True)
        return os.path.join(appdata, 'config.json')

    def _load_region(self):
        path = self._config_path()
        if os.path.exists(path):
            with open(path, 'r') as f:
                cfg = json.load(f)
                r = cfg.get('region')
                if r:
                    self._saved_region = (r[0], r[1], r[2], r[3])

    def _save_region(self):
        with open(self._config_path(), 'w') as f:
            json.dump({'region': list(self._saved_region)}, f)

    def get_region(self):
        return self._saved_region

    def is_showing_content(self) -> bool:
        """检查当前是否有正在显示的内容（标注、按钮、label 等）。
        
        用于全屏截图前判断，防止覆盖层内容被截入图片导致识别异常。
        """
        # 有正在显示的标注（含未过期）
        now = int(time.time() * 1000)
        if any(a[3] > now for a in self._annotations):
            return True
        # 有可见的功能按钮
        if any(btn.isVisible() for btn in self._mode_buttons.values()):
            return True
        # label 有文字且未过期
        if self._hide_at > now and self.label.text():
            return True
        return False

    # ========== 功能选择按钮（★ 新增）==========

    def _setup_buttons(self):
        """创建功能选择按钮，初始隐藏"""
        self._mode_buttons = {}
        btn_style = """
            QPushButton {
                background-color: rgba(30, 30, 30, 230);
                color: #FFD900;
                border: 2px solid #FFD900;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 16px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: rgba(60, 60, 60, 230);
                border-color: #FFF;
                color: #FFF;
            }
        """

        # 定义可用功能（可在此处扩展新功能）
        modes = [
            ("check_status", "📋 出入库查询"),
            ("query_parts", "🔍 遗物内容查询"),
        ]

        for i, (mode_id, label) in enumerate(modes):
            btn = QPushButton(label, self)
            btn.setStyleSheet(btn_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.hide()
            # 点击时发射信号并隐藏所有按钮
            btn.clicked.connect(lambda checked, m=mode_id: self._on_mode_clicked(m))
            self._mode_buttons[mode_id] = btn

    def _on_mode_clicked(self, mode: str):
        """按钮被点击：隐藏按钮面板，发射信号给 main.py 处理"""
        self._hide_mode_buttons()
        self.mode_selected.emit(mode)
        self._log(f"▶ 用户选择了功能: {mode}")

    def show_mode_buttons(self, relic_count: int = -1):
        """★ 截图完成后立即调用：显示功能选择按钮

        如果 relic_count >= 0: OCR 已完成，显示识别数量
        如果 relic_count == -1: OCR 还在后台跑，显示通用文案
        """
        if relic_count >= 0:
            self.label.setText(f"识别到 {relic_count} 个遗物 — 请选择操作：")
        else:
            self.label.setText("截图完成 — 请选择操作（后台识别中...）：")
        self.label.adjustSize()
        # 屏幕上方居中
        self.label.move((self.width() - self.label.width()) // 2, 20)
        self.label.show()

        # 布局按钮（水平排列在标签下方，也居中）
        btn_width = 200
        btn_height = 45
        btn_gap = 20
        total_btns = len(self._mode_buttons)
        total_width = total_btns * btn_width + (total_btns - 1) * btn_gap
        start_x = (self.width() - total_width) // 2
        start_y = 70

        for i, (mode_id, btn) in enumerate(self._mode_buttons.items()):
            x = start_x + i * (btn_width + btn_gap)
            btn.setGeometry(x, start_y, btn_width, btn_height)
            btn.show()

        self._hide_at = 0  # 不自动隐藏，等用户选

    def _hide_mode_buttons(self):
        """隐藏所有功能按钮"""
        for btn in self._mode_buttons.values():
            btn.hide()

    # ========== 框选模式 ==========

    def start_selection(self):
        self._log("▶ 框选模式启动")
        self._selecting = True
        self._start_pos = None
        self._current_pos = self.mapFromGlobal(QCursor.pos())
        self._left_was_down = self._is_left_down()
        self._status = "移动鼠标到目标位置，按住左键拖拽框选，右键/ESC 取消"
        self._annotations = []
        self._hide_mode_buttons()          # ★ 进入框选时隐藏按钮
        self._apply_mouse_passthrough(False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.label.hide()
        if hasattr(self, '_preview_label'):
            self._preview_label.hide()
        self._hide_at = 0
        self._track_timer = QTimer()
        self._track_timer.timeout.connect(self._track_mouse)
        self._track_timer.start(16)
        self.update()

    def end_selection(self):
        self._log("■ 框选模式结束")
        self._selecting = False
        self._start_pos = None
        self._current_pos = None
        self._left_was_down = False
        self._status = ""
        self._apply_mouse_passthrough(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.label.show()
        if self._track_timer:
            self._track_timer.stop()
            self._track_timer = None
        self.update()

    def _track_mouse(self):
        if not self._selecting:
            return

        pos = self.mapFromGlobal(QCursor.pos())
        self._current_pos = pos
        left_down = self._is_left_down()

        if ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000:
            self._log("✕ 用户右键取消框选")
            self.label.setText("框选已取消")
            self.label.adjustSize()
            self.label.move(50, 50)
            self.label.show()
            self._hide_at = int(time.time() * 1000) + 3000
            self.end_selection()
            return

        if self._is_esc_down():
            self._log("✕ 用户按 ESC 取消框选")
            self.label.setText("框选已取消")
            self.label.adjustSize()
            self.label.move(50, 50)
            self.label.show()
            self._hide_at = int(time.time() * 1000) + 3000
            self.end_selection()
            return

        if left_down and not self._left_was_down:
            self._start_pos = pos
            self._left_was_down = True
            self._status = f"左键已按下 [{pos.x()},{pos.y()}]，拖拽中..."
            self._log(f"↓ 左键按下 @ ({pos.x()},{pos.y()})")

        elif left_down and self._left_was_down:
            if self._start_pos:
                w = abs(pos.x() - self._start_pos.x())
                h = abs(pos.y() - self._start_pos.y())
                self._status = f"拖拽中... 选区 {w}×{h}"

        elif not left_down and self._left_was_down:
            self._left_was_down = False
            self._log(f"↑ 左键松开 @ ({pos.x()},{pos.y()})")
            if self._start_pos:
                self._status = "左键松开，正在保存..."
                self._finish_selection()
            else:
                self._status = "移动鼠标到目标位置，按住左键拖拽框选"
            return

        else:
            self._left_was_down = left_down
            self._status = "移动鼠标到目标位置，按住左键拖拽框选，右键/ESC 取消"

        self.update()

    def _finish_selection(self):
        p1, p2 = self._start_pos, self._current_pos
        left, right = min(p1.x(), p2.x()), max(p1.x(), p2.x())
        top, bottom = min(p1.y(), p2.y()), max(p1.y(), p2.y())
        w, h = right - left, bottom - top

        if w > 20 and h > 20:
            self._saved_region = (left, top, right, bottom)
            self._save_region()
            msg = f"区域已保存: [{left},{top}] → [{right},{bottom}]  ({w}×{h})"
            self._log(f"✓ {msg}")
            self.label.setText(msg)
        else:
            msg = f"框选太小 ({w}×{h})，请重新框选"
            self._log(f"✗ {msg}")
            self.label.setText(msg)

        self.label.adjustSize()
        self.label.move(50, 50)
        self.label.show()
        self._hide_at = int(time.time() * 1000) + 2000
        self.end_selection()

        if self.on_selection_done and w > 20 and h > 20:
            self.on_selection_done()

    # ========== 标注系统 ==========

    def _normalize_annotations(self, annotations, auto_hide_ms=5000):
        """预处理标注列表，统一为 (text, x, y, expire_ms, color, line_colors) 格式。

        annotations 元素格式（向后兼容）：
          - 3元组: (text, x, y)                        → 默认金色 + auto_hide_ms
          - 4元组: (text, x, y, color)                  → 指定颜色 + auto_hide_ms
          - 5元组: (text, x, y, expire_ms, color)        → 完全自定义
          - 6元组: (text, x, y, expire_ms, color, line_colors) → 多行分别着色
        """
        now_ms = int(time.time() * 1000)
        default_color = "#FFD900"
        result = []
        for item in annotations:
            line_colors = None
            if len(item) >= 6:
                text, x, y, expire_offset, color = item[:5]
                line_colors = item[5]
                result.append((text, int(x), int(y), now_ms + int(expire_offset), color, line_colors))
            elif len(item) >= 5:
                text, x, y, expire_offset, color = item[:5]
                result.append((text, int(x), int(y), now_ms + int(expire_offset), color, None))
            elif len(item) == 4:
                val4 = item[3]
                if isinstance(val4, str) and val4.startswith('#'):
                    text, x, y, color = item
                    result.append((text, int(x), int(y), now_ms + auto_hide_ms, color, None))
                else:
                    text, x, y, expire_offset = item
                    result.append((text, int(x), int(y), now_ms + int(expire_offset), default_color, None))
            else:
                text, x, y = item
                result.append((text, int(x), int(y), now_ms + auto_hide_ms, default_color, None))
        return result

    def show_annotations(self, annotations, auto_hide_ms=5000):
        """显示标注列表，支持带颜色的标注和多行分别着色。"""
        self._annotations = self._normalize_annotations(annotations, auto_hide_ms)
        self.update()

    def clear_annotations(self):
        self._annotations = []
        self._stream_queue = []
        self._stream_timer.stop()
        self.update()

    # ========== 流式标注（逐条出现，提升体验）==========

    def show_annotations_stream(self, annotations, auto_hide_ms=5000, interval_ms=30, batch_size=2):
        """逐批显示标注，产生「逐步出现」的动画感。"""
        self.clear_annotations()

        # 预处理所有标注项（复用归一化逻辑）
        self._stream_queue = self._normalize_annotations(annotations, auto_hide_ms)
        self._stream_batch_size = batch_size

        # 启动定时器
        self._stream_timer.start(interval_ms)

    def _stream_tick(self):
        """每次定时器触发：从队列弹出 batch_size 条追加到显示列表"""
        if not self._stream_queue:
            self._stream_timer.stop()
            return

        batch = self._stream_queue[:self._stream_batch_size]
        self._stream_queue = self._stream_queue[self._stream_batch_size:]

        self._annotations.extend(batch)
        self.update()

        # 队空则停
        if not self._stream_queue:
            self._stream_timer.stop()

    # ========== 绘制 ==========

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        now = int(time.time() * 1000)
        active = [a for a in self._annotations if a[3] > now]
        if active:
            painter.setFont(QFont("Microsoft YaHei", 12))
            for item in active:
                # 解包（兼容新旧格式）
                if len(item) >= 6:
                    text, x, y, _, color, line_colors = item
                else:
                    text, x, y, _, color = item
                    line_colors = None

                fm = painter.fontMetrics()
                line_height = fm.height() + 4  # 行高（含行间距）

                # 背景颜色：深色半透明，确保文字可读
                bg_color = QColor(20, 20, 20, 210)

                if '\n' in text:
                    # === 多行文本 ===
                    lines = text.split('\n')
                    max_tw = max(fm.boundingRect(line).width() for line in lines) + 16
                    total_th = line_height * len(lines) + 8

                    # 绘制深色半透明背景（整体外框）
                    painter.fillRect(x, y, max_tw, total_th, bg_color)

                    # 逐行绘制：有 line_colors 则按行着色，否则统一用 color
                    for i, line in enumerate(lines):
                        if line_colors and i < len(line_colors):
                            painter.setPen(QColor(line_colors[i]))
                        else:
                            painter.setPen(QColor(color))
                        line_y = y + fm.ascent() + 2 + i * line_height
                        painter.drawText(x + 8, line_y, line)
                else:
                    # === 单行文本 ===
                    tw = fm.boundingRect(text).width() + 12
                    th = fm.height() + 6
                    painter.fillRect(x, y, tw, th, bg_color)
                    painter.setPen(QColor(color))
                    painter.drawText(x + 6, y + fm.ascent() + 3, text)

        if not self._selecting:
            return

        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self._status:
            painter.fillRect(0, 0, self.width(), 36, QColor(0, 0, 0, 180))
            painter.setPen(QColor("#FFD900"))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(20, 24, self._status)

        if not self._current_pos:
            return

        cx, cy = self._current_pos.x(), self._current_pos.y()

        if not self._start_pos:
            self._draw_crosshair(painter, self._current_pos)
            return

        sx, sy = self._start_pos.x(), self._start_pos.y()
        x = min(sx, cx)
        y = min(sy, cy)
        w = abs(cx - sx)
        h = abs(cy - sy)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(x, y, w, h, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        pen = QPen(QColor("#FFD700"), 2)
        painter.setPen(pen)
        painter.drawRect(x, y, w, h)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Microsoft YaHei", 11))
        painter.drawText(x + 5, y - 8, f"{w} × {h}")

    def _draw_crosshair(self, painter, pos):
        pen = QPen(QColor("#FFD700"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(0, pos.y(), self.width(), pos.y())
        painter.drawLine(pos.x(), 0, pos.x(), self.height())
        painter.setPen(QPen(QColor("#FFD700"), 2))
        painter.drawLine(pos.x() - 12, pos.y(), pos.x() + 12, pos.y())
        painter.drawLine(pos.x(), pos.y() - 12, pos.x(), pos.y() + 12)

    # ========== 窗口设置 ==========

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 只覆盖主屏幕（1号屏），dxcam 也只截主屏幕
        primary_geo = QApplication.primaryScreen().geometry()
        self.setGeometry(primary_geo)

    def _setup_label(self):
        self.label = QLabel("", self)
        self.label.setFont(QFont("Microsoft YaHei", 14))
        self.label.setStyleSheet("color: #FFD900; background: transparent;")

    # ========== 显示信息 ==========

    def display(self, text, auto_hide_ms=5000, pos=None):
        self.label.setText(text)
        self.label.adjustSize()
        if pos:
            self.label.move(pos[0], pos[1])
        else:
            # 屏幕上方居中
            self.label.move((self.width() - self.label.width()) // 2, 20)
        self.label.show()
        self._hide_at = int(time.time() * 1000) + auto_hide_ms

    def display_preview(self, pixmap, x=50, y=100):
        if not hasattr(self, '_preview_label'):
            self._preview_label = QLabel(self)
        self._preview_label.setPixmap(pixmap)
        self._preview_label.setStyleSheet("background: transparent;")
        self._preview_label.move(x, y)
        self._preview_label.show()

    def _check_auto_hide(self):
        now = int(time.time() * 1000)

        # 右键清除标注（非框选模式）
        if not self._selecting:
            right_now = self._is_right_down()
            if right_now and not self._right_was_down:
                had_annotations = len(self._annotations) > 0
                had_buttons = any(btn.isVisible() for btn in self._mode_buttons.values())
                self.clear_annotations()
                self._hide_mode_buttons()
                self.label.clear()
                if hasattr(self, '_preview_label'):
                    self._preview_label.hide()
                self._hide_at = 0
                if had_annotations:
                    self._log("🗑 右键清除标注")
                if had_buttons:
                    self._log("🗑 右键关闭功能选择")
            self._right_was_down = right_now

        # 自动隐藏计时器
        if self._hide_at and now > self._hide_at:
            self.label.clear()
            if hasattr(self, '_preview_label'):
                self._preview_label.hide()
            self._hide_at = 0

    def _log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")
