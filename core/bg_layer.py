"""
WARFRAME-RELIC 背景图层管理 Mixin

通过 QGridLayout 同格子叠加四层：
  - BgImagePlaceholder（底）：背景图 + QGraphicsBlurEffect 模糊
  - OpacityOverlay（中）：纯色遮罩，WA_TransparentForMouseEvents
  - ContentLayer（顶）：透明 UI 层

作为 Mixin 注入 ManagementPanel，所有方法通过 self 访问控件。
"""

import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsBlurEffect
from core.constants import theme
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget


class BgImageWidget(QWidget):
    """自绘制背景图控件，用 paintEvent 绘制 QPixmap，绕过 QSS 的 background-size 限制。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._offset_x: int = 0
        self._offset_y: int = 0

    def set_pixmap(self, pixmap: QPixmap, offset_x: int = 0, offset_y: int = 0):
        """设置要绘制的 pixmap 及居中偏移量。"""
        self._pixmap = pixmap
        self._offset_x = offset_x
        self._offset_y = offset_y
        self.update()

    def clear_pixmap(self):
        """清除背景图。"""
        self._pixmap = None
        self.update()

    def paintEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self._offset_x, self._offset_y, self._pixmap)
        else:
            super().paintEvent(event)


class BgLayerMixin:
    """背景图层管理：模糊、透明度、背景图尺寸。"""

    # ── 以下属性由 ManagementPanel.__init__ / _setup_ui 创建 ──
    # _bg_image_placeholder: QWidget
    # _bg_blur_effect: QGraphicsBlurEffect
    # _opacity_overlay: QWidget

    # ============================================================
    # 窗口事件
    # ============================================================

    def resizeEvent(self, event):
        """窗口大小变化时动态更新背景图尺寸（带 Debounce）"""
        super().resizeEvent(event)
        self._schedule_background_update()

    # ============================================================
    # 背景图尺寸（Debounce）
    # ============================================================

    def _schedule_background_update(self):
        """延迟更新背景图尺寸（Debounce: 100ms）"""
        if not hasattr(self, '_bg_update_timer'):
            from PyQt6.QtCore import QTimer
            self._bg_update_timer = QTimer()
            self._bg_update_timer.setSingleShot(True)
            self._bg_update_timer.timeout.connect(self._update_background_size_debounced)

        self._bg_update_timer.stop()
        self._bg_update_timer.start(100)

    def _update_background_size_debounced(self):
        """Debounce 后的背景图尺寸更新（带阈值过滤）"""
        if not theme.background_enabled or not theme.background_image_path:
            return
        if hasattr(self, '_last_bg_width') and hasattr(self, '_last_bg_height'):
            if abs(self.width() - self._last_bg_width) < 50 and abs(self.height() - self._last_bg_height) < 50:
                return
        self._update_bg_pixmap()
        self._last_bg_width = self.width()
        self._last_bg_height = self.height()

    # ============================================================
    # 背景图样式
    # ============================================================

    
    def _update_bg_pixmap(self):
        """用 QPixmap 缩放 + self._bg_image_placeholder.paintEvent 来显示背景图。

        完全绕过 QSS background-size（Qt 不支持），通过 QPixmap.scaled()
        和 paintEvent 中的 QPainter.drawPixmap 实现 cover + 居中效果。
        """
        if not theme.background_enabled or not theme.background_image_path:
            self._bg_image_placeholder.clear_pixmap()
            return

        pixmap = QPixmap(theme.background_image_path)
        if pixmap.isNull():
            return

        img_w = pixmap.width()
        img_h = pixmap.height()
        win_w = self.width()
        win_h = self.height()

        if img_w > 0 and img_h > 0 and win_w > 0 and win_h > 0:
            # cover 模式：取较大缩放比，保证至少一个方向填满窗口
            scale = max(win_w / img_w, win_h / img_h)
            scale = min(scale, 1.5)  # 最大放大 1.5 倍

            # 模糊时放大 10% 消除白边
            blur_radius = getattr(theme, 'background_blur', 0)
            if blur_radius > 0:
                scale *= 1.10

            target_w = int(img_w * scale)
            target_h = int(img_h * scale)
        else:
            target_w = win_w
            target_h = win_h

        # 缩放
        scaled = pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # 居中偏移
        offset_x = (win_w - target_w) // 2
        offset_y = (win_h - target_h) // 2

        self._bg_image_placeholder.set_pixmap(scaled, offset_x, offset_y)

    

    def _update_background_size_immediate(self):
        """立即更新背景图尺寸（不带 debounce，用于主题变更时）"""
        self._update_bg_pixmap()

    # ============================================================
    # 不透明度遮罩
    # ============================================================

    def _apply_opacity_overlay(self):
        """极轻量刷新：只更新遮罩层 alpha，一行 QSS 零开销。

        遮罩颜色跟随主题 panel_darkest，白天模式用浅色，暗色模式用深色。
        """
        # 解析当前主题的 panel_darkest 颜色
        base_color = theme.panel_darkest if hasattr(theme, 'panel_darkest') else "#040412"
        if isinstance(base_color, str) and base_color.startswith('#'):
            r = int(base_color[1:3], 16)
            g = int(base_color[3:5], 16)
            b = int(base_color[5:7], 16)
        else:
            r, g, b = 4, 4, 18

        alpha = int(theme.background_opacity * 200)
        self._opacity_overlay.setStyleSheet(
            f"background-color: rgba({r}, {g}, {b}, {alpha});"
        )

    # ============================================================
    # 模糊效果
    # ============================================================

    def _apply_blur_effect(self):
        """刷新模糊效果：设置模糊半径 + 同步更新图片尺寸（消除白边）。"""
        self._bg_blur_effect.setBlurRadius(theme.background_blur)
        # 模糊值变化时需要重新计算图片放大比例
        if theme.background_enabled and theme.background_image_path:
            self._update_bg_pixmap()
