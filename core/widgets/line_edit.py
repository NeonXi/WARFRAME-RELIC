"""
[L4] CyberLineEdit — 赛博风格输入框

继承: CyberWidgetMixin + QLineEdit
依赖: core.tokens.manager
职责: 自绘切角背景+状态边框,保留 Qt 原生输入能力(光标/选中/IME)

继承 QLineEdit 原生能力（文字输入、撤销、复制粘贴等），
仅覆盖视觉部分（切角背景 + 状态边框）。

使用方式::

    input = CyberLineEdit(placeholder="搜索...")
    input.set_placeholder("请输入内容")

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QLineEdit.__init__(self, parent)
- ✗ 禁止 paintEvent 漏 super() → 光标/选中/IME 会失效
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止调 Service / 发网络请求 / 读写 JSON

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLineEdit, QWidget
from PySide6.QtGui import (
    QPainter, QPaintEvent, QFocusEvent, QColor,
    QPen, QBrush, QPainterPath,
)
from PySide6.QtCore import Qt, QRectF

from core.widgets.base import CyberWidgetMixin


class CyberLineEdit(CyberWidgetMixin, QLineEdit):
    """赛博风格输入框。"""

    def __init__(
        self,
        placeholder: str = "",
        parent: Optional[QWidget] = None,
    ):
        QLineEdit.__init__(self, parent)

        if placeholder:
            self.setPlaceholderText(placeholder)

        # 尺寸
        h = self.space("height.input", 36)
        self.setFixedHeight(h)

        # 隐藏原生边框和背景，完全自绘
        self.setStyleSheet("""
            QLineEdit {
                border: none;
                background: transparent;
                padding-left: 12px;
                padding-right: 12px;
            }
        """)

        # 文字颜色
        self._cyber_subscribe_theme()
        self.cyber_refresh_style()

    def cyber_refresh_style(self) -> None:
        """重建输入框文字色(palette token 内联,主题切换时更新)。"""
        text_color = self.token_color("components.input.text")
        palette = self.palette()
        palette.setColor(palette.ColorRole.Text, text_color)
        self.setPalette(palette)

    def set_placeholder(self, text: str) -> None:
        """设置占位符文字。"""
        self.setPlaceholderText(text)

    # ── 事件 ──

    def enterEvent(self, event) -> None:
        self.cyber_enter_event(event)

    def leaveEvent(self, event) -> None:
        self.cyber_leave_event(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        self.cyber_focus_in_event(event)
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.cyber_focus_out_event(event)
        super().focusOutEvent(event)

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        corner = self.space("components.input.corner_size", 6)
        path = self._chamfered_path(QRectF(self.rect()), corner, mode="all")

        # 背景(沉浸黑色模式时覆写 RGB,折减 alpha)
        state = self._state
        is_glass = self._is_glass_mode()

        if is_glass:
            # 玻璃拟态：半透明填充 + 细边框 + 微弱高光
            bg_color = self.token_color("components.input.bg")
            if state == "focused":
                border_color = self.token_color("components.input.border_focus")
            else:
                border_color = self.token_color("components.input.border")
            self._draw_glass_bg(painter, self.rect(), corner, bg_color, border_color)
        else:
            # 赛博朋克风格：纯色填充 + 边框
            if state == "focused":
                # focused 态优先用 semantic.state.focused.bg,token 缺失时回退到 input.bg
                try:
                    base_c = self.token_color("semantic.state.focused.bg")
                except Exception:
                    base_c = self.token_color("components.input.bg")
                bg_color = self._cyber_immersive_resolve_bg_qcolor(base_c, 0.95)
            elif state == "hover":
                bg_color = self._cyber_immersive_resolve_bg("components.input.bg", 0.85)
            else:
                bg_color = self._cyber_immersive_resolve_bg("components.input.bg", 0.75)

            painter.fillPath(path, QBrush(bg_color))

            # 边框
            if state == "focused":
                border_color = self.token_color("components.input.border_focus")
                pen_width = 1.5
            else:
                border_color = self.token_color("components.input.border")
                pen_width = 1.0

            painter.setPen(QPen(border_color, pen_width))
            painter.drawPath(path)

        # 让 Qt 渲染文字（光标、选中、占位符等）
        super().paintEvent(event)
