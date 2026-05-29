"""
WARFRAME-RELIC 管理面板
- 独立窗口，通过热键 Ctrl+Shift+G 唤起
- 功能：数据库更新、状态查看、统计信息、一键刷新
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
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.hotkey_config import (
    load_hotkeys, save_hotkeys, validate_hotkey,
    DEFAULT_HOTKEYS, HOTKEY_LABELS,
)
from core.update_worker import UpdateWorker
from core.fetch_worker import FetchWorker, ALLJSON_URL


# ============================================================
# 数据库读取辅助
# ============================================================

def _get_db_stats(db_path: str) -> dict:
    """读取数据库统计信息
    vaulted=1 → 出库, vaulted=0 → 入库, vaulted=2 → 虚空商人
    """
    if not os.path.exists(db_path):
        return {
            'exists': False,
            'relics': 0, 'parts': 0, 'aliases': 0,
            'vaulted': 0, 'available': 0, 'voidtrader': 0, 'db_size': 0,
            'db_mtime': '',
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
            'exists': True,
            'relics': total,
            'parts': parts,
            'aliases': aliases,
            'vaulted': vaulted,       # 出库(可获取)
            'available': total - vaulted - voidtrader,  # 入库(不可获取)
            'voidtrader': voidtrader, # 虚空商人可购买
            'db_size': stat.st_size,
            'db_mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception as e:
        return {'exists': False, 'error': str(e)}


# ============================================================
# 管理面板窗口
# ============================================================

STYLE_DARK = """
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Microsoft YaHei";
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: #FFD900;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLabel {
    color: #c0c0c0;
}
QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #FFD900;
}
QLabel#statValue {
    color: #FFD900;
    font-weight: bold;
}
QLabel#statLabel {
    color: #888;
}
QPushButton {
    background-color: #2a2a4a;
    color: #FFD900;
    border: 1px solid #FFD900;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #3a3a5a;
    border-color: #FFF;
    color: #FFF;
}
QPushButton:pressed {
    background-color: #1a1a3a;
}
QPushButton:disabled {
    background-color: #1a1a2e;
    color: #555;
    border-color: #444;
}
QPushButton#primaryBtn {
    background-color: #FFD900;
    color: #1a1a2e;
    border: 1px solid #FFD900;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background-color: #FFE44D;
    color: #1a1a2e;
    border-color: #FFF;
}
QPushButton#primaryBtn:disabled {
    background-color: #555;
    color: #999;
    border-color: #555;
}
QPushButton#dangerBtn {
    border-color: #FF6B6B;
    color: #FF6B6B;
}
QPushButton#dangerBtn:hover {
    background-color: #4a2a2a;
    color: #FF8888;
}
QPushButton#successBtn {
    border-color: #33FF66;
    color: #33FF66;
}
QPushButton#successBtn:hover {
    background-color: #2a4a2a;
    color: #66FF99;
}
QProgressBar {
    border: 1px solid #3a3a5c;
    border-radius: 3px;
    background-color: #2a2a4a;
    text-align: center;
    color: #FFD900;
}
QProgressBar::chunk {
    background-color: #FFD900;
    border-radius: 2px;
}
QFrame#sep {
    background-color: #3a3a5c;
    max-height: 1px;
}
"""


class ManagementPanel(QWidget):
    """WARFRAME-RELIC 管理面板"""

    # 通知外部数据库已更新 / 热键已变更
    db_updated = pyqtSignal(str)       # 携带新的 db_path
    hotkeys_changed = pyqtSignal(dict)  # 携带新的热键字典

    def __init__(self):
        super().__init__()
        self._data_dir = Path(__file__).resolve().parent.parent / 'data'
        self._db_path = str(self._data_dir / 'relics.db')
        self._alljson_path = str(self._data_dir / 'all.json')
        self._worker = None
        self._fetch_worker = None
        self._updating = False
        self._fetching = False

        # 加载热键配置
        self._hotkeys = load_hotkeys()

        self._setup_ui()
        self._refresh_stats()
        self._refresh_hotkey_ui()
        self._first_show = True

    def showEvent(self, event):
        """首次显示时强制更新布局，解决被压缩的问题"""
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            # 延迟一帧让布局完全计算后再调整
            from PyQt6.QtCore import QTimer
            def _fix_size():
                self.updateGeometry()
                self.layout().activate()
                # 重新设置一个合理的最小尺寸
                content_h = self.layout().sizeHint().height()
                self.setMinimumSize(580, max(content_h, 780))
                if self.height() < 680:
                    self.resize(580, 840)
            QTimer.singleShot(50, _fix_size)

    # ============================================================
    # UI 构建
    # ============================================================

    def _setup_ui(self):
        self.setWindowTitle("WARFRAME-RELIC - 管理面板")
        self.setMinimumSize(580, 680)
        self.resize(580, 840)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setStyleSheet(STYLE_DARK)

        # ====== 顶层：水平布局 ======
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ---- 左侧面板（可滚动）----
        from PyQt6.QtWidgets import QScrollArea
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("QScrollArea { border: none; background-color: #1a1a2e; }")

        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #1a1a2e;")
        main_layout = QVBoxLayout(left_widget)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # ---- 标题 ----
        title = QLabel("WARFRAME-RELIC 管理面板")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # ---- 数据库状态组 ----
        status_group = QGroupBox("数据库状态")
        status_layout = QVBoxLayout(status_group)

        # 状态行（网格布局）
        self._stat_labels = {}
        stat_grid = [
            ("遗物总数", "relics"),
            ("部件总数", "parts"),
            ("别名总数", "aliases"),
            ("出库(可获取)", "vaulted"),
            ("入库(不可获取)", "available"),
            ("虚空商人可购买", "voidtrader"),
            ("文件大小", "db_size"),
            ("最后更新", "db_mtime"),
        ]

        for i, (label, key) in enumerate(stat_grid):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("statLabel")
            lbl.setFixedWidth(110)
            val = QLabel("--")
            val.setObjectName("statValue")
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            status_layout.addLayout(row)
            self._stat_labels[key] = val

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._progress.setFixedHeight(6)
        status_layout.addWidget(self._progress)

        # 进度文本
        self._progress_text = QLabel("")
        self._progress_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_text.hide()
        status_layout.addWidget(self._progress_text)

        main_layout.addWidget(status_group)

        # ---- 手动数据更新 ----
        source_group = QGroupBox("手动数据更新")
        source_layout = QVBoxLayout(source_group)

        # 当前 all.json 路径
        self._source_label = QLabel("")
        self._source_label.setWordWrap(True)
        source_layout.addWidget(self._source_label)

        # 选择文件 + 更新按钮
        btn_row = QHBoxLayout()
        self._btn_browse = QPushButton("选择文件...")
        self._btn_browse.clicked.connect(self._on_browse)
        self._btn_update = QPushButton("更新数据库")
        self._btn_update.setObjectName("primaryBtn")
        self._btn_update.clicked.connect(self._on_update)
        self._btn_update.setStyleSheet(
            "QPushButton { background-color: #FFD900; color: #1a1a2e; border: 1px solid #FFD900; "
            "border-radius: 4px; padding: 8px 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #FFE44D; color: #1a1a2e; border-color: #FFF; }"
            "QPushButton:disabled { background-color: #555; color: #999; border-color: #555; }"
        )
        btn_row.addWidget(self._btn_browse)
        btn_row.addWidget(self._btn_update)
        source_layout.addLayout(btn_row)

        main_layout.addWidget(source_group)

        # ---- 自动数据更新 ----
        action_group = QGroupBox("自动数据更新")
        action_layout = QVBoxLayout(action_group)

        # 行1: 拉取最新数据 + 更新数据库
        row_fetch = QHBoxLayout()
        self._btn_fetch = QPushButton("拉取最新数据 (GitHub)")
        self._btn_fetch.setObjectName("primaryBtn")
        self._btn_fetch.clicked.connect(self._on_fetch)
        self._btn_fetch.setStyleSheet(
            "QPushButton { background-color: #FFD900; color: #1a1a2e; border: 1px solid #FFD900; "
            "border-radius: 4px; padding: 8px 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #FFE44D; color: #1a1a2e; border-color: #FFF; }"
            "QPushButton:disabled { background-color: #555; color: #999; border-color: #555; }"
        )
        self._btn_update2 = QPushButton("更新数据库")
        self._btn_update2.clicked.connect(self._on_update)
        row_fetch.addWidget(self._btn_fetch)
        row_fetch.addWidget(self._btn_update2)
        action_layout.addLayout(row_fetch)

        # 行2: 数据更新教程 + 打开目录
        row1 = QHBoxLayout()
        self._btn_tutorial = QPushButton("数据更新教程")
        self._btn_tutorial.setObjectName("successBtn")
        self._btn_tutorial.clicked.connect(self._show_tutorial)
        self._btn_browse_db = QPushButton("打开数据目录")
        self._btn_browse_db.clicked.connect(self._open_data_dir)
        row1.addWidget(self._btn_tutorial)
        row1.addWidget(self._btn_browse_db)
        action_layout.addLayout(row1)

        main_layout.addWidget(action_group)

        # ---- 热键配置组 ----
        hotkey_group = QGroupBox("快捷键设置")
        hotkey_layout = QVBoxLayout(hotkey_group)

        # 提示文字
        hotkey_tip = QLabel("格式: ctrl+g / alt+shift+f 等。修改后立即生效，无需重启。")
        hotkey_tip.setStyleSheet("color: #666; font-size: 11px;")
        hotkey_layout.addWidget(hotkey_tip)

        self._hotkey_editors = {}   # key -> QLineEdit
        self._hotkey_errors = {}    # key -> QLabel (错误提示)

        for key in DEFAULT_HOTKEYS:
            row = QHBoxLayout()

            # 功能名
            lbl_func = QLabel(HOTKEY_LABELS.get(key, key))
            lbl_func.setStyleSheet("color: #c0c0c0; font-size: 12px;")
            lbl_func.setFixedWidth(100)
            row.addWidget(lbl_func)

            # 输入框
            edit = QLineEdit()
            edit.setPlaceholderText("如 ctrl+g")
            edit.setStyleSheet("""
                QLineEdit {
                    background-color: #0d0d1a;
                    color: #FFD900;
                    border: 1px solid #3a3a5c;
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-family: "Consolas", "Microsoft YaHei";
                    font-size: 12px;
                }
                QLineEdit:focus {
                    border-color: #FFD900;
                }
            """)
            edit.setFixedWidth(140)
            row.addWidget(edit)

            # 错误提示
            err = QLabel("")
            err.setStyleSheet("color: #FF4444; font-size: 11px;")
            row.addWidget(err)
            row.addStretch()

            hotkey_layout.addLayout(row)
            self._hotkey_editors[key] = edit
            self._hotkey_errors[key] = err

        # 保存 + 重置按钮
        btn_row = QHBoxLayout()
        self._btn_save_hotkeys = QPushButton("保存快捷键")
        self._btn_save_hotkeys.setObjectName("primaryBtn")
        self._btn_save_hotkeys.clicked.connect(self._on_save_hotkeys)
        self._btn_save_hotkeys.setStyleSheet(
            "QPushButton { background-color: #FFD900; color: #1a1a2e; border: 1px solid #FFD900; "
            "border-radius: 4px; padding: 8px 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #FFE44D; color: #1a1a2e; border-color: #FFF; }"
            "QPushButton:disabled { background-color: #555; color: #999; border-color: #555; }"
        )
        self._btn_reset_hotkeys = QPushButton("恢复默认")
        self._btn_reset_hotkeys.clicked.connect(self._on_reset_hotkeys)
        btn_row.addWidget(self._btn_save_hotkeys)
        btn_row.addWidget(self._btn_reset_hotkeys)
        btn_row.addStretch()
        hotkey_layout.addLayout(btn_row)

        main_layout.addWidget(hotkey_group)

        # ---- 关于作者 ----
        about_group = QGroupBox("关于作者")
        about_layout = QVBoxLayout(about_group)
        about_layout.setSpacing(4)

        # 作者信息
        author_row = QHBoxLayout()
        author_label = QLabel("作者: NeonXi (B站: MichaelJackso2)")
        author_label.setStyleSheet("color: #c0c0c0; font-size: 12px;")
        author_row.addWidget(author_label)
        author_row.addStretch()
        about_layout.addLayout(author_row)

        # Bilibili 链接按钮
        bili_row = QHBoxLayout()
        bili_icon = QLabel("📺")
        bili_icon.setStyleSheet("font-size: 14px;")
        self._btn_bilibili = QPushButton("Bilibili 主页 →")
        self._btn_bilibili.setObjectName("bilibiliBtn")
        self._btn_bilibili.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_bilibili.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #FB7299;
                border: none;
                padding: 4px 0px;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover {
                color: #FF8DB0;
            }
        """)
        self._btn_bilibili.clicked.connect(self._open_bilibili)
        bili_row.addWidget(bili_icon)
        bili_row.addWidget(self._btn_bilibili, 1)
        about_layout.addLayout(bili_row)

        # 项目信息
        project_row = QHBoxLayout()
        project_label = QLabel("WARFRAME-RELIC v1.0")
        project_label.setStyleSheet("color: #666; font-size: 11px;")
        project_row.addWidget(project_label)
        project_row.addStretch()
        about_layout.addLayout(project_row)

        main_layout.addWidget(about_group)

        # ---- 底部提示 ----
        tip = QLabel("提示: 按 Ctrl+Shift+G 可随时唤出此面板 | 主程序 Ctrl+G 框选截图")
        tip.setStyleSheet("color: #666; font-size: 11px;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(tip)

        # 左侧面板添加弹性空间
        main_layout.addStretch()

        left_scroll.setWidget(left_widget)
        left_scroll.setMinimumWidth(580)
        outer_layout.addWidget(left_scroll, 1)  # stretch=1，默认占全部

        # ---- 右侧日志面板（初始隐藏）----
        self._log_panel = QWidget()
        self._log_panel.setStyleSheet("background-color: #12122a;")
        self._log_panel.setMinimumWidth(420)
        self._log_panel.setMaximumWidth(520)
        self._log_panel.hide()  # 平时隐藏

        log_layout = QVBoxLayout(self._log_panel)
        log_layout.setContentsMargins(12, 12, 12, 12)
        log_layout.setSpacing(8)

        # 日志标题
        log_title = QLabel("运行日志")
        log_title.setStyleSheet("color: #FFD900; font-size: 14px; font-weight: bold;")
        log_layout.addWidget(log_title)

        # 分隔线
        sep_log = QFrame()
        sep_log.setObjectName("sep")
        sep_log.setFrameShape(QFrame.Shape.HLine)
        log_layout.addWidget(sep_log)

        # 当前步骤指示
        step_row = QHBoxLayout()
        self._step_icon = QLabel("⏳")
        self._step_icon.setStyleSheet("font-size: 20px;")
        self._step_icon.setFixedWidth(32)
        self._step_label = QLabel("等待操作...")
        self._step_label.setStyleSheet("color: #888; font-size: 13px;")
        self._step_label.setWordWrap(True)
        step_row.addWidget(self._step_icon)
        step_row.addWidget(self._step_label, 1)
        log_layout.addLayout(step_row)

        # 下载进度条
        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 100)
        self._dl_progress.setValue(0)
        self._dl_progress.setFixedHeight(18)
        self._dl_progress.setFormat("%p%")
        self._dl_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a5c;
                border-radius: 4px;
                background-color: #1a1a3a;
                text-align: center;
                color: #FFD900;
                font-size: 11px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FFD900, stop:1 #FFA500);
                border-radius: 3px;
            }
        """)
        log_layout.addWidget(self._dl_progress)

        # 详细状态信息
        self._log_detail = QLabel("")
        self._log_detail.setStyleSheet("color: #AAAACC; font-size: 11px; padding: 4px 0;")
        self._log_detail.setWordWrap(True)
        log_layout.addWidget(self._log_detail)

        # 日志文本区域（滚动）
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet("""
            QTextEdit {
                background-color: #0d0d1a;
                color: #ccc;
                border: 1px solid #333;
                border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px;
                padding: 8px;
            }
            QScrollBar:vertical {
                background: #1a1a2e;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #3a3a5c;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self._log_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        log_layout.addWidget(self._log_area, 1)  # stretch=1，占据剩余空间

        # 关闭日志按钮
        self._btn_close_log = QPushButton("关闭日志面板")
        self._btn_close_log.clicked.connect(self._hide_log_panel)
        self._btn_close_log.setStyleSheet("""
            QPushButton {
                background-color: #2a2a4a;
                color: #AAA;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3a3a5a;
                color: #FFF;
            }
        """)
        log_layout.addWidget(self._btn_close_log)

        outer_layout.addWidget(self._log_panel)  # 初始不占空间（已 hide）

    # ============================================================
    # 逻辑
    # ============================================================

    def add_log(self, log_type: str = "info", msg: str = ""):
        """外部调用：向右侧日志面板追加一条日志

        log_type: "ok"(绿), "warn"(橙), "error"(红), "info"(灰)
        如果日志面板未显示，会自动显示
        """
        # 自动显示日志面板
        if not self._log_panel.isVisible():
            self._show_log_panel()
        now = datetime.now().strftime("%H:%M:%S")
        colors = {
            "ok":    "#33FF66",
            "warn":  "#FFAA33",
            "error": "#FF4444",
            "info":  "#AAAACC",
        }
        color = colors.get(log_type, "#CCC")
        prefix = {"ok": "✓", "warn": "⚠", "error": "✗", "info": "  "}
        p = prefix.get(log_type, " ")
        self._log_area.append(
            f'<span style="color:#666;">[{now}]</span> <span style="color:{color};">{p} {msg}</span>'
        )
        # 自动滚动到底部
        self._log_area.verticalScrollBar().setValue(
            self._log_area.verticalScrollBar().maximum()
        )

    def _refresh_stats(self):
        """刷新数据库统计信息显示"""
        stats = _get_db_stats(self._db_path)

        if not stats.get('exists'):
            self._stat_labels['relics'].setText("数据库不存在")
            for k in ['parts', 'aliases', 'vaulted', 'available', 'voidtrader', 'db_size', 'db_mtime']:
                self._stat_labels[k].setText("--")
            return

        self._stat_labels['relics'].setText(str(stats['relics']))
        self._stat_labels['parts'].setText(str(stats['parts']))
        self._stat_labels['aliases'].setText(str(stats['aliases']))

        # 颜色区分出库/入库/虚空商人
        self._stat_labels['vaulted'].setText(f"{stats['vaulted']}  (绿色可获取)")
        self._stat_labels['vaulted'].setStyleSheet("color: #33FF66; font-weight: bold;")
        self._stat_labels['available'].setText(f"{stats['available']}  (红色不可获取)")
        self._stat_labels['available'].setStyleSheet("color: #FF6B6B; font-weight: bold;")
        self._stat_labels['voidtrader'].setText(f"{stats.get('voidtrader', 0)}  (功能未实现)")
        self._stat_labels['voidtrader'].setStyleSheet("color: #448AFF; font-weight: bold;")

        # 文件大小
        size_kb = stats['db_size'] / 1024
        self._stat_labels['db_size'].setText(f"{size_kb:.1f} KB")

        self._stat_labels['db_mtime'].setText(stats['db_mtime'])

        # 数据源路径
        if os.path.exists(self._alljson_path):
            self._source_label.setText(f"当前: {self._alljson_path}")
            self._source_label.setStyleSheet("color: #33FF66;")
        else:
            self._source_label.setText(f"all.json 未找到: {self._alljson_path}")
            self._source_label.setStyleSheet("color: #FF6B6B;")

    # ============================================================
    # 热键配置
    # ============================================================

    def _refresh_hotkey_ui(self):
        """将当前热键配置填充到输入框"""
        for key, edit in self._hotkey_editors.items():
            edit.setText(self._hotkeys.get(key, ""))
            # 清空错误提示
            if key in self._hotkey_errors:
                self._hotkey_errors[key].setText("")

    def _on_save_hotkeys(self):
        """保存热键配置"""
        new_hotkeys = {}
        has_error = False

        for key, edit in self._hotkey_editors.items():
            val = edit.text().strip().lower()
            new_hotkeys[key] = val

            if not val:
                self._hotkey_errors[key].setText("不能为空")
                has_error = True
            elif not validate_hotkey(val):
                self._hotkey_errors[key].setText("格式错误")
                has_error = True
            else:
                self._hotkey_errors[key].setText("")

        if has_error:
            QMessageBox.warning(self, "格式错误", "请修正红色提示的快捷键格式。\n\n正确格式如: ctrl+g / alt+shift+f / ctrl+shift+g")
            return

        # 保存到文件
        if save_hotkeys(new_hotkeys):
            self._hotkeys = new_hotkeys
            self._refresh_hotkey_ui()
            # 通知 main.py 重新绑定热键
            self.hotkeys_changed.emit(self._hotkeys)
            QMessageBox.information(self, "保存成功", "快捷键已更新，立即生效！")
        else:
            QMessageBox.critical(self, "保存失败", "无法写入配置文件，请检查磁盘空间和权限。")

    def _on_reset_hotkeys(self):
        """恢复默认热键"""
        reply = QMessageBox.question(
            self, "恢复默认",
            "确定要恢复默认快捷键吗？\n\n"
            f"框选截图: {DEFAULT_HOTKEYS['select']}\n"
            f"全屏截图: {DEFAULT_HOTKEYS['fullscreen']}\n"
            f"管理面板: {DEFAULT_HOTKEYS['panel']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if save_hotkeys({}):  # 空字典 = 删除自定义配置，恢复默认
            self._hotkeys = dict(DEFAULT_HOTKEYS)
            self._refresh_hotkey_ui()
            self.hotkeys_changed.emit(self._hotkeys)
            QMessageBox.information(self, "已恢复", "快捷键已恢复为默认值。")

    def _show_error_dialog(self, title: str, message: str):
        """显示可复制文本的错误/信息弹窗"""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(480, 320)
        dlg.resize(550, 380)
        dlg.setStyleSheet(STYLE_DARK)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        label = QLabel(title)
        label.setStyleSheet("color: #FF4444; font-size: 14px; font-weight: bold;")
        layout.addWidget(label)

        text = QTextEdit()
        text.setReadOnly(False)           # 允许选中复制
        text.setPlainText(message)
        text.setStyleSheet("""
            QTextEdit {
                background-color: #0d0d1a;
                color: #ccc;
                border: 1px solid #333;
                border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 12px;
                padding: 8px;
            }
        """)
        layout.addWidget(text, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("""
            QPushButton {
                background-color: #2a2a4a;
                color: #FFD900;
                border: 1px solid #FFD900;
                border-radius: 4px;
                padding: 6px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a5a;
                color: #FFF;
            }
        """)
        layout.addWidget(btn_box)

        dlg.exec()

    def _on_browse(self):
        """浏览选择 all.json 文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 WFInfo 数据文件",
            str(self._data_dir),
            "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if path:
            self._alljson_path = path
            self._source_label.setText(f"当前: {self._alljson_path}")
            self._source_label.setStyleSheet("color: #FFD900;")
            self._refresh_stats()

    def _on_fetch(self):
        """从 GitHub 拉取最新 all.json"""
        if self._fetching or self._updating:
            return

        # 确认
        reply = QMessageBox.question(
            self, "拉取最新数据",
            f"将从 GitHub 下载最新 all.json:\n\n"
            f"{ALLJSON_URL}\n\n"
            f"保存到: {self._alljson_path}\n"
            f"下载完成后将自动更新数据库。\n\n"
            "确认继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 显示右侧日志面板
        self._show_log_panel()

        # 清空日志区域
        self._log_area.clear()
        self._log_area.append('<span style="color:#888;">========== 开始拉取数据 ==========</span>')
        self._log_area.append(f'<span style="color:#AAAACC;">  源地址: {ALLJSON_URL}</span>')
        self._log_area.append(f'<span style="color:#AAAACC;">  保存到: {self._alljson_path}</span>')
        self._dl_progress.setValue(0)
        self._step_icon.setText("⏳")
        self._step_label.setText("准备中...")
        self._step_label.setStyleSheet("color: #FFD900; font-size: 13px;")
        self._log_detail.setText("等待开始...")

        # 禁用按钮
        self._fetching = True
        self._btn_fetch.setEnabled(False)
        self._btn_update.setEnabled(False)
        self._btn_update2.setEnabled(False)
        self._btn_browse.setEnabled(False)
        self._progress.show()
        self._progress_text.show()
        self._progress_text.setText("正在下载数据...")

        # 启动后台线程下载
        self._fetch_worker = FetchWorker(self._alljson_path)
        self._fetch_worker.step_changed.connect(self._on_fetch_step)
        self._fetch_worker.log.connect(self._on_fetch_log)
        self._fetch_worker.progress_pct.connect(self._on_fetch_progress)
        self._fetch_worker.finished.connect(self._on_fetch_finished)
        self._fetch_worker.error.connect(self._on_fetch_error)

        thread = threading.Thread(target=self._fetch_worker.run, daemon=True)
        thread.start()

    def _on_fetch_step(self, step: int, desc: str):
        """当前步骤更新"""
        step_details = {
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
        self._step_label.setStyleSheet("color: #FFD900; font-size: 13px;")
        self._log_detail.setText(step_details.get(step, desc))
        self._log_area.append(f'<span style="color:#FFD900;">▶ [{step}/7] {desc}</span>')

    def _on_fetch_log(self, log_type: str, msg: str):
        """追加日志行（带时间戳）"""
        now = datetime.now().strftime("%H:%M:%S")
        colors = {
            "ok":    "#33FF66",
            "warn":  "#FFAA33",
            "error": "#FF4444",
            "info":  "#AAAACC",
        }
        color = colors.get(log_type, "#CCC")
        prefix = {"ok": "✓", "warn": "⚠", "error": "✗", "info": "  "}
        p = prefix.get(log_type, " ")
        self._log_area.append(f'<span style="color:#666;">[{now}]</span> <span style="color:{color};">{p} {msg}</span>')
        # 自动滚动到底部
        self._log_area.verticalScrollBar().setValue(
            self._log_area.verticalScrollBar().maximum()
        )

    def _on_fetch_progress(self, pct: int):
        """更新下载进度条和详情"""
        self._dl_progress.setValue(pct)
        self._log_detail.setText(f"正在下载... 已完成 {pct}%，请耐心等待")

    def _on_fetch_finished(self, save_path: str):
        """下载完成 → 自动触发数据库更新"""
        self._alljson_path = save_path
        self._source_label.setText(f"当前: {self._alljson_path}")
        self._source_label.setStyleSheet("color: #33FF66;")

        self._step_icon.setText("✅")
        self._step_label.setText("下载成功！")
        self._step_label.setStyleSheet("color: #33FF66; font-size: 13px;")
        self._log_detail.setText("下载完成，正在自动更新数据库...")

        self._progress_text.setText("下载完成，开始更新数据库...")

        # ★ 注意：_fetching 仍为 True，这样 _on_update 会跳过确认弹窗
        # 自动触发更新（_on_update 完成后会恢复按钮状态）
        self._on_update()
        self._fetching = False

    def _on_fetch_error(self, msg: str):
        """下载失败"""
        self._fetching = False
        self._btn_fetch.setEnabled(True)
        self._btn_update.setEnabled(True)
        self._btn_update2.setEnabled(True)
        self._btn_browse.setEnabled(True)
        self._progress.hide()
        self._progress_text.hide()

        self._step_icon.setText("❌")
        self._step_label.setText("下载失败")
        self._step_label.setStyleSheet("color: #FF4444; font-size: 13px;")
        self._log_detail.setText(f"下载失败: {msg[:200]}")
        self._log_area.append(f'<span style="color:#FF4444;">  ✗ 失败: {msg}</span>')
        self._log_area.append(f'<span style="color:#FFAA33;">  → 请手动下载: {ALLJSON_URL}</span>')
        self._log_area.append(f'<span style="color:#FFAA33;">  → 保存到: {self._alljson_path}</span>')
        self._log_area.append('<span style="color:#888;">========== 拉取失败 ==========</span>')

        self._show_error_dialog(
            "下载失败",
            f"无法从 GitHub 拉取数据:\n{msg}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"请手动下载:\n"
            f"{ALLJSON_URL}\n\n"
            f"保存到:\n"
            f"{self._alljson_path}\n\n"
            f"保存后点击「更新数据库」按钮即可。\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    # ============================================================
    # 数据库更新
    # ============================================================

    def _on_update(self):
        """执行数据库更新"""
        if self._updating:
            return

        if not os.path.exists(self._alljson_path):
            QMessageBox.warning(self, "文件不存在", f"找不到数据文件:\n{self._alljson_path}")
            return

        # 如果是 fetch 触发的自动更新，跳过确认弹窗
        if not self._fetching:
            reply = QMessageBox.question(
                self, "确认更新",
                f"将从以下文件更新数据库:\n{self._alljson_path}\n\n"
                f"目标: {self._db_path}\n\n"
                "此操作会覆盖现有数据库。确认继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 禁用按钮
        self._updating = True
        self._btn_update.setEnabled(False)
        self._btn_update2.setEnabled(False)
        self._btn_fetch.setEnabled(False)
        self._btn_browse.setEnabled(False)
        self._progress.show()
        self._progress_text.show()
        self._progress_text.setText("正在准备...")

        # 启动后台线程
        self._worker = UpdateWorker(self._alljson_path, self._db_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)

        thread = threading.Thread(target=self._worker.run, daemon=True)
        thread.start()

    def _on_progress(self, msg: str):
        self._progress_text.setText(msg)
        if self._log_panel.isVisible():
            self._log_detail.setText(f"数据库更新: {msg}")

    def _on_finished(self, stats: dict):
        self._updating = False
        self._btn_update.setEnabled(True)
        self._btn_update2.setEnabled(True)
        self._btn_fetch.setEnabled(True)
        self._btn_browse.setEnabled(True)
        self._progress.hide()
        self._progress_text.hide()

        self._refresh_stats()

        # 如果日志面板是拉取触发的，追加更新结果
        if self._log_panel.isVisible():
            self._step_icon.setText("✅")
            self._step_label.setText("全部完成！")
            self._step_label.setStyleSheet("color: #33FF66; font-size: 13px;")
            dropping = stats.get('dropping', 0)
            total = stats.get('relics', 0)
            vaulted_count = total - dropping
            detail_text = (
                f"数据库更新成功！\n"
                f"  遗物: {total} | 部件: {stats.get('parts', 0)} | 别名: {stats.get('aliases', 0)}\n"
                f"  出库: {dropping} | 入库: {vaulted_count}"
            )
            self._log_detail.setText(detail_text)
            self._log_area.append(f'<span style="color:#33FF66;">  ✓ 数据库更新完成 (遗物 {total} 个)</span>')
            self._log_area.append('<span style="color:#888;">========== 全部完成 ==========</span>')

        # 弹窗显示结果
        dropping = stats.get('dropping', 0)
        total = stats.get('relics', 0)
        msg = (
            f"数据库更新成功!\n\n"
            f"遗物数: {total}\n"
            f"部件数: {stats.get('parts', 0)}\n"
            f"别名数: {stats.get('aliases', 0)}\n"
            f"出库:   {dropping} 个\n"
            f"入库:   {total - dropping} 个\n"
        )
        QMessageBox.information(self, "更新完成", msg)

        # 通知 main.py 重新加载数据库
        self.db_updated.emit(self._db_path)

    def _on_error(self, msg: str):
        self._updating = False
        self._btn_update.setEnabled(True)
        self._btn_update2.setEnabled(True)
        self._btn_fetch.setEnabled(True)
        self._btn_browse.setEnabled(True)
        self._progress.hide()
        self._progress_text.hide()

        self._show_error_dialog("更新失败", f"数据库更新出错:\n{msg}")

    def _show_tutorial(self):
        """显示数据更新教程"""
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
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("数据更新教程")
        dlg.setMinimumSize(520, 560)
        dlg.resize(560, 600)
        dlg.setStyleSheet(STYLE_DARK)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(tutorial_text)
        text.setStyleSheet("""
            QTextEdit {
                background-color: #0d0d1a;
                color: #ccc;
                border: 1px solid #333;
                border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 12px;
                padding: 8px;
            }
        """)
        layout.addWidget(text, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("""
            QPushButton {
                background-color: #2a2a4a;
                color: #FFD900;
                border: 1px solid #FFD900;
                border-radius: 4px;
                padding: 6px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a5a;
                color: #FFF;
            }
        """)
        layout.addWidget(btn_box)

        dlg.exec()

    def _open_bilibili(self):
        """打开作者 Bilibili 主页"""
        import webbrowser
        webbrowser.open("https://space.bilibili.com/21001459")

    def _open_data_dir(self):
        """打开数据目录"""
        os.startfile(str(self._data_dir))

    # ============================================================
    # 日志面板显示/隐藏
    # ============================================================

    def _show_log_panel(self):
        """显示右侧日志面板，窗口变宽"""
        self._log_panel.show()
        # 窗口加宽以容纳右侧面板
        self.resize(1020, max(self.height(), 700))

    def _hide_log_panel(self):
        """隐藏右侧日志面板，窗口恢复原始宽度"""
        self._log_panel.hide()
        self.resize(580, max(self.height(), 700))

    # ============================================================
    # 窗口关闭
    # ============================================================

    def closeEvent(self, event):
        """关闭窗口时仅隐藏，不销毁，避免影响主程序功能"""
        if self._updating:
            event.ignore()
            return
        # 关闭日志面板（如果有打开）
        if self._log_panel.isVisible():
            self._hide_log_panel()
        self.hide()
        event.ignore()  # 阻止默认关闭行为（销毁窗口）
