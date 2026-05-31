"""
WARFRAME-RELIC 管理面板
- 独立窗口，通过热键 Ctrl+Shift+G 唤起
- 功能：数据库状态、更新、快捷键配置、主题换肤
- 内部委托给 theme_panel.py / update_panel.py 处理子功能
"""
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QMessageBox, QGroupBox,
    QApplication, QTextEdit, QLineEdit,
    QScrollArea, QListWidget, QListWidgetItem,
)
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from core.constants import theme, reload_theme, ThemeConfig
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
from data.ui_strings import S


# ============================================================
# 管理面板窗口
# ============================================================

class ManagementPanel(QWidget):
    """WARFRAME-RELIC 管理面板。

    将主题配色委托给 ThemePanel，数据更新/日志委托给 UpdatePanel。
    """

    db_updated = pyqtSignal(str)
    hotkeys_changed = pyqtSignal(dict)
    theme_changed = pyqtSignal()
    reset_requested = pyqtSignal()
    feature_toggles_changed = pyqtSignal(dict)  # 功能开关变更
    item_region_select_requested = pyqtSignal()  # 物品区域框选请求

    def __init__(self):
        super().__init__()
        self._data_dir = Path(__file__).resolve().parent.parent / 'data'
        self._db_path = str(self._data_dir / 'relics.db')
        self._alljson_path = str(self._data_dir / 'all.json')
        self._hotkeys = load_hotkeys()
        self._feature_toggles = load_feature_toggles()  # 功能开关
        self._first_show = True

        # 子面板
        self._theme_panel = None   # ThemePanel 实例
        self._update_panel = None  # UpdatePanel 实例

        self._setup_ui()
        self._update_panel.refresh_stats()
        self._update_panel.refresh_translation_stats()
        self.refresh_items_i18n_stats()
        self.refresh_price_stats()
        self._refresh_hotkey_ui()

    # ---- showEvent ----

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self._update_panel.enable_auto_show()
            QTimer.singleShot(50, self._fix_initial_size)

    def _fix_initial_size(self):
        self.updateGeometry()
        self.layout().activate()
        # 内容区合理最小宽度（导航栏140 + 内容区margin 20*2 + group内容至少420）
        content_min_w = 140 + 20 * 2 + 420
        min_h = 780
        self.setMinimumSize(content_min_w, min_h)
        # 窗口初始宽度取 sizeHint 和最小值的较大者，避免过窄挤压功能区边框
        hint = self.layout().sizeHint()
        init_w = max(hint.width(), content_min_w)
        init_h = max(hint.height(), min_h)
        self.resize(init_w, init_h)

    @property
    def _theme_panel_width(self):
        """当前主题侧滑面板的实际宽度。"""
        if self._theme_panel:
            return self._theme_panel.widget.width() if self._theme_panel.is_expanded else 0
        return 0

    # ============================================================
    # UI 构建
    # ============================================================

    def _setup_ui(self):
        # 文字刷新注册表：[(widget, S_category, S_key), ...]
        # 切换语言预设时遍历刷新所有已注册的控件文字
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

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ============================================================
        # 左侧导航栏
        # ============================================================
        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(140)
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {theme.panel_darkest};
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
        # 导航项定义：(nav_id, 图标, S_category, S_key, 默认显示名)
        self._nav_items = [
            ("toggles",  "⚙", "nav", "nav_toggles",  "功能开关"),
            ("status",   "📊", "nav", "nav_status",   "数据状态"),
            ("relic",    "🔄", "nav", "nav_relic",    "遗物更新"),
            ("trans",    "🌐", "nav", "nav_trans",    "翻译库"),
            ("items",    "🔍", "nav", "nav_items",    "物品查询"),
            ("prices",   "💰", "nav", "nav_prices",   "价格数据"),
            ("hotkeys",  "⌨", "nav", "nav_hotkeys",  "快捷键"),
            ("theme",    "🎨", "nav", "nav_theme",    "主题换肤"),
            ("about",    "ℹ", "nav", "nav_about",    "关于"),
            ("reset",    "⚠", "nav", "nav_reset",    "紧急重置"),
        ]
        for nav_id, icon, s_cat, s_key, default_text in self._nav_items:
            # S() 不存在该 key 时返回 "??category.key??"，此时用默认文本
            text = S(s_cat, s_key)
            if text.startswith("??") and text.endswith("??"):
                text = default_text
            item = QListWidgetItem(f"{icon}  {text}")
            item.setData(Qt.ItemDataRole.UserRole, nav_id)
            self._nav_list.addItem(item)
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)

        outer_layout.addWidget(self._nav_list)

        # ============================================================
        # 右侧内容区域（可滚动）
        # ============================================================
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._left_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {theme.panel_bg}; }}")


        self._left_widget = QWidget()
        self._left_widget.setStyleSheet(f"background-color: {theme.panel_bg};")
        # 安装事件过滤器，让鼠标滚轮可以滚动隐藏了滚动条的 QScrollArea
        self._left_widget.installEventFilter(self)
        main_layout = QVBoxLayout(self._left_widget)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 标题
        title = QLabel(S("title", "management_panel"))
        self._reg_text(title, "title", "management_panel")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # 初始化子面板（必须先于 build 方法）
        self._update_panel = UpdatePanel(self, self._data_dir, self._db_path, self._add_log)

        # ---- 各功能区块 ----
        self._build_feature_toggles_group(main_layout)
        self._build_status_group(main_layout)
        self._build_relic_update_group(main_layout)
        self._build_translation_group(main_layout)
        self._build_items_i18n_group(main_layout)
        self._build_price_group(main_layout)
        self._build_hotkey_group(main_layout)
        self._build_theme_group(main_layout)
        self._build_about_group(main_layout)
        self._build_reset_group(main_layout)
        self._build_language_preset_group(main_layout)

        # 底部提示 + 退出
        self._bottom_tip = QLabel(S("hint", "bottom_tip"))
        self._bottom_tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        self._bottom_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self._bottom_tip)

        exit_row = QHBoxLayout()
        exit_row.addStretch()
        self._btn_exit = WordWrapButton(S("button", "exit"))
        self._reg_text(self._btn_exit, "button", "exit")
        self._btn_exit.setObjectName("dangerBtn")
        self._btn_exit.clicked.connect(self._on_exit)
        exit_row.addWidget(self._btn_exit)
        main_layout.addLayout(exit_row)
        main_layout.addStretch()

        # 收集各区块的 QGroupBox，用于导航跳转
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
        ]:
            if group is not None:
                self._nav_groups[nav_id] = group

        self._apply_word_wrap_to_buttons()

        self._left_scroll.setWidget(self._left_widget)
        outer_layout.addWidget(self._left_scroll, 1)

        # 右侧面板
        self._build_log_panel(outer_layout)
        self._build_theme_slide_panel(outer_layout)

        # 默认选中第一个导航项
        self._nav_list.setCurrentRow(0)

    # ---- 文字刷新注册 ----

    def _reg_text(self, widget, category: str, key: str):
        """注册需要刷新文字的控件。切换语言预设时自动遍历刷新。"""
        self._text_registry.append((widget, category, key))

    # ---- 状态区块 ----

    def _build_status_group(self, parent_layout):
        group = QGroupBox(S("group", "db_status"))
        self._status_group = group
        self._reg_text(group, "group", "db_status")
        layout = QVBoxLayout(group)
        self._stat_label_refs = {}  # key → (label_widget, S_key)  用于预设切换时刷新
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
            val = QLabel(S("status", "placeholder"))
            self._reg_text(val, "status", "placeholder")
            val.setObjectName("statValue")
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            layout.addLayout(row)
            stat_labels[data_key] = val

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {theme.border}; max-height: 1px;")
        layout.addWidget(sep)

        # 翻译库 & 物品库概要
        self._status_trans_label = QLabel(S("status", "translation_db"))
        self._reg_text(self._status_trans_label, "status", "translation_db")
        self._status_trans_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 2px 0;")
        layout.addWidget(self._status_trans_label)

        self._status_items_label = QLabel(S("status", "items_db"))
        self._reg_text(self._status_items_label, "status", "items_db")
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

        # 注入到 update_panel
        self._update_panel.set_stat_labels(stat_labels)
        self._update_panel.set_status_extra_labels(self._status_trans_label, self._status_items_label)
        self._update_panel.set_progress(self._progress, self._progress_text)

    # ---- 遗物数据库更新 ----

    def _build_relic_update_group(self, parent_layout):
        group = QGroupBox(S("group", "relic_update"))
        self._relic_group = group
        self._reg_text(group, "group", "relic_update")
        layout = QVBoxLayout(group)

        # 数据源提示行
        source_label = QLabel(""); source_label.setWordWrap(True)
        layout.addWidget(source_label)

        # 主要按钮行：自动拉取 + 手动选择 + 更新
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

        # 辅助按钮行：教程 + 打开目录
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

        # 数据源说明
        hint = QLabel(S("hint", "data_source_relic"))
        self._reg_text(hint, "hint", "data_source_relic")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        parent_layout.addWidget(group)

        # 注入到 update_panel
        self._update_panel.set_source_label(source_label)
        self._update_panel.set_buttons(
            btn_update=self._btn_update, btn_fetch=self._btn_fetch,
            btn_browse=self._btn_browse,
            btn_browse_db=self._btn_browse_db, btn_tutorial=self._btn_tutorial)

    # ---- 翻译数据库 ----

    def _build_translation_group(self, parent_layout):
        group = QGroupBox(S("group", "translation_db"))
        self._trans_group = group
        self._reg_text(group, "group", "translation_db")
        layout = QVBoxLayout(group)

        # 统计行
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

        # 分类详情（可折叠）
        self._trans_cat_label = QLabel("")
        self._trans_cat_label.setWordWrap(True)
        self._trans_cat_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 2px 0;")
        self._trans_cat_label.hide()
        layout.addWidget(self._trans_cat_label)

        # 数据源提示
        source_hint = QLabel(S("hint", "data_source_trans"))
        self._reg_text(source_hint, "hint", "data_source_trans")
        source_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        layout.addWidget(source_hint)

        # 按钮行
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

        # 翻译进度条
        self._trans_progress = QProgressBar()
        self._trans_progress.setRange(0, 100)
        self._trans_progress.setValue(0)
        self._trans_progress.setFixedHeight(16)
        self._trans_progress.setFormat("%p%")
        self._trans_progress.hide()
        layout.addWidget(self._trans_progress)

        parent_layout.addWidget(group)

        # 注入到 update_panel
        self._update_panel.set_trans_widgets(
            stat_labels=self._trans_stat_labels,
            cat_label=self._trans_cat_label,
            btn_update=self._btn_update_trans,
            progress=self._trans_progress,
        )

        parent_layout.addWidget(group)

    # ---- 全物品中英对照数据库 ----

    def _build_items_i18n_group(self, parent_layout):
        group = QGroupBox(S("group", "items_i18n"))
        self._items_group = group
        self._reg_text(group, "group", "items_i18n")
        layout = QVBoxLayout(group)

        # 统计行
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

        # ---- 中英双语查询区 ----
        query_title = QLabel(S("hint", "items_query_title"))
        self._reg_text(query_title, "hint", "items_query_title")
        query_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 12px; font-weight: bold; margin-top: 6px;")
        layout.addWidget(query_title)

        # 输入行（输入框 + 清除按钮叠放）
        input_row = QHBoxLayout()
        input_row.setSpacing(0)
        input_row.setContentsMargins(0, 0, 0, 0)

        # 用 QFrame 做容器，按钮绝对定位叠在输入框上
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
                background-color: {theme.panel_darkest};
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

        # 清除按钮：叠在输入框内右侧
        self._items_clear_btn = WordWrapButton(S("button", "search_clear"))
        self._reg_text(self._items_clear_btn, "button", "search_clear")
        self._items_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._items_clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.panel_darkest};
                color: {theme.text_dim};
                border: 1px solid {theme.border};
                border-left: none;
                border-radius: 0px 3px 3px 0px;
                font-family: "Microsoft YaHei";
                font-size: 12px;
                min-width: 44px;
                padding: 0px 8px;
            }}
            QPushButton:hover {{
                background-color: {theme.cyber_red};
                color: #fff;
                border-color: {theme.cyber_red};
            }}
        """)
        self._items_clear_btn.clicked.connect(self._items_search_input.clear)
        self._items_clear_btn.setParent(self._items_input_frame)
        self._items_clear_btn.setFixedSize(46, 28)
        self._items_clear_btn.move(self._items_input_frame.width() - 47, 3)
        self._items_clear_btn.show()

        input_row.addWidget(self._items_input_frame)
        layout.addLayout(input_row)

        # 窗口大小变化时重新定位清除按钮
        self._items_search_input.installEventFilter(self)

        # 搜索结果提示
        self._items_search_hint = QLabel(S("hint", "items_search_default"))
        self._items_search_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 0;")
        layout.addWidget(self._items_search_hint)

        # 搜索结果列表（可点击复制英文名）
        self._items_result_list = QListWidget()
        self._items_result_list.setMaximumHeight(200)
        self._items_result_list.itemClicked.connect(self._on_item_result_clicked)
        self._items_result_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {theme.panel_darkest};
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

        # 数据源提示
        hint = QLabel(S("hint", "data_source_items"))
        self._reg_text(hint, "hint", "data_source_items")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 防抖定时器
        self._items_search_timer = QTimer()
        self._items_search_timer.setSingleShot(True)
        self._items_search_timer.timeout.connect(self._do_items_search)

        parent_layout.addWidget(group)

    # ---- warframe.market 价格数据库 ----

    def _build_price_group(self, parent_layout):
        group = QGroupBox(S("group", "wm_prices"))
        self._price_group = group
        self._reg_text(group, "group", "wm_prices")
        layout = QVBoxLayout(group)

        # 统计行
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

        # ---- 物品区域设置 ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {theme.border}; max-height: 1px; margin: 4px 0;")
        layout.addWidget(sep)

        region_title = QLabel("📐 物品截图区域")
        region_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 12px; font-weight: bold;")
        layout.addWidget(region_title)

        # 当前区域状态
        self._price_region_status = QLabel("")
        self._price_region_status.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 2px 0;")
        self._price_region_status.setWordWrap(True)
        layout.addWidget(self._price_region_status)

        # 设置区域按钮行
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
                            "按快捷键 Ctrl+Shift+P 即可自动截4图并查询价格。")
        region_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        region_hint.setWordWrap(True)
        layout.addWidget(region_hint)

        # ---- 分隔 ----
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background-color: {theme.border}; max-height: 1px; margin: 4px 0;")
        layout.addWidget(sep2)

        # 数据源提示
        hint = QLabel(S("hint", "data_source_wm"))
        self._reg_text(hint, "hint", "data_source_wm")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 按钮行
        btn_row = QHBoxLayout()
        self._btn_fetch_prices = WordWrapButton(S("button", "fetch_prices"))
        self._reg_text(self._btn_fetch_prices, "button", "fetch_prices")
        self._btn_fetch_prices.setObjectName("primaryBtn")
        self._btn_fetch_prices.clicked.connect(self._on_fetch_prices)
        btn_row.addWidget(self._btn_fetch_prices)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 价格拉取进度条
        self._price_progress = QProgressBar()
        self._price_progress.setRange(0, 100)
        self._price_progress.setValue(0)
        self._price_progress.setFixedHeight(16)
        self._price_progress.setFormat("%p%")
        self._price_progress.hide()
        layout.addWidget(self._price_progress)

        parent_layout.addWidget(group)

        # 初始化区域状态显示
        self._refresh_item_region_status()

    def refresh_price_stats(self):
        """刷新 warframe.market 价格数据库统计信息到 UI 标签。"""
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
        self._price_stat_labels['price_total'].setStyleSheet(
            f"color: {theme.cyber_green}; font-weight: bold;")

        self._price_stat_labels['price_has_sell'].setText(S.format("stat_fmt", "count_items", count=stats['has_sell']))
        self._price_stat_labels['price_has_weighted'].setText(S.format("stat_fmt", "count_items", count=stats['has_weighted']))
        self._price_stat_labels['price_mtime'].setText(stats['updated_at'])

    # ---- 物品区域设置 ----

    def _refresh_item_region_status(self):
        """刷新物品区域状态显示。"""
        region = load_item_region()
        if region:
            self._price_region_status.setText(
                f"已设置: x={region['x']}, y={region['y']}, w={region['w']}, h={region['h']} "
                f"(将横向4等分)")
            self._price_region_status.setStyleSheet(
                f"color: {theme.cyber_green}; font-size: 11px;")
        else:
            self._price_region_status.setText("未设置物品区域（需要先设置才能用快捷键查询价格）")
            self._price_region_status.setStyleSheet(
                f"color: {theme.cyber_orange}; font-size: 11px;")

    def _on_set_item_region(self):
        """设置物品区域：发出信号让主程序启动框选模式。"""
        # 最小化面板让用户看到桌面
        self.showMinimized()
        # 通过信号通知主程序启动物品区域框选
        self._request_item_region_selection()

    def _request_item_region_selection(self):
        """请求主程序启动物品区域框选。通过已有的 reset_requested 变通，
        或新增信号。这里使用一个更简单的方式：直接通知 overlay 开始框选。"""
        # 使用 item_region_select_requested 信号
        if hasattr(self, 'item_region_select_requested'):
            self.item_region_select_requested.emit()
        else:
            # 信号未定义时，使用 QTimer 延迟弹窗提示
            from PyQt6.QtWidgets import QMessageBox
            self.showNormal()
            QMessageBox.information(self, "提示",
                "请先在 Warframe 游戏中打开物品选择界面，\n"
                "然后按 Ctrl+G 框选包含4个物品卡片的横向区域。\n\n"
                "区域设置功能需要通过主程序框选完成。")

    def _on_clear_item_region(self):
        """清除物品区域设置。"""
        try:
            path = os.path.join(str(self._data_dir), 'item_region.json')
            if os.path.exists(path):
                os.remove(path)
            self._refresh_item_region_status()
            self._add_log('ok', '物品区域已清除')
        except Exception as e:
            self._add_log('error', f'清除物品区域失败: {e}')

    def _on_fetch_prices(self):
        """触发 warframe.market 价格拉取。"""
        if not os.path.exists(str(self._data_dir / 'items_i18n.db')):
            QMessageBox.warning(self, S("price", "no_items_title"),
                S("price", "no_items_msg"))
            return

        reply = QMessageBox.question(
            self, S("price", "fetch_confirm_title"),
            S("price", "fetch_confirm_msg"),
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

    def _toggle_trans_detail(self):
        """切换翻译分类详情的显示/隐藏。"""
        if self._trans_cat_label.isVisible():
            self._trans_cat_label.hide()
            self._btn_toggle_trans_detail.setText(S("button", "toggle_detail_expand"))
            self._reg_text(self._btn_toggle_trans_detail, "button", "toggle_detail_expand")
        else:
            self._trans_cat_label.show()
            self._btn_toggle_trans_detail.setText(S("button", "toggle_detail_collapse"))
            self._reg_text(self._btn_toggle_trans_detail, "button", "toggle_detail_collapse")

    def _on_update_trans_wfcd(self):
        """从网络拉取 WFCD 数据更新翻译库。"""
        self._update_panel.on_update_translation(source='wfcd')

    def refresh_items_i18n_stats(self):
        """刷新全物品数据库统计信息到 UI 标签。"""
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

    # ---- 物品名称查询 ----

    def eventFilter(self, obj, event):
        """事件过滤器：动态调整清除按钮位置 + 滚轮转发到隐藏滚动条。"""
        from PyQt6.QtCore import QEvent
        if hasattr(self, '_items_search_input') and obj is self._items_search_input and event.type() == QEvent.Type.Resize:
            btn = self._items_clear_btn
            frame = self._items_input_frame
            btn.move(frame.width() - btn.width() - 1, 4)
        # 将内容区的鼠标滚轮事件转发到已隐藏的垂直滚动条
        if obj is self._left_widget and event.type() == QEvent.Type.Wheel:
            if hasattr(self, '_left_scroll') and self._left_scroll:
                vbar = self._left_scroll.verticalScrollBar()
                if vbar.isVisible() or vbar.maximum() > vbar.minimum():
                    vbar.wheelEvent(event)
                    return True
        return super().eventFilter(obj, event)

    def _on_items_search_changed(self, text: str):
        """输入文本变化时启动防抖定时器。"""
        self._items_search_timer.stop()
        if len(text.strip()) >= 1:
            self._items_search_timer.start(200)  # 200ms 防抖
        else:
            self._items_result_list.clear()
            self._items_search_hint.setText(S("hint", "items_search_default"))
            self._reg_text(self._items_search_hint, "hint", "items_search_default")
            self._items_search_hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px;")

    def _do_items_search(self):
        """执行实时模糊搜索并显示结果（自动中英双向，富文本彩色展示）。"""
        query = self._items_search_input.text().strip()
        if len(query) < 1:
            return

        try:
            from data.items_i18n import suggest_items
            results = suggest_items(query, limit=30)
        except Exception:
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
            self._items_search_hint.setStyleSheet(
                f"color: {theme.cyber_orange}; font-size: 10px;")
            return

        # 判断搜索模式
        search_mode = results[0].get('search_mode', 'en2cn')

        # 统计
        exact_count = sum(1 for r in results if r['match_quality'] == 'exact')
        prefix_count = sum(1 for r in results if r['match_quality'] == 'prefix')
        contain_count = sum(1 for r in results if r['match_quality'] == 'contains')

        if search_mode == 'cn2en':
            hint_text = S.format("search", "mode_cn2en",
                total=len(results), exact=exact_count, prefix=prefix_count, contain=contain_count)
        else:
            hint_text = S.format("search", "mode_en2cn",
                total=len(results), exact=exact_count, prefix=prefix_count, contain=contain_count)

        self._items_search_hint.setText(hint_text)
        self._items_search_hint.setStyleSheet(
            f"color: {theme.cyber_green}; font-size: 10px;")

        t = theme
        for r in results:
            en = r['en_name']
            zh = r['zh_name']
            cat = r['category']
            quality = r['match_quality']

            # 匹配质量颜色和标记
            q_color = {'exact': t.cyber_green, 'prefix': t.cyber_yellow, 'contains': t.text_dim}
            q_mark = {'exact': '=', 'prefix': '~', 'contains': '·'}
            qc = q_color.get(quality, t.text_dim)
            qm = q_mark.get(quality, '?')

            # 根据搜索模式决定高亮哪个字段
            if search_mode == 'cn2en':
                # 输入中文 → 高亮中文匹配部分
                highlight_field = zh
            else:
                # 输入英文 → 高亮英文匹配部分
                highlight_field = en

            idx = highlight_field.lower().find(query.lower())
            if idx >= 0:
                highlighted = (
                    f'<span style="color:{t.text_dim};">{self._escape_html(highlight_field[:idx])}</span>'
                    f'<span style="color:{t.cyber_yellow}; font-weight:bold;">'
                    f'{self._escape_html(highlight_field[idx:idx+len(query)])}</span>'
                    f'<span style="color:{t.text_dim};">{self._escape_html(highlight_field[idx+len(query):])}</span>'
                )
            else:
                highlighted = f'<span style="color:{t.text_dim};">{self._escape_html(highlight_field)}</span>'

            # 中文名：有翻译显示青色加粗，无翻译显示暗色斜体
            if zh != en:
                zh_display = f'<span style="color:{t.cyber_cyan}; font-weight:bold;">{self._escape_html(zh)}</span>'
            else:
                zh_display = f'<span style="color:{t.text_dim}; font-style:italic;">{S("hint", "items_no_translation")}</span>'

            # 英文名显示
            en_display = f'<span style="color:{t.text_dim};">{self._escape_html(en)}</span>'

            # 如果是中文搜索，高亮中文名；如果是英文搜索，高亮英文名
            if search_mode == 'cn2en':
                # 中文高亮 + 英文普通
                if zh != en:
                    zh_display = highlighted
                html = (
                    f'<span style="color:{qc};">{qm}</span> '
                    f'{zh_display}  '
                    f'<span style="color:{t.text_dim};">←</span> {en_display}  '
                    f'<span style="color:{t.cyber_magenta}; font-size:10px;">[{self._escape_html(cat)}]</span>'
                )
            else:
                # 英文高亮 + 中文普通
                en_display = highlighted
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
                f"font-family: 'Consolas', 'Microsoft YaHei', monospace; font-size: 12px; "
                f"padding: 0px 6px; background: transparent;"
            )
            # 强制设置 item 高度，避免 QLabel 的 sizeHint() 计算偏小导致文字截断
            item.setSizeHint(QtCore.QSize(self._items_result_list.viewport().width() - 20, 28))
            # 英文名存 UserRole，点击时复制
            item.setData(Qt.ItemDataRole.UserRole, en)
            self._items_result_list.addItem(item)
            self._items_result_list.setItemWidget(item, lbl)

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符。"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def _on_item_result_clicked(self, item: QListWidgetItem):
        """点击某条结果：复制其英文名称到剪贴板。"""
        en_name = item.data(Qt.ItemDataRole.UserRole)
        if en_name:
            clipboard = QApplication.clipboard()
            clipboard.setText(en_name)
            # 在提示中显示已复制
            self._items_search_hint.setText(
                S.format("search", "copied", name=en_name))
            self._items_search_hint.setStyleSheet(
                f"color: {theme.cyber_cyan}; font-size: 10px;")

    def _show_trans_tutorial(self):
        """显示中英文翻译数据库更新教程。"""
        data_dir = str(Path(__file__).resolve().parent.parent / 'data')
        tutorial_text = S.format("tutorial", "trans_content", data_dir=data_dir)
        dlg = self._update_panel._build_text_dialog(
            S("tutorial", "trans_title"), tutorial_text, 560, 600, True, theme.cyber_yellow)
        dlg.exec()

    # ---- 热键配置 ----

    def _build_hotkey_group(self, parent_layout):
        group = QGroupBox(S("group", "hotkey_settings"))
        self._hotkey_group = group
        self._reg_text(group, "group", "hotkey_settings")
        layout = QVBoxLayout(group)

        self._hotkey_tip = QLabel("点击按钮后按下组合键即可录制，按 Esc 取消")
        self._hotkey_tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        layout.addWidget(self._hotkey_tip)

        self._hotkey_buttons = {}  # key → HotkeyCaptureButton

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

    def _hotkey_btn_style(self) -> str:
        """快捷键按钮通用样式。"""
        return f"""
            HotkeyCaptureButton {{
                background-color: {theme.panel_darkest};
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
                background-color: {theme.panel_darkest};
            }}
        """

    # ---- 紧急重置 ----

    def _build_reset_group(self, parent_layout):
        group = QGroupBox(S("group", "recovery"))
        self._reset_group = group
        self._reg_text(group, "group", "recovery")
        group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {theme.panel_darkest};
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
                background-color: {theme.panel_darkest};
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

    # ---- 功能开关 ----


    def _build_feature_toggles_group(self, parent_layout):
        """构建截图后功能开关区域——2x2 大按钮网格。"""
        from PyQt6.QtWidgets import QGridLayout

        group = QGroupBox(S("group", "feature_toggles"))
        self._toggle_group = group
        self._reg_text(group, "group", "feature_toggles")

        layout = QVBoxLayout(group)

        # 提示文字
        hint = QLabel(S("feature_toggle", "hint"))
        self._reg_text(hint, "feature_toggle", "hint")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 功能大按钮（2x2 网格）
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

        # 首次更新按钮文字和样式
        self._refresh_toggle_button_texts()
        self._refresh_toggle_button_styles()

    def _refresh_toggle_button_texts(self):
        """刷新所有功能开关按钮的文字（名称 + 描述）。"""
        if not hasattr(self, '_feature_toggle_buttons'):
            return
        _ft_labels = get_feature_toggle_labels()
        for key, btn in self._feature_toggle_buttons.items():
            label = _ft_labels.get(key, key)
            desc = S("feature_toggle", f"desc_{key}")
            btn.setText(f"{label}\n{desc}")

    def _refresh_toggle_button_styles(self):
        """根据开关状态刷新按钮样式：亮=开，暗=关。"""
        if not hasattr(self, '_feature_toggle_buttons'):
            return
        for key, btn in self._feature_toggle_buttons.items():
            is_on = btn.isChecked()
            if is_on:
                btn.setStyleSheet(f"""
                    QPushButton#toggleFeatureBtn {{
                        background-color: {theme.card_bg};
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
                        background-color: {theme.btn_hover_bg};
                        border-color: {theme.cyber_yellow};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton#toggleFeatureBtn {{
                        background-color: {theme.panel_darkest};
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

    def _on_feature_toggle_changed(self, key: str, state):
        """功能开关按钮点击时保存并发射信号。"""
        self._feature_toggles[key] = bool(state)
        if save_feature_toggles(self._feature_toggles):
            self.feature_toggles_changed.emit(self._feature_toggles)
            _ft_labels = get_feature_toggle_labels()
            self._add_log('ok', f'功能开关已更新: {_ft_labels.get(key, key)}')
            self._refresh_toggle_button_styles()
        else:
            self._add_log('error', S("feature_toggle", "save_failed"))

    def get_feature_toggles(self) -> dict:
        """获取当前功能开关配置。"""
        return dict(self._feature_toggles)

    # ---- 主题入口按钮 ----


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

    # ---- 主题侧滑面板 ----

    def _build_theme_slide_panel(self, outer_layout):
        self._theme_panel = ThemePanel(
            parent_widget=self,
            on_theme_changed=self._on_theme_changed_internal,
            add_log=self._add_log,
        )
        # 重写动画回调以包含窗口尺寸调整
        orig_anim_step = self._theme_panel._on_anim_step
        def anim_step_with_resize(w):
            orig_anim_step(w)
            self._theme_panel.on_resize(self._update_panel.log_panel_visible)
        self._theme_panel._on_anim_step = anim_step_with_resize
        outer_layout.addWidget(self._theme_panel.widget)

    # ---- 导航切换 ----

    def _on_nav_changed(self, index: int):
        """点击导航标签时，滚动到对应的功能区块并高亮其边框。"""
        if index < 0 or index >= len(self._nav_items):
            return
        nav_id = self._nav_items[index][0]  # nav_id 在 tuple 的第一个位置
        group = self._nav_groups.get(nav_id)
        if group and self._left_scroll:
            # 使用垂直滚动条精确定位，避免 ensureWidgetVisible 导致水平偏移
            vbar = self._left_scroll.verticalScrollBar()
            target_y = group.y() - 16  # 留一点顶部边距
            vbar.setValue(max(0, target_y))

        # 恢复上一个高亮的 group 边框
        if hasattr(self, '_last_highlighted_group') and self._last_highlighted_group:
            self._restore_group_border(self._last_highlighted_group)

        # 高亮当前 group 的边框
        if group:
            self._highlight_group_border(group)
            self._last_highlighted_group = group

    def _highlight_group_border(self, group: QGroupBox):
        """高亮 group 边框（荧光绿加粗效果）。"""
        group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {theme.panel_darkest};
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
        # 紧急重置 group 有特殊样式（橙色），需要特殊处理
        if group is getattr(self, '_reset_group', None):
            group.setStyleSheet(f"""
                QGroupBox {{
                    background-color: {theme.panel_darkest};
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
                    background-color: {theme.panel_darkest};
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

    def _refresh_nav_labels(self):
        """刷新导航标签文字（语言预设切换时调用）。"""
        if not hasattr(self, '_nav_list') or not hasattr(self, '_nav_items'):
            return
        for i, (nav_id, icon, s_cat, s_key, default_text) in enumerate(self._nav_items):
            item = self._nav_list.item(i)
            if item:
                text = S(s_cat, s_key)
                if text.startswith("??") and text.endswith("??"):
                    text = default_text
                item.setText(f"{icon}  {text}")

    # ---- 关于作者 ----

    def _build_about_group(self, parent_layout):
        group = QGroupBox(S("group", "about_author"))
        self._about_group = group
        self._reg_text(group, "group", "about_author")
        layout = QVBoxLayout(group); layout.setSpacing(4)

        author_row = QHBoxLayout()
        about_lbl = QLabel(S("hint", "about_author"))
        self._reg_text(about_lbl, "hint", "about_author")
        author_row.addWidget(about_lbl)
        author_row.addStretch()
        layout.addLayout(author_row)

        for icon, label, obj_name, color, hover, handler, s_key in [
            ("⏣", S("button", "bilibili_home"), "bilibiliBtn",
             theme.brand_bilibili, theme.brand_bilibili_hover, self._open_bilibili, "bilibili_home"),
            ("⏣", S("button", "github_repo"), "githubBtn",
             theme.brand_github, theme.brand_github_hover, self._open_github, "github_repo"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(icon))
            btn = WordWrapButton(label)
            self._reg_text(btn, "button", s_key)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent; color: {color};
                    border: none; padding: 4px 0; font-size: 12px; text-align: left;
                }}
                QPushButton:hover {{ color: {hover}; }}
            """)
            btn.clicked.connect(handler)
            row.addWidget(btn, 1)
            layout.addLayout(row)

        ver = QLabel(S("hint", "version"))

        self._reg_text(ver, "hint", "version")
        ver.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        layout.addWidget(ver)
        parent_layout.addWidget(group)

    # ---- 语言预设切换 ----

    def _build_language_preset_group(self, parent_layout):
        """构建语言风格预设切换区域。"""
        from PyQt6.QtWidgets import QComboBox

        from data.ui_strings import get_active_preset, get_preset_info, set_language_preset

        group = QGroupBox("语言风格 · 文案预设")
        group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {theme.panel_darkest};
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
        lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 12px; border: none; background: transparent;")
        row.addWidget(lbl)

        self._preset_combo = QComboBox()
        self._preset_combo.wheelEvent = lambda e: e.ignore()  # 禁用滚轮切换
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
                background-color: {theme.panel_darkest};
                color: {theme.text};
                border: 1px solid {theme.border};
                selection-background-color: {theme.cyber_yellow};
                selection-color: #000;
            }}
        """)

        # 填充预设列表
        presets = get_preset_info()
        active_id = get_active_preset()
        self._preset_data = {}  # display_name -> preset_id
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

        # 预设描述
        self._preset_desc = QLabel("")
        self._preset_desc.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; border: none; background: transparent; padding: 2px 0;")
        self._preset_desc.setWordWrap(True)
        self._update_preset_desc()

        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self._preset_desc)

        parent_layout.addWidget(group)

    def _update_preset_desc(self):
        """更新预设描述文字。"""
        from data.ui_strings import get_active_preset, get_preset_info
        active = get_active_preset()
        presets = get_preset_info()
        info = presets.get(active, {})
        desc = info.get("desc", "")
        self._preset_desc.setText(f"  {desc}")

    def _on_preset_changed(self, index: int):
        """切换语言预设。"""
        display = self._preset_combo.currentText()
        preset_id = self._preset_data.get(display)
        if not preset_id:
            return

        from data.ui_strings import set_language_preset, reload_strings
        if set_language_preset(preset_id):
            self._update_preset_desc()
            self._add_log('ok', f'语言风格已切换至: {display}')
            # 重建整个 UI 以刷新所有文字
            self._rebuild_ui_for_preset()
        else:
            self._add_log('error', f'语言风格切换失败: {preset_id}')

    def _rebuild_ui_for_preset(self):
        """切换预设后刷新所有文字。

        遍历 _text_registry 中注册的所有控件，用最新的 S() 文案重新 setText。
        注意：_text_registry 遍历会覆盖数据标签（statLabel/statValue），
        必须在最后调用 refresh_* 系列方法恢复真实数据。
        """
        # 刷新窗口标题
        self.setWindowTitle(S("window_title", "management_panel"))

        # 遍历注册表：所有在 _setup_ui 中通过 _reg_text() 注册的控件
        for widget, category, key in self._text_registry:
            try:
                # QGroupBox 需要 setTitle，但 QWidget.setTitle 不存在
                # 优先判断 setTitle（QGroupBox 特有），其次 setPlaceholderText，最后 setText
                if hasattr(widget, 'setTitle') and type(widget).__name__ == 'QGroupBox':
                    widget.setTitle(S(category, key))
                elif hasattr(widget, 'setPlaceholderText'):
                    widget.setPlaceholderText(S(category, key))
                elif hasattr(widget, 'setText'):
                    widget.setText(S(category, key))
            except Exception:
                pass  # 控件可能已被销毁

        # 刷新导航标签文字
        self._refresh_nav_labels()

        # 刷新功能开关按钮文字（名称 + 描述）
        self._refresh_toggle_button_texts()
        self._refresh_toggle_button_styles()

        # 刷新主题面板
        if self._theme_panel:
            self._theme_panel.refresh_inline_styles()

        # 刷新样式
        self.setStyleSheet(build_stylesheet())
        self._refresh_inline_styles()

        # ★ 恢复数据标签（上面的 _text_registry 遍历把它们覆盖成了占位符 "--"）
        self._update_panel.refresh_stats()
        self._update_panel.refresh_translation_stats()
        self.refresh_items_i18n_stats()
        self.refresh_price_stats()

    # ---- 日志面板 ----

    def _build_log_panel(self, outer_layout):
        log_panel = QWidget()
        log_panel.setStyleSheet(f"background-color: {theme.panel_darkest};")
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
        dl_progress.hide()  # 初始隐藏，下载时才显示
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
        log_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {theme.panel_deeper}; color: {theme.text};
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
                background-color: {theme.card_bg}; color: {theme.text_dim};
                border: 1px solid {theme.border}; border-radius: 4px;
                padding: 6px; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.btn_hover_bg}; color: {theme.text};
            }}
        """)
        layout.addWidget(btn_close_log)
        outer_layout.addWidget(log_panel)

        # 注入到 update_panel
        self._update_panel.set_log_panel_widgets(
            log_panel, log_area, step_icon, step_label,
            log_detail, dl_progress, btn_close_log)

        # 修正 btn_close_log 回调（此时 _update_panel 已存在）
        btn_close_log.clicked.disconnect()
        btn_close_log.clicked.connect(self._update_panel.hide_log_panel)

    # ============================================================
    # 主题面板交互
    # ============================================================

    def _toggle_theme_panel(self):
        self._theme_panel.toggle()

    def _on_theme_changed_internal(self):
        """主题变更后刷新 UI。"""
        self._rebuild_styles_and_swatches()
        self._refresh_all_inline_styles()
        self.theme_changed.emit()

    def _rebuild_styles_and_swatches(self):
        """刷新全局样式表、内联样式和色块。"""
        self.setStyleSheet(build_stylesheet())
        self._refresh_inline_styles()
        self._theme_panel.rebuild_swatches()

    def _refresh_inline_styles(self):
        """刷新所有颜色相关的内联样式。"""
        t = theme

        # === 导航栏 ===
        if hasattr(self, '_nav_list'):
            self._nav_list.setStyleSheet(f"""
                QListWidget {{
                    background-color: {t.panel_darkest};
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
                }}
                QListWidget::item:hover {{
                    background-color: {t.card_bg};
                    color: {t.text};
                }}
                QListWidget::item:selected {{
                    background-color: {t.cyber_yellow};
                    color: #000;
                    font-weight: bold;
                }}
            """)

        # === 滚动区域 & 主面板背景 ===
        if hasattr(self, '_left_scroll'):
            self._left_scroll.setStyleSheet(
                f"QScrollArea {{ border: none; background-color: {t.panel_bg}; }}")
            self._left_widget.setStyleSheet(f"background-color: {t.panel_bg};")

        # === 数据库状态区概要标签 ===
        if hasattr(self, '_status_trans_label'):
            self._status_trans_label.setStyleSheet(f"color: {t.text_dim}; font-size: 11px; padding: 2px 0;")
        if hasattr(self, '_status_items_label'):
            self._status_items_label.setStyleSheet(f"color: {t.text_dim}; font-size: 11px; padding: 2px 0;")

        # === 底部提示 ===
        if hasattr(self, '_bottom_tip'):
            self._bottom_tip.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")

        # === 日志标题 ===
        if hasattr(self, '_log_title_lbl'):
            self._log_title_lbl.setStyleSheet(f"color: {t.cyber_yellow}; font-size: 14px; font-weight: bold;")

        # === 热键编辑区 ===
        for btn in self._hotkey_buttons.values():
            btn.setStyleSheet(self._hotkey_btn_style())
        if hasattr(self, '_hotkey_tip'):
            self._hotkey_tip.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")

        # === 子面板样式 ===
        self._theme_panel.refresh_inline_styles()
        self._update_panel.refresh_inline_styles()

        # === 功能开关按钮 ===
        self._refresh_toggle_button_styles()

        # === 翻译进度条 ===
        if hasattr(self, '_trans_progress'):
            self._trans_progress.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid {t.border}; border-radius: 3px;
                    background-color: {t.card_bg}; text-align: center;
                    color: {t.cyber_yellow}; font-size: 11px; font-weight: bold;
                }}
                QProgressBar::chunk {{
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {t.progress_gradient_start},
                        stop:0.5 {t.progress_gradient_mid},
                        stop:1 {t.progress_gradient_end});
                    border-radius: 2px;
                }}
            """)

        # === 物品搜索组件 ===
        if hasattr(self, '_items_search_input'):
            self._items_search_input.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {t.panel_darkest};
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
                    background-color: {t.panel_darkest};
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

        # 重新应用当前导航高亮
        self._reapply_nav_highlight()

    def _refresh_all_inline_styles(self):
        """完整刷新（含数据重新查询）。"""
        self._update_panel.refresh_stats()
        self._update_panel.refresh_translation_stats()
        self.refresh_items_i18n_stats()
        self._refresh_hotkey_ui()

    def _reapply_nav_highlight(self):
        """主题/预设切换后重新应用当前导航项的高亮边框。"""
        if hasattr(self, '_nav_list') and hasattr(self, '_nav_items'):
            current_row = self._nav_list.currentRow()
            if 0 <= current_row < len(self._nav_items):
                nav_id = self._nav_items[current_row][0]
                group = self._nav_groups.get(nav_id)
                if group:
                    self._last_highlighted_group = None  # 先清空，确保重新高亮
                    self._highlight_group_border(group)
                    self._last_highlighted_group = group

    # ============================================================
    # 日志（转发给 update_panel）
    # ============================================================

    def _add_log(self, log_type: str, msg: str, source: str = ""):
        self._update_panel.add_log(log_type, msg, source)

    def add_log(self, log_type: str, msg: str, source: str = ""):
        """外部调用日志入口。"""
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
                fullscreen=DEFAULT_HOTKEYS['fullscreen'],
                panel=DEFAULT_HOTKEYS['panel']),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # ★ 关键修复：先设置内存中的值，再发射信号
        # 这样即使文件 I/O 失败，快捷键也能正确恢复
        self._hotkeys = dict(DEFAULT_HOTKEYS)
        self._refresh_hotkey_ui()
        self.hotkeys_changed.emit(self._hotkeys)

        # 保存到文件（异步思维：失败不影响核心功能）
        if save_hotkeys({}):
            self.add_log("ok", S("hotkey", "reset_done_msg"), "_on_reset_hotkeys")
            QMessageBox.information(self, S("hotkey", "reset_done_title"),
                S("hotkey", "reset_done_msg"))
        else:
            self.add_log("warn", "快捷键配置已恢复默认，但保存到文件失败", "_on_reset_hotkeys")
            QMessageBox.information(self, S("hotkey", "reset_done_title"),
                S("hotkey", "reset_done_msg") + "\n(配置已恢复，但文件保存失败)")

    def _on_reset_state(self):
        """重置程序状态：清除异常、重新注册热键、刷新 Overlay。"""
        self.add_log("info", S("log_msg", "reset_start"), "_on_reset_state")
        # 发射信号让 AppCore 执行重置（同步调用）
        self.reset_requested.emit()

    def _on_reload_hotkeys(self):
        """仅重新注册快捷键（不清除其他状态）。"""
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
    # 按钮换行支持
    # ============================================================

    def _apply_word_wrap_to_buttons(self):
        """给 QCheckBox 设置最小高度以保证布局稳定。

        WordWrapButton 自带换行支持，无需额外处理。
        QCheckBox 不支持换行，仅设最小高度防止布局被挤压。
        """
        min_btn_height = 40

        def _walk(widget):
            from PyQt6.QtWidgets import QCheckBox
            for child in widget.children():
                if isinstance(child, QCheckBox):
                    if child.minimumHeight() < min_btn_height:
                        child.setMinimumHeight(min_btn_height)
                _walk(child)

        _walk(self._left_widget)

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

    def closeEvent(self, event):
        if self._update_panel and self._update_panel.is_busy:
            event.ignore()
            return
        if self._update_panel and self._update_panel.log_panel_visible:
            self._update_panel.hide_log_panel()
        self.hide()
        event.ignore()
