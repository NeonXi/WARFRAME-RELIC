"""
[L4/L5] CyberProgressBar — 切角进度条(支持内嵌文字)

继承: CyberWidgetMixin + QWidget
依赖: core.tokens.manager(只此一个外部)
职责: 绘制切角轨道 + 比例填充 + 居中文字(文字在填充上层)
信号: 无

用法:
    bar = CyberProgressBar()
    bar.set_state("07:42", 0.63, "accent.primary")
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPaintEvent,
    QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget

from core.widgets.base import CyberWidgetMixin


class CyberProgressBar(CyberWidgetMixin, QWidget):
    """赛博风切角进度条。

    刷新时只调 set_state() 更新数据并触发重绘,
    不在每次刷新时改样式,以避免闪烁。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        QWidget.__init__(self, parent)

        self._cyber_text: str = ""
        self._cyber_fraction: float = 1.0
        # 填充色 token 路径(由外部按语义传入)
        self._cyber_color_path: str = "accent.primary"

    def set_state(
        self, text: str, fraction: float, color_path: str
    ) -> None:
        """更新进度条。

        Args:
            text: 居中显示的文字(如倒计时)
            fraction: 填充比例 0.0~1.0
            color_path: 填充色 token 路径
        """
        self._cyber_text = text
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0
        self._cyber_fraction = fraction
        self._cyber_color_path = color_path
        self.update()

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        corner = float(self.space("components.progress.corner_size", 4))
        pad = self.space("spacing.xs", 4)
        rect = QRectF(self.rect()).adjusted(pad, pad, -pad, -pad)

        # 切角轨道路径
        path = self._chamfered_path(rect, corner, mode="all")

        is_glass = self._is_glass_mode()

        # ① 轨道底色
        if is_glass:
            # 玻璃拟态：半透明轨道 + 细边框
            track_bg = self.token_color("components.progress.track_bg")
            track_border = self.token_color("components.progress.track_border")
            self._draw_glass_bg(painter, rect, corner, track_bg, track_border)
        else:
            track_bg = self.token_color("components.progress.track_bg")
            painter.fillPath(path, QBrush(track_bg))

        # ② 比例填充:裁剪到轨道内,不会超出切角
        fill_color = QColor(self.token_color(self._cyber_color_path))
        fill_color.setAlpha(150)
        fill_w = rect.width() * self._cyber_fraction
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(
            QRectF(rect.left(), rect.top(), fill_w, rect.height()),
            QBrush(fill_color)
        )
        painter.restore()

        # ③ 轨道边框（玻璃模式下已由 _draw_glass_bg 处理）
        if not is_glass:
            border = self.token_color("components.progress.track_border")
            painter.setPen(QPen(border, 1))
            painter.drawPath(path)

        # ④ 居中文字:深色描边 + 主色填充,保证在任何底色上可读
        if self._cyber_text:
            font = QFont(self.font())
            text_path = QPainterPath()
            metrics = QFontMetrics(font)
            br = metrics.tightBoundingRect(self._cyber_text)
            text_path.addText(
                QPointF(-br.width() / 2 - br.left(),
                        -br.height() / 2 - br.top()),
                font, self._cyber_text
            )
            text_path.translate(rect.center())

            stroke = QColor(self.token_color("bg.base"))
            stroke.setAlpha(220)
            painter.setPen(QPen(stroke, 2))
            painter.drawPath(text_path)

            text_color = self.token_color("components.progress.text")
            painter.fillPath(text_path, QBrush(text_color))

        painter.end()
