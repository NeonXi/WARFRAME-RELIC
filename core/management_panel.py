"""
WARFRAME-RELIC 管理面板
- 主窗口，启动即显示，关闭面板 = 退出程序
- 功能：数据库状态、更新、快捷键配置、主题换肤
- 通过 Mixin 模式拆分：bg_layer / panel_styles / panel_builder
- 内部委托给 theme_panel.py / update_panel.py 处理子功能
"""
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QApplication, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from core.constants import theme
from core.hotkey_config import (
    load_hotkeys, save_hotkeys,
    DEFAULT_HOTKEYS, HOTKEY_LABELS,
    load_feature_toggles, save_feature_toggles,
)
from core.bg_layer import BgLayerMixin
from core.panel_styles import PanelStylesMixin
from core.panel_builder import PanelBuilderMixin
from data.ui_strings import S


# ============================================================
# 管理面板窗口（通过 Mixin 组合）
# ============================================================

class ManagementPanel(BgLayerMixin, PanelStylesMixin, PanelBuilderMixin, QWidget):
    """WARFRAME-RELIC 管理面板。

    通过多重继承组合以下 Mixin：
      - BgLayerMixin: 背景图层管理（模糊/透明度/尺寸）
      - PanelStylesMixin: 内联样式刷新
      - PanelBuilderMixin: UI 构建方法（_setup_ui + _build_*）
    """

    db_updated = pyqtSignal(str)
    hotkeys_changed = pyqtSignal(dict)
    theme_changed = pyqtSignal()
    reset_requested = pyqtSignal()
    feature_toggles_changed = pyqtSignal(dict)
    item_region_select_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._data_dir = Path(__file__).resolve().parent.parent / 'data'
        self._db_path = str(self._data_dir / 'relics.db')
        self._alljson_path = str(self._data_dir / 'all.json')
        self._hotkeys = load_hotkeys()
        self._feature_toggles = load_feature_toggles()
        self._first_show = True

        # 子面板
        self._theme_panel = None
        self._update_panel = None

        # 性能优化：延迟初始化 RelicDB 缓存（用于悬停 tooltip）
        self._relic_db_cache = None

        self._setup_ui()
        self._update_panel.refresh_stats()
        self._update_panel.refresh_translation_stats()
        self.refresh_items_i18n_stats()
        self.refresh_price_stats()
        self._refresh_hotkey_ui()

    # ============================================================
    # closeEvent / showEvent
    # ============================================================

    def closeEvent(self, event):
        """关闭面板 = 退出程序，清理所有运行缓存。"""
        theme.save_background_config_now()
        QApplication.instance().quit()
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self._update_panel.enable_auto_show()
            QTimer.singleShot(50, self._fix_initial_size)

    def _fix_initial_size(self):
        self.updateGeometry()
        self.layout().activate()
        self.setMinimumHeight(780)
        self._adjust_window_width()
        hint = self.layout().sizeHint()
        if hint.height() > self.height():
            self.resize(self.width(), hint.height())
        screen = QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            self.move(screen_geom.left(), screen_geom.top())
        self._set_bg_image_style()

    # ============================================================
    # 窗口宽度调整
    # ============================================================

    @property
    def _theme_panel_width(self):
        if self._theme_panel:
            return self._theme_panel.widget.width() if self._theme_panel.is_expanded else 0
        return 0

    def _adjust_window_width(self):
        """根据当前内容自动调整窗口宽度。"""
        nav_w = 140
        content_margins = 40
        content_needed_w = 420
        if self._left_widget and self._left_widget.layout():
            for i in range(self._left_widget.layout().count()):
                item = self._left_widget.layout().itemAt(i)
                if item and item.widget():
                    hint = item.widget().sizeHint()
                    content_needed_w = max(content_needed_w, hint.width())
            margins = self._left_widget.layout().contentsMargins()
            content_needed_w += margins.left() + margins.right()
        else:
            content_needed_w += content_margins

        theme_w = self._theme_panel_width
        log_w = 420 if self._update_panel.log_panel_visible else 0
        needed_w = nav_w + content_needed_w + theme_w + log_w
        min_w = self.minimumWidth()
        new_w = max(needed_w, min_w)

        if new_w > self.width():
            self.resize(new_w, self.height())

    # ============================================================
    # 主题面板交互
    # ============================================================

    def _toggle_theme_panel(self):
        self._theme_panel.toggle()

    def _on_theme_changed_internal(self, change_type="full"):
        """主题变更后刷新 UI。"""
        if change_type == "opacity":
            self._apply_opacity_overlay()
            return
        elif change_type == "blur":
            self._apply_blur_effect()
            return
        elif change_type == "color":
            self._rebuild_styles_and_swatches_partial()
        else:
            self._rebuild_styles_and_swatches_full()

        self.theme_changed.emit()

    # ============================================================
    # 日志（转发给 update_panel）
    # ============================================================

    def _add_log(self, log_type: str, msg: str, source: str = ""):
        self._update_panel.add_log(log_type, msg, source)

    def add_log(self, log_type: str, msg: str, source: str = ""):
        self._update_panel.add_log(log_type, msg, source)

    # ============================================================
    # 热键
    # ============================================================

    def _refresh_hotkey_ui(self):
        for key, btn in self._hotkey_buttons.items():
            btn.set_hotkey(self._hotkeys.get(key, ""))

    def _on_save_hotkeys(self):
        new_hotkeys = {}
        for key, btn in self._hotkey_buttons.items():
            val = btn.hotkey().strip().lower()
            new_hotkeys[key] = val
            if not val:
                self.add_log("warn", f"「{HOTKEY_LABELS.get(key, key)}」未设置快捷键，请点击按钮录制。", "hotkeys")
                return
        if save_hotkeys(new_hotkeys):
            self._hotkeys = new_hotkeys
            self._refresh_hotkey_ui()
            self.hotkeys_changed.emit(self._hotkeys)
            self.add_log("ok", "快捷键已保存并生效", "hotkeys")
        else:
            self.add_log("error", "快捷键保存失败，请检查文件权限", "hotkeys")

    def _on_reset_hotkeys(self):
        reply = QMessageBox.question(
            self, S("hotkey", "reset_confirm_title"),
            S.format("hotkey", "reset_confirm_msg",
                select=DEFAULT_HOTKEYS['select'],
                fullscreen=DEFAULT_HOTKEYS['fullscreen']),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._hotkeys = dict(DEFAULT_HOTKEYS)
        self._refresh_hotkey_ui()
        self.hotkeys_changed.emit(self._hotkeys)

        if save_hotkeys({}):
            self.add_log("ok", S("hotkey", "reset_done_msg"), "_on_reset_hotkeys")
            QMessageBox.information(self, S("hotkey", "reset_done_title"),
                S("hotkey", "reset_done_msg"))
        else:
            self.add_log("warn", "快捷键配置已恢复默认，但保存到文件失败", "_on_reset_hotkeys")
            QMessageBox.information(self, S("hotkey", "reset_done_title"),
                S("hotkey", "reset_done_msg") + "\n(配置已恢复，但文件保存失败)")

    def _on_reset_state(self):
        self.add_log("info", S("log_msg", "reset_start"), "_on_reset_state")
        self.reset_requested.emit()

    def _on_reload_hotkeys(self):
        self.hotkeys_changed.emit(self._hotkeys)
        self.add_log("ok", S("log_msg", "hotkeys_reloaded"), "_on_reload_hotkeys")

    # ============================================================
    # 链接
    # ============================================================

    def _open_bilibili(self):
        import webbrowser
        webbrowser.open("https://space.bilibili.com/21001459")

    def _open_github(self):
        import webbrowser
        webbrowser.open("https://github.com/NeonXi/WARFRAME-RELIC")

    def _open_data_dir(self):
        os.startfile(str(self._data_dir))

    # ============================================================
    # 退出
    # ============================================================

    def _on_exit(self):
        reply = QMessageBox.question(
            self, S("exit", "confirm_title"),
            S("exit", "confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.instance().quit()
