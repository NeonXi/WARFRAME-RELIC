"""
WARFRAME-RELIC 内联样式刷新 Mixin

负责所有 QGroupBox / QPushButton / 导航栏等内联样式的刷新。
作为 Mixin 注入 ManagementPanel，所有方法通过 self 访问控件。
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGroupBox
from core.constants import theme
from core.stylesheet import build_stylesheet


class PanelStylesMixin:
    """内联样式刷新：导航高亮、GroupBox 边框、按钮样式等。"""

    # ── 以下属性由 ManagementPanel.__init__ / _setup_ui 创建 ──
    # _nav_list, _nav_items, _nav_groups, _last_highlighted_group
    # _left_scroll, _left_widget
    # 各 _*_group (QGroupBox)
    # _hotkey_buttons, _hotkey_tip
    # _feature_toggle_buttons, _toggle_hint_label
    # _about_link_buttons
    # _reset_hint_label, _btn_reset_state, _btn_reload_hotkeys
    # _lang_preset_group, _lang_preset_label, _preset_combo, _preset_desc
    # _items_search_input, _items_result_list, _items_search_hint
    
    # _log_title_lbl
    # _bottom_tip

    # ============================================================
    # 导航高亮
    # ============================================================

    def _highlight_group_border(self, group: QGroupBox):
        """高亮 group 边框（荧光绿加粗效果）。"""
        group.setStyleSheet(f"""
            QGroupBox {{
                background-color: transparent;
                border: 3px solid {theme.cyber_green};
                border-radius: 6px;
                padding: 10px;
                margin-top: 8px;
                font-size: 12px;
                color: {theme.cyber_green};
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }}
        """)

    def _restore_group_border(self, group: QGroupBox):
        """恢复 group 默认边框样式。"""
        if group is getattr(self, '_reset_group', None):
            group.setStyleSheet(f"""
                QGroupBox {{
                    background-color: transparent;
                    border: 2px solid {theme.cyber_orange};
                    border-radius: 6px;
                    padding: 10px;
                    margin-top: 8px;
                    font-size: 12px;
                    color: {theme.cyber_orange};
                    font-weight: bold;
                }}
            """)
        else:
            group.setStyleSheet(f"""
                QGroupBox {{
                    background-color: transparent;
                    border: 1px solid {theme.border};
                    border-radius: 4px;
                    padding: 10px;
                    margin-top: 8px;
                    font-size: 12px;
                    color: {theme.text};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 6px;
                }}
            """)

    def _reapply_nav_highlight(self):
        """主题/预设切换后重新应用当前导航项的高亮边框。"""
        if hasattr(self, '_nav_list') and hasattr(self, '_nav_items'):
            current_row = self._nav_list.currentRow()
            if 0 <= current_row < len(self._nav_items):
                nav_id = self._nav_items[current_row][0]
                group = self._nav_groups.get(nav_id)
                if group:
                    self._last_highlighted_group = None
                    self._highlight_group_border(group)
                    self._last_highlighted_group = group

    # ============================================================
    # 导航栏样式
    # ============================================================

    def _refresh_nav_list_style(self, t=None):
        """刷新导航栏 QListWidget 样式。"""
        if t is None:
            t = theme
        if not hasattr(self, '_nav_list'):
            return
        self._nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                border-right: 1px solid {t.border};
                padding: 8px 4px;
                outline: none;
            }}
            QListWidget::item {{
                color: {t.text_dim};
                padding: 10px 12px;
                border-radius: 6px;
                margin: 2px 4px;
                font-size: 13px;
                background-color: {t.get_panel_bg_color(180)};
            }}
            QListWidget::item:hover {{
                background-color: {t.get_panel_bg_color(180)};
                color: {t.text};
            }}
            QListWidget::item:selected {{
                background-color: {t.cyber_yellow};
                color: #000;
                font-weight: bold;
            }}
        """)

    # ============================================================
    # 功能开关按钮
    # ============================================================

    def _refresh_toggle_button_styles(self):
        """根据开关状态刷新按钮样式：亮=开，暗=关。"""
        if not hasattr(self, '_feature_toggle_buttons'):
            return
        for key, btn in self._feature_toggle_buttons.items():
            is_on = btn.isChecked()
            if is_on:
                btn.setStyleSheet(f"""
                    QPushButton#toggleFeatureBtn {{
                        background-color: {theme.get_panel_bg_color(200)};
                        color: {theme.cyber_cyan};
                        border: 2px solid {theme.cyber_yellow};
                        border-radius: 6px;
                        padding: 12px 10px;
                        font-size: 12px;
                        font-weight: bold;
                        text-align: center;
                        min-height: 64px;
                    }}
                    QPushButton#toggleFeatureBtn:hover {{
                        background-color: {theme.get_panel_bg_color(220)};
                        border-color: {theme.cyber_yellow};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton#toggleFeatureBtn {{
                        background-color: transparent;
                        color: {theme.text_dim};
                        border: 2px solid {theme.border};
                        border-radius: 6px;
                        padding: 12px 10px;
                        font-size: 12px;
                        text-align: center;
                        min-height: 64px;
                    }}
                    QPushButton#toggleFeatureBtn:hover {{
                        border-color: {theme.cyber_cyan};
                        color: {theme.text};
                    }}
                """)

    # ============================================================
    # 热键按钮样式
    # ============================================================

    def _hotkey_btn_style(self) -> str:
        """快捷键按钮通用样式。"""
        return f"""
            HotkeyCaptureButton {{
                background-color: transparent;
                color: {theme.cyber_cyan};
                border: 1px solid {theme.border};
                border-radius: 3px;
                padding: 4px 8px;
                font-family: "Consolas", "Microsoft YaHei";
                font-size: 12px;
                font-weight: bold;
            }}
            HotkeyCaptureButton:hover {{
                border-color: {theme.cyber_yellow};
                color: {theme.cyber_yellow};
            }}
            HotkeyCaptureButton:focus {{
                border-color: {theme.cyber_yellow};
                background-color: transparent;
            }}
        """

    def _refresh_hotkey_btn_styles(self, t=None):
        """刷新所有热键按钮样式。"""
        if t is None:
            t = theme
        for btn in self._hotkey_buttons.values():
            btn.setStyleSheet(self._hotkey_btn_style())
        if hasattr(self, '_hotkey_tip'):
            self._hotkey_tip.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")

    # ============================================================
    # 关于作者区
    # ============================================================

    def _refresh_about_inline_styles(self):
        """刷新关于作者区内部组件的内联样式。"""
        t = theme
        if hasattr(self, '_about_version_label'):
            self._about_version_label.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")
        if hasattr(self, '_about_link_buttons'):
            link_styles = {
                "bilibili_home": (t.brand_bilibili, t.brand_bilibili_hover),
                "github_repo": (t.brand_github, t.brand_github_hover),
            }
            for btn, s_key in self._about_link_buttons:
                color, hover = link_styles.get(s_key, (t.text, t.cyber_yellow))
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent; color: {color};
                        border: none; padding: 4px 0; font-size: 12px; text-align: left;
                    }}
                    QPushButton:hover {{ color: {hover}; }}
                """)

    def _refresh_reset_button_styles(self, t=None):
        """刷新紧急恢复区按钮样式。"""
        if t is None:
            t = theme
        if hasattr(self, '_btn_reset_state'):
            self._btn_reset_state.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.cyber_red};
                    color: white;
                    border: 2px solid {t.cyber_orange};
                    border-radius: 6px;
                    padding: 8px 20px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #cc3333;
                    border-color: {t.cyber_yellow};
                }}
                QPushButton:pressed {{
                    background-color: #aa2222;
                }}
            """)
        if hasattr(self, '_btn_reload_hotkeys'):
            self._btn_reload_hotkeys.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {t.cyber_orange};
                    border: 1px solid {t.cyber_orange};
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {t.card_bg};
                    border-color: {t.cyber_yellow};
                    color: {t.cyber_yellow};
                }}
            """)
        if hasattr(self, '_reset_hint_label'):
            self._reset_hint_label.setStyleSheet(
                f"color: {t.text_dim}; font-size: 11px; border: none; background: transparent;")

    # ============================================================
    # 杂项组件
    # ============================================================

    def _refresh_misc_styles(self, t=None):
        """刷新滚动区、搜索框、下拉框等杂项样式。"""
        if t is None:
            t = theme

        # 滚动区域 & 主面板
        if hasattr(self, '_left_scroll'):
            self._left_scroll.setStyleSheet(
                "QScrollArea { border: none; background-color: transparent; }")
            self._left_widget.setStyleSheet("background-color: transparent;")

        # 底部提示
        if hasattr(self, '_bottom_tip'):
            self._bottom_tip.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")

        # 日志标题
        if hasattr(self, '_log_title_lbl'):
            self._log_title_lbl.setStyleSheet(f"color: {t.cyber_yellow}; font-size: 14px; font-weight: bold;")

        # 功能开关提示
        if hasattr(self, '_toggle_hint_label'):
            self._toggle_hint_label.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")

        # 物品搜索组件
        if hasattr(self, '_items_search_input'):
            self._items_search_input.setStyleSheet(f"""
                QLineEdit {{
                    background-color: transparent;
                    color: {t.cyber_cyan};
                    border: 1px solid {t.border};
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-family: "Consolas", "Microsoft YaHei";
                    font-size: 13px;
                }}
                QLineEdit:focus {{ border-color: {t.cyber_yellow}; }}
            """)
        if hasattr(self, '_items_result_list'):
            self._items_result_list.setStyleSheet(f"""
                QTextEdit {{
                    background-color: transparent;
                    color: {t.text};
                    border: 1px solid {t.border};
                    border-radius: 4px;
                    font-family: "Consolas", "Microsoft YaHei", monospace;
                    font-size: 12px;
                    padding: 6px;
                }}
                QScrollBar:vertical {{
                    background: {t.panel_bg}; width: 8px; border-radius: 4px;
                }}
                QScrollBar::handle:vertical {{
                    background: {t.border}; border-radius: 4px; min-height: 20px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            """)
        if hasattr(self, '_items_search_hint'):
            self._items_search_hint.setStyleSheet(f"color: {t.text_dim}; font-size: 10px;")

        # 语言预设组
        if hasattr(self, '_lang_preset_label'):
            self._lang_preset_label.setStyleSheet(
                f"color: {t.text_dim}; font-size: 12px; border: none; background: transparent;")
        if hasattr(self, '_preset_combo'):
            self._preset_combo.setStyleSheet(f"""
                QComboBox {{
                    background-color: {t.card_bg};
                    color: {t.cyber_cyan};
                    border: 1px solid {t.border};
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 12px;
                    min-width: 160px;
                }}
                QComboBox:hover {{ border-color: {t.cyber_yellow}; }}
                QComboBox::drop-down {{
                    border: none;
                    width: 20px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: transparent;
                    color: {t.text};
                    border: 1px solid {t.border};
                    selection-background-color: {t.cyber_yellow};
                    selection-color: #000;
                }}
            """)
        if hasattr(self, '_preset_desc'):
            self._preset_desc.setStyleSheet(
                f"color: {t.text_dim}; font-size: 10px; border: none; background: transparent; padding: 2px 0;")

    # ============================================================
    # 完整刷新入口
    # ============================================================

    def _refresh_inline_styles(self):
        """刷新所有颜色相关的内联样式。"""
        t = theme

        self._refresh_nav_list_style(t)
        self._refresh_misc_styles(t)
        self._refresh_hotkey_btn_styles(t)
        self._refresh_toggle_button_styles()
        self._refresh_about_inline_styles()
        self._refresh_reset_button_styles(t)

        # 子面板样式
        self._theme_panel.refresh_inline_styles()
        self._update_panel.refresh_inline_styles()

        # 重新应用当前导航高亮
        self._reapply_nav_highlight()

    def _refresh_all_inline_styles(self):
        """完整刷新（含数据重新查询）。"""
        self._refresh_inline_styles()
        self._update_panel.refresh_stats()
        self._refresh_hotkey_ui()

    # ============================================================
    # 主题变更后的样式重建
    # ============================================================

    def _rebuild_styles_and_swatches_full(self):
        """完整刷新：全局样式表、内联样式和色块（批量操作，阻断中间重绘）。"""
        self.setUpdatesEnabled(False)
        try:
            self.setStyleSheet(build_stylesheet())
            self._refresh_inline_styles()
            self._theme_panel.rebuild_swatches()
            self._apply_opacity_overlay()
            self._bg_blur_effect.setBlurRadius(theme.background_blur)
        finally:
            self.setUpdatesEnabled(True)

    def _rebuild_styles_and_swatches_partial(self):
        """部分刷新：只更新样式表和内联样式，不重建色块（批量操作，阻断中间重绘）。"""
        self.setUpdatesEnabled(False)
        try:
            self.setStyleSheet(build_stylesheet())
            self._refresh_inline_styles()
            self._apply_opacity_overlay()
            self._bg_blur_effect.setBlurRadius(theme.background_blur)
        finally:
            self.setUpdatesEnabled(True)

    def _rebuild_styles_and_swatches(self):
        """刷新全局样式表、内联样式和色块（旧接口，转发到完整刷新）。"""
        self._rebuild_styles_and_swatches_full()
