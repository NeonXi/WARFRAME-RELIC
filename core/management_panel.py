"""
WARFRAME-RELIC 管理面板
- 独立窗口，通过热键 Ctrl+Shift+G 唤起
- 功能：数据库状态、更新、快捷键配置、主题换肤
"""
import os
import sqlite3
import threading
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QProgressBar, QMessageBox, QGroupBox,
    QApplication, QDialog, QDialogButtonBox, QTextEdit, QLineEdit,
    QScrollArea, QSizePolicy, QColorDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor

from core.constants import theme, reload_theme
from core.stylesheet import build_stylesheet, build_dialog_button_style
from core.hotkey_config import (
    load_hotkeys, save_hotkeys, validate_hotkey,
    DEFAULT_HOTKEYS, HOTKEY_LABELS,
)
from core.update_worker import UpdateWorker
from core.fetch_worker import FetchWorker, ALLJSON_URL


# ============================================================
# 主题编辑字段定义
# ============================================================

THEME_FIELDS = [
    # (json_key, 通俗标签, 类别)
    ("cyber_yellow", "标题/高亮文字", "界面主色"),
    ("cyber_cyan", "数据/数值文字", "界面主色"),
    ("cyber_magenta", "装饰品红", "界面主色"),
    ("cyber_orange", "警告提示色", "界面主色"),
    ("cyber_red", "错误/入库标注", "界面主色"),
    ("cyber_green", "成功/出库标注", "界面主色"),
    ("cyber_blue", "辅助蓝色", "界面主色"),
    ("dark_bg", "窗口背景", "面板背景"),
    ("panel_bg", "页面底色", "面板背景"),
    ("card_bg", "输入框/卡片底色", "面板背景"),
    ("border", "所有边框线", "面板背景"),
    ("text", "正文/日志文字", "面板背景"),
    ("text_dim", "提示/次要文字", "面板背景"),
    ("label_default", "统计标签文字", "面板背景"),
    ("panel_darkest", "最深底色（日志/配色区）", "面板背景"),
    ("panel_deeper", "次深底色（代码框）", "面板背景"),
    ("color_vaulted", "遗物出库标注色", "遗物状态"),
    ("color_available", "遗物入库标注色", "遗物状态"),
    ("color_unknown", "遗物未知标注色", "遗物状态"),
    ("color_gold", "金部件（稀有）", "部件稀有度"),
    ("color_silver", "银部件（罕见）", "部件稀有度"),
    ("color_copper", "铜部件（常见）", "部件稀有度"),
    ("log_ok", "日志 [成功]", "日志颜色"),
    ("log_warn", "日志 [警告]", "日志颜色"),
    ("log_error", "日志 [错误]", "日志颜色"),
    ("log_info", "日志 [信息]", "日志颜色"),
    ("log_debug", "日志 [调试]", "日志颜色"),
    ("log_timestamp", "日志 时间戳", "日志颜色"),
    ("btn_default_bg", "普通按钮 背景", "按钮样式"),
    ("btn_default_text", "普通按钮 文字", "按钮样式"),
    ("btn_default_border", "普通按钮 边框", "按钮样式"),
    ("btn_hover_bg", "普通按钮 悬停背景", "按钮样式"),
    ("btn_hover_text", "普通按钮 悬停文字", "按钮样式"),
    ("btn_hover_border", "普通按钮 悬停边框", "按钮样式"),
    ("btn_pressed_bg", "普通按钮 按下背景", "按钮样式"),
    ("btn_disabled_bg", "禁用按钮 背景", "按钮样式"),
    ("btn_disabled_text", "禁用按钮 文字", "按钮样式"),
    ("btn_disabled_border", "禁用按钮 边框", "按钮样式"),
    ("primary_bg", "蓝色主按钮 背景", "按钮样式"),
    ("primary_text", "蓝色主按钮 文字", "按钮样式"),
    ("primary_border", "蓝色主按钮 边框", "按钮样式"),
    ("primary_hover_bg", "蓝色主按钮 悬停背景", "按钮样式"),
    ("primary_hover_border", "蓝色主按钮 悬停边框", "按钮样式"),
    ("primary_disabled_bg", "蓝色主按钮 禁用背景", "按钮样式"),
    ("primary_disabled_text", "蓝色主按钮 禁用文字", "按钮样式"),
    ("primary_disabled_border", "蓝色主按钮 禁用边框", "按钮样式"),
    ("danger_text", "红色危险按钮 文字", "按钮样式"),
    ("danger_border", "红色危险按钮 边框", "按钮样式"),
    ("danger_hover_bg", "红色危险按钮 悬停背景", "按钮样式"),
    ("danger_hover_text", "红色危险按钮 悬停文字", "按钮样式"),
    ("success_text", "绿色成功按钮 文字", "按钮样式"),
    ("success_border", "绿色成功按钮 边框", "按钮样式"),
    ("success_hover_bg", "绿色成功按钮 悬停背景", "按钮样式"),
    ("success_hover_text", "绿色成功按钮 悬停文字", "按钮样式"),
    ("brand_bilibili", "B站链接 默认色", "外链品牌"),
    ("brand_bilibili_hover", "B站链接 悬停色", "外链品牌"),
    ("brand_github", "GitHub链接 默认色", "外链品牌"),
    ("brand_github_hover", "GitHub链接 悬停色", "外链品牌"),
    ("overlay_crosshair_color", "截图准星", "游戏覆盖层"),
    ("overlay_selection_border", "截图框选边框", "游戏覆盖层"),
    ("progress_gradient_start", "进度条 左端色", "游戏覆盖层"),
    ("progress_gradient_mid", "进度条 中间色", "游戏覆盖层"),
    ("progress_gradient_end", "进度条 右端色", "游戏覆盖层"),
    ("fetch_manual_hint", "下载提示色", "游戏覆盖层"),
    ("fetch_error_color", "下载失败色", "游戏覆盖层"),
]


