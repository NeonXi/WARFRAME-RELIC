"""
源数据浏览器 — JSON 文件可视化查看器

用于浏览 external/ 文件夹中原始 GitHub 仓库的 JSON 数据文件。
支持大型 JSON 文件的懒加载树形展开，类型感知颜色编码。
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from data.ui_strings import S
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QSplitter, QLineEdit, QTextEdit, QFrame, QHeaderView, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QStyle, QProxyStyle, QStyleOption

from core.constants import theme
from core.theme_proxy import JSON_BOOLEAN, COLOR_BLACK


# ============================================================
# 常量
# ============================================================

EXTERNAL_DIR = Path(__file__).resolve().parent.parent / "external"

# 每个仓库的 JSON 文件映射: {repo_dir_name: [(display_name, relative_path), ...]}
REPO_FILES = {
    "warframe-items_sparse": [
        ("All.json", "data/json/All.json"),
        ("Relics.json", "data/json/Relics.json"),
        ("i18n.json", "data/json/i18n.json"),
    ],
    "warframe-drop-data_sparse": [
        ("all.json", "data/all.json"),
    ],
    "warframe-i18n_sparse": [
        ("dict.en.json", "dict.en.json"),
        ("dict.zh.json", "dict.zh.json"),
    ],
}

REPO_LABELS = {
    "warframe-items_sparse": "WFCD/warframe-items",
    "warframe-drop-data_sparse": "WFCD/warframe-drop-data",
    "warframe-i18n_sparse": "calamity-inc/warframe-public-export-plus",
}

# 类型颜色
TYPE_COLORS = {
    "object": QColor(theme.cyber_orange),
    "array":  QColor(theme.cyber_orange),
    "string": QColor(theme.cyber_green),
    "number": QColor(theme.cyber_cyan),
    "boolean": QColor(str(JSON_BOOLEAN)),
    "null":   QColor(theme.text_dim),
}

# 数组每批加载数量
ARRAY_CHUNK_SIZE = 50


# ============================================================
# 自定义分支箭头样式
# ============================================================

class _BranchStyle(QProxyStyle):
    """确保分支箭头在深色背景下可见。"""

    def __init__(self, base_style=None):
        super().__init__(base_style)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorBranch:
            # 用亮色绘制展开/折叠箭头
            painter.save()
            painter.setPen(QColor(theme.text_dim))
            painter.setBrush(QColor(theme.text_dim))
            super().drawPrimitive(element, option, painter, widget)
            painter.restore()
        else:
            super().drawPrimitive(element, option, painter, widget)


# ============================================================
# 工具函数
# ============================================================

def _get_type_label(value: Any) -> str:
    """获取值的类型标签。"""
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) or isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return "unknown"


def _get_value_preview(value: Any) -> str:
    """获取值的预览文本（截断）。"""
    if isinstance(value, dict):
        return f"{{ {len(value)} 字段 }}"
    if isinstance(value, list):
        return f"[ {len(value)} 项 ]"
    if isinstance(value, str):
        if len(value) > 80:
            return f'"{value[:77]}..."'
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _format_file_size(path: Path) -> str:
    """格式化文件大小。"""
    try:
        size = path.stat().st_size
    except OSError:
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# ============================================================
# 数据访问
# ============================================================

class JsonDataLoader:
    """JSON 数据加载器（缓存已加载的文件）。"""

    def __init__(self):
        self._cache: dict[str, Any] = {}

    def load(self, file_path: str) -> Optional[Any]:
        """加载 JSON 文件（带缓存）。"""
        if file_path in self._cache:
            return self._cache[file_path]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache[file_path] = data
            return data
        except Exception:
            return None

    def clear(self):
        self._cache.clear()


# ============================================================
# JSON 树节点数据
# ============================================================

class JsonNode:
    """JSON 树中的一个节点，持有数据引用和位置信息。"""

    __slots__ = ("key", "value", "path", "depth", "is_placeholder")

    def __init__(self, key: str, value: Any, path: str, depth: int,
                 is_placeholder: bool = False):
        self.key = key
        self.value = value
        self.path = path
        self.depth = depth
        self.is_placeholder = is_placeholder

    @property
    def type_label(self) -> str:
        return _get_type_label(self.value)

    @property
    def preview(self) -> str:
        if self.is_placeholder:
            return "点击加载更多..."
        return _get_value_preview(self.value)

    @property
    def color(self) -> QColor:
        return TYPE_COLORS.get(self.type_label, QColor(theme.text))


# ============================================================
# JSON 树形视图
# ============================================================

class JsonTreeWidget(QTreeWidget):
    """JSON 懒加载树形视图。"""

    node_selected = pyqtSignal(dict)  # 发射节点信息

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Any = None
        self._root_path: str = "$"
        self._loader = JsonDataLoader()
        self._load_stats: dict = {"total_nodes": 0, "max_depth": 0}

        self.setColumnCount(2)
        self.setHeaderLabels(["Key", "Value"])
        self.setAlternatingRowColors(True)
        self.setAnimated(True)
        self.setExpandsOnDoubleClick(True)
        self.setIndentation(18)
        self.setStyleSheet(self._style())

        header = self.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 260)

        # 深色背景下的分支箭头
        self.setStyle(_BranchStyle(self.style()))

        self.itemExpanded.connect(self._on_expand)
        self.itemClicked.connect(self._on_click)

    def _style(self) -> str:
        return f"""
            QTreeWidget {{
                background-color: {theme.panel_bg};
                color: {theme.text};
                border: none;
                font-size: 12px;
                alternate-background-color: rgba(255,255,255,0.02);
            }}
            QTreeWidget::item {{
                padding: 3px 6px;
                border: none;
            }}
            QTreeWidget::item:hover {{
                background: rgba(255,255,255,0.05);
            }}
            QTreeWidget::item:selected {{
                background: rgba(0,255,255,0.12);
            }}
            QHeaderView {{
                background: {theme.panel_bg};
            }}
            QHeaderView::section {{
                background: {theme.panel_bg};
                color: rgba(255,255,255,0.65);
                font-size: 11px;
                font-weight: 600;
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }}
            """

    def load_file(self, file_path: str):
        """加载 JSON 文件并显示根节点。"""
        self.clear()
        self._data = self._loader.load(file_path)
        if self._data is None:
            root = QTreeWidgetItem(self, ["（加载失败）", ""])
            root.setForeground(0, QColor(theme.cyber_red))
            return

        self._load_stats = {"total_nodes": 0, "max_depth": 0}
        self._root_path = "$"

        if isinstance(self._data, dict):
            typename = "object"
            info = f"{{ {len(self._data)} 字段 }}"
        elif isinstance(self._data, list):
            typename = "array"
            info = f"[ {len(self._data)} 项 ]"
        else:
            typename = _get_type_label(self._data)
            info = _get_value_preview(self._data)

        root = QTreeWidgetItem(self, [typename, info])
        root.setForeground(0, TYPE_COLORS.get(typename, QColor(theme.text)))
        root.setData(0, Qt.ItemDataRole.UserRole, JsonNode(
            key="", value=self._data, path="$", depth=0,
        ))
        # 添加占位子节点以显示展开箭头
        if isinstance(self._data, (dict, list)):
            QTreeWidgetItem(root, ["加载中...", ""])
        self.addTopLevelItem(root)

    def _on_expand(self, item: QTreeWidgetItem):
        """展开时懒加载子节点。"""
        # 检查是否已加载（子节点数 > 0 且第一个不是占位符）
        if item.childCount() == 0:
            return
        first_child = item.child(0)
        first_text = first_child.text(0)
        if first_text not in ("加载中...", "", "点击加载更多..."):
            return  # 已加载

        node: JsonNode = item.data(0, Qt.ItemDataRole.UserRole)
        if node is None:
            return

        # 占位符节点：需要将新项添加到父级（数组节点），而非占位符自身
        if node.is_placeholder:
            parent_item = item.parent()
            if parent_item is None:
                return
            # 移除占位符本身
            idx_in_parent = parent_item.indexOfChild(item)
            parent_item.takeChild(idx_in_parent)
            # 解析起始索引
            base_idx = 0
            try:
                base_idx = int(node.key.strip("[]"))
            except ValueError:
                pass
            self._populate_array_chunk(parent_item, node, base_idx)
            return

        # 移除占位子节点
        item.takeChildren()

        if isinstance(node.value, dict):
            self._populate_object(item, node)
        elif isinstance(node.value, list):
            self._populate_array(item, node)

    def _populate_object(self, parent: QTreeWidgetItem, node: JsonNode):
        """填充对象的所有子节点。"""
        obj: dict = node.value
        depth = node.depth + 1
        self._load_stats["max_depth"] = max(self._load_stats["max_depth"], depth)

        for key in obj:
            val = obj[key]
            child_path = f'{node.path}["{key}"]'
            child_node = JsonNode(key=key, value=val, path=child_path, depth=depth)
            self._add_tree_item(parent, child_node)
        self._load_stats["total_nodes"] += len(obj)

    def _populate_array(self, parent: QTreeWidgetItem, node: JsonNode):
        """填充数组的第一批 ARRAY_CHUNK_SIZE 项。"""
        self._populate_array_chunk(parent, node, base_idx=0)

    def _populate_array_chunk(self, parent: QTreeWidgetItem, node: JsonNode, base_idx: int):
        """向数组节点添加一批项，从 base_idx 开始。"""
        arr: list = node.value
        depth = node.depth + 1
        self._load_stats["max_depth"] = max(self._load_stats["max_depth"], depth)
        total = len(arr)
        chunk = min(ARRAY_CHUNK_SIZE, total - base_idx)

        for i in range(base_idx, base_idx + chunk):
            val = arr[i]
            child_path = f"{node.path}[{i}]"
            child_node = JsonNode(key=f"[{i}]", value=val, path=child_path, depth=depth)
            self._add_tree_item(parent, child_node)

        # 如果还有更多，添加占位符
        remaining = total - (base_idx + chunk)
        if remaining > 0:
            placeholder = JsonNode(
                key=f"[{base_idx + chunk}]", value=arr, path=node.path,
                depth=depth, is_placeholder=True,
            )
            item = QTreeWidgetItem(parent, [
                f"[{base_idx + chunk}]",
                f"点击加载更多... ({remaining} 项剩余)"
            ])
            item.setForeground(0, QColor(theme.text_dim))
            item.setForeground(1, QColor(theme.text_dim))
            item.setData(0, Qt.ItemDataRole.UserRole, placeholder)
            # 占位节点需要一个子节点来显示展开箭头
            QTreeWidgetItem(item, ["加载中...", ""])

        self._load_stats["total_nodes"] += chunk

    def _add_tree_item(self, parent: QTreeWidgetItem, node: JsonNode):
        """添加一个树节点。"""
        item = QTreeWidgetItem(parent, [node.key, node.preview])
        item.setForeground(0, TYPE_COLORS.get("string", QColor(theme.text)))
        item.setForeground(1, node.color)
        item.setData(0, Qt.ItemDataRole.UserRole, node)

        if node.is_placeholder:
            item.setForeground(0, QColor(theme.text_dim))
            item.setForeground(1, QColor(theme.text_dim))
            QTreeWidgetItem(item, ["加载中...", ""])
            return

        # 容器类型：添加占位子节点以显示展开箭头，并加粗区分
        if isinstance(node.value, (dict, list)):
            QTreeWidgetItem(item, ["", ""])
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        # 对于字符串，如果太长，设置 tooltip
        elif isinstance(node.value, str) and len(node.value) > 80:
            item.setToolTip(1, node.value)

        # 特殊处理布尔值颜色
        if node.type_label == "boolean":
            item.setForeground(1, TYPE_COLORS["boolean"])

    def _on_click(self, item: QTreeWidgetItem, col: int):
        """点击节点：左列显示信息，右列复制值。"""
        node: JsonNode = item.data(0, Qt.ItemDataRole.UserRole)
        if node is None:
            return

        # 右列（Value 列）：复制值到剪贴板
        if col == 1:
            self._copy_node_value(node)
            return

        # 左列（Key 列）：显示节点信息
        info = {
            "key": node.key,
            "type": node.type_label,
            "path": node.path,
            "depth": node.depth,
            "preview": node.preview,
        }
        if node.type_label == "string":
            info["value"] = node.value
        elif node.type_label == "number":
            info["value"] = str(node.value)
        elif node.type_label == "boolean":
            info["value"] = "true" if node.value else "false"
        elif node.type_label == "null":
            info["value"] = "null"
        elif node.type_label == "object":
            info["value"] = f"对象，{len(node.value)} 个字段"
        elif node.type_label == "array":
            info["value"] = f"数组，{len(node.value)} 项"

        self.node_selected.emit(info)

    def _copy_node_value(self, node: JsonNode):
        """复制节点值到剪贴板。"""
        if node.type_label == "string":
            text = node.value
        elif node.type_label == "number":
            text = str(node.value)
        elif node.type_label == "boolean":
            text = "true" if node.value else "false"
        elif node.type_label == "null":
            text = "null"
        else:
            # 容器类型：复制 JSON 路径
            text = node.path

        QApplication.clipboard().setText(text)
        # 更新底部信息面板提示复制成功
        self.node_selected.emit({
            "key": node.key,
            "type": node.type_label,
            "path": node.path,
            "depth": node.depth,
            "preview": f"已复制: {text}" if len(text) <= 80 else f"已复制: {text[:77]}...",
        })

    def get_stats(self) -> dict:
        """获取统计信息。"""
        total = 0
        max_depth = 0
        if isinstance(self._data, dict):
            total = len(self._data)
        elif isinstance(self._data, list):
            total = len(self._data)
        return {
            "total": total,
            "loaded_nodes": self._load_stats["total_nodes"],
            "max_depth": self._load_stats["max_depth"],
        }

    # ======================== 搜索定位 ========================

    def _parse_path(self, path: str) -> list[str]:
        """解析 JSON 路径为段列表。
        $[0]["rewards"][2]["name"] → ["[0]", "rewards", "[2]", "name"]
        """
        segments = []
        for m in re.finditer(r'\[(\d+)\]|\["([^"]*)"\]', path):
            if m.group(1) is not None:
                segments.append(f"[{m.group(1)}]")
            elif m.group(2) is not None:
                segments.append(m.group(2))
        return segments

    def navigate_to_path(self, path: str) -> Optional[QTreeWidgetItem]:
        """按路径展开树节点，返回目标节点。"""
        segments = self._parse_path(path)
        if not segments:
            return None

        # 从根节点开始
        root = self.topLevelItem(0)
        if root is None:
            return None
        root.setExpanded(True)

        current = root
        for seg in segments:
            found = self._find_child_by_key(current, seg)
            if found is None:
                return None
            found.setExpanded(True)
            current = found
        return current

    def _find_child_by_key(self, parent: QTreeWidgetItem, key: str) -> Optional[QTreeWidgetItem]:
        """在 parent 的子节点中查找 key 匹配的项，处理数组懒加载。"""
        for i in range(parent.childCount()):
            child = parent.child(i)
            node = child.data(0, Qt.ItemDataRole.UserRole)
            if node is None:
                continue
            if node.key == key:
                return child
            # 数组占位符：如果目标索引 >= 占位符起始索引，展开占位符
            if node.is_placeholder and key.startswith("["):
                try:
                    target_idx = int(key.strip("[]"))
                    placeholder_idx = int(node.key.strip("[]"))
                    if target_idx >= placeholder_idx:
                        child.setExpanded(True)  # 触发 _on_expand 加载更多
                        # 加载后递归查找
                        return self._find_child_by_key(parent, key)
                except ValueError:
                    pass
        return None

    def highlight_item(self, item: QTreeWidgetItem):
        """高亮选中节点并滚动到可见位置。"""
        self.clearSelection()
        self.setCurrentItem(item)
        self.scrollToItem(item, QTreeWidget.ScrollHint.PositionAtCenter)
        # 高亮背景 + 亮色文字
        highlight_bg = QColor(theme.cyber_yellow)
        highlight_bg.setAlpha(160)
        item.setBackground(0, highlight_bg)
        item.setBackground(1, highlight_bg)
        item.setForeground(0, QColor(str(COLOR_BLACK)))
        item.setForeground(1, QColor(str(COLOR_BLACK)))

    def clear_highlights(self):
        """清除所有高亮。"""
        it = QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            item.setBackground(0, QColor(0, 0, 0, 0))
            item.setBackground(1, QColor(0, 0, 0, 0))
            # 恢复原始前景色
            node: JsonNode = item.data(0, Qt.ItemDataRole.UserRole)
            if node is not None:
                item.setForeground(0, QColor(theme.text))
                item.setForeground(1, node.color)
            it += 1

    def search(self, keyword: str) -> list:
        """在已加载的数据中搜索关键词（广度优先，限制深度）。"""
        if not self._data or not keyword:
            return []
        results = []
        keyword_lower = keyword.lower()
        self._search_recursive(self._data, "$", keyword_lower, 0, 6, results)
        return results

    def _search_recursive(self, data: Any, path: str, keyword: str,
                          depth: int, max_depth: int, results: list):
        if depth > max_depth or len(results) >= 200:
            return
        if isinstance(data, dict):
            for k, v in data.items():
                child_path = f'{path}["{k}"]'
                if keyword in k.lower():
                    results.append({"path": child_path, "key": k, "type": "object_key"})
                if isinstance(v, str) and keyword in v.lower():
                    preview = v[:80] + "..." if len(v) > 80 else v
                    results.append({"path": child_path, "key": k, "value": preview, "type": "string_value"})
                if isinstance(v, (dict, list)):
                    self._search_recursive(v, child_path, keyword, depth + 1, max_depth, results)
        elif isinstance(data, list):
            for i, v in enumerate(data):
                if i >= 100:
                    break
                child_path = f"{path}[{i}]"
                if isinstance(v, str) and keyword in v.lower():
                    preview = v[:80] + "..." if len(v) > 80 else v
                    results.append({"path": child_path, "key": f"[{i}]", "value": preview, "type": "string_value"})
                if isinstance(v, (dict, list)):
                    self._search_recursive(v, child_path, keyword, depth + 1, max_depth, results)


# ============================================================
# 文件树
# ============================================================

class FileTreeWidget(QTreeWidget):
    """显示 external/ 文件夹结构的文件树。"""

    file_selected = pyqtSignal(str, str)  # (file_path, display_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setAnimated(True)
        self.setStyleSheet(self._style())
        self.itemClicked.connect(self._on_click)
        self._build_tree()

    def _style(self) -> str:
        return f"""
            QTreeWidget {{
                background-color: {theme.card_bg};
                color: {theme.text};
                border: none;
                font-size: 12px;
            }}
            QTreeWidget::item {{
                padding: 5px 8px;
                border: none;
                border-radius: 4px;
                margin: 1px 4px;
            }}
            QTreeWidget::item:hover {{
                background: rgba(255,255,255,0.05);
            }}
            QTreeWidget::item:selected {{
                background: rgba(0,255,255,0.12);
                color: {theme.cyber_cyan};
            }}
        """

    def _build_tree(self):
        """构建文件树。"""
        self.clear()

        ext_root = QTreeWidgetItem(self, ["📁 external"])
        ext_root.setForeground(0, QColor(theme.cyber_cyan))
        font = ext_root.font(0)
        font.setBold(True)
        ext_root.setFont(0, font)

        for repo_dir, files in REPO_FILES.items():
            repo_path = EXTERNAL_DIR / repo_dir
            repo_label = REPO_LABELS.get(repo_dir, repo_dir)
            exists = repo_path.exists()

            icon = "📁" if exists else "📁"
            repo_item = QTreeWidgetItem(ext_root, [f"{icon} {repo_label}"])
            repo_item.setForeground(0, QColor(theme.cyber_yellow if exists else theme.text_dim))
            repo_item.setToolTip(0, str(repo_path))

            if not exists:
                repo_item.setForeground(0, QColor(theme.text_dim))
                no_file = QTreeWidgetItem(repo_item, ["（仓库未克隆）"])
                no_file.setForeground(0, QColor(theme.text_dim))
                continue

            for display_name, rel_path in files:
                full_path = repo_path / rel_path
                file_exists = full_path.exists()
                size = _format_file_size(full_path) if file_exists else "—"

                file_icon = "📄" if file_exists else "📄"
                file_item = QTreeWidgetItem(repo_item, [
                    f"{file_icon} {display_name}  ({size})"
                ])
                if file_exists:
                    file_item.setForeground(0, QColor(theme.cyber_green))
                    file_item.setData(0, Qt.ItemDataRole.UserRole, {
                        "path": str(full_path),
                        "name": display_name,
                        "repo": repo_label,
                    })
                else:
                    file_item.setForeground(0, QColor(theme.text_dim))

        ext_root.setExpanded(True)
        for i in range(ext_root.childCount()):
            ext_root.child(i).setExpanded(True)

    def _on_click(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and isinstance(data, dict):
            self.file_selected.emit(data["path"], data["name"])

    def refresh(self):
        self._build_tree()


# ============================================================
# 搜索面板
# ============================================================

class SearchPanel(QWidget):
    """搜索面板，带结果导航。"""

    search_requested = pyqtSignal(str)       # keyword
    navigate_requested = pyqtSignal(int)     # direction: -1=上一个, +1=下一个
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setStyleSheet(f"background: {theme.card_bg};")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText(S("json_viewer", "search_placeholder"))
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0,0,0,0.25); color: {theme.text};
                border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;
                padding: 3px 8px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: rgba(0,255,255,0.3); }}
        """)
        layout.addWidget(self._input, 1)

        search_btn = QPushButton(S("json_viewer", "search_btn"))
        search_btn.setFixedHeight(26)
        search_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,255,255,0.12); color: {theme.cyber_cyan};
                border: none; border-radius: 4px; padding: 2px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(0,255,255,0.22); }}
        """)
        search_btn.clicked.connect(self._do_search)
        layout.addWidget(search_btn)

        # 上一个 / 下一个 导航按钮
        nav_style = f"""
            QPushButton {{
                background: transparent; color: {theme.text_dim};
                border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;
                padding: 2px 8px; font-size: 13px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.06); color: {theme.text}; }}
        """
        self._btn_prev = QPushButton("▲")
        self._btn_prev.setFixedHeight(26)
        self._btn_prev.setStyleSheet(nav_style)
        self._btn_prev.clicked.connect(lambda: self.navigate_requested.emit(-1))
        self._btn_prev.setVisible(False)
        layout.addWidget(self._btn_prev)

        self._btn_next = QPushButton("▼")
        self._btn_next.setFixedHeight(26)
        self._btn_next.setStyleSheet(nav_style)
        self._btn_next.clicked.connect(lambda: self.navigate_requested.emit(1))
        self._btn_next.setVisible(False)
        layout.addWidget(self._btn_next)

        # 结果计数标签
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {theme.text_dim}; font-size: 11px; padding: 0 4px;"
        )
        self._count_label.setVisible(False)
        layout.addWidget(self._count_label)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {theme.text_dim};
                border: none; font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ color: {theme.cyber_red}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(close_btn)

        self._input.returnPressed.connect(self._do_search)

    def show(self):
        super().show()
        self._input.setFocus()
        self._input.selectAll()

    def _do_search(self):
        keyword = self._input.text().strip()
        if keyword:
            self.search_requested.emit(keyword)

    def update_count(self, current: int, total: int):
        """更新结果计数显示。"""
        has_results = total > 0
        self._btn_prev.setVisible(has_results)
        self._btn_next.setVisible(has_results)
        self._count_label.setVisible(has_results)
        if has_results:
            self._count_label.setText(f"{current}/{total}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
        super().keyPressEvent(event)


# ============================================================
# 主页面
# ============================================================

class JsonViewerPage(QWidget):
    """源数据浏览器主页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_file: Optional[str] = None
        self._search_results: list = []
        self._search_index: int = -1
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        layout.addWidget(self._build_toolbar())

        # 搜索面板
        self._search_panel = SearchPanel()
        self._search_panel.search_requested.connect(self._on_search)
        self._search_panel.navigate_requested.connect(self._on_navigate)
        self._search_panel.close_requested.connect(self._on_search_close)
        layout.addWidget(self._search_panel)

        # 主体：文件树 + JSON 树 + 信息面板
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,0.04); }")

        # 文件树
        self._file_tree = FileTreeWidget()
        self._file_tree.file_selected.connect(self._on_file_selected)
        self._file_tree.setFixedWidth(260)
        splitter.addWidget(self._file_tree)

        # 右侧容器
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # JSON 树
        self._json_tree = JsonTreeWidget()
        self._json_tree.node_selected.connect(self._on_node_selected)
        right_layout.addWidget(self._json_tree, 1)

        # 底部信息面板
        self._info_panel = QFrame()
        self._info_panel.setStyleSheet(f"""
            QFrame {{
                background: {theme.card_bg};
                border-top: 1px solid rgba(255,255,255,0.04);
                min-height: 80px;
                max-height: 120px;
            }}
        """)
        info_layout = QHBoxLayout(self._info_panel)
        info_layout.setContentsMargins(14, 8, 14, 8)
        info_layout.setSpacing(16)

        # 节点信息
        self._info_label = QLabel(S("json_viewer", "info_hint"))
        self._info_label.setStyleSheet(
            f"color: {theme.text_dim}; font-size: 11px; font-family: Consolas, monospace;"
        )
        self._info_label.setWordWrap(True)
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._info_label, 1)

        # 统计信息
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet(
            f"color: {theme.text_dim}; font-size: 11px;"
        )
        self._stats_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        info_layout.addWidget(self._stats_label)

        right_layout.addWidget(self._info_panel)

        splitter.addWidget(right_widget)
        splitter.setSizes([260, 740])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

    def _build_toolbar(self) -> QFrame:
        """构建工具栏。"""
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background: {theme.card_bg};
                border-bottom: 1px solid rgba(255,255,255,0.04);
                min-height: 38px;
                max-height: 38px;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        file_label = QLabel("📂 源数据浏览器")
        file_label.setStyleSheet(
            f"color: {theme.cyber_cyan}; font-size: 13px; font-weight: 600;"
        )
        layout.addWidget(file_label)

        layout.addStretch()

        # 搜索按钮
        self._btn_search = QPushButton("🔍 搜索")
        self._btn_search.setFixedHeight(26)
        self._btn_search.setStyleSheet(self._btn_style())
        self._btn_search.clicked.connect(self._toggle_search)
        layout.addWidget(self._btn_search)

        # 复制路径
        self._btn_copy_path = QPushButton("📋 复制路径")
        self._btn_copy_path.setFixedHeight(26)
        self._btn_copy_path.setStyleSheet(self._btn_style())
        self._btn_copy_path.clicked.connect(self._copy_path)
        layout.addWidget(self._btn_copy_path)

        # 展开/折叠
        self._btn_expand = QPushButton("📖 全部展开")
        self._btn_expand.setFixedHeight(26)
        self._btn_expand.setStyleSheet(self._btn_style())
        self._btn_expand.clicked.connect(self._toggle_expand)
        layout.addWidget(self._btn_expand)

        # 刷新
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setFixedHeight(26)
        refresh_btn.setStyleSheet(self._btn_style())
        # 延迟绑定：_file_tree 在 _build_ui 中稍后创建
        refresh_btn.clicked.connect(lambda: self._file_tree.refresh())
        layout.addWidget(refresh_btn)

        return bar

    def _btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {theme.text_dim};
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.06);
                color: {theme.text};
                border-color: rgba(255,255,255,0.12);
            }}
        """

    # ======================== 事件处理 ========================

    def _on_file_selected(self, file_path: str, name: str):
        """选择文件时加载 JSON。"""
        self._current_file = file_path
        self._json_tree.load_file(file_path)
        self._info_label.setText(f"已加载: {name}")
        self._update_stats()

    def _on_node_selected(self, info: dict):
        """选中 JSON 节点时更新信息面板。"""
        lines = []
        lines.append(f"路径: {info['path']}")
        lines.append(f"类型: {info['type']}")
        lines.append(f"深度: {info['depth']}")
        if "value" in info:
            value = info["value"]
            if len(value) > 200:
                value = value[:200] + "..."
            lines.append(f"值: {value}")
        self._info_label.setText("\n".join(lines))

    def _toggle_search(self):
        if self._search_panel.isVisible():
            self._search_panel.hide()
        else:
            self._search_panel.show()

    def _on_search(self, keyword: str):
        """执行搜索并导航到第一个结果。"""
        self._json_tree.clear_highlights()
        results = self._json_tree.search(keyword)
        self._search_results = results
        self._search_index = -1

        if not results:
            self._info_label.setText(f"未找到匹配 \"{keyword}\" 的结果")
            self._search_panel.update_count(0, 0)
            return

        # 导航到第一个结果
        self._search_index = 0
        self._navigate_to_result(0)

    def _on_navigate(self, direction: int):
        """导航搜索结果：direction=-1 上一个，+1 下一个。"""
        if not self._search_results:
            return
        total = len(self._search_results)
        self._search_index = (self._search_index + direction) % total
        self._navigate_to_result(self._search_index)

    def _navigate_to_result(self, index: int):
        """定位到第 index 个搜索结果。"""
        if index < 0 or index >= len(self._search_results):
            return
        result = self._search_results[index]
        path = result["path"]

        # 清除之前的高亮
        self._json_tree.clear_highlights()

        # 导航并高亮
        item = self._json_tree.navigate_to_path(path)
        if item:
            self._json_tree.highlight_item(item)

        # 更新计数
        self._search_panel.update_count(index + 1, len(self._search_results))

        # 更新信息面板
        r = result
        if r["type"] == "string_value":
            self._info_label.setText(
                f"搜索结果 {index + 1}/{len(self._search_results)}\n"
                f"路径: {r['path']}\n"
                f"值: \"{r['value']}\""
            )
        else:
            self._info_label.setText(
                f"搜索结果 {index + 1}/{len(self._search_results)}\n"
                f"路径: {r['path']}\n"
                f"匹配: key \"{r['key']}\""
            )

    def _on_search_close(self):
        self._search_panel.hide()

    def _copy_path(self):
        """复制当前选中节点的路径。"""
        try:
            items = self._json_tree.selectedItems()
            if items:
                node: JsonNode = items[0].data(0, Qt.ItemDataRole.UserRole)
                if node:
                    QApplication.clipboard().setText(node.path)
                    self._info_label.setText(f"已复制: {node.path}")
        except Exception:
            pass

    def _toggle_expand(self):
        """展开/折叠所有顶层节点。"""
        if self._btn_expand.text() == "📖 全部展开":
            self._json_tree.expandAll()
            self._btn_expand.setText("📕 全部折叠")
        else:
            self._json_tree.collapseAll()
            self._btn_expand.setText("📖 全部展开")
        self._update_stats()

    def _update_stats(self):
        """更新统计信息。"""
        stats = self._json_tree.get_stats()
        if stats["total"] > 0:
            self._stats_label.setText(
                f"根节点: {stats['total']:,} 项\n"
                f"已加载节点: {stats['loaded_nodes']:,}\n"
                f"最深嵌套: {stats['max_depth']} 层"
            )

    def closeEvent(self, event):
        self._json_tree._loader.clear()
        super().closeEvent(event)