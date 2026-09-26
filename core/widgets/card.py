"""
[L4] CyberCard — 赛博风格卡片

继承: CyberWidgetMixin + QFrame
依赖: core.tokens.manager
职责: 轻量级内容卡片,用于展示信息块或可点击项

轻量级内容卡片，用于展示信息块或可点击项。
比 CyberPanel 更轻量，适合列表内嵌套。

使用方式::

    card = CyberCard()
    layout = QVBoxLayout(card.content_widget())
    layout.addWidget(QLabel("卡片内容"))

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QFrame.__init__(self, parent)
- ✗ 禁止 paintEvent 漏 super() → 文字/快捷键会失效
- ✗ 禁止 paintEvent 顺序写反 → 必须 QPainter → 自绘 → super()
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止调 Service / 发网络请求 / 读写 JSON

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QLabel,
)
from PySide6.QtGui import (
    QPainter, QPaintEvent, QMouseEvent,
    QColor, QPen, QBrush, QPainterPath,
)
from PySide6.QtCore import Qt, QRectF

from core.widgets.base import CyberWidgetMixin


class CyberCard(CyberWidgetMixin, QFrame):
    """赛博风格卡片。

    支持 hover 状态变化（背景提亮），可用于交互式卡片。
    """

    def __init__(
        self,
        title: str = "",
        clickable: bool = False,
        parent: Optional[QWidget] = None,
    ):
        QFrame.__init__(self, parent)

        self._clickable = clickable

        # 布局
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # ── 可选标题栏 ──
        if title:
            self._title_bar = QLabel(title)
            from PySide6.QtGui import QFont
            try:
                font_size = self.space("font.xs", 11)
            except Exception:
                font_size = 11
            title_font = QFont("Iceberg", font_size)
            self._title_bar.setFont(title_font)
            accent = self.token_color("accent.primary")
            self._title_bar.setStyleSheet(f"color: {accent.name()}; padding: 10px 16px 6px 16px;")
            self._layout.addWidget(self._title_bar)
        else:
            self._title_bar = None

        # 内容区
        self._content = QWidget()
        pad_h = self.space("components.card.padding_h", 16)
        pad_v_top = 4 if title else self.space("components.card.padding_v", 12)
        pad_v_bot = self.space("components.card.padding_v", 12)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(pad_h, pad_v_top, pad_h, pad_v_bot)
        self._layout.addWidget(self._content)

        # 样式：透明背景让玻璃效果透出下层
        self.setStyleSheet("""
            QFrame#CyberCard { border: none; background: transparent; }
            QWidget#cyberCardContent { background: transparent; }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("CyberCard")
        self._content.setObjectName("cyberCardContent")

        # 可点击时光标
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def clickable(self) -> bool:
        return self._clickable

    @clickable.setter
    def clickable(self, value: bool) -> None:
        self._clickable = value
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if value
            else Qt.CursorShape.ArrowCursor
        )

    def content_widget(self) -> QWidget:
        """返回内容区 widget。"""
        return self._content

    def content_layout(self) -> QVBoxLayout:
        """返回内容区布局。"""
        return self._content_layout

    # ── 事件 ──

    def enterEvent(self, event) -> None:
        if self._clickable:
            self.cyber_enter_event(event)

    def leaveEvent(self, event) -> None:
        if self._clickable:
            self.cyber_leave_event(event)

    def mousePressEvent(self, event) -> None:
        if self._clickable and not self.isEnabled():
            return
        super().mousePressEvent(event)

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        corner = self.space("components.card.corner_size", 8)
        path = self._chamfered_path(QRectF(self.rect()), corner, mode="br")

        # 背景
        state = self._state
        is_glass = self._is_glass_mode()

        if is_glass:
            # 玻璃拟态：半透明填充 + 细边框 + 微弱高光
            bg_color = self.token_color("components.card.bg")
            if state == "hover" and self._clickable:
                # hover 时稍微加深
                bg_color.setAlphaF(min(bg_color.alphaF() * 1.3, 0.6))
            border_color = self.token_color("components.card.border")
            self._draw_glass_bg(painter, self.rect(), corner, bg_color, border_color)
        else:
            # 赛博朋克风格：纯色填充 + 边框
            if state == "hover" and self._clickable:
                hover_color = self._cyber_immersive_resolve_bg(
                    "components.list_item.bg_hover", 0.85
                )
                painter.fillPath(path, QBrush(hover_color))
            else:
                bg_color = self._cyber_immersive_resolve_bg("components.card.bg", 0.85)
                painter.fillPath(path, QBrush(bg_color))

            # 边框
            border_color = self.token_color("components.card.border")
            border_width = float(self.token("components.card.border_width") or "1")
            painter.setPen(QPen(border_color, border_width))
            painter.drawPath(path)

        super().paintEvent(event)
