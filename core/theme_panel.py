"""
WARFRAME-RELIC 主题配色侧滑面板
- 色块编辑、预设切换、动画
- 作为 ManagementPanel 的子面板存在
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QColorDialog, QMessageBox,
    QComboBox,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor

from core.constants import theme, ThemeConfig
from core.theme_fields import THEME_FIELDS
from data.ui_strings import S





# ============================================================
# 主题侧滑面板
# ============================================================

class ThemePanel:
    """管理 ManagementPanel 中的主题配色侧滑面板。

    不继承 QWidget，而是管理一个嵌入到 ManagementPanel 布局中的 QWidget。
    通过回调与 ManagementPanel 通信。
    """

    PANEL_WIDTH = 320

    def __init__(self, parent_widget, on_theme_changed, add_log):
        """
        Args:
            parent_widget: ManagementPanel 实例
            on_theme_changed: 主题变更回调 (无参数)
            add_log: 日志回调 (log_type, msg)
        """
        self._parent = parent_widget
        self._on_theme_changed = on_theme_changed
        self._add_log = add_log

        self._theme_swatches = {}   # json_key → swatch QLabel
        self._theme_draft = {}      # 未保存的颜色修改
        self._expanded = False
        self._anim = None

        # 构建面板
        self._panel = QWidget()
        self._panel.setFixedWidth(0)
        self._panel.setStyleSheet(f"background-color: {theme.panel_darkest};")
        self._panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._build_ui()

    @property
    def widget(self):
        """返回实际的 QWidget。"""
        return self._panel

    @property
    def width(self):
        return self._panel.width()

    @property
    def is_expanded(self):
        return self._expanded

    @property
    def swatches(self):
        return self._theme_swatches

    @property
    def draft(self):
        return self._theme_draft

    # ============================================================
    # UI 构建
    # ============================================================

    def _build_ui(self):
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        self._title_lbl = QLabel(S("theme", "panel_title"))
        self._title_lbl.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 14px; font-weight: bold;")
        title_row.addWidget(self._title_lbl); title_row.addStretch()
        self._btn_close = QPushButton("✕")
        self._btn_close.setFixedSize(28, 28)
        self._btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {theme.text_dim}; border: none;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ color: {theme.cyber_red}; }}
        """)
        self._btn_close.clicked.connect(self.collapse)
        title_row.addWidget(self._btn_close)
        panel_layout.addLayout(title_row)

        # ── 预设主题一键切换 ──
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        self._preset_label = QLabel(S("theme", "preset_label"))
        self._preset_label.setStyleSheet(f"color: {theme.text}; font-size: 12px;")
        preset_row.addWidget(self._preset_label)

        self._preset_combo = QComboBox()
        self._preset_combo.wheelEvent = lambda e: e.ignore()  # 禁用滚轮切换
        self._preset_combo.setMinimumHeight(26)
        for pid, pinfo in ThemeConfig.PRESETS.items():
            self._preset_combo.addItem(pinfo["name"], pid)
        current_preset_name = theme.current_preset_name()
        idx = self._preset_combo.findText(current_preset_name)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.card_bg}; color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 3px;
                padding: 2px 8px; font-size: 12px;
            }}
            QComboBox:hover {{ border-color: {theme.cyber_yellow}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {theme.card_bg}; color: {theme.text};
                border: 1px solid {theme.border}; selection-background-color: {theme.cyber_cyan};
            }}
        """)
        preset_row.addWidget(self._preset_combo, 1)

        self._btn_apply_preset = QPushButton(S("button", "apply_preset"))
        self._btn_apply_preset.setFixedHeight(26)
        self._btn_apply_preset.setObjectName("primaryBtn")
        self._btn_apply_preset.clicked.connect(self._on_apply_preset)
        preset_row.addWidget(self._btn_apply_preset)
        panel_layout.addLayout(preset_row)

        tip = QLabel(S("hint", "theme_tip"))
        tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px;")
        tip.setWordWrap(True)
        panel_layout.addWidget(tip)

        # 色块滚动区
        self._build_swatches(panel_layout)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton(S("button", "save_theme"))
        self._btn_save.setObjectName("primaryBtn")
        self._btn_save.clicked.connect(self._on_save)
        self._btn_reset = QPushButton(S("button", "reset_default"))
        self._btn_reset.setObjectName("actionBtn")
        self._btn_reset.clicked.connect(self._on_reset)
        self._btn_refresh = QPushButton(S("button", "refresh_preview"))
        self._btn_refresh.setObjectName("actionBtn")
        self._btn_refresh.clicked.connect(self._on_refresh_preview)
        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_reset)
        btn_row.addWidget(self._btn_refresh)
        panel_layout.addLayout(btn_row)

    def _build_swatches(self, panel_layout):
        self._swatch_scroll = QScrollArea()
        self._swatch_scroll.setWidgetResizable(True)
        self._swatch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._swatch_scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {theme.border}; "
            f"border-radius: 4px; background: {theme.panel_deeper}; }}")

        tw = QWidget()
        self._swatch_container = tw
        tw.setStyleSheet(f"background: {theme.panel_deeper};")
        tw_layout = QVBoxLayout(tw)
        tw_layout.setSpacing(6)

        categories = {}
        for jk, lbl, cat in THEME_FIELDS:
            if cat == "外链品牌":
                continue
            categories.setdefault(cat, []).append((jk, lbl))

        data = theme.to_dict()
        for cat_name, fields in categories.items():
            cat_lbl = QLabel(f"▸ {cat_name}")
            cat_lbl.setStyleSheet(
                f"color: {theme.cyber_cyan}; font-weight: bold; font-size: 13px; padding: 4px 0;")
            tw_layout.addWidget(cat_lbl)

            row = QHBoxLayout(); row.setSpacing(4); col_count = 0
            for json_key, label in fields:
                color = data.get(json_key, theme.panel_deeper)
                item = QWidget()
                item.setMinimumWidth(64)
                item_layout = QVBoxLayout(item)
                item_layout.setContentsMargins(2, 3, 2, 3)
                item_layout.setSpacing(3)

                swatch = QLabel("　")
                swatch.setFixedSize(48, 18)
                swatch.setStyleSheet(
                    f"background-color: {color}; border: none; border-radius: 2px;")
                swatch.setCursor(Qt.CursorShape.PointingHandCursor)
                swatch.mousePressEvent = lambda e, k=json_key, s=swatch: self._pick_color(k, s)
                item_layout.addWidget(swatch)

                name_lbl = QLabel(label)
                name_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 12px;")
                name_lbl.setWordWrap(True)
                item_layout.addWidget(name_lbl)

                row.addWidget(item)
                row.setStretchFactor(item, 1)
                self._theme_swatches[json_key] = swatch
                col_count += 1
                if col_count >= 3:
                    tw_layout.addLayout(row)
                    row = QHBoxLayout(); row.setSpacing(4); col_count = 0
            if col_count > 0:
                row.addStretch(); tw_layout.addLayout(row)
        tw_layout.addStretch()
        self._swatch_scroll.setWidget(tw)
        panel_layout.addWidget(self._swatch_scroll, 1)

    # ============================================================
    # 色块交互
    # ============================================================

    def _pick_color(self, json_key, swatch):
        current = theme.to_dict().get(json_key, theme.panel_deeper)
        color = QColorDialog.getColor(QColor(current), self._parent,
            S.format("theme", "color_pick_title", key=json_key))
        if color.isValid():
            hex_color = color.name()
            self._theme_draft[json_key] = hex_color
            swatch.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid {theme.border}; border-radius: 2px;")

    # ============================================================
    # 刷新 / 保存 / 重置 / 预设
    # ============================================================

    def _on_refresh_preview(self):
        if not self._theme_draft:
            QMessageBox.information(self._parent, S("theme", "prompt_title"),
                S("theme", "no_changes_preview"))
            return
        prev_preset = theme.active_preset
        theme.save(self._theme_draft)
        self._sync_preset_combo(prev_preset)
        self._on_theme_changed()

    def _on_save(self):
        if not self._theme_draft:
            QMessageBox.information(self._parent, S("theme", "prompt_title"),
                S("theme", "no_changes"))
            return
        prev_preset = theme.active_preset
        if theme.save(self._theme_draft):
            self._theme_draft = {}
            self._sync_preset_combo(prev_preset)
            self._on_theme_changed()
            preset_name = theme.current_preset_name()
            if prev_preset != theme.active_preset:
                self._add_log("ok", S.format("theme", "saved_to", name=preset_name))
            else:
                self._add_log("ok", S.format("theme", "saved", name=preset_name))
        else:
            self._add_log("error", S("theme", "save_failed"))

    def _sync_preset_combo(self, prev_preset: str):
        """如果预设被自动切换了，同步下拉框显示。"""
        if theme.active_preset != prev_preset:
            idx = self._preset_combo.findData(theme.active_preset)
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)

    def _on_reset(self):
        reply = QMessageBox.question(
            self._parent, S("theme", "reset_confirm_title"),
            S.format("theme", "reset_confirm_msg", name=theme.current_preset_name()),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        theme.reset()
        self._theme_draft = {}
        self._on_theme_changed()
        QMessageBox.information(self._parent, S("theme", "reset_done_title"),
            S.format("theme", "reset_done_msg", name=theme.current_preset_name()))

    def _on_apply_preset(self):
        preset_id = self._preset_combo.currentData()
        if not preset_id:
            return
        preset_name = ThemeConfig.PRESETS[preset_id]["name"]
        if theme.apply_preset(preset_id):
            self._theme_draft = {}
            self._on_theme_changed()
            # 确保下拉框停留在当前选择的预设
            idx = self._preset_combo.findData(preset_id)
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)
            self._add_log("ok", S.format("theme", "preset_applied", name=preset_name))
        else:
            self._add_log("error", S("theme", "preset_failed"))

    # ============================================================
    # 样式刷新
    # ============================================================

    def refresh_inline_styles(self):
        """刷新主题面板中所有颜色相关的内联样式。"""
        t = theme

        self._panel.setStyleSheet(f"background-color: {t.panel_darkest};")

        # 标题
        self._title_lbl.setStyleSheet(f"color: {t.cyber_yellow}; font-size: 14px; font-weight: bold;")

        # 预设方案标签
        self._preset_label.setStyleSheet(f"color: {t.text}; font-size: 12px;")

        # 同步预设下拉框
        current_name = theme.current_preset_name()
        idx = self._preset_combo.findText(current_name)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)

        # 关闭按钮
        self._btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {t.text_dim}; border: none;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ color: {t.cyber_red}; }}
        """)

        # 预设下拉框
        self._preset_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {t.card_bg}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 3px;
                padding: 2px 8px; font-size: 12px;
            }}
            QComboBox:hover {{ border-color: {t.cyber_yellow}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {t.card_bg}; color: {t.text};
                border: 1px solid {t.border}; selection-background-color: {t.cyber_cyan};
            }}
        """)

        # 色块滚动区
        self._swatch_scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {t.border}; "
            f"border-radius: 4px; background: {t.panel_deeper}; }}")
        self._swatch_container.setStyleSheet(f"background: {t.panel_deeper};")

    def rebuild_swatches(self):
        """刷新所有色块颜色。"""
        data = theme.to_dict()
        for json_key, swatch in self._theme_swatches.items():
            color = data.get(json_key, theme.panel_deeper)
            swatch.setStyleSheet(
                f"background-color: {color}; border: none; border-radius: 2px;")

    # ============================================================
    # 展开 / 折叠动画
    # ============================================================

    def toggle(self):
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if self._expanded:
            return
        self._expanded = True
        self._run_anim(0, self.PANEL_WIDTH)

    def collapse(self):
        if not self._expanded:
            return
        self._expanded = False
        self._run_anim(self._panel.width(), 0)

    def _run_anim(self, start_w, end_w):
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        self._anim = QPropertyAnimation(self._panel, b"minimumWidth")
        self._anim.setDuration(250)
        self._anim.setStartValue(start_w)
        self._anim.setEndValue(end_w)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)
        self._anim.start()

    def _on_anim_step(self, w):
        self._panel.setFixedWidth(w)
        self._panel.setVisible(w > 0)

    def on_resize(self, log_panel_visible):
        """动画步骤回调：同时更新父窗口宽度。"""
        extra = self._panel.width() + (420 if log_panel_visible else 0)
        self._parent.resize(580 + extra, self._parent.height())
