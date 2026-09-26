"""
[L4] CyberComboBox — 赛博风格下拉菜单

继承: CyberWidgetMixin + QComboBox
依赖: core.tokens.manager
职责: 自绘切角+状态边框+下拉箭头,保留 Qt 原生弹窗与搜索

继承 QComboBox 原生能力（下拉列表、搜索过滤等），
仅覆盖视觉部分（切角背景 + 状态边框 + 下拉箭头）。

使用方式::

    combo = CyberComboBox()
    combo.addItems(["选项 A", "选项 B", "选项 C"])

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QComboBox.__init__(self, parent)
- ✗ 禁止 paintEvent 漏 super() → 下拉弹窗/键盘搜索会失效
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止调 Service / 发网络请求 / 读写 JSON

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QComboBox, QWidget
from PySide6.QtGui import (
    QPainter, QPaintEvent, QFocusEvent, QColor,
    QPen, QBrush, QPainterPath,
)
from PySide6.QtCore import Qt, QRect, QRectF

from core.widgets.base import CyberWidgetMixin


class CyberComboBox(CyberWidgetMixin, QComboBox):
    """赛博风格下拉菜单。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        QComboBox.__init__(self, parent)

        # 尺寸
        h = self.space("height.input", 36)
        self.setFixedHeight(h)

        # 隐藏原生边框和背景,完全自绘(弹窗 QSS 拆到 _apply_popup_style,
        # 沉浸黑色模式切换时由 AppShell 重新调用以应用最新底色)
        self._apply_popup_style()

    # ── 事件 ──

    def wheelEvent(self, event) -> None:
        """禁用滚轮切换下拉选项，避免滚动页面时误改选项。"""
        event.ignore()

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
        from PySide6.QtGui import QPolygonF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        corner = self.space("components.input.corner_size", 6)
        path = self._chamfered_path(QRectF(self.rect()), corner, mode="all")

        # 背景(沉浸黑色模式时覆写 RGB,折减 alpha)
        state = self._state
        is_glass = self._is_glass_mode()

        if is_glass:
            # 玻璃拟态：半透明填充 + 细边框 + 微弱高光
            bg_color = self.token_color("components.combo_box.bg")
            if state == "focused":
                border_color = self.token_color("components.combo_box.border_focus")
            else:
                border_color = self.token_color("components.combo_box.border")
            self._draw_glass_bg(painter, self.rect(), corner, bg_color, border_color)
        else:
            # 赛博朋克风格：纯色填充 + 边框
            if state == "focused":
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

        # ── 下拉箭头（右侧绘制）──
        arrow_color = self.token_color("accent.secondary")
        if state == "hover" or state == "focused":
            arrow_color = self.token_color("accent.primary")
        painter.setPen(QPen(arrow_color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        ax = self.width() - 16
        ay = self.height() / 2 - 3
        arrow = QPolygonF([
            __import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(ax - 5, ay),
            __import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(ax + 5, ay),
            __import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(ax, ay + 7),
        ])
        painter.drawPolygon(arrow)

        # 让 Qt 渲染文字
        super().paintEvent(event)

    # ── 沉浸黑色模式 / 颜色预设切换刷新 ──

    def _apply_popup_style(self) -> None:
        """构造并应用下拉弹窗 QSS。

        沉浸黑色模式时,弹窗背景和选中/hover 项背景都覆写为纯黑,
        避免与本体底色不一致。由 __init__ 调用一次,沉浸颜色模式
        切换时由 AppShell 遍历调 cyber_refresh_immersive_style 重新调用。
        """
        # 弹窗背景:沉浸黑色模式时覆写为纯黑
        bg_raised = self._cyber_immersive_resolve_token_str("surface.raised", 1.0)
        text_main = self.token_color("text.primary").name()
        border_default = self.token_color("border.default").name()
        # 选中/hover 项背景:沉浸黑色模式时也覆写为纯黑
        selection_bg = self._cyber_immersive_resolve_token_str("neutral.dark", 1.0)
        accent_primary = self.token_color("accent.primary").name()

        self.setStyleSheet(f"""
            QComboBox {{
                border: none;
                background: transparent;
                padding-left: 12px;
                padding-right: 28px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {bg_raised};
                color: {text_main};
                border: 1px solid {border_default};
                selection-background-color: {selection_bg};
                selection-color: {accent_primary};
                outline: none;
            }}
            /* 下拉列表项 hover 样式 */
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                min-height: 28px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {selection_bg};
                color: {accent_primary};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {selection_bg};
                color: {accent_primary};
            }}
        """)

    def cyber_refresh_immersive_style(self) -> None:
        """沉浸模式 / 颜色预设变化时由 AppShell 调用,重设依赖 token 的 QSS。"""
        self._apply_popup_style()
