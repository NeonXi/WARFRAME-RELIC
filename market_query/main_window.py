"""
Main Window - WM Item Search & Price Query
"""

import sys
import os
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QClipboard, QColor

from search_widget import SearchWidget
from price_fetcher import PriceFetcher
from progress_bar import QProgressBar as CustomProgressBar
from code_rain import CodeRainOverlay
from utils import format_slug, get_status_text, get_status_color

# 确保能找到 core 模块
_src_root = os.path.dirname(os.path.dirname(__file__))
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from core.theme_config import theme


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WM Item Search & Price Query")
        self.setGeometry(100, 100, 1000, 650)
        
        self._price_fetcher = None
        self._s = self._build_styles()
        self._init_ui()
    
    # ─── Styles ────────────────────────────────────────────
    
    def _build_styles(self) -> dict:
        """根据当前主题配色构建样式表 dict"""
        t = theme
        return {
            "central": f"background: {t.panel_darkest};",
            "search_widget": f"""
    QWidget {{
        background: {t.card_bg};
        border-radius: 6px;
        border: 1px solid {t.border};
    }}
""",
            "table_frame": f"background: {t.card_bg}; border-radius: 6px;",
            "table_label": f"color: {t.cyber_cyan}; font-weight: bold; padding: 10px; font-size: 14px;",
            "item_name": f"""
    color: {t.cyber_cyan};
    font-weight: bold;
    font-size: 14px;
    background: {t.panel_bg};
    border-radius: 4px;
    border: 1px solid {t.border};
    padding: 10px;
""",
            "results_table": f"""
    QTableWidget {{
        background: {t.panel_bg};
        color: {t.text};
        border: none;
        gridline-color: {t.card_bg};
        outline: none;
    }}
    QTableWidget::item {{
        padding: 10px;
        border: none;
        outline: none;
    }}
    QTableWidget::item:hover {{
        background: {t.border};
    }}
    QTableWidget::item:selected {{
        background: {t.border};
        outline: none;
        border: none;
    }}
    QHeaderView {{
        background: {t.card_bg};
        border: none;
    }}
    QHeaderView::section {{
        background: {t.card_bg};
        color: {t.cyber_cyan};
        padding: 10px;
        border: none;
        border-bottom: 1px solid {t.border};
    }}
    QTableCornerButton::section {{
        background: {t.card_bg};
        border: none;
        border-right: 1px solid {t.border};
        border-bottom: 1px solid {t.border};
    }}
""",
            "status_label": f"color: {t.text_dim}; font-size: 12px; padding: 5px;",
        }
    
    # ─── UI Initialization ─────────────────────────────────
    
    def _init_ui(self):
        """Initialize UI components"""
        s = self._s
        central_widget = QWidget()
        central_widget.setStyleSheet(s["central"])
        self.setCentralWidget(central_widget)
        
        # Code Rain overlay
        self._code_rain = CodeRainOverlay(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Search Widget
        self._search_widget = SearchWidget()
        self._search_widget.setStyleSheet(s["search_widget"])
        self._search_widget.item_selected.connect(self._on_item_selected)
        main_layout.addWidget(self._search_widget, alignment=Qt.AlignmentFlag.AlignTop)
        
        # Results Table Frame
        table_frame = QFrame()
        table_frame.setStyleSheet(s["table_frame"])
        table_layout = QVBoxLayout(table_frame)
        
        # Header
        header_layout = QHBoxLayout()
        table_label = QLabel("🏷️ 搜索结果")
        table_label.setStyleSheet(s["table_label"])
        header_layout.addWidget(table_label)
        table_layout.addLayout(header_layout)
        
        # Item Name Display
        self._item_name_label = QLabel()
        self._item_name_label.setStyleSheet(s["item_name"])
        self._item_name_label.hide()
        table_layout.addWidget(self._item_name_label)
        
        # Progress Bar
        self._progress_bar = CustomProgressBar()
        self._progress_bar.hide()
        table_layout.addWidget(self._progress_bar)
        
        # Results Table
        self._results_table = QTableWidget()
        self._results_table.setColumnCount(5)
        self._results_table.setHorizontalHeaderLabels([
            "卖家", "状态", "价格 (Plat)", "物品等级", "声望"
        ])
        self._results_table.setStyleSheet(s["results_table"])
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._results_table.cellClicked.connect(self._on_cell_clicked)
        table_layout.addWidget(self._results_table)
        
        main_layout.addWidget(table_frame)
        
        # Status Bar
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(s["status_label"])
        main_layout.addWidget(self._status_label)
    
    # ─── Event Handlers ────────────────────────────────────
    
    def _on_item_selected(self, item_data):
        """Handle item selection from search widget"""
        zh_name = item_data['zh_name']
        en_name = item_data['en_name']
        
        self._item_name_label.setText(f"{zh_name} ({en_name})")
        self._item_name_label.show()
        self._results_table.setRowCount(0)
        self._results_table.setColumnCount(5)
        self._results_table.setHorizontalHeaderLabels([
            "卖家", "状态", "价格 (Plat)", "物品等级", "声望"
        ])
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # Start code rain
        self._code_rain.start_rain()
        
        # Show progress bar
        self._progress_bar.setRange(0, 0)
        self._progress_bar.show()
        
        # Generate slug
        print(f"[性能] 开始处理物品: {en_name}")
        slug_start = time.time()
        slug = format_slug(en_name)
        print(f"[性能] Slug 处理完成: {slug} (耗时 {time.time() - slug_start:.2f}s)")
        
        # Cancel previous fetcher if running
        if self._price_fetcher and self._price_fetcher.isRunning():
            self._price_fetcher.stop()
            self._price_fetcher.wait(1000)
        
        # Start new fetcher
        self._price_fetcher = PriceFetcher(slug, en_name)
        self._price_fetcher.progress_update.connect(self._on_progress_update)
        self._price_fetcher.order_received.connect(self._on_order_received)
        self._price_fetcher.finished.connect(self._on_fetch_finished)
        self._price_fetcher.start()
    
    def _on_progress_update(self, progress, message):
        """Update progress bar"""
        self._progress_bar.setStatusText(message)
        if progress > 0:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(progress)
    
    def _on_order_received(self, order_data):
        """Handle single order received (streaming)"""
        row = self._results_table.rowCount()
        self._results_table.insertRow(row)
        
        # Fade out code rain on first result
        if row == 0:
            self._code_rain.start_fade_out()
        
        # Username
        username = str(order_data.get('username', 'Unknown'))
        username_item = QTableWidgetItem(username)
        username_item.setData(Qt.ItemDataRole.UserRole, username)
        username_item.setFlags(username_item.flags() | Qt.ItemFlag.ItemIsSelectable)
        username_item.setForeground(QColor(theme.cyber_cyan))
        username_item.setToolTip("点击复制用户名")
        self._results_table.setItem(row, 0, username_item)
        
        # Status
        status = str(order_data.get('status', 'offline'))
        status_item = QTableWidgetItem(get_status_text(status))
        status_item.setForeground(QColor(get_status_color(status)))
        self._results_table.setItem(row, 1, status_item)
        
        # Price
        platinum = order_data.get('platinum', 0)
        price_item = QTableWidgetItem(str(platinum))
        price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._results_table.setItem(row, 2, price_item)
        
        # Item Level
        level = order_data.get('item_level', 0)
        level_display = f"{level} {'●' * level}" if level > 0 else "-"
        level_item = QTableWidgetItem(level_display)
        level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._results_table.setItem(row, 3, level_item)
        
        # Reputation
        reputation = order_data.get('reputation', 0)
        reputation_item = QTableWidgetItem(str(reputation))
        reputation_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._results_table.setItem(row, 4, reputation_item)
    
    def _on_cell_clicked(self, row, column):
        """Copy username when clicking first column"""
        if column == 0:
            item = self._results_table.item(row, column)
            if item:
                username = item.data(Qt.ItemDataRole.UserRole)
                if username:
                    QApplication.clipboard().setText(str(username))
                    self._status_label.setText(f"已复制用户名: {username}")
    
    def _on_fetch_finished(self, success, message):
        """Handle fetch completion"""
        self._progress_bar.hide()
        self._status_label.setText(message)
        self._code_rain.start_fade_out()
        
        if not success:
            print(f"[WM实时查询] 错误: {message}", flush=True)
            is_network_error = any(kw in message for kw in ("网络超时", "网络错误", "HTTP 错误"))
            
            if is_network_error:
                self._show_network_error_help(message)
            else:
                self._results_table.setRowCount(1)
                error_item = QTableWidgetItem(message)
                error_item.setForeground(QColor(theme.cyber_red))
                self._results_table.setItem(0, 0, error_item)
                self._results_table.setSpan(0, 0, 1, 5)
    
    def _show_network_error_help(self, brief_msg):
        """显示网络错误的友好说明"""
        lines = [
            ("错误信息", brief_msg),
            ("可能原因",
             "• warframe.market 服务器暂时繁忙或维护中\n"
             "• 本地网络不稳定或连接超时\n"
             "• 该物品卖家数量过多，响应数据过大"),
            ("建议操作",
             "• 点击其他物品重新搜索，再切回来重试\n"
             "• 检查网络是否正常，必要时使用加速器\n"
             "• 等待片刻后再次尝试查询"),
        ]
        
        self._results_table.setRowCount(len(lines))
        self._results_table.setColumnCount(2)
        self._results_table.setHorizontalHeaderLabels(["类型", "详情"])
        
        for i, (label, detail) in enumerate(lines):
            label_item = QTableWidgetItem(label)
            label_item.setForeground(QColor(theme.cyber_cyan))
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._results_table.setItem(i, 0, label_item)
            
            detail_item = QTableWidgetItem(detail)
            detail_item.setForeground(QColor(theme.text))
            detail_item.setFlags(detail_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._results_table.setItem(i, 1, detail_item)
        
        header = self._results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._results_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    
    def closeEvent(self, event):
        """Cleanup on close"""
        if self._price_fetcher and self._price_fetcher.isRunning():
            self._price_fetcher.stop()
            self._price_fetcher.wait(2000)
        event.accept()


def main():
    """Application entry point"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())