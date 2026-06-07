"""启动动画 — 纯 Qt 实现，先淡出内容，再淡出遮罩。"""
from data.ui_strings import S
from core.theme_proxy import CYBER_ORANGE, CYBER_CYAN, COLOR_GOLD
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtProperty,
)
from PyQt6.QtGui import QPainter, QColor, QLinearGradient


class PulsingDot(QWidget):
    """三个脉动小圆点，模拟加载中动画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 16)
        self._phase = 0.0  # 0.0 ~ 1.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(40)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._phase = (self._phase + 0.025) % 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = [QColor(str(CYBER_ORANGE)), QColor(str(CYBER_CYAN)), QColor(str(COLOR_GOLD))]
        for i in range(3):
            phi = (self._phase + i * 0.33) % 1.0
            scale = 0.4 + 0.6 * (1.0 - abs(phi * 2.0 - 1.0))
            alpha = int(100 + 155 * (1.0 - abs(phi * 2.0 - 1.0)))
            c = QColor(colors[i])
            c.setAlpha(alpha)
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            r = int(4 * scale)
            x = 10 + i * 20
            y = 8
            p.drawEllipse(QPoint(x, y), r, r)
        p.end()


class SplashScreen(QWidget):
    """启动遮罩 + 动画，覆盖在管理面板之上。

    两段式淡出：先淡出文字内容，再淡出遮罩背景。
    """

    CONTENT_DURATION_MS = 2500  # 内容显示时长
    CONTENT_FADE_MS = 400       # 内容淡出时长
    OVERLAY_FADE_MS = 600       # 遮罩淡出时长

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._overlay_opacity = 1.0

        # 全屏覆盖父控件
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)

        # 内容容器（独立控制透明度）
        self._content = QWidget(self)
        self._content.setGeometry(self.rect())
        self._content.setStyleSheet("background: transparent;")
        self._content_effect = QGraphicsOpacityEffect(self._content)
        self._content_effect.setOpacity(1.0)
        self._content.setGraphicsEffect(self._content_effect)

        layout = QVBoxLayout(self._content)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # 标题
        self._title = QLabel("WARFRAME-RELIC")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(
            f"color: {COLOR_GOLD}; font-size: 28px; font-weight: bold;"
            "background: transparent; border: none;"
        )
        layout.addWidget(self._title)

        # 副标题
        self._subtitle = QLabel(S("splash", "starting"))
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet(
            f"color: {CYBER_CYAN}; font-size: 13px;"
            "background: transparent; border: none;"
        )
        layout.addWidget(self._subtitle)

        # 脉动圆点
        self._dots = PulsingDot(self._content)
        layout.addWidget(self._dots, alignment=Qt.AlignmentFlag.AlignCenter)

        # 阶段1：内容淡出
        QTimer.singleShot(self.CONTENT_DURATION_MS, self._start_content_fade)

    # ---- 遮罩透明度属性（供 QPropertyAnimation 驱动）----

    def _get_overlay_opacity(self) -> float:
        return self._overlay_opacity

    def _set_overlay_opacity(self, value: float):
        self._overlay_opacity = value
        self.update()

    overlay_opacity = pyqtProperty(float, _get_overlay_opacity, _set_overlay_opacity)

    # ---- 事件 ----

    def eventFilter(self, obj, event):
        """跟随父控件尺寸变化。"""
        if obj is self.parent() and event.type() == event.Type.Resize:
            self.setGeometry(self.parent().rect())
            self._content.setGeometry(self.rect())
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self._dots.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(10, 10, 18, int(230 * self._overlay_opacity)))
        grad.setColorAt(0.5, QColor(15, 15, 28, int(235 * self._overlay_opacity)))
        grad.setColorAt(1.0, QColor(10, 10, 18, int(230 * self._overlay_opacity)))
        p.fillRect(self.rect(), grad)
        p.end()

    # ---- 两段式淡出 ----

    def _start_content_fade(self):
        """阶段1：淡出文字内容。"""
        self._dots.stop()
        self._content_anim = QPropertyAnimation(self._content_effect, b"opacity")
        self._content_anim.setDuration(self.CONTENT_FADE_MS)
        self._content_anim.setStartValue(1.0)
        self._content_anim.setEndValue(0.0)
        self._content_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._content_anim.finished.connect(self._start_overlay_fade)
        self._content_anim.start()

    def _start_overlay_fade(self):
        """阶段2：淡出遮罩背景。"""
        self._overlay_anim = QPropertyAnimation(self, b"overlay_opacity")
        self._overlay_anim.setDuration(self.OVERLAY_FADE_MS)
        self._overlay_anim.setStartValue(1.0)
        self._overlay_anim.setEndValue(0.0)
        self._overlay_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._overlay_anim.finished.connect(self.close)
        self._overlay_anim.start()