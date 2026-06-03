"""
WARFRAME-RELIC 背景图层管理 Mixin

通过 QGridLayout 同格子叠加四层：
  - BgImagePlaceholder（底）：背景图 + QGraphicsBlurEffect 模糊
  - OpacityOverlay（中）：纯色遮罩，WA_TransparentForMouseEvents
  - ContentLayer（顶）：透明 UI 层

作为 Mixin 注入 ManagementPanel，所有方法通过 self 访问控件。
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsBlurEffect
from core.constants import theme
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget


class BgImageWidget(QWidget):
    """自绘制背景图控件，paintEvent 内实时缩放，拖动窗口零开销。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig_pixmap: QPixmap | None = None
        self._blur_scale: float = 1.0

    def set_orig_pixmap(self, pixmap: QPixmap, blur_scale: float = 1.0):
        """设置原始图片，paintEvent 绘制时自动 cover 缩放。"""
        self._orig_pixmap = pixmap
        self._blur_scale = blur_scale
        self.update()

    def clear_pixmap(self):
        self._orig_pixmap = None
        self.update()

    def paintEvent(self, event):
        if self._orig_pixmap and not self._orig_pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            img_w = self._orig_pixmap.width()
            img_h = self._orig_pixmap.height()
            win_w = self.width()
            win_h = self.height()

            if img_w > 0 and img_h > 0 and win_w > 0 and win_h > 0:
                scale = max(win_w / img_w, win_h / img_h) * self._blur_scale
                scale = min(scale, 1.5 * self._blur_scale)
                target_w = int(img_w * scale)
                target_h = int(img_h * scale)
                offset_x = (win_w - target_w) // 2
                offset_y = (win_h - target_h) // 2

                painter.drawPixmap(
                    offset_x, offset_y, target_w, target_h,
                    self._orig_pixmap,
                )
        else:
            super().paintEvent(event)


class BgLayerMixin:
    """背景图层管理：模糊、透明度、背景图尺寸。

    paintEvent 内实时缩放背景图，拖动窗口时无需重建 QPixmap，流畅无卡顿。
    """

    # ── 以下属性由 ManagementPanel.__init__ / _setup_ui 创建 ──
    # _bg_image_placeholder: BgImageWidget
    # _bg_blur_effect: QGraphicsBlurEffect
    # _opacity_overlay: QWidget

    # ============================================================
    # 背景图加载（仅加载原图，缩放由 BgImageWidget.paintEvent 处理）
    # ============================================================

    def _update_bg_pixmap(self):
        """加载背景图原图，缩放由 paintEvent 实时处理，拖动窗口零开销。"""
        if not theme.background_enabled or not theme.background_image_path:
            self._bg_image_placeholder.clear_pixmap()
            return

        pixmap = QPixmap(theme.background_image_path)
        if pixmap.isNull():
            return

        blur_radius = getattr(theme, 'background_blur', 0)
        blur_scale = 1.10 if blur_radius > 0 else 1.0

        self._bg_image_placeholder.set_orig_pixmap(pixmap, blur_scale)

    def _update_background_size_immediate(self):
        """立即重新加载背景图（主题/路径变更时）。"""
        self._update_bg_pixmap()

    # ============================================================
    # 不透明度遮罩
    # ============================================================

    def _apply_opacity_overlay(self):
        """极轻量刷新：只更新遮罩层 alpha，一行 QSS 零开销。

        遮罩颜色跟随主题 panel_bg，白天模式用浅色，暗色模式用深色。
        """
        # 解析当前主题的 panel_bg 颜色
        base_color = theme.panel_bg if hasattr(theme, 'panel_bg') else "#040412"
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
