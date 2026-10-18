"""
[L2] core.pages.prices_page — 价格查询页面 (v2: 状态机驱动)

═══════════════════════════════════════════════════════════════════════
归属层:    [L2] (core/pages/)
依赖:      core.state.price_query_state  (单例,订阅信号)
           core.services.wm_items_repository / search_coordinator / price_fetcher
           core.widgets.* + 现有 UI 元素
职责:      纯 UI 组装 + 状态订阅
═══════════════════════════════════════════════════════════════════════

v2 重构(2026-08-07):
  - 改用 PriceQueryState 单例 + Signal 驱动 UI
  - 顶部状态条: 反映顶层状态(LOADING/READY/DEGRADED/FAILED)
  - 搜索反馈: spinner / 空结果 / 错误
  - 查询反馈: 进度 + 重试按钮
  - 自动降级: 网络问题走 DB 搜索
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations


from PySide6.QtCore import Qt, QTimer, Signal, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QTableWidget, QTableWidgetItem, QFrame, QToolButton,
    QProgressBar, QAbstractItemView, QHeaderView,
)

from core.pages.base_page import PageBase
from core.state.price_query_state import PriceQueryState, TopStatus
from core.services.wm_items_repository import WmItemsRepository
from core.services.search_coordinator import SearchCoordinator
from core.services.price_fetcher import PriceFetcher
from core.logging_utils import log as _dbg


# ── DB 路径(给 component 翻译用;打包/开发环境自适应,见 core.paths) ──
# 注意: 实际数据在 warframe.db(139MB),warframe_items.db 是 0 字节的旧文件
from core.paths import ensure_user_file
from core.fonts import FONT_DISPLAY
DB_PATH = ensure_user_file("warframe.db")

# ── 搜索 debounce ──
SEARCH_DEBOUNCE_MS = 300

# ── 表格列定义 ──
COLUMNS = [
    ("seller", "prices.col_seller", "卖家"),
    ("status", "prices.col_status", "状态"),
    ("price", "prices.col_price", "价格"),
    ("quantity", "prices.col_quantity", "数量"),
    ("rank", "prices.col_rank", "等级"),
    ("reputation", "prices.col_reputation", "声望"),
]

# ── 状态颜色 ──
_STATUS_COLORS = {
    "ingame": "alias.semantic.success",
    "online": "alias.text.primary",
    "offline": "alias.text.tertiary",
}


# ════════════════════════════════════════════════════════════════════════
#  顶部状态条
# ════════════════════════════════════════════════════════════════════════

class _StatusBar(QFrame):
    """顶部状态条: 反映 PriceQueryState 顶层状态。

    视觉:
      IDLE     → "就绪"           (灰)
      LOADING  → "加载中 50% ..."  (蓝,带进度条)
      READY    → "✓ 3065 个物品"   (绿)
      DEGRADED → "⚠ 网络问题"      (黄,带重试按钮)
      FAILED   → "✗ 加载失败"      (红,带重试按钮)
    """

    retry_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("prices_status_bar")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)

        # 图标 + 文字
        self._icon = QLabel("●")
        self._icon.setFixedWidth(20)
        layout.addWidget(self._icon)

        self._text = QLabel("")
        layout.addWidget(self._text, stretch=1)

        # 进度条(LOADING 时显示)
        self._progress = QProgressBar()
        self._progress.setMaximum(100)
        self._progress.setFixedWidth(120)
        self._progress.setTextVisible(False)
        self._progress.hide()
        layout.addWidget(self._progress)

        # 重试按钮(DEGRADED/FAILED 时显示)
        self._retry_btn = QToolButton()
        self._retry_btn.setText("重试")
        self._retry_btn.setFixedHeight(24)
        self._retry_btn.clicked.connect(self.retry_clicked)
        self._retry_btn.hide()
        layout.addWidget(self._retry_btn)

    def update_status(self, status: TopStatus, message: str = "") -> None:
        """根据顶层状态更新视觉。"""
        from core.tokens.manager import TokenManager
        tm = TokenManager.instance()
        if status == TopStatus.IDLE:
            self._icon.setText("○")
            self._text.setText(message or "就绪")
            self._apply_color("text.tertiary")
            self._progress.hide()
            self._retry_btn.hide()
        elif status == TopStatus.LOADING:
            self._icon.setText("⟳")
            self._text.setText(message or "加载中...")
            self._apply_color("accent.primary")
            self._progress.show()
            self._retry_btn.hide()
        elif status == TopStatus.READY:
            self._icon.setText("✓")
            self._text.setText(message or "就绪")
            self._apply_color("alias.semantic.success")
            self._progress.hide()
            self._retry_btn.hide()
        elif status == TopStatus.DEGRADED:
            self._icon.setText("⚠")
            self._text.setText(message or "网络问题 · 仅中文搜索")
            self._apply_color("alias.semantic.warning")
            self._progress.hide()
            self._retry_btn.show()
        elif status == TopStatus.FAILED:
            self._icon.setText("✗")
            self._text.setText(message or "加载失败")
            self._apply_color("alias.semantic.error")
            self._progress.hide()
            self._retry_btn.show()

    def update_progress(self, percent: int) -> None:
        self._progress.setValue(percent)

    def _apply_color(self, token_key: str) -> None:
        from core.tokens.manager import TokenManager
        color = TokenManager.instance().get(token_key)
        self._icon.setStyleSheet(f"color: {color}; font-weight: bold;")
        self._text.setStyleSheet(f"color: {color};")


# ════════════════════════════════════════════════════════════════════════
#  PricesPage — 价格查询主页面
# ════════════════════════════════════════════════════════════════════════

class PricesPage(PageBase):
    """价格数据查询页面(状态机驱动 v2)。

    数据流:
      State 单例 → Signal → Page._on_* 槽 → UI 更新

    生命周期:
      on_enter:  订阅 State 信号 + 启动仓库预热
      on_leave:  解绑信号(避免下次重复连接)
    """

    page_id = "prices"
    page_title = ""
    page_icon = "nav_prices"

    def __init__(self) -> None:
        # ── 引用(必须在 super().__init__() 前声明) ──
        self._suppress_search: bool = False
        self._search_timer: QTimer | None = None
        self._status_bar: _StatusBar | None = None
        self._search_input: QLineEdit | None = None
        self._dropdown: QListWidget | None = None
        self._summary_label: QLabel | None = None
        self._table: QTableWidget | None = None
        self._status_label: QLabel | None = None
        self._current_item_name: str = ""
        self._current_item_slug: str = ""

        # 状态机订阅是否已连接(防重复)
        self._state_bound: bool = False

        # 加载进度冷却 tick
        self._cooldown_timer: QTimer | None = None

        super().__init__()
        self.page_title = self._copy("nav.prices", "价格数据")

    # ══════════════════════════════════════════════════════
    #  生命周期
    # ══════════════════════════════════════════════════════

    def build_content(self) -> QWidget:
        """构建价格查询页(顶部状态条 + 搜索区 + 摘要 + 表格)。"""
        _cp = self._copy
        _co = self._color
        _fs = self._font_size

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(
            self._spacing("lg", 20), self._spacing("sm", 8),
            self._spacing("lg", 20), self._spacing("lg", 20)
        )
        root.setSpacing(self._spacing("sm", 8))

        # ── 标题 ──
        title = QLabel(_cp("prices.title", "市场价格监控"))
        title.setFont(QFont(FONT_DISPLAY, _fs("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        root.addWidget(title)

        # ── 顶部状态条 ──
        self._status_bar = _StatusBar()
        self._status_bar.retry_clicked.connect(self._on_retry_clicked)
        root.addWidget(self._status_bar)

        # ── 搜索框 ──
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            _cp("prices.ph_search", "输入物品名称搜索 (中文/英文/拼音)...")
        )
        self._search_input.setFixedHeight(36)
        self._search_input.setClearButtonEnabled(True)
        self._style(self._search_input, color="text.primary")
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._do_search)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        root.addWidget(self._search_input)

        # ── 摘要 ──
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            f"color: {_co('alias.text.tertiary')}; "
            f"font-size: {_fs('xs', 11)}px; padding: 4px 0;"
        )
        self._summary_label.hide()
        root.addWidget(self._summary_label)

        # ── 结果表格 ──
        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels([c[2] for c in COLUMNS])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.cellClicked.connect(self._on_cell_clicked)
        root.addWidget(self._table, stretch=1)

        # ── 状态行 ──
        self._status_label = QLabel("")
        self._style(self._status_label, color="text.tertiary", font_size="sm")
        root.addWidget(self._status_label)

        # ── 下拉建议(浮层) ──
        self._dropdown = QListWidget()
        self._dropdown.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self._dropdown.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._dropdown.setMaximumHeight(240)
        self._dropdown.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._dropdown.itemClicked.connect(self._on_dropdown_item_clicked)
        self._dropdown.hide()

        # 启动后 15s 后台预热物品列表(不等用户进页面):
        # 首启无缓存时网络拉取约 30-60s,提前预热可消除「进页面后不可搜」窗口;
        # warm_cache_async 幂等(有缓存且新鲜/加载中均跳过),与 on_enter 不冲突
        QTimer.singleShot(
            15_000, lambda: WmItemsRepository.instance().warm_cache_async()
        )
        return container

    def on_enter(self) -> None:
        """进入页面:订阅 State + 启动预热。"""
        if not self._state_bound:
            self._bind_state_signals()
        self._update_status_bar_from_state()
        # 启动后台预热(仅当缓存空 + 不在冷却)
        WmItemsRepository.instance().warm_cache_async()

        # 启动冷却倒计时显示 tick
        if self._cooldown_timer is None:
            self._cooldown_timer = QTimer()
            self._cooldown_timer.setInterval(1000)
            self._cooldown_timer.timeout.connect(self._update_status_bar_from_state)
        self._cooldown_timer.start()

    def on_leave(self) -> None:
        """离开页面:停止冷却 tick + 隐藏下拉。"""
        if self._cooldown_timer is not None:
            self._cooldown_timer.stop()
        if self._dropdown is not None:
            self._dropdown.hide()

    def on_close(self) -> None:
        """关闭页面:解绑 State 信号(防止泄漏)。"""
        self._unbind_state_signals()

    # ══════════════════════════════════════════════════════
    #  State 信号订阅
    # ══════════════════════════════════════════════════════

    def _bind_state_signals(self) -> None:
        state = PriceQueryState.instance()
        state.top_status_changed.connect(self._on_top_status_changed)
        state.load_progress.connect(self._on_load_progress)
        state.error_occurred.connect(self._on_error_occurred)
        state.search_started.connect(self._on_search_started)
        state.search_completed.connect(self._on_search_completed)
        state.search_failed.connect(self._on_search_failed)
        state.search_empty.connect(self._on_search_empty)
        state.query_started.connect(self._on_query_started)
        state.query_completed.connect(self._on_query_completed)
        state.query_failed.connect(self._on_query_failed)
        self._state_bound = True

    def _unbind_state_signals(self) -> None:
        if not self._state_bound:
            return
        try:
            state = PriceQueryState.instance()
            state.top_status_changed.disconnect(self._on_top_status_changed)
            state.load_progress.disconnect(self._on_load_progress)
            state.error_occurred.disconnect(self._on_error_occurred)
            state.search_started.disconnect(self._on_search_started)
            state.search_completed.disconnect(self._on_search_completed)
            state.search_failed.disconnect(self._on_search_failed)
            state.search_empty.disconnect(self._on_search_empty)
            state.query_started.disconnect(self._on_query_started)
            state.query_completed.disconnect(self._on_query_completed)
            state.query_failed.disconnect(self._on_query_failed)
        except (RuntimeError, TypeError):
            pass
        self._state_bound = False

    # ── 顶层状态变化 ──

    def _on_top_status_changed(self, status_value: str) -> None:
        _dbg("page", f"_on_top_status_changed: {status_value}")
        self._update_status_bar_from_state()

    def _on_load_progress(self, percent: int, message: str) -> None:
        if self._status_bar is not None:
            self._status_bar.update_progress(percent)
            # 进度期间更新文字
            top = PriceQueryState.instance().top_status
            if top == TopStatus.LOADING:
                self._status_bar.update_status(top, f"{message} {percent}%")

    def _on_error_occurred(self, level: str, message: str) -> None:
        # 显示 toast
        _dbg("page", f"_on_error_occurred: [{level}] {message}")
        if level == "error":
            self._show_status_label(f"⚠ {message}", error=True)
        elif level == "warn":
            self._show_status_label(f"⚠ {message}", warn=True)

    def _update_status_bar_from_state(self) -> None:
        """根据 State 当前值更新状态条。"""
        if self._status_bar is None:
            return
        state = PriceQueryState.instance()
        top = state.top_status
        if top == TopStatus.READY:
            count = len(state.get_items())
            # 根据数据来源显示不同文案,让用户知道这是本地还是网络的数据
            source = state.get_items_source()
            age_str = state.format_cache_age()
            if source == "disk" and age_str:
                # 本地缓存(包含启动时磁盘加载 + 后续本地未变)
                msg = self._copy(
                    "prices.status_items_ready_disk",
                    "就绪 · {count} 个物品 · 本地缓存 {age}",
                ).format(count=count, age=age_str)
            else:
                # 网络刷新的(本次进程拉过)
                msg = self._copy(
                    "prices.status_items_ready",
                    "就绪 · {count} 个物品",
                ).format(count=count)
            self._status_bar.update_status(top, msg)
        elif top == TopStatus.LOADING:
            self._status_bar.update_status(top, "正在加载物品列表...")
        elif top == TopStatus.DEGRADED:
            err = state.get_failure_message()
            msg = self._copy("prices.status_items_degraded", "网络问题 · 仅中文搜索")
            if err:
                msg = f"{msg} ({err})"
            self._status_bar.update_status(top, msg)
        elif top == TopStatus.FAILED:
            err = state.get_failure_message()
            self._status_bar.update_status(top, err or "加载失败")
        else:  # IDLE
            # 如果在冷却,显示倒计时
            remaining = state.failure_cooldown_remaining()
            if remaining > 0:
                tpl = self._copy("prices.cooldown_hint", "失败冷却中 · 还剩 {seconds}s")
                self._status_bar.update_status(top, tpl.format(seconds=int(remaining)))
            else:
                self._status_bar.update_status(top, "")

    # ── 搜索相关 ──

    def _on_search_text_changed(self, text: str) -> None:
        if self._suppress_search:
            return
        self._search_timer.start()

    def _do_search(self) -> None:
        """debounce 触发:调 SearchCoordinator。"""
        if self._search_input is None:
            return
        kw = self._search_input.text().strip()
        if not kw:
            self._hide_dropdown()
            return
        # 检查顶层状态
        state = PriceQueryState.instance()
        top = state.top_status
        # LOADING 不拦截:Coordinator 内部会等 1s 重试,超时自动降级 DB 搜索,
        # 保证首启列表加载窗口期(网络慢时可达 1 分钟)用户仍可搜索
        if top is TopStatus.LOADING or top.is_search_available:
            SearchCoordinator.instance().search_async(kw)
            return
        # 仅 IDLE / FAILED(网络 + DB 都不通)才拦截
        self._show_status_label("列表不可用,无法搜索", warn=True)

    def _on_search_started(self) -> None:
        _dbg("page", "_on_search_started: 显示搜索 spinner")
        # 在下拉里显示"搜索中..."
        if self._dropdown is not None:
            self._dropdown.clear()
            item = QListWidgetItem(self._copy("prices.status_searching", "搜索中..."))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._dropdown.addItem(item)
            self._show_dropdown()

    def _on_search_completed(self, results: list) -> None:
        _dbg("page", f"_on_search_completed: {len(results)} 条")
        if self._dropdown is None:
            return
        self._dropdown.clear()
        for r in results:
            item = QListWidgetItem(self._format_item_display(r))
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._dropdown.addItem(item)
        if self._dropdown.count() > 0:
            self._show_dropdown()
        else:
            self._hide_dropdown()

    @staticmethod
    def _format_item_display(item: dict) -> str:
        """下拉项显示文本: 英文(中文),降级时末尾追加 ⚠降级。

        Args:
            item: 搜索结果 dict,含 name / zh_name / degraded 字段

        Returns:
            "Rhino Prime Set (战甲犀牛 Prime 套装)"   — 有中文
            "Forma"                                    — 无中文 / zh==en
            "战甲犀牛 Prime 套装"                       — name 空(只显示中文)
            "Rhino Prime Set (战甲犀牛 Prime 套装)  ⚠降级"  — 降级
            ""                                         — 都空
        """
        zh = (item.get("zh_name", "") or "").strip()
        name = (item.get("name", "") or "").strip()
        if name and zh and zh != name:
            display = f"{name} ({zh})"
        elif name:
            display = name
        elif zh:
            display = zh
        else:
            display = ""
        if item.get("degraded", False) and display:
            display = f"{display}  ⚠降级"
        return display

    def _on_search_failed(self, error: str) -> None:
        _dbg("page", f"_on_search_failed: {error}")
        if self._dropdown is not None:
            self._dropdown.clear()
            item = QListWidgetItem(f"搜索失败: {error}")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._dropdown.addItem(item)
            self._show_dropdown()

    def _on_search_empty(self, keyword: str) -> None:
        _dbg("page", f"_on_search_empty: {keyword!r}")
        if self._dropdown is not None:
            self._dropdown.clear()
            tpl = self._copy("prices.status_search_empty", "未匹配到 '{keyword}'")
            item = QListWidgetItem(tpl.format(keyword=keyword))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._dropdown.addItem(item)
            self._show_dropdown()

    # ── 查询相关 ──

    def _on_query_started(self, slug: str) -> None:
        _dbg("page", f"_on_query_started: {slug}")
        self._table.setRowCount(0)
        self._summary_label.hide()
        if self._current_item_name:
            tpl = self._copy("prices.status_querying_slug", "正在查询 {name}...")
            self._show_status_label(tpl.format(name=self._current_item_name))
        else:
            self._show_status_label(self._copy("prices.status_querying", "正在查询..."))

    def _on_query_completed(self, result: dict) -> None:
        _dbg("page", f"_on_query_completed: {result.get('slug')}")
        self._populate_table(result)
        self._populate_summary(result)

    def _on_query_failed(self, slug: str, error: str) -> None:
        _dbg("page", f"_on_query_failed: {slug} - {error}")
        tpl = self._copy("prices.status_query_failed", "查询失败: {error}")
        self._show_status_label(tpl.format(error=error), error=True)

    # ── 内部辅助 ──

    def _populate_table(self, result: dict) -> None:
        orders = result.get("sell_orders", [])
        self._table.setRowCount(len(orders))
        for row, o in enumerate(orders):
            # seller
            self._make_cell(row, 0, o.get("user_name", ""))
            # status
            status = o.get("user_status", "offline")
            self._make_cell(row, 1, self._translate_status(status), status_key=status)
            # price
            self._make_cell(row, 2, f"{o.get('platinum', 0)}p", color_key="accent.primary", bold=True)
            # quantity
            self._make_cell(row, 3, str(o.get("quantity", 1)))
            # rank
            self._make_cell(row, 4, str(o.get("rank", 0)))
            # reputation
            self._make_cell(row, 5, str(o.get("user_reputation", 0)))

    def _populate_summary(self, result: dict) -> None:
        count = result.get("online_count", 0)
        total = result.get("total_count", 0)
        min_p = result.get("min_platinum", 0)
        max_p = result.get("max_platinum", 0)
        avg = result.get("avg_platinum", 0)
        # 中位价 = 按数量加权均价(更准确反映市场)
        median = result.get("weighted_avg", avg)
        tpl = self._copy(
            "prices.summary_format",
            "共 {count} 个卖家  |  最低 {min_p}p  |  均价 {avg_p:.1f}p  |  最高 {max_p}p",
        )
        # 模板里可能含 {median_p},用 try/except 兼容两种模板
        try:
            text = tpl.format(count=total, min_p=min_p, avg_p=avg, max_p=max_p, median_p=median)
        except KeyError:
            text = tpl.format(count=total, min_p=min_p, avg_p=avg, max_p=max_p)
        self._summary_label.setText(text)
        self._summary_label.show()
        tpl2 = self._copy("prices.status_found", "共找到 {count} 个卖家")
        self._show_status_label(tpl2.format(count=total))

    def _make_cell(self, row: int, col: int, text: str, *, color_key: str = "", bold: bool = False, status_key: str = "") -> None:
        item = QTableWidgetItem(text)
        if color_key:
            color = self._color(color_key)
            item.setForeground(self._qcolor(color))
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        if status_key and status_key in _STATUS_COLORS:
            color = self._color(_STATUS_COLORS[status_key])
            item.setForeground(self._qcolor(color))
        self._table.setItem(row, col, item)

    def _qcolor(self, hex_str: str):
        from PySide6.QtGui import QColor
        return QColor(hex_str)

    def _translate_status(self, status: str) -> str:
        mapping = {
            "ingame": ("prices.status_ingame", "游戏中"),
            "online": ("prices.status_online", "在线"),
            "offline": ("prices.status_offline", "离线"),
            "away": ("prices.status_away", "离开"),
        }
        key, default = mapping.get(status, (None, status))
        return self._copy(key, default) if key else status

    def _show_status_label(self, text: str, *, error: bool = False, warn: bool = False) -> None:
        if self._status_label is None:
            return
        self._status_label.setText(text)
        if error:
            self._status_label.setStyleSheet(f"color: {self._color('alias.semantic.danger')};")
        elif warn:
            self._status_label.setStyleSheet(f"color: {self._color('alias.semantic.warning')};")
        else:
            self._status_label.setStyleSheet(f"color: {self._color('text.tertiary')};")

    def _show_dropdown(self) -> None:
        if self._dropdown is None or self._search_input is None:
            return
        if self._dropdown.count() == 0:
            self._hide_dropdown()
            return
        # 定位到搜索框下方
        pos = self._search_input.mapToGlobal(QPoint(0, self._search_input.height() + 2))
        self._dropdown.move(pos)
        self._dropdown.resize(self._search_input.width(), 240)
        self._dropdown.show()

    def _hide_dropdown(self) -> None:
        if self._dropdown is not None:
            self._dropdown.hide()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        # 点击 seller 列(0)→ 复制密语
        if col != 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        username = item.text()
        if not username or username == "Unknown":
            return
        # 从当前行取价格(col 2),剥掉末尾 "p"(如 "15p" → "15")
        price_item = self._table.item(row, 2)
        if price_item is not None:
            # 先 strip 去掉首尾空格,再 rstrip("p"),再 strip 一次防御
            # 例: "  7p  " → "7p" → "7" → "7"
            price_text = price_item.text().strip().rstrip("p").strip()
            price_str = price_text or "0"
        else:
            price_str = "0"
        # 模板: /w 用户 Hi! I want to buy: "物品" for 价格 platinum. (warframe.market)
        whisper = (
            f'/w {username} Hi! I want to buy: "{self._current_item_name}" '
            f"for {price_str} platinum. (warframe.market)"
        )
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(whisper)
        tpl = self._copy("prices.status_copied", "已复制悄悄话: {text}")
        self._show_status_label(tpl.format(text=whisper))

    def _on_dropdown_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        self._hide_dropdown()
        self._search_input.blockSignals(True)
        self._search_input.setText(self._format_item_display(data))
        self._search_input.blockSignals(False)
        self._on_query_selected(data)

    def _on_query_selected(self, item_data: dict) -> None:
        """用户选中下拉项:触发价格查询。"""
        self._current_item_name = item_data.get("name", "")
        self._current_item_slug = item_data.get("slug", "")
        PriceFetcher.instance().fetch_async(
            slug=self._current_item_slug,
            name=self._current_item_name,
        )

    def _on_retry_clicked(self) -> None:
        _dbg("page", "_on_retry_clicked: 用户点重试")
        WmItemsRepository.instance().refresh()

    # ══════════════════════════════════════════════════════
    #  对外接口(供 OCR pipeline 调用)
    # ══════════════════════════════════════════════════════

    def query_item_by_name(self, en_name: str, slug: str = "") -> None:
        """OCR pipeline 调用入口(向后兼容)。"""
        if slug:
            self._current_item_name = en_name
            self._current_item_slug = slug
            PriceFetcher.instance().fetch_async(slug=slug, name=en_name)
        else:
            # 没有 slug, 走搜索
            self._search_input.setText(en_name)
            self._do_search()
