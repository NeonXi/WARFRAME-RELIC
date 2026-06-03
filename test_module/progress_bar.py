"""
Custom Progress Bar with enhanced animation effects
"""

from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QLinearGradient


class LoadingSpinner(QWidget):
    """Rotating loading spinner widget"""
    
    def __init__(self):
        super().__init__()
        self._angle = 0
        self.setFixedSize(24, 24)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_angle)
        self._timer.start(20)  # 50 FPS
    
    def _update_angle(self):
        self._angle = (self._angle + 8) % 360
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() // 2, self.height() // 2)
        painter.rotate(self._angle)
        
        radius = 8
        for i in range(8):
            angle = i * 45
            x = radius * (1.5 ** 0.5) if i % 4 in (1, 2) else 0
            y = radius * (1 if i < 4 else -1) if i % 2 == 0 else 0
            
            alpha = int(255 * (1 - i / 8))
            painter.setBrush(QColor(0, 217, 255, alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)


class QProgressBar(QWidget):
    """Progress bar with smooth animation and loading spinner"""
    
    def __init__(self):
        super().__init__()
        self._value = 0
        self._max = 100
        self._anim_offset = 0
        self._pulse_offset = 0
        self.setMinimumHeight(36)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._spinner = LoadingSpinner()
        self._spinner.hide()
        layout.addWidget(self._spinner)
        
        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #00d9ff; font-size: 14px;")
        layout.addWidget(self._status_label)
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)
    
    def setRange(self, min_val, max_val):
        self._max = max_val
        if max_val == 0:
            self._anim_offset = 0
            self._pulse_offset = 0
            self._timer.start(20)
            self._spinner.show()
        else:
            self._timer.stop()
            self._spinner.hide()
    
    def setStatusText(self, text):
        self._status_label.setText(text)
    
    def setValue(self, value):
        self._value = min(max(value, 0), self._max)
        self.update()
    
    def _update_animation(self):
        self._anim_offset = (self._anim_offset + 2) % 100
        self._pulse_offset = (self._pulse_offset + 1) % 100
        self.update()
    
    def showEvent(self, event):
        super().showEvent(event)
        if self._max == 0:
            self._anim_offset = 0
            self._timer.start(20)
    
    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background bar
        bar_rect = self.rect()
        bar_rect.setHeight(4)
        bar_rect.moveTop(self.height() - 10)
        
        painter.setBrush(QColor('#0f3460'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_rect, 2, 2)
        
        if self._max == 0:
            # Indeterminate: animated sliding bar
            w = int(self.width() * 0.3)
            total = self.width() + w
            x = int((self._anim_offset / 100) * total) - w
            
            alpha = 128 + int(127 * abs(self._pulse_offset - 50) / 50)
            
            gradient = QLinearGradient(x, 0, x + w, 0)
            gradient.setColorAt(0, QColor(0, 217, 255, alpha))
            gradient.setColorAt(0.3, QColor(0, 255, 136))
            gradient.setColorAt(0.7, QColor(0, 255, 136))
            gradient.setColorAt(1, QColor(0, 217, 255, alpha))
            
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, bar_rect.top(), w, 4, 2, 2)
            
            # Glow trail
            glow_w = w // 2
            glow_x = x + w
            glow_gradient = QLinearGradient(glow_x, 0, glow_x + glow_w, 0)
            glow_gradient.setColorAt(0, QColor(0, 217, 255, 100))
            glow_gradient.setColorAt(1, QColor(0, 217, 255, 0))
            painter.setBrush(glow_gradient)
            painter.drawRoundedRect(glow_x, bar_rect.top(), glow_w, 4, 2, 2)
        else:
            # Determinate: filled bar
            w = int(self.width() * (self._value / self._max))
            gradient = QLinearGradient(0, 0, w, 0)
            gradient.setColorAt(0, QColor('#00d9ff'))
            gradient.setColorAt(1, QColor('#00ff88'))
            
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bar_rect.left(), bar_rect.top(), w, 4, 2, 2)