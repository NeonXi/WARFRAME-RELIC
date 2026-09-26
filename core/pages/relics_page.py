"""
[L-Page] RelicsPage — 遗物查询页面。

依赖: PySide6 + core.services.item_service + core.services.localization_service
用途: 查询遗物内含物品、出入库状态、掉落途径。

功能:
  - 关键词搜索遗物（支持中/英文/时代缩写）
  - 显示遗物入库/可获取状态
  - 遗物内含物品列表（中文名称 + 稀有度颜色 + 掉落概率）
  - 掉落途径（自动中文化）

数据源: warframe.db → ItemService.get_relic_contents() / get_relic_drop_locations()

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.services/*(读), PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接), 任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止遗物数据加载在 Page 内实现 → 走 Service
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5,别走捷径。
"""


from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QSizePolicy,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPoint
from PySide6.QtGui import QFont, QColor, QCursor

from core.pages.base_page import PageBase
from core.widgets.panel import CyberPanel
from core.widgets.button import CyberButton
from core.widgets.line_edit import CyberLineEdit
from core.widgets.card import CyberCard
from core.services.item_service import ItemService
from core.services.localization_service import (
    translate_location, RARITY_CN, SOURCE_TYPE_CN,
)
from core.tokens.manager import TokenManager


# ── 时代英→中映射（DB 可能没有，硬编码回退）──
_TIER_CN = {
    "Lith": "古纪", "Meso": "前纪", "Neo": "中纪",
    "Axi": "后纪", "Requiem": "安魂", "Vanguard": "先锋",
}

_STATE_CN = {
    "Intact": "完好", "Exceptional": "优异",
    "Flawless": "无瑕", "Radiant": "光辉",
}


