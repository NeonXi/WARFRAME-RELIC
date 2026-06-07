"""
代理镜像配置对话框

允许用户编辑 GitHub 代理镜像列表，并测试连通性。
"""
import threading
from data.ui_strings import S
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QDialogButtonBox, QProgressBar, QTextEdit,
)
from PyQt6.QtCore import pyqtSignal, QObject

from core.constants import theme
from core.theme_proxy import COLOR_BLACK, COLOR_DARK_GRAY
from core.stylesheet import build_stylesheet, build_dialog_button_style
from core.proxy_config import (
    get_mirrors, set_mirrors, get_default_mirrors, get_config_path,
    get_repo_defs, test_repo_mirror, update_test_result, clear_test_results,
)


class _ProxyTestWorker(QObject):
    """后台线程：测试所有代理镜像对所有仓库的连通性。"""

    progress = pyqtSignal(int, str)        # (pct, 描述)
    log = pyqtSignal(str, str)             # (level, msg)
    finished = pyqtSignal(dict)            # (汇总结果)
    error = pyqtSignal(str)               # (错误信息)

    def __init__(self, mirrors: list, timeout: int = 10):
        super().__init__()
        self._mirrors = mirrors
        self._timeout = timeout
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        repos = get_repo_defs()
        total_tests = len(repos) * len(self._mirrors)
        completed = 0
        results = {}

        clear_test_results()

        for repo_name in repos:
            results[repo_name] = {"working": [], "failed": []}
            for idx, mirror in enumerate(self._mirrors):
                if self._cancelled:
                    return
                completed += 1
                pct = int(completed / total_tests * 100)
                self.progress.emit(pct, f"测试 {repo_name} [{idx + 1}/{len(self._mirrors)}]")
                self.log.emit("info", f"  测试: {repo_name} ← 镜像 [{idx}]")

                success = test_repo_mirror(repo_name, mirror, timeout=self._timeout)
                update_test_result(repo_name, idx, success)

                if success:
                    results[repo_name]["working"].append(idx)
                    self.log.emit("ok", f"    ✓ 镜像 [{idx}] 连通")
                else:
                    results[repo_name]["failed"].append(idx)
                    self.log.emit("warn", f"    ✗ 镜像 [{idx}] 不可用")

        self.progress.emit(100, "测试完成")
        self.finished.emit(results)


