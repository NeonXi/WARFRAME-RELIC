"""
WARFRAME-RELIC 数据更新面板 & 日志面板
- 数据拉取（GitHub）、数据库更新、日志输出
- 作为 ManagementPanel 的子面板存在
"""
import os
import re
import sqlite3
import threading
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QProgressBar, QMessageBox, QGroupBox,
    QDialog, QDialogButtonBox, QTextEdit, QTextBrowser,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from core.constants import theme
from core.stylesheet import build_stylesheet, build_dialog_button_style
from core.update_worker import UpdateWorker
from core.fetch_worker import FetchWorker, ALLJSON_URL
from data.ui_strings import S
from data.translation_db import TranslationUpdateWorker, get_translation_db_stats
from data.ui_strings import S


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
        return {'exists': False, 'error': S.format("status", "db_corrupted", error=str(e))}
    except PermissionError as e:
        return {'exists': False, 'error': S.format("status", "db_no_permission", error=str(e))}
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
        self._trans_worker = None
        self._updating = False
        self._fetching = False
        self._trans_updating = False
        self._log_panel_auto_show = False

        # 保存原始日志记录，用于主题切换时重新着色
        self._log_records = []  # [(log_type, msg, source), ...]

        # 统计标签
        self._stat_labels = {}

        # 翻译数据库组件
        self._trans_stat_labels = {}
        self._trans_cat_label = None
        self._btn_update_trans = None
        self._trans_progress = None

        # UI 组件引用（由 ManagementPanel 的 _build_* 方法设置）
        self._source_label = None
        self._progress = None
        self._progress_text = None
        self._btn_update = None
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

    def set_buttons(self, btn_update, btn_fetch, btn_browse,
                    btn_browse_db=None, btn_tutorial=None):
        self._btn_update = btn_update
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
    
    def set_trans_widgets(self, stat_labels: dict, cat_label, btn_update, progress):
        """注入翻译数据库 UI 组件引用。"""
        self._trans_stat_labels = stat_labels
        self._trans_cat_label = cat_label
        self._btn_update_trans = btn_update
        self._trans_progress = progress

    @property
    def log_panel_visible(self):
        return self._log_panel and self._log_panel.isVisible()

    @property
    def is_busy(self):
        return self._updating or self._fetching or self._trans_updating

    # ============================================================
    # 统计刷新
    # ============================================================

    def refresh_stats(self):
        """刷新数据库统计信息到 UI 标签。"""
        stats = get_db_stats(self._db_path)
        if not stats.get('exists'):
            self._stat_labels['relics'].setText(S("status", "db_not_exist"))
            for k in ['parts', 'aliases', 'vaulted', 'available', 'voidtrader', 'db_size', 'db_mtime']:
                self._stat_labels[k].setText(S("status", "placeholder"))
            return

        self._stat_labels['relics'].setText(str(stats['relics']))
        self._stat_labels['parts'].setText(str(stats['parts']))
        self._stat_labels['aliases'].setText(str(stats['aliases']))
        self._stat_labels['vaulted'].setText(str(stats['vaulted']))
        self._stat_labels['vaulted'].setStyleSheet(f"color: {theme.cyber_green}; font-weight: bold;")
        self._stat_labels['available'].setText(str(stats['available']))
        self._stat_labels['available'].setStyleSheet(f"color: {theme.cyber_red}; font-weight: bold;")
        self._stat_labels['voidtrader'].setText(str(stats.get('voidtrader', 0)))
        self._stat_labels['voidtrader'].setStyleSheet(f"color: {theme.cyber_cyan}; font-weight: bold;")
        self._stat_labels['db_size'].setText(f"{stats['db_size'] / 1024:.1f} KB")
        self._stat_labels['db_mtime'].setText(stats['db_mtime'])

        if os.path.exists(self._alljson_path):
            self._source_label.setText(S.format("update", "source_current", path=self._alljson_path))
            self._source_label.setStyleSheet(f"color: {theme.cyber_green};")
        else:
            self._source_label.setText(S.format("update", "source_not_found", path=self._alljson_path))
            self._source_label.setStyleSheet(f"color: {theme.cyber_red};")

        # 翻译库 & 物品库概要
        self._refresh_status_extra_labels()

    def _refresh_status_extra_labels(self):
        """刷新数据库状态区的翻译库和物品库概要标签。"""
        if not hasattr(self, '_status_trans_label') or not self._status_trans_label:
            return

        t = theme
        # 翻译库
        try:
            t_stats = get_translation_db_stats()
            if t_stats.get('exists'):
                self._status_trans_label.setText(
                    S.format("status", "translation_db_fmt", total=t_stats['total'], size=t_stats['db_size']/1024.0))
                self._status_trans_label.setStyleSheet(f"color: {t.cyber_green}; font-size: 11px; padding: 2px 0;")
            else:
                self._status_trans_label.setText(S("status", "translation_db_none"))
                self._status_trans_label.setStyleSheet(f"color: {t.cyber_red}; font-size: 11px; padding: 2px 0;")
        except Exception:
            self._status_trans_label.setText(S("status", "translation_db_error"))
            self._status_trans_label.setStyleSheet(f"color: {t.cyber_red}; font-size: 11px; padding: 2px 0;")

        # 物品库
        try:
            from data.items_i18n import get_db_stats as get_items_stats
            i_stats = get_items_stats()
            if i_stats.get('exists'):
                self._status_items_label.setText(
                    S.format("status", "items_db_fmt", total=i_stats['total'], has_cn=i_stats['has_cn'], size=i_stats['db_size']/1024.0))
                self._status_items_label.setStyleSheet(f"color: {t.cyber_green}; font-size: 11px; padding: 2px 0;")
            else:
                self._status_items_label.setText(S("status", "items_db_none"))
                self._status_items_label.setStyleSheet(f"color: {t.cyber_red}; font-size: 11px; padding: 2px 0;")
        except Exception:
            self._status_items_label.setText(S("status", "items_db_error"))
            self._status_items_label.setStyleSheet(f"color: {t.cyber_red}; font-size: 11px; padding: 2px 0;")

    # ============================================================
    # 翻译数据库统计 & 更新
    # ============================================================

    def refresh_translation_stats(self):
        """刷新翻译数据库统计信息到 UI 标签。"""
        if not self._trans_stat_labels:
            return
        stats = get_translation_db_stats()
        if not stats.get('exists'):
            self._trans_stat_labels['trans_total'].setText(S("status", "db_not_exist"))
            self._trans_stat_labels['db_size'].setText(S("status", "placeholder"))
            self._trans_stat_labels['last_update'].setText(S("status", "placeholder"))
            if self._trans_cat_label:
                self._trans_cat_label.setText("")
            return

        self._trans_stat_labels['trans_total'].setText(S.format("stat_fmt", "trans_count", count=stats['total']))
        self._trans_stat_labels['trans_total'].setStyleSheet(f"color: {theme.cyber_green}; font-weight: bold;")
        self._trans_stat_labels['db_size'].setText(S.format("stat_fmt", "db_size_kb", size=stats['db_size'] / 1024))
        self._trans_stat_labels['last_update'].setText(stats['db_mtime'])

        # 分类详情
        if self._trans_cat_label and stats.get('categories'):
            cat_lines = []
            for cat, count in stats['categories'].items():
                cat_lines.append(S.format("stat_fmt", "cat_detail", cat=cat, count=count))
            self._trans_cat_label.setText("  " + " | ".join(cat_lines))

    def on_update_translation(self, source: str = 'local'):
        """点击「更新翻译库」按钮。

        Args:
            source: 'local' (本地文件) | 'wfcd' (网络拉取) | 'adminroc' (AdminRoc)
        """
        if self._trans_updating or self._updating or self._fetching:
            return

        from data.translation_db import SOURCE_NAMES

        source_name = SOURCE_NAMES.get(source, source)

        reply = QMessageBox.question(
            self._parent, S("update", "trans_confirm_title"),
            S.format("update", "trans_confirm_msg", source=source_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._show_log_panel()
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">========== 开始更新翻译数据库 ==========</span>')
        self._log_area.append(
            f'<span style="color:{theme.cyber_cyan};">  数据源: {source_name}</span>')
        self._step_icon.setText("⬢")
        self._step_label.setText(S("update", "trans_updating"))
        self._step_label.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 13px;")
        self._log_detail.setText(S("update", "trans_updating"))

        self._trans_updating = True
        self._btn_update_trans.setEnabled(False)
        if self._trans_progress:
            self._trans_progress.setValue(0)
            self._trans_progress.show()

        self._trans_worker = TranslationUpdateWorker(source=source)
        self._trans_worker.step_changed.connect(self._on_trans_step)
        self._trans_worker.log.connect(self._on_trans_log)
        self._trans_worker.progress_pct.connect(self._on_trans_progress)
        self._trans_worker.finished.connect(self._on_trans_finished)
        self._trans_worker.error.connect(self._on_trans_error)
        threading.Thread(target=self._trans_worker.run, daemon=True).start()

    def _on_trans_step(self, step: int, desc: str):
        icons = {1: "⏉", 2: "⬢", 3: "⊛", 4: "↓", 5: "⏃", 6: "◉"}
        self._step_icon.setText(icons.get(step, "◷"))
        self._step_label.setText(f"[{step}/6] {desc}")
        self._step_label.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 13px;")
        self._log_area.append(
            f'<span style="color:{theme.cyber_yellow};">▶ [{step}/6] {desc}</span>')

    def _on_trans_log(self, log_type: str, msg: str):
        self._log_area.append(self._format_log_line(log_type, msg))
        self._log_area.verticalScrollBar().setValue(
            self._log_area.verticalScrollBar().maximum())

    def _on_trans_progress(self, pct: int):
        if self._trans_progress:
            self._trans_progress.setValue(pct)
        self._log_detail.setText(S.format("update", "downloading_pct", pct=pct))

    def _on_trans_finished(self, stats: dict):
        self._trans_updating = False
        self._btn_update_trans.setEnabled(True)
        if self._trans_progress:
            self._trans_progress.hide()

        self._step_icon.setText("✔")
        self._step_label.setText(S("update", "trans_done"))
        self._step_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 13px;")
        source_info = stats.get('source', '')
        self._log_detail.setText(
            S.format("update", "trans_success_log", total=stats['total'], source=source_info))

        self._log_area.append(
            f'<span style="color:{theme.cyber_green};">{S("update", "log_update_done_line")}</span>')
        self._log_area.append(
            f'<span style="color:{theme.cyber_green};">{S("update", "log_trans_done")}</span>')
        self._log_area.append(
            f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
            f'{S.format("update", "log_trans_source", source=source_info)}</span>')
        self._log_area.append(
            f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
            f'{S.format("update", "log_trans_total", count=stats["total"])}</span>')
        for cat, count in stats.get('categories', {}).items():
            self._log_area.append(
                f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
                f'{S.format("update", "log_trans_cat", cat=cat, count=count)}</span>')
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">{S("update", "log_trans_finished")}</span>')

        self.refresh_translation_stats()
        # 通知管理面板刷新全物品数据库统计
        if hasattr(self._parent, 'refresh_items_i18n_stats'):
            self._parent.refresh_items_i18n_stats()

    def _on_trans_error(self, msg: str):
        self._trans_updating = False
        self._btn_update_trans.setEnabled(True)
        if self._trans_progress:
            self._trans_progress.hide()

        self._step_icon.setText("✘")
        self._step_label.setText(S("update", "trans_failed"))
        self._step_label.setStyleSheet(f"color: {theme.fetch_error_color}; font-size: 13px;")
        self._log_detail.setText(S.format("update", "trans_error", msg=msg[:200]))

        self._log_area.append(
            f'<span style="color:{theme.fetch_error_color};">{S.format("update", "log_trans_error", msg=msg)}</span>')
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">{S("update", "log_trans_failed_line")}</span>')

    # ============================================================
    # 样式刷新
    # ============================================================

    def refresh_inline_styles(self):
        """刷新数据更新区 & 日志面板中所有颜色相关的内联样式。"""
        t = theme

        self._log_panel.setStyleSheet(f"background-color: transparent;")

        # 重新渲染所有旧日志，应用新主题颜色
        self._refresh_log_colors()
        self._step_label.setStyleSheet(f"color: {t.text_dim}; font-size: 13px;")
        self._log_detail.setStyleSheet(f"color: {t.cyber_cyan}; font-size: 11px; padding: 4px 0;")
        self._log_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t.get_panel_bg_color(160)}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px; padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {t.get_panel_bg_color(180)}; width: 8px; border-radius: 4px;
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

    def set_status_extra_labels(self, trans_label, items_label):
        """注入数据库状态区的翻译库/物品库概要标签。"""
        self._status_trans_label = trans_label
        self._status_items_label = items_label

    # ============================================================
    # 日志
    # ============================================================

    def add_log(self, log_type: str, msg: str, source: str = ""):
        """添加日志到日志面板。"""
        if not self._log_panel.isVisible() and self._log_panel_auto_show:
            self._show_log_panel()
        # 保存原始记录，用于主题切换时重新渲染
        self._log_records.append((log_type, msg, source))
        self._log_area.append(self._format_log_line(log_type, msg, source))
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
        if hasattr(self._parent, '_adjust_window_width'):
            self._parent._adjust_window_width()
        else:
            # 兼容旧逻辑
            extra_w = getattr(self._parent, '_theme_panel_width', 0) + 420
            self._parent.resize(580 + extra_w, max(self._parent.height(), 700))

    def _hide_log_panel(self):
        self._log_panel.hide()
        # 通知父窗口调整宽度
        if hasattr(self._parent, '_adjust_window_width'):
            self._parent._adjust_window_width()
        else:
            # 兼容旧逻辑
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
            self._parent, S("update", "browse_dialog_title"), str(self._data_dir),
            S("update", "browse_filter"))
        if path:
            self._alljson_path = path
            self._source_label.setText(S.format("update", "source_current", path=self._alljson_path))
            self._source_label.setStyleSheet(f"color: {theme.cyber_yellow};")
            self.refresh_stats()

    def on_fetch(self):
        if self._fetching or self._updating:
            return
        reply = QMessageBox.question(
            self._parent, S("update", "fetch_confirm_title"),
            S.format("update", "fetch_confirm_msg", url=ALLJSON_URL, save_path=self._alljson_path),
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
        self._step_label.setText(S("update", "preparing"))
        self._step_label.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 13px;")
        self._log_detail.setText(S("update", "waiting_start"))

        self._fetching = True
        self._set_buttons_enabled(False)
        self._progress.show(); self._progress_text.show()
        self._progress_text.setText(S("update", "download_starting"))

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
            QMessageBox.warning(self._parent, S("update", "file_not_found_title"),
                S.format("update", "file_not_found_msg", path=self._alljson_path))
            return
        if not self._fetching:
            reply = QMessageBox.question(
                self._parent, S("update", "confirm_update_title"),
                S.format("update", "confirm_update_msg", source=self._alljson_path, target=self._db_path),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._updating = True
        self._set_buttons_enabled(False)
        self._progress.show(); self._progress_text.show()
        self._progress_text.setText(S("update", "preparing"))

        # 打开日志面板并记录开始信息
        self._show_log_panel()
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">{S("update", "log_start_update")}</span>')
        self._log_area.append(
            f'<span style="color:{theme.cyber_cyan};">{S.format("update", "log_data_source", path=self._alljson_path)}</span>')
        self._log_area.append(
            f'<span style="color:{theme.cyber_cyan};">{S.format("update", "log_target_db", path=self._db_path)}</span>')
        self._step_icon.setText("⏳")
        self._step_label.setText(S("update", "updating_db"))
        self._step_label.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 13px;")
        self._log_detail.setText(S("update", "reading_data"))

        self._worker = UpdateWorker(self._alljson_path, self._db_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        threading.Thread(target=self._worker.run, daemon=True).start()

    # ---- Fetch 回调 ----

    def _on_fetch_step(self, step, desc):
        details = {
            1: S("update", "fetch_step_1"),
            2: S("update", "fetch_step_2"),
            3: S("update", "fetch_step_3"),
            4: S("update", "fetch_step_4"),
            5: S("update", "fetch_step_5"),
            6: S("update", "fetch_step_6"),
            7: S("update", "fetch_step_7"),
        }
        icons = {1: "⏉", 2: "⬢", 3: "⊛", 4: "⊞", 5: "↓", 6: "✔", 7: "◉"}
        self._step_icon.setText(icons.get(step, "◷"))
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
        self._log_detail.setText(S.format("update", "downloading_pct_wait", pct=pct))

    def _on_fetch_finished(self, save_path):
        self._alljson_path = save_path
        self._source_label.setText(S.format("update", "source_current", path=self._alljson_path))
        self._source_label.setStyleSheet(f"color: {theme.cyber_green};")
        self._dl_progress.hide()
        self._step_icon.setText("✔")
        self._step_label.setText(S("update", "download_success"))
        self._step_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 13px;")
        self._log_detail.setText(S("update", "download_complete"))
        self._progress_text.setText(S("update", "download_complete"))
        self.on_update()
        self._fetching = False

    def _on_fetch_error(self, msg):
        self._fetching = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        self._dl_progress.hide()
        self._step_icon.setText("✘")
        self._step_label.setText(S("update", "download_failed"))
        self._step_label.setStyleSheet(f"color: {theme.fetch_error_color}; font-size: 13px;")
        self._log_detail.setText(S.format("update", "trans_error", msg=msg[:200]))
        self._log_area.append(
            f'<span style="color:{theme.fetch_error_color};">{S.format("update", "log_trans_error", msg=msg)}</span>')
        self._log_area.append(
            f'<span style="color:{theme.fetch_manual_hint};">{S("update", "log_manual_guide_title")}</span>')
        self._log_area.append(
            f'<span style="color:{theme.fetch_manual_hint};">{S.format("update", "log_manual_step1", url=ALLJSON_URL)}</span>')
        self._log_area.append(
            f'<span style="color:{theme.fetch_manual_hint};">{S("update", "log_manual_step2")}</span>')
        self._log_area.append(
            f'<span style="color:{theme.fetch_manual_hint};">{S("update", "log_manual_step3")}</span>')
        self._log_area.append(
            f'<span style="color:{theme.text_dim};">{S("update", "log_fetch_failed_line")}</span>')

    # ---- Update 回调 ----

    def _on_progress(self, msg):
        self._progress_text.setText(msg)
        if self._log_panel.isVisible():
            self._log_detail.setText(S.format("update", "updating_db_detail", msg=msg))
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
            self._step_icon.setText("✔")
            self._step_label.setText(S("update", "update_complete"))
            self._step_label.setStyleSheet(f"color: {theme.cyber_green}; font-size: 13px;")
            self._log_detail.setText(
                S.format("update", "update_success",
                    relics=total, parts=stats.get('parts', 0),
                    aliases=stats.get('aliases', 0), dropping=dropping,
                    vaulted=total - dropping))

            # 详细汇总日志
            self._log_area.append(
                f'<span style="color:{theme.cyber_green};">{S("update", "log_update_done_line")}</span>')
            self._log_area.append(
                f'<span style="color:{theme.cyber_green};">{S("update", "log_update_done")}</span>')
            self._log_area.append(
                f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
                f'{S.format("update", "log_relics_total", count=total)}</span>')
            self._log_area.append(
                f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
                f'{S.format("update", "log_parts_total", count=stats.get("parts", 0))}</span>')
            self._log_area.append(
                f'<span style="color:{theme.text}; display:block; margin-left:20px;">'
                f'{S.format("update", "log_aliases_total", count=stats.get("aliases", 0))}</span>')
            self._log_area.append(
                f'<span style="color:{theme.cyber_green}; display:block; margin-left:20px;">'
                f'{S.format("update", "log_dropping", count=dropping)}</span>')
            self._log_area.append(
                f'<span style="color:{theme.cyber_red}; display:block; margin-left:20px;">'
                f'{S.format("update", "log_vaulted", count=total - dropping)}</span>')
            self._log_area.append(
                f'<span style="color:{theme.text_dim};">{S("update", "log_update_finished")}</span>')

        # 自动跟随更新全物品中英对照数据库
        try:
            from data.items_i18n import auto_rebuild_items_db, get_db_stats as get_items_stats
            self._log_area.append(
                f'<span style="color:{theme.cyber_yellow};">  ⏳ {S("update", "items_rebuilding")}</span>')
            ok = auto_rebuild_items_db(silent=True)
            if ok:
                s = get_items_stats()
                self._log_area.append(
                    f'<span style="color:{theme.cyber_green};">  ✓ {S.format("update", "items_rebuilt", total=s["total"])}</span>')
                if hasattr(self._parent, 'refresh_items_i18n_stats'):
                    self._parent.refresh_items_i18n_stats()
        except Exception:
            pass

        self.db_updated.emit(self._db_path)

    def _on_error(self, msg):
        self._updating = False
        self._set_buttons_enabled(True)
        self._progress.hide(); self._progress_text.hide()
        if self._log_panel.isVisible():
            self._step_icon.setText("✘")
            self._step_label.setText(S("update", "update_failed"))
            self._step_label.setStyleSheet(f"color: {theme.fetch_error_color}; font-size: 13px;")
            self._log_detail.setText(S.format("update", "update_error", msg=msg[:200]))
            self._log_area.append(
                f'<span style="color:{theme.fetch_error_color};">  ✗ 更新失败: {msg}</span>')
            self._log_area.append(
                f'<span style="color:{theme.text_dim};">========== 更新失败 ==========</span>')
        # 不再弹窗，日志区已显示错误详情

    def _set_buttons_enabled(self, enabled: bool):
        for btn in [self._btn_update, self._btn_fetch, self._btn_browse]:
            if btn:
                btn.setEnabled(enabled)

    # ============================================================
    # 对话框
    # ============================================================

    @staticmethod
    def _urls_to_html(text_content: str) -> str:
        """将纯文本中的 URL 转换为可点击的 HTML 链接。"""
        html = text_content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html = html.replace('\n', '<br>')
        url_pattern = r'(https?://[^\s<>"]+)'
        html = re.sub(url_pattern, r'<a href="\1" style="color: #5dade2;">\1</a>', html)
        return html

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

        text = QTextBrowser()
        text.setReadOnly(readonly)
        text.setOpenExternalLinks(True)
        text.setHtml(self._urls_to_html(text_content))
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

    def _refresh_log_colors(self):
        """主题切换时重新渲染所有日志，应用新配色。"""
        if not self._log_area:
            return
        # 保存当前滚动位置
        scrollbar = self._log_area.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        # 清空并重新渲染
        self._log_area.clear()
        for log_type, msg, source in self._log_records:
            self._log_area.append(self._format_log_line(log_type, msg, source))

        # 恢复滚动位置
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _format_log_line(self, log_type: str, msg: str, source: str = "") -> str:
        now = datetime.now().strftime("%H:%M:%S")
        color = theme.log_color_map.get(log_type, theme.text)
        prefix_map = {"ok": "✓", "warn": "⚠", "error": "✗", "info": "  "}
        p = prefix_map.get(log_type, " ")
        src = f' <span style="color:{theme.text_dim};">[{source}]</span>' if source else ""
        return (
            f'<span style="color:{theme.text_dim};">[{now}]</span>'
            f'{src}'
            f' <span style="color:{color};">{p} {msg}</span>')

    def show_tutorial(self):
        tutorial_text = S.format("tutorial", "relic_content", data_dir=str(self._data_dir))
        dlg = self._build_text_dialog(
            S("tutorial", "relic_title"), tutorial_text, 560, 600, True, theme.cyber_yellow)
        dlg.exec()
