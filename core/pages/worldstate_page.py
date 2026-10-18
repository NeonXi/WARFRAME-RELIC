"""
[L2] core.pages.worldstate_page — 虚空裂缝一线战报页面

═══════════════════════════════════════════════════════════════════════
归属层:    [L2] (core/pages/)
依赖:      core.services.worldstate_service (裂缝数据)
           core.widgets.* + PySide6
职责:      纯 UI 组装 + 信号订阅(纪元筛选 / 仅钢铁之路 / 倒计时)
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import time

import shiboken6

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from core.pages.base_page import PageBase
from core.services.worldstate_service import WorldstateService
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.progress_bar import CyberProgressBar


# ── 纪元筛选项: (tier_en, 中文标签);空串表示"全部" ──
_TIER_FILTERS: list[tuple[str, str]] = [
    ("", "全部"),
    ("Lith", "古纪"),
    ("Meso", "前纪"),
    ("Neo", "中纪"),
    ("Axi", "后纪"),
    ("Requiem", "安魂"),
    ("Omnia", "全能"),
]

# ── 表格列: (表头, 宽度权重) ──
_COLUMNS = ["纪元", "任务", "节点", "派系", "模式", "剩余时间"]


class WorldstatePage(PageBase):
    """虚空裂缝一线战报页。

    数据流:
      WorldstateService → Signal → 本页槽 → 表格
    """

    page_id = "worldstate"
    page_title = ""
    page_icon = "nav_worldstate"

    def __init__(self) -> None:
        # ── 引用(在 super 前声明) ──
        self._table: QTableWidget | None = None
        self._status_label: QLabel | None = None
        self._retry_btn: CyberButton | None = None
        self._tier_chips: dict[str, CyberButton] = {}
        self._mode_btn_hard: CyberButton | None = None
        self._mode_btn_normal: CyberButton | None = None
        self._tick_timer: QTimer | None = None

        # 数据与筛选
        self._fissures: list[dict] = []
        self._tier_filter: str = ""
        # 模式筛选: ""=全部 / "hard"=仅钢铁之路 / "normal"=仅普通
        self._mode_filter: str = ""
        self._last_update: float = 0.0

        # 信号是否已连接(防重复)
        self._bound: bool = False

        super().__init__()
        self.page_title = "一线战报"

        # 启动 10s 后台预取一次裂缝数据(不等用户进页面):
        # DE 官方 API 国内访问 10-20s,预取写入磁盘缓存后,
        # 用户首次进页面即可秒显数据(refresh 幂等,worker 有去重锁)
        QTimer.singleShot(10_000, WorldstateService.instance().refresh)

    # ══════════════════════════════════════════════════
    #  构建
    # ══════════════════════════════════════════════════

    def build_content(self) -> QWidget:
        _fs = self._font_size

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(
            self._spacing("lg", 20), self._spacing("sm", 8),
            self._spacing("lg", 20), self._spacing("lg", 20)
        )
        root.setSpacing(self._spacing("sm", 8))

        # ── 标题 ──
        title = QLabel("一线战报 · 虚空裂缝")
        title.setFont(QFont("Iceberg", _fs("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        root.addWidget(title)

        # ── 半透明衬底卡片:统一包裹筛选条 + 表格 + 状态行 ──
        card = CyberCard()
        card_layout = card.content_layout()
        card_layout.setSpacing(self._spacing("sm", 8))

        card_layout.addWidget(self._build_filter_bar())

        # ── 裂缝表格(透明背景,露出卡片半透明衬底)──
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        # 行高给进度条留空间(btn_sm=28)
        self._table.verticalHeader().setDefaultSectionSize(
            self._spacing("height.btn_sm", 28)
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._style(
            self._table,
            raw=(
                "QTableWidget {"
                "  background-color: transparent;"
                "  border: none;"
                "  outline: none;"
                "}"
                "QTableWidget::item { background-color: transparent; }"
                "QTableCornerButton::section {"
                "  background-color: transparent;"
                "  border: none;"
                "}"
                "QHeaderView::section {"
                "  background-color: transparent;"
                "  border: none;"
                "}"
            ),
        )
        card_layout.addWidget(self._table, stretch=1)

        # ── 状态行 ──
        status_row = QHBoxLayout()
        status_row.setSpacing(self._spacing("sm", 8))
        self._status_label = QLabel("正在加载…")
        self._style(self._status_label, color="text.tertiary", font_size="sm")
        status_row.addWidget(self._status_label, stretch=1)
        self._retry_btn = CyberButton("重试", variant="ghost")
        self._retry_btn.clicked.connect(self._on_retry)
        self._retry_btn.hide()
        status_row.addWidget(self._retry_btn)
        card_layout.addLayout(status_row)

        root.addWidget(card, stretch=1)

        return container

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._spacing("xs", 4))

        for tier_en, label in _TIER_FILTERS:
            chip = CyberButton(
                label,
                variant="solid" if tier_en == self._tier_filter else "outlined",
            )
            chip.setFixedHeight(28)
            chip.clicked.connect(lambda checked=False, t=tier_en: self._on_tier(t))
            self._tier_chips[tier_en] = chip
            layout.addWidget(chip)

        layout.addStretch(1)

        self._mode_btn_hard = CyberButton("仅钢铁之路", variant="outlined")
        self._mode_btn_hard.setFixedHeight(28)
        self._mode_btn_hard.clicked.connect(
            lambda: self._on_mode("hard")
        )
        layout.addWidget(self._mode_btn_hard)

        self._mode_btn_normal = CyberButton("仅普通", variant="outlined")
        self._mode_btn_normal.setFixedHeight(28)
        self._mode_btn_normal.clicked.connect(
            lambda: self._on_mode("normal")
        )
        layout.addWidget(self._mode_btn_normal)

        return bar

    # ══════════════════════════════════════════════════
    #  生命周期
    # ══════════════════════════════════════════════════

    def on_enter(self) -> None:
        if not self._bound:
            svc = WorldstateService.instance()
            svc.fissures_changed.connect(self._on_fissures)
            svc.loading_started.connect(self._on_loading)
            svc.load_failed.connect(self._on_failed)
            self._bound = True

        WorldstateService.instance().attach()

        # 进入即提示刷新(attach 内会发起请求;此处立即给视觉反馈)
        self._set_status(
            "正在加载…" if not self._fissures else "正在刷新…"
        )

        # 每秒刷新倒计时
        if self._tick_timer is None:
            self._tick_timer = QTimer(self)
            self._tick_timer.setInterval(1000)
            self._tick_timer.timeout.connect(self._render)
        self._tick_timer.start()

    def on_leave(self) -> None:
        WorldstateService.instance().detach()
        if self._tick_timer is not None:
            self._tick_timer.stop()

    # ══════════════════════════════════════════════════
    #  服务槽
    # ══════════════════════════════════════════════════

    def _on_loading(self) -> None:
        if self._status_label is None:
            return
        # 有旧数据时是"刷新",无数据时是首次"加载"
        self._set_status(
            "正在加载…" if not self._fissures else "正在刷新…"
        )

    def _on_fissures(self, fissures: list) -> None:
        self._fissures = list(fissures)
        self._last_update = time.time()
        if self._retry_btn is not None:
            self._retry_btn.hide()
        self._render()

    def _on_failed(self, error: str) -> None:
        if self._fissures:
            # 有旧数据:只提示,继续展示缓存
            self._set_status(f"刷新失败,显示旧数据 · {error}", warn=True)
            return
        self._set_status(f"加载失败 · {error}", error=True)
        if self._retry_btn is not None:
            self._retry_btn.show()

    # ══════════════════════════════════════════════════
    #  筛选交互
    # ══════════════════════════════════════════════════

    def _on_tier(self, tier_en: str) -> None:
        self._tier_filter = tier_en
        for t, chip in self._tier_chips.items():
            chip.variant = "solid" if t == tier_en else "outlined"
        self._render()

    def _on_mode(self, mode: str) -> None:
        """模式筛选切换(互斥):再点当前项则取消,回全部。

        Args:
            mode: "hard"(仅钢铁) / "normal"(仅普通)
        """
        self._mode_filter = "" if self._mode_filter == mode else mode
        self._update_mode_variants()
        self._render()

    def _update_mode_variants(self) -> None:
        """按当前模式刷新两个按钮:选中 solid 黄,其余 outlined 蓝。"""
        if self._mode_btn_hard is not None:
            self._mode_btn_hard.variant = (
                "solid" if self._mode_filter == "hard" else "outlined"
            )
        if self._mode_btn_normal is not None:
            self._mode_btn_normal.variant = (
                "solid" if self._mode_filter == "normal" else "outlined"
            )

    def _on_retry(self) -> None:
        WorldstateService.instance().refresh()

    # ══════════════════════════════════════════════════
    #  渲染
    # ══════════════════════════════════════════════════

    def _filtered(self) -> list[dict]:
        rows = self._fissures
        if self._tier_filter:
            rows = [x for x in rows if x["tier_en"] == self._tier_filter]
        if self._mode_filter == "hard":
            rows = [x for x in rows if x["hard"]]
        elif self._mode_filter == "normal":
            rows = [x for x in rows if not x["hard"]]
        return rows

    def _render(self) -> None:
        rows = self._filtered()
        now = time.time()

        # 行数将减少时,手动移除多余行的 cell widget
        # (QTableWidget.setRowCount 不会自动销毁它们;且本环境下
        # deleteLater 不生效 → 解绑后用 shiboken 立即销毁)
        new_n = len(rows)
        old_n = self._table.rowCount()
        if new_n < old_n:
            for r in range(new_n, old_n):
                w = self._table.cellWidget(r, 5)
                if w is not None:
                    self._table.removeCellWidget(r, 5)
                    w.setParent(None)
                    shiboken6.delete(w)

        self._table.setRowCount(new_n)
        for row, x in enumerate(rows):
            remaining = int(x["expiry"] - now)
            cells = [
                f"{x['tier_zh']} {x['tier_en']}",
                x["mission"],
                f"{x['node']}({x['planet']})" if x.get("planet") else x["node"],
                x["faction"],
                "钢铁之路" if x["hard"] else "普通",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setForeground(QColor(self._color("accent.primary")))
                self._table.setItem(row, col, item)

            # 第 6 列:进度条(下层)+ 时间文字(上层),widget 复用
            total = int(x["expiry"] - x["activation"])
            fraction = remaining / total if total > 0 else 0.0
            bar = self._table.cellWidget(row, 5)
            if bar is None:
                bar = CyberProgressBar()
                self._table.setCellWidget(row, 5, bar)
            bar.set_state(
                self._format_remaining(remaining),
                fraction,
                self._remaining_color(remaining),
            )

        # 状态行
        if self._fissures:
            shown = len(rows)
            age = int(now - self._last_update) if self._last_update else 0
            self._set_status(f"共 {shown} 个裂缝 · {age} 秒前更新")

    @staticmethod
    def _format_remaining(seconds: int) -> str:
        if seconds <= 0:
            return "即将结束"
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def _remaining_color(seconds: int) -> str:
        """进度条填充色:青(正常)→橙(<15分)→红(<5分)。"""
        if seconds < 300:
            return "alias.semantic.danger"
        if seconds < 900:
            return "alias.semantic.warning"
        return "accent.secondary"

    def _set_status(self, text: str, *, error: bool = False, warn: bool = False) -> None:
        if self._status_label is None:
            return
        self._status_label.setText(text)
        if error:
            self._style(self._status_label, color="alias.semantic.danger", font_size="sm")
        elif warn:
            self._style(self._status_label, color="alias.semantic.warning", font_size="sm")
        else:
            self._style(self._status_label, color="text.tertiary", font_size="sm")