class ProxyMirrorDialog(QDialog):
    """代理镜像配置对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置 GitHub 代理镜像")
        self.setMinimumSize(600, 520)
        self.resize(640, 560)
        self.setStyleSheet(
            f"QDialog {{ background-color: {theme.panel_bg}; }}"
            + build_stylesheet()
        )

        self._test_worker = None
        self._test_thread = None
        self._build_ui()
        self._load_mirrors()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 标题
        title = QLabel("GitHub 代理镜像列表")
        title.setStyleSheet(
            f"color: {theme.cyber_yellow}; font-size: 14px; font-weight: bold; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        # 说明
        desc = QLabel(
            "每行一个代理镜像 URL 模板。\n"
            "支持占位符: {owner}（仓库所有者）、{repo}（仓库名）\n"
            "拉取失败时按顺序尝试，连通性测试通过的和上次成功的优先使用。"
        )
        desc.setStyleSheet(
            f"color: {theme.text_dim}; font-size: 11px; background: transparent;"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 编辑区
        self._text_edit = QPlainTextEdit()
        self._text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {theme.get_panel_bg_color(160)};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 12px;
                padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {theme.get_panel_bg_color(180)};
                width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.border}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        layout.addWidget(self._text_edit, 1)

        # 配置文件路径提示
        config_path = get_config_path()
        hint = QLabel(f"配置文件: {config_path}\n你也可以直接编辑此文件，修改后无需重启程序即可生效。")
        hint.setStyleSheet(
            f"color: {theme.cyber_cyan}; font-size: 10px; background: transparent;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 测试进度条
        self._test_progress = QProgressBar()
        self._test_progress.setRange(0, 100)
        self._test_progress.setValue(0)
        self._test_progress.setFixedHeight(16)
        self._test_progress.setFormat("  %p%  %v/%m")
        self._test_progress.hide()
        self._test_progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {theme.border}; border-radius: 3px;
                background-color: {theme.card_bg}; text-align: center;
                color: {theme.cyber_yellow}; font-size: 10px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {theme.progress_gradient_start},
                    stop:0.5 {theme.progress_gradient_mid},
                    stop:1 {theme.progress_gradient_end});
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._test_progress)

        # 测试日志区
        self._test_log = QTextEdit()
        self._test_log.setReadOnly(True)
        self._test_log.setMaximumHeight(120)
        self._test_log.hide()
        self._test_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: {theme.get_panel_bg_color(160)};
                color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px; padding: 6px;
            }}
        """)
        layout.addWidget(self._test_log)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_reset = QPushButton(S("proxy_mirror", "reset_default"))
        self._btn_reset.setToolTip("恢复为程序内置的默认代理镜像列表")
        self._btn_reset.clicked.connect(self._on_reset_default)
        self._btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.card_bg}; color: {theme.text_dim};
                border: 1px solid {theme.border}; border-radius: 4px;
                padding: 6px 14px; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.btn_hover_bg}; color: {theme.cyber_orange};
                border-color: {theme.cyber_orange};
            }}
        """)
        btn_row.addWidget(self._btn_reset)

        self._btn_test = QPushButton(S("proxy_mirror", "test_connectivity"))
        self._btn_test.setToolTip("测试所有代理镜像对每个仓库的连通性（每项超时 10 秒）")
        self._btn_test.clicked.connect(self._on_test_connectivity)
        self._btn_test.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.cyber_cyan}; color: {COLOR_BLACK};
                font-weight: bold; border: none; border-radius: 4px;
                padding: 6px 16px; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.cyber_yellow};
            }}
            QPushButton:disabled {{
                background-color: {theme.text_dim}; color: {COLOR_DARK_GRAY};
            }}
        """)
        btn_row.addWidget(self._btn_test)

        btn_row.addStretch()

        # 确定/取消
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            build_dialog_button_style())
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton {{ background-color: {theme.card_bg}; color: {theme.text_dim}; "
            f"border: 1px solid {theme.border}; border-radius: 4px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {theme.btn_hover_bg}; color: {theme.text}; }}"
        )
        btn_row.addWidget(btn_box)
        layout.addLayout(btn_row)

    def _load_mirrors(self):
        """加载当前配置到编辑区。"""
        mirrors = get_mirrors()
        self._text_edit.setPlainText("\n".join(mirrors))

    def _on_reset_default(self):
        """恢复默认镜像列表。"""
        defaults = get_default_mirrors()
        self._text_edit.setPlainText("\n".join(defaults))

    def _on_accept(self):
        """保存并关闭。"""
        text = self._text_edit.toPlainText().strip()
        mirrors = [line.strip() for line in text.split("\n") if line.strip()]
        if mirrors:
            set_mirrors(mirrors)
        self.accept()

    def _on_test_connectivity(self):
        """测试连通性。"""
        # 先保存当前编辑内容
        text = self._text_edit.toPlainText().strip()
        mirrors = [line.strip() for line in text.split("\n") if line.strip()]
        if not mirrors:
            return
        set_mirrors(mirrors)

        # 显示测试 UI
        self._test_progress.setValue(0)
        self._test_progress.show()
        self._test_log.clear()
        self._test_log.show()
        self._btn_test.setEnabled(False)
        self._btn_reset.setEnabled(False)

        # 启动后台测试线程
        self._test_worker = _ProxyTestWorker(mirrors, timeout=10)
        self._test_worker.progress.connect(self._on_test_progress)
        self._test_worker.log.connect(self._on_test_log)
        self._test_worker.finished.connect(self._on_test_finished)
        self._test_worker.error.connect(self._on_test_error)

        self._test_thread = threading.Thread(
            target=self._test_worker.run, daemon=True
        )
        self._test_thread.start()

    def _on_test_progress(self, pct: int, desc: str):
        self._test_progress.setValue(pct)
        self._test_progress.setFormat(f"  {desc}  %p%")

    def _on_test_log(self, level: str, msg: str):
        now = __import__("datetime").datetime.now().strftime("%H:%M:%S")
        color_map = {
            "ok": theme.cyber_green,
            "warn": theme.cyber_orange,
            "error": theme.cyber_red,
            "info": theme.text,
        }
        color = color_map.get(level, theme.text)
        self._test_log.append(
            f'<span style="color:{theme.text_dim};">[{now}]</span> '
            f'<span style="color:{color};">{msg}</span>'
        )

    def _on_test_finished(self, results: dict):
        self._btn_test.setEnabled(True)
        self._btn_reset.setEnabled(True)
        self._test_progress.setFormat("测试完成  %p%")

        # 汇总结果
        repo_names = list(results.keys())
        summary_lines = []
        for repo_name in repo_names:
            r = results[repo_name]
            working = r["working"]
            failed = r["failed"]
            if working:
                summary_lines.append(
                    f'<span style="color:{theme.cyber_green};">'
                    f'✓ {repo_name}: {len(working)} 个可用</span>'
                )
            else:
                summary_lines.append(
                    f'<span style="color:{theme.cyber_red};">'
                    f'✗ {repo_name}: 0 个可用</span>'
                )
        self._test_log.append("")
        self._test_log.append(
            f'<span style="color:{theme.cyber_yellow}; font-weight:bold;">'
            f'{" | ".join(summary_lines)}</span>'
        )
        self._test_log.append(
            f'<span style="color:{theme.text_dim};">测试结果已保存到 {get_config_path()}</span>'
        )

    def _on_test_error(self, err: str):
        self._btn_test.setEnabled(True)
        self._btn_reset.setEnabled(True)
        self._test_log.append(
            f'<span style="color:{theme.cyber_red};">✗ 测试错误: {err}</span>'
        )