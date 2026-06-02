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
        self._set_bg_image_style()
        self._last_bg_width = self.width()
        self._last_bg_height = self.height()

    # ============================================================
    # 背景图样式
    # ============================================================

    def _set_bg_image_style(self):
        """设置背景图占位层的 QSS"""
        if not theme.background_enabled or not theme.background_image_path:
            return
        bg_size = theme.calculate_background_size(self.width(), self.height())
        escaped_path = os.path.normpath(theme.background_image_path).replace('\\', '/')
        self._bg_image_placeholder.setStyleSheet(f"""
            QWidget#BgImagePlaceholder {{
                background-image: url("{escaped_path}");
                background-repeat: no-repeat;
                background-position: center center;
                background-size: {bg_size};
            }}
        """)

    def _update_background_size_immediate(self):
        """立即更新背景图尺寸（不带 debounce，用于主题变更时）"""
        self._set_bg_image_style()

    # ============================================================
    # 不透明度遮罩
    # ============================================================

    def _apply_opacity_overlay(self):
        """极轻量刷新：只更新遮罩层 alpha，一行 QSS 零开销。"""
        alpha = int(theme.background_opacity * 200)
        self._opacity_overlay.setStyleSheet(
            f"background-color: rgba(8, 8, 26, {alpha});"
        )

    # ============================================================
    # 模糊效果
    # ============================================================

    def _apply_blur_effect(self):
        """极轻量刷新：只更新背景图层的模糊半径，零 QSS 重解析。"""
        self._bg_blur_effect.setBlurRadius(theme.background_blur)
