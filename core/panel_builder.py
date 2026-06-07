"""
WARFRAME-RELIC UI 构建 Mixin

负责 _setup_ui 主入口及各功能区块的 _build_* 方法。
还包括物品搜索、价格拉取、遗物 tooltip 等业务逻辑。

作为 Mixin 注入 ManagementPanel，所有方法通过 self 访问控件。
"""

import os
import sys
from pathlib import Path
from core.bg_layer import BgImageWidget

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QMessageBox, QGroupBox,
    QApplication, QTextEdit, QLineEdit,
    QScrollArea, QListWidget, QListWidgetItem,
    QToolTip, QCheckBox,
)
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtWidgets import QGraphicsBlurEffect

from core.constants import theme, reload_theme, ThemeConfig
from core.constants import (CYBER_YELLOW, CYBER_CYAN, CYBER_MAGENTA,
                            COLOR_GOLD, COLOR_SILVER, COLOR_COPPER,
                            COLOR_VAULTED, COLOR_AVAILABLE)
from core.theme_proxy import (
    CYBER_CARD_BG, CYBER_TEXT_DIM, CYBER_RED, CYBER_GREEN, CYBER_ORANGE,
    COLOR_BLACK, COLOR_DARK_GRAY, COLOR_ENEMY, COLOR_PURPLE, MUTED_TEXT,
    SUBTLE_BORDER, LIGHT_TEXT,
)
from core.stylesheet import build_stylesheet
from core.hotkey_config import (
    load_hotkeys, save_hotkeys, validate_hotkey,
    DEFAULT_HOTKEYS, HOTKEY_LABELS,
    load_feature_toggles, save_feature_toggles,
    DEFAULT_FEATURE_TOGGLES, get_feature_toggle_labels,
    load_item_region, save_item_region, clear_item_region,
    set_active_region, get_active_region_key, load_all_item_regions,
)
from core.theme_fields import THEME_FIELDS
from core.theme_panel import ThemePanel
from core.update_panel import UpdatePanel, get_db_stats
from core.word_wrap_button import WordWrapButton
from core.hotkey_capture_button import HotkeyCaptureButton
from core.proxy_mirror_dialog import ProxyMirrorDialog
from data.game_terms import SOURCE_TYPE_CN, RARITY_CN
from data.ui_strings import S


