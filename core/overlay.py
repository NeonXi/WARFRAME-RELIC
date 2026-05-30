import time
import json
import os
import ctypes
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QPushButton
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QCursor

from core.word_wrap_button import WordWrapButton
from core.constants import (
    CYBER_YELLOW, CYBER_CYAN, CYBER_MAGENTA,
    CYBER_DARK_BG, CYBER_BORDER, CYBER_TEXT,
    OVERLAY_BG_COLOR, OVERLAY_SELECTION_OVERLAY, OVERLAY_STATUS_BG,
    OVERLAY_CROSSHAIR_COLOR, OVERLAY_SELECTION_BORDER,
    BTN_DEFAULT_BG, BTN_DEFAULT_TEXT, BTN_DEFAULT_BORDER,
    BTN_HOVER_BG, BTN_HOVER_TEXT, BTN_HOVER_BORDER,
    PANEL_DARKEST,
)
from data.ui_strings import S


def _hex_to_rgb(hex_color: str) -> tuple:
    """将 #RRGGBB 转为 (R, G, B) 整数元组"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


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
        self._ignore_right_until = 0  # 框选结束后短暂忽略右键（防误触）

        # ★ 价格查询4等分区域框线（临时显示）
        self._split_regions = []          # [(rx, ry, rw, rh, label), ...] 物理坐标
        self._split_regions_until = 0     # 过期时间戳(ms)

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

    def show_split_regions(self, regions, duration_ms=2000):
        """显示4等分区域框线（用于价格查询前确认截图区域）。

        regions: [(x, y, w, h, label), ...] 屏幕物理坐标列表
        duration_ms: 框线显示时长（毫秒），到时自动清除
        """
        self._split_regions = regions
        self._split_regions_until = int(time.time() * 1000) + duration_ms
        self.update()

    def _clear_split_regions(self):
        """清除4等分区域框线。"""
        if self._split_regions:
            self._split_regions = []
            self._split_regions_until = 0
            self.update()

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

    # ========== 功能选择按钮（动态生成）==========

    # 功能按钮定义：mode_id → (显示名, 图标)
    # 注：显示名通过 S("button", ...) 从 ui_strings 读取
    MODE_DEFS = {
        "check_status": ("⊞", "mode_check_status"),
        "query_parts":  ("◎", "mode_query_parts"),
        "query_price":  ("⟐", "mode_query_price"),
        "translate":    ("⬢", "mode_translate"),
    }

    def _setup_buttons(self):
        """初始化按钮字典（按钮按需创建/销毁）。"""
        self._mode_buttons = {}  # mode_id → QPushButton

    def _create_mode_button(self, mode_id: str, label: str) -> QPushButton:
        """创建单个功能按钮。"""
        btn_bg_r, btn_bg_g, btn_bg_b = _hex_to_rgb(BTN_DEFAULT_BG)
        btn_hover_r, btn_hover_g, btn_hover_b = _hex_to_rgb(BTN_HOVER_BORDER)
        btn_style = f"""
            QPushButton {{
                background-color: rgba({btn_bg_r}, {btn_bg_g}, {btn_bg_b}, 220);
                color: {BTN_DEFAULT_TEXT};
                border: 2px solid {BTN_DEFAULT_BORDER};
                border-radius: 6px;
                padding: 10px 24px;
                font-size: 16px;
                font-family: "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: rgba({btn_hover_r}, {btn_hover_g}, {btn_hover_b}, 30);
                border-color: {BTN_HOVER_BORDER};
                color: {BTN_HOVER_TEXT};
            }}
        """
        btn = WordWrapButton(label, self)
        btn.setStyleSheet(btn_style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.hide()
        btn.clicked.connect(lambda checked, m=mode_id: self._on_mode_clicked(m))
        return btn

    def _on_mode_clicked(self, mode: str):
        """按钮被点击：隐藏按钮面板，发射信号给 main.py 处理"""
        self._hide_mode_buttons()
        self.mode_selected.emit(mode)
        self._log(S.format("overlay", "mode_selected", mode=mode))

    def show_mode_buttons(self, enabled_modes: list):
        """截图完成后调用：根据启用的功能动态显示按钮。

        Args:
            enabled_modes: 启用的功能列表，如 ['check_status', 'query_parts', 'query_price']
        """
        print(f"[DEBUG show_mode_buttons] called, enabled_modes={enabled_modes}, _selecting={self._selecting}, _mode_buttons keys={list(self._mode_buttons.keys())}")
        # 清理旧按钮
        self._hide_mode_buttons()
        for btn in self._mode_buttons.values():
            btn.deleteLater()
        self._mode_buttons.clear()

        if not enabled_modes:
            self.label.setText(S("overlay", "no_features_enabled"))
            self.label.adjustSize()
            self.label.move((self.width() - self.label.width()) // 2, 20)
            self.label.show()
            self._hide_at = 0
            print("[DEBUG show_mode_buttons] no enabled modes, returning")
            return

        # 为每个启用的功能创建按钮
        for mode_id in enabled_modes:
            icon, string_key = self.MODE_DEFS.get(mode_id, ("", mode_id))
            display_name = S("button", string_key)
            label = f"{icon} {display_name}"
            btn = self._create_mode_button(mode_id, label)
            self._mode_buttons[mode_id] = btn

        # 布局按钮（纵向排列，屏幕居中）
        # 宽度 320 容纳约 20 个中文字 + 图标（16px 字体），高度 60 支持两行
        btn_width = 320
        btn_height = 60
        btn_gap = 14
        total_btns = len(self._mode_buttons)
        total_height = total_btns * btn_height + (total_btns - 1) * btn_gap
        start_x = (self.width() - btn_width) // 2
        start_y = (self.height() - total_height) // 2

        for i, (mode_id, btn) in enumerate(self._mode_buttons.items()):
            y = start_y + i * (btn_height + btn_gap)
            btn.setGeometry(start_x, y, btn_width, btn_height)
            btn.show()
            print(f"[DEBUG show_mode_buttons] btn {mode_id}: geometry=({start_x},{y},{btn_width},{btn_height}), visible={btn.isVisible()}, isWindow={btn.isWindow()}")

        # 提示文字放在按钮上方
        self.label.setText(S("overlay", "screenshot_done"))
        self.label.adjustSize()
        self.label.move((self.width() - self.label.width()) // 2, max(start_y - 40, 10))
        self.label.show()

        self._hide_at = 0  # 不自动隐藏，等用户选
        print(f"[DEBUG show_mode_buttons] done, total buttons={total_btns}, _hide_at={self._hide_at}")

    def _hide_mode_buttons(self):
        """隐藏所有功能按钮"""
        for btn in self._mode_buttons.values():
            btn.hide()

    # ========== 框选模式 ==========

    def start_selection(self):
        self._log("▶ 框选模式启动")
        print(f"[DEBUG start_selection] _selecting was {self._selecting}, _mode_buttons keys={list(self._mode_buttons.keys())}")
        self._selecting = True
        self._start_pos = None
        self._current_pos = self.mapFromGlobal(QCursor.pos())
        self._left_was_down = self._is_left_down()
        self._status = S("overlay", "selection_status_idle")
        self._annotations = []
        self._hide_mode_buttons()          # ★ 进入框选时隐藏按钮
        self._apply_mouse_passthrough(False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.label.hide()
        if hasattr(self, '_preview_label'):
            self._preview_label.hide()
        self._hide_at = 0
        # 确保 overlay 在最前面且可见
        self.show()
        self.raise_()
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
        # 框选结束后 500ms 内忽略右键（防止拖拽时误触右键清除按钮）
        self._ignore_right_until = int(time.time() * 1000) + 500
        self.update()

    def _track_mouse(self):
        if not self._selecting:
            return

        pos = self.mapFromGlobal(QCursor.pos())
        self._current_pos = pos
        left_down = self._is_left_down()

        if ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000:
            self._log("✕ 用户右键取消框选")
            self.label.setText(S("overlay", "selection_cancelled"))
            self.label.adjustSize()
            self.label.move(50, 50)
            self.label.show()
            self._hide_at = int(time.time() * 1000) + 3000
            self.end_selection()
            return

        if self._is_esc_down():
            self._log("✕ 用户按 ESC 取消框选")
            self.label.setText(S("overlay", "selection_cancelled"))
            self.label.adjustSize()
            self.label.move(50, 50)
            self.label.show()
            self._hide_at = int(time.time() * 1000) + 3000
            self.end_selection()
            return

        if left_down and not self._left_was_down:
            self._start_pos = pos
            self._left_was_down = True
            self._status = S.format("overlay", "selection_status_pressed", x=pos.x(), y=pos.y())
            self._log(f"↓ 左键按下 @ ({pos.x()},{pos.y()})")

        elif left_down and self._left_was_down:
            if self._start_pos:
                w = abs(pos.x() - self._start_pos.x())
                h = abs(pos.y() - self._start_pos.y())
                self._status = S.format("overlay", "selection_status_dragging", w=w, h=h)

        elif not left_down and self._left_was_down:
            self._left_was_down = False
            self._log(f"↑ 左键松开 @ ({pos.x()},{pos.y()})")
            if self._start_pos:
                self._status = S("overlay", "selection_status_released")
                self._finish_selection()
            else:
                self._status = S("overlay", "selection_status_idle")
            return

        else:
            self._left_was_down = left_down
            self._status = S("overlay", "selection_status_idle")

        self.update()

    def _finish_selection(self):
        p1, p2 = self._start_pos, self._current_pos
        left, right = min(p1.x(), p2.x()), max(p1.x(), p2.x())
        top, bottom = min(p1.y(), p2.y()), max(p1.y(), p2.y())
        w, h = right - left, bottom - top
        print(f"[DEBUG _finish_selection] region=({left},{top},{right},{bottom}) w={w} h={h}")

        if w > 20 and h > 20:
            self._saved_region = (left, top, right, bottom)
            self._save_region()
            msg = S.format("overlay", "region_saved", l=left, t=top, r=right, b=bottom, w=w, h=h)
            self._log(f"✓ {msg}")
            self.label.setText(msg)
        else:
            msg = S.format("overlay", "region_too_small", w=w, h=h)
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
        default_color = CYBER_YELLOW
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

                # 背景颜色：2077 深蓝黑半透明
                bg_color = QColor(*OVERLAY_BG_COLOR)

                if '\n' in text:
                    # === 多行文本 ===
                    lines = text.split('\n')
                    max_tw = max(fm.boundingRect(line).width() for line in lines) + 16
                    total_th = line_height * len(lines) + 8

                    # 绘制半透明背景 + 2077 风格左边框装饰条
                    painter.fillRect(x, y, max_tw, total_th, bg_color)
                    painter.fillRect(x, y, 3, total_th, QColor(str(CYBER_YELLOW)))

                    # 逐行绘制：有 line_colors 则按行着色，否则统一用 color
                    for i, line in enumerate(lines):
                        if line_colors and i < len(line_colors):
                            painter.setPen(QColor(str(line_colors[i])))
                        else:
                            painter.setPen(QColor(str(color)))
                        line_y = y + fm.ascent() + 2 + i * line_height
                        painter.drawText(x + 12, line_y, line)
                else:
                    # === 单行文本 ===
                    tw = fm.boundingRect(text).width() + 16
                    th = fm.height() + 6
                    painter.fillRect(x, y, tw, th, bg_color)
                    painter.fillRect(x, y, 3, th, QColor(str(CYBER_YELLOW)))
                    painter.setPen(QColor(str(color)))
                    painter.drawText(x + 10, y + fm.ascent() + 3, text)

        # ★ 绘制4等分区域框线（价格查询用，物理坐标 → 需除以dpi转逻辑坐标）
        if self._split_regions:
            dpi = self._dpi_scale
            colors = [
                QColor(255, 50, 50),      # 红
                QColor(50, 255, 50),      # 绿
                QColor(50, 180, 255),     # 蓝
                QColor(255, 50, 255),     # 紫
            ]
            painter.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
            for idx, (rx, ry, rw, rh, label) in enumerate(self._split_regions):
                color = colors[idx % len(colors)]
                # 物理坐标 → 逻辑坐标
                lx = int(rx / dpi)
                ly = int(ry / dpi)
                lw = int(rw / dpi)
                lh = int(rh / dpi)
                pen = QPen(color, 3)
                painter.setPen(pen)
                painter.drawRect(lx, ly, lw, lh)

                # 标签
                fm = painter.fontMetrics()
                label_w = fm.boundingRect(label).width() + 12
                label_h = fm.height() + 6
                label_y = ly - label_h - 4
                if label_y < 0:
                    label_y = ly + lh + 4
                painter.fillRect(lx, label_y, label_w, label_h, color)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(lx + 6, label_y + fm.ascent() + 2, label)

        if not self._selecting:
            return

        painter.fillRect(self.rect(), QColor(*OVERLAY_SELECTION_OVERLAY))

        if self._status:
            painter.fillRect(0, 0, self.width(), 36, QColor(*OVERLAY_STATUS_BG))
            painter.setPen(QColor(str(CYBER_YELLOW)))
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

        pen = QPen(QColor(str(OVERLAY_SELECTION_BORDER)), 2)
        painter.setPen(pen)
        painter.drawRect(x, y, w, h)

        painter.setPen(QColor(str(CYBER_CYAN)))
        painter.setFont(QFont("Microsoft YaHei", 11))
        painter.drawText(x + 5, y - 8, f"{w} × {h}")

    def _draw_crosshair(self, painter, pos):
        pen = QPen(QColor(str(OVERLAY_CROSSHAIR_COLOR)), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(0, pos.y(), self.width(), pos.y())
        painter.drawLine(pos.x(), 0, pos.x(), self.height())
        painter.setPen(QPen(QColor(str(OVERLAY_CROSSHAIR_COLOR)), 2))
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
        self.label.setStyleSheet(f"color: {CYBER_YELLOW}; background: transparent;")

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

        # 清理过期的标注（避免 paintEvent 每帧遍历全列表）
        if self._annotations:
            active = [a for a in self._annotations if a[3] > now]
            if len(active) != len(self._annotations):
                self._annotations = active
                self.update()

        # 右键清除标注（非框选模式）
        if not self._selecting:
            right_now = self._is_right_down()
            if right_now and not self._right_was_down and now > self._ignore_right_until:
                had_annotations = len(self._annotations) > 0
                had_buttons = any(btn.isVisible() for btn in self._mode_buttons.values())
                print(f"[DEBUG _check_auto_hide] RIGHT CLICK DETECTED, had_annotations={had_annotations}, had_buttons={had_buttons}")
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

        # 清除过期的4等分区域框线
        if self._split_regions and now > self._split_regions_until:
            self._clear_split_regions()

    def refresh_theme(self):
        """主题变更时刷新 Overlay 中缓存的样式（label、按钮的 stylesheet）。"""
        # label 样式
        self.label.setStyleSheet(f"color: {CYBER_YELLOW}; background: transparent;")

        # 按钮样式（重建 rgba + stylesheet）
        btn_bg_r, btn_bg_g, btn_bg_b = _hex_to_rgb(BTN_DEFAULT_BG)
        btn_hover_r, btn_hover_g, btn_hover_b = _hex_to_rgb(BTN_HOVER_BORDER)
        btn_style = f"""
            QPushButton {{
                background-color: rgba({btn_bg_r}, {btn_bg_g}, {btn_bg_b}, 220);
                color: {BTN_DEFAULT_TEXT};
                border: 2px solid {BTN_DEFAULT_BORDER};
                border-radius: 6px;
                padding: 10px 24px;
                font-size: 16px;
                font-family: "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: rgba({btn_hover_r}, {btn_hover_g}, {btn_hover_b}, 30);
                border-color: {BTN_HOVER_BORDER};
                color: {BTN_HOVER_TEXT};
            }}
        """
        for btn in self._mode_buttons.values():
            btn.setStyleSheet(btn_style)

        # 强制重绘
        self.update()

    def _log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _schedule_call(self, callback, delay_ms=0):
        """从任意线程调度回调到主线程执行。"""
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(delay_ms, callback)
