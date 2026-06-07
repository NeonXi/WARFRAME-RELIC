"""
Search Widget Component - Handles item search and dropdown display
"""

import sqlite3
import os
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QListWidget,
    QListWidgetItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

# 确保能找到 core 模块
_src_root = os.path.dirname(os.path.dirname(__file__))
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from core.theme_config import theme

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'warframe.db')

# Excluded categories (non-tradable cosmetics)
_EXCLUDE_ZH = ('浮印', '外观', '遗物', '摇头娃娃', '披饰', '站姿')
_EXCLUDE_EN = ('Glyph', 'Skin', 'Animation', 'Helmet')

_SEARCH_SQL = f"""
    SELECT rowid AS id, name AS en_name, zh_name
    FROM items
    WHERE (zh_name LIKE ? OR name LIKE ? OR zh_pinyin LIKE ?)
    AND tradable = 1
    AND zh_name NOT LIKE '%{"%' AND zh_name NOT LIKE '%".join(_EXCLUDE_ZH)}%'
    AND name NOT LIKE '%{"%' AND name NOT LIKE '%".join(_EXCLUDE_EN)}%'
    ORDER BY
        CASE WHEN zh_name LIKE '%一套%' OR name LIKE '%Set%' THEN 0 ELSE 1 END,
        CASE WHEN zh_name LIKE '%蓝图%' OR name LIKE '%Blueprint%' THEN 0 ELSE 1 END,
        zh_name
    LIMIT 20
"""


class SearchWidget(QWidget):
    """Search widget with dropdown suggestions"""
    
    item_selected = pyqtSignal(dict)  # Emitted when item is selected
    
    def __init__(self):
        super().__init__()
        self._conn = None
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)
        self._init_ui()
    
    def _get_conn(self):
        """Get or create persistent SQLite connection"""
        if self._conn is None:
            self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            from data.db_connections import db_conn_registry
            db_conn_registry.register("search_widget", self.close_db)
        return self._conn

    def close_db(self):
        """Close the persistent database connection (for registry)."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        from data.db_connections import db_conn_registry
        db_conn_registry.unregister("search_widget")
    
    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Search bar container
        self._search_bar = QWidget()
        self._search_bar.setFixedHeight(48)
        search_bar_layout = QHBoxLayout(self._search_bar)
        search_bar_layout.setContentsMargins(4, 4, 4, 4)
        search_bar_layout.setSpacing(0)
        
        # Search field
        search_field = QWidget()
        search_field.setStyleSheet(f"""
            QWidget {{
                background: {theme.panel_bg};
                border-radius: 4px;
                border: 1px solid {theme.border};
            }}
        """)
        search_field_layout = QHBoxLayout(search_field)
        search_field_layout.setContentsMargins(0, 0, 0, 0)
        search_field_layout.setSpacing(0)
        
        # Icon
        icon_container = QWidget()
        icon_container.setFixedSize(40, 40)
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("font-size: 18px;")
        search_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(search_icon)
        search_field_layout.addWidget(icon_container)
        
        # Input box
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入物品名称 (中文/英文/拼音)...")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {theme.text};
                border: none;
                padding: 0 15px;
                font-size: 14px;
                min-height: 40px;
            }}
            QLineEdit:focus {{ outline: none; }}
            QLineEdit::placeholder {{ color: {theme.text_dim}; }}
        """)
        self._search_input.textChanged.connect(self._on_text_changed)
        search_field_layout.addWidget(self._search_input)
        
        search_bar_layout.addWidget(search_field)
        layout.addWidget(self._search_bar)
        
        # Dropdown
        self._dropdown = QListWidget()
        self._dropdown.setObjectName("resultsDropdown")
        self._dropdown.setStyleSheet(f"""
            QListWidget#resultsDropdown {{
                background: {theme.panel_bg};
                color: {theme.text};
                border: none;
                border-top: 1px solid {theme.border};
                border-radius: 0 0 4px 4px;
            }}
            QListWidget#resultsDropdown::item {{
                padding: 10px 15px;
                border-bottom: 1px solid {theme.card_bg};
            }}
            QListWidget#resultsDropdown::item:hover {{
                background: {theme.border};
            }}
            QListWidget#resultsDropdown::item:selected {{
                background: {theme.cyber_cyan};
                color: {theme.panel_bg};
            }}
        """)
        self._dropdown.itemClicked.connect(self._on_item_clicked)
        self._dropdown.hide()
        layout.addWidget(self._dropdown)
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        
        # Keyboard navigation
        self._search_input.returnPressed.connect(self._on_enter_pressed)
        self._search_input.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Filter events for keyboard navigation"""
        if obj == self._search_input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Down:
                if self._dropdown.isVisible():
                    row = self._dropdown.currentRow()
                    if row < self._dropdown.count() - 1:
                        self._dropdown.setCurrentRow(row + 1)
                    elif row == -1 and self._dropdown.count() > 0:
                        self._dropdown.setCurrentRow(0)
                return True
            elif event.key() == Qt.Key.Key_Up:
                if self._dropdown.isVisible():
                    row = self._dropdown.currentRow()
                    if row > 0:
                        self._dropdown.setCurrentRow(row - 1)
                return True
            elif event.key() == Qt.Key.Key_Escape:
                if self._dropdown.isVisible():
                    self._dropdown.hide()
                return True
        return super().eventFilter(obj, event)
    
    def _on_enter_pressed(self):
        """Handle Enter key press"""
        if self._dropdown.isVisible():
            current_item = self._dropdown.currentItem()
            if current_item:
                self._on_item_clicked(current_item)
    
    def _on_text_changed(self, text):
        """Handle text change - debounce search"""
        if text.strip():
            self._search_timer.start(150)
        else:
            self._dropdown.hide()
    
    def _do_search(self):
        """Perform search with pinyin support"""
        keyword = self._search_input.text().strip()
        if not keyword:
            return
        
        results = self._search_items(keyword)
        self._show_dropdown(results)
    
    def _search_items(self, keyword):
        """Search database for tradable items"""
        try:
            conn = self._get_conn()
            pattern = f"%{keyword}%"
            cur = conn.cursor()
            cur.execute(_SEARCH_SQL, [pattern, pattern, pattern])
            db_results = [dict(row) for row in cur.fetchall()]

            return [{
                'id': item['id'],
                'en_name': item['en_name'],
                'zh_name': item['zh_name']
            } for item in db_results]
        except Exception as e:
            print(f"Search Error: {e}")
            return []
    
    def _show_dropdown(self, items):
        """Show dropdown with search results"""
        self._dropdown.clear()
        
        if not items:
            self._dropdown.hide()
            return
        
        for item in items:
            display_name = f"{item['zh_name']} ({item['en_name']})"
            item_widget = QListWidgetItem(display_name)
            item_widget.setData(Qt.ItemDataRole.UserRole, item)
            self._dropdown.addItem(item_widget)
        
        self._dropdown.setMaximumHeight(min(len(items) * 40, 250))
        self._dropdown.show()
    
    def _on_item_clicked(self, item):
        """Handle item selection"""
        item_data = item.data(Qt.ItemDataRole.UserRole)
        if item_data:
            self._dropdown.hide()
            self.item_selected.emit(item_data)
    
    def closeEvent(self, event):
        """Close SQLite connection on widget close"""
        if self._conn:
            self._conn.close()
            self._conn = None
        event.accept()