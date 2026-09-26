"""
[L2] ItemsPage — 物品查询页面

依赖: widgets/, services/item_service.py
职责: 关键词搜索物品,显示掉落来源,支持复制/悬停预览

功能:
  - 关键词搜索(中/英/拼音联想)
  - 搜索结果列表展示(含稀有度、分类标签)
  - 悬停悬浮窗显示掉落途径(自动中文化)
  - 双击复制物品名称到剪贴板
  - 数据库状态检测与提示

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.services.item_service, PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接)
           任何反向依赖 widgets(Widget 不能调本 Page)
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止直接读写 JSON / 调网络 → 走 item_service.get()
- ✗ 禁止直接持有并修改另一个 Page → 走 EventBus
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space
- ✗ 禁止搜索逻辑在 Page 内实现 → 走 Service.search()

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QScrollArea,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QFont, QColor, QCursor

from core.pages.base_page import PageBase
from core.widgets.panel import CyberPanel
from core.widgets.line_edit import CyberLineEdit
from core.widgets.combo_box import CyberComboBox
from core.widgets.card import CyberCard
from core.tokens.manager import TokenManager
from core.services.item_service import ItemService
from core.services.localization_service import translate_location


class ItemsPage(PageBase):
    """物品查询页面。"""

    page_id = "items"
    page_title = ""
    page_icon = "nav_items"

    # ── 稀有度颜色映射（token_key → copy_token_key）──
    # 颜色值和文案均通过 self._color() / self._copy() 在运行时解析
    _RARITY_COLOR_TOKENS = {
        "Common":    ("raw.game.gold",    "items.rarity_gold"),
        "Uncommon":  ("raw.game.silver",  "items.rarity_silver"),
        "Rare":      ("raw.game.copper",  "items.rarity_copper"),
        "Legendary": ("raw.game.gold",    "items.rarity_legendary"),
        "Prime":     ("accent.purple","items.rarity_prime"),
    }

    # ── HTML 内联半透明背景色（QSS/HTML 不支持 token 解析，集中定义）──
    # 这些颜色在 __init__ 中从 Token 动态解析，此处仅作类型声明
    _BG_VAULTED: str = ""   # 入库状态：红色淡底
    _BG_AVAILABLE: str = ""  # 出库状态：绿色淡底
    _BORDER_SUBTLE: str = "" # 列表项分隔线

    def __init__(self):
        # 必须在 PageBase.__init__() 之前初始化 build_content() 所需的属性
        self._svc = ItemService()
        self._suggest_timer = None

        PageBase.__init__(self)

        # 从 Token 解析 HTML 内联颜色（QSS/HTML 不支持运行时 token 解析）
        _vaulted_c = TokenManager.instance().get_qcolor("semantic.danger")
        _avail_c = TokenManager.instance().get_qcolor("brand.green")
        _subtle_c = TokenManager.instance().get_qcolor("border.subtle")
        type(self)._BG_VAULTED = f"rgba({_vaulted_c.red()},{_vaulted_c.green()},{_vaulted_c.blue()},0.15)"
        type(self)._BG_AVAILABLE = f"rgba({_avail_c.red()},{_avail_c.green()},{_avail_c.blue()},0.12)"
        type(self)._BORDER_SUBTLE = f"rgba({_subtle_c.red()},{_subtle_c.green()},{_subtle_c.blue()},0.05)"

        self.page_title = self._copy("nav.items", "物品查询")

        # 联想防抖定时器（需在 super 后创建 QObject）
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(250)
        self._suggest_timer.timeout.connect(self._on_suggest_trigger)

    def build_content(self) -> QWidget:
        """构建物品查询页(搜索框 + 结果列表 + 详情面板)。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            self._spacing("lg", 20), self._spacing("sm", 8),
            self._spacing("lg", 20), self._spacing("lg", 20)
        )
        layout.setSpacing(self._spacing("xs", 4))

        # ── 标题 ──
        title = QLabel(self._copy("items.title", "物品检索"))
        title.setFont(QFont("Iceberg", self._font_size("lg_xl", 18)))
        self._style(
            title,
            color="accent.primary",
            padding=(f"{self._spacing('spacing.xs', 4)}px", "0"),
        )
        layout.addWidget(title)

        desc = QLabel(
            self._copy("items.desc",
                       "搜索遗物内含物品、Prime 部件、蓝图等，支持中文/英文/拼音")
        )
        self._style(
            desc,
            color="text.tertiary",
            font_size="sm",
            padding=("0", "0", "12px", "0"),
        )
        layout.addWidget(desc)

        # ── 搜索栏区域 ──
        search_card = CyberCard(title=self._copy("items.card_search", "搜索条件"))
        search_layout = search_card.content_layout()
        search_layout.setContentsMargins(
            self._spacing("md", 12), self._spacing("xs", 4),
            self._spacing("md", 12), self._spacing("xs", 4)
        )
        search_layout.setSpacing(self._spacing("sm", 8))

        # 搜索输入行
        search_row = QHBoxLayout()
        search_label = QLabel(self._copy("items.label_keyword", "关键词:"))
        self._style(
            search_label,
            color="text.secondary",
            font_size="sm_md",
        )
        search_label.setFixedWidth(self._spacing("label_w", 60))
        search_row.addWidget(search_label)

        self._search_input = CyberLineEdit(
            placeholder=self._copy("items.placeholder_search",
                                   "输入物品名称，如 Forma、Braton...")
        )
        self._search_input.setMinimumWidth(300)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self._search_input, stretch=1)

        search_layout.addLayout(search_row)

        layout.addWidget(search_card)

        # ── 结果统计栏 + 复制 toast ──
        self._stats_bar = QLabel("")
        self._style(
            self._stats_bar,
            color="text.tertiary",
            font_size="xs",
            padding=(f"{self._spacing('spacing.none', 0)}px", "0"),
        )
        # 复制成功提示(toast):默认隐藏,2 秒后自动清空
        self._copy_toast = QLabel("")
        self._copy_toast.setStyleSheet(
            f"color: {self._color('semantic.success')};"
            f"font-size: {self._font_size('xs', 11)}px;"
            f"font-weight: bold;"
            f"background: transparent;"
            f"border: none;"
        )
        self._copy_toast.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._copy_toast.hide()
        # 复制 toast 定时器(2 秒后自动清空,无副作用)
        self._copy_toast_timer = QTimer(self)
        self._copy_toast_timer.setSingleShot(True)
        self._copy_toast_timer.setInterval(2000)
        self._copy_toast_timer.timeout.connect(lambda: self._copy_toast.clear() or self._copy_toast.hide())

        # 同一行:左边统计,右边 toast
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(self._spacing("sm", 8))
        stats_row.addWidget(self._stats_bar)
        stats_row.addStretch()
        stats_row.addWidget(self._copy_toast)
        layout.addLayout(stats_row)

        # ── 搜索结果区域 ──
        result_card = CyberCard(title=self._copy("items.card_result", "搜索结果"))
        result_layout = result_card.content_layout()
        result_layout.setContentsMargins(
            self._spacing("xs", 4), self._spacing("xs", 4),
            self._spacing("xs", 4), self._spacing("xs", 4)
        )
        result_layout.setSpacing(4)

        # 结果列表（使用 QListWidget + 自定义 item）
        self._result_list = QListWidget()
        self._result_list.setFrameShape(QFrame.Shape.NoFrame)
        self._result_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._result_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._result_list.itemClicked.connect(self._on_item_clicked)
        self._result_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._result_list.setMouseTracking(True)
        self._result_list.itemEntered.connect(self._on_item_hovered)
        self._result_list.viewport().installEventFilter(self)

        list_bg = self._color("components.list_item.bg_normal")
        # 复杂 QSS(多选择器)走 raw 通道;callable 形式支持主题切换重放
        def _list_qss():
            hover_bg = self._color("components.list_item.bg_hover")
            ac = self._color("accent.primary")
            return (
                f"QListWidget {{"
                f"  background-color: transparent;"
                f"  border: none;"
                f"  outline: none;"
                f"  font-size: {self._font_size('sm_md', 13)}px;"
                f"}}"
                f"QListWidget::item {{"
                f"  color: {self._color('text.primary')};"
                f"  padding: {self._spacing('spacing.sm', 8)}px {self._spacing('spacing.md', 12)}px;"
                f"  border-bottom: 1px solid {self._BORDER_SUBTLE};"
                f"  border-radius: {self._spacing('corner.xs', 4)}px;"
                f"  border: 1px solid transparent;"  # 占位边框,选中态切换时不抖尺寸
                f"}}"
                f"QListWidget::item:selected {{"
                f"  background-color: transparent;"  # 整行变蓝底 → 改为透明
                f"  color: {ac};"
                f"  border: 1px solid {ac};"     # 蓝色边框(单/双击后视觉提示)
                f"}}"
                f"QListWidget::item:hover {{"
                f"  border: 1px solid {ac};"
                f"}}"
            )
        self._style(self._result_list, raw=_list_qss)
        self._result_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        result_layout.addWidget(self._result_list, stretch=1)
        layout.addWidget(result_card, stretch=1)

        return container

    # ════════════════════════════════════
    #  数据加载
    # ════════════════════════════════════

    def on_enter(self):
        """页面激活时检查数据库状态。"""
        self._check_db_status()

    # ════════════════════════════════════
    #  搜索 & 联想
    # ════════════════════════════════════

    def _on_search_text_changed(self, text: str):
        """输入变化 → 防抖触发联想（清空时立即清理列表）。"""
        if len(text.strip()) < 1:
            self._result_list.clear()
            self._update_stats_bar(0)
            self._hide_tooltip()
            return
        self._suggest_timer.start()

    def _on_suggest_trigger(self):
        """防抖到期 → 执行联想搜索并填充下拉建议。"""
        query = self._search_input.text().strip()
        if not query or len(query) < 1:
            return

        suggestions = self._svc.suggest(query)
        if not suggestions:
            self._result_list.clear()
            self._update_stats_bar(0)
            return

        # 用联想结果填充列表作为预览
        self._populate_results(suggestions, is_suggest=True)

    def _populate_results(self, results: list[dict], is_suggest: bool = False):
        """填充结果列表。

        Args:
            results: 搜索/联想结果
            is_suggest: 是否为联想模式（显示匹配质量）
        """
        self._result_list.clear()

        if not results:
            empty_item = QListWidgetItem(
                self._copy("items.no_results", "未找到匹配的物品")
            )
            empty_item.setData(Qt.ItemDataRole.UserRole, None)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._result_list.addItem(empty_item)
            self._update_stats_bar(0)
            return

        for item_data in results:
            zh_name = item_data.get("zh_name", "")
            en_name = item_data.get("en_name", "")
            category = item_data.get("category", "")

            # 构建显示文本：中文名优先，格式为 "中文名 (英文名)"
            display_parts = [zh_name] if zh_name else [en_name]
            if zh_name and en_name and zh_name != en_name:
                display_parts.append(f"({en_name})")
            elif not zh_name:
                display_parts = [en_name]

            suffix_parts = []
            if category:
                suffix_parts.append(category)

            if is_suggest:
                quality = item_data.get("match_quality", "")
                field = item_data.get("match_field", "")
                quality_labels = {
                    "exact": "=",
                    "prefix": "~",
                    "contains": "*",
                    "py": "拼",
                }
                q_mark = quality_labels.get(quality, "?")
                suffix_parts.append(f"[{q_mark}{field}]")

            text = " ".join(display_parts)
            if suffix_parts:
                text += f"  {' | '.join(suffix_parts)}"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, item_data)
            self._result_list.addItem(item)

        self._update_stats_bar(len(results))

    def _update_stats_bar(self, count: int):
        """更新统计栏文字。"""
        if count == 0:
            self._stats_bar.setText("")
        else:
            total_str = str(count)
            self._stats_bar.setText(
                self._copy("items.result_count", f"共 {total_str} 条结果")
            )

    # ════════════════════════════════════
    #  结果交互
    # ════════════════════════════════════

    def _on_item_clicked(self, item: QListWidgetItem):
        """单击 → 复制英文名到剪贴板 + toast 状态提示(2 秒)。

        设计意图:用户搜索结果一眼看到中英对照,但实际想用英文名(wf 市场、
        warframe.market、英文 wiki 都用英文名),单击是最快的复制动作。
        双击保留为复制中文,作为备选。
        """
        from PySide6.QtWidgets import QApplication
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        en_name = (data.get("en_name") or "").strip()
        if not en_name:
            # 没英文名就复制中文兜底(老物品/翻译缺失场景)
            en_name = (data.get("zh_name") or "").strip()
        if not en_name:
            return
        QApplication.clipboard().setText(en_name)
        # 触发 toast 提示(右侧状态条,2 秒后自动清空)
        self._show_copy_toast(en_name)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """双击 → 复制中文名到剪贴板 + toast 状态提示(2 秒)。

        保留旧行为: 双击复制中文名,作为单击(英文)的备选。
        """
        from PySide6.QtWidgets import QApplication
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        name = data.get("zh_name") or data.get("en_name", "")
        if not name:
            return
        QApplication.clipboard().setText(name)
        self._show_copy_toast(name)

    def _show_copy_toast(self, name: str):
        """显示"已复制:xxx"toast 提示,2 秒后自动清空。

        用 QTimer 单次定时器,完全无副作用(不清空 stats_bar)。
        """
        msg = self._copy("items.copy_toast", "✓ 已复制: {name}", name=name)
        self._copy_toast.setText(msg)
        self._copy_toast.show()
        # 重启定时器(连续点击时也只显示最后一条,2 秒后清空)
        self._copy_toast_timer.start()

    # ── 事件过滤（用于检测鼠标离开列表区域）──

    def eventFilter(self, obj, event):
        """拦截列表 viewport 的鼠标离开事件，延迟隐藏 tooltip。"""
        if obj is self._result_list.viewport():
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.Type.Leave:
                self._on_item_left()
        return super().eventFilter(obj, event)

    # ── 悬停 Tooltip（自定义 Widget，不移开不消失）──

    def _on_item_hovered(self, item: QListWidgetItem):
        """鼠标悬停 → 显示自定义 Widget 悬浮窗。"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            self._hide_tooltip()
            return

        html = self._build_hover_tooltip(data)
        if not html:
            self._hide_tooltip()
            return

        self._show_tooltip_widget(html, item)

    def _on_item_left(self):
        """鼠标离开列表项 → 延迟隐藏（给移入悬浮窗的时间）。"""
        if hasattr(self, '_tooltip_hide_timer'):
            self._tooltip_hide_timer.start(150)

    def _create_tooltip_widget(self) -> QFrame:
        """创建可滚动的悬浮窗容器（整体背景 + 阴影 + 圆角）。"""
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        container = QFrame(self.window())
        container.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(False)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(label)
        layout.addWidget(scroll)

        # 整体背景色（与主题一致）
        self._style(
            container,
            background="components.card.bg",
            raw=lambda: (
                f"border: 1px solid {self._color('border.subtle')};"
                f"border-radius: {self._spacing('corner.sm', 6)}px;"
            ),
        )
        self._style(
            label,
            transparent=True,
            raw=lambda: (
                f"padding: {self._spacing('spacing.sm', 8)}px "
                f"{self._spacing('spacing.lg', 16)}px;"
            ),
        )

        # 阴影效果
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        # 保存内部控件引用，便于外部更新内容
        container._label = label
        container._scroll = scroll

        # 鼠标进入悬浮窗时取消隐藏定时器
        container.enterEvent = lambda e: (
            getattr(self, '_tooltip_hide_timer', type('', (), {'stop': lambda *a: None})()).stop()
            if hasattr(self, '_tooltip_hide_timer') else None,
            None
        )[-1] or None

        # 鼠标离开悬浮窗 → 立即隐藏
        container.leaveEvent = lambda e: self._hide_tooltip()

        return container

    def _show_tooltip_widget(self, html: str, item: QListWidgetItem):
        """定位并显示悬浮窗，自动限制最大尺寸并在超出时启用滚动。"""
        from PySide6.QtWidgets import QApplication

        # 多显示器环境下，优先以主窗口所在屏幕为基准；
        # QCursor.pos() + screenAt 在跨屏/DPI 缩放场景下容易误判到主屏。
        host = self.window()
        screen = host.screen() if host else None
        if not screen:
            screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        scr_geo = screen.availableGeometry() if screen else None

        if not hasattr(self, '_tip_widget') or self._tip_widget is None:
            self._tip_widget = self._create_tooltip_widget()
        if not hasattr(self, '_tooltip_hide_timer'):
            self._tooltip_hide_timer = QTimer(self)
            self._tooltip_hide_timer.setSingleShot(True)
            self._tooltip_hide_timer.timeout.connect(self._hide_tooltip)

        tip = self._tip_widget
        label = tip._label
        label.setText(html)

        # 限制悬浮窗最大尺寸，避免过长内容撑破屏幕
        max_width = 420
        max_height = 480
        if scr_geo:
            max_height = int(scr_geo.height() * 0.7)

        # 先让 QLabel 按自然宽度计算，再用 heightForWidth 估算固定宽度下的高度
        label.setMinimumWidth(220)
        label.adjustSize()
        content_width = max_width - 24  # 预留边距与滚动条空间
        content_h = label.heightForWidth(content_width)
        if content_h <= 0:
            content_h = label.sizeHint().height()

        tip_w = max_width
        tip_h = min(content_h + 16, max_height)
        tip.setFixedSize(tip_w, tip_h)

        # 定位：在鼠标右下方，偏移 16px
        pos = QCursor.pos()
        pos += QPoint(16, 16)

        # ── 防溢出：检查屏幕边界 ──
        if scr_geo:
            # 右侧溢出 → 贴右边
            if pos.x() + tip_w > scr_geo.right():
                pos.setX(scr_geo.right() - tip_w - 4)

            # 下侧溢出 → 移到鼠标上方
            if pos.y() + tip_h > scr_geo.bottom():
                pos.setY(max(scr_geo.top(), pos.y() - tip_h - 32))

            # 左侧溢出 → 贴左边
            if pos.x() < scr_geo.left():
                pos.setX(scr_geo.left() + 4)

            # 上侧溢出 → 贴顶部（留出一点边距）
            if pos.y() < scr_geo.top():
                pos.setY(scr_geo.top() + 4)

        tip.move(pos)
        tip.show()
        tip.raise_()

    def _hide_tooltip(self):
        """隐藏悬浮窗。"""
        if hasattr(self, '_tip_widget') and self._tip_widget is not None:
            self._tip_widget.hide()

    def _build_hover_tooltip(self, item_data: dict) -> str:
        """构建悬停 tooltip 的 HTML 内容。

        逻辑：
          - 非遗物物品 → 显示掉落来源列表
          - 遗物       → 显示遗物内含物品（含稀有度和概率）
        """
        en_name = item_data.get("en_name", "")
        zh_name = item_data.get("zh_name", "")
        category = (item_data.get("category", "") or "").strip().lower()

        # 赛博朋克风格颜色（从主题代理取，fallback 用硬编码）
        bg = self._color("components.card.bg")
        border_color = self._color("border.subtle")
        accent = self._color("accent.primary")
        text_main = self._color("text.primary")
        text_dim = self._color("text.disabled")
        text_sec = self._color("text.secondary")
        # YAML 主题金银铜色
        c_gold = self._color("raw.game.gold")    # 概率最低 → 金
        c_silver = self._color("raw.game.silver") # 中等概率 → 银
        c_copper = self._color("raw.game.copper") # 最高概率 → 铜
        cyan = self._color("accent.secondary")
        red = self._color("semantic.danger")
        green = self._color("semantic.success")
        purple = self._color("accent.tertiary")
        orange = self._color("semantic.warning")

        display_name = zh_name if zh_name else en_name
        if zh_name and en_name and zh_name != en_name:
            display_name = f"{zh_name} / {en_name}"

        # ── 按品级/稀有度决定名称颜色 ──
        rarity = (item_data.get("rarity") or "").strip().lower()
        _RARITY_COLOR_MAP = {
            "legendary": self._color("raw.game.gold"),
            "rare":      self._color("raw.game.gold"),
            "uncommon":  self._color("raw.game.silver"),
            "common":    self._color("raw.game.copper"),
        }
        name_color = _RARITY_COLOR_MAP.get(rarity, accent)

        parts = []
        # 内层容器（无背景，外层 QLabel 已有整体背景）
        parts.append(
            f"<div style='font-family:Microsoft YaHei, sans-serif;'>"
        )

        # ── 标题行（品级着色）──
        parts.append(
            f"<div style='font-size:13px; font-weight:bold; color:{name_color}; "
            f"margin-bottom:6px; padding-bottom:4px; "
            f"border-bottom:1px solid {border_color};'>"
            f"{self._esc(display_name)}"
            f"</div>"
        )

        is_relic = category in ("relics", "relic")

        if is_relic:
            # ═══ 遗物：状态 + 掉落途径 + 内含物品 ═══
            relic_info = self._svc.get_relic_contents(en_name)
            contents = relic_info.get("contents", [])
            is_vaulted = relic_info.get("vaulted", False)

            # ── 入库/出库 状态（入库=红，出库=绿）──
            if is_vaulted:
                # 入库：红色（无法通过任务掉落获取）
                parts.append(
                    f"<div style='margin-top:4px;padding:3px 8px;"
                    f"background:{self._BG_VAULTED};border-radius:4px;"
                    f"border-left:3px solid {red};'>"
                    f"<span style='color:{red};font-size:11px;font-weight:bold;'>"
                    f"| {self._copy('items.detail_vaulted', '入库 (Vaulted)')}</span>"
                    f"</div>"
                )
            else:
                # 出库：绿色（当前可掉落）
                parts.append(
                    f"<div style='margin-top:4px;padding:3px 8px;"
                    f"background:{self._BG_AVAILABLE};border-radius:4px;"
                    f"border-left:3px solid {green};'>"
                    f"<span style='color:{green};font-size:11px;font-weight:bold;'>"
                    f"| {self._copy('items.detail_available', '出库 (Available)')}</span>"
                    f"</div>"
                )

            # ── 掉落途径（悬浮窗已支持滚动，显示全部）──
            drop_locs, drop_total = self._svc.get_relic_drop_locations(en_name, max_results=None)
            if drop_locs:
                tip = f"掉落途径 (共{drop_total})"
                parts.append(
                    f"<div style='margin-top:6px;margin-bottom:1px;'>"
                    f"<span style='color:{cyan};font-size:11px;font-weight:bold;'>| {tip}</span>"
                    f"</div>"
                )
                parts.append(
                    f"<div style='padding-right:4px;'>"
                )
                for loc in drop_locs:
                    planet = loc.get('planet', '')
                    node = loc.get('node_name', '')
                    gm = loc.get('game_mode', '')
                    rot = loc.get('rotation', '')
                    chance = loc.get('chance', 0)

                    # 构建英文位置文本，统一翻译
                    loc_text = planet
                    if node:
                        loc_text += f" - {node}"
                    if gm:
                        loc_text += f" ({gm})"
                    loc_text = translate_location(loc_text)

                    extra_parts = []
                    if rot:
                        extra_parts.append(self._copy('items.detail_rotation_label', '轮次{rot}', rot=rot))
                    if chance > 0 and chance < 100:
                        extra_parts.append(f"{chance:g}%")
                    extra_str = ""
                    if extra_parts:
                        extra_str = f" <span style='color:{text_dim};font-size:10px;'>({' | '.join(extra_parts)})</span>"

                    parts.append(
                        f"<div style='padding:1px 0 1px 12px;font-size:11px;"
                        f"color:{text_sec};'>"
                        f"&bull; {self._esc(loc_text)}{extra_str}"
                        f"</div>"
                    )
                parts.append("</div>")
            else:
                parts.append(
                    f"<div style='margin-top:4px;color:{text_dim};font-size:11px;'>"
                    f"{self._copy('items.detail_no_drop_data', '暂无掉落途径数据')}</div>"
                )

            # ── 内含物品（按概率分金银铜：最低=金，中=银，最高=铜）──
            if contents:
                parts.append(
                    f"<div style='margin-top:6px;margin-bottom:1px;'>"
                    f"<span style='color:{c_gold};font-size:11px;font-weight:bold;'>"
                    f"| {self._copy('items.detail_contents', '内含物品 ({n})', n=len(contents))}</span>"
                    f"</div>"
                )

                _TIER_NAMES = {
                    c_gold: self._copy("items.detail_tier_gold", "金"),
                    c_silver: self._copy("items.detail_tier_silver", "银"),
                    c_copper: self._copy("items.detail_tier_copper", "铜"),
                }

                for c in contents:
                    item_cn = c.get("zh_name", "") or c.get("item_name", "?")
                    chance = c.get("chance", 0)

                    # 按概率分档：越低越稀有 → 金
                    if chance <= 6:
                        tier_color = c_gold
                    elif chance <= 16:
                        tier_color = c_silver
                    else:
                        tier_color = c_copper

                    tier_name = _TIER_NAMES.get(tier_color, "?")
                    chance_str = ""
                    if chance > 0 and chance < 100:
                        chance_str = f" <span style='color:{text_dim};'>({chance:g}%)</span>"

                    parts.append(
                        f"<div style='padding:2px 0; font-size:12px;'>"
                        f"<span style='display:inline-block;width:8px;height:8px;"
                        f"background:{tier_color};border-radius:50%;"
                        f"margin-right:6px;vertical-align:middle;'></span>"
                        f"<span style='color:{tier_color};'>{self._esc(item_cn)}</span>"
                        f" <span style='color:{tier_color};font-size:11px;'>({tier_name})</span>"
                        f"{chance_str}"
                        f"</div>"
                    )
        else:
            # ═══ 普通物品：显示掉落来源 ═══
            sources = self._svc.get_drop_sources(
                en_name,
                unique_name=item_data.get("unique_name", ""),
                max_results=None,
            )

            if sources:
                # 按 source_type 分组 + 翻译中文标签
                type_labels = {
                    "relics": (self._copy("items.source_relics", "遗物奖励"), c_gold),
                    "missionRewards": (self._copy("items.source_missions", "任务奖励"), cyan),
                    "bountyRewards": (self._copy("items.source_bounties", "赏金奖励"), orange),
                    "sortieRewards": (self._copy("items.source_sorties", "突击奖励"), red),
                    "syndicates": (self._copy("items.source_syndicates", "集团兑换"), c_gold),
                    "itemDrops": (self._copy("items.source_item_drops", "获取途径"), green),
                    "modLocations": (self._copy("items.source_mods", "Mod 掉落"), purple),
                    "blueprintLocations": (self._copy("items.source_blueprints", "蓝图掉落"), cyan),
                    "transientRewards": (self._copy("items.source_transient", "临场奖励"), orange),
                    "keyRewards": (self._copy("items.source_keys", "钥匙奖励"), c_silver),
                }

                by_type: dict[str, list] = {}
                for s in sources:
                    st = s.get("source_type", "")
                    if st not in by_type:
                        by_type[st] = []
                    by_type[st].append(s)

                for st, items in by_type.items():
                    label, tcolor = type_labels.get(st, (st, text_dim))
                    parts.append(
                        f"<div style='margin-top:5px;margin-bottom:1px;'>"
                        f"<span style='color:{tcolor};font-size:11px;font-weight:bold;'>"
                        f"| {label} ({len(items)})</span>"
                        f"</div>"
                    )

                    for src in items:
                        loc = translate_location(src.get("location", "?"))
                        rarity = src.get("rarity", "")
                        chance = src.get("chance", 0)
                        rotation = src.get("rotation", "")

                        extra_parts = []
                        if rarity:
                            extra_parts.append(rarity)
                        if chance > 0 and chance < 100:
                            extra_parts.append(f"{chance:g}%")
                        elif chance >= 100:
                            extra_parts.append(self._copy("items.drop_guaranteed", "必定"))
                        if rotation:
                            extra_parts.append(self._copy('items.detail_rotation_label', '轮次{rot}', rot=rotation))

                        extra = f" <span style='color:{text_dim};font-size:10px;'>"
                        extra += " | ".join(extra_parts) + "</span>" if extra_parts else ""

                        parts.append(
                            f"<div style='padding:1px 0 1px 12px;font-size:11px;"
                            f"color:{text_sec};'>"
                            f"&bull; {self._esc(loc)}{extra}"
                            f"</div>"
                        )
            else:
                parts.append(
                    f"<div style='color:{text_dim};font-size:11px;margin-top:4px;'>"
                    f"{self._copy('items.detail_no_source_data', '暂无掉落来源数据')}</div>"
                )

        parts.append("</div>")
        return "".join(parts)

    @staticmethod
    def _esc(text: str) -> str:
        """HTML 转义。"""
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;"))

    # ════════════════════════════════════
    #  数据库状态检查
    # ════════════════════════════════════

    def _check_db_status(self):
        """检查数据库是否可用，必要时显示提示。"""
        status = self._svc.check_db_status()
        if status["status"] in ("missing", "empty"):
            hint = self._copy(
                "items.db_missing_hint",
                "数据库尚未初始化，请先在「数据总览」页面执行「更新基础数据」"
            )
            self._result_list.clear()
            empty_item = QListWidgetItem(hint)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._result_list.addItem(empty_item)