class BlockWheelFilter(QtCore.QObject):
    """事件过滤器：阻止 QComboBox 响应滚轮事件（防止误触切换选项）。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True  # 吞掉滚轮事件
        return super().eventFilter(obj, event)


class CrosshairPicker(QWidget):
    """全屏十字线取点覆盖层。

    点击「设置位置」按钮后弹出，全屏半透明遮罩 + 红色十字准星。
    鼠标移动时十字线跟随，左键点击即捕获坐标并关闭。
    参考 RegionSelector._draw_crosshair 的绘制风格。
    """

    position_picked = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        from PyQt6.QtGui import QGuiApplication
        self._init_ui()

        # 鼠标追踪定时器（约 60fps）
        self._track_timer = QTimer(self)
        self._track_timer.timeout.connect(self._update_mouse_pos)
        self._mouse_pos = None

        # 计算所有屏幕总区域
        screens = QGuiApplication.screens()
        total_rect = screens[0].geometry() if screens else self.geometry()
        for s in screens[1:]:
            total_rect = total_rect.united(s.geometry())
        self._total_rect = total_rect

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.CursorShape.BlankCursor)  # 隐藏系统光标，用绘制的十字线代替

    def show_overlay(self):
        """显示覆盖层（覆盖所有屏幕）。"""
        self.setGeometry(self._total_rect)
        self._mouse_pos = None
        self._track_timer.start(16)  # ~60fps
        self.show()

    def _update_mouse_pos(self):
        """更新鼠标全局坐标并重绘十字线。"""
        from PyQt6.QtGui import QCursor
        self._mouse_pos = QCursor.pos()
        self.update()

    def paintEvent(self, event):
        """绘制半透明遮罩 + 红色十字准星。"""
        from PyQt6.QtGui import QColor, QFont, QPainter, QPen
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pw = self.width()
        ph = self.height()

        # 半透明黑色遮罩
        painter.fillRect(0, 0, pw, ph, QColor(0, 0, 0, 60))

        if not self._mouse_pos:
            return

        px = self._mouse_pos.x() - self._total_rect.x()
        py = self._mouse_pos.y() - self._total_rect.y()

        # 红色虚线十字线（贯穿全屏）
        pen_dash = QPen(QColor(220, 30, 30), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_dash)
        painter.drawLine(0, py, pw, py)
        painter.drawLine(px, 0, px, ph)

        # 红色实心小十字（中心）
        pen_solid = QPen(QColor(220, 30, 30), 2)
        painter.setPen(pen_solid)
        painter.drawLine(px - 16, py, px + 16, py)
        painter.drawLine(px, py - 16, px, py + 16)

        # 坐标文字（右下角）
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Microsoft YaHei", 11))
        coord_text = f"X: {self._mouse_pos.x()}  Y: {self._mouse_pos.y()}"
        fm = painter.fontMetrics()
        tw = fm.boundingRect(coord_text).width() + 16
        th = fm.height() + 8
        tx = px + 20
        ty = py + 20
        if tx + tw > pw:
            tx = px - tw - 20
        if ty + th > ph:
            ty = py - th - 20
        painter.fillRect(tx, ty, tw, th, QColor(0, 0, 0, 180))
        painter.drawText(tx + 8, ty + fm.ascent() + 4, coord_text)

    def mousePressEvent(self, event):
        """点击时捕获鼠标全局坐标，发射信号后关闭。"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.globalPosition().toPoint()
            self._track_timer.stop()
            self.position_picked.emit(pos.x(), pos.y())
            self.close()

    def keyPressEvent(self, event):
        """按 Esc 取消取点。"""
        if event.key() == Qt.Key.Key_Escape:
            self._track_timer.stop()
            self.close()


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
    item_region_select_requested = pyqtSignal(str)

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
                background-color: {theme.get_panel_bg_color(180)};
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
            ("toggles",     "nav", "nav_toggles",     "功能开关"),
            ("db_overview", "nav", "nav_status",      "数据总览"),
            ("items",       "nav", "nav_items",       "物品查询"),
            ("triggers",    "nav", "nav_triggers",    "辅助触发器"),
            ("prices",      "nav", "nav_prices",      "价格数据"),
            ("hotkeys",     "nav", "nav_hotkeys",     "快捷键"),
            ("theme",       "nav", "nav_theme",       "主题换肤"),
            ("reset",       "nav", "nav_reset",       "紧急重置"),
            ("preset",      "nav", "nav_preset",      "语言预设"),
            ("about",       "nav", "nav_about",       "关于作者"),
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
        self._build_data_overview_group(content_layout)
        self._build_item_index_group(content_layout)
        self._build_trigger_group(content_layout)
        self._build_price_group(content_layout)
        self._build_hotkey_group(content_layout)
        self._build_theme_group(content_layout)
        self._build_reset_group(content_layout)
        self._build_language_preset_group(content_layout)
        self._build_about_group(content_layout)

        # 退出按钮行
        exit_row = QHBoxLayout()
        self._btn_reload_ui = WordWrapButton(S("button", "reload_ui"))
        self._reg_text(self._btn_reload_ui, "button", "reload_ui")
        self._btn_reload_ui.setToolTip("完全重载面板 UI")
        self._btn_reload_ui.clicked.connect(self._on_reload_ui)
        exit_row.addWidget(self._btn_reload_ui)
        
        exit_row.addStretch()
        self._btn_exit = WordWrapButton(S("button", "exit"))
        self._reg_text(self._btn_exit, "button", "exit")
        self._btn_exit.clicked.connect(self._on_exit)
        exit_row.addWidget(self._btn_exit)
        content_layout.addLayout(exit_row)
        content_layout.addStretch()

        # 导航映射
        self._nav_groups = {}
        for nav_id, group in [
            ("toggles",     getattr(self, '_toggle_group', None)),
            ("db_overview", getattr(self, '_data_overview_group', None)),
            ("items",       getattr(self, '_items_group', None)),
            ("triggers",    getattr(self, '_trigger_group', None)),
            ("prices",      getattr(self, '_price_group', None)),
            ("hotkeys",     getattr(self, '_hotkey_group', None)),
            ("theme",       getattr(self, '_theme_group', None)),
            ("reset",       getattr(self, '_reset_group', None)),
            ("preset",      getattr(self, '_lang_preset_group', None)),
            ("about",       getattr(self, '_about_group', None)),
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
        group.setObjectName("normalGroup")
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

    def _build_data_overview_group(self, parent_layout):
        """数据总览 + 数据管理（合并区域）：宏观级数据库状态 + 操作按钮。"""
        group = QGroupBox(S("group", "data_overview"))
        self._data_overview_group = group
        group.setObjectName("normalGroup")
        self._reg_text(group, "group", "data_overview")
        layout = QVBoxLayout(group)

        # ── 宏观数据统计 ──
        self._stat_label_refs = {}
        stat_grid = [
            (S("stat_label", "relics_summary"), "relics_summary"),
            (S("stat_label", "relic_vault"), "relic_vault"),
            (S("stat_label", "items_summary"), "items_summary"),
            (S("stat_label", "db_size"), "db_size"),
            (S("stat_label", "last_update"), "last_update"),
        ]
        for label_text, data_key in stat_grid:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setObjectName("statLabel")
            lbl.setFixedWidth(80)
            val = QLabel(S("status", "placeholder"))
            val.setObjectName("statValue")
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            layout.addLayout(row)
            self._stat_label_refs[data_key] = val

        # ── 分隔线 ──
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.border};")
        layout.addWidget(sep)

        # ── 数据源信息 ──
        source_label = QLabel(""); source_label.setWordWrap(True)
        layout.addWidget(source_label)

        db_files_label = QLabel(""); db_files_label.setWordWrap(True)
        db_files_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px; padding: 4px 0;")
        layout.addWidget(db_files_label)

        # ── 主要操作按钮 ──
        row_fetch = QHBoxLayout()
        self._btn_update_base = WordWrapButton(S("management", "update_base_data"))
        self._btn_update_base.setStyleSheet(
            f"QPushButton {{ background-color: {theme.cyber_yellow}; color: {COLOR_BLACK}; "
            f"font-weight: bold; padding: 8px 16px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: {theme.cyber_cyan}; }}"
            f"QPushButton:disabled {{ background-color: {theme.text_dim}; color: {COLOR_DARK_GRAY}; }}"
        )
        self._btn_update_base.clicked.connect(self._on_update_base_data)
        self._btn_fetch_prices = WordWrapButton(S("management", "fetch_market_prices"))
        self._btn_fetch_prices.setStyleSheet(
            f"QPushButton {{ background-color: {theme.cyber_cyan}; color: {COLOR_BLACK}; "
            f"font-weight: bold; padding: 8px 16px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: {theme.cyber_yellow}; }}"
            f"QPushButton:disabled {{ background-color: {theme.text_dim}; color: {COLOR_DARK_GRAY}; }}"
        )
        self._btn_fetch_prices.clicked.connect(self._on_fetch_prices)
        self._btn_browse = WordWrapButton(S("button", "browse_file"))
        self._reg_text(self._btn_browse, "button", "browse_file")
        self._btn_browse.clicked.connect(self._update_panel.on_browse)
        row_fetch.addWidget(self._btn_update_base)
        row_fetch.addWidget(self._btn_fetch_prices)
        row_fetch.addWidget(self._btn_browse)
        layout.addLayout(row_fetch)

        # ── 辅助操作按钮 ──
        row1 = QHBoxLayout()
        self._btn_tutorial = WordWrapButton(S("button", "update_tutorial"))
        self._reg_text(self._btn_tutorial, "button", "update_tutorial")
        self._btn_tutorial.clicked.connect(self._update_panel.show_tutorial)
        self._btn_browse_db = WordWrapButton(S("button", "open_data_dir"))
        self._reg_text(self._btn_browse_db, "button", "open_data_dir")
        self._btn_browse_db.clicked.connect(self._open_data_dir)
        self._btn_proxy_config = WordWrapButton(S("management", "proxy_mirrors"))
        self._btn_proxy_config.setToolTip("配置 GitHub 代理镜像列表")
        self._btn_proxy_config.clicked.connect(self._on_open_proxy_config)
        self._btn_proxy_config.setStyleSheet(
            f"QPushButton {{ background-color: {theme.card_bg}; color: {theme.cyber_cyan}; "
            f"border: 1px solid {theme.border}; border-radius: 4px; padding: 6px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {theme.btn_hover_bg}; border-color: {theme.cyber_yellow}; }}"
        )
        row1.addWidget(self._btn_tutorial)
        row1.addWidget(self._btn_browse_db)
        row1.addWidget(self._btn_proxy_config)
        row1.addStretch()
        layout.addLayout(row1)

        # ── 后台数据中心按钮 ──
        row2 = QHBoxLayout()
        self._btn_data_center = WordWrapButton(S("button", "data_center"))
        self._reg_text(self._btn_data_center, "button", "data_center")
        self._btn_data_center.setToolTip("打开后台数据处理中心")
        self._btn_data_center.clicked.connect(self._on_open_data_center)
        self._btn_data_center.setStyleSheet(
            f"QPushButton {{ background-color: {theme.card_bg}; color: {theme.cyber_cyan}; "
            f"border: 1px solid {theme.border}; border-radius: 4px; padding: 6px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {theme.btn_hover_bg}; border-color: {theme.cyber_yellow}; }}"
        )
        row2.addWidget(self._btn_data_center)
        row2.addStretch()
        layout.addLayout(row2)

        # ── 下载源选择 ──
        source_label_row = QHBoxLayout()
        source_title = QLabel(S("management", "download_source"))
        source_title.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        source_label_row.addWidget(source_title)
        source_label_row.addStretch()
        layout.addLayout(source_label_row)

        hint = QLabel(S("hint", "data_source_db_center"))
        self._reg_text(hint, "hint", "data_source_db_center")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        parent_layout.addWidget(group)

        self._update_panel.set_stat_labels(self._stat_label_refs)
        self._update_panel.set_source_label(source_label, db_files_label=db_files_label)
        self._update_panel.set_buttons(
            btn_update_base=self._btn_update_base,
            btn_fetch_prices=self._btn_fetch_prices,
            btn_browse=self._btn_browse,
            btn_browse_db=self._btn_browse_db, btn_tutorial=self._btn_tutorial)

    # ============================================================
    # 全物品中英对照
    # ============================================================

    def _build_item_index_group(self, parent_layout):
        group = QGroupBox(S("group", "item_index"))
        self._items_group = group
        group.setObjectName("normalGroup")
        self._reg_text(group, "group", "item_index")
        layout = QVBoxLayout(group)

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
            from data.item_index import suggest_items
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
        # 匹配两种格式: "Axi A1 Relic" 或 "Axi A1 Intact/Exceptional/Flawless/Radiant"
        m = re.match(
            r'(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s+([A-Za-z0-9]+)(?:\s+(?:Relic|Intact|Exceptional|Flawless|Radiant))?',
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
            f"<div style='background:{CYBER_CARD_BG}; border-radius:8px; overflow:hidden;'>"
        )

        # ── 标题栏 ──
        parts.append(
            f"<div style='background:{CYBER_CARD_BG}; padding:8px 12px; "
            f"border-bottom:1px solid {SUBTLE_BORDER};'>"
            f"<span style='color:{CYBER_CYAN}; font-size:16px; font-weight:bold;'>"
            f"◈ {esc(item_name)}</span>"
        )
        if relic_info:
            vaulted = relic_info.get('vaulted', False)
            # vaulted=True → 已入库(红色), vaulted=False → 可获取(绿色)
            status_color = COLOR_VAULTED if vaulted else COLOR_AVAILABLE
            status_text = '已入库' if vaulted else '可获取'
            parts.append(
                f"<span style='color:{status_color}; font-size:13px; margin-left:8px;'>"
                f"[{status_text}]</span>"
            )
        parts.append("</div>")

        # ── 遗物内含物品 ──
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
                f"background:{COLOR_GOLD}; border-radius:2px; margin-right:6px; "
                f"vertical-align:middle;'></span>"
                f"<span style='color:{COLOR_GOLD}; font-size:14px; font-weight:bold; "
                f"vertical-align:middle;'>遗物内容</span>"
                f"<span style='color:{CYBER_TEXT_DIM}; font-size:12px; margin-left:4px;'>"
                f"({len(sorted_parts)}个部件)</span></div>"
            )
            for p in sorted_parts:
                ch = p.get('chance', 0)
                clr = chance_to_color.get(ch, COLOR_SILVER)
                rarity = p.get('rarity', '')
                rarity_cn = RARITY_CN.get(rarity, rarity)
                parts.append(
                    f"<div style='padding:2px 0 2px 20px; font-size:13px; white-space:nowrap;'>"
                    f"<span style='color:{clr};'>● {esc(p['name'])}</span>"
                    f"<span style='color:{CYBER_TEXT_DIM}; margin-left:6px; font-size:11px;'>"
                    f"{rarity_cn} ({ch:.1f}%)</span></div>"
                )
            parts.append(
                f"<div style='margin:4px 12px; border-bottom:1px solid rgba(100,100,150,40);'></div>"
            )

        # ── 掉落来源（只显示真正的遗物获取途径） ──
        if sources:
            import re as _re
            _RELIC_RE = _re.compile(
                r'^(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s+\w+\s+'
                r'(?:Relic(?:\s*\([^)]*\))?|Intact|Exceptional|Flawless|Radiant)$',
                _re.IGNORECASE,
            )

            # 过滤：只保留真正的遗物掉落来源，排除：
            #   - relics 类型（这是部件→遗物的反向映射，不是遗物的获取途径）
            #   - 精炼版本遗物自身（Axi S20 Relic (Exceptional) 等）
            #   - 遗物内含部件的其他来源链（Forma Blueprint 等）
            filtered = []
            for s in sources:
                st = s.get('source_type', '')
                loc = s.get('location', '')
                # 掉除 relics 类型（部件→遗物映射）
                if st == 'relics':
                    continue
                # 排除精炼版本遗物和遗物本身
                if _RELIC_RE.match(loc):
                    continue
                # 排除看起来像物品名而非地点的 location
                # （纯英文且不含常见地点特征词的，通常是污染数据）
                filtered.append(s)

            if not filtered:
                # 无有效掉落来源时不显示该区域
                pass
            else:
                by_type = {}
                for s in filtered:
                    st = s.get('source_type', '')
                    if st not in by_type:
                        by_type[st] = []
                    by_type[st].append(s)

                type_colors = {
                    'missionRewards': CYBER_CYAN,
                    'bountyRewards': CYBER_ORANGE, 'cetusBountyRewards': CYBER_ORANGE,
                    'solarisBountyRewards': CYBER_ORANGE, 'deimosRewards': CYBER_ORANGE,
                    'zarimanRewards': CYBER_ORANGE, 'entratiLabRewards': CYBER_ORANGE,
                    'hexRewards': CYBER_ORANGE, 'sortieRewards': CYBER_RED,
                    'keyRewards': CYBER_GREEN, 'transientRewards': COLOR_PURPLE,
                    'syndicates': CYBER_YELLOW,
                }

                total_sources = sum(len(v) for v in by_type.values())
                parts.append(
                    f"<div style='padding:4px 12px 2px 12px;'>"
                    f"<span style='display:inline-block; width:3px; height:12px; "
                    f"background:{CYBER_CYAN}; border-radius:2px; margin-right:6px; "
                    f"vertical-align:middle;'></span>"
                    f"<span style='color:{CYBER_CYAN}; font-size:14px; font-weight:bold; "
                    f"vertical-align:middle;'>掉落来源</span>"
                    f"<span style='color:{CYBER_TEXT_DIM}; font-size:12px; margin-left:4px;'>"
                    f"({total_sources} 条)</span></div>"
                )
                for st, items in by_type.items():
                    cn_st = SOURCE_TYPE_CN.get(st, st)
                    accent = type_colors.get(st, CYBER_TEXT_DIM)
                    parts.append(
                        f"<div style='margin-top:4px; margin-bottom:1px; padding-left:12px;'>"
                        f"<span style='color:{accent}; font-size:12px; font-weight:bold;'>"
                        f"{esc(cn_st)}</span>"
                        f"<span style='color:{CYBER_TEXT_DIM}; font-size:11px; margin-left:4px;'>"
                        f"({len(items)})</span></div>"
                    )
                    for item in items:
                        loc = item.get('location', '?')
                        loc_zh = item.get('location_zh', '')
                        display_name = loc_zh if loc_zh else loc
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
                                f"<span style='display:inline-block; background:{SUBTLE_BORDER}; "
                                f"color:{MUTED_TEXT}; font-size:11px; padding:1px 5px; "
                                f"border-radius:3px; margin-left:4px;'>轮次{rotation}</span>"
                            )
                        extra = ""
                        if chance_str and rot_tag:
                            extra = f" -- <span style='color:{MUTED_TEXT};'>{chance_str}</span> {rot_tag}"
                        elif chance_str:
                            extra = f" -- <span style='color:{MUTED_TEXT};'>{chance_str}</span>"
                        elif rot_tag:
                            extra = f" -- {rot_tag}"
                        parts.append(
                            f"<div style='padding:1px 0 1px 24px; font-size:12px; white-space:nowrap;'>"
                            f"<span style='color:{LIGHT_TEXT};'>{esc(display_name)}</span>"
                            f"{extra}</div>"
                        )

        parts.append("</div>")
        return "".join(parts)

    # ============================================================
    # 辅助触发器
    # ============================================================

    def _build_trigger_group(self, parent_layout):
        """构建辅助触发器配置区域：支持多触发器，每个含名称/触发输入/延迟/动作列表/开关按钮。"""
        from PyQt6.QtWidgets import QComboBox, QSpinBox

        from core.trigger_config import (
            load_triggers, save_triggers,
            create_blank_trigger, create_blank_action,
            TRIGGER_INPUT_TYPES, TRIGGER_INPUT_LABELS,
            MOUSE_BUTTONS, MOUSE_BUTTON_VALUES,
            ACTION_TYPES, ACTION_TYPE_VALUES,
            MOUSE_CLICK_BUTTONS, MOUSE_CLICK_VALUES,
            format_trigger_summary, get_action_placeholder,
        )

        group = QGroupBox("辅助触发器")
        self._trigger_group = group
        group.setObjectName("normalGroup")
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
        layout.setSpacing(10)

        # 提示文字
        hint = QLabel("检测到指定输入后，自动执行响应动作（按键/点击/移动鼠标）")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 动态触发器卡片容器 ──
        self._trigger_cards_container = QWidget()
        self._trigger_cards_container.setStyleSheet("background-color: transparent;")
        cards_layout = QVBoxLayout(self._trigger_cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(8)
        layout.addWidget(self._trigger_cards_container)

        # 存储每个卡片控件的引用（用于读取值和保存）
        self._trigger_card_widgets: list[dict] = []

        # 共享防抖计时器（所有卡片共用，避免多卡片时重复触发 save + reload）
        self._trigger_save_timer = QTimer()
        self._trigger_save_timer.setSingleShot(True)
        self._trigger_save_timer.setInterval(300)
        self._trigger_save_timer.timeout.connect(self._save_all_triggers)

        # 加载已有触发器并渲染卡片
        triggers_data = load_triggers()
        if not triggers_data:
            triggers_data = [create_blank_trigger()]

        for t in triggers_data:
            card = self._build_trigger_card(t, cards_layout)
            self._trigger_card_widgets.append(card)

        # ── 新增触发器按钮 ──
        btn_add = WordWrapButton("+ 新增触发器")
        btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.cyber_cyan};
                border: 1px dashed {theme.cyber_cyan};
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{3
                background-color: {theme.card_bg};
                border-style: solid;
            }}
        """)
        btn_add.clicked.connect(lambda: self._on_add_trigger_card(cards_layout))
        layout.addWidget(btn_add)

        parent_layout.addWidget(group)

    def _build_trigger_card(self, trigger_data: dict, parent_layout) -> dict:
        """构建单个触发器卡片，返回控件引用字典。

        Args:
            trigger_data: 触发器配置数据（dict）。
            parent_layout: 卡片要添加到的布局。

        Returns:
            包含所有子控件引用的字典。
        """
        from PyQt6.QtWidgets import QComboBox, QSpinBox

        from core.trigger_config import (
            create_blank_action,
            TRIGGER_INPUT_TYPES, MOUSE_BUTTONS, MOUSE_BUTTON_VALUES,
            ACTION_TYPES, ACTION_TYPE_VALUES,
            MOUSE_CLICK_BUTTONS, MOUSE_CLICK_VALUES,
            format_trigger_summary, get_action_placeholder,
        )

        card_frame = QFrame()
        card_frame.setObjectName("triggerCardFrame")
        card_frame.setStyleSheet(f"""
            QFrame#triggerCardFrame {{
                background-color: {theme.get_panel_bg_color(180)};
                border: 1px solid {theme.border};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)

        # ── 第1行：名称 ──
        name_row = QHBoxLayout()
        name_label = QLabel("名称:")
        name_label.setFixedWidth(36)
        name_label.setStyleSheet(f"color: {theme.text}; font-size: 12px;")
        name_input = QLineEdit()
        name_input.setText(trigger_data.get("name", ""))
        name_input.setPlaceholderText("如: 快速拾取")
        name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {theme.get_panel_bg_color(220)};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {theme.cyber_yellow}; }}
        """)
        name_row.addWidget(name_label)
        name_row.addWidget(name_input, 1)
        card_layout.addLayout(name_row)

        # ── 第2行：触发类型 + 按钮/按键选择 + 延迟 ──
        _h = 30                          # 与响应动作行统一行高
        input_row = QHBoxLayout()
        input_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 触发类型下拉框
        type_label = QLabel("触发:")
        type_label.setFixedWidth(36)
        type_label.setFixedHeight(_h)
        type_label.setStyleSheet(f"color: {theme.text}; font-size: 12px;")

        trigger_type_combo = QComboBox()
        trigger_type_combo.addItems(TRIGGER_INPUT_TYPES)
        ti = trigger_data.get("trigger_input", {})
        current_ti_type = ti.get("type", "mouse")
        idx = TRIGGER_INPUT_TYPES.index(current_ti_type) if current_ti_type in TRIGGER_INPUT_TYPES else 0
        trigger_type_combo.setCurrentIndex(idx)
        trigger_type_combo.setFixedHeight(_h)
        trigger_type_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.get_panel_bg_color(220)};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 12px;
                min-width: 80px;
            }}
            QComboBox:focus {{ border-color: {theme.cyber_yellow}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {theme.card_bg};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 2px;
                selection-background-color: {theme.cyber_yellow};
                selection-color: #000;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 4px 8px;
                min-height: 24px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {theme.btn_hover_bg};
            }}
            }}
        """)
        # 修复 Windows 下 QComboBox 弹窗脱离父窗口（重写 showPopup）
        _pf = (Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        _orig_show_tt = trigger_type_combo.showPopup
        def _fixed_show_tt():
            _orig_show_tt()
            try:
                w = trigger_type_combo.view().window()
                if w: w.setWindowFlags(_pf); w.show()
            except Exception: pass
        trigger_type_combo.showPopup = _fixed_show_tt
        trigger_type_combo.installEventFilter(BlockWheelFilter(self))

        # 鼠标按钮选择（默认可见）
        mouse_btn_combo = QComboBox()
        for label in MOUSE_BUTTONS:
            mouse_btn_combo.addItem(label[1])
        current_btn = ti.get("button", "right")
        bidx = MOUSE_BUTTON_VALUES.index(current_btn) if current_btn in MOUSE_BUTTON_VALUES else 1
        mouse_btn_combo.setCurrentIndex(bidx)
        mouse_btn_combo.setFixedHeight(_h)
        mouse_btn_combo.setStyleSheet(trigger_type_combo.styleSheet())
        # 修复 Windows 下 QComboBox 弹窗脱离父窗口（重写 showPopup）
        _orig_show_mb = mouse_btn_combo.showPopup
        def _fixed_show_mb():
            _orig_show_mb()
            try:
                w = mouse_btn_combo.view().window()
                if w: w.setWindowFlags(_pf); w.show()
            except Exception: pass
        mouse_btn_combo.showPopup = _fixed_show_mb
        mouse_btn_combo.installEventFilter(BlockWheelFilter(self))

        # 键盘按键输入（默认隐藏，使用 HotkeyCaptureButton 捕获实际按键）
        kb_key_input = HotkeyCaptureButton(hotkey=ti.get("key", ""))
        kb_key_input.setFixedHeight(_h)
        kb_key_input.setStyleSheet(name_input.styleSheet())
        # 根据触发类型设置初始显隐
        mouse_btn_combo.setVisible(current_ti_type != "keyboard")
        kb_key_input.setVisible(current_ti_type == "keyboard")

        # 延迟输入
        delay_label = QLabel("延迟:")
        delay_label.setFixedHeight(_h)
        delay_label.setStyleSheet(f"color: {theme.text}; font-size: 12px;")
        delay_spin = QSpinBox()
        delay_spin.setRange(0, 5000)
        delay_spin.setSingleStep(5)
        delay_spin.setValue(trigger_data.get("delay_ms", 10))
        delay_spin.setSuffix(" ms")
        delay_spin.setFixedWidth(100)
        delay_spin.setFixedHeight(_h)
        delay_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {theme.get_panel_bg_color(220)};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 12px;
            }}
            QSpinBox:focus {{ border-color: {theme.cyber_yellow}; }}
        """)

        # 切换触发类型时显示/隐藏对应控件
        def _on_trigger_type_changed(index):
            is_kb = TRIGGER_INPUT_TYPES[index] == "keyboard"
            mouse_btn_combo.setVisible(not is_kb)
            kb_key_input.setVisible(is_kb)

        trigger_type_combo.currentIndexChanged.connect(_on_trigger_type_changed)

        input_row.addWidget(type_label)
        input_row.addWidget(trigger_type_combo)
        input_row.addWidget(mouse_btn_combo)
        input_row.addWidget(kb_key_input)
        input_row.addStretch()
        input_row.addWidget(delay_label)
        input_row.addWidget(delay_spin)
        card_layout.addLayout(input_row)

        # ── 动作列表区域 ──
        actions_label = QLabel("响应动作:")
        actions_label.setStyleSheet(f"color: {theme.text}; font-size: 12px;")
        card_layout.addWidget(actions_label)

        actions_container = QWidget()
        actions_container.setStyleSheet("background-color: transparent;")
        actions_layout = QVBoxLayout(actions_container)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        card_layout.addWidget(actions_container)

        # 存储动作行控件引用
        action_widgets_list: list[dict] = []

        actions_data = trigger_data.get("actions", [])
        if not actions_data:
            actions_data = [create_blank_action()]

        for act in actions_data:
            aw = self._build_action_row(act, actions_layout)
            action_widgets_list.append(aw)

        # 添加动作按钮
        btn_add_action = WordWrapButton("+ 添加动作")
        btn_add_action.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.text_dim};
                border: 1px dashed {theme.border};
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {theme.cyber_cyan};
                border-color: {theme.cyber_cyan};
            }}
        """)

        def _make_add_action():
            blank = create_blank_action()
            aw = self._build_action_row(blank, actions_layout)
            action_widgets_list.append(aw)
            # 新增行的控件也要连接更新信号
            aw["key_value_input"].hotkey_changed.connect(_on_any_change)
            aw["click_value_combo"].currentIndexChanged.connect(_on_any_change)
            aw["move_value_input"].textChanged.connect(_on_any_change)
            aw["type_combo"].currentIndexChanged.connect(_on_any_change)
            btn_add_action.setParent(None)  # 从旧布局移除
            actions_layout.addWidget(btn_add_action)  # 重新添加到最后

        btn_add_action.clicked.connect(_make_add_action)
        actions_layout.addWidget(btn_add_action)

        # ── 开关按钮（样式同功能开关）──
        toggle_btn = WordWrapButton("")
        toggle_btn.setObjectName("triggerToggleBtn")
        toggle_btn.setCheckable(True)
        toggle_btn.setChecked(bool(trigger_data.get("enabled", False)))
        self._refresh_trigger_toggle_style(toggle_btn)
        toggle_btn.clicked.connect(
            lambda checked, btn=toggle_btn: self._on_trigger_toggle(btn, checked)
        )

        # 更新开关按钮文字
        self._update_trigger_toggle_text(toggle_btn, trigger_data)

        # ★ 将开关按钮添加到卡片布局
        card_layout.addWidget(toggle_btn)

        # ── 删除触发器按钮（放在开关下方）──
        del_row = QHBoxLayout()
        del_row.addStretch()
        btn_delete = WordWrapButton("✖ 删除此触发器")
        btn_delete.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.border};
                border: 1px solid {theme.border};
                border-radius: 3px;
                padding: 4px 16px;
                font-size: 11px;
                min-height: 0px; max-height: none;
            }}
            QPushButton:hover {{
                background-color: {theme.border};
                color: #fff;
            }}
        """)
        del_row.addWidget(btn_delete)
        card_layout.addLayout(del_row)

        # 当任何输入变化时更新开关摘要（使用共享防抖避免频繁 I/O）
        def _on_any_change():
            self._update_trigger_toggle_text_from_widgets(
                toggle_btn, name_input, trigger_type_combo,
                mouse_btn_combo, kb_key_input, delay_spin,
                action_widgets_list,
            )
            self._trigger_save_timer.start()  # 防抖：300ms 内再次变化则重置计时

        name_input.textChanged.connect(_on_any_change)
        trigger_type_combo.currentIndexChanged.connect(_on_any_change)
        mouse_btn_combo.currentIndexChanged.connect(_on_any_change)
        kb_key_input.hotkey_changed.connect(_on_any_change)
        delay_spin.valueChanged.connect(_on_any_change)

        # 响应动作行的控件值变化也要触发更新（按键捕获/鼠标点击/坐标输入）
        for aw in action_widgets_list:
            aw["key_value_input"].hotkey_changed.connect(_on_any_change)
            aw["click_value_combo"].currentIndexChanged.connect(_on_any_change)
            aw["move_value_input"].textChanged.connect(_on_any_change)
            aw["type_combo"].currentIndexChanged.connect(_on_any_change)

        btn_delete.clicked.connect(lambda: self._on_delete_trigger_card(card_frame))

        parent_layout.addWidget(card_frame)

        return {
            "frame": card_frame,
            "name_input": name_input,
            "trigger_type_combo": trigger_type_combo,
            "mouse_btn_combo": mouse_btn_combo,
            "kb_key_input": kb_key_input,
            "delay_spin": delay_spin,
            "toggle_btn": toggle_btn,
            "action_widgets": action_widgets_list,
            "btn_delete": btn_delete,
            "actions_container": actions_container,
        }

    def _build_action_row(self, action_data: dict, parent_layout) -> dict:
        """构建单个动作行（类型选择 + 值输入 + 删除）。

        Args:
            action_data: 动作配置数据。
            parent_layout: 行要添加到的布局。

        Returns:
            控件引用字典。
        """
        from PyQt6.QtWidgets import QComboBox

        from core.trigger_config import (
            ACTION_TYPES, ACTION_TYPE_VALUES,
            MOUSE_CLICK_BUTTONS, MOUSE_CLICK_VALUES,
            get_action_placeholder,
        )
        from core.hotkey_capture_button import HotkeyCaptureButton

        # ── 统一行高 ──
        _h = 30
        _w_type = 96
        _bg = theme.get_panel_bg_color(230)
        _bdr = theme.border
        _txt = theme.text

        _ss = f"""
            background-color: {_bg}; color: {_txt};
            border: 1px solid {_bdr}; border-radius: 4px;
            padding: 0px 8px; font-size: 12px;
        """
        _ss_focus = f"border-color: {theme.cyber_yellow};"
        _ss_popup = f"""
            QComboBox QAbstractItemView {{
                background: {theme.card_bg}; color: {_txt};
                border: 1px solid {_bdr}; border-radius: 4px; padding: 2px;
                selection-background-color: {theme.cyber_yellow}; selection-color: #000;
            }}
            QComboBox QAbstractItemView::item {{ padding: 4px 10px; min-height: 24px; }}
            QComboBox QAbstractItemView::item:hover {{ background-color: {theme.btn_hover_bg}; }}
        """

        def _fix_combo_popup(combo: QComboBox):
            """修复 Windows 下 QComboBox 弹窗脱离父窗口的问题。
            重写 showPopup()，在弹窗打开前强制设置 Popup 标志。
            """
            _orig_show = combo.showPopup

            def _fixed_showPopup():
                _orig_show()
                # 弹窗已创建，立即修正窗口标志
                view = combo.view()
                if view:
                    w = view.window()
                    if w:
                        try:
                            flags = (Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                                     Qt.WindowType.NoDropShadowWindowHint)
                            w.setWindowFlags(flags)
                            w.show()
                        except Exception:
                            pass

            combo.showPopup = _fixed_showPopup
        # 删除按钮样式（必须显式覆盖全局 QPushButton 的 min-height/padding）
        _ss_del = f"""
            QPushButton {{
                background: transparent; color: {theme.border};
                border: 1px solid {theme.border}; border-radius: 4px;
                font-size: 12px; font-weight: bold;
                padding: 0px; min-height: {_h}px; max-height: {_h}px;
            }}
            QPushButton:hover {{ background: {theme.border}; color: #fff; }}
        """

        # ── 行容器（不设固定高度，避免硬裁切导致子控件边框被切）──
        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # ---- 类型下拉框 ----
        type_combo = QComboBox()
        for at in ACTION_TYPES:
            type_combo.addItem(at[1])
        current_type = action_data.get("type", "key")
        aidx = ACTION_TYPE_VALUES.index(current_type) if current_type in ACTION_TYPE_VALUES else 0
        type_combo.setCurrentIndex(aidx)
        type_combo.setFixedSize(_w_type, _h)
        type_combo.setStyleSheet(f"QComboBox {{ {_ss} }} QComboBox:focus {{{_ss_focus}}} "
                                 f"QComboBox::drop-down {{ border: none; width: 18px; }} {_ss_popup}")
        _fix_combo_popup(type_combo)
        type_combo.installEventFilter(BlockWheelFilter(self))

        # ---- 值控件容器（用 replaceWidget 而非 hide/show 避免 Windows Qt 弹窗脱离父窗口的 bug）----
        value_container = QWidget()
        value_container_layout = QHBoxLayout(value_container)
        value_container_layout.setContentsMargins(0, 0, 0, 0)
        value_container_layout.setSpacing(0)
        value_container.setLayout(value_container_layout)

        # ---- 值控件 ① 按键捕获 ----
        key_value_input = HotkeyCaptureButton(hotkey=action_data.get("value", ""))
        key_value_input.setFixedHeight(_h)
        key_value_input.setStyleSheet(f"QLineEdit {{ {_ss} }} QLineEdit:focus {{{_ss_focus}}}")

        # ---- 值控件 ② 鼠标点击下拉 ----
        click_value_combo = QComboBox()
        for mc in MOUSE_CLICK_BUTTONS:
            click_value_combo.addItem(mc[1])
        cidx = MOUSE_CLICK_VALUES.index(action_data.get("value", "")) \
            if action_data.get("value", "") in MOUSE_CLICK_VALUES else 0
        click_value_combo.setCurrentIndex(cidx)
        click_value_combo.setFixedHeight(_h)
        click_value_combo.setStyleSheet(f"QComboBox {{ {_ss} }} QComboBox:focus {{{_ss_focus}}} "
                                       f"QComboBox::drop-down {{ border: none; width: 18px; }} {_ss_popup}")
        _fix_combo_popup(click_value_combo)
        click_value_combo.installEventFilter(BlockWheelFilter(self))

        # ---- 值控件 ③ 鼠标移动坐标（隐藏输入框 + 设置位置按钮）----
        move_value_input = QLineEdit()
        move_value_input.setText(action_data.get("value", ""))
        move_value_input.setVisible(False)  # 隐藏，仅用于存储坐标值

        def _update_button_text(btn, val):
            btn.setText(val if val else "设置位置")

        move_pos_button = QPushButton()
        _update_button_text(move_pos_button, action_data.get("value", ""))
        move_pos_button.setFixedHeight(_h)
        move_pos_button.setCursor(Qt.CursorShape.PointingHandCursor)
        move_pos_button.setStyleSheet(
            f"QPushButton {{ {_ss} min-height: {_h}px; max-height: {_h}px; }}"
            f" QPushButton:hover {{ {_ss_focus} }}"
        )

        def _on_pick_position():
            # 懒创建 CrosshairPicker（每个 ManagementPanel 实例一个）
            if not hasattr(self, "_crosshair_picker"):
                self._crosshair_picker = CrosshairPicker()
            # 每次打开前重新绑定信号，确保更新的是当前行的控件
            try:
                self._crosshair_picker.position_picked.disconnect()
            except Exception:
                pass
            self._crosshair_picker.position_picked.connect(
                lambda x, y: _on_position_picked(x, y)
            )
            self._crosshair_picker.show_overlay()

        def _on_position_picked(x, y):
            val = f"{x}, {y}"
            move_value_input.setText(val)
            _update_button_text(move_pos_button, val)

        move_pos_button.clicked.connect(_on_pick_position)

        # ---- 显隐切换：用 replaceWidget 替代 hide/show，避免 Windows Qt 弹窗脱离父窗口 ----
        _value_widgets = {"key": key_value_input, "mouse_click": click_value_combo, "mouse_move": move_pos_button}

        def _on_action_type_changed(index):
            atype = ACTION_TYPE_VALUES[index]
            current = _value_widgets[atype]
            # 容器中已有控件则替换，否则直接添加
            if value_container_layout.count() > 0:
                old = value_container_layout.itemAt(0).widget()
                if old is not current:
                    value_container_layout.removeWidget(old)
                    old.setParent(None)
                    value_container_layout.addWidget(current, 1)
            else:
                value_container_layout.addWidget(current, 1)

        type_combo.currentIndexChanged.connect(_on_action_type_changed)
        _on_action_type_changed(aidx)

        # ---- 删除按钮 ----
        btn_del_act = QPushButton("\u2715")
        btn_del_act.setFixedSize(_h, _h)
        btn_del_act.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del_act.setStyleSheet(_ss_del)          # 复用统一样式变量
        btn_del_act.clicked.connect(lambda: self._on_delete_action_row(row_widget))

        # ---- 布局：类型 | 值容器(stretch) | 删除按钮 ──
        row_layout.addWidget(type_combo)
        row_layout.addWidget(value_container, 1)
        row_layout.addWidget(btn_del_act)

        parent_layout.addWidget(row_widget)

        return {
            "widget": row_widget,
            "type_combo": type_combo,
            "key_value_input": key_value_input,
            "click_value_combo": click_value_combo,
            "move_value_input": move_value_input,
        }

    # ============================================================
    # 触发器交互回调
    # ============================================================

    def _on_add_trigger_card(self, parent_layout):
        """新增一个空白触发器卡片。"""
        from core.trigger_config import create_blank_trigger
        blank = create_blank_trigger()
        card = self._build_trigger_card(blank, parent_layout)
        self._trigger_card_widgets.append(card)
        self._save_all_triggers()

    def _on_delete_trigger_card(self, card_frame: QFrame):
        """删除一个触发器卡片。"""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认删除",
            "确定删除此触发器？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 找到对应的 card_widgets 并移除
        for i, cw in enumerate(self._trigger_card_widgets):
            if cw["frame"] is card_frame:
                self._trigger_card_widgets.pop(i)
                break

        card_frame.setParent(None)
        card_frame.deleteLater()
        self._save_all_triggers()

    def _on_delete_action_row(self, row_widget: QWidget):
        """删除一个动作行。"""
        # 先从所属卡片的 action_widgets 中取出引用，用于断开信号
        aw_ref = None
        for card in self._trigger_card_widgets:
            for j, aw in enumerate(card.get("action_widgets", [])):
                if aw["widget"] is row_widget:
                    aw_ref = card["action_widgets"].pop(j)
                    break

        # 断开所有信号连接，防止析构过程中回调
        if aw_ref:
            try:
                aw_ref["type_combo"].currentIndexChanged.disconnect()
                aw_ref["key_value_input"].hotkey_changed.disconnect()
                aw_ref["click_value_combo"].currentIndexChanged.disconnect()
                aw_ref["move_value_input"].textChanged.disconnect()
            except Exception:
                pass

        row_widget.setParent(None)
        row_widget.deleteLater()
        self._save_all_triggers()

    def _on_trigger_toggle(self, toggle_btn, checked: bool):
        """触发器开关切换回调。"""
        toggle_btn.setChecked(checked)
        self._refresh_trigger_toggle_style(toggle_btn)
        self._save_all_triggers()

    def _refresh_trigger_toggle_style(self, btn):
        """刷新单个触发器开关按钮样式（亮=开，暗=关）。与功能开关风格一致）。"""
        is_on = btn.isChecked()
        if is_on:
            btn.setStyleSheet(f"""
                QPushButton#triggerToggleBtn {{
                    background-color: {theme.get_panel_bg_color(200)};
                    color: {theme.cyber_cyan};
                    border: 2px solid {theme.cyber_yellow};
                    border-radius: 6px;
                    padding: 10px 10px;
                    font-size: 12px;
                    text-align: center;
                    min-height: 56px;
                }}
                QPushButton#triggerToggleBtn:hover {{
                    background-color: {theme.get_panel_bg_color(220)};
                    border-color: {theme.cyber_yellow};
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton#triggerToggleBtn {{
                    background-color: transparent;
                    color: {theme.text_dim};
                    border: 2px solid {theme.border};
                    border-radius: 6px;
                    padding: 10px 10px;
                    font-size: 12px;
                    text-align: center;
                    min-height: 56px;
                }}
                QPushButton#triggerToggleBtn:hover {{
                    border-color: {theme.cyber_cyan};
                    color: {theme.text};
                }}
            """)

    def _update_trigger_toggle_text(self, toggle_btn, trigger_data: dict):
        """根据触发器数据更新开关按钮的显示文字。"""
        from core.trigger_config import format_trigger_summary
        summary = format_trigger_summary(trigger_data)
        name = trigger_data.get("name", "未命名") or "未命名"
        status_icon = "●" if trigger_data.get("enabled") else "○"
        toggle_btn.setText(f"{status_icon}  {name}\n{summary}")

    def _update_trigger_toggle_text_from_widgets(
        self, toggle_btn, name_input, trigger_type_combo,
        mouse_btn_combo, kb_key_input, delay_spin, action_widgets_list,
    ):
        """从 UI 控件读取当前值并更新开关按钮摘要文字。"""
        from core.trigger_config import (
            TRIGGER_INPUT_TYPES, MOUSE_BUTTON_VALUES,
            ACTION_TYPE_VALUES, MOUSE_CLICK_VALUES,
            format_action_summary,
        )

        name = name_input.text().strip() or "未命名"
        is_on = toggle_btn.isChecked()
        status_icon = "●" if is_on else "○"

        # 构建触发描述
        ti_idx = trigger_type_combo.currentIndex()
        ti_type = TRIGGER_INPUT_TYPES[ti_idx] if ti_idx < len(TRIGGER_INPUT_TYPES) else "mouse"
        if ti_type == "mouse":
            bidx = mouse_btn_combo.currentIndex()
            btn = MOUSE_BUTTON_VALUES[bidx] if bidx < len(MOUSE_BUTTON_VALUES) else "right"
            trigger_desc = {"left": "左键", "right": "右键", "middle": "中键",
                           "x1": "侧键1", "x2": "侧键2"}.get(btn, btn)
        else:
            trigger_desc = f"键:{kb_key_input.hotkey() or '?'}"

        delay = delay_spin.value()

        # 取第一个动作摘要
        action_desc = "(无动作)"
        if action_widgets_list:
            aw = action_widgets_list[0]
            aidx = aw["type_combo"].currentIndex()
            atype = ACTION_TYPE_VALUES[aidx] if aidx < len(ACTION_TYPE_VALUES) else "key"
            val = ""
            if atype == "key":
                val = aw["key_value_input"].hotkey()
            elif atype == "mouse_click":
                cidx = aw["click_value_combo"].currentIndex()
                val = MOUSE_CLICK_VALUES[cidx] if cidx < len(MOUSE_CLICK_VALUES) else ""
            elif atype == "mouse_move":
                val = aw["move_value_input"].text().strip()
            action_desc = format_action_summary({"type": atype, "value": val})

        if len(action_widgets_list) > 1:
            action_desc += f" +{len(action_widgets_list) - 1}"

        toggle_btn.setText(f"{status_icon}  {name}\n{trigger_desc} → {delay}ms → {action_desc}")

    def _save_all_triggers(self):
        """从所有卡片控件读取当前值，保存到文件并通知 TriggerManager 重载。"""
        from core.trigger_config import (
            TRIGGER_INPUT_TYPES, MOUSE_BUTTON_VALUES,
            ACTION_TYPE_VALUES, MOUSE_CLICK_VALUES,
            save_triggers,
        )

        triggers = []
        for cw in self._trigger_card_widgets:
            name = cw["name_input"].text().strip()

            # 触发输入
            ti_idx = cw["trigger_type_combo"].currentIndex()
            ti_type = TRIGGER_INPUT_TYPES[ti_idx] if ti_idx < len(TRIGGER_INPUT_TYPES) else "mouse"
            trigger_input = {
                "type": ti_type,
                "button": "",
                "key": "",
            }
            if ti_type == "mouse":
                bidx = cw["mouse_btn_combo"].currentIndex()
                trigger_input["button"] = MOUSE_BUTTON_VALUES[bidx] if bidx < len(MOUSE_BUTTON_VALUES) else "right"
            else:
                trigger_input["key"] = cw["kb_key_input"].hotkey()

            # 动作列表
            actions = []
            for aw in cw.get("action_widgets", []):
                aidx = aw["type_combo"].currentIndex()
                atype = ACTION_TYPE_VALUES[aidx] if aidx < len(ACTION_TYPE_VALUES) else "key"
                value = ""
                if atype == "key":
                    value = aw["key_value_input"].hotkey()
                elif atype == "mouse_click":
                    cidx = aw["click_value_combo"].currentIndex()
                    value = MOUSE_CLICK_VALUES[cidx] if cidx < len(MOUSE_CLICK_VALUES) else ""
                elif atype == "mouse_move":
                    value = aw["move_value_input"].text().strip()
                actions.append({
                    "type": atype,
                    "value": value,
                })

            triggers.append({
                "name": name,
                "enabled": cw["toggle_btn"].isChecked(),
                "trigger_input": trigger_input,
                "delay_ms": cw["delay_spin"].value(),
                "actions": actions,
            })

        if save_triggers(triggers):
            # 通知 TriggerManager 热重载
            if hasattr(self, '_trigger_manager') and self._trigger_manager:
                self._trigger_manager.reload(triggers)

    # ============================================================
    # 价格数据库
    # ============================================================

    def _build_price_group(self, parent_layout):
        group = QGroupBox(S("group", "wm_prices"))
        self._price_group = group
        group.setObjectName("normalGroup")
        self._reg_text(group, "group", "wm_prices")
        layout = QVBoxLayout(group)

        # ── 区域标题 + 选中提示 ──
        region_title = QLabel("📐 物品截图区域")
        region_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 12px; font-weight: bold;")
        layout.addWidget(region_title)

        # 当前选中指示
        self._price_active_label = QLabel("")
        self._price_active_label.setStyleSheet(f"color: {theme.cyber_cyan}; font-size: 11px; padding: 2px 0;")
        self._price_active_label.setWordWrap(True)
        layout.addWidget(self._price_active_label)

        # ── 三个区域槽位 ──
        self._slot_status_labels = {}

        region_names = {"1": "区域 1", "2": "区域 2", "3": "区域 3"}
        for slot in ("1", "2", "3"):
            slot_frame = QFrame()
            slot_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme.get_panel_bg_color(120)};
                    border: 1px solid {theme.border};
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
            slot_layout = QHBoxLayout(slot_frame)
            slot_layout.setContentsMargins(8, 4, 8, 4)
            slot_layout.setSpacing(6)

            # 选中单选按钮
            radio = QPushButton("●")
            radio.setCheckable(True)
            radio.setFixedSize(22, 22)
            radio.setToolTip(f"选择{region_names[slot]}作为当前使用区域")
            radio.setProperty("_slot", slot)
            radio.clicked.connect(lambda checked, s=slot: self._on_select_region_slot(s))
            radio.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {theme.text_dim};
                    border: 1px solid {theme.border}; border-radius: 11px;
                    font-size: 12px; padding: 0px;
                }}
                QPushButton:hover {{ border-color: {theme.cyber_yellow}; color: {theme.cyber_yellow}; }}
                QPushButton:checked {{ background: {theme.cyber_yellow}; color: #000; border-color: {theme.cyber_yellow}; }}
            """)
            slot_layout.addWidget(radio)

            # 区域名称标签
            name_label = QLabel(region_names[slot])
            name_label.setStyleSheet(f"color: {theme.text}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
            name_label.setFixedWidth(45)
            slot_layout.addWidget(name_label)

            # 状态标签
            status_label = QLabel(S("management", "price_not_set"))
            status_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; background: transparent; border: none;")
            status_label.setWordWrap(True)
            self._slot_status_labels[slot] = status_label
            slot_layout.addWidget(status_label, 1)

            # 设置按钮
            set_btn = WordWrapButton(S("management", "price_set_hint"))
            set_btn.setFixedWidth(48)
            set_btn.setFixedHeight(26)
            set_btn.setToolTip(f"框选设置{region_names[slot]}")
            set_btn.clicked.connect(lambda checked, s=slot: self._on_set_slot_region(s))
            slot_layout.addWidget(set_btn)

            # 清除按钮
            clear_btn = WordWrapButton(S("management", "price_clear_hint"))
            clear_btn.setFixedWidth(48)
            clear_btn.setFixedHeight(26)
            clear_btn.setToolTip(f"清除{region_names[slot]}")
            clear_btn.clicked.connect(lambda checked, s=slot: self._on_clear_slot_region(s))
            slot_layout.addWidget(clear_btn)

            layout.addWidget(slot_frame)

        # 保存 radio 引用
        self._slot_radios = {}
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, QFrame):
                for child in w.children():
                    if isinstance(child, QPushButton) and child.isCheckable():
                        slot = child.property("_slot")
                        if slot:
                            self._slot_radios[slot] = child

        # ── 市场价格查询按钮 ──
        btn_row = QHBoxLayout()
        self._btn_open_market_query = WordWrapButton(S("button", "open_market_query"))
        self._reg_text(self._btn_open_market_query, "button", "open_market_query")
        self._btn_open_market_query
        self._btn_open_market_query.clicked.connect(self._open_market_query)
        btn_row.addWidget(self._btn_open_market_query)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 提示
        hint = QLabel(S("hint", "data_source_wm"))
        self._reg_text(hint, "hint", "data_source_wm")
        hint.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; padding: 2px 0;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        parent_layout.addWidget(group)
        self._refresh_item_region_status()

    def refresh_price_stats(self):
        """刷新价格区域状态。"""
        self._refresh_item_region_status()

    def _refresh_item_region_status(self):
        """刷新三个区域槽位的状态显示。"""
        cfg = load_all_item_regions()
        active = cfg.get("active", "1")

        for slot in ("1", "2", "3"):
            region = cfg["regions"].get(slot)
            if region and all(k in region for k in ('x', 'y', 'w', 'h')):
                text = f"x={region['x']}, y={region['y']}, {region['w']}x{region['h']}"
                color = theme.cyber_green
            else:
                text = "未设置"
                color = theme.text_dim

            if slot in self._slot_status_labels:
                self._slot_status_labels[slot].setText(text)
                self._slot_status_labels[slot].setStyleSheet(
                    f"color: {color}; font-size: 10px; background: transparent; border: none;")

            if slot in self._slot_radios:
                self._slot_radios[slot].setChecked(slot == active)

        # 更新选中提示
        active_region = cfg["regions"].get(active)
        if active_region and all(k in active_region for k in ('x', 'y', 'w', 'h')):
            self._price_active_label.setText(
                f"当前使用: 区域 {active} (x={active_region['x']}, y={active_region['y']}, "
                f"{active_region['w']}x{active_region['h']}) 将横向4等分")
            self._price_active_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 11px;")
        else:
            self._price_active_label.setText(S("management", "price_no_region"))
            self._price_active_label.setStyleSheet(f"color: {theme.cyber_orange}; font-size: 11px;")

    def _on_select_region_slot(self, slot: str):
        """选择当前使用的区域槽位。"""
        if set_active_region(slot):
            self._refresh_item_region_status()
            self._add_log('ok', f'已切换到区域 {slot}')

    def _on_set_slot_region(self, slot: str):
        """请求框选设置指定槽位的物品区域。"""
        self._pending_region_slot = slot
        self.showMinimized()
        self._request_item_region_selection(slot)

    def _request_item_region_selection(self, slot: str = "1"):
        """发射信号请求主程序启动框选。"""
        if hasattr(self, 'item_region_select_requested'):
            self.item_region_select_requested.emit(slot)
        else:
            from PyQt6.QtWidgets import QMessageBox
            self.showNormal()
            QMessageBox.information(self, S("management", "hint"),
                "请先在 Warframe 游戏中打开物品选择界面，\n"
                "然后按 Ctrl+G 框选包含4个物品卡片的横向区域。\n\n"
                "区域设置功能需要通过主程序框选完成。")

    def _on_clear_slot_region(self, slot: str):
        """清除指定槽位的物品区域。"""
        if clear_item_region(slot):
            self._refresh_item_region_status()
            self._add_log('ok', f'区域 {slot} 已清除')
        else:
            self._add_log('error', f'清除区域 {slot} 失败')

    def _on_open_proxy_config(self):
        """打开代理镜像配置对话框。"""
        dlg = ProxyMirrorDialog(self)
        dlg.exec()

    def _on_update_base_data(self):
        """更新基础数据（快速）。

        流水线: WFCD → warframe.db (统一数据库)
        不含市场价格拉取（耗时较长）。
        """
        reply = QMessageBox.question(
            self, S("management", "update_base_data"),
            S.format("management", "update_base_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._pipeline_mode = "base"
        self._btn_update_base.setEnabled(False)
        self._btn_fetch_prices.setEnabled(False)
        self._add_log('info', '========== 更新基础数据 ==========')
        self._add_log('info', '流水线: WFCD → warframe.db (统一数据库)')

        self._launch_pipeline(skip_prices=True)

    def _on_fetch_prices(self):
        """拉取 warframe.market 市场价格（耗时较长）。

        仅拉取市场价格，不更新其他数据库。
        """
        reply = QMessageBox.question(
            self, S("management", "fetch_market_prices"),
            S.format("management", "fetch_prices_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._pipeline_mode = "prices"
        self._btn_update_base.setEnabled(False)
        self._btn_fetch_prices.setEnabled(False)
        self._add_log('info', '========== 拉取市场价格 ==========')
        self._add_log('info', '数据源: warframe.market API v2')

        self._launch_pipeline(prices_only=True)

    def _launch_pipeline(self, skip_prices=False, prices_only=False):
        """启动数据流水线后台线程。"""
        from data.data_pipeline import DataPipelineWorker
        import threading

        # 构建完成前关闭所有缓存的数据库连接，释放文件锁
        from data.db_connections import close_all_db_connections

        self._pipeline_worker = DataPipelineWorker(
            skip_prices=skip_prices, prices_only=prices_only,
            close_connections_fn=close_all_db_connections)
        self._pipeline_worker.step_changed.connect(self._on_pipeline_step)
        self._pipeline_worker.log.connect(self._on_pipeline_log)
        self._pipeline_worker.progress_pct.connect(self._on_pipeline_progress)
        self._pipeline_worker.progress_detail.connect(self._on_pipeline_detail)
        self._pipeline_worker.repo_progress.connect(self._on_pipeline_repo_progress)
        self._pipeline_worker.finished.connect(self._on_pipeline_finished)
        self._pipeline_worker.error.connect(self._on_pipeline_error)
        # 显示总进度条
        self._update_panel._dl_progress.setValue(0)
        self._update_panel._dl_progress.show()
        # 初始化分进度条（3 个仓库）
        self._init_sub_progress_bars(["遗物/物品", "掉落数据", "翻译数据"])
        threading.Thread(target=self._pipeline_worker.run, daemon=True).start()

    def _init_sub_progress_bars(self, keys: list[str]):
        """初始化分进度条（动态创建）。"""
        # 清除旧的
        for key, (lbl, bar, status_lbl) in self._sub_progress_bars.items():
            lbl.setParent(None); bar.setParent(None); status_lbl.setParent(None)
        # 清空布局
        while self._sub_progress_layout.count():
            item = self._sub_progress_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        self._sub_progress_bars.clear()

        for key in keys:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(key)
            lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px; background: transparent;")
            lbl.setFixedWidth(60)
            row.addWidget(lbl)
            bar = QProgressBar()
            bar.setRange(0, 100); bar.setValue(0)
            bar.setFixedHeight(14)
            bar.setFormat("")
            bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid {theme.border}; border-radius: 3px;
                    background-color: {theme.card_bg};
                    text-align: center; color: {theme.cyber_cyan};
                    font-size: 9px;
                }}
                QProgressBar::chunk {{
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {theme.progress_gradient_start},
                        stop:0.5 {theme.progress_gradient_mid},
                        stop:1 {theme.progress_gradient_end});
                    border-radius: 2px;
                }}
            """)
            row.addWidget(bar, 1)
            status_lbl = QLabel("")
            status_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 9px; background: transparent;")
            status_lbl.setFixedWidth(100)
            row.addWidget(status_lbl)
            self._sub_progress_layout.addLayout(row)
            self._sub_progress_bars[key] = (lbl, bar, status_lbl)
        self._sub_progress_container.show()

    def _on_pipeline_step(self, step, desc):
        self._add_log('info', f'[步骤 {step}] {desc}')

    def _on_pipeline_log(self, level, msg):
        self._add_log(level, msg)

    def _on_pipeline_progress(self, pct):
        self._update_panel._dl_progress.setValue(pct)
        QApplication.processEvents()

    def _on_pipeline_detail(self, stage, cur, total):
        if total > 0:
            self._update_panel._log_detail.setText(f"{stage}: {cur}/{total}")

    def _on_pipeline_repo_progress(self, repo_name, pct, status_text):
        """更新分进度条。"""
        if repo_name in self._sub_progress_bars:
            _, bar, status_lbl = self._sub_progress_bars[repo_name]
            bar.setValue(pct)
            status_lbl.setText(status_text)
            if "✓" in status_text:
                status_lbl.setStyleSheet(
                    f"color: {theme.cyber_green}; font-size: 9px; background: transparent;")
            elif "✗" in status_text:
                status_lbl.setStyleSheet(
                    f"color: {theme.cyber_red}; font-size: 9px; background: transparent;")
            elif "⚠" in status_text:
                status_lbl.setStyleSheet(
                    f"color: {theme.cyber_orange}; font-size: 9px; background: transparent;")
            else:
                status_lbl.setStyleSheet(
                    f"color: {theme.cyber_cyan}; font-size: 9px; background: transparent;")

    def _on_pipeline_finished(self, result):
        self._btn_update_base.setEnabled(True)
        self._btn_fetch_prices.setEnabled(True)
        self._update_panel._dl_progress.hide()
        self._sub_progress_container.hide()
        self._update_panel.refresh_stats()
        self.refresh_price_stats()

        if result.get("success"):
            mode = getattr(self, '_pipeline_mode', 'base')
            if mode == "prices":
                self._add_log('ok', f'市场价格拉取完成! 总耗时: {result.get("elapsed", 0):.0f}s')
                QMessageBox.information(self, S("management", "fetch_complete"),
                    f"市场价格拉取完成！\n\n"
                    f"总耗时: {result.get('elapsed', 0):.0f}s\n\n"
                    "价格数据已刷新。")
            else:
                self._add_log('ok', f'基础数据更新完成! 总耗时: {result.get("elapsed", 0):.0f}s')
                QMessageBox.information(self, S("management", "update_complete"),
                    f"基础数据更新完成！\n\n"
                    f"总耗时: {result.get('elapsed', 0):.0f}s\n\n"
                    "各数据库状态已刷新，可查看数据总览。")
        else:
            self._add_log('error', f'流水线执行失败: {result.get("error", "未知错误")}')
            QMessageBox.warning(self, S("management", "update_failed"),
                f"部分数据库更新失败:\n{result.get('error', '未知错误')}\n\n"
                "已完成的步骤不受影响，可查看日志了解详情。")

    def _on_pipeline_error(self, err_msg):
        self._btn_update_base.setEnabled(True)
        self._btn_fetch_prices.setEnabled(True)
        self._update_panel._dl_progress.hide()
        self._sub_progress_container.hide()
        self._add_log('error', f'流水线错误: {err_msg}')

    # ============================================================
    # 热键配置
    # ============================================================

    def _build_hotkey_group(self, parent_layout):
        group = QGroupBox(S("group", "hotkey_settings"))
        self._hotkey_group = group
        group.setObjectName("normalGroup")
        self._reg_text(group, "group", "hotkey_settings")
        layout = QVBoxLayout(group)

        self._hotkey_tip = QLabel(S("management", "hotkey_tip"))
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
        self._btn_save_hotkeys
        self._btn_save_hotkeys.clicked.connect(self._on_save_hotkeys)
        self._btn_reset_hotkeys = WordWrapButton(S("button", "reset_default"))
        self._reg_text(self._btn_reset_hotkeys, "button", "reset_default")
        self._btn_reset_hotkeys
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
        group.setObjectName("resetGroup")
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
        self._btn_reset_state
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
                background-color: {CYBER_RED};
                border-color: {theme.cyber_yellow};
            }}
            QPushButton:pressed {{
                background-color: {CYBER_RED};
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
        group.setObjectName("normalGroup")
        self._reg_text(group, "group", "theme")
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self._btn_toggle_theme = WordWrapButton(S("button", "custom_theme"))
        self._reg_text(self._btn_toggle_theme, "button", "custom_theme")
        self._btn_toggle_theme
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
        group.setObjectName("normalGroup")
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

        group = QGroupBox(S("group", "lang_preset"))
        self._lang_preset_group = group
        group.setObjectName("presetGroup")
        self._reg_text(group, "group", "lang_preset")
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

        lbl = QLabel(S("management", "current_style"))
        self._lang_preset_label = lbl
        lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 12px; border: none; background: transparent;")
        row.addWidget(lbl)

        self._preset_combo = QComboBox()
        self._preset_combo.wheelEvent = lambda e: e.ignore()
        self._preset_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.get_panel_bg_color(120)};
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
                background: {theme.card_bg};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 2px;
                selection-background-color: {theme.cyber_yellow};
                selection-color: #000;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 4px 8px;
                min-height: 24px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {theme.btn_hover_bg};
            }}
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
        """语言预设切换后重建 UI 文案（批量操作，阻断中间重绘）。"""
        self.setUpdatesEnabled(False)
        try:
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
            self.refresh_price_stats()
        finally:
            self.setUpdatesEnabled(True)

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

        # ── 进度条区域（日志区上方）──
        # 总进度条
        dl_progress = QProgressBar()
        dl_progress.setRange(0, 100); dl_progress.setValue(0)
        dl_progress.setFixedHeight(18)
        dl_progress.setFormat("总进度: %p%")
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

        # 分进度条容器（子步骤/分仓库进度）
        self._sub_progress_container = QWidget()
        self._sub_progress_container.setStyleSheet("background: transparent;")
        self._sub_progress_layout = QVBoxLayout(self._sub_progress_container)
        self._sub_progress_layout.setContentsMargins(0, 2, 0, 2)
        self._sub_progress_layout.setSpacing(4)
        self._sub_progress_bars = {}  # key -> (label, progress_bar, status_label)
        self._sub_progress_container.hide()
        layout.addWidget(self._sub_progress_container)

        log_detail = QLabel("")
        log_detail.setStyleSheet(f"color: {theme.cyber_cyan}; font-size: 11px; padding: 4px 0;")
        log_detail.setWordWrap(True)
        layout.addWidget(log_detail)

        log_area = QTextEdit()
        log_area.setReadOnly(True)
        log_area.setObjectName("LogArea")
        log_area.setStyleSheet(f"""
            QTextEdit#LogArea {{
                background-color: {theme.get_panel_bg_color(160)};
                color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px; padding: 8px;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; border-radius: 4px;
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

        auto_show_cb = QCheckBox("本次使用不再展开")
        auto_show_cb.setChecked(False)
        auto_show_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {theme.text_dim}; font-size: 12px; spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {theme.border}; border-radius: 3px;
                background-color: {theme.get_panel_bg_color(180)};
            }}
            QCheckBox::indicator:checked {{
                background-color: {theme.cyber_red};
            }}
        """)
        auto_show_cb.toggled.connect(self._update_panel.set_auto_show_suppress if self._update_panel else lambda v: None)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(auto_show_cb)
        btn_row.addStretch()
        btn_row.addWidget(btn_close_log)
        layout.addLayout(btn_row)
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
        from data.icon_loader import get_icon_loader, get_nav_icon
        icon_loader = get_icon_loader()
        for i, item_tuple in enumerate(self._nav_items):
            item = self._nav_list.item(i)
            if item:
                nav_id, s_cat, s_key, default_text = item_tuple
                text = S(s_cat, s_key)
                if text.startswith("??") and text.endswith("??"):
                    text = default_text
                # 与 _build_nav 保持一致的图标处理逻辑
                qicon = icon_loader.get_icon("nav", nav_id, size=20)
                if qicon:
                    item.setIcon(qicon)
                    item.setText(text)
                else:
                    icon = get_nav_icon(nav_id)
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
                category = obj.property("_item_category") or ''
                is_relic = ('Relic' in category or 'Relic' in en_name
                            or en_name.split()[0] in {'Lith', 'Meso', 'Neo', 'Axi', 'Requiem', 'Vanguard'})

                # 遗物名称格式转换: items 表用 "Axi A1 Intact"，drop 索引用 "Axi A1 Relic"
                query_name = en_name
                if is_relic:
                    import re
                    m = re.match(
                        r'(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s+([A-Za-z0-9]+)\s+(?:Intact|Exceptional|Flawless|Radiant)$',
                        en_name, re.IGNORECASE
                    )
                    if m:
                        query_name = f"{m.group(1)} {m.group(2)} Relic"

                sources = idx.query(query_name, max_sources=20)
                if is_relic:
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
