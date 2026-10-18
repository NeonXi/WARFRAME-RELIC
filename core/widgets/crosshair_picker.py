"""
[L4] core.widgets.crosshair_picker — CrosshairPicker 全屏十字线选点覆盖层

归属层:    [L4] (core/widgets/)
允许依赖:  PySide6
禁止依赖:  core.services/*, core.pages/*, 任何 IO/JSON/网络

职责:
  - 提供全屏选点交互(覆盖所有屏幕)
  - 半透明遮罩 + 红色虚线十字准星
  - 跟随鼠标位置实时更新
  - 左键点击发射 position_picked(x, y) 信号

迁移记录: 2026-06-17 从 core/pages/triggers_page.py 内部类 _CrosshairPicker 迁出
违反规范: §6.5 "Page 禁止内嵌自定义控件,只能组装 Widget/Section"

本文件相关红线:
- ✗ 禁止 setStyleSheet(f-string) → 全自绘
- ✗ 禁止读写 JSON / 调 service / 任何 IO
- ✗ 禁止硬编码颜色 → 红/白/黑是功能性需求(选点反馈),不通过 token
  但说明: 这里红色虚线是 UX 约定(选点器的视觉语言),
        不可被主题化(否则用户找不到准星)。
        这种"功能色"硬编码在 widgets 是允许的。
"""

# ── 标准库 ──
from __future__ import annotations

# ── PySide6 ──
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont,
    QGuiApplication, QCursor,
)
from core.fonts import FONT_FALLBACK


class CrosshairPicker(QWidget):
    """全屏十字线取点覆盖层(覆盖所有屏幕)。

    使用流程:
      1. 实例化一次(长期持有)
      2. 监听 position_picked(int, int) 信号获取坐标
      3. 需要选点时调 show_overlay()

    视觉:
      - 半透明黑遮罩(60 alpha)覆盖所有屏幕
      - 红色虚线十字线(粗 1 px)
      - 中心红色实心小十字(粗 2 px,长 16 px)
      - 跟随鼠标的坐标文字框(白字 + 黑底 180 alpha)

    行为细节:
      - 16ms 刷新(约 60 FPS)跟随鼠标
      - 隐藏鼠标光标(BlankCursor),只显示自定义十字
      - 窗口无边框 + 始终置顶 + 不抢焦点
      - 左键点击即捕获全局屏幕坐标(QCursor.pos())
    """

    # ── 信号 ──
    # 参数: 全局屏幕坐标 x, y(QCursor.pos() 返回的全局坐标)
    position_picked = Signal(int, int)

    # ── 视觉常量 ──
    # 这些是 UX 约定色(选点器的视觉语言),不做主题化
    _CROSSHAIR_COLOR = QColor(220, 30, 30)    # 红色十字
    _COORD_TEXT_COLOR = QColor(255, 255, 255)  # 白色坐标文字
    _COORD_BG_COLOR = QColor(0, 0, 0, 180)    # 半透明黑底
    _OVERLAY_BG_COLOR = QColor(0, 0, 0, 60)   # 半透明黑遮罩
    _CROSSHAIR_RADIUS = 16                    # 中心十字臂长
    _REFRESH_MS = 16                          # 刷新间隔(60 FPS)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # ── 鼠标位置定时器 ──
        self._track_timer = QTimer(self)
        self._track_timer.timeout.connect(self._update_mouse_pos)
        self._mouse_pos = None  # type: ignore[var-annotated]

        # ── 计算所有屏幕总区域(用于跨屏选点) ──
        screens = QGuiApplication.screens()
        total_rect = screens[0].geometry() if screens else self.geometry()
        for s in screens[1:]:
            total_rect = total_rect.united(s.geometry())
        self._total_rect = total_rect

        # ── 窗口属性 ──
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.CursorShape.BlankCursor)

    # ── 公开 API ──

    def show_overlay(self) -> None:
        """显示覆盖层(覆盖所有屏幕,开始捕获)。

        调用后:
          - 窗口铺满所有屏幕
          - 启动鼠标跟踪定时器
          - 隐藏系统光标
        """
        self.setGeometry(self._total_rect)
        self._mouse_pos = None
        self._track_timer.start(self._REFRESH_MS)
        self.show()

    # ── 内部 ──

    def _update_mouse_pos(self) -> None:
        """定时器回调:更新鼠标全局坐标并重绘。"""
        self._mouse_pos = QCursor.pos()
        self.update()

    # ── 事件 ──

    def mousePressEvent(self, event) -> None:
        """左键点击:发射坐标信号并关闭覆盖层。"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = QCursor.pos()
            self.position_picked.emit(pos.x(), pos.y())
            self._track_timer.stop()
            self.hide()

    # ── 绘制 ──

    def paintEvent(self, event) -> None:
        """绘制全屏遮罩 + 十字线 + 坐标文字。

        顺序(规范 §5.3): QPainter → 自绘全部 → (QWidget 默认无内容,无需 super)

        坐标系: 画布左上角 = (0, 0)
        鼠标位置 _mouse_pos 是 QCursor.pos() 全局坐标,
        需要减去 _total_rect.topLeft() 转换为画布局部坐标。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pw = self.width()
        ph = self.height()

        # ── 1. 半透明遮罩覆盖整个跨屏区域 ──
        painter.fillRect(0, 0, pw, ph, self._OVERLAY_BG_COLOR)

        if not self._mouse_pos:
            return  # 没有鼠标位置时只画遮罩

        # ── 2. 转换为画布局部坐标 ──
        px = self._mouse_pos.x() - self._total_rect.x()
        py = self._mouse_pos.y() - self._total_rect.y()

        # ── 3. 红色虚线十字线(从屏幕一边到另一边) ──
        pen_dash = QPen(self._CROSSHAIR_COLOR, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_dash)
        painter.drawLine(0, py, pw, py)
        painter.drawLine(px, 0, px, ph)

        # ── 4. 中心红色实心小十字 ──
        pen_solid = QPen(self._CROSSHAIR_COLOR, 2)
        painter.setPen(pen_solid)
        painter.drawLine(px - self._CROSSHAIR_RADIUS, py, px + self._CROSSHAIR_RADIUS, py)
        painter.drawLine(px, py - self._CROSSHAIR_RADIUS, px, py + self._CROSSHAIR_RADIUS)

        # ── 5. 坐标文字框(自动避边) ──
        painter.setPen(self._COORD_TEXT_COLOR)
        painter.setFont(QFont(FONT_FALLBACK, 11))
        coord_text = f"X: {self._mouse_pos.x()}  Y: {self._mouse_pos.y()}"
        fm = painter.fontMetrics()
        tw = fm.boundingRect(coord_text).width() + 16
        th = fm.height() + 8
        # 默认放在十字右下角,超界则反向
        tx = px + 20
        ty = py + 20
        if tx + tw > pw:
            tx = px - tw - 20
        if ty + th > ph:
            ty = py - th - 20
        # 背景 + 文字
        painter.fillRect(tx, ty, tw, th, self._COORD_BG_COLOR)
        painter.drawText(tx + 8, ty + fm.ascent() + 4, coord_text)
