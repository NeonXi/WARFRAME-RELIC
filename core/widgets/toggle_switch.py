"""
[L4] CyberToggleSwitch — 赛博风格切角开关按钮

继承: CyberWidgetMixin + QPushButton(checkable)
依赖: core.tokens.manager
职责: 切角开关,关闭/开启两态切色
信号: toggled(bool)(继承自 QPushButton)

使用 CyberWidgetMixin + QPushButton（checkable）实现。
- 关闭态：透明填充 + 黄色描边（accent.primary）
- 开启态：黄色填充 + 深色文字（surface.base）
- hover 时淡入填充，pressed 时加深
- 右下角切角（br）——赛博朋克标志性风格

使用方式::

    sw = CyberToggleSwitch("GAUSS", checked=False)
    sw.toggled.connect(lambda checked: print(f"GAUSS: {checked}"))

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QPushButton.__init__(self, text, parent)
- ✗ 禁止 paintEvent 漏 super() → 文字/状态指示会失效
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止调 Service / 发网络请求 / 读写 JSON

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QPushButton, QWidget
from PySide6.QtGui import (
    QPainter, QPaintEvent, QMouseEvent, QFont, QFontMetrics, QPen, QBrush, QColor,
)
from PySide6.QtCore import Qt, QRectF

from core.widgets.base import CyberWidgetMixin


class CyberToggleSwitch(CyberWidgetMixin, QPushButton):
    """赛博风格切角开关按钮。

    属性：
        checked（继承自 QPushButton）— 开关状态

    信号：
        toggled(bool)（继承自 QPushButton）— 状态切换时发射
    """

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        parent: Optional[QWidget] = None,
        on_off: bool = False,
    ):
        QPushButton.__init__(self, text, parent)

        self.setCheckable(True)
        self.setChecked(checked)

        # ON/OFF 状态文字模式：开启后文字随状态显示 "ON"/"OFF"，
        # 忽略构造传入的 text（用于无标签、纯状态指示的开关）
        self._on_off_mode: bool = bool(on_off)

        h = self.space("height.toggle_sw", 28)
        self.setFixedHeight(h)
        self.setMinimumWidth(80)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QPushButton { border: none; background: transparent; }")

    # ── ON/OFF 模式 ──

    def set_on_off_mode(self, enabled: bool) -> None:
        """开关 ON/OFF 状态文字模式（True=文字随状态显示 ON/OFF）。"""
        enabled = bool(enabled)
        if self._on_off_mode == enabled:
            return
        self._on_off_mode = enabled
        self.update()

    # ── 事件转发到状态机 ──

    def enterEvent(self, event) -> None:
        self.cyber_enter_event(event)

    def leaveEvent(self, event) -> None:
        self.cyber_leave_event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.cyber_mouse_press_event(event)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.cyber_mouse_release_event(event)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.toggle()
        event.accept()

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        corner = self.space("components.button.solid.corner_size", 8)

        # 主色调：黄色（brand.yellow = #FFE600）
        accent = self.token_color("accent.primary")

        is_checked = self.isChecked()
        state = self._state

        # 切角路径
        path = self._chamfered_path(QRectF(0, 0, w, h), corner, mode="br")

        # ── 填充 ──
        is_glass = self._is_glass_mode()
        if is_glass:
            # 玻璃拟态：半透明填充 + 细边框 + 微弱高光
            if is_checked:
                # 开启态：主色半透明
                glass_bg = QColor(accent)
                glass_bg.setAlphaF(0.35)
                border_color = QColor(accent)
            else:
                # 关闭态：背景色半透明
                glass_bg = self.token_color("components.toggle.track_bg")
                border_color = self.token_color("components.toggle.track_border")
            self._draw_glass_bg(painter, QRectF(0, 0, w, h), corner, glass_bg, border_color)
        else:
            # 赛博朋克风格：纯色填充 + 外发光 + 边框
            fill = QColor(accent)
            if is_checked:
                if state == "pressed":
                    fill = fill.darker(130)
                elif state == "hover":
                    fill = fill.lighter(110)
            else:
                if state == "hover":
                    fill.setAlpha(20)       # 关闭态 hover：微弱显示
                elif state == "pressed":
                    fill.setAlpha(45)
                else:
                    fill.setAlpha(0)

            painter.fillPath(path, QBrush(fill))

            # ── 外发光（hover / pressed）──
            if state in ("hover", "pressed"):
                glow = QColor(accent)
                glow.setAlphaF(0.15 if state == "hover" else 0.22)
                painter.setPen(QPen(glow, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)

            # ── 边框 ──
            pen_color = QColor(accent)
            pen_width = 1.5
            painter.setPen(QPen(pen_color, pen_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # ── 文字 ──
        text_color = self.token_color("surface.base") if is_checked else accent
        font_size = self.space("font_size.sm", 10)
        font = QFont()
        font.setPointSize(font_size)
        font.setBold(True)
        painter.setPen(text_color)
        painter.setFont(font)

        fm = QFontMetrics(font)
        # ON/OFF 模式：文字随状态；否则用外部设置的 text
        txt = ("ON" if is_checked else "OFF") if self._on_off_mode else self.text()
        if txt:
            cx = w / 2.0 - fm.horizontalAdvance(txt) / 2.0
            cy = h / 2.0 + fm.ascent() / 2.0 - fm.descent() / 2.0
            painter.drawText(int(cx), int(cy), txt)

        painter.end()