# ============================================================
# 数据库读取辅助
# ============================================================

def _get_db_stats(db_path: str) -> dict:
    """读取数据库统计信息。"""
    if not os.path.exists(db_path):
        return {
            'exists': False, 'relics': 0, 'parts': 0, 'aliases': 0,
            'vaulted': 0, 'available': 0, 'voidtrader': 0,
            'db_size': 0, 'db_mtime': '',
        }
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM relics").fetchone()[0]
        vaulted = cur.execute("SELECT COUNT(*) FROM relics WHERE vaulted=1").fetchone()[0]
        voidtrader = cur.execute("SELECT COUNT(*) FROM relics WHERE vaulted=2").fetchone()[0]
        aliases = cur.execute("SELECT COUNT(*) FROM relic_aliases").fetchone()[0]
        parts = cur.execute("SELECT COUNT(*) FROM relic_parts").fetchone()[0]
        conn.close()
        stat = os.stat(db_path)
        return {
            'exists': True, 'relics': total, 'parts': parts,
            'aliases': aliases, 'vaulted': vaulted,
            'available': total - vaulted - voidtrader,
            'voidtrader': voidtrader, 'db_size': stat.st_size,
            'db_mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }
    except sqlite3.DatabaseError as e:
        return {'exists': False, 'error': f"数据库损坏: {e}"}
    except PermissionError as e:
        return {'exists': False, 'error': f"无权限读取: {e}"}
    except Exception as e:
        return {'exists': False, 'error': str(e)}


# ============================================================
# 管理面板窗口
# ============================================================

class ManagementPanel(QWidget):
    """WARFRAME-RELIC 管理面板。"""

    db_updated = pyqtSignal(str)
    hotkeys_changed = pyqtSignal(dict)
    theme_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._data_dir = Path(__file__).resolve().parent.parent / 'data'
        self._db_path = str(self._data_dir / 'relics.db')
        self._alljson_path = str(self._data_dir / 'all.json')
        self._worker = None
        self._fetch_worker = None
        self._updating = False
        self._fetching = False
        self._hotkeys = load_hotkeys()
        self._theme_swatches = {}
        self._theme_draft = {}
        self._first_show = True
        self._log_panel_auto_show = False  # 初始禁止自动展开，等 showEvent 后再允许

        self._setup_ui()
        self._refresh_stats()
        self._refresh_hotkey_ui()

    # ---- showEvent ----

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self._log_panel_auto_show = True  # 首次显示后，允许日志自动展开
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, self._fix_initial_size)

    def _fix_initial_size(self):
        self.updateGeometry()
        self.layout().activate()
        content_h = self.layout().sizeHint().height()
        self.setMinimumSize(580, max(content_h, 780))
        if self.height() < 680:
            self.resize(580, 840)

    # ============================================================
    # UI 构建
    # ============================================================

    def _setup_ui(self):
        self.setWindowTitle("WARFRAME-RELIC - 管理面板")
        self.setMinimumSize(580, 680)
        self.resize(580, 840)
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

        # 左侧主面板（可滚动）
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {theme.panel_bg}; }}")

        left_widget = QWidget()
        left_widget.setStyleSheet(f"background-color: {theme.panel_bg};")
        main_layout = QVBoxLayout(left_widget)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 标题
        title = QLabel("WARFRAME-RELIC 管理面板")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # 各功能区块
        self._build_status_group(main_layout)
        self._build_source_group(main_layout)
        self._build_action_group(main_layout)
        self._build_hotkey_group(main_layout)
        self._build_theme_group(main_layout)
        self._build_about_group(main_layout)

        # 底部提示
        tip = QLabel("提示: 按 Ctrl+Shift+G 可随时唤出此面板 | 主程序 Ctrl+G 框选截图")
        tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(tip)

        # 退出按钮
        exit_row = QHBoxLayout()
        exit_row.addStretch()
        self._btn_exit = QPushButton("退出程序")
        self._btn_exit.setObjectName("dangerBtn")
        self._btn_exit.clicked.connect(self._on_exit)
        exit_row.addWidget(self._btn_exit)
        main_layout.addLayout(exit_row)
        main_layout.addStretch()

        left_scroll.setWidget(left_widget)
        left_scroll.setMinimumWidth(580)
        outer_layout.addWidget(left_scroll, 1)

        # 右侧面板
        self._build_log_panel(outer_layout)
        self._build_theme_slide_panel(outer_layout)

    # ---- 状态区块 ----

    def _build_status_group(self, parent_layout):
        group = QGroupBox("数据库状态")
        layout = QVBoxLayout(group)
        self._stat_labels = {}
        stat_grid = [
            ("遗物总数", "relics"), ("部件总数", "parts"),
            ("别名总数", "aliases"), ("出库(可获取)", "vaulted"),
            ("入库(不可获取)", "available"), ("虚空商人可购买", "voidtrader"),
            ("文件大小", "db_size"), ("最后更新", "db_mtime"),
        ]
        for label, key in stat_grid:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("statLabel")
            lbl.setFixedWidth(110)
            val = QLabel("--")
            val.setObjectName("statValue")
            row.addWidget(lbl); row.addWidget(val); row.addStretch()
            layout.addLayout(row)
            self._stat_labels[key] = val

        self._progress = QProgressBar()
        self._progress.setRange(0, 0); self._progress.hide()
        self._progress.setFixedHeight(6)
        layout.addWidget(self._progress)

        self._progress_text = QLabel("")
        self._progress_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_text.hide()
        layout.addWidget(self._progress_text)
        parent_layout.addWidget(group)

    # ---- 手动数据更新 ----

    def _build_source_group(self, parent_layout):
        group = QGroupBox("手动数据更新")
        layout = QVBoxLayout(group)
        self._source_label = QLabel(""); self._source_label.setWordWrap(True)
        layout.addWidget(self._source_label)

        row = QHBoxLayout()
        self._btn_browse = QPushButton("选择文件...")
        self._btn_browse.clicked.connect(self._on_browse)
        self._btn_update = QPushButton("更新数据库")
        self._btn_update.setObjectName("primaryBtn")
        self._btn_update.clicked.connect(self._on_update)
        row.addWidget(self._btn_browse); row.addWidget(self._btn_update)
        layout.addLayout(row)
        parent_layout.addWidget(group)

    # ---- 自动数据更新 ----

    def _build_action_group(self, parent_layout):
        group = QGroupBox("自动数据更新")
        layout = QVBoxLayout(group)

        row_fetch = QHBoxLayout()
        self._btn_fetch = QPushButton("拉取最新数据 (GitHub)")
        self._btn_fetch.setObjectName("primaryBtn")
        self._btn_fetch.clicked.connect(self._on_fetch)
        self._btn_update2 = QPushButton("更新数据库")
        self._btn_update2.setObjectName("actionBtn")
        self._btn_update2.clicked.connect(self._on_update)
        row_fetch.addWidget(self._btn_fetch); row_fetch.addWidget(self._btn_update2)
        layout.addLayout(row_fetch)

        row1 = QHBoxLayout()
        self._btn_tutorial = QPushButton("数据更新教程")
        self._btn_tutorial.setObjectName("successBtn")
        self._btn_tutorial.clicked.connect(self._show_tutorial)
        self._btn_browse_db = QPushButton("打开数据目录")
        self._btn_browse_db.setObjectName("actionBtn")
        self._btn_browse_db.clicked.connect(self._open_data_dir)
        row1.addWidget(self._btn_tutorial); row1.addWidget(self._btn_browse_db)
        layout.addLayout(row1)
        parent_layout.addWidget(group)

    # ---- 热键配置 ----

    def _build_hotkey_group(self, parent_layout):
        group = QGroupBox("快捷键设置")
        layout = QVBoxLayout(group)

        tip = QLabel("格式: ctrl+g / alt+shift+f 等。修改后立即生效，无需重启。")
        tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        layout.addWidget(tip)

        self._hotkey_editors = {}
        self._hotkey_errors = {}

        for key in DEFAULT_HOTKEYS:
            row = QHBoxLayout()
            lbl = QLabel(HOTKEY_LABELS.get(key, key))
            lbl.setStyleSheet(f"color: {theme.label_default}; font-size: 12px;")
            lbl.setFixedWidth(100)
            row.addWidget(lbl)

            edit = QLineEdit()
            edit.setPlaceholderText("如 ctrl+g")
            edit.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {theme.panel_darkest};
                    color: {theme.cyber_cyan};
                    border: 1px solid {theme.border};
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-family: "Consolas", "Microsoft YaHei";
                    font-size: 12px;
                }}
                QLineEdit:focus {{ border-color: {theme.cyber_yellow}; }}
            """)
            edit.setFixedWidth(140)
            row.addWidget(edit)

            err = QLabel("")
            err.setStyleSheet(f"color: {theme.cyber_red}; font-size: 11px;")
            row.addWidget(err); row.addStretch()
            layout.addLayout(row)
            self._hotkey_editors[key] = edit
            self._hotkey_errors[key] = err

        btn_row = QHBoxLayout()
        self._btn_save_hotkeys = QPushButton("保存快捷键")
        self._btn_save_hotkeys.setObjectName("primaryBtn")
        self._btn_save_hotkeys.clicked.connect(self._on_save_hotkeys)
        self._btn_reset_hotkeys = QPushButton("恢复默认")
        self._btn_reset_hotkeys.setObjectName("actionBtn")
        self._btn_reset_hotkeys.clicked.connect(self._on_reset_hotkeys)
        btn_row.addWidget(self._btn_save_hotkeys)
        btn_row.addWidget(self._btn_reset_hotkeys); btn_row.addStretch()
        layout.addLayout(btn_row)
        parent_layout.addWidget(group)

    # ---- 主题入口按钮 ----

    def _build_theme_group(self, parent_layout):
        btn_row = QHBoxLayout()
        self._btn_toggle_theme = QPushButton("🎨 换肤")
        self._btn_toggle_theme.setObjectName("primaryBtn")
        self._btn_toggle_theme.clicked.connect(self._toggle_theme_panel)
        btn_row.addWidget(self._btn_toggle_theme); btn_row.addStretch()
        parent_layout.addLayout(btn_row)

    # ---- 主题侧滑面板 ----

    def _build_theme_slide_panel(self, outer_layout):
        self._theme_panel = QWidget()
        self._theme_panel.setFixedWidth(0)
        self._theme_panel.setStyleSheet(f"background-color: {theme.panel_darkest};")
        self._theme_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        panel_layout = QVBoxLayout(self._theme_panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        title_lbl = QLabel("🎨 主题配色")
        title_lbl.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 14px; font-weight: bold;")
        title_row.addWidget(title_lbl); title_row.addStretch()
        self._btn_close_theme = QPushButton("✕")
        self._btn_close_theme.setFixedSize(28, 28)
        self._btn_close_theme.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {theme.text_dim}; border: none;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ color: {theme.cyber_red}; }}
        """)
        self._btn_close_theme.clicked.connect(self._collapse_theme_panel)
        title_row.addWidget(self._btn_close_theme)
        panel_layout.addLayout(title_row)

        tip = QLabel("点击色块改颜色 → 刷新预览看效果 → 保存主题持久化")
        tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px;")
        tip.setWordWrap(True)
        panel_layout.addWidget(tip)

        # 色块滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {theme.border}; "
            f"border-radius: 4px; background: {theme.panel_deeper}; }}")

        tw = QWidget()
        tw.setStyleSheet(f"background: {theme.panel_deeper};")
        tw_layout = QVBoxLayout(tw)
        tw_layout.setSpacing(6)

        categories = {}
        for jk, lbl, cat in THEME_FIELDS:
            categories.setdefault(cat, []).append((jk, lbl))

        data = theme.to_dict()
        for cat_name, fields in categories.items():
            cat_lbl = QLabel(f"▸ {cat_name}")
            cat_lbl.setStyleSheet(
                f"color: {theme.cyber_cyan}; font-weight: bold; font-size: 11px; padding: 2px 0;")
            tw_layout.addWidget(cat_lbl)

            row = QHBoxLayout(); row.setSpacing(4); col_count = 0
            for json_key, label in fields:
                color = data.get(json_key, "#000000")
                item = QWidget()
                item.setFixedWidth(56)
                item_layout = QVBoxLayout(item)
                item_layout.setContentsMargins(2, 2, 2, 2)
                item_layout.setSpacing(1)

                swatch = QLabel("　")
                swatch.setFixedSize(48, 14)
                swatch.setStyleSheet(
                    f"background-color: {color}; border: 1px solid {theme.border}; border-radius: 2px;")
                swatch.setCursor(Qt.CursorShape.PointingHandCursor)
                swatch.mousePressEvent = lambda e, k=json_key, s=swatch: self._pick_color(k, s)
                item_layout.addWidget(swatch)

                name_lbl = QLabel(label)
                name_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 8px;")
                name_lbl.setWordWrap(True)
                item_layout.addWidget(name_lbl)

                row.addWidget(item)
                self._theme_swatches[json_key] = swatch
                col_count += 1
                if col_count >= 4:
                    tw_layout.addLayout(row)
                    row = QHBoxLayout(); row.setSpacing(4); col_count = 0
            if col_count > 0:
                row.addStretch(); tw_layout.addLayout(row)
        tw_layout.addStretch()
        scroll.setWidget(tw)
        panel_layout.addWidget(scroll, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._btn_save_theme = QPushButton("保存主题")
        self._btn_save_theme.setObjectName("primaryBtn")
        self._btn_save_theme.clicked.connect(self._on_save_theme)
        self._btn_reset_theme = QPushButton("恢复默认")
        self._btn_reset_theme.setObjectName("actionBtn")
        self._btn_reset_theme.clicked.connect(self._on_reset_theme)
        self._btn_apply_theme = QPushButton("刷新预览")
        self._btn_apply_theme.setObjectName("actionBtn")
        self._btn_apply_theme.clicked.connect(self._on_refresh_theme_preview)
        btn_row.addWidget(self._btn_save_theme)
        btn_row.addWidget(self._btn_reset_theme)
        btn_row.addWidget(self._btn_apply_theme)
        panel_layout.addLayout(btn_row)

        outer_layout.addWidget(self._theme_panel)
        self._theme_expanded = False
        self._theme_anim = None

    # ---- 主题动画 ----

    def _toggle_theme_panel(self):
        if self._theme_expanded:
            self._collapse_theme_panel()
        else:
            self._expand_theme_panel()

    def _expand_theme_panel(self):
        if self._theme_expanded:
            return
        self._theme_expanded = True
        self._run_theme_anim(0, 320)

    def _collapse_theme_panel(self):
        if not self._theme_expanded:
            return
        self._theme_expanded = False
        self._run_theme_anim(self._theme_panel.width(), 0)

    def _run_theme_anim(self, start_w, end_w):
        if self._theme_anim and self._theme_anim.state() == QPropertyAnimation.State.Running:
            self._theme_anim.stop()
        self._theme_anim = QPropertyAnimation(self._theme_panel, b"minimumWidth")
        self._theme_anim.setDuration(250)
        self._theme_anim.setStartValue(start_w)
        self._theme_anim.setEndValue(end_w)
        self._theme_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._theme_anim.valueChanged.connect(self._on_theme_anim_step)
        self._theme_anim.start()

    def _on_theme_anim_step(self, w):
        self._theme_panel.setFixedWidth(w)
        self._theme_panel.setVisible(w > 0)
        extra = w + (420 if self._log_panel.isVisible() else 0)
        self.resize(580 + extra, self.height())

    # ---- 关于作者 ----

    def _build_about_group(self, parent_layout):
        group = QGroupBox("关于作者")
        layout = QVBoxLayout(group); layout.setSpacing(4)

        author_row = QHBoxLayout()
        author_row.addWidget(QLabel("作者: NeonXi (B站: MichaelJackso2)"))
        author_row.addStretch()
        layout.addLayout(author_row)

        for icon, label, obj_name, color, hover, handler in [
            ("📺", "Bilibili 主页 →", "bilibiliBtn",
             theme.brand_bilibili, theme.brand_bilibili_hover, self._open_bilibili),
            ("🐙", "GitHub 仓库 →", "githubBtn",
             theme.brand_github, theme.brand_github_hover, self._open_github),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(icon))
            btn = QPushButton(label)
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

        ver = QLabel("WARFRAME-RELIC v1.0")
        ver.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        layout.addWidget(ver)
        parent_layout.addWidget(group)

    # ---- 日志面板 ----

    def _build_log_panel(self, outer_layout):
        self._log_panel = QWidget()
        self._log_panel.setStyleSheet(f"background-color: {theme.panel_darkest};")
        self._log_panel.setMinimumWidth(420)
        self._log_panel.setMaximumWidth(520)
        self._log_panel.hide()

        layout = QVBoxLayout(self._log_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        log_title = QLabel("运行日志")
        log_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 14px; font-weight: bold;")
        layout.addWidget(log_title)

        sep = QFrame(); sep.setObjectName("sep"); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        step_row = QHBoxLayout()
        self._step_icon = QLabel("⏳")
        self._step_icon.setStyleSheet("font-size: 20px;")
        self._step_icon.setFixedWidth(32)
        self._step_label = QLabel("等待操作...")
        self._step_label.setStyleSheet(f"color: {theme.text_dim}; font-size: 13px;")
        self._step_label.setWordWrap(True)
        step_row.addWidget(self._step_icon); step_row.addWidget(self._step_label, 1)
        layout.addLayout(step_row)

        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 100); self._dl_progress.setValue(0)
        self._dl_progress.setFixedHeight(18)
        self._dl_progress.setFormat("%p%")
        self._dl_progress.setStyleSheet(f"""
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
        layout.addWidget(self._dl_progress)

        self._log_detail = QLabel("")
        self._log_detail.setStyleSheet(f"color: {theme.cyber_cyan}; font-size: 11px; padding: 4px 0;")
        self._log_detail.setWordWrap(True)
        layout.addWidget(self._log_detail)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet(f"""
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
        self._log_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self._log_area, 1)

        self._btn_close_log = QPushButton("关闭日志面板")
        self._btn_close_log.clicked.connect(self._hide_log_panel)
        self._btn_close_log.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.card_bg}; color: {theme.text_dim};
                border: 1px solid {theme.border}; border-radius: 4px;
                padding: 6px; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.btn_hover_bg}; color: {theme.text};
            }}
        """)
        layout.addWidget(self._btn_close_log)
        outer_layout.addWidget(self._log_panel)

    # ============================================================
    # 主题配色功能
    # ============================================================

    def _pick_color(self, json_key, swatch):
        current = theme.to_dict().get(json_key, "#000000")
        color = QColorDialog.getColor(QColor(current), self, f"选择颜色 - {json_key}")
        if color.isValid():
            hex_color = color.name()
            self._theme_draft[json_key] = hex_color
            swatch.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid {theme.border}; border-radius: 2px;")

    def _on_refresh_theme_preview(self):
        if not self._theme_draft:
            QMessageBox.information(self, "提示", "请先点击色块修改颜色，再刷新预览。")
            return
        theme.save(self._theme_draft)
        self._rebuild_styles_and_swatches()

    def _on_save_theme(self):
        if not self._theme_draft:
            QMessageBox.information(self, "提示", "没有需要保存的修改。请先调整颜色。")
            return
        if theme.save(self._theme_draft):
            self._theme_draft = {}
            self._rebuild_styles_and_swatches()
            self.theme_changed.emit()
            QMessageBox.information(self, "保存成功", "主题配色已保存，界面已刷新！")
        else:
            QMessageBox.critical(self, "保存失败", "无法写入配置文件。")

    def _on_reset_theme(self):
        reply = QMessageBox.question(
            self, "恢复默认主题",
            "确定要恢复为默认 Cyberpunk 2077 配色吗？\n\n当前修改将全部丢失。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        theme.reset()
        self._theme_draft = {}
        self._rebuild_styles_and_swatches()
        self._refresh_all_inline_styles()
        self.theme_changed.emit()
        QMessageBox.information(self, "已恢复", "主题已恢复为默认 Cyberpunk 2077 配色。")

    def _rebuild_styles_and_swatches(self):
        """刷新全局样式表、内联样式和色块（仅 UI 层）。"""
        # _ThemeProxy 已自动代理，只需刷新 QSS 和内联样式
        self.setStyleSheet(build_stylesheet())
        self._refresh_inline_styles()
        self._rebuild_theme_swatches()

    def _refresh_inline_styles(self):
        """仅刷新内联样式（颜色相关的 UI 元素），不重新查询数据库。"""
        # 更新按钮样式
        self._btn_browse.setStyleSheet("")
        self._btn_browse.setObjectName("")
        self._btn_update.setStyleSheet("")
        self._btn_update2.setStyleSheet("")
        self._btn_fetch.setStyleSheet("")
        self._btn_tutorial.setStyleSheet("")
        self._btn_browse_db.setStyleSheet("")
        self._btn_save_hotkeys.setStyleSheet("")
        self._btn_reset_hotkeys.setStyleSheet("")
        self._btn_save_theme.setStyleSheet("")
        self._btn_reset_theme.setStyleSheet("")
        self._btn_apply_theme.setStyleSheet("")
        self._btn_exit.setStyleSheet("")
        self._btn_close_log.setStyleSheet("")
        self._btn_toggle_theme.setStyleSheet("")
        self._btn_close_theme.setStyleSheet("")
        # 数据值颜色
        self._stat_labels.get('vaulted', QLabel()).setStyleSheet(
            f"color: {theme.cyber_green}; font-weight: bold;")
        self._stat_labels.get('available', QLabel()).setStyleSheet(
            f"color: {theme.cyber_red}; font-weight: bold;")
        self._stat_labels.get('voidtrader', QLabel()).setStyleSheet(
            f"color: {theme.cyber_cyan}; font-weight: bold;")
        # 日志面板背景
        self._log_panel.setStyleSheet(f"background-color: {theme.panel_darkest};")
        self._theme_panel.setStyleSheet(f"background-color: {theme.panel_darkest};")

    def _rebuild_theme_swatches(self):
        data = theme.to_dict()
        for json_key, swatch in self._theme_swatches.items():
            color = data.get(json_key, "#000000")
            swatch.setStyleSheet(
                f"background-color: {color}; border: 1px solid {theme.border}; border-radius: 2px;")

    def _refresh_all_inline_styles(self):
        """完整刷新（含数据重新查询）。"""
        self._refresh_stats()
        self._refresh_hotkey_ui()

    # ============================================================
    # 日志
    # ============================================================

    def add_log(self, log_type: str, msg: str):
        """添加日志（log_type: ok/warn/error/info/debug）。"""
        if not self._log_panel.isVisible() and self._log_panel_auto_show:
            self._show_log_panel()
        self._log_area.append(self._format_log_line(log_type, msg))
        self._log_area.verticalScrollBar().setValue(
            self._log_area.verticalScrollBar().maximum())

    # ============================================================
    # 统计刷新
    # ============================================================

    def _refresh_stats(self):
        stats = _get_db_stats(self._db_path)
        if not stats.get('exists'):
            self._stat_labels['relics'].setText("数据库不存在")
            for k in ['parts', 'aliases', 'vaulted', 'available', 'voidtrader', 'db_size', 'db_mtime']:
                self._stat_labels[k].setText("--")
            return

        self._stat_labels['relics'].setText(str(stats['relics']))
        self._stat_labels['parts'].setText(str(stats['parts']))
        self._stat_labels['aliases'].setText(str(stats['aliases']))
        self._stat_labels['vaulted'].setText(str(stats['vaulted']))
        self._stat_labels['vaulted'].setStyleSheet(f"color: {theme.cyber_green}; font-weight: bold;")
        self._stat_labels['available'].setText(str(stats['available']))
        self._stat_labels['available'].setStyleSheet(f"color: {theme.cyber_red}; font-weight: bold;")
        self._stat_labels['voidtrader'].setText(f"{stats.get('voidtrader', 0)}  (功能未实现)")
        self._stat_labels['voidtrader'].setStyleSheet(f"color: {theme.cyber_cyan}; font-weight: bold;")
        self._stat_labels['db_size'].setText(f"{stats['db_size'] / 1024:.1f} KB")
        self._stat_labels['db_mtime'].setText(stats['db_mtime'])

        if os.path.exists(self._alljson_path):
            self._source_label.setText(f"当前: {self._alljson_path}")
            self._source_label.setStyleSheet(f"color: {theme.cyber_green};")
        else:
            self._source_label.setText(f"all.json 未找到: {self._alljson_path}")
            self._source_label.setStyleSheet(f"color: {theme.cyber_red};")

    # ============================================================
    # 热键
    # ============================================================

    def _refresh_hotkey_ui(self):
        for key, edit in self._hotkey_editors.items():
            edit.setText(self._hotkeys.get(key, ""))
            if key in self._hotkey_errors:
                self._hotkey_errors[key].setText("")

    def _on_save_hotkeys(self):
        new_hotkeys = {}; has_error = False
        for key, edit in self._hotkey_editors.items():
            val = edit.text().strip().lower()
            new_hotkeys[key] = val
            if not val:
                self._hotkey_errors[key].setText("不能为空"); has_error = True
            elif not validate_hotkey(val):
                self._hotkey_errors[key].setText("格式错误"); has_error = True
            else:
                self._hotkey_errors[key].setText("")
        if has_error:
            QMessageBox.warning(self, "格式错误",
                "请修正红色提示的快捷键格式。\n\n正确格式如: ctrl+g / alt+shift+f / ctrl+shift+g")
            return
        if save_hotkeys(new_hotkeys):
            self._hotkeys = new_hotkeys
            self._refresh_hotkey_ui()
            self.hotkeys_changed.emit(self._hotkeys)
            QMessageBox.information(self, "保存成功", "快捷键已更新，立即生效！")
        else:
            QMessageBox.critical(self, "保存失败", "无法写入配置文件，请检查磁盘空间和权限。")

    def _on_reset_hotkeys(self):
        reply = QMessageBox.question(
            self, "恢复默认",
            f"确定要恢复默认快捷键吗？\n\n"
            f"框选截图: {DEFAULT_HOTKEYS['select']}\n"
            f"全屏截图: {DEFAULT_HOTKEYS['fullscreen']}\n"
            f"管理面板: {DEFAULT_HOTKEYS['panel']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        if save_hotkeys({}):
            self._hotkeys = dict(DEFAULT_HOTKEYS)
            self._refresh_hotkey_ui()
            self.hotkeys_changed.emit(self._hotkeys)
            QMessageBox.information(self, "已恢复", "快捷键已恢复为默认值。")

    # ============================================================
    # 对话框（公共工厂方法）
    # ============================================================

    _TEXTEDIT_STYLE = (
        "QTextEdit {{"
        "  background-color: {bg}; color: {fg};"
        "  border: 1px solid {border}; border-radius: 4px;"
        "  font-family: \"Consolas\", \"Microsoft YaHei\", monospace;"
        "  font-size: 12px; padding: 8px;"
        "}}"
    )

    def _build_text_dialog(self, title: str, text_content: str,
                           width: int = 560, height: int = 600,
                           readonly: bool = True,
                           title_color: str = None) -> QDialog:
        """构建带 QTextEdit 的通用对话框，消除重复代码。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(width, height)
        dlg.resize(width, height)
        dlg.setStyleSheet(build_stylesheet())
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        label = QLabel(title)
        label.setStyleSheet(
            f"color: {title_color or theme.cyber_red}; font-size: 14px; font-weight: bold;")
        layout.addWidget(label)

        text = QTextEdit()
        text.setReadOnly(readonly)
        text.setPlainText(text_content)
        text.setStyleSheet(
            self._TEXTEDIT_STYLE.format(
                bg=theme.panel_deeper, fg=theme.text, border=theme.border))
        layout.addWidget(text, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            build_dialog_button_style())
        layout.addWidget(btn_box)
        return dlg

    def _format_log_line(self, log_type: str, msg: str) -> str:
        """格式化单条日志为 HTML 行（消除 add_log / _on_fetch_log 重复）。"""
        now = datetime.now().strftime("%H:%M:%S")
        color = theme.log_color_map.get(log_type, theme.text)
        prefix_map = {"ok": "✓", "warn": "⚠", "error": "✗", "info": "  "}
        p = prefix_map.get(log_type, " ")
        return (
            f'<span style="color:{theme.log_timestamp};">[{now}]</span> '
            f'<span style="color:{color};">{p} {msg}</span>')

    def _show_error_dialog(self, title: str, message: str):
        dlg = self._build_text_dialog(title, message, 550, 380, False)
        dlg.exec()

    # ============================================================
    # 数据更新
    # ============================================================

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 WFInfo 数据文件", str(self._data_dir),
            "JSON 文件 (*.json);;所有文件 (*.*)")
        if path:
            self._alljson_path = path
            self._source_label.setText(f"当前: {self._alljson_path}")
            self._source_label.setStyleSheet(f"color: {theme.cyber_yellow};")
            self._refresh_stats()

    def _on_fetch(self):
        if self._fetching or self._updating:
            return
        reply = QMessageBox.question(
            self, "拉取最新数据",
            f"将从 GitHub 下载最新 all.json:\n\n{ALLJSON_URL}\n\n"
            f"保存到: {self._alljson_path}\n下载完成后将自动更新数据库。\n\n确认继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._show_log_panel()
        self._log_area.clear()
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">========== 开始拉取数据 ==========</span>')
        self._log_area.append(f'<span style="color:{theme.cyber_cyan};">  源地址: {ALLJSON_URL}</span>')
        self._log_area.append(
            f'<span style="color:{theme.cyber_cyan};">  保存到: {self._alljson_path}</span>')
        self._dl_progress.setValue(0)
        self._step_icon.setText("⏳")
        self._step_label.setText("准备中...")
        self._step_label.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 13px;")
        self._log_detail.setText("等待开始...")

        self._fetching = True
        self._set_buttons_enabled(False)
        self._progress.show(); self._progress_text.show()
        self._progress_text.setText("正在下载数据...")

        self._fetch_worker = FetchWorker(self._alljson_path)
        self._fetch_worker.step_changed.connect(self._on_fetch_step)
        self._fetch_worker.log.connect(self._on_fetch_log)
        self._fetch_worker.progress_pct.connect(self._on_fetch_progress)
        self._fetch_worker.finished.connect(self._on_fetch_finished)
        self._fetch_worker.error.connect(self._on_fetch_error)
        threading.Thread(target=self._fetch_worker.run, daemon=True).start()

    def _on_fetch_step(self, step, desc):
        details = {
            1: "正在解析 GitHub 仓库地址，检测网络环境...",
            2: "正在解析 DNS，查找 raw.githubusercontent.com 的 IP 地址...",
            3: "正在建立 HTTPS 安全连接（TCP + TLS 握手）...",
            4: "正在获取文件元信息（大小、类型）...",
            5: "正在下载 all.json 数据文件...",
            6: "正在验证 JSON 数据格式完整性...",
            7: "正在保存文件到本地 data 目录...",
        }
        icons = {1: "🔗", 2: "🌐", 3: "🔒", 4: "📋", 5: "⬇️", 6: "✅", 7: "💾"}
        self._step_icon.setText(icons.get(step, "⏳"))
        self._step_label.setText(f"[{step}/7] {desc}")
        self._step_label.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 13px;")
        self._log_detail.setText(details.get(step, desc))
        self._log_area.append(
            f'<span style="color:{theme.cyber_yellow};">▶ [{step}/7] {desc}</span>')

    def _on_fetch_log(self, log_type, msg):
        self._log_area.append(self._format_log_line(log_type, msg))
        self._log_area.verticalScrollBar().setValue(
            self._log_area.verticalScrollBar().maximum())

    def _on_fetch_progress(self, pct):
        self._dl_progress.setValue(pct)
        self._log_detail.setText(f"正在下载... 已完成 {pct}%，请耐心等待")

    def _on_fetch_finished(self, save_path):
        self._alljson_path = save_path
        self._source_label.setText(f"当前: {self._alljson_path}")
        self._source_label.setStyleSheet(f"color: {theme.cyber_green};")
        self._step_icon.setText("✅")
        self._step_label.setText("下载成功！")
        self._step_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 13px;")
        self._log_detail.setText("下载完成，正在自动更新数据库...")
        self._progress_text.setText("下载完成，开始更新数据库...")
        self._on_update()
        self._fetching = False

    def _on_fetch_error(self, msg):
        self._fetching = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        self._step_icon.setText("❌")
        self._step_label.setText("下载失败")
        self._step_label.setStyleSheet(f"color: {theme.fetch_error_color}; font-size: 13px;")
        self._log_detail.setText(f"下载失败: {msg[:200]}")
        self._log_area.append(
            f'<span style="color:{theme.fetch_error_color};">  ✗ 失败: {msg}</span>')
        self._log_area.append(
            f'<span style="color:{theme.fetch_manual_hint};">  → 请手动下载: {ALLJSON_URL}</span>')
        self._log_area.append(
            f'<span style="color:{theme.fetch_manual_hint};">  → 保存到: {self._alljson_path}</span>')
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">========== 拉取失败 ==========</span>')
        self._show_error_dialog("下载失败",
            f"无法从 GitHub 拉取数据:\n{msg}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"请手动下载:\n{ALLJSON_URL}\n\n"
            f"保存到:\n{self._alljson_path}\n\n"
            f"保存后点击「更新数据库」按钮即可。\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━")

    def _on_update(self):
        if self._updating:
            return
        if not os.path.exists(self._alljson_path):
            QMessageBox.warning(self, "文件不存在", f"找不到数据文件:\n{self._alljson_path}")
            return
        if not self._fetching:
            reply = QMessageBox.question(
                self, "确认更新",
                f"将从以下文件更新数据库:\n{self._alljson_path}\n\n"
                f"目标: {self._db_path}\n\n此操作会覆盖现有数据库。确认继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._updating = True
        self._set_buttons_enabled(False)
        self._progress.show(); self._progress_text.show()
        self._progress_text.setText("正在准备...")

        self._worker = UpdateWorker(self._alljson_path, self._db_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        threading.Thread(target=self._worker.run, daemon=True).start()

    def _on_progress(self, msg):
        self._progress_text.setText(msg)
        if self._log_panel.isVisible():
            self._log_detail.setText(f"数据库更新: {msg}")

    def _on_finished(self, stats):
        self._updating = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        self._refresh_stats()

        if self._log_panel.isVisible():
            self._step_icon.setText("✅")
            self._step_label.setText("全部完成！")
            self._step_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 13px;")
            dropping = stats.get('dropping', 0)
            total = stats.get('relics', 0)
            self._log_detail.setText(
                f"数据库更新成功！\n  遗物: {total} | 部件: {stats.get('parts', 0)} | "
                f"别名: {stats.get('aliases', 0)}\n  出库: {dropping} | 入库: {total - dropping}")
            self._log_area.append(
                f'<span style="color:{theme.cyber_green};">  ✓ 数据库更新完成 (遗物 {total} 个)</span>')
            self._log_area.append(
                f'<span style="color:{theme.text_dim};">========== 全部完成 ==========</span>')

        dropping = stats.get('dropping', 0)
        total = stats.get('relics', 0)
        QMessageBox.information(self, "更新完成",
            f"数据库更新成功!\n\n"
            f"遗物数: {total}\n部件数: {stats.get('parts', 0)}\n"
            f"别名数: {stats.get('aliases', 0)}\n"
            f"出库:   {dropping} 个\n入库:   {total - dropping} 个")
        self.db_updated.emit(self._db_path)

    def _on_error(self, msg):
        self._updating = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        self._show_error_dialog("更新失败", f"数据库更新出错:\n{msg}")

    def _set_buttons_enabled(self, enabled: bool):
        for btn in [self._btn_update, self._btn_update2, self._btn_fetch, self._btn_browse]:
            btn.setEnabled(enabled)

    # ============================================================
    # 教程 / 链接
    # ============================================================

    def _show_tutorial(self):
        tutorial_text = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📖 WARFRAME-RELIC 数据更新教程\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "本程序使用 WFCD/warframe-drop-data 项目提供的游戏数据，\n"
            "数据源地址：\n"
            "https://github.com/WFCD/warframe-drop-data\n\n"
            "由于 GitHub 在国内访问可能较慢或不稳定，建议使用以下\n"
            "任一方式获取数据文件：\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法一：使用 Watt Toolkit (原名 Steam++) 加速\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Watt Toolkit 是一款免费、开源、跨平台的网络加速工具，\n"
            "可以稳定加速 GitHub 访问，完全免费无广告。\n\n"
            "① 下载安装\n"
            "   官网：https://steampp.net/\n"
            "   也可在微软应用商店搜索「Watt Toolkit」安装。\n\n"
            "② 启用 GitHub 加速\n"
            "   - 打开 Watt Toolkit\n"
            "   - 点击左侧「网络加速」\n"
            "   - 在「平台加速」选项卡中勾选「GitHub」\n"
            "   - 点击右上角「一键加速」按钮\n\n"
            "③ 启动加速后，再点击本程序的「拉取最新数据(GitHub)」按钮\n"
            "   即可流畅下载 all.json 数据文件。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法二：手动下载（无需任何工具）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "① 在浏览器中打开以下链接：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data/all.json\n\n"
            "② 右键 → 另存为（或 Ctrl+S），将文件保存为 all.json\n\n"
            "③ 将下载好的 all.json 放到以下目录：\n"
            f"   {self._data_dir}\n\n"
            "④ 回到本程序，在「手动数据更新」区域点击「更新数据库」即可。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 提示：如果浏览器也无法打开该链接，建议先使用方法一\n"
            "   安装 Watt Toolkit 加速 GitHub 后再下载。\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        dlg = self._build_text_dialog(
            "数据更新教程", tutorial_text, 560, 600, True, theme.cyber_yellow)
        dlg.exec()

    def _open_bilibili(self):
        import webbrowser
        webbrowser.open("https://space.bilibili.com/21001459")

    def _open_github(self):
        import webbrowser
        webbrowser.open("https://github.com/NeonXi/WARFRAME-RELIC")

    def _open_data_dir(self):
        os.startfile(str(self._data_dir))

    # ============================================================
    # 日志面板显示/隐藏
    # ============================================================

    def _show_log_panel(self):
        self._log_panel.show()
        extra_w = (self._theme_panel.width() if self._theme_expanded else 0) + 420
        self.resize(580 + extra_w, max(self.height(), 700))

    def _hide_log_panel(self):
        self._log_panel.hide()
        extra_w = self._theme_panel.width() if self._theme_expanded else 0
        self.resize(580 + extra_w, max(self.height(), 700))

    # ============================================================
    # 退出
    # ============================================================

    def _on_exit(self):
        reply = QMessageBox.question(
            self, "退出确认",
            "确定要退出 WARFRAME-RELIC 吗？\n\n退出后截图识别和快捷键功能将停止工作。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.instance().quit()

    def closeEvent(self, event):
        if self._updating:
            event.ignore()
            return
        if self._log_panel.isVisible():
            self._hide_log_panel()
        self.hide()
        event.ignore()
