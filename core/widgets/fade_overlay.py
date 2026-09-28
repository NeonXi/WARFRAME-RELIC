"""
[L4] FadeOverlay — 全屏截图渐隐遮罩

继承: QWidget(纯遮罩,无 Qt 原生控件可复用)
依赖: PySide6
职责: 主题切换交叉溶解的遮罩层 —— 覆盖整个窗口显示旧主题截图,
      通过 opacity 属性(QPropertyAnimation 驱动)渐隐,露出底下的新主题。

  为什么不用 QLabel + QGraphicsOpacityEffect:
  QGraphicsOpacityEffect 每帧把控件子树渲染到离屏缓冲再混合,
  对全窗口截图是双重渲染开销;本类在 paintEvent 里直接
  painter.setOpacity() 一次绘制,开销最小。

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  PySide6
禁止依赖:  core.services/*, core.pages/*, core.tokens/*
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPixmap, QPaintEvent
from PySide6.QtCore import Qt, Property


class FadeOverlay(QWidget):
    """旧界面截图的渐隐遮罩。

    ``opacity`` 是 Qt Property,可直接被 QPropertyAnimation(b"opacity")
    驱动;动画只改透明度并触发 update(),无额外离屏缓冲。
    """

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._opacity = 1.0
        # 动画期间点击/悬停穿透到底下已切换好的新界面
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    # ── Qt Property(动画目标) ──

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        self.update()

    opacity = Property(float, _get_opacity, _set_opacity)

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self._pixmap)
