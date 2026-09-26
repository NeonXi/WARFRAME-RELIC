"""
[L4] CyberPanel — 赛博风格面板容器

继承: CyberWidgetMixin + QFrame
依赖: core.tokens.manager
职责: 带标题栏的面板,切角+边框+可选 title

用于包裹内容区域的通用面板，提供切角背景、边框和可选的标题栏。

使用方式::

    panel = CyberPanel(title="数据总览")
    layout = QVBoxLayout(panel.content_widget())
    layout.addWidget(some_content)

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QFrame.__init__(self, parent)
- ✗ 禁止 paintEvent 漏 super() → 标题栏文字会消失
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止调 Service / 发网络请求 / 读写 JSON

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QLabel,
)
from PySide6.QtGui import QPaintEvent
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
from PySide6.QtCore import Qt

from core.widgets.base import CyberWidgetMixin


class CyberPanel(CyberWidgetMixin, QFrame):
    """赛博风格面板容器。

    Attributes:
        title: 面板标题文字（可选）
    """

    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
    ):
        QFrame.__init__(self, parent)

        self._title = title

        # 布局：外层 frame 包含标题 + 内容区
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # 标题栏
        if title:
            self._title_label = QLabel(title)
            self._title_label.setObjectName("cyberPanelTitle")
            title_font = self._title_label.font()
            title_font.setBold(True)
            title_fs = self.space("font.md_lg", 15)
            title_font.setPointSize(title_fs)
            self._title_label.setFont(title_font)
            self._title_label.setFixedHeight(36)
            self._title_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            title_pad = self.space("spacing.md", 12)
            self._title_label.setContentsMargins(title_pad, 0, title_pad, 0)
            self._layout.addWidget(self._title_label)
        else:
            self._title_label = None

        # 内容区容器
        self._content = QWidget()
        self._content.setObjectName("cyberPanelContent")
        content_pad = self.space("spacing.md", 12)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(content_pad, content_pad, content_pad, content_pad)
        self._layout.addWidget(self._content, stretch=1)

        # 样式：透明背景让玻璃效果透出下层
        self.setStyleSheet("""
            QFrame#CyberPanel { border: none; background: transparent; }
            QLabel#cyberPanelTitle {
                background: transparent;
                border: none;
                border-bottom: 1px solid transparent;
            }
            QWidget#cyberPanelContent { background: transparent; }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("CyberPanel")

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value
        if self._title_label:
            self._title_label.setText(value)
        self.update()

    def content_widget(self) -> QWidget:
        """返回内容区 widget，用于添加子控件。"""
        return self._content

    def content_layout(self) -> QVBoxLayout:
        """返回内容区的布局。"""
        return self._content_layout

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        corner = self.space("components.panel.corner_size", 12)
        path = self._chamfered_path(self.rect(), corner, mode="all")

        is_glass = self._is_glass_mode()
        if is_glass:
            # 玻璃拟态：半透明填充 + 细边框 + 微弱高光
            bg_color = self.token_color("components.panel.bg")
            border_color = self.token_color("components.panel.border")
            self._draw_glass_bg(painter, self.rect(), corner, bg_color, border_color)
            # 玻璃模式下不画角落装饰线（简洁风格）
        else:
            # 赛博朋克风格：纯色填充 + 外发光 + 角落装饰
            opacity = float(self.token("components.panel.bg_opacity") or "0.92")
            bg_color = self._cyber_immersive_resolve_bg("components.panel.bg", opacity)
            painter.fillPath(path, QBrush(bg_color))

            # 边框
            border_color = self.token_color("components.panel.border")
            border_width = float(self.token("components.panel.border_width") or "1")
            painter.setPen(QPen(border_color, border_width))
            painter.drawPath(path)

            # 角落装饰线
            self._draw_corner_decor(painter, path)

        super().paintEvent(event)

    def _draw_corner_decor(self, painter: QPainter, path: QPainterPath) -> None:
        """绘制四角的装饰短线。"""
        decor_color = self.token_color("components.panel.corner_decor.color")
        length = self.space("components.panel.corner_decor.length", 12)
        thickness = float(self.token("components.panel.corner_decor.thickness") or "2")

        r = self.rect()
        c = min(length, r.width() / 4, r.height() / 4)

        pen = QPen(decor_color, thickness)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)

        # 左上角 ┐
        painter.drawLine(int(r.left() + c), int(r.top()), int(r.left()), int(r.top()))
        painter.drawLine(int(r.left()), int(r.top()), int(r.left()), int(r.top() + c))

        # 右上角 ┌
        painter.drawLine(int(r.right() - c), int(r.top()), int(r.right()), int(r.top()))
        painter.drawLine(int(r.right()), int(r.top()), int(r.right()), int(r.top() + c))

        # 左下角 └
        painter.drawLine(int(r.left() + c), int(r.bottom()), int(r.left()), int(r.bottom()))
        painter.drawLine(int(r.left()), int(r.bottom()), int(r.left()), int(r.bottom() - c))

        # 右下角 ┘
        painter.drawLine(int(r.right() - c), int(r.bottom()), int(r.right()), int(r.bottom()))
        painter.drawLine(int(r.right()), int(r.bottom()), int(r.right()), int(r.bottom() - c))
