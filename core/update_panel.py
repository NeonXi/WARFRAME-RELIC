"""
WARFRAME-RELIC 数据更新面板 & 日志面板
- 数据拉取（GitHub）、数据库更新、日志输出
- 作为 ManagementPanel 的子面板存在
"""
import os
import sqlite3
import threading
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QProgressBar, QMessageBox, QGroupBox,
    QDialog, QDialogButtonBox, QTextEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from core.constants import theme
from core.stylesheet import build_stylesheet, build_dialog_button_style
from core.update_worker import UpdateWorker
from core.fetch_worker import FetchWorker, ALLJSON_URL


# ============================================================
# 数据库统计工具
# ============================================================

def get_db_stats(db_path: str) -> dict:
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
# 更新 & 日志面板
# ============================================================

class UpdatePanel(QObject):
    """管理 ManagementPanel 中的数据更新区和日志面板。

    通过回调与 ManagementPanel 通信。
    """

    db_updated = pyqtSignal(str)

    _TEXTEDIT_STYLE = (
        "QTextEdit {{"
        "  background-color: {bg}; color: {fg};"
        "  border: 1px solid {border}; border-radius: 4px;"
        "  font-family: \"Consolas\", \"Microsoft YaHei\", monospace;"
        "  font-size: 12px; padding: 8px;"
        "}}"
    )

    def __init__(self, parent_widget, data_dir: Path, db_path: str, add_log):
        """
        Args:
            parent_widget: ManagementPanel 实例
            data_dir: data 目录路径
            db_path: 数据库路径
            add_log: 日志回调 (log_type, msg)
        """
        super().__init__()
        self._parent = parent_widget
        self._data_dir = data_dir
        self._db_path = db_path
        self._alljson_path = str(data_dir / 'all.json')
        self._add_log = add_log

        self._worker = None
        self._fetch_worker = None
        self._updating = False
        self._fetching = False
        self._log_panel_auto_show = False

        # 统计标签
        self._stat_labels = {}

        # UI 组件引用（由 ManagementPanel 的 _build_* 方法设置）
        self._source_label = None
        self._progress = None
        self._progress_text = None
        self._btn_update = None
        self._btn_update2 = None
        self._btn_fetch = None
        self._btn_browse = None
        self._btn_browse_db = None
        self._btn_tutorial = None

        # 日志面板组件
        self._log_panel = None
        self._log_area = None
        self._step_icon = None
        self._step_label = None
        self._log_detail = None
        self._dl_progress = None
        self._btn_close_log = None

    # ---- 属性设置器（由 ManagementPanel._build_* 调用） ----

    def set_source_label(self, label):
        self._source_label = label

    def set_progress(self, progress, progress_text):
        self._progress = progress
        self._progress_text = progress_text

    def set_buttons(self, btn_update, btn_update2, btn_fetch, btn_browse,
                    btn_browse_db=None, btn_tutorial=None):
        self._btn_update = btn_update
        self._btn_update2 = btn_update2
        self._btn_fetch = btn_fetch
        self._btn_browse = btn_browse
        self._btn_browse_db = btn_browse_db
        self._btn_tutorial = btn_tutorial

    def set_log_panel_widgets(self, log_panel, log_area, step_icon, step_label,
                              log_detail, dl_progress, btn_close_log):
        self._log_panel = log_panel
        self._log_area = log_area
        self._step_icon = step_icon
        self._step_label = step_label
        self._log_detail = log_detail
        self._dl_progress = dl_progress
        self._btn_close_log = btn_close_log

    @property
    def log_panel_visible(self):
        return self._log_panel and self._log_panel.isVisible()

    @property
    def is_busy(self):
        return self._updating or self._fetching

    # ============================================================
    # 统计刷新
    # ============================================================

    def refresh_stats(self):
        """刷新数据库统计信息到 UI 标签。"""
        stats = get_db_stats(self._db_path)
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

    def refresh_inline_styles(self):
        """刷新数据更新区 & 日志面板中所有颜色相关的内联样式。"""
        t = theme

        self._log_panel.setStyleSheet(f"background-color: {t.panel_darkest};")
        self._step_label.setStyleSheet(f"color: {t.text_dim}; font-size: 13px;")
        self._log_detail.setStyleSheet(f"color: {t.cyber_cyan}; font-size: 11px; padding: 4px 0;")
        self._log_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t.panel_deeper}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px; padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {t.panel_bg}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {t.border}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        self._btn_close_log.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.card_bg}; color: {t.text_dim};
                border: 1px solid {t.border}; border-radius: 4px;
                padding: 6px; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {t.btn_hover_bg}; color: {t.text};
            }}
        """)
        self._dl_progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {t.border}; border-radius: 3px;
                background-color: {t.card_bg}; text-align: center;
                color: {t.cyber_yellow};
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.progress_gradient_start},
                    stop:0.5 {t.progress_gradient_mid},
                    stop:1 {t.progress_gradient_end});
                border-radius: 2px;
            }}
        """)

        # 数据状态颜色
        for key, color_key in [('vaulted', 'cyber_green'), ('available', 'cyber_red'),
                                ('voidtrader', 'cyber_cyan')]:
            lbl = self._stat_labels.get(key)
            if lbl:
                lbl.setStyleSheet(f"color: {getattr(t, color_key)}; font-weight: bold;")

    def set_stat_labels(self, stat_labels: dict):
        """注入统计标签引用。"""
        self._stat_labels = stat_labels

    # ============================================================
    # 日志
    # ============================================================

    def add_log(self, log_type: str, msg: str):
        """添加日志到日志面板。"""
        if not self._log_panel.isVisible() and self._log_panel_auto_show:
            self._show_log_panel()
        self._log_area.append(self._format_log_line(log_type, msg))
        self._log_area.verticalScrollBar().setValue(
            self._log_area.verticalScrollBar().maximum())

    def enable_auto_show(self):
        self._log_panel_auto_show = True

    # ============================================================
    # 日志面板显示/隐藏
    # ============================================================

    def _show_log_panel(self):
        self._log_panel.show()
        # 通知父窗口调整宽度
        extra_w = getattr(self._parent, '_theme_panel_width', 0) + 420
        self._parent.resize(580 + extra_w, max(self._parent.height(), 700))

    def _hide_log_panel(self):
        self._log_panel.hide()
        extra_w = getattr(self._parent, '_theme_panel_width', 0)
        self._parent.resize(580 + extra_w, max(self._parent.height(), 700))

    def show_log_panel(self):
        self._show_log_panel()

    def hide_log_panel(self):
        self._hide_log_panel()

    # ============================================================
    # 数据更新操作
    # ============================================================

    def on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self._parent, "选择 WFInfo 数据文件", str(self._data_dir),
            "JSON 文件 (*.json);;所有文件 (*.*)")
        if path:
            self._alljson_path = path
            self._source_label.setText(f"当前: {self._alljson_path}")
            self._source_label.setStyleSheet(f"color: {theme.cyber_yellow};")
            self.refresh_stats()

    def on_fetch(self):
        if self._fetching or self._updating:
            return
        reply = QMessageBox.question(
            self._parent, "拉取最新数据",
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
        self._dl_progress.show()
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

    def on_update(self):
        if self._updating:
            return
        if not os.path.exists(self._alljson_path):
            QMessageBox.warning(self._parent, "文件不存在", f"找不到数据文件:\n{self._alljson_path}")
            return
        if not self._fetching:
            reply = QMessageBox.question(
                self._parent, "确认更新",
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

        # 打开日志面板并记录开始信息
        self._show_log_panel()
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">========== 开始更新数据库 ==========</span>')
        self._log_area.append(
            f'<span style="color:{theme.cyber_cyan};">  数据源: {self._alljson_path}</span>')
        self._log_area.append(
            f'<span style="color:{theme.cyber_cyan};">  目标库: {self._db_path}</span>')
        self._step_icon.setText("⏳")
        self._step_label.setText("正在更新数据库...")
        self._step_label.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 13px;")
        self._log_detail.setText("正在读取数据文件并写入数据库，请耐心等待...")

        self._worker = UpdateWorker(self._alljson_path, self._db_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        threading.Thread(target=self._worker.run, daemon=True).start()

    # ---- Fetch 回调 ----

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
        self._dl_progress.hide()
        self._step_icon.setText("✅")
        self._step_label.setText("下载成功！")
        self._step_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 13px;")
        self._log_detail.setText("下载完成，正在自动更新数据库...")
        self._progress_text.setText("下载完成，开始更新数据库...")
        self.on_update()
        self._fetching = False

    def _on_fetch_error(self, msg):
        self._fetching = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        self._dl_progress.hide()
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
        # 不再弹窗，日志区已显示错误详情和手动下载指引

    # ---- Update 回调 ----

    def _on_progress(self, msg):
        self._progress_text.setText(msg)
        if self._log_panel.isVisible():
            self._log_detail.setText(f"数据库更新: {msg}")
            self._log_area.append(
                f'<span style="color:{theme.cyber_yellow};">  ▶ {msg}</span>')

    def _on_finished(self, stats):
        self._updating = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        self.refresh_stats()

        total = stats.get('relics', 0)
        dropping = stats.get('dropping', 0)

        if self._log_panel.isVisible():
            self._step_icon.setText("✅")
            self._step_label.setText("更新完成！")
            self._step_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 13px;")
            self._log_detail.setText(
                f"数据库更新成功！\n"
                f"  遗物: {total} | 部件: {stats.get('parts', 0)} | "
                f"别名: {stats.get('aliases', 0)}\n"
                f"  出库: {dropping} | 入库: {total - dropping}")

            # 详细汇总日志
            self._log_area.append(
                f'<span style="color:{theme.cyber_green};">━━━━━━━━━━━━━━━━━━━━━━━━</span>')
            self._log_area.append(
                f'<span style="color:{theme.cyber_green};">  ✓ 数据库更新完成</span>')
            self._log_area.append(
                f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
                f'遗物总数: {total} 个</span>')
            self._log_area.append(
                f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
                f'部件总数: {stats.get("parts", 0)} 个</span>')
            self._log_area.append(
                f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
                f'别名总数: {stats.get("aliases", 0)} 个</span>')
            self._log_area.append(
                f'<span style="color:{theme.cyber_green}; display:block; margin-left:20px;">'
                f'出库（可获取）: {dropping} 个</span>')
            self._log_area.append(
                f'<span style="color:{theme.cyber_red}; display:block; margin-left:20px;">'
                f'入库（不可获取）: {total - dropping} 个</span>')
            self._log_area.append(
                f'<span style="color:{theme.text_dim};">========== 更新完成 ==========</span>')

        self.db_updated.emit(self._db_path)

    def _on_error(self, msg):
        self._updating = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        if self._log_panel.isVisible():
            self._step_icon.setText("❌")
            self._step_label.setText("更新失败")
            self._step_label.setStyleSheet(f"color: {theme.fetch_error_color}; font-size: 13px;")
            self._log_detail.setText(f"数据库更新出错: {msg[:200]}")
            self._log_area.append(
                f'<span style="color:{theme.fetch_error_color};">  ✗ 更新失败: {msg}</span>')
            self._log_area.append(
                f'<span style="color:{theme.text_dim};">========== 更新失败 ==========</span>')
        # 不再弹窗，日志区已显示错误详情

    def _set_buttons_enabled(self, enabled: bool):
        for btn in [self._btn_update, self._btn_update2, self._btn_fetch, self._btn_browse]:
            if btn:
                btn.setEnabled(enabled)

    # ============================================================
    # 对话框
    # ============================================================

    def _show_error_dialog(self, title: str, message: str):
        dlg = self._build_text_dialog(title, message, 550, 380, False)
        dlg.exec()

    def _build_text_dialog(self, title: str, text_content: str,
                           width: int = 560, height: int = 600,
                           readonly: bool = True,
                           title_color: str = None) -> QDialog:
        dlg = QDialog(self._parent)
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

    # ============================================================
    # 工具方法
    # ============================================================

    def _format_log_line(self, log_type: str, msg: str) -> str:
        now = datetime.now().strftime("%H:%M:%S")
        color = theme.log_color_map.get(log_type, theme.text)
        prefix_map = {"ok": "✓", "warn": "⚠", "error": "✗", "info": "  "}
        p = prefix_map.get(log_type, " ")
        return (
            f'<span style="color:{theme.log_timestamp};">[{now}]</span> '
            f'<span style="color:{color};">{p} {msg}</span>')

    def show_tutorial(self):
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
