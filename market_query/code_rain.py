"""
Code Rain Overlay - Matrix-style falling characters effect
"""

import random
import math
import os
import sys

from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QFont

# 确保能找到 core 模块
_src_root = os.path.dirname(os.path.dirname(__file__))
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from core.theme_config import theme

# 字符集：数字 + 英文字母
_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_CHARS_LEN = len(_CHARS)


class Drop:
    """单列雨滴"""
    __slots__ = ('x', 'y', 'speed', 'length', 'chars', 'brightness',
                 'font_size', 'wobble_phase', 'wobble_amp')

    def __init__(self, x: int, max_y: int, col_idx: int):
        self.x = x
        # 从顶部上方开始，错开初始位置避免太整齐
        self.y = random.uniform(-max_y * 0.8, -10)
        self.speed = random.uniform(3, 12)
        self.length = random.randint(5, 22)
        self.chars = [random.choice(_CHARS) for _ in range(self.length)]
        self.brightness = random.uniform(0.4, 1.0)
        # 每列字体大小略有差异
        self.font_size = random.randint(16, 22)
        # 水平摆动
        self.wobble_phase = random.uniform(0, 6.28)
        self.wobble_amp = 0  # 无抖动

    def update(self, max_y: int, frame: int):
        self.y += self.speed
        # 每帧随机换一个字符，让雨滴更"活"
        idx = random.randint(0, self.length - 1)
        self.chars[idx] = random.choice(_CHARS)
        if self.y - self.length > max_y:
            self.y = random.uniform(-max_y * 0.3, -10)
            self.speed = random.uniform(3, 12)
            self.length = random.randint(5, 22)
            self.chars = [random.choice(_CHARS) for _ in range(self.length)]
            self.brightness = random.uniform(0.4, 1.0)
            self.font_size = random.randint(16, 22)
            self.wobble_amp = 0  # 无抖动

    def head_char(self) -> str:
        return self.chars[-1]


class CodeRainOverlay(QWidget):
    """代码雨覆盖层，性能优先的批量绘制"""

    _FPS = 35

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drops: list[Drop] = []
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)
        self._font = QFont("Consolas", 18)
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setBold(True)
        self._col_width = 22
        self._running = False
        self._fading = False
        self.hide()

    def start_rain(self):
        """开始代码雨"""
        if self._running:
            return
        self._fading = False
        self._running = True
        self._frame = 0
        self._init_drops()
        self._timer.start(1000 // self._FPS)
        self.show()
        self.raise_()

    def start_fade_out(self, duration_ms: int = 600):
        """开始淡出，完成后自动隐藏"""
        if self._fading or not self._running:
            return
        self._fading = True
        self._running = False
        self._timer.stop()

        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(effect.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(self._on_fade_finished)
        anim.start()

    def _on_fade_finished(self):
        self.setGraphicsEffect(None)
        self.hide()
        self._fading = False

    def _init_drops(self):
        """初始化雨滴列，部分列为空增加自然感"""
        self._drops.clear()
        self.resize(self.parent().width(), self.parent().height())
        n_cols = max(24, self.width() // self._col_width)
        for i in range(n_cols):
            # 随机跳过部分列，让雨滴有疏密变化
            if random.random() < 0.25:
                continue
            self._drops.append(Drop(i * self._col_width, self.height(), i))

    def _update_frame(self):
        """更新并重绘一帧"""
        self._frame += 1
        h = self.height()
        for drop in self._drops:
            drop.update(h, self._frame)
        self.update()

    def paintEvent(self, event):
        if not self._drops:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        base_color = QColor(theme.cyber_cyan)
        # 几乎透明的遮罩，仅微微压暗背景
        bg_color = QColor(0, 0, 0, 25)
        painter.fillRect(self.rect(), bg_color)

        for drop in self._drops:
            painter.setFont(self._font)
            font = painter.font()
            font.setPixelSize(drop.font_size)
            painter.setFont(font)

            for i, ch in enumerate(drop.chars):
                cy = int(drop.y - i * drop.font_size * 1.15)
                if cy < -20 or cy > self.height() + 20:
                    continue
                # 头部最亮（纯白），尾部渐暗到主题色
                ratio = i / drop.length
                if ratio < 0.15:
                    # 头部：偏白
                    c = QColor(200, 255, 255, 220)
                else:
                    alpha = int(40 + 180 * (1.0 - ratio) * drop.brightness)
                    c = QColor(base_color)
                    c.setAlpha(alpha)

                # 水平摆动
                wobble = drop.wobble_amp * 1.5 * (1.0 - ratio) if i < drop.length - 1 else 0
                dx = int(wobble * math.sin(drop.wobble_phase + self._frame * 0.08 + i * 0.3))

                painter.setPen(c)
                painter.drawText(drop.x + dx, cy, ch)

        painter.end()

    def resizeEvent(self, event):
        """窗口大小变化时重建雨滴"""
        if self._running:
            self._init_drops()
        super().resizeEvent(event)