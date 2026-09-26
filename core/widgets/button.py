"""
[L4] CyberButton — 赛博风格按钮

继承: CyberWidgetMixin + QPushButton
依赖: core.tokens.manager
职责: 自绘切角+外发光,四种变体(solid/outlined/ghost/danger)
信号: clicked(继承自 QPushButton)

四种视觉变体:
- solid:    实心填充(主操作)
- outlined: 描边边框(次操作)
- ghost:    幽灵透明(第三操作)
- danger:   红色危险(删除/破坏性操作)

使用方式::

    btn = CyberButton("确认", variant="solid")
    btn = CyberButton("取消", variant="outlined")
    btn = CyberButton("详情", variant="ghost")
    btn = CyberButton("删除", variant="semantic.danger")

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
           (Widget 只绘制和发信号,绝不调业务/数据)
必读规范:  .trae/rules/开发规范.md §6.4 (L4/L5 控件层)

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QPushButton.__init__(self, text, parent)
- ✗ 禁止 paintEvent 漏 super() → 文字/快捷键会失效
- ✗ 禁止 paintEvent 顺序写反 → 必须 QPainter → 自绘 → super()
- ✗ 禁止硬编码颜色 "#FF0000" 或尺寸 26 → 必须 self.token() / self.space()
- ✗ 禁止调 Service / 发网络请求 / 读写 JSON → Widget 只画 UI
- ✗ 禁止用 _xxx 命名私有属性 → 必须 _cyber_xxx 前缀

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4,别走捷径。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtWidgets import QPushButton, QWidget
from PySide6.QtGui import QPainter, QPaintEvent, QMouseEvent, QFocusEvent
from PySide6.QtCore import Qt

from core.widgets.base import CyberWidgetMixin


class ButtonVariant(str, Enum):
    """按钮视觉变体。"""
    SOLID = "solid"
    OUTLINED = "outlined"
    GHOST = "ghost"
    DANGER = "semantic.danger"


class CyberButton(CyberWidgetMixin, QPushButton):
    """赛博风格按钮。

    Attributes:
        variant: 按钮变体 (solid / outlined / ghost)
    """

    def __init__(
        self,
        text: str = "",
        variant: str | ButtonVariant = ButtonVariant.SOLID,
        parent: Optional[QWidget] = None,
    ):
        QPushButton.__init__(self, text, parent)

        if isinstance(variant, str):
            self._variant = ButtonVariant(variant)
        else:
            self._variant = variant

        # 尺寸
        h = self.space("height.btn_md", 36)
        self.setFixedHeight(h)
        self.setMinimumWidth(80)

        # 光标
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 无原生边框/背景，完全自绘；透明背景让玻璃效果透出下层
        self.setStyleSheet("QPushButton { border: none; background: transparent; }")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    # ── 属性 ──

    @property
    def variant(self) -> ButtonVariant:
        return self._variant

    @variant.setter
    def variant(self, value: str | ButtonVariant) -> None:
        if isinstance(value, str):
            self._variant = ButtonVariant(value)
        else:
            self._variant = value
        self.update()

    # ── 事件转发到状态机 ──

    def enterEvent(self, event) -> None:
        self.cyber_enter_event(event)

    def leaveEvent(self, event) -> None:
        self.cyber_leave_event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.cyber_mouse_press_event(event)
        event.accept()  # 不调用 super，阻止原生渲染

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.cyber_mouse_release_event(event)
        # 发出 clicked 信号（因为不调用 super，需要手动触发）
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        event.accept()  # 不调用 super，阻止原生渲染

    def focusInEvent(self, event: QFocusEvent) -> None:
        self.cyber_focus_in_event(event)
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.cyber_focus_out_event(event)
        super().focusOutEvent(event)

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        from PySide6.QtGui import (
            QColor, QPen, QBrush, QFont, QFontMetrics,
            QPainterPath, QLinearGradient,
        )
        from PySide6.QtCore import QPointF, QRectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        corner = self.space("components.button.solid.corner_size", 8)
        path = self._chamfered_path(QRectF(self.rect()), corner, mode="br")

        # ── 根据变体和状态取色 ──
        v = self._variant.value
        state = self._state

        if v == "solid":
            fill_key = f"components.button.solid.fill"
            text_key = f"components.button.solid.text"
            border_key = f"components.button.solid.border"
            glow_opacity_map = {"hover": 0.20, "focused": 0.15}
        elif v == "outlined":
            fill_key = f"components.button.outlined.fill"
            text_key = f"components.button.outlined.text"
            border_key = f"components.button.outlined.border"
            glow_opacity_map = {"hover": 0.12, "focused": 0.10}
        else:  # ghost (also fallback for unknown variants)
            fill_key = f"components.button.ghost.fill"
            text_key = f"components.button.ghost.text"
            border_key = f"components.button.ghost.border"
            glow_opacity_map = {}

        # ── danger 变体：从 token 推导颜色 ──
        if v == "semantic.danger":
            base_danger = self.token_color("alias.semantic.danger")
            bg_color = QColor(base_danger)
            bg_color.setAlpha(20)                  # rgba(~0.08)
            text_color = base_danger
            border_color = base_danger
        else:
            bg_color = self.token_color(fill_key)
            text_color = self.token_color(text_key)
            border_color = self.token_color(border_key)

        # 状态覆盖：优先使用组件级 token，fallback 到 semantic
        if state == "hover":
            if v == "semantic.danger":
                bg_color = QColor(base_danger)
                bg_color.setAlpha(51)               # rgba(~0.20)
                text_color = base_danger            # 统一使用 token 色
                border_color = base_danger
            else:
                hover_fill = f"components.button.{v}_hover.fill"
                try:
                    bg_color = self.token_color(hover_fill)
                except Exception:
                    bg_color = self.token_color(f"semantic.state.hover.bg")
        elif state == "pressed":
            if v == "semantic.danger":
                bg_color = QColor(base_danger)
                bg_color.setAlpha(90)               # rgba(~0.35)
                text_color = base_danger
                border_color = base_danger
            else:
                # 背景覆盖
                pressed_fill = f"components.button.{v}_pressed.fill"
                try:
                    bg_color = self.token_color(pressed_fill)
                except Exception:
                    bg_color = self.token_color(f"semantic.state.pressed.bg")
                # 文字覆盖为黄色
                pressed_text = f"components.button.{v}_pressed.text"
                try:
                    text_color = self.token_color(pressed_text)
                except Exception:
                    text_color = self.token_color("semantic.warning")
                # 边框覆盖为黄色
                pressed_border = f"components.button.{v}_pressed.border"
                try:
                    border_color = self.token_color(pressed_border)
                except Exception:
                    border_color = self.token_color("semantic.warning")
        elif state == "disabled":
            if v != "semantic.danger":
                bg_color = self.token_color(f"semantic.state.disabled.bg")
                text_color = self.token_color(f"semantic.state.disabled.text")

        # ── 填充背景 ──
        is_glass = self._is_glass_mode()
        if is_glass:
            # 玻璃拟态：半透明填充 + 细边框 + 微弱高光
            glass_bg = QColor(bg_color)
            if v == "ghost":
                glass_bg.setAlphaF(0)
            elif v == "outlined":
                glass_bg.setAlphaF(0.08 if state == "normal" else 0.15)
            # solid 直接用 token 中的透明度（如 rgba(168,199,250,0.15)）
            self._draw_glass_bg(
                painter, QRectF(self.rect()), corner,
                glass_bg, border_color, border_width=1
            )
            # 玻璃模式下不画外发光，边框已在 _draw_glass_bg 中处理
        else:
            # 赛博朋克风格：纯色填充 + 外发光
            if v == "ghost":
                bg_color.setAlphaF(0)
            elif v == "outlined":
                bg_color.setAlphaF(0.06 if state == "normal" else 0.12)

            painter.fillPath(path, QBrush(bg_color))

            # ── 外发光（仅 solid / outlined）──
            if glow_opacity_map and state in glow_opacity_map:
                glow_color = self.token_color("accent.secondary")
                glow_color.setAlphaF(glow_opacity_map[state])
                painter.setPen(QPen(glow_color, 1))
                painter.drawPath(path)

            # ── 边框 ──
            if v in ("outlined", "ghost", "semantic.danger"):
                pen_width = 1.5 if state == "focused" else 1.0
                pen_color = border_color
                if state == "focused":
                    pen_color = self.token_color("border.focus")
                painter.setPen(QPen(pen_color, pen_width))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
            elif v == "solid":
                # solid 默认无边框，focused / pressed 时画细边框
                if state in ("focused", "pressed"):
                    painter.setPen(QPen(border_color, 1.2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)

        # ── 文字（交给 Qt 原生渲染）──
        painter.setPen(text_color)
        font_size = self.space("font_size.sm", 10)
        font = QFont()
        font.setPointSize(font_size)
        font.setBold(True)
        painter.setFont(font)

        fm = QFontMetrics(font)
        txt = self.text()
        if txt:
            cx = self.width() / 2 - fm.horizontalAdvance(txt) / 2
            cy = self.height() / 2 + fm.ascent() / 2 - fm.descent() / 2
            painter.drawText(int(cx), int(cy), txt)
