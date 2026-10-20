"""
[L4] CyberRivenResultTable — 紫卡计算结果表格（赛博风格）

继承: CyberWidgetMixin + QTableWidget
依赖: core.tokens.manager
职责: 以冻结表头的五列表格展示词条计算结果
      （词条名称 / 最低值 / 最高值 / 我的数值 / 浮动位置），
      支持「正面」与「负面」两种语义（负面值列用危险色强调）。

交互:
- 点击「词条名称」列：将该词条加入置顶列表（排到表格最前面）；
  再次点击已置顶的同一词条则从列表中移除。支持多选，顺序与点击顺序一致。
- 双击「我的数值」列：输入自己洗出的实际数值（可带 % 号），
  下方「浮动位置」列实时显示它落在浮动区间的百分比并绘制迷你进度条。
- 切换武器/布局后，置顶词条若在新数据里不存在会自动移除；
  已输入的数值按词条名保留，位置随新区间重算。

设计要点:
- 冻结表头：QTableWidget 的水平表头在表格内部纵向滚动时固定不动，天然满足
  「冻结表头」需求；表格自身限定可视行数、超出部分内部滚动，
  避免整页滚动把表头带走。
- 主题切换：QSS 内联了 token 颜色，需在 theme_changed 时重建（cyber_refresh_style）；
  置顶高亮色 / 位置进度条颜色均在绘制时实时读 token，天然跟随主题。
- 单位着色：数值列右对齐；负面语义下最低/最高值用 alias.semantic.danger 着色。
- 位置配色：正面表 高=绿 / 中=黄 / 低=灰；负面表反向（位置越高诅咒越强=越红）；
  越界统一红色并显示真实百分比。

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
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter

from core.widgets.base import CyberWidgetMixin

# ── 列索引（页面 / 测试共用契约）──
COL_NAME = 0
COL_MIN = 1
COL_MAX = 2
COL_MINE = 3
COL_POS = 4

# 浮动位置分档阈值（百分比）
_BAND_HIGH = 66.0
_BAND_MID = 33.0


# ══════════════════════════════════════════════
#  纯函数（无 Qt 依赖，可直接单测）
# ══════════════════════════════════════════════

def position_pct(value: float, lo: float, hi: float) -> Optional[float]:
    """计算数值在浮动区间 [lo, hi] 中的位置百分比。

    按绝对值比较：负值词条（如后坐力 -33.9% ~ -41.5%）的「幅度」才是
    玩家关心的强弱，因此统一用 |value| / |lo| / |hi| 计算。
    区间退化（|hi| == |lo|）时返回 None（无法定义位置）。
    """
    a, l, h = abs(value), abs(lo), abs(hi)
    span = h - l
    if abs(span) < 1e-9:
        return None
    return (a - l) / span * 100.0


def parse_input(text: str) -> Optional[float]:
    """解析用户输入的数值：允许 "150" / "150%" / "+150" / "2.5"。

    空串或非法输入返回 None（调用方据此清空该行位置）。
    """
    cleaned = (text or "").strip().replace("%", "").replace("+", "").replace("＋", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


# ══════════════════════════════════════════════
#  浮动位置列绘制（迷你进度条 + 百分比）
# ══════════════════════════════════════════════

class _PositionBarDelegate(QStyledItemDelegate):
    """「浮动位置」列委托：先画标准背景，再叠加进度条与百分比文本。

    背景交给基类绘制（保留交替行 / hover / 置顶高亮），文字清空后自行绘制，
    避免默认文字与进度条重叠。
    """

    # 进度条尺寸（4 的倍数，随列宽固定不拉伸）
    _BAR_WIDTH = 88
    _BAR_HEIGHT = 6
    _PADDING = 8
    _TEXT_GAP = 8

    def __init__(self, table: "CyberRivenResultTable"):
        QStyledItemDelegate.__init__(self, table)
        self._table = table

    def paint(self, painter: QPainter, option, index) -> None:
        # 1) 只画背景 / 交替行 / hover / 置顶高亮，文字由本委托自绘。
        #    注意不能调 super().paint()：QStyledItemDelegate.paint 内部会再执行
        #    一次 initStyleOption()，把这里清空的 opt.text 重新填上，
        #    导致默认文字与本委托文字叠加出现重影。
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # 双保险：清空文本 + 关闭 HasDisplay 特性，确保样式层不会画默认文字
        opt.text = ""
        opt.features &= ~QStyleOptionViewItem.ViewItemFeature.HasDisplay
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        data = index.data(Qt.ItemDataRole.UserRole) or {}
        pct = data.get("pct")
        out = bool(data.get("out", False))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect
        x = rect.left() + self._PADDING
        bar_y = rect.center().y() - self._BAR_HEIGHT / 2

        # 2) 轨道
        track = self._table.token_color("border.subtle")
        track.setAlphaF(0.6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(
            QRectF(x, bar_y, self._BAR_WIDTH, self._BAR_HEIGHT), 3, 3
        )

        # 3) 填充（越界时截断在 100%，颜色标红）
        text_color = self._table.token_color("text.tertiary")
        if pct is not None:
            color = self._table.band_color(float(pct), out)
            text_color = color
            ratio = max(0.0, min(1.0, float(pct) / 100.0))
            fill_w = self._BAR_WIDTH * ratio
            if fill_w > 0:
                painter.setBrush(color)
                painter.drawRoundedRect(
                    QRectF(x, bar_y, fill_w, self._BAR_HEIGHT), 3, 3
                )

        # 4) 文本（真实百分比；空值显示 "—"）
        text = index.data(Qt.ItemDataRole.DisplayRole) or "—"
        font = QFont(option.font)
        painter.setFont(font)
        painter.setPen(text_color)
        text_rect = QRectF(
            x + self._BAR_WIDTH + self._TEXT_GAP,
            rect.top(),
            max(0.0, rect.width() - self._BAR_WIDTH - self._PADDING * 2 - self._TEXT_GAP),
            rect.height(),
        )
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            str(text),
        )
        painter.restore()


# ══════════════════════════════════════════════
#  表格控件
# ══════════════════════════════════════════════

class CyberRivenResultTable(CyberWidgetMixin, QTableWidget):
    """紫卡计算结果表格（五列，冻结表头，支持多选置顶与浮动位置反算）。"""

    # 固定列宽（4 的倍数）：最低/最高/我的数值/浮动位置
    _W_MIN = 104
    _W_MAX = 104
    _W_MINE = 96
    _W_POS = 220
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
        self._raw_rows: list[dict] = []        # 服务层注入的原始数据
        self._pinned_names: list[str] = []     # 置顶词条名（按点击顺序）
        self._custom_values: dict[str, float] = {}  # 词条名 → 玩家洗出的数值
        self._rendering = False                # 程序化渲染中，屏蔽 itemChanged

        # 五列（表头文案取自 copy token，缺省兜底中文）
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels([
            self.copy("riven_calc.col_name", "词条名称"),
            self.copy("riven_calc.col_min", "最低值"),
            self.copy("riven_calc.col_max", "最高值"),
            self.copy("riven_calc.col_mine", "我的数值"),
            self.copy("riven_calc.col_pos", "浮动位置"),
        ])

        # 列宽：名称拉伸占满剩余，其余四列固定
        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col, width in (
            (COL_MIN, self._W_MIN),
            (COL_MAX, self._W_MAX),
            (COL_MINE, self._W_MINE),
            (COL_POS, self._W_POS),
        ):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(col, width)
        self.setCornerButtonEnabled(False)

        # 行高固定（整行等高，数字不抖）
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(self._ROW_HEIGHT)

        # 仅「我的数值」列可编辑（双击进入）；其它列在 _make_item 里清掉可编辑位
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        # 禁原生选择（置顶高亮自己管）/ 禁聚焦框
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAlternatingRowColors(True)
        # 表格内部纵向滚动（超出可视行数时出现），表头因此保持冻结
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 鼠标跟踪：名称列可点击置顶，需要 mouseMoveEvent 实时切换手型光标
        # （QScrollArea 的 viewport 是独立子控件，两个都要开，否则移动不响应）
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # 点击词条名称列 → 置顶/取消置顶
        self.cellClicked.connect(self._on_cell_clicked)
        # 编辑「我的数值」→ 重算该行位置
        self.itemChanged.connect(self._on_item_changed)
        # 浮动位置列交给自绘委托
        self.setItemDelegateForColumn(COL_POS, _PositionBarDelegate(self))

        # 应用 token 配色（主题切换时重建）
        self._cyber_subscribe_theme()
        self.cyber_refresh_style()

    # ── 数据注入 ──

    def set_rows(self, rows: list[dict]) -> None:
        """填充结果行。

        Args:
            rows: 服务层产出的结果行列表（每行为 dict，含
                  name/min/max/min_str/max_str）；顺序已在服务层排好。
        """
        self._raw_rows = list(rows)
        # 过滤掉在新数据里已不存在的置顶词条
        valid_names = {r.get("name") for r in self._raw_rows}
        self._pinned_names = [n for n in self._pinned_names if n in valid_names]
        self._render_rows()

    def clear_inputs(self) -> None:
        """清空所有「我的数值」并重置位置列。"""
        if not self._custom_values:
            return
        self._custom_values.clear()
        self._render_rows()

    # ── 置顶交互 ──

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """点击单元格：只有点击「词条名称」列（第 0 列）才触发置顶切换。"""
        if col != COL_NAME:
            return
        item = self.item(row, COL_NAME)
        if item is None:
            return
        name = item.text()
        if name in self._pinned_names:
            self._pinned_names.remove(name)
        else:
            self._pinned_names.append(name)
        self._render_rows()

    # ── 光标提示（名称列可点的可发现性） ──

    def mouseMoveEvent(self, event) -> None:
        """悬停词条名称列显示手型光标，其它区域/列还原默认。"""
        pos = event.position().toPoint()
        col = self.columnAt(pos.x())
        if col == COL_NAME and self.itemAt(pos) is not None:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        """移出表格：还原光标（避免残留手型）。"""
        self.viewport().unsetCursor()
        super().leaveEvent(event)

    # ── 输入 → 位置重算 ──

    def _position_for(self, row: dict, value: float) -> Optional[float]:
        """按词条单位换算后计算位置。

        "%" 词条的原始 min/max 是「×1.0 = 100%」量纲（如 1.392），
        而用户输入按百分数填写（150 表示 150%），需先 /100 对齐量纲；
        "n" 词条（穿透等）两边都是纯数字，直接比较。
        """
        raw = value / 100.0 if row.get("unit") == "%" else value
        return position_pct(raw, row.get("min", 0.0), row.get("max", 0.0))

    def _on_item_changed(self, item) -> None:
        """「我的数值」编辑完成：解析数值、缓存并重算该行位置。

        只更新本行位置单元格（不整表重建），避免编辑框/滚动位置跳变。
        """
        if self._rendering or item is None:
            return
        row, col = item.row(), item.column()
        if col != COL_MINE:
            return
        name_item = self.item(row, COL_NAME)
        if name_item is None:
            return
        row_data = name_item.data(Qt.ItemDataRole.UserRole) or {}
        name = row_data.get("name", name_item.text())

        value = parse_input(item.text())
        pct = None
        out = False

        self._rendering = True  # 下面会改 item 文本，避免递归触发
        try:
            if value is None:
                self._custom_values.pop(name, None)
                item.setText("—")
                item.setForeground(self.token_color("text.tertiary"))
            else:
                self._custom_values[name] = value
                item.setText(f"{value:g}")
                item.setForeground(self.token_color("text.primary"))
                pct = self._position_for(row_data, value)
                out = pct is not None and (pct < 0.0 or pct > 100.0)

            pos_item = self.item(row, COL_POS)
            if pos_item is not None:
                pos_item.setText(f"{pct:.1f}%" if pct is not None else "—")
                pos_item.setData(
                    Qt.ItemDataRole.UserRole, {"pct": pct, "out": out}
                )
        finally:
            self._rendering = False
        self.viewport().update()

    # ── 渲染 ──

    def _render_rows(self) -> None:
        """按原始数据渲染表格；置顶词条按点击顺序提到最前面并以醒目色高亮。"""
        row_by_name = {r["name"]: r for r in self._raw_rows}
        pinned_set = set(self._pinned_names)

        pinned = [row_by_name[n] for n in self._pinned_names if n in row_by_name]
        others = [r for r in self._raw_rows if r["name"] not in pinned_set]
        rows = pinned + others

        self._rendering = True
        try:
            self.setRowCount(len(rows))

            accent = self.token_color("accent.primary")
            pinned_bg = QColor(accent)
            pinned_bg.setAlphaF(0.12)
            danger = self.token_color("alias.semantic.danger")
            tertiary = self.token_color("text.tertiary")
            primary = self.token_color("text.primary")

            for r, row in enumerate(rows):
                name = row.get("name", "")
                is_pinned = name in pinned_set
                bg = pinned_bg if is_pinned else None
                val_color = danger if self._is_negative else None

                name_item = self._make_item(
                    name,
                    align=Qt.AlignmentFlag.AlignLeft,
                    color=accent if is_pinned else None,
                    bg=bg,
                    bold=is_pinned,
                )
                # 原始行挂在名称列上，供编辑回调取 min/max
                name_item.setData(Qt.ItemDataRole.UserRole, row)

                min_item = self._make_item(
                    row.get("min_str", ""),
                    align=Qt.AlignmentFlag.AlignRight,
                    color=val_color,
                    bg=bg,
                )
                max_item = self._make_item(
                    row.get("max_str", ""),
                    align=Qt.AlignmentFlag.AlignRight,
                    color=val_color,
                    bg=bg,
                )

                # 我的数值：已填 → 显示数值；未填 → "—" 占位（双击可编辑）
                custom = self._custom_values.get(name)
                mine_item = self._make_item(
                    f"{custom:g}" if custom is not None else "—",
                    align=Qt.AlignmentFlag.AlignRight,
                    color=primary if custom is not None else tertiary,
                    bg=bg,
                    editable=True,
                )
                mine_item.setToolTip(
                    self.copy(
                        "riven_calc.mine_tip",
                        "双击输入你洗出的数值（可带 % 号）",
                    )
                )

                # 浮动位置：数据存 UserRole，由委托绘制进度条
                pct = None
                out = False
                if custom is not None:
                    pct = self._position_for(row, custom)
                    out = pct is not None and (pct < 0.0 or pct > 100.0)
                pos_item = self._make_item(
                    f"{pct:.1f}%" if pct is not None else "—",
                    align=Qt.AlignmentFlag.AlignRight,
                    bg=bg,
                )
                pos_item.setData(
                    Qt.ItemDataRole.UserRole, {"pct": pct, "out": out}
                )

                self.setItem(r, COL_NAME, name_item)
                self.setItem(r, COL_MIN, min_item)
                self.setItem(r, COL_MAX, max_item)
                self.setItem(r, COL_MINE, mine_item)
                self.setItem(r, COL_POS, pos_item)
        finally:
            self._rendering = False

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
        editable: bool = False,
    ):
        """构造表格项：可指定对齐/前景/背景/加粗/是否可编辑。"""
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
        flags = item.flags()
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        else:
            flags &= ~Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        return item

    # ── 位置配色（供委托调用） ──

    def band_color(self, pct: float, out: bool) -> QColor:
        """按位置百分比返回颜色。

        正面表：高=绿、中=黄、低=灰；
        负面表反向：高=红（诅咒更强）、中=黄、低=绿；
        越界统一红色。
        """
        if out:
            return self.token_color("alias.semantic.danger")
        if self._is_negative:
            if pct > _BAND_HIGH:
                return self.token_color("alias.semantic.danger")
            if pct >= _BAND_MID:
                return self.token_color("alias.semantic.warning")
            return self.token_color("alias.semantic.success")
        if pct > _BAND_HIGH:
            return self.token_color("alias.semantic.success")
        if pct >= _BAND_MID:
            return self.token_color("alias.semantic.warning")
        return self.token_color("text.tertiary")

    # ── 主题切换：重建内联 token 配色 ──

    def cyber_refresh_style(self) -> None:
        """重建 QSS（含 token 颜色），主题/沉浸模式切换时由框架调用。"""
        bg = self.token_color("surface.raised")
        border = self.token_color("border.default")
        text = self.token_color("text.primary")
        header_bg = self.token_color("alias.bg.raised")
        header_text = self.token_color("accent.primary")
        alt = self.token_color("surface.overlay")
        hover = self.token_color("semantic.state.hover.bg")

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
            QTableWidget::item:hover {{
                background-color: {hover.name(QColor.NameFormat.HexArgb)};
            }}
            QTableWidget::item:alternate {{
                background-color: {alt_alpha.name(QColor.NameFormat.HexArgb)};
            }}
        """)

        # 若已有数据，用新主题色重新渲染（置顶高亮色会随之更新）
        if self._raw_rows:
            self._render_rows()
