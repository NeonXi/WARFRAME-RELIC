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
    QFrame, QFileDialog, QProgressBar, QMessageBox, QGroupBox,
    QApplication, QDialog, QTextEdit, QLineEdit,
    QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from core.constants import theme, reload_theme, ThemeConfig
from core.stylesheet import build_stylesheet
from core.hotkey_config import (
    load_hotkeys, save_hotkeys, validate_hotkey,
    DEFAULT_HOTKEYS, HOTKEY_LABELS,
)
from core.theme_fields import THEME_FIELDS
from core.theme_panel import ThemePanel
from core.update_panel import UpdatePanel, get_db_stats


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

    def __init__(self):
        super().__init__()
        self._data_dir = Path(__file__).resolve().parent.parent / 'data'
        self._db_path = str(self._data_dir / 'relics.db')
        self._alljson_path = str(self._data_dir / 'all.json')
        self._hotkeys = load_hotkeys()
        self._first_show = True

        # 子面板
        self._theme_panel = None   # ThemePanel 实例
        self._update_panel = None  # UpdatePanel 实例

        self._setup_ui()
        self._update_panel.refresh_stats()
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
        content_h = self.layout().sizeHint().height()
        self.setMinimumSize(580, max(content_h, 780))
        if self.height() < 680:
            self.resize(580, 840)

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
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._left_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {theme.panel_bg}; }}")

        self._left_widget = QWidget()
        self._left_widget.setStyleSheet(f"background-color: {theme.panel_bg};")
        main_layout = QVBoxLayout(self._left_widget)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 标题
        title = QLabel("WARFRAME-RELIC 管理面板")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # 初始化子面板
        self._update_panel = UpdatePanel(self, self._data_dir, self._db_path, self._add_log)

        # 各功能区块
        self._build_status_group(main_layout)
        self._build_source_group(main_layout)
        self._build_action_group(main_layout)
        self._build_hotkey_group(main_layout)
        self._build_theme_group(main_layout)
        self._build_about_group(main_layout)

        # 底部提示
        self._bottom_tip = QLabel("提示: 按 Ctrl+Shift+G 可随时唤出此面板 | 主程序 Ctrl+G 框选截图")
        self._bottom_tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        self._bottom_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self._bottom_tip)

        # 退出按钮
        exit_row = QHBoxLayout()
        exit_row.addStretch()
        self._btn_exit = QPushButton("退出程序")
        self._btn_exit.setObjectName("dangerBtn")
        self._btn_exit.clicked.connect(self._on_exit)
        exit_row.addWidget(self._btn_exit)
        main_layout.addLayout(exit_row)
        main_layout.addStretch()

        self._left_scroll.setWidget(self._left_widget)
        self._left_scroll.setMinimumWidth(580)
        self._left_scroll.setMaximumWidth(720)
        outer_layout.addWidget(self._left_scroll, 0)

        # 右侧面板
        self._build_log_panel(outer_layout)
        self._build_theme_slide_panel(outer_layout)

    # ---- 状态区块 ----

    def _build_status_group(self, parent_layout):
        group = QGroupBox("数据库状态")
        layout = QVBoxLayout(group)
        stat_labels = {}
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
            stat_labels[key] = val

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
        self._update_panel.set_progress(self._progress, self._progress_text)

    # ---- 手动数据更新 ----

    def _build_source_group(self, parent_layout):
        group = QGroupBox("手动数据更新")
        layout = QVBoxLayout(group)
        source_label = QLabel(""); source_label.setWordWrap(True)
        layout.addWidget(source_label)

        row = QHBoxLayout()
        self._btn_browse = QPushButton("选择文件...")
        self._btn_browse.clicked.connect(self._update_panel.on_browse)
        self._btn_update = QPushButton("更新数据库")
        self._btn_update.setObjectName("primaryBtn")
        self._btn_update.clicked.connect(self._update_panel.on_update)
        row.addWidget(self._btn_browse); row.addWidget(self._btn_update)
        layout.addLayout(row)
        parent_layout.addWidget(group)

        self._update_panel.set_source_label(source_label)

    # ---- 自动数据更新 ----

    def _build_action_group(self, parent_layout):
        group = QGroupBox("自动数据更新")
        layout = QVBoxLayout(group)

        row_fetch = QHBoxLayout()
        self._btn_fetch = QPushButton("拉取最新数据 (GitHub)")
        self._btn_fetch.setObjectName("primaryBtn")
        self._btn_fetch.clicked.connect(self._update_panel.on_fetch)
        self._btn_update2 = QPushButton("更新数据库")
        self._btn_update2.setObjectName("actionBtn")
        self._btn_update2.clicked.connect(self._update_panel.on_update)
        row_fetch.addWidget(self._btn_fetch); row_fetch.addWidget(self._btn_update2)
        layout.addLayout(row_fetch)

        row1 = QHBoxLayout()
        self._btn_tutorial = QPushButton("数据更新教程")
        self._btn_tutorial.setObjectName("successBtn")
        self._btn_tutorial.clicked.connect(self._update_panel.show_tutorial)
        self._btn_browse_db = QPushButton("打开数据目录")
        self._btn_browse_db.setObjectName("actionBtn")
        self._btn_browse_db.clicked.connect(self._open_data_dir)
        row1.addWidget(self._btn_tutorial); row1.addWidget(self._btn_browse_db)
        layout.addLayout(row1)
        parent_layout.addWidget(group)

        # 注入到 update_panel（使用 self 上的按钮引用）
        self._update_panel.set_buttons(
            btn_update=self._btn_update, btn_update2=self._btn_update2,
            btn_fetch=self._btn_fetch, btn_browse=self._btn_browse,
            btn_browse_db=self._btn_browse_db, btn_tutorial=self._btn_tutorial)

    # ---- 热键配置 ----

    def _build_hotkey_group(self, parent_layout):
        group = QGroupBox("快捷键设置")
        layout = QVBoxLayout(group)

        self._hotkey_tip = QLabel("格式: ctrl+g / alt+shift+f 等。修改后立即生效，无需重启。")
        self._hotkey_tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        layout.addWidget(self._hotkey_tip)

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
        self._btn_toggle_theme = QPushButton("🎨 自定义配色")
        self._btn_toggle_theme.setObjectName("primaryBtn")
        self._btn_toggle_theme.clicked.connect(self._toggle_theme_panel)
        btn_row.addWidget(self._btn_toggle_theme); btn_row.addStretch()
        parent_layout.addLayout(btn_row)

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
        log_panel = QWidget()
        log_panel.setStyleSheet(f"background-color: {theme.panel_darkest};")
        log_panel.setMinimumWidth(420)
        log_panel.setMaximumWidth(520)
        log_panel.hide()

        layout = QVBoxLayout(log_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        log_title = QLabel("运行日志")
        log_title.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 14px; font-weight: bold;")
        self._log_title_lbl = log_title
        layout.addWidget(log_title)

        sep = QFrame(); sep.setObjectName("sep"); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        step_row = QHBoxLayout()
        step_icon = QLabel("⏳")
        step_icon.setStyleSheet("font-size: 20px;")
        step_icon.setFixedWidth(32)
        step_label = QLabel("等待操作...")
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

        btn_close_log = QPushButton("关闭日志面板")
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

        # === 滚动区域 & 主面板背景 ===
        if hasattr(self, '_left_scroll'):
            self._left_scroll.setStyleSheet(
                f"QScrollArea {{ border: none; background-color: {t.panel_bg}; }}")
            self._left_widget.setStyleSheet(f"background-color: {t.panel_bg};")

        # === 底部提示 ===
        if hasattr(self, '_bottom_tip'):
            self._bottom_tip.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")

        # === 日志标题 ===
        if hasattr(self, '_log_title_lbl'):
            self._log_title_lbl.setStyleSheet(f"color: {t.cyber_yellow}; font-size: 14px; font-weight: bold;")

        # === 热键编辑区 ===
        for edit in self._hotkey_editors.values():
            edit.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {t.panel_darkest};
                    color: {t.cyber_cyan};
                    border: 1px solid {t.border};
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-family: "Consolas", "Microsoft YaHei";
                    font-size: 12px;
                }}
                QLineEdit:focus {{ border-color: {t.cyber_yellow}; }}
            """)
        for err in self._hotkey_errors.values():
            err.setStyleSheet(f"color: {t.cyber_red}; font-size: 11px;")
        if hasattr(self, '_hotkey_tip'):
            self._hotkey_tip.setStyleSheet(f"color: {t.text_dim}; font-size: 11px;")

        # === 子面板样式 ===
        self._theme_panel.refresh_inline_styles()
        self._update_panel.refresh_inline_styles()

    def _refresh_all_inline_styles(self):
        """完整刷新（含数据重新查询）。"""
        self._update_panel.refresh_stats()
        self._refresh_hotkey_ui()

    # ============================================================
    # 日志（转发给 update_panel）
    # ============================================================

    def _add_log(self, log_type: str, msg: str):
        self._update_panel.add_log(log_type, msg)

    def add_log(self, log_type: str, msg: str):
        """外部调用日志入口。"""
        self._update_panel.add_log(log_type, msg)

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
            self, "退出确认",
            "确定要退出 WARFRAME-RELIC 吗？\n\n退出后截图识别和快捷键功能将停止工作。",
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
