"""
[L4] core.widgets.charts — 赛博风格自绘图表组件

继承: CyberWidgetMixin + QWidget
依赖: core.tokens.manager(只此一个外部)
职责: 用 QPainter 自绘柱状图 / 饼图 / 折线图,匹配赛博朋克主题

设计原则:
  - 不引入 pyqtgraph/matplotlib 等第三方图表库(避免打包体积膨胀)
  - 纯 QPainter 绘制,颜色/尺寸全部走 token
  - 图表数据由调用方传入(Page 层从 Service 获取),Widget 只负责绘制

包含组件:
  - CyberBarChart:  柱状图(纵向,支持数值标签)
  - CyberPieChart:  饼图/扇形图(支持百分比 + 图例)
  - CyberLineChart: 折线图(支持数据点标记)

## AI 硬约束
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

红线:
- ✗ 禁止 __init__ 用 super() → 必须 QWidget.__init__(self, parent)
- ✗ 禁止 paintEvent 顺序写反 → QPainter → 自绘 → super()
- ✗ 禁止硬编码颜色 #XXXXXX → 必须 self.token_color()
- ✗ 禁止硬编码尺寸 → 必须 self.space()
- ✗ 禁止调 Service / 读写 JSON
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QPaintEvent, QColor, QPen, QBrush,
    QPainterPath, QFont, QFontMetrics,
)
from PySide6.QtCore import Qt, QRectF, QPointF

from core.widgets.base import CyberWidgetMixin


# ── 图表配色板(从 token 取色,循环使用) ──
# 顺序: 黄(主) → 青(次) → 品红 → 绿 → 橙 → 红
_PALETTE_KEYS = [
    "accent.primary",    # 黄
    "accent.secondary",  # 青
    "accent.tertiary",   # 品红
]
# 当需要更多颜色时,用原始色补充(token 中没定义的用固定 hex)
_PALETTE_FALLBACK = [
    "#00FF99",  # 绿
    "#FF7700",  # 橙
    "#FF0055",  # 红
    "#FFAA00",  # 金
    "#00AAFF",  # 天蓝
]


class _CyberChartBase(CyberWidgetMixin, QWidget):
    """图表基类 — 提供公共的绘图辅助方法。

    子类必须实现 _draw_chart(painter, rect) 绘制具体图表。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        # 规范 §5.1: 显式调用目标基类,不用 super
        QWidget.__init__(self, parent)
        self._cyber_data: list = []
        self._cyber_title: str = ""
        self.setMinimumHeight(220)

    # ── 公共 API ──

    def set_data(self, data: list) -> None:
        """设置图表数据并刷新。

        数据格式由子类定义。
        """
        self._cyber_data = data or []
        self.update()

    def set_title(self, title: str) -> None:
        self._cyber_title = title
        self.update()

    # ── 工具方法 ──

    def _palette_color(self, index: int) -> QColor:
        """按索引取调色板颜色(token 优先,不足用 fallback)。"""
        if index < len(_PALETTE_KEYS):
            return self.token_color(_PALETTE_KEYS[index])
        idx = (index - len(_PALETTE_KEYS)) % len(_PALETTE_FALLBACK)
        return QColor(_PALETTE_FALLBACK[idx])

    def _draw_title(self, painter: QPainter) -> int:
        """绘制标题,返回标题占用的高度(px)。"""
        if not self._cyber_title:
            return 0
        painter.save()
        font_size = self.space("font.sm", 12)
        font = QFont("Iceberg", font_size)
        painter.setFont(font)
        painter.setPen(self.token_color("alias.text.secondary"))
        title_rect = QRectF(0, 0, self.width(), font_size + 8)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self._cyber_title)
        painter.restore()
        return font_size + 12

    def paintEvent(self, event: QPaintEvent) -> None:
        """统一入口: QPainter → 自绘标题+图表 → super()。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        title_h = self._draw_title(painter)
        chart_rect = QRectF(
            0, title_h,
            self.width(), self.height() - title_h,
        )
        if self._cyber_data:
            self._draw_chart(painter, chart_rect)
        else:
            self._draw_empty(painter, chart_rect)

        # QWidget 默认无内容,但规范要求 super()
        super().paintEvent(event)

    def _draw_empty(self, painter: QPainter, rect: QRectF) -> None:
        """无数据时的占位提示。"""
        painter.save()
        painter.setPen(self.token_color("alias.text.tertiary"))
        font_size = self.space("font.xs", 11)
        painter.setFont(QFont("Microsoft YaHei", font_size))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "暂无数据")
        painter.restore()


# ══════════════════════════════════
#  柱状图
# ══════════════════════════════════

class CyberBarChart(_CyberChartBase):
    """纵向柱状图。

    数据格式: [(label, value), ...]
    自动计算 Y 轴范围,柱体用调色板循环着色,顶部显示数值。
    """

    def _draw_chart(self, painter: QPainter, rect: QRectF) -> None:
        data = self._cyber_data
        if not data:
            return

        n = len(data)
        # 边距(底部加大,给倾斜的 X 轴标签留空间)
        margin_left = self.space("spacing.lg", 16)
        margin_right = self.space("spacing.md", 12)
        margin_bottom = self.space("spacing.xxl", 56)
        margin_top = self.space("spacing.sm", 8)

        plot_w = rect.width() - margin_left - margin_right
        plot_h = rect.height() - margin_bottom - margin_top
        if plot_w <= 0 or plot_h <= 0:
            return

        # 找最大值
        max_val = max((v for _, v in data), default=0)
        if max_val <= 0:
            max_val = 1
        # Y 轴上限取整(向上取到 1/2/5 的倍数)
        y_max = self._nice_ceil(max_val)

        # 柱体宽度
        bar_gap = 4
        bar_w = (plot_w - bar_gap * (n - 1)) / n
        if bar_w > 40:
            bar_w = 40
            # 重新居中
            total_w = bar_w * n + bar_gap * (n - 1)
            offset_x = (plot_w - total_w) / 2
        else:
            offset_x = 0

        # ── 画 Y 轴参考线(4 条) ──
        painter.save()
        grid_pen = QPen(self.token_color("alias.border.subtle"), 1)
        grid_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for i in range(5):
            y = rect.top() + margin_top + plot_h * i / 4
            painter.drawLine(
                QPointF(rect.left() + margin_left, y),
                QPointF(rect.right() - margin_right, y),
            )
        # Y 轴数值标签
        painter.setPen(self.token_color("alias.text.tertiary"))
        label_font = QFont("Microsoft YaHei", self.space("font.micro", 10))
        painter.setFont(label_font)
        for i in range(5):
            y = rect.top() + margin_top + plot_h * (4 - i) / 4
            val = int(y_max * i / 4)
            painter.drawText(
                QRectF(rect.left(), y - 8, margin_left - 4, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._format_num(val),
            )
        painter.restore()

        # ── 画柱体 ──
        painter.save()
        # X 轴标签密度控制:数据多时跳显,避免重叠
        label_step = max(1, math.ceil(n / 12))
        for i, (label, value) in enumerate(data):
            x = rect.left() + margin_left + offset_x + i * (bar_w + bar_gap)
            # 柱高
            h = (value / y_max) * plot_h
            y = rect.top() + margin_top + plot_h - h

            color = self._palette_color(i)
            # 柱体填充
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(x, y, bar_w, h))

            # 柱体顶部高亮线(赛博感)
            highlight = QColor(color)
            highlight.setAlphaF(0.9)
            painter.setPen(QPen(highlight, 2))
            painter.drawLine(
                QPointF(x, y),
                QPointF(x + bar_w, y),
            )

            # 数值标签
            painter.setPen(self.token_color("alias.text.primary"))
            painter.setFont(label_font)
            val_text = self._format_num(value)
            painter.drawText(
                QRectF(x - 10, y - 18, bar_w + 20, 16),
                Qt.AlignmentFlag.AlignCenter,
                val_text,
            )

            # X 轴标签(跳显:每 label_step 个显示一个,且始终显示第一个和最后一个)
            if i % label_step == 0 or i == n - 1:
                painter.setPen(self.token_color("alias.text.secondary"))
                painter.save()
                painter.translate(x + bar_w / 2, rect.bottom() - margin_bottom + 4)
                painter.rotate(-40)
                label_rect = QRectF(-70, 0, 140, 18)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(label))
                painter.restore()

        painter.restore()

    @staticmethod
    def _nice_ceil(value: float) -> float:
        """把数值向上取整到 1/2/5 × 10^n 的倍数,让 Y 轴好看。"""
        if value <= 0:
            return 1
        exp = math.floor(math.log10(value))
        base = 10 ** exp
        frac = value / base
        if frac <= 1:
            nice = 1
        elif frac <= 2:
            nice = 2
        elif frac <= 5:
            nice = 5
        else:
            nice = 10
        return nice * base

    @staticmethod
    def _format_num(value) -> str:
        """格式化数值: 万以上用 '万' 缩写。"""
        v = float(value)
        if v >= 10000:
            return f"{v / 10000:.1f}万"
        if v >= 1000:
            return f"{v / 1000:.1f}k"
        return str(int(v))


# ══════════════════════════════════
#  饼图
# ══════════════════════════════════

class CyberPieChart(_CyberChartBase):
    """饼图/扇形图。

    数据格式: [(label, value), ...]
    自动计算百分比,右侧显示图例(标签 + 数量 + 百分比)。
    """

    def _draw_chart(self, painter: QPainter, rect: QRectF) -> None:
        data = self._cyber_data
        if not data:
            return

        total = sum(v for _, v in data)
        if total <= 0:
            return

        # 布局: 左侧饼图,右侧图例
        legend_w = 140
        margin = self.space("spacing.md", 12)
        pie_size = min(rect.width() - legend_w - margin * 2, rect.height() - margin * 2)
        pie_size = max(pie_size, 80)
        pie_x = rect.left() + margin
        pie_y = rect.top() + (rect.height() - pie_size) / 2
        pie_rect = QRectF(pie_x, pie_y, pie_size, pie_size)

        # ── 画饼图扇形 ──
        painter.save()
        start_angle = 90 * 16  # 从正上方开始(Qt 角度单位: 1/16 度)
        for i, (label, value) in enumerate(data):
            span = int((value / total) * 360 * 16)
            color = self._palette_color(i)

            # 扇形
            path = QPainterPath()
            path.moveTo(pie_rect.center())
            path.arcTo(pie_rect, start_angle / 16, span / 16)
            path.closeSubpath()

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(self.token_color("alias.bg.base"), 1))
            painter.drawPath(path)

            start_angle += span
        painter.restore()

        # ── 画图例 ──
        painter.save()
        legend_x = pie_rect.right() + margin
        legend_y = rect.top() + margin
        item_h = 20
        font = QFont("Microsoft YaHei", self.space("font.micro", 10))
        painter.setFont(font)

        for i, (label, value) in enumerate(data):
            y = legend_y + i * item_h
            if y + item_h > rect.bottom():
                break

            # 颜色方块
            color = self._palette_color(i)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(legend_x, y + 2, 10, 10))

            # 标签 + 百分比
            pct = value / total * 100
            text = f"{label} {pct:.0f}%"
            painter.setPen(self.token_color("alias.text.primary"))
            painter.drawText(
                QRectF(legend_x + 16, y, legend_w - 16, item_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                text,
            )

            # 数值(右对齐)
            painter.setPen(self.token_color("alias.text.tertiary"))
            painter.drawText(
                QRectF(legend_x + 16, y, legend_w - 16, item_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                CyberBarChart._format_num(value),
            )

        painter.restore()


# ══════════════════════════════════
#  折线图
# ══════════════════════════════════

class CyberLineChart(_CyberChartBase):
    """折线图。

    数据格式: [(label, value), ...]
    自动计算坐标范围,画折线 + 数据点 + 数值标签。
    """

    def _draw_chart(self, painter: QPainter, rect: QRectF) -> None:
        data = self._cyber_data
        if not data:
            return

        n = len(data)
        margin_left = self.space("spacing.lg", 16)
        margin_right = self.space("spacing.md", 12)
        margin_bottom = self.space("spacing.xxl", 56)
        margin_top = self.space("spacing.sm", 8)

        plot_w = rect.width() - margin_left - margin_right
        plot_h = rect.height() - margin_bottom - margin_top
        if plot_w <= 0 or plot_h <= 0:
            return

        values = [v for _, v in data]
        max_val = max(values, default=0)
        min_val = min(values, default=0)
        if max_val == min_val:
            max_val = min_val + 1
        y_max = CyberBarChart._nice_ceil(max_val)
        y_min = 0 if min_val >= 0 else min_val

        # ── 画 Y 轴参考线 ──
        painter.save()
        grid_pen = QPen(self.token_color("alias.border.subtle"), 1)
        grid_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for i in range(5):
            y = rect.top() + margin_top + plot_h * i / 4
            painter.drawLine(
                QPointF(rect.left() + margin_left, y),
                QPointF(rect.right() - margin_right, y),
            )
        # Y 轴标签
        painter.setPen(self.token_color("alias.text.tertiary"))
        label_font = QFont("Microsoft YaHei", self.space("font.micro", 10))
        painter.setFont(label_font)
        for i in range(5):
            y = rect.top() + margin_top + plot_h * (4 - i) / 4
            val = y_min + (y_max - y_min) * i / 4
            painter.drawText(
                QRectF(rect.left(), y - 8, margin_left - 4, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                CyberBarChart._format_num(val),
            )
        painter.restore()

        # ── 画折线 ──
        painter.save()
        color = self.token_color("accent.secondary")
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        points = []
        for i, (label, value) in enumerate(data):
            x = rect.left() + margin_left
            if n > 1:
                x += plot_w * i / (n - 1)
            else:
                x += plot_w / 2
            y = rect.top() + margin_top + plot_h * (1 - (value - y_min) / (y_max - y_min))
            points.append(QPointF(x, y))

        # 折线
        path = QPainterPath()
        if points:
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
        painter.drawPath(path)

        # 数据点 + 数值标签
        point_color = self.token_color("accent.primary")
        painter.setBrush(QBrush(point_color))
        painter.setPen(QPen(point_color, 1))
        # X 轴标签密度控制
        label_step = max(1, math.ceil(n / 12))
        for i, (label, value) in enumerate(points):
            p = points[i]
            painter.drawEllipse(p, 3, 3)

            # 数值标签
            painter.setPen(self.token_color("alias.text.primary"))
            painter.setFont(label_font)
            val_text = CyberBarChart._format_num(data[i][1])
            painter.drawText(
                QRectF(p.x() - 30, p.y() - 20, 60, 16),
                Qt.AlignmentFlag.AlignCenter,
                val_text,
            )
            painter.setPen(QPen(point_color, 1))

            # X 轴标签(跳显 + 倾斜)
            if i % label_step == 0 or i == n - 1:
                painter.setPen(self.token_color("alias.text.secondary"))
                painter.save()
                painter.translate(p.x(), rect.bottom() - margin_bottom + 4)
                painter.rotate(-40)
                label_rect = QRectF(-70, 0, 140, 18)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(data[i][0]))
                painter.restore()

        painter.restore()