class RelicsPage(PageBase):
    """遗物查询页面。"""

    page_id = "relics"
    page_title = ""
    page_icon = "nav_items"   # 复用物品图标（后续可替换为专用图标）

    # ── 稀有度颜色 token 映射 ──
    _RARITY_TOKENS = {
        "Common":    ("raw.game.copper",  "青铜"),
        "Uncommon":  ("raw.game.silver",  "白银"),
        "Rare":      ("raw.game.gold",    "黄金"),
        "Legendary": ("raw.game.gold",    "传说"),
    }

    # ── HTML 内联半透明背景色（QSS/HTML 不支持 token 解析）──
    # 这些颜色在 __init__ 中从 Token 动态解析，此处仅作类型声明
    _BG_VAULTED: str = ""   # 入库状态：红色淡底
    _BG_AVAILABLE: str = ""  # 出库状态：绿色淡底

    def __init__(self):
        self._svc = ItemService()
        self._current_results: list[dict] = []
        self._selected_relic: dict | None = None
        self._suggest_timer = None

        PageBase.__init__(self)

        # 从 Token 解析 HTML 内联颜色（QSS/HTML 不支持运行时 token 解析）
        _rv = TokenManager.instance().get_qcolor("semantic.danger")
        _ra = TokenManager.instance().get_qcolor("brand.green")
        type(self)._BG_VAULTED = f"rgba({_rv.red()},{_rv.green()},{_rv.blue()},0.15)"
        type(self)._BG_AVAILABLE = f"rgba({_ra.red()},{_ra.green()},{_ra.blue()},0.12)"

        self.page_title = self._copy("nav.relics", "遗物查询")

        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(250)
        self._suggest_timer.timeout.connect(self._on_suggest_trigger)

    def build_content(self) -> QWidget:
        """构建遗物内容查询页(遗物选择 + 部件概率表)。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            self._spacing("lg", 20), self._spacing("sm", 8),
            self._spacing("lg", 20), self._spacing("lg", 20)
        )
        layout.setSpacing(self._spacing("xs", 4))

        # ── 标题 ──
        title = QLabel(self._copy("relics.title", "遗物检索"))
        title.setFont(QFont("Iceberg", self._font_size("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        desc = QLabel(
            self._copy("relics.desc",
                       "查询遗物内含 Prime 部件、出入库状态及掉落途径")
        )
        self._style(
            desc,
            color="text.tertiary",
            font_size="sm",
            padding=("0", "0", "12px", "0"),
        )
        layout.addWidget(desc)

        # ── 搜索栏 ──
        search_card = CyberCard(title=self._copy("relics.card_search", "搜索条件"))
        search_layout = search_card.content_layout()
        search_layout.setContentsMargins(
            self._spacing("md", 12), self._spacing("xs", 4),
            self._spacing("md", 12), self._spacing("xs", 4)
        )
        search_layout.setSpacing(self._spacing("sm", 8))

        search_row = QHBoxLayout()
        search_label = QLabel(self._copy("relics.label_keyword", "关键词:"))
        search_label.setStyleSheet(
            f"color: {self._color('text.secondary')}; "
            f"font-size: {self._font_size('sm_md', 13)}px;"
        )
        search_label.setFixedWidth(self._spacing("label_w", 60))
        search_row.addWidget(search_label)

        self._search_input = CyberLineEdit(
            placeholder=self._copy("relics.placeholder_search",
                                   "输入遗物名称，如 Axi A1、Lith S2...")
        )
        self._search_input.setMinimumWidth(300)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input, stretch=1)

        btn_search = CyberButton(text=self._copy("relics.btn_search", "搜索"), variant="solid")
        btn_search.setFixedWidth(self._spacing("btn_sm", 80))
        btn_search.clicked.connect(self._on_search)
        search_row.addWidget(btn_search)

        search_layout.addLayout(search_row)
        layout.addWidget(search_card)

        # ── 统计栏 ──
        self._stats_bar = QLabel("")
        self._stats_bar.setStyleSheet(
            f"color: {self._color('text.tertiary')}; "
            f"font-size: {self._font_size('xs', 11)}px; padding: 2px 0;"
        )
        layout.addWidget(self._stats_bar)

        # ── 结果列表 ──
        result_card = CyberCard(title=self._copy("relics.card_result", "搜索结果"))
        result_layout = result_card.content_layout()
        result_layout.setContentsMargins(
            self._spacing("xs", 4), self._spacing("xs", 4),
            self._spacing("xs", 4), self._spacing("xs", 4)
        )
        result_layout.setSpacing(4)

        self._result_list = QListWidget()
        self._result_list.setFrameShape(QFrame.Shape.NoFrame)
        self._result_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._result_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._result_list.itemClicked.connect(self._on_item_clicked)
        self._result_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._result_list.setMouseTracking(True)
        self._result_list.itemEntered.connect(self._on_item_hovered)
        self._result_list.viewport().installEventFilter(self)

        # 复杂 QSS(多选择器 + rgba)走 raw 通道;callable 形式支持主题切换重放
        def _list_qss():
            hover_bg = self._color("components.list_item.bg_hover")
            ac = self._color("accent.primary")
            sb = TokenManager.instance().get_qcolor("border.subtle")
            return (
                f"QListWidget {{"
                f"  background-color: transparent;"
                f"  border: none;"
                f"  outline: none;"
                f"  font-size: {self._font_size('sm_md', 13)}px;"
                f"}}"
                f"QListWidget::item {{"
                f"  color: {self._color('text.primary')};"
                f"  padding: {self._spacing('spacing.sm', 10)}px {self._spacing('spacing.md', 12)}px;"
                f"  border-bottom: 1px solid rgba({sb.red()}, {sb.green()}, {sb.blue()}, 0.05);"
                f"  border-radius: {self._spacing('corner.xs', 4)}px;"
                f"}}"
                f"QListWidget::item:selected {{"
                f"  background-color: {hover_bg};"
                f"  color: {ac};"
                f"}}"
                f"QListWidget::item:hover {{"
                f"  background-color: {hover_bg};"
                f"}}"
            )
        self._style(self._result_list, raw=_list_qss)
        self._result_list.setMinimumHeight(300)
        self._result_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        result_layout.addWidget(self._result_list)
        layout.addWidget(result_card)

        # ── 详情面板 ──
        self._detail_card = CyberCard(title=self._copy("relics.card_detail", "遗物详情"))
        detail_layout = self._detail_card.content_layout()
        detail_layout.setContentsMargins(
            self._spacing("md", 16), self._spacing("lg_xl", 28),
            self._spacing("md", 16), self._spacing("md", 16)
        )
        detail_layout.setSpacing(8)

        self._detail_content = QLabel(
            self._copy("relics.detail_hint", "点击上方结果查看详细信息")
        )
        self._detail_content.setWordWrap(True)
        self._detail_content.setStyleSheet(
            f"color: {self._color('text.tertiary')}; "
            f"font-size: {self._font_size('sm_md', 13)}px; padding: 8px 0;"
        )
        detail_layout.addWidget(self._detail_content)

        self._detail_card.setVisible(False)
        layout.addWidget(self._detail_card)

        layout.addStretch()

        return container

    # ════════════════════════════════════
    #  搜索 & 联想
    # ════════════════════════════════════

    def on_enter(self):
        """页面激活时检查数据库状态。"""
        self._check_db_status()

    def _on_search_text_changed(self, text: str):
        """输入变化 → 防抖触发联想。"""
        if len(text.strip()) < 1:
            return
        self._suggest_timer.start()

    def _on_suggest_trigger(self):
        """防抖到期 → 执行联想。"""
        query = self._search_input.text().strip()
        if not query or len(query) < 1:
            return
        results = self._svc.search_relics(query, limit=30)
        if results:
            self._populate_results(results, is_suggest=True)

    def _on_search(self):
        """点击搜索 / 回车 → 完整搜索。"""
        query = self._search_input.text().strip()
        results = self._svc.search_relics(query, limit=200)
        self._current_results = results
        self._populate_results(results, is_suggest=False)

    def _populate_results(self, results: list[dict], is_suggest: bool = False):
        """填充结果列表。"""
        self._result_list.clear()

        if not results:
            empty = QListWidgetItem(self._copy("relics.no_results", "未找到匹配的遗物"))
            empty.setData(Qt.ItemDataRole.UserRole, None)
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._result_list.addItem(empty)
            self._update_stats_bar(0)
            return

        for r in results:
            tier = r.get("tier", "")
            name = r.get("relic_name", "")
            state = r.get("state", "Intact")
            vaulted = bool(r.get("vaulted", 0))

            # 构建显示文本
            tier_cn = _TIER_CN.get(tier, tier)
            display = f"{tier_cn} {name}"
            if state != "Intact":
                state_cn = _STATE_CN.get(state, state)
                display += f" ({state_cn})"

            # 入库标记
            if vaulted:
                display += f" [{self._copy('relics.status_vaulted', '入库')}]"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._result_list.addItem(item)

        self._update_stats_bar(len(results))

    def _update_stats_bar(self, count: int):
        """更新统计栏。"""
        if count == 0:
            self._stats_bar.setText("")
        else:
            self._stats_bar.setText(
                self._copy("relics.result_count", f"共 {count} 条结果")
            )

    # ════════════════════════════════════
    #  结果交互
    # ════════════════════════════════════

    def _on_item_clicked(self, item: QListWidgetItem):
        """单击 → 显示详情。"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        self._show_detail(data)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """双击 → 复制名称。"""
        from PySide6.QtWidgets import QApplication
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            tier = data.get("tier", "")
            name = data.get("relic_name", "")
            QApplication.clipboard().setText(f"{tier} {name}")

    def eventFilter(self, obj, event):
        """拦截鼠标离开事件。"""
        from PySide6.QtCore import QEvent
        if obj is self._result_list.viewport():
            if event.type() == QEvent.Type.Leave:
                self._on_item_left()
        return super().eventFilter(obj, event)

    def _on_item_hovered(self, item: QListWidgetItem):
        """悬停 → 显示悬浮窗。"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            self._hide_tooltip()
            return
        html = self._build_hover_html(data)
        if not html:
            self._hide_tooltip()
            return
        self._show_tooltip_widget(html, item)

    def _on_item_left(self):
        """鼠标离开 → 延迟隐藏。"""
        if hasattr(self, '_tooltip_hide_timer'):
            self._tooltip_hide_timer.start(150)

    # ════════════════════════════════════
    #  悬浮窗
    # ════════════════════════════════════

    def _create_tooltip_widget(self) -> QLabel:
        """创建悬浮窗 QLabel。"""
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        tip = QLabel(self.window())
        tip.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        tip.setTextFormat(Qt.TextFormat.RichText)
        tip.setOpenExternalLinks(False)
        tip.setWordWrap(False)

        bg = self._color("components.card.bg")
        border_color = self._color("border.subtle")
        tip.setStyleSheet(
            f"QLabel {{"
            f"  background:{bg};"
            f"  border:1px solid {border_color};"
            f"  border-radius:8px;"
            f"  padding:10px 14px;"
            f"}}"
        )

        shadow = QGraphicsDropShadowEffect(tip)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 4)
        tip.setGraphicsEffect(shadow)

        tip.enterEvent = lambda e: (
            getattr(self, '_tooltip_hide_timer',
                    type('', (), {'start': lambda *a: None})()).start(0)
            if hasattr(self, '_tooltip_hide_timer') else None,
            None)[-1] or None
        tip.leaveEvent = lambda e: self._hide_tooltip()

        return tip

    def _show_tooltip_widget(self, html: str, item: QListWidgetItem):
        """定位并显示悬浮窗。"""
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        scr_geo = screen.availableGeometry() if screen else None

        if not hasattr(self, '_tip_widget') or self._tip_widget is None:
            self._tip_widget = self._create_tooltip_widget()
        if not hasattr(self, '_tooltip_hide_timer'):
            self._tooltip_hide_timer = QTimer(self)
            self._tooltip_hide_timer.setSingleShot(True)
            self._tooltip_hide_timer.timeout.connect(self._hide_tooltip)

        tip = self._tip_widget
        tip.setText(html)
        tip.adjustSize()

        pos = QCursor.pos() + QPoint(16, 16)

        if scr_geo:
            if pos.x() + tip.width() > scr_geo.right():
                pos.setX(scr_geo.right() - tip.width() - 4)
            if pos.y() + tip.height() > scr_geo.bottom():
                pos.setY(max(scr_geo.top(), pos.y() - tip.height() - 32))
            if pos.x() < scr_geo.left():
                pos.setX(scr_geo.left() + 4)

        tip.move(pos)
        tip.show()
        tip.raise_()

    def _hide_tooltip(self):
        """隐藏悬浮窗。"""
        if hasattr(self, '_tip_widget') and self._tip_widget is not None:
            self._tip_widget.hide()

    # ════════════════════════════════════
    #  HTML 构建
    # ════════════════════════════════════

    def _build_hover_html(self, relic_data: dict) -> str:
        """构建悬浮窗 HTML。"""
        tier = relic_data.get("tier", "")
        name = relic_data.get("relic_name", "")
        state = relic_data.get("state", "Intact")
        vaulted = bool(relic_data.get("vaulted", 0))

        tier_cn = _TIER_CN.get(tier, tier)
        full_name = f"{tier_cn} {name}"
        if state != "Intact":
            state_cn = _STATE_CN.get(state, state)
            full_name += f" / {state_cn}"

        bg = self._color("components.card.bg")
        border_color = self._color("border.subtle")
        accent = self._color("accent.primary")
        text_main = self._color("text.primary")
        text_dim = self._color("text.disabled")
        red = self._color("semantic.danger")
        green = self._color("semantic.success")
        c_gold = self._color("raw.game.gold")
        c_silver = self._color("raw.game.silver")
        c_copper = self._color("raw.game.copper")

        parts = [f"<div style='max-width:400px;font-family:Microsoft YaHei,sans-serif;'>"]

        # 标题行
        name_color = red if vaulted else green
        parts.append(
            f"<div style='font-size:13px;font-weight:bold;color:{name_color};"
            f"margin-bottom:6px;padding-bottom:4px;"
            f"border-bottom:1px solid {border_color};'>"
            f"{full_name}</div>"
        )

        # 入库/出库状态
        if vaulted:
            parts.append(
                f"<div style='margin-top:4px;padding:3px 8px;"
                f"background:{self._BG_VAULTED};border-radius:4px;"
                f"border-left:3px solid {red};'>"
                f"<span style='color:{red};font-size:11px;font-weight:bold;'>"
                f"| {self._copy('relics.status_vaulted', '入库 (Vaulted)')}</span></div>"
            )
        else:
            parts.append(
                f"<div style='margin-top:4px;padding:3px 8px;"
                f"background:{self._BG_AVAILABLE};border-radius:4px;"
                f"border-left:3px solid {green};'>"
                f"<span style='color:{green};font-size:11px;font-weight:bold;'>"
                f"| {self._copy('relics.status_available', '出库 (Available)')}</span></div>"
            )

        # 内含物品摘要
        relic_key = f"{tier} {name}"
        contents = self._svc.get_relic_contents(relic_key)
        items_list = contents.get("contents", [])
        if items_list:
            parts.append(f"<div style='margin-top:8px;'>")
            parts.append(
                f"<span style='color:{c_gold};font-size:11px;font-weight:bold;'>"
                f"| {self._copy('relics.label_contents', '内含物品')} ({len(items_list)})</span>"
            )

            rarity_colors = {"Rare": c_gold, "Uncommon": c_silver, "Common": c_copper}
            for item in items_list[:6]:
                zh = item.get("zh_name", "") or item.get("item_name", "")
                rarity = item.get("rarity", "?")
                chance = item.get("chance", 0)
                rc = rarity_colors.get(rarity, text_dim)
                rarity_cn = RARITY_CN.get(rarity, rarity)
                chance_str = f"{chance:.1f}%" if chance > 0 else ""
                parts.append(
                    f"<div style='padding:1px 0 1px 12px;color:{rc};font-size:11px;'>"
                    f"&bull; {zh}"
                    f" <span style='color:{text_dim};'>{rarity_cn}</span>"
                    f"{f' <span style=\"color:{text_dim};\">({chance_str})</span>' if chance_str else ''}"
                    f"</div>"
                )
            if len(items_list) > 6:
                parts.append(
                    f"<div style='padding:1px 0 1px 12px;color:{text_dim};font-size:10px;'>"
                    f"... {self._copy('common.more_items', '还有 {n} 个', n=len(items_list) - 6)}</div>"
                )
            parts.append("</div>")

        parts.append("</div>")
        return "\n".join(parts)

    # ════════════════════════════════════
    #  详情面板
    # ════════════════════════════════════

    def _show_detail(self, relic_data: dict):
        """构建详情 HTML 并显示。"""
        self._selected_relic = relic_data
        tier = relic_data.get("tier", "")
        name = relic_data.get("relic_name", "")
        state = relic_data.get("state", "Intact")
        vaulted = bool(relic_data.get("vaulted", 0))

        tier_cn = _TIER_CN.get(tier, tier)
        state_cn = _STATE_CN.get(state, state)
        relic_key = f"{tier} {name}"

        # 获取完整数据
        contents = self._svc.get_relic_contents(relic_key)
        drop_locs, drop_total = self._svc.get_relic_drop_locations(relic_key)

        bg = self._color("components.card.bg")
        border_color = self._color("border.subtle")
        accent = self._color("accent.primary")
        text_main = self._color("text.primary")
        text_dim = self._color("text.disabled")
        text_sec = self._color("text.secondary")
        red = self._color("semantic.danger")
        green = self._color("semantic.success")
        c_gold = self._color("raw.game.gold")
        c_silver = self._color("raw.game.silver")
        c_copper = self._color("raw.game.copper")

        lines = []

        # ── 标题 ──
        display_name = f"{tier_cn} {name}"
        if state != "Intact":
            display_name += f" / {state_cn}"
        name_color = red if vaulted else green
        lines.append(
            f"<h3 style='color:{name_color};margin:0 0 8px 0;'>{display_name}</h3>"
        )

        # ── 属性 ──
        attr_lines = []
        attr_lines.append(
            f"{self._copy('relics.label_tier', '时代')}: {tier_cn}"
        )
        attr_lines.append(
            f"{self._copy('relics.label_state', '精炼度')}: {state_cn}"
        )
        status_text = (
            self._copy("relics.status_vaulted", "入库")
            if vaulted else
            self._copy("relics.status_available", "出库")
        )
        status_color = red if vaulted else green
        attr_lines.append(
            f"{self._copy('common.status', '状态')}: "
            f"<span style='color:{status_color};'>{status_text}</span>"
        )
        lines.append("<br>".join(attr_lines))

        # ── 分隔线 ──
        lines.append(f"<hr style='border:none;border-top:1px solid {border_color};margin:10px 0;'>")

        # ── 内含物品 ──
        items_list = contents.get("contents", [])
        if items_list:
            lines.append(
                f"<b style='color:{c_gold};'>{self._copy('relics.label_contents', '内含物品')}</b> "
                f"({len(items_list)})<br>"
            )
            rarity_colors = {"Rare": c_gold, "Uncommon": c_silver, "Common": c_copper}
            for item in items_list:
                zh = item.get("zh_name", "") or item.get("item_name", "")
                rarity = item.get("rarity", "?")
                chance = item.get("chance", 0)
                rc = rarity_colors.get(rarity, text_dim)
                rarity_cn = RARITY_CN.get(rarity, rarity)
                chance_str = f"{chance:.1f}%" if chance > 0 else ""
                lines.append(
                    f"&nbsp;&nbsp;<span style='color:{rc};'>{zh}</span>"
                    f" <span style='color:{text_dim};font-size:11px;'>"
                    f"[{rarity_cn}]"
                    f"{f' {chance_str}' if chance_str else ''}"
                    f"</span><br>"
                )

        # ── 掉落途径 ──
        if drop_locs:
            count_label = f"共{drop_total}" if drop_total <= 40 else f"共{drop_total}，显示40"
            lines.append(f"<hr style='border:none;border-top:1px solid {border_color};margin:10px 0;'>")
            lines.append(
                f"<b style='color:{accent};'>"
                f"{self._copy('relics.label_drops', '掉落途径')}</b> "
                f"({count_label})<br>"
            )

            # 按来源类型分组
            by_type: dict[str, list] = {}
            for loc in drop_locs:
                st = loc.get("source_type", "missionRewards")
                if st not in by_type:
                    by_type[st] = []
                by_type[st].append(loc)

            for st, items in by_type.items():
                st_cn = SOURCE_TYPE_CN.get(st, st)
                lines.append(
                    f"<b style='color:{text_sec};font-size:11px;'>"
                    f"&nbsp;&nbsp;{st_cn} ({len(items)})</b><br>"
                )
                for loc in items[:8]:
                    planet = translate_location(loc.get("planet", ""))
                    node = translate_location(loc.get("node_name", ""))
                    mode = translate_location(loc.get("game_mode", ""))
                    rotation = loc.get("rotation", "")
                    chance = loc.get("chance", 0)

                    loc_text = f"{planet}"
                    if node and node != planet:
                        loc_text += f" - {node}"
                    if mode:
                        loc_text += f" ({mode})"
                    if rotation:
                        loc_text += self._copy("common.label_rotation", " 轮次{rot}", rot=rotation)
                    if 0 < chance < 100:
                        loc_text += f" {chance:.0f}%"
                    elif chance >= 100:
                        loc_text += f" {self._copy('items.detail_guaranteed', '必掉')}"

                    lines.append(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;"
                        f"<span style='color:{text_main};font-size:11px;'>{loc_text}</span><br>"
                    )
                if len(items) > 8:
                    lines.append(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;"
                        f"<span style='color:{text_dim};font-size:10px;'>"
                        f"... 还有 {len(items) - 8} 条</span><br>"
                    )

        html = "\n".join(lines)
        self._detail_content.setTextFormat(Qt.TextFormat.RichText)
        self._detail_content.setText(html)
        self._detail_card.setVisible(True)

    # ════════════════════════════════════
    #  辅助方法
    # ════════════════════════════════════

    def _check_db_status(self):
        """检查数据库是否可用。"""
        try:
            test = self._svc.search_relics("", limit=1)
        except Exception as e:
            danger_color = self._color("semantic.danger")
            self._detail_content.setText(
                f"<span style='color:{danger_color};'>"
                f"{self._copy('relics.err_db_connect', '数据库连接失败: {error}', error=e)}</span>"
            )
            self._detail_card.setVisible(True)
