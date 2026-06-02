"""
WARFRAME-RELIC UI 构建 Mixin

负责 _setup_ui 主入口及各功能区块的 _build_* 方法。
还包括物品搜索、价格拉取、遗物 tooltip 等业务逻辑。

作为 Mixin 注入 ManagementPanel，所有方法通过 self 访问控件。
"""

import os
from pathlib import Path
from core.bg_layer import BgImageWidget

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QMessageBox, QGroupBox,
    QApplication, QTextEdit, QLineEdit,
    QScrollArea, QListWidget, QListWidgetItem,
    QToolTip,
)
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtWidgets import QGraphicsBlurEffect

from core.constants import theme, reload_theme, ThemeConfig
from core.constants import (CYBER_YELLOW, CYBER_CYAN, CYBER_MAGENTA,
                            COLOR_GOLD, COLOR_SILVER, COLOR_COPPER,
                            COLOR_VAULTED, COLOR_AVAILABLE)
from core.stylesheet import build_stylesheet
from core.hotkey_config import (
    load_hotkeys, save_hotkeys, validate_hotkey,
    DEFAULT_HOTKEYS, HOTKEY_LABELS,
    load_feature_toggles, save_feature_toggles,
    DEFAULT_FEATURE_TOGGLES, get_feature_toggle_labels,
    load_item_region, save_item_region,
)
from core.theme_fields import THEME_FIELDS
from core.theme_panel import ThemePanel
from core.update_panel import UpdatePanel, get_db_stats
from core.word_wrap_button import WordWrapButton
from core.hotkey_capture_button import HotkeyCaptureButton
from core.drop_tooltip import SOURCE_TYPE_CN
from data.ui_strings import S


