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
from utils import format_slug, get_status_text, get_status_color

# ─── Stylesheets ───────────────────────────────────────────
STYLE_SEARCH_WIDGET = """
    QWidget {
        background: #1a1a2e;
        border-radius: 6px;
        border: 1px solid #0f3460;
    }
"""

STYLE_TABLE_FRAME = "background: #1a1a2e; border-radius: 6px;"

STYLE_TABLE_LABEL = "color: #00d9ff; font-weight: bold; padding: 10px; font-size: 14px;"

STYLE_ITEM_INFO_FRAME = """
    QFrame {
        background: #16213e;
        border-radius: 4px;
        border: 1px solid #0f3460;
        padding: 10px;
    }
"""

STYLE_ITEM_NAME = "color: #00d9ff; font-weight: bold; font-size: 14px;"

STYLE_RESULTS_TABLE = """
    QTableWidget {
        background: #16213e;
        color: #eaeaea;
        border: none;
        gridline-color: #1a1a2e;
        outline: none;
    }
    QTableWidget::item {
        padding: 10px;
        border: none;
        outline: none;
    }
    QTableWidget::item:hover {
        background: #0f3460;
    }
    QTableWidget::item:selected {
        background: #0f3460;
        outline: none;
        border: none;
    }
    QHeaderView {
        background: #1a1a2e;
        border: none;
    }
    QHeaderView::section {
        background: #1a1a2e;
        color: #00d9ff;
        padding: 10px;
        border: none;
        border-bottom: 1px solid #0f3460;
    }
    QTableCornerButton::section {
        background: #1a1a2e;
        border: none;
        border-right: 1px solid #0f3460;
        border-bottom: 1px solid #0f3460;
    }
"""

STYLE_STATUS_LABEL = "color: #666; font-size: 12px; padding: 5px;"


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WM Item Search & Price Query")
        self.setGeometry(100, 100, 1000, 650)
        
        self._price_fetcher = None
        self._init_ui()
    
    # ─── UI Initialization ─────────────────────────────────
    
    def _init_ui(self):
        """Initialize UI components"""
        central_widget = QWidget()
        central_widget.setStyleSheet("background: #0d1117;")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Search Widget
        self._search_widget = SearchWidget()
        self._search_widget.setStyleSheet(STYLE_SEARCH_WIDGET)
        self._search_widget.item_selected.connect(self._on_item_selected)
        main_layout.addWidget(self._search_widget, alignment=Qt.AlignmentFlag.AlignTop)
        
        # Results Table Frame
        table_frame = QFrame()
        table_frame.setStyleSheet(STYLE_TABLE_FRAME)
        table_layout = QVBoxLayout(table_frame)
        
        # Header
        header_layout = QHBoxLayout()
        table_label = QLabel("🏷️ 搜索结果")
        table_label.setStyleSheet(STYLE_TABLE_LABEL)
        header_layout.addWidget(table_label)
        table_layout.addLayout(header_layout)
        
        # Item Name Display
        self._item_info_frame = QFrame()
        self._item_info_frame.setStyleSheet(STYLE_ITEM_INFO_FRAME)
        self._item_info_frame.hide()
        item_info_layout = QVBoxLayout(self._item_info_frame)
        
        self._item_name_label = QLabel()
        self._item_name_label.setStyleSheet(STYLE_ITEM_NAME)
        item_info_layout.addWidget(self._item_name_label)
        table_layout.addWidget(self._item_info_frame)
        
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
        self._results_table.setStyleSheet(STYLE_RESULTS_TABLE)
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._results_table.cellClicked.connect(self._on_cell_clicked)
        table_layout.addWidget(self._results_table)
        
        main_layout.addWidget(table_frame)
        
        # Status Bar
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(STYLE_STATUS_LABEL)
        main_layout.addWidget(self._status_label)
    
    # ─── Event Handlers ────────────────────────────────────
    
    def _on_item_selected(self, item_data):
        """Handle item selection from search widget"""
        zh_name = item_data['zh_name']
        en_name = item_data['en_name']
        
        self._item_name_label.setText(f"{zh_name} ({en_name})")
        self._item_info_frame.show()
        self._results_table.setRowCount(0)
        
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
        
        # Username
        username = str(order_data.get('username', 'Unknown'))
        username_item = QTableWidgetItem(username)
        username_item.setData(Qt.ItemDataRole.UserRole, username)
        username_item.setFlags(username_item.flags() | Qt.ItemFlag.ItemIsSelectable)
        username_item.setForeground(QColor("#00d9ff"))
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
        
        if not success:
            self._results_table.setRowCount(1)
            error_item = QTableWidgetItem(message)
            error_item.setForeground(QColor('#ff4444'))
            self._results_table.setItem(0, 0, error_item)
    
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