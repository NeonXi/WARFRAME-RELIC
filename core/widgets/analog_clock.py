"""
[L4] CyberAnalogClock — 赛博风格自绘模拟时钟

继承: CyberWidgetMixin + QWidget
依赖: core.tokens.manager（经 mixin）、core.fonts、PySide6
职责: 纯自绘表盘（外圈/刻度/时针/分针/秒针），由页面每秒调用
      set_time() 驱动；自身不含任何定时器与业务数据。

设计说明:
  - 颜色/描边随主题自适应：paintEvent 内实时读 token，不内联 QSS，
    因此主题切换后下一次重绘即换色，无需订阅 theme_changed。
  - 尺寸按控件几何等比缩放（半径的百分比），窗口/卡片尺寸变化时
    表盘自动适配，不引入固定像素魔数。
  - 走时由页面层的 QTimer 每秒推一次 set_time()，控件本身
    "给多少画多少"，离屏（未显示）时不会空转。

分层红线（规范 §6.4）:
  - 禁止 import core.services / core.pages —— 本控件不认识"城市/时区"，
    只接收 (时, 分, 秒) 三个整数。
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import QWidget
from core.widgets.base import CyberWidgetMixin
from core.fonts import FONT_DISPLAY

# 表盘最小边长（4 的倍数；卡片内单列布局下足够看清指针）
_MIN_SIZE = 96


class CyberAnalogClock(CyberWidgetMixin, QWidget):
    """自绘模拟时钟表盘。

    用法::

        clock = CyberAnalogClock()
        clock.set_time(18, 30, 45)   # 18:30:45
    """

    def __init__(self, parent: QWidget | None = None):
        # Mixin 红线：必须显式调用目标基类 __init__，禁止 super().__init__()
        QWidget.__init__(self, parent)

        # 私有属性统一 _cyber_ 前缀（避开 Qt 内部命名空间）
        self._cyber_hour = 0
        self._cyber_minute = 0
        self._cyber_second = 0

        self.setMinimumSize(_MIN_SIZE, _MIN_SIZE)
        # 表盘为正方形：允许宽度变化时保持等比（页面用固定方尺寸放置），
        # 具体边长由页面卡片布局决定，控件内部按 min(w, h) 自适应

    # ══════════════════════════════
    #  对外 API
    # ══════════════════════════════

    def set_time(self, hour: int, minute: int, second: int) -> None:
        """设置表盘时间（本地 24 小时制的时/分/秒）。

        数值会被规整到合法范围（如 hour=25 → 1），避免调用方
        边界疏漏导致表盘画错；数值未变化时不触发重绘。
        """
        hour = int(hour) % 24
        minute = int(minute) % 60
        second = int(second) % 60
        if (hour, minute, second) == (
            self._cyber_hour, self._cyber_minute, self._cyber_second
        ):
            return
        self._cyber_hour = hour
        self._cyber_minute = minute
        self._cyber_second = second
        self.update()

    # ══════════════════════════════
    #  绘制
    # ══════════════════════════════

    def paintEvent(self, event) -> None:
        """Mixin 红线：QPainter → 自绘 → super() 的顺序不可调换。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_clock(painter)
        super().paintEvent(event)

    def _draw_clock(self, painter: QPainter) -> None:
        """按当前 _cyber_* 时间绘制完整表盘。"""
        side = min(self.width(), self.height())
        if side < 8:
            return  # 尺寸异常（极端压缩）时跳过，避免除零/负半径
        center = QPointF(self.width() / 2, self.height() / 2)
        # 外圈留白：边距取边长的 8%，指针不超过外圈
        radius = side / 2 - side * 0.08

        ring_color = self.token_color("alias.accent.primary")
        tick_color = self.token_color("alias.text.tertiary")
        hand_color = self.token_color("alias.text.primary")
        second_color = self.token_color("alias.accent.secondary")

        self._draw_face_ring(painter, center, radius, ring_color)
        self._draw_ticks(painter, center, radius, tick_color)
        self._draw_hands(
            painter, center, radius, hand_color, second_color
        )

    def _draw_face_ring(
        self, painter: QPainter, center: QPointF, radius: float, color: QColor
    ) -> None:
        """外圈圆环：细线 + 12/3/6/9 方位的小刻度块（赛博刻度感）。"""
        pen = QPen(color)
        # 线宽随半径缩放（大表盘不显得发丝细）
        pen.setWidthF(max(1.0, radius * 0.045))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius * 0.92, radius * 0.92)

    def _draw_ticks(
        self, painter: QPainter, center: QPointF, radius: float, color: QColor
    ) -> None:
        """60 根刻度：整点加粗加长，其余为分钟细刻度。"""
        pen = QPen(color)
        painter.setPen(pen)
        for i in range(60):
            angle = math.radians(i * 6)  # 每分钟 6°
            is_major = (i % 5)  # 0/5/10... 为整点刻度
            # 细刻度：长 6%；整点刻度：长 14% 且线宽翻倍
            tick_len = radius * (0.14 if not is_major else 0.06)
            pen.setWidthF(
                max(1.0, radius * (0.05 if not is_major else 0.025))
            )
            # 整点刻度更亮（alpha 拉满），细刻度半透明
            tick_color = QColor(color)
            tick_color.setAlphaF(1.0 if not is_major else 0.55)
            pen.setColor(tick_color)
            painter.setPen(pen)
            outer = QPointF(
                center.x() + radius * 0.92 * math.sin(angle),
                center.y() - radius * 0.92 * math.cos(angle),
            )
            inner = QPointF(
                center.x() + (radius * 0.92 - tick_len) * math.sin(angle),
                center.y() - (radius * 0.92 - tick_len) * math.cos(angle),
            )
            painter.drawLine(inner, outer)

    def _draw_hands(
        self,
        painter: QPainter,
        center: QPointF,
        radius: float,
        hand_color: QColor,
        second_color: QColor,
    ) -> None:
        """时针/分针/秒针（秒针带配重尾巴），中心点为实心圆。"""
        # ── 角度换算：时针含分钟平滑，分针含秒平滑 ──
        hour_angle = math.radians(
            (self._cyber_hour % 12 + self._cyber_minute / 60) * 30
        )
        minute_angle = math.radians(
            (self._cyber_minute + self._cyber_second / 60) * 6
        )
        second_angle = math.radians(self._cyber_second * 6)

        # ── 时针（粗短）──
        pen = QPen(hand_color)
        pen.setWidthF(max(2.0, radius * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(
            center,
            QPointF(
                center.x() + radius * 0.5 * math.sin(hour_angle),
                center.y() - radius * 0.5 * math.cos(hour_angle),
            ),
        )

        # ── 分针（细长）──
        pen.setWidthF(max(1.5, radius * 0.055))
        painter.setPen(pen)
        painter.drawLine(
            center,
            QPointF(
                center.x() + radius * 0.72 * math.sin(minute_angle),
                center.y() - radius * 0.72 * math.cos(minute_angle),
            ),
        )

        # ── 秒针（强调色 + 配重尾巴）──
        pen = QPen(second_color)
        pen.setWidthF(max(1.0, radius * 0.025))
        painter.setPen(pen)
        tip = QPointF(
            center.x() + radius * 0.8 * math.sin(second_angle),
            center.y() - radius * 0.8 * math.cos(second_angle),
        )
        tail = QPointF(
            center.x() - radius * 0.18 * math.sin(second_angle),
            center.y() + radius * 0.18 * math.cos(second_angle),
        )
        painter.drawLine(tail, tip)

        # ── 中心轴点（覆盖指针根部）──
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(second_color))
        painter.drawEllipse(center, radius * 0.07, radius * 0.07)