class PanelBuilderMixin:
    """UI 构建：_setup_ui 及各功能区块 _build_* 方法。"""

    # ── 由 ManagementPanel.__init__ 设置 ──
    # _data_dir, _db_path, _alljson_path
    # _hotkeys, _feature_toggles

    # ── 信号 ──
    db_updated = pyqtSignal(str)
    hotkeys_changed = pyqtSignal(dict)
    theme_changed = pyqtSignal()
    reset_requested = pyqtSignal()
    feature_toggles_changed = pyqtSignal(dict)
    item_region_select_requested = pyqtSignal()

    # ============================================================
    # _setup_ui 主入口
    # ============================================================

    def _setup_ui(self):
        # 文字刷新注册表
        self._text_registry = []

        self.setWindowTitle(S("window_title", "management_panel"))
        self.setMinimumSize(420, 680)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setStyleSheet(build_stylesheet())

        # ============================================================
        # 分层架构：QGridLayout 同格子叠加四层
        # ============================================================
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. 背景图占位层（最底层）
        self._bg_image_placeholder = BgImageWidget()
        self._bg_image_placeholder.setObjectName("BgImagePlaceholder")
        self._bg_image_placeholder.setStyleSheet("background-color: transparent;")
        self._bg_blur_effect = QGraphicsBlurEffect()
        self._bg_blur_effect.setBlurRadius(theme.background_blur)
        self._bg_blur_effect.setBlurHints(QGraphicsBlurEffect.BlurHint.PerformanceHint)
        self._bg_image_placeholder.setGraphicsEffect(self._bg_blur_effect)
        main_layout.addWidget(self._bg_image_placeholder, 0, 0)

        # 2. 不透明度遮罩层（中层）
        self._opacity_overlay = QWidget()
        self._opacity_overlay.setObjectName("OpacityOverlay")
        self._opacity_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        main_layout.addWidget(self._opacity_overlay, 0, 0)

        # 3. 内容层（顶层）
        self._content_layer = QWidget()
        self._content_layer.setObjectName("ContentLayer")
        main_layout.addWidget(self._content_layer, 0, 0)

        self._update_background_size_immediate()
        self._apply_opacity_overlay()

        # 4. UI控件布局（在内容层上）
        outer_layout = QHBoxLayout(self._content_layer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ── 导航栏 ──
        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(140)
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                border-right: 1px solid {theme.border};
                padding: 8px 4px;
                outline: none;
            }}
            QListWidget::item {{
                color: {theme.text_dim};
                padding: 10px 12px;
                border-radius: 6px;
                margin: 2px 4px;
                font-size: 13px;
                background-color: rgba(5, 5, 20, 180);
            }}
            QListWidget::item:hover {{
                background-color: {theme.card_bg};
                color: {theme.text};
            }}
            QListWidget::item:selected {{
                background-color: {theme.cyber_yellow};
                color: #000;
                font-weight: bold;
            }}
        """)
        from data.icon_loader import get_icon_loader, get_nav_icon
        icon_loader = get_icon_loader()

        self._nav_items = [
            ("toggles",  "nav", "nav_toggles",  "功能开关"),
            ("status",   "nav", "nav_status",   "数据状态"),
            ("relic",    "nav", "nav_relic",    "遗物更新"),
            ("trans",    "nav", "nav_trans",    "翻译库"),
            ("items",    "nav", "nav_items",    "物品查询"),
            ("prices",   "nav", "nav_prices",   "价格数据"),
            ("hotkeys",  "nav", "nav_hotkeys",  "快捷键"),
            ("theme",    "nav", "nav_theme",    "主题换肤"),
            ("about",    "nav", "nav_about",    "关于"),
            ("reset",    "nav", "nav_reset",    "紧急重置"),
            ("preset",   "nav", "nav_preset",   "语言预设"),
        ]
        for nav_id, s_cat, s_key, default_text in self._nav_items:
            text = S(s_cat, s_key)
            if text.startswith("??") and text.endswith("??"):
                text = default_text
            qicon = icon_loader.get_icon("nav", nav_id, size=20)
            if qicon:
                item = QListWidgetItem(qicon, text)
            else:
                icon = get_nav_icon(nav_id)
                item = QListWidgetItem(f"{icon}  {text}")
            item.setData(Qt.ItemDataRole.UserRole, nav_id)
            self._nav_list.addItem(item)
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        outer_layout.addWidget(self._nav_list)

        # ── 右侧内容区域（可滚动）──
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._left_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }")

        self._left_widget = QWidget()
        self._left_widget.setStyleSheet("background-color: transparent;")
        self._left_widget.installEventFilter(self)
        content_layout = QVBoxLayout(self._left_widget)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(12)

        # 标题
        title = QLabel(S("title", "management_panel"))
        self._reg_text(title, "title", "management_panel")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(title)

        # 初始化子面板
        self._update_panel = UpdatePanel(self, self._data_dir, self._db_path, self._add_log)

        # 各功能区块
        self._build_feature_toggles_group(content_layout)
        self._build_status_group(content_layout)
        self._build_relic_update_group(content_layout)
        self._build_translation_group(content_layout)
        self._build_items_i18n_group(content_layout)
        self._build_price_group(content_layout)
        self._build_hotkey_group(content_layout)
        self._build_theme_group(content_layout)
        self._build_about_group(content_layout)
        self._build_reset_group(content_layout)
        self._build_language_preset_group(content_layout)

        # 退出按钮行
        exit_row = QHBoxLayout()
        exit_row.addStretch()
        self._btn_exit = WordWrapButton(S("button", "exit"))
        self._reg_text(self._btn_exit, "button", "exit")
        self._btn_exit.setObjectName("dangerBtn")
        self._btn_exit.clicked.connect(self._on_exit)
        exit_row.addWidget(self._btn_exit)
        content_layout.addLayout(exit_row)
        content_layout.addStretch()

        # 导航映射
        self._nav_groups = {}
        for nav_id, group in [
            ("toggles",  getattr(self, '_toggle_group', None)),
            ("status",   getattr(self, '_status_group', None)),
            ("relic",    getattr(self, '_relic_group', None)),
            ("trans",    getattr(self, '_trans_group', None)),
            ("items",    getattr(self, '_items_group', None)),
            ("prices",   getattr(self, '_price_group', None)),
            ("hotkeys",  getattr(self, '_hotkey_group', None)),
            ("theme",    getattr(self, '_theme_group', None)),
            ("about",    getattr(self, '_about_group', None)),
            ("reset",    getattr(self, '_reset_group', None)),
            ("preset",   getattr(self, '_lang_preset_group', None)),
        ]:
            if group is not None:
                self._nav_groups[nav_id] = group

        self._apply_word_wrap_to_buttons()
        self._left_scroll.setWidget(self._left_widget)
        outer_layout.addWidget(self._left_scroll, 1)

        # 右侧面板
        self._build_log_panel(outer_layout)
        self._build_theme_slide_panel(outer_layout)

        # 默认选中第一个
        self._nav_list.setCurrentRow(0)

    # ============================================================
    # 文字注册
    # ============================================================

    def _reg_text(self, widget, category: str, key: str):
        """注册需要刷新文字的控件。"""
        self._text_registry.append((widget, category, key))

    # ============================================================
    # 功能开关
    # ============================================================

    def _build_feature_toggles_group(self, parent_layout):
        from PyQt6.QtWidgets import QGridLayout
        group = QGroupBox(S("group", "feature_toggles"))
        self._toggle_group = group
        self._reg_text(group, "group", "feature_toggles")
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
        layout = QVBoxLayout(group)

        hint = QLabel(S("feature_toggle", "hint"))
        self._toggle_hint_label = hint
        self._reg_text(hint, "feature_toggle", "hint")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._feature_toggle_buttons = {}
        keys = list(DEFAULT_FEATURE_TOGGLES.keys())
        for i, key in enumerate(keys):
            row = i // 2
            col = i % 2
            btn = WordWrapButton()
            btn.setObjectName("toggleFeatureBtn")
            btn.setCheckable(True)
            btn.setChecked(self._feature_toggles.get(key, True))
            btn.clicked.connect(lambda checked, k=key: self._on_feature_toggle_changed(k, checked))
            self._feature_toggle_buttons[key] = btn
            grid.addWidget(btn, row, col)
        layout.addLayout(grid)
        parent_layout.addWidget(group)

        self._refresh_toggle_button_texts()
        self._refresh_toggle_button_styles()

    def _refresh_toggle_button_texts(self):
        if not hasattr(self, '_feature_toggle_buttons'):
            return
        _ft_labels = get_feature_toggle_labels()
        for key, btn in self._feature_toggle_buttons.items():
            label = _ft_labels.get(key, key)
            desc = S("feature_toggle", f"desc_{key}")
            btn.setText(f"{label}\n{desc}")

    def _on_feature_toggle_changed(self, key: str, state):
        self._feature_toggles[key] = bool(state)
        if save_feature_toggles(self._feature_toggles):
            self.feature_toggles_changed.emit(self._feature_toggles)
            _ft_labels = get_feature_toggle_labels()
            self._add_log('ok', f'功能开关已更新: {_ft_labels.get(key, key)}')
            self._refresh_toggle_button_styles()
        else:
            self._add_log('error', S("feature_toggle", "save_failed"))

    def get_feature_toggles(self) -> dict:
        return dict(self._feature_toggles)

    # ============================================================
    # 数据库状态
    # ============================================================

    def _build_status_group(self, parent_layout):
        group = QGroupBox(S("group", "db_status"))
        self._status_group = group
        self._reg_text(group, "group", "db_status")
        layout = QVBoxLayout(group)
        self._stat_label_refs = {}
        stat_labels = {}
        stat_grid = [
            (S("stat_label", "relics_total"), "relics", "relics_total"),
            (S("stat_label", "parts_total"), "parts", "parts_total"),
            (S("stat_label", "aliases_total"), "aliases", "aliases_total"),
            (S("stat_label", "vaulted"), "vaulted", "vaulted"),
            (S("stat_label", "available"), "available", "available"),
            (S("stat_label", "voidtrader"), "voidtrader", "voidtrader"),
            (S("stat_label", "db_size"), "db_size", "db_size"),
            (S("stat_label", "last_update"), "db_mtime", "last_update"),
        ]
        for label_text, data_key, s_key in stat_grid:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            self._reg_text(lbl, "stat_label", s_key)
            lbl.setObjectName("statLabel")
            lbl.setFixedWidth(110)
            val = QLabel(S("status", "placeholder"))
            val.setObjectName("statValue")
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            layout.addLayout(row)
            stat_labels[data_key] = val

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {theme.border}; max-height: 1px;")
        layout.addWidget(sep)

        self._status_trans_label = QLabel(S("status", "translation_db"))
        self._status_trans_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 2px 0;")
        layout.addWidget(self._status_trans_label)

        self._status_items_label = QLabel(S("status", "items_db"))
        self._status_items_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 2px 0;")
        layout.addWidget(self._status_items_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0); self._progress.hide()
        self._progress.setFixedHeight(6)
        layout.addWidget(self._progress)

        self._progress_text = QLabel("")
        self._progress_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_text.hide()
        layout.addWidget(self._progress_text)
        parent_layout.addWidget(group)

        self._update_panel.set_stat_labels(stat_labels)
        self._update_panel.set_status_extra_labels(self._status_trans_label, self._status_items_label)
        self._update_panel.set_progress(self._progress, self._progress_text)

    # ============================================================
    # 遗物数据库更新
    # ============================================================

    def _build_relic_update_group(self, parent_layout):
        group = QGroupBox(S("group", "relic_update"))
        self._relic_group = group
        self._reg_text(group, "group", "relic_update")
        layout = QVBoxLayout(group)

        source_label = QLabel(""); source_label.setWordWrap(True)
        layout.addWidget(source_label)

        row_fetch = QHBoxLayout()
        self._btn_fetch = WordWrapButton(S("button", "fetch_github"))
        self._reg_text(self._btn_fetch, "button", "fetch_github")
        self._btn_fetch.setObjectName("primaryBtn")
        self._btn_fetch.clicked.connect(self._update_panel.on_fetch)
        self._btn_browse = WordWrapButton(S("button", "browse_file"))
        self._reg_text(self._btn_browse, "button", "browse_file")
        self._btn_browse.clicked.connect(self._update_panel.on_browse)
        self._btn_update = WordWrapButton(S("button", "update_db"))
        self._reg_text(self._btn_update, "button", "update_db")
        self._btn_update.setObjectName("actionBtn")
        self._btn_update.clicked.connect(self._update_panel.on_update)
        row_fetch.addWidget(self._btn_fetch)
        row_fetch.addWidget(self._btn_browse)
        row_fetch.addWidget(self._btn_update)
        layout.addLayout(row_fetch)

        row1 = QHBoxLayout()
        self._btn_tutorial = WordWrapButton(S("button", "update_tutorial"))
        self._reg_text(self._btn_tutorial, "button", "update_tutorial")
        self._btn_tutorial.setObjectName("actionBtn")
        self._btn_tutorial.clicked.connect(self._update_panel.show_tutorial)
        self._btn_browse_db = WordWrapButton(S("button", "open_data_dir"))
        self._reg_text(self._btn_browse_db, "button", "open_data_dir")
        self._btn_browse_db.setObjectName("actionBtn")
        self._btn_browse_db.clicked.connect(self._open_data_dir)
        row1.addWidget(self._btn_tutorial)
        row1.addWidget(self._btn_browse_db)
        row1.addStretch()
        layout.addLayout(row1)

        hint = QLabel(S("hint", "data_source_relic"))
        self._reg_text(hint, "hint", "data_source_relic")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        parent_layout.addWidget(group)

        self._update_panel.set_source_label(source_label)
        self._update_panel.set_buttons(
            btn_update=self._btn_update, btn_fetch=self._btn_fetch,
            btn_browse=self._btn_browse,
            btn_browse_db=self._btn_browse_db, btn_tutorial=self._btn_tutorial)

    # ============================================================
    # 翻译数据库
    # ============================================================

    def _build_translation_group(self, parent_layout):
        group = QGroupBox(S("group", "translation_db"))
        self._trans_group = group
        self._reg_text(group, "group", "translation_db")
        layout = QVBoxLayout(group)

        stat_grid = [
            (S("stat_label", "trans_total"), "trans_total"),
            (S("stat_label", "db_size"), "db_size"),
            (S("stat_label", "last_update"), "last_update"),
        ]
        self._trans_stat_labels = {}
        for label, key in stat_grid:
            row = QHBoxLayout()
            lbl = QLabel(label)
            self._reg_text(lbl, "stat_label", key)
            lbl.setObjectName("statLabel")
            lbl.setFixedWidth(80)
            val = QLabel(S("status", "placeholder"))
            self._reg_text(val, "status", "placeholder")
            val.setObjectName("statValue")
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            layout.addLayout(row)
            self._trans_stat_labels[key] = val

        self._trans_cat_label = QLabel("")
        self._trans_cat_label.setWordWrap(True)
        self._trans_cat_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 2px 0;")
        self._trans_cat_label.hide()
        layout.addWidget(self._trans_cat_label)

        source_hint = QLabel(S("hint", "data_source_trans"))
        self._reg_text(source_hint, "hint", "data_source_trans")
        source_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        layout.addWidget(source_hint)

        btn_row = QHBoxLayout()
        self._btn_update_trans = WordWrapButton(S("button", "update_from_local"))
        self._reg_text(self._btn_update_trans, "button", "update_from_local")
        self._btn_update_trans.setObjectName("primaryBtn")
        self._btn_update_trans.clicked.connect(
            lambda: self._update_panel.on_update_translation('local'))
        self._btn_update_trans_wfcd = WordWrapButton(S("button", "update_from_network"))
        self._reg_text(self._btn_update_trans_wfcd, "button", "update_from_network")
        self._btn_update_trans_wfcd.setObjectName("actionBtn")
        self._btn_update_trans_wfcd.clicked.connect(self._on_update_trans_wfcd)
        self._btn_toggle_trans_detail = WordWrapButton(S("button", "toggle_detail_expand"))
        self._reg_text(self._btn_toggle_trans_detail, "button", "toggle_detail_expand")
        self._btn_toggle_trans_detail.setObjectName("actionBtn")
        self._btn_toggle_trans_detail.clicked.connect(self._toggle_trans_detail)
        self._btn_trans_tutorial = WordWrapButton(S("button", "update_tutorial"))
        self._reg_text(self._btn_trans_tutorial, "button", "update_tutorial")
        self._btn_trans_tutorial.setObjectName("actionBtn")
        self._btn_trans_tutorial.clicked.connect(self._show_trans_tutorial)
        btn_row.addWidget(self._btn_update_trans)
        btn_row.addWidget(self._btn_update_trans_wfcd)
        btn_row.addWidget(self._btn_toggle_trans_detail)
        btn_row.addWidget(self._btn_trans_tutorial)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._trans_progress = QProgressBar()
        self._trans_progress.setRange(0, 100)
        self._trans_progress.setValue(0)
        self._trans_progress.setFixedHeight(16)
        self._trans_progress.setFormat("%p%")
        self._trans_progress.hide()
        layout.addWidget(self._trans_progress)

        parent_layout.addWidget(group)

        self._update_panel.set_trans_widgets(
            stat_labels=self._trans_stat_labels,
            cat_label=self._trans_cat_label,
            btn_update=self._btn_update_trans,
            progress=self._trans_progress,
        )

    def _toggle_trans_detail(self):
        if self._trans_cat_label.isVisible():
            self._trans_cat_label.hide()
            self._btn_toggle_trans_detail.setText(S("button", "toggle_detail_expand"))
            self._reg_text(self._btn_toggle_trans_detail, "button", "toggle_detail_expand")
        else:
            self._trans_cat_label.show()
            self._btn_toggle_trans_detail.setText(S("button", "toggle_detail_collapse"))
            self._reg_text(self._btn_toggle_trans_detail, "button", "toggle_detail_collapse")

    def _on_update_trans_wfcd(self):
        self._update_panel.on_update_translation(source='wfcd')

    def _show_trans_tutorial(self):
        data_dir = str(Path(__file__).resolve().parent.parent / 'data')
        tutorial_text = S.format("tutorial", "trans_content", data_dir=data_dir)
        dlg = self._update_panel._build_text_dialog(
            S("tutorial", "trans_title"), tutorial_text, 560, 600, True, theme.cyber_yellow)
        dlg.exec()

    # ============================================================
    # 全物品中英对照
    # ============================================================

    def _build_items_i18n_group(self, parent_layout):
        group = QGroupBox(S("group", "items_i18n"))
        self._items_group = group
        self._reg_text(group, "group", "items_i18n")
        layout = QVBoxLayout(group)

        stat_grid = [
            (S("stat_label", "items_total"), "items_total"),
            (S("stat_label", "items_has_cn"), "items_has_cn"),
            (S("stat_label", "db_size"), "db_size"),
            (S("stat_label", "last_update"), "last_update"),
        ]
        self._items_stat_labels = {}
        for label, key in stat_grid:
            row = QHBoxLayout()
            lbl = QLabel(label)
            self._reg_text(lbl, "stat_label", key)
            lbl.setObjectName("statLabel")
            lbl.setFixedWidth(80)
            val = QLabel(S("status", "placeholder"))
            self._reg_text(val, "status", "placeholder")
            val.setObjectName("statValue")
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            layout.addLayout(row)
            self._items_stat_labels[key] = val

        query_title = QLabel(S("hint", "items_query_title"))
        self._reg_text(query_title, "hint", "items_query_title")
        query_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 12px; font-weight: bold; margin-top: 6px;")
        layout.addWidget(query_title)

        input_row = QHBoxLayout()
        input_row.setSpacing(0)
        input_row.setContentsMargins(0, 0, 0, 0)
        self._items_input_frame = QFrame()
        self._items_input_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        self._items_input_frame.setFixedHeight(36)
        frame_layout = QHBoxLayout()
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        self._items_search_input = QLineEdit()
        self._items_search_input.setPlaceholderText(S("hint", "items_search_placeholder"))
        self._reg_text(self._items_search_input, "hint", "items_search_placeholder")
        self._items_search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                color: {theme.cyber_cyan};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 6px 50px 6px 10px;
                font-family: "Consolas", "Microsoft YaHei";
                font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {theme.cyber_yellow}; }}
        """)
        self._items_search_input.textChanged.connect(self._on_items_search_changed)
        frame_layout.addWidget(self._items_search_input)
        self._items_input_frame.setLayout(frame_layout)
        input_row.addWidget(self._items_input_frame)
        layout.addLayout(input_row)

        self._items_search_hint = QLabel(S("hint", "items_search_default"))
        self._items_search_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 0;")
        layout.addWidget(self._items_search_hint)

        self._items_result_list = QListWidget()
        self._items_result_list.setMaximumHeight(320)
        self._items_result_list.itemClicked.connect(self._on_item_result_clicked)
        self._items_result_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 12px;
                padding: 2px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {theme.border};
            }}
            QListWidget::item:hover {{
                background-color: {theme.panel_bg};
            }}
            QListWidget::item:selected {{
                background-color: {theme.cyber_yellow};
                color: #000;
            }}
            QScrollBar:vertical {{
                background: {theme.panel_bg}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.border}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        layout.addWidget(self._items_result_list)

        hint = QLabel(S("hint", "data_source_items"))
        self._reg_text(hint, "hint", "data_source_items")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._items_search_timer = QTimer()
        self._items_search_timer.setSingleShot(True)
        self._items_search_timer.timeout.connect(self._do_items_search)

        parent_layout.addWidget(group)

    def refresh_items_i18n_stats(self):
        if not hasattr(self, '_items_stat_labels') or not self._items_stat_labels:
            return
        try:
            from data.items_i18n import get_db_stats
            stats = get_db_stats()
        except Exception:
            return
        if not stats.get('exists'):
            self._items_stat_labels['items_total'].setText(S("status", "db_not_exist"))
            for k in ['items_has_cn', 'db_size', 'last_update']:
                self._items_stat_labels[k].setText(S("status", "placeholder"))
            return
        self._items_stat_labels['items_total'].setText(S.format("stat_fmt", "count_items", count=stats['total']))
        self._items_stat_labels['items_total'].setStyleSheet(f"color: {theme.cyber_green}; font-weight: bold;")
        self._items_stat_labels['items_has_cn'].setText(S.format("stat_fmt", "count_items", count=stats['has_cn']))
        self._items_stat_labels['db_size'].setText(S.format("stat_fmt", "db_size_kb", size=stats['db_size'] / 1024))
        self._items_stat_labels['last_update'].setText(stats['db_mtime'])

    # ============================================================
    # 物品搜索
    # ============================================================

    def _on_items_search_changed(self, text: str):
        self._items_search_timer.stop()
        if len(text.strip()) >= 1:
            self._items_search_timer.start(200)
        else:
            self._items_result_list.clear()
            self._items_search_hint.setText(S("hint", "items_search_default"))
            self._reg_text(self._items_search_hint, "hint", "items_search_default")
            self._items_search_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px;")

    def _do_items_search(self):
        query = self._items_search_input.text().strip()
        if len(query) < 1:
            return
        try:
            from data.items_i18n import suggest_items
            results = suggest_items(query, limit=30)
        except Exception as e:
            import traceback
            print(f"[物品搜索] 异常: {e}")
            traceback.print_exc()
            self._items_result_list.clear()
            item = QListWidgetItem()
            lbl = QLabel(S("hint", "items_search_error"))
            self._reg_text(lbl, "hint", "items_search_error")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            item.setSizeHint(lbl.sizeHint())
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._items_result_list.addItem(item)
            self._items_result_list.setItemWidget(item, lbl)
            return

        self._items_result_list.clear()
        if not results:
            self._items_search_hint.setText(S.format("search", "no_match", query=query))
            self._items_search_hint.setStyleSheet(f"color: {theme.cyber_orange}; font-size: 10px;")
            return

        exact_count = sum(1 for r in results if r['match_quality'] == 'exact')
        prefix_count = sum(1 for r in results if r['match_quality'] == 'prefix')
        contain_count = sum(1 for r in results if r['match_quality'] == 'contains')
        hint_text = S.format("search", "mode_result",
            total=len(results), exact=exact_count, prefix=prefix_count, contain=contain_count)
        self._items_search_hint.setText(hint_text)
        self._items_search_hint.setStyleSheet(f"color: {theme.cyber_green}; font-size: 10px;")

        t = theme
        for r in results:
            en = r['en_name']
            zh = r['zh_name']
            cat = r['category']
            quality = r['match_quality']
            match_field = r.get('match_field', 'en')

            q_color = {'exact': t.cyber_green, 'prefix': t.cyber_yellow, 'contains': t.text_dim}
            q_mark = {'exact': '=', 'prefix': '~', 'contains': '·'}
            qc = q_color.get(quality, t.text_dim)
            qm = q_mark.get(quality, '?')

            highlight_field = en if match_field == 'en' else zh
            idx = highlight_field.lower().find(query.lower())
            if idx >= 0:
                highlighted = (
                    f'<span style="color:{t.text_dim};">{self._escape_html(highlight_field[:idx])}</span>'
                    f'<span style="color:{t.cyber_yellow}; font-weight:bold;">'
                    f'{self._escape_html(highlight_field[idx:idx+len(query)])}</span>'
                    f'<span style="color:{t.text_dim};">{self._escape_html(highlight_field[idx+len(query):])}</span>'
                )
            elif match_field == 'py':
                highlighted = (
                    f'<span style="color:{t.cyber_yellow}; font-weight:bold;">'
                    f'{self._escape_html(highlight_field)}</span>'
                )
            else:
                highlighted = f'<span style="color:{t.text_dim};">{self._escape_html(highlight_field)}</span>'

            if zh != en:
                zh_display = f'<span style="color:{t.cyber_cyan}; font-weight:bold;">{self._escape_html(zh)}</span>'
            else:
                zh_display = f'<span style="color:{t.text_dim}; font-style:italic;">{S("hint", "items_no_translation")}</span>'

            en_display = f'<span style="color:{t.text_dim};">{self._escape_html(en)}</span>'
            if match_field == 'en':
                en_display = highlighted
            else:
                if zh != en:
                    zh_display = highlighted

            html = (
                f'<span style="color:{qc};">{qm}</span> '
                f'{zh_display}  '
                f'<span style="color:{t.text_dim};">←</span> {en_display}  '
                f'<span style="color:{t.cyber_magenta}; font-size:10px;">[{self._escape_html(cat)}]</span>'
            )

            item = QListWidgetItem()
            lbl = QLabel(html)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setStyleSheet(
                "font-family: 'Consolas', 'Microsoft YaHei', monospace; font-size: 12px; "
                "padding: 0px 6px; background: transparent;"
            )
            lbl.setProperty("_item_en_name", en)
            lbl.setProperty("_item_category", cat)
            lbl.setMouseTracking(True)
            lbl.installEventFilter(self)
            item.setSizeHint(QtCore.QSize(self._items_result_list.viewport().width() - 20, 28))
            item.setData(Qt.ItemDataRole.UserRole, en)
            self._items_result_list.addItem(item)
            self._items_result_list.setItemWidget(item, lbl)

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def _on_item_result_clicked(self, item: QListWidgetItem):
        en_name = item.data(Qt.ItemDataRole.UserRole)
        if en_name:
            clipboard = QApplication.clipboard()
            clipboard.setText(en_name)
            self._items_search_hint.setText(S.format("search", "copied", name=en_name))
            self._items_search_hint.setStyleSheet(f"color: {theme.cyber_cyan}; font-size: 10px;")

    # ============================================================
    # 遗物 tooltip
    # ============================================================

    def _get_relic_info(self, en_name: str) -> dict | None:
        import re
        m = re.match(
            r'(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s+([A-Za-z0-9]+)\s+Relic',
            en_name, re.IGNORECASE
        )
        if not m:
            return None
        era_en = m.group(1).capitalize()
        code = m.group(2).upper()
        era_map = {
            'Lith': '古纪', 'Meso': '前纪', 'Neo': '中纪',
            'Axi': '后纪', 'Requiem': '安魂', 'Vanguard': '先锋',
        }
        era_cn = era_map.get(era_en)
        if not era_cn:
            return None
        relic_name_cn = f"{era_cn} {code}"
        try:
            if self._relic_db_cache is None:
                from data.wfinfo_relics import RelicDB
                self._relic_db_cache = RelicDB()
            info = self._relic_db_cache.find(relic_name_cn)
            if info:
                return info
        except Exception as e:
            print(f"[RelicTooltip] 查询遗物失败: {e}")
        return None

    @staticmethod
    def _format_relic_tooltip(relic_info: dict | None, sources: list[dict], item_name: str) -> str:
        def esc(text: str) -> str:
            return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

        parts = []
        parts.append(
            f"<div style='background:#0E0E24; padding:8px 12px; "
            f"border-bottom:1px solid #1a1a3a;'>"
            f"<span style='color:#00FFFF; font-size:16px; font-weight:bold;'>"
            f"◈ {esc(item_name)}</span>"
        )
        if relic_info:
            vaulted = relic_info.get('vaulted', False)
            status_color = '#00FF66' if vaulted else '#FF4444'
            status_text = '可获取' if vaulted else '已入库'
            parts.append(
                f"<span style='color:{status_color}; font-size:13px; margin-left:8px;'>"
                f"[{status_text}]</span>"
            )
        parts.append("</div>")

        if relic_info and relic_info.get('parts'):
            relic_parts = relic_info['parts']
            sorted_parts = sorted(relic_parts, key=lambda p: p.get('chance', 0))
            chances = sorted(set(p.get('chance', 0) for p in sorted_parts))
            if len(chances) >= 3:
                chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_SILVER, chances[2]: COLOR_COPPER}
            elif len(chances) == 2:
                chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_COPPER}
            else:
                chance_to_color = {chances[0]: COLOR_SILVER}

            parts.append(
                f"<div style='padding:6px 12px 4px 12px;'>"
                f"<span style='display:inline-block; width:3px; height:12px; "
                f"background:#FFD700; border-radius:2px; margin-right:6px; "
                f"vertical-align:middle;'></span>"
                f"<span style='color:#FFD700; font-size:14px; font-weight:bold; "
                f"vertical-align:middle;'>遗物内容</span>"
                f"<span style='color:#6677AA; font-size:12px; margin-left:4px;'>"
                f"({len(sorted_parts)}个部件)</span></div>"
            )
            for p in sorted_parts:
                ch = p.get('chance', 0)
                clr = chance_to_color.get(ch, COLOR_SILVER)
                rarity = p.get('rarity', '')
                rarity_cn_map = {'Common': '普通', 'Uncommon': '罕见', 'Rare': '稀有', 'Legendary': '传说'}
                rarity_cn = rarity_cn_map.get(rarity, rarity)
                parts.append(
                    f"<div style='padding:2px 0 2px 20px; font-size:13px; white-space:nowrap;'>"
                    f"<span style='color:{clr};'>● {esc(p['name'])}</span>"
                    f"<span style='color:#6677AA; margin-left:6px; font-size:11px;'>"
                    f"{rarity_cn} ({ch:.1f}%)</span></div>"
                )
            parts.append(
                f"<div style='margin:4px 12px; border-bottom:1px solid rgba(100,100,150,40);'></div>"
            )

        if sources:
            by_type = {}
            for s in sources:
                st = s.get('source_type', '')
                if st not in by_type:
                    by_type[st] = []
                by_type[st].append(s)

            type_colors = {
                'relics': '#FFD700', 'missionRewards': '#00FFFF',
                'bountyRewards': '#FF7700', 'cetusBountyRewards': '#FF7700',
                'solarisBountyRewards': '#FF7700', 'deimosRewards': '#FF7700',
                'zarimanRewards': '#FF7700', 'entratiLabRewards': '#FF7700',
                'hexRewards': '#FF7700', 'sortieRewards': '#FF0055',
                'keyRewards': '#00FF99', 'transientRewards': '#E066FF',
                'blueprintLocations': '#00FFFF', 'enemyModTables': '#FF6B6B',
                'enemyBlueprintTables': '#FF6B6B', 'modLocations': '#FF6B6B',
                'syndicates': '#FFE600', 'resourceByAvatar': '#8E9CB2',
                'sigilByAvatar': '#8E9CB2', 'additionalItemByAvatar': '#8E9CB2',
            }

            parts.append(
                f"<div style='padding:4px 12px 2px 12px;'>"
                f"<span style='display:inline-block; width:3px; height:12px; "
                f"background:#00FFFF; border-radius:2px; margin-right:6px; "
                f"vertical-align:middle;'></span>"
                f"<span style='color:#00FFFF; font-size:14px; font-weight:bold; "
                f"vertical-align:middle;'>掉落来源</span>"
                f"<span style='color:#6677AA; font-size:12px; margin-left:4px;'>"
                f"({len(sources)} 条)</span></div>"
            )
            for st, items in by_type.items():
                cn_st = SOURCE_TYPE_CN.get(st, st)
                accent = type_colors.get(st, '#6677AA')
                parts.append(
                    f"<div style='margin-top:4px; margin-bottom:1px; padding-left:12px;'>"
                    f"<span style='color:{accent}; font-size:12px; font-weight:bold;'>"
                    f"{esc(cn_st)}</span>"
                    f"<span style='color:#6677AA; font-size:11px; margin-left:4px;'>"
                    f"({len(items)})</span></div>"
                )
                for item in items:
                    loc = item.get('location', '?')
                    chance = item.get('chance', 0)
                    rotation = item.get('rotation', '')
                    if 0 < chance < 100:
                        chance_str = f"{chance:.1f}%"
                    elif chance >= 100:
                        chance_str = "必定"
                    else:
                        chance_str = ""
                    rot_tag = ""
                    if rotation:
                        rot_tag = (
                            f"<span style='display:inline-block; background:#1a1a3a; "
                            f"color:#8E9CB2; font-size:11px; padding:1px 5px; "
                            f"border-radius:3px; margin-left:4px;'>轮次{rotation}</span>"
                        )
                    parts.append(
                        f"<div style='padding:1px 0 1px 24px; font-size:12px; white-space:nowrap;'>"
                        f"<span style='color:#C8D0E0;'>{esc(loc)}</span>"
                        f"<span style='color:#8E9CB2; margin-left:6px;'>{chance_str}</span>"
                        f"{rot_tag}</div>"
                    )

        parts.append(
            f"<div style='background:#0E0E24; padding:4px 12px; "
            f"border-top:1px solid #1a1a3a; margin-top:4px;'>"
            f"<span style='color:#444466; font-size:11px;'>"
            f"数据来源: WFCD warframe-drop-data</span></div>"
        )
        return "".join(parts)

    # ============================================================
    # 价格数据库
    # ============================================================

    def _build_price_group(self, parent_layout):
        group = QGroupBox(S("group", "wm_prices"))
        self._price_group = group
        self._reg_text(group, "group", "wm_prices")
        layout = QVBoxLayout(group)

        stat_grid = [
            (S("stat_label", "price_total"), "price_total"),
            (S("stat_label", "price_has_sell"), "price_has_sell"),
            (S("stat_label", "price_has_weighted"), "price_has_weighted"),
            (S("stat_label", "last_update"), "price_mtime"),
        ]
        self._price_stat_labels = {}
        for label, key in stat_grid:
            row = QHBoxLayout()
            lbl = QLabel(label)
            self._reg_text(lbl, "stat_label", key)
            lbl.setObjectName("statLabel")
            lbl.setFixedWidth(80)
            val = QLabel(S("status", "placeholder"))
            self._reg_text(val, "status", "placeholder")
            val.setObjectName("statValue")
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            layout.addLayout(row)
            self._price_stat_labels[key] = val

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {theme.border}; max-height: 1px; margin: 4px 0;")
        layout.addWidget(sep)

        region_title = QLabel("📐 物品截图区域")
        region_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 12px; font-weight: bold;")
        layout.addWidget(region_title)

        self._price_region_status = QLabel("")
        self._price_region_status.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 2px 0;")
        self._price_region_status.setWordWrap(True)
        layout.addWidget(self._price_region_status)

        region_btn_row = QHBoxLayout()
        self._btn_set_item_region = WordWrapButton("设置物品区域")
        self._btn_set_item_region.setObjectName("actionBtn")
        self._btn_set_item_region.clicked.connect(self._on_set_item_region)
        self._btn_clear_item_region = WordWrapButton("清除区域")
        self._btn_clear_item_region.setObjectName("actionBtn")
        self._btn_clear_item_region.clicked.connect(self._on_clear_item_region)
        region_btn_row.addWidget(self._btn_set_item_region)
        region_btn_row.addWidget(self._btn_clear_item_region)
        region_btn_row.addStretch()
        layout.addLayout(region_btn_row)

        region_hint = QLabel("提示：框选4个物品卡片的总区域，程序会自动横向4等分。\n"
                            "按快捷键 Ctrl+T 即可自动截4图并查询价格。")
        region_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        region_hint.setWordWrap(True)
        layout.addWidget(region_hint)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background-color: {theme.border}; max-height: 1px; margin: 4px 0;")
        layout.addWidget(sep2)

        hint = QLabel(S("hint", "data_source_wm"))
        self._reg_text(hint, "hint", "data_source_wm")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self._btn_fetch_prices = WordWrapButton(S("button", "fetch_prices"))
        self._reg_text(self._btn_fetch_prices, "button", "fetch_prices")
        self._btn_fetch_prices.setObjectName("primaryBtn")
        self._btn_fetch_prices.clicked.connect(self._on_fetch_prices)
        btn_row.addWidget(self._btn_fetch_prices)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._price_progress = QProgressBar()
        self._price_progress.setRange(0, 100)
        self._price_progress.setValue(0)
        self._price_progress.setFixedHeight(16)
        self._price_progress.setFormat("%p%")
        self._price_progress.hide()
        layout.addWidget(self._price_progress)

        parent_layout.addWidget(group)
        self._refresh_item_region_status()

    def refresh_price_stats(self):
        if not hasattr(self, '_price_stat_labels') or not self._price_stat_labels:
            return
        try:
            from data.wm_prices import get_price_stats
            stats = get_price_stats()
        except Exception:
            return
        if not stats.get('exists'):
            self._price_stat_labels['price_total'].setText(S("status", "db_not_exist"))
            for k in ['price_has_sell', 'price_has_weighted', 'price_mtime']:
                self._price_stat_labels[k].setText(S("status", "placeholder"))
            return
        self._price_stat_labels['price_total'].setText(S.format("stat_fmt", "count_items", count=stats['total']))
        self._price_stat_labels['price_total'].setStyleSheet(f"color: {theme.cyber_green}; font-weight: bold;")
        self._price_stat_labels['price_has_sell'].setText(S.format("stat_fmt", "count_items", count=stats['has_sell']))
        self._price_stat_labels['price_has_weighted'].setText(S.format("stat_fmt", "count_items", count=stats['has_weighted']))
        self._price_stat_labels['price_mtime'].setText(stats['updated_at'])

    def _refresh_item_region_status(self):
        region = load_item_region()
        if region:
            self._price_region_status.setText(
                f"已设置: x={region['x']}, y={region['y']}, w={region['w']}, h={region['h']} "
                f"(将横向4等分)")
            self._price_region_status.setStyleSheet(f"color: {theme.cyber_green}; font-size: 11px;")
        else:
            self._price_region_status.setText("未设置物品区域（需要先设置才能用快捷键查询价格）")
            self._price_region_status.setStyleSheet(f"color: {theme.cyber_orange}; font-size: 11px;")

    def _on_set_item_region(self):
        self.showMinimized()
        self._request_item_region_selection()

    def _request_item_region_selection(self):
        if hasattr(self, 'item_region_select_requested'):
            self.item_region_select_requested.emit()
        else:
            from PyQt6.QtWidgets import QMessageBox
            self.showNormal()
            QMessageBox.information(self, "提示",
                "请先在 Warframe 游戏中打开物品选择界面，\n"
                "然后按 Ctrl+G 框选包含4个物品卡片的横向区域。\n\n"
                "区域设置功能需要通过主程序框选完成。")

    def _on_clear_item_region(self):
        try:
            path = os.path.join(str(self._data_dir), 'item_region.json')
            if os.path.exists(path):
                os.remove(path)
            self._refresh_item_region_status()
            self._add_log('ok', '物品区域已清除')
        except Exception as e:
            self._add_log('error', f'清除物品区域失败: {e}')

    def _on_fetch_prices(self):
        if not os.path.exists(str(self._data_dir / 'items_i18n.db')):
            QMessageBox.warning(self, S("price", "no_items_title"), S("price", "no_items_msg"))
            return
        reply = QMessageBox.question(
            self, S("price", "fetch_confirm_title"), S("price", "fetch_confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._btn_fetch_prices.setEnabled(False)
        self._price_progress.show()
        self._price_progress.setValue(0)
        self._add_log('info', '========== 开始拉取 warframe.market 卖价数据 ==========')
        self._add_log('info', 'API: https://api.warframe.market/v2/')
        self._add_log('info', '模式: 多线程并发拉取 (8线程) + 全局限速 3请求/秒')
        self._add_log('info', '权重机制: 偏离中位数 >30% 视为压价，权重降为 0.1')

        from data.wm_prices import PriceFetchWorker, MAX_WORKERS
        import threading
        self._price_worker = PriceFetchWorker(max_workers=MAX_WORKERS)
        self._price_worker.step_changed.connect(self._on_price_step)
        self._price_worker.log.connect(self._on_price_log)
        self._price_worker.progress_pct.connect(self._price_progress.setValue)
        self._price_worker.progress_detail.connect(self._on_price_progress)
        self._price_worker.finished.connect(self._on_price_finished)
        self._price_worker.error.connect(self._on_price_error)
        threading.Thread(target=self._price_worker.run, daemon=True).start()

    def _on_price_step(self, step, desc):
        self._add_log('info', f'[步骤 {step}] {desc}')

    def _on_price_log(self, level, msg):
        self._add_log(level, msg)

    def _on_price_progress(self, current, total):
        if total > 0:
            pct = current * 100 // total
            self._price_progress.setFormat(f"{current}/{total} ({pct}%)")

    def _on_price_finished(self, result):
        self._btn_fetch_prices.setEnabled(True)
        self._price_progress.setValue(100)
        self._price_progress.setFormat(S("status", "done"))
        self.refresh_price_stats()
        self._add_log('ok', S("price", "fetch_done"))
        QMessageBox.information(self, S("price", "fetch_done_title"),
            S.format("price", "fetch_done_msg",
                total=result.get('total', 0),
                with_sell=result.get('with_sell', 0),
                with_weighted=result.get('with_weighted', 0),
                total_abnormal=result.get('total_abnormal', 0),
                elapsed=result.get('elapsed', 0)))

    def _on_price_error(self, err_msg):
        self._btn_fetch_prices.setEnabled(True)
        self._price_progress.hide()
        self._add_log('error', f'价格拉取失败: {err_msg}')
        QMessageBox.critical(self, S("price", "fetch_failed_title"),
            S.format("price", "fetch_failed_msg", error=err_msg))

    # ============================================================
    # 热键配置
    # ============================================================

    def _build_hotkey_group(self, parent_layout):
        group = QGroupBox(S("group", "hotkey_settings"))
        self._hotkey_group = group
        self._reg_text(group, "group", "hotkey_settings")
        layout = QVBoxLayout(group)

        self._hotkey_tip = QLabel("点击按钮后按下组合键即可录制，按 Esc 取消")
        self._hotkey_tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        layout.addWidget(self._hotkey_tip)

        self._hotkey_buttons = {}
        for key in DEFAULT_HOTKEYS:
            row = QHBoxLayout()
            lbl = QLabel(HOTKEY_LABELS.get(key, key))
            lbl.setStyleSheet(f"color: {theme.label_default}; font-size: 12px;")
            lbl.setFixedWidth(140)
            row.addWidget(lbl)
            btn = HotkeyCaptureButton(self._hotkeys.get(key, ""))
            btn.setFixedWidth(160)
            btn.setFixedHeight(32)
            btn.setStyleSheet(self._hotkey_btn_style())
            row.addWidget(btn)
            row.addStretch()
            layout.addLayout(row)
            self._hotkey_buttons[key] = btn

        btn_row = QHBoxLayout()
        self._btn_save_hotkeys = WordWrapButton(S("button", "save_hotkeys"))
        self._reg_text(self._btn_save_hotkeys, "button", "save_hotkeys")
        self._btn_save_hotkeys.setObjectName("primaryBtn")
        self._btn_save_hotkeys.clicked.connect(self._on_save_hotkeys)
        self._btn_reset_hotkeys = WordWrapButton(S("button", "reset_default"))
        self._reg_text(self._btn_reset_hotkeys, "button", "reset_default")
        self._btn_reset_hotkeys.setObjectName("actionBtn")
        self._btn_reset_hotkeys.clicked.connect(self._on_reset_hotkeys)
        btn_row.addWidget(self._btn_save_hotkeys)
        btn_row.addWidget(self._btn_reset_hotkeys); btn_row.addStretch()
        layout.addLayout(btn_row)
        parent_layout.addWidget(group)

    # ============================================================
    # 紧急重置
    # ============================================================

    def _build_reset_group(self, parent_layout):
        group = QGroupBox(S("group", "recovery"))
        self._reset_group = group
        self._reg_text(group, "group", "recovery")
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
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        hint = QLabel(S("hint", "recovery"))
        self._reset_hint_label = hint
        self._reg_text(hint, "hint", "recovery")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; border: none; background: transparent;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self._btn_reset_state = WordWrapButton(S("button", "reset_state"))
        self._reg_text(self._btn_reset_state, "button", "reset_state")
        self._btn_reset_state.setObjectName("dangerBtn")
        self._btn_reset_state.setMinimumHeight(40)
        self._btn_reset_state.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.cyber_red};
                color: white;
                border: 2px solid {theme.cyber_orange};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #cc3333;
                border-color: {theme.cyber_yellow};
            }}
            QPushButton:pressed {{
                background-color: #aa2222;
            }}
        """)
        self._btn_reset_state.clicked.connect(self._on_reset_state)
        btn_row.addWidget(self._btn_reset_state)

        self._btn_reload_hotkeys = WordWrapButton(S("button", "reload_hotkeys"))
        self._reg_text(self._btn_reload_hotkeys, "button", "reload_hotkeys")
        self._btn_reload_hotkeys.setMinimumHeight(40)
        self._btn_reload_hotkeys.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.cyber_orange};
                border: 1px solid {theme.cyber_orange};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {theme.card_bg};
                border-color: {theme.cyber_yellow};
                color: {theme.cyber_yellow};
            }}
        """)
        self._btn_reload_hotkeys.clicked.connect(self._on_reload_hotkeys)
        btn_row.addWidget(self._btn_reload_hotkeys)
        layout.addLayout(btn_row)
        parent_layout.addWidget(group)

    # ============================================================
    # 主题入口
    # ============================================================

    def _build_theme_group(self, parent_layout):
        group = QGroupBox(S("group", "theme"))
        self._theme_group = group
        self._reg_text(group, "group", "theme")
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self._btn_toggle_theme = WordWrapButton(S("button", "custom_theme"))
        self._reg_text(self._btn_toggle_theme, "button", "custom_theme")
        self._btn_toggle_theme.setObjectName("primaryBtn")
        self._btn_toggle_theme.clicked.connect(self._toggle_theme_panel)
        btn_row.addWidget(self._btn_toggle_theme); btn_row.addStretch()
        layout.addLayout(btn_row)
        parent_layout.addWidget(group)

    # ============================================================
    # 主题侧滑面板
    # ============================================================

    def _build_theme_slide_panel(self, outer_layout):
        self._theme_panel = ThemePanel(
            parent_widget=self,
            on_theme_changed=self._on_theme_changed_internal,
            add_log=self._add_log,
        )
        orig_anim_step = self._theme_panel._on_anim_step
        def anim_step_with_resize(w):
            orig_anim_step(w)
            self._adjust_window_width()
        self._theme_panel._on_anim_step = anim_step_with_resize
        outer_layout.addWidget(self._theme_panel.widget)

    # ============================================================
    # 关于作者
    # ============================================================

    def _build_about_group(self, parent_layout):
        group = QGroupBox(S("group", "about_author"))
        self._about_group = group
        self._reg_text(group, "group", "about_author")
        group.setStyleSheet(f"""
            QGroupBox {{
                background-color: transparent;
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 16px;
                margin-top: 8px;
                font-size: 12px;
                color: {theme.text};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                font-weight: bold;
            }}
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 8, 8, 8)

        author_info = QLabel(S("hint", "about_author"))
        self._reg_text(author_info, "hint", "about_author")
        author_info.setStyleSheet(f"""
            color: {theme.cyber_cyan};
            font-size: 13px;
            font-weight: bold;
            padding: 4px 0;
        """)
        author_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author_info)

        links_layout = QHBoxLayout()
        links_layout.setSpacing(24)
        links_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._about_link_buttons = []
        for icon, label, color, hover, handler, s_key in [
            ("📺", S("button", "bilibili_home"),
             theme.brand_bilibili, theme.brand_bilibili_hover, self._open_bilibili, "bilibili_home"),
            ("💻", S("button", "github_repo"),
             theme.brand_github, theme.brand_github_hover, self._open_github, "github_repo"),
        ]:
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(6)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 14px;")
            btn = WordWrapButton(label)
            self._reg_text(btn, "button", s_key)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255,255,255,0.05);
                    color: {color};
                    border: 1px solid {color};
                    border-radius: 4px;
                    padding: 6px 16px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: rgba(255,255,255,0.1);
                    color: {hover};
                    border-color: {hover};
                }}
            """)
            btn.clicked.connect(handler)
            self._about_link_buttons.append((btn, s_key))
            btn_layout.addWidget(icon_lbl)
            btn_layout.addWidget(btn)
            links_layout.addLayout(btn_layout)
        layout.addLayout(links_layout)

        from data.version import PROJECT_FULL_NAME, VERSION_DESCRIPTION
        version_label = QLabel(f"{PROJECT_FULL_NAME}\n{VERSION_DESCRIPTION}")
        version_label.setStyleSheet(f"""
            color: {theme.text_dim};
            font-size: 11px;
            font-family: 'Consolas', monospace;
        """)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setWordWrap(True)
        layout.addWidget(version_label)
        parent_layout.addWidget(group)

    # ============================================================
    # 语言预设
    # ============================================================

    def _build_language_preset_group(self, parent_layout):
        from PyQt6.QtWidgets import QComboBox
        from data.ui_strings import get_active_preset, get_preset_info, set_language_preset

        group = QGroupBox("语言风格 · 文案预设")
        self._lang_preset_group = group
        group.setStyleSheet(f"""
            QGroupBox {{
                background-color: transparent;
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 8px;
                margin-top: 8px;
                font-size: 11px;
                color: {theme.text_dim};
            }}
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("当前风格：")
        self._lang_preset_label = lbl
        lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 12px; border: none; background: transparent;")
        row.addWidget(lbl)

        self._preset_combo = QComboBox()
        self._preset_combo.wheelEvent = lambda e: e.ignore()
        self._preset_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.card_bg};
                color: {theme.cyber_cyan};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                min-width: 160px;
            }}
            QComboBox:hover {{ border-color: {theme.cyber_yellow}; }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: transparent;
                color: {theme.text};
                border: 1px solid {theme.border};
                selection-background-color: {theme.cyber_yellow};
                selection-color: #000;
            }}
        """)

        presets = get_preset_info()
        active_id = get_active_preset()
        self._preset_data = {}
        selected_index = 0
        for idx, (pid, info) in enumerate(presets.items()):
            display = f"{info.get('name', pid)}"
            self._preset_combo.addItem(display)
            self._preset_data[display] = pid
            if pid == active_id:
                selected_index = idx
        self._preset_combo.setCurrentIndex(selected_index)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        row.addWidget(self._preset_combo, 1)

        self._preset_desc = QLabel("")
        self._preset_desc.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; border: none; background: transparent; padding: 2px 0;")
        self._preset_desc.setWordWrap(True)
        self._update_preset_desc()

        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self._preset_desc)
        parent_layout.addWidget(group)

    def _update_preset_desc(self):
        from data.ui_strings import get_active_preset, get_preset_info
        active = get_active_preset()
        presets = get_preset_info()
        info = presets.get(active, {})
        desc = info.get("desc", "")
        self._preset_desc.setText(f"  {desc}")

    def _on_preset_changed(self, index: int):
        display = self._preset_combo.currentText()
        preset_id = self._preset_data.get(display)
        if not preset_id:
            return
        from data.ui_strings import set_language_preset, reload_strings
        if set_language_preset(preset_id):
            self._update_preset_desc()
            self._add_log('ok', f'语言风格已切换至: {display}')
            self._rebuild_ui_for_preset()
        else:
            self._add_log('error', f'语言风格切换失败: {preset_id}')

    def _rebuild_ui_for_preset(self):
        self.setWindowTitle(S("window_title", "management_panel"))
        for widget, category, key in self._text_registry:
            try:
                if hasattr(widget, 'setTitle') and type(widget).__name__ == 'QGroupBox':
                    widget.setTitle(S(category, key))
                elif hasattr(widget, 'setPlaceholderText'):
                    widget.setPlaceholderText(S(category, key))
                elif hasattr(widget, 'setText'):
                    widget.setText(S(category, key))
            except Exception:
                pass
        self._refresh_nav_labels()
        self._refresh_toggle_button_texts()
        self._refresh_toggle_button_styles()
        if self._theme_panel:
            self._theme_panel.refresh_inline_styles()
        self.setStyleSheet(build_stylesheet())
        self._refresh_inline_styles()
        self._update_panel.refresh_stats()
        self._update_panel.refresh_translation_stats()
        self.refresh_items_i18n_stats()
        self.refresh_price_stats()

    # ============================================================
    # 日志面板
    # ============================================================

    def _build_log_panel(self, outer_layout):
        log_panel = QWidget()
        log_panel.setStyleSheet("background-color: transparent;")
        log_panel.setMinimumWidth(420)
        log_panel.setMaximumWidth(520)
        log_panel.hide()

        layout = QVBoxLayout(log_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        log_title = QLabel(S("log", "panel_title"))
        self._reg_text(log_title, "log", "panel_title")
        log_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 14px; font-weight: bold;")
        self._log_title_lbl = log_title
        layout.addWidget(log_title)

        sep = QFrame(); sep.setObjectName("sep"); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        step_row = QHBoxLayout()
        step_icon = QLabel("⏳")
        step_icon.setStyleSheet("font-size: 20px;")
        step_icon.setFixedWidth(32)
        step_label = QLabel(S("log", "waiting"))
        self._reg_text(step_label, "log", "waiting")
        step_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 13px;")
        step_label.setWordWrap(True)
        step_row.addWidget(step_icon); step_row.addWidget(step_label, 1)
        layout.addLayout(step_row)

        dl_progress = QProgressBar()
        dl_progress.setRange(0, 100); dl_progress.setValue(0)
        dl_progress.setFixedHeight(18)
        dl_progress.setFormat("%p%")
        dl_progress.hide()
        dl_progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {theme.border}; border-radius: 4px;
                background-color: {theme.card_bg};
                text-align: center; color: {theme.cyber_yellow};
                font-size: 11px; font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {theme.progress_gradient_start},
                    stop:0.5 {theme.progress_gradient_mid},
                    stop:1 {theme.progress_gradient_end});
                border-radius: 3px;
            }}
        """)
        layout.addWidget(dl_progress)

        log_detail = QLabel("")
        log_detail.setStyleSheet(f"color: {theme.cyber_cyan}; font-size: 11px; padding: 4px 0;")
        log_detail.setWordWrap(True)
        layout.addWidget(log_detail)

        log_area = QTextEdit()
        log_area.setReadOnly(True)
        log_area.setObjectName("LogArea")
        log_area.setStyleSheet(f"""
            QTextEdit#LogArea {{
                color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px; padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {theme.panel_bg}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.border}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        log_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(log_area, 1)

        btn_close_log = WordWrapButton(S("button", "close_log_panel"))
        self._reg_text(btn_close_log, "button", "close_log_panel")
        btn_close_log.clicked.connect(self._update_panel.hide_log_panel if self._update_panel else lambda: log_panel.hide())
        btn_close_log.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.get_panel_bg_color(180)}; color: {theme.text_dim};
                border: 1px solid {theme.border}; border-radius: 4px;
                padding: 6px; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.btn_hover_bg}; color: {theme.text};
            }}
        """)
        layout.addWidget(btn_close_log)
        outer_layout.addWidget(log_panel)

        self._update_panel.set_log_panel_widgets(
            log_panel, log_area, step_icon, step_label,
            log_detail, dl_progress, btn_close_log)

        btn_close_log.clicked.disconnect()
        btn_close_log.clicked.connect(self._update_panel.hide_log_panel)

    # ============================================================
    # 导航切换
    # ============================================================

    def _on_nav_changed(self, index: int):
        if index < 0 or index >= len(self._nav_items):
            return
        nav_id = self._nav_items[index][0]
        group = self._nav_groups.get(nav_id)
        if group and self._left_scroll:
            vbar = self._left_scroll.verticalScrollBar()
            target_y = group.y() - 16
            vbar.setValue(max(0, target_y))

        if hasattr(self, '_last_highlighted_group') and self._last_highlighted_group:
            self._restore_group_border(self._last_highlighted_group)
        if group:
            self._highlight_group_border(group)
            self._last_highlighted_group = group

        QTimer.singleShot(50, self._adjust_window_width)

    def _refresh_nav_labels(self):
        if not hasattr(self, '_nav_list') or not hasattr(self, '_nav_items'):
            return
        for i, (nav_id, icon, s_cat, s_key, default_text) in enumerate(self._nav_items):
            item = self._nav_list.item(i)
            if item:
                text = S(s_cat, s_key)
                if text.startswith("??") and text.endswith("??"):
                    text = default_text
                item.setText(f"{icon}  {text}")

    # ============================================================
    # 事件过滤器（滚轮转发 + tooltip）
    # ============================================================

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._left_widget and event.type() == QEvent.Type.Wheel:
            if hasattr(self, '_left_scroll') and self._left_scroll:
                vbar = self._left_scroll.verticalScrollBar()
                if vbar.isVisible() or vbar.maximum() > vbar.minimum():
                    vbar.wheelEvent(event)
                    return True

        if event.type() == QEvent.Type.ToolTip and isinstance(obj, QLabel):
            en_name = obj.property("_item_en_name")
            if en_name:
                from core.drop_tooltip import get_index
                idx = get_index()
                sources = idx.query(en_name, max_sources=20)
                category = obj.property("_item_category") or ''
                if 'Relic' in category or 'Relic' in en_name:
                    relic_info = self._get_relic_info(en_name)
                    tooltip_html = self._format_relic_tooltip(relic_info, sources, en_name)
                else:
                    tooltip_html = idx.format_tooltip(sources, en_name)
                QToolTip.showText(event.globalPos(), tooltip_html, obj)
                return True

        return super().eventFilter(obj, event)

    # ============================================================
    # 按钮换行
    # ============================================================

    def _apply_word_wrap_to_buttons(self):
        min_btn_height = 40
        def _walk(widget):
            from PyQt6.QtWidgets import QCheckBox
            for child in widget.children():
                if isinstance(child, QCheckBox):
                    if child.minimumHeight() < min_btn_height:
                        child.setMinimumHeight(min_btn_height)
                _walk(child)
        _walk(self._left_widget)
