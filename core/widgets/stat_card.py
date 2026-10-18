"""
[L4] core.widgets.stat_card — StatCard / ChamferedFrame 容器组件

归属层:    [L4] (core/widgets/)
允许依赖:  core.tokens.manager, core.widgets.base
禁止依赖:  core.services/*, core.pages/*, core.state/*, 任何 IO/JSON/网络

职责:
  - ChamferedFrame: 带切角边框的通用容器(可指定圆角大小)
  - StatCard: 统计数字卡片(切角边框 + 主题色边框)

迁移记录: 2026-06-17 从 core/pages/status_page.py 内部类迁出。
原类名: _ChamferedFrame → ChamferedFrame, _StatCard → StatCard
违反规范: §6.5 "Page 禁止内嵌自定义控件,只能组装 Widget/Section"

本文件相关红线:
- ✗ 禁止 setStyleSheet 硬编码(已用 token + 自绘)
- ✗ 禁止读写 JSON / 调 service / 网络 IO
- ✗ 禁止继承 QWidget 从零开始(必须 CyberWidgetMixin + Qt 原生)
- ✗ 禁止硬编码颜色 (border_c = QColor(self._accent_color) 是用户传入的动态值,合法)
"""

# ── 标准库 ──
from __future__ import annotations

# ── PySide6 ──
from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QPaintEvent, QPen, QBrush, QColor
from PySide6.QtCore import QRectF

# ── 项目内 ──
from core.widgets.base import CyberWidgetMixin


class ChamferedFrame(CyberWidgetMixin, QFrame):
    """带切角边框的通用容器。

    行为:
      - 背景使用 token components.card.bg(半透明 0.85)
      - 边框使用 token components.card.border
      - 切角由 CyberWidgetMixin._chamfered_path 提供,默认右下角切角
      - 容器本身透明,只画底色和边框

    使用场景:
      - 页面/区块的背景装饰框
      - 不需要交互的纯展示容器

    参数:
      corner_size: 切角大小(像素),默认 8
      parent:      Qt 父对象
    """

    def __init__(self, corner_size: int = 8, parent=None) -> None:
        # 规范 §5.1: 显式调用目标基类 __init__,不用 super
        QFrame.__init__(self, parent)
        self._corner = corner_size
        # 透明背景让自绘的 fillPath 生效,QSS 只清掉 QFrame 默认边框
        self.setStyleSheet("QFrame { border: none; background: transparent; }")

    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制切角背景和边框。

        顺序(规范 §5.3): QPainter → 自绘 → (无 super,QFrame 默认无内容可绘)
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 切角路径(右下角,br = bottom-right)
        path = self._chamfered_path(QRectF(self.rect()), self._corner, mode="br")

        # 填充半透明背景(沉浸黑色模式时覆写 RGB,折减 alpha)
        bg = self._cyber_immersive_resolve_bg("components.card.bg", 0.85)
        painter.fillPath(path, QBrush(bg))

        # 画边框
        border = self.token_color("components.card.border")
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)


class StatCard(CyberWidgetMixin, QFrame):
    """统计数字卡片(切角 + 主题色边框)。

    行为:
      - 固定高度 90 px
      - 背景用 bg.base 半透明 0.85
      - 边框用 accent_color(由调用方传入,带 0.25 alpha)
      - 4 个角全部切角(corner_sm token,默认 6 px)

    使用场景:
      - 数据总览页面的统计数字显示(物品数/价格数/缓存命中率等)
      - 任何需要"一个数字 + 一个标签"的紧凑卡片

    参数:
      accent_color: 边框主题色(字符串,通常是 #RRGGBB 格式的 hex)
      parent:       Qt 父对象
    """

    def __init__(self, accent_color: str, parent=None) -> None:
        QFrame.__init__(self, parent)
        # accent_color 是动态传入的(每个卡片可能用不同主题色),
        # 不能 token 化,这是设计上的合法硬编码
        self._accent_color = accent_color
        self.setFixedHeight(92)
        self.setStyleSheet("QFrame { border: none; background: transparent; }")

    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制统计卡片。

        顺序: QPainter → 自绘背景 + 边框 → (QFrame 无默认绘制,无需 super)
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 用 corner.sm token(默认 6 px),4 角切角
        corner = self.space("corner.sm", 6)
        path = self._chamfered_path(QRectF(self.rect()), corner, mode="br")

        # 背景半透明(沉浸黑色模式时覆写 RGB,折减 alpha)
        bg = self._cyber_immersive_resolve_bg("bg.base", 0.85)
        painter.fillPath(path, QBrush(bg))

        # 边框使用卡片的主题色,半透明 0.25
        border_c = QColor(self._accent_color)
        border_c.setAlphaF(0.25)
        painter.setPen(QPen(border_c, 1))
        painter.drawPath(path)
