"""
[L4] CyberRivenResultTable — 紫卡计算结果表格（赛博风格）

继承: CyberWidgetMixin + QTableWidget
依赖: core.tokens.manager
职责: 以冻结表头的三列表格展示词条计算结果（词条名称 / 最低值 / 最高值），
      支持「正面」与「负面」两种语义（负面值列用危险色强调）。

交互:
- 点击「词条名称」列的任意单元格：将该词条加入置顶列表（排到表格最前面）；
  再次点击已置顶的同一词条则从列表中移除，取消置顶。
- 支持同时置顶多条词条，置顶顺序与用户点击顺序一致。
- 切换武器/布局后，置顶的词条若在新数据里不存在，自动从列表中移除。

设计要点:
- 冻结表头：QTableWidget 的水平表头在表格内部纵向滚动时固定不动，天然满足
  「冻结表头」需求；表格自身限定可视行数、超出部分内部滚动，
  避免整页滚动把表头带走。
- 主题切换：QSS 内联了 token 颜色，需在 theme_changed 时重建（cyber_refresh_style）；
  同时置顶高亮色也随主题重新取 token。
- 单位着色：数值列右对齐；负面语义下最低/最高值用 alias.semantic.danger 着色，
  与正面区隔，呼应「负面词条」的视觉语义。

禁止依赖: core.services/* / core.pages/* / core.state/* / data/*
           （Widget 只绘制与发信号，数据由页面经 set_rows() 注入）

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4 (L4/L5 控件层)

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QTableWidget.__init__(self, parent)
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止调 Service / 发网络请求 / 读写 JSON → 数据由 set_rows() 注入
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QTableWidget, QWidget, QAbstractItemView, QHeaderView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from core.widgets.base import CyberWidgetMixin


class CyberRivenResultTable(CyberWidgetMixin, QTableWidget):
    """紫卡计算结果表格（词条名称 / 最低值 / 最高值，冻结表头，支持多选置顶）。"""

    # 数值列固定宽度（4 的倍数，适配中文百分比「+187.9%」与数字）
    _VALUE_COL_WIDTH = 120
    # 单行高度（4 的倍数）
    _ROW_HEIGHT = 28
    # 最多直接展开的可视行数；超出则表格内部滚动（表头保持冻结）
    _MAX_VISIBLE_ROWS = 14

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        is_negative: bool = False,
    ):
        QTableWidget.__init__(self, parent)

        self._is_negative = is_negative
        self._raw_rows: list[dict] = []   # 服务层注入的原始数据
        self._pinned_names: list[str] = []  # 当前置顶的词条名列表（按点击顺序）

        # 三列：词条名称 / 最低值 / 最高值（表头文案取自 copy token，缺省兜底中文）
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels([
            self.copy("riven_calc.col_name", "词条名称"),
            self.copy("riven_calc.col_min", "最低值"),
            self.copy("riven_calc.col_max", "最高值"),
        ])

        # 列宽：名称拉伸占满，两数值列固定
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, self._VALUE_COL_WIDTH)
        self.setColumnWidth(2, self._VALUE_COL_WIDTH)
        # 隐藏左上角按钮
        self.setCornerButtonEnabled(False)

        # 行高固定（整行等高，数字不抖）
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(self._ROW_HEIGHT)

        # 禁编辑 / 禁原生选择（我们自己管置顶高亮）/ 禁聚焦高亮
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAlternatingRowColors(True)
        # 表格内部纵向滚动（超出可视行数时出现），表头因此保持冻结
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 点击词条名称列 → 置顶/取消置顶
        self.cellClicked.connect(self._on_cell_clicked)

        # 应用 token 配色（主题切换时重建）
        self._cyber_subscribe_theme()
        self.cyber_refresh_style()

    # ── 数据注入 ──

    def set_rows(self, rows: list[dict]) -> None:
        """填充结果行。

        Args:
            rows: 服务层产出的结果行列表（每行为 dict，含 name/min_str/max_str）；
                  顺序已在服务层排好（按最高值绝对值降序），控件不再排序。
        """
        self._raw_rows = list(rows)
        # 过滤掉在新数据里已不存在的置顶词条
        valid_names = {r.get("name") for r in self._raw_rows}
        self._pinned_names = [n for n in self._pinned_names if n in valid_names]
        self._render_rows()

    # ── 置顶交互 ──

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """点击单元格：只有点击「词条名称」列（第 0 列）才触发置顶切换。

        点击新词条 → 加入置顶列表；点击已置顶词条 → 从列表移除。
        """
        if col != 0:
            return
        item = self.item(row, 0)
        if item is None:
            return
        name = item.text()
        if name in self._pinned_names:
            self._pinned_names.remove(name)
        else:
            self._pinned_names.append(name)
        self._render_rows()

    def _render_rows(self) -> None:
        """按原始数据渲染表格；置顶词条按点击顺序提到最前面并以醒目色高亮。"""
        # 按名称索引原始行（O(n) 建表，后续查找 O(1)）
        row_by_name = {r["name"]: r for r in self._raw_rows}
        pinned_set = set(self._pinned_names)

        # 置顶行按用户点击顺序排列，其余行保持原序
        pinned = [row_by_name[n] for n in self._pinned_names if n in row_by_name]
        others = [r for r in self._raw_rows if r["name"] not in pinned_set]
        rows = pinned + others

        self.setRowCount(len(rows))

        # 颜色预取
        accent = self.token_color("accent.primary")
        pinned_bg = QColor(accent)
        pinned_bg.setAlphaF(0.12)
        danger = self.token_color("alias.semantic.danger")

        for r, row in enumerate(rows):
            is_pinned = row.get("name") in pinned_set

            # 名称列
            name_item = self._make_item(
                row.get("name", ""),
                align=Qt.AlignmentFlag.AlignLeft,
                color=accent if is_pinned else None,
                bg=pinned_bg if is_pinned else None,
                bold=is_pinned,
            )
            # 数值列：负面语义保持 danger 色，置顶时背景高亮
            val_color = danger if self._is_negative else None
            min_item = self._make_item(
                row.get("min_str", ""),
                align=Qt.AlignmentFlag.AlignRight,
                color=val_color,
                bg=pinned_bg if is_pinned else None,
            )
            max_item = self._make_item(
                row.get("max_str", ""),
                align=Qt.AlignmentFlag.AlignRight,
                color=val_color,
                bg=pinned_bg if is_pinned else None,
            )

            self.setItem(r, 0, name_item)
            self.setItem(r, 1, min_item)
            self.setItem(r, 2, max_item)

        # 高度自适应：至多展开 _MAX_VISIBLE_ROWS 行，超出内部滚动
        visible = min(len(rows), self._MAX_VISIBLE_ROWS)
        header_h = self.horizontalHeader().height()
        self.setFixedHeight(header_h + visible * self._ROW_HEIGHT + 2)

    @staticmethod
    def _make_item(
        text: str,
        align: Qt.AlignmentFlag,
        color: Optional[QColor] = None,
        bg: Optional[QColor] = None,
        bold: bool = False,
    ):
        """构造一个只读表格项，可指定对齐、前景色、背景色、加粗。"""
        from PySide6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(text)
        item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        if color is not None:
            item.setForeground(color)
        if bg is not None:
            item.setBackground(bg)
        if bold:
            font = QFont(item.font())
            font.setBold(True)
            item.setFont(font)
        return item

    # ── 主题切换：重建内联 token 配色 ──

    def cyber_refresh_style(self) -> None:
        """重建 QSS（含 token 颜色），主题/沉浸模式切换时由框架调用。

        置顶高亮色也依赖当前主题 accent.primary，因此重建 QSS 后若已有数据，
        需重新渲染一次以更新置顶行的背景/文字色。
        """
        bg = self.token_color("surface.raised")
        border = self.token_color("border.default")
        text = self.token_color("text.primary")
        header_bg = self.token_color("alias.bg.raised")
        header_text = self.token_color("accent.primary")
        alt = self.token_color("surface.overlay")
        selection = self.token_color("alias.accent.secondary")

        # 背景带透明，叠在卡片之上保证可读性又不死黑
        bg_alpha = QColor(bg)
        alt_alpha = QColor(alt)
        bg_alpha.setAlphaF(0.55)
        alt_alpha.setAlphaF(0.35)

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_alpha.name(QColor.NameFormat.HexArgb)};
                border: 1px solid {border.name()};
                gridline-color: {border.name()};
                color: {text.name()};
                border-radius: 4px;
            }}
            QHeaderView::section {{
                background-color: {header_bg.name()};
                color: {header_text.name()};
                border: none;
                border-bottom: 1px solid {border.name()};
                padding: 6px 8px;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 2px 8px;
            }}
            QTableWidget::item:alternate {{
                background-color: {alt_alpha.name(QColor.NameFormat.HexArgb)};
            }}
            QTableWidget::item:selected {{
                background-color: {selection.name()};
            }}
        """)

        # 若已有数据，用新主题色重新渲染（置顶高亮色会随之更新）
        if self._raw_rows:
            self._render_rows()
