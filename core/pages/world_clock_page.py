"""
[L2] WorldClockPage — 世界时钟页面

依赖: widgets/(CyberCard/CyberButton/CyberAnalogClock/CyberWorldClockAddDialog),
      services/world_clock_service(纯数据层), PySide6
职责: 以卡片网格展示用户配置的世界时钟（表盘 + 数字时间 + 日期 + 时区偏移），
      提供「添加城市 / 删除(二次确认) / 恢复默认(弹窗确认)」交互。
父类: PageBase (core/pages/base_page.py)

数据流（单向）:
    world_clock_service(JSON) → _reload() 重建卡片；
    任何变更都由 service 落盘后再 _reload()，页面不缓存列表数据。

走时机制:
    页面 on_enter 时创建 1 秒 QTimer，每秒取一次 UTC 基准时刻，
    经 service.now_in_zone() 换算成各城市本地时间后推给卡片刷新；
    on_leave 时停表（页面不可见时空转毫无意义，也避免多页同时跑心跳）。
    秒针/数字时间的渲染全部由控件自绘完成，页面只做"取数 → 分发"。
"""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QWidget, QGridLayout, QMessageBox,
)

from core.pages.base_page import PageBase
from core.services import world_clock_service
from core.widgets.analog_clock import CyberAnalogClock
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.world_clock_add_dialog import CyberWorldClockAddDialog

# 心跳间隔（毫秒）：秒级精度足够，1Hz 对 CPU 无感
_TICK_MS = 1000
# 删除二次确认的等待时长（毫秒）
_DELETE_CONFIRM_MS = 3000
# 卡片网格列数（内容区宽约 840px，2 列每卡约 400px，时钟卡信息不拥挤）
_GRID_COLUMNS = 2
# 表盘边长（4 的倍数）
_CLOCK_SIZE = 108
# 操作按钮固定宽（4 的倍数）
_BTN_ADD_WIDTH = 128
_BTN_RESET_WIDTH = 128
_BTN_DELETE_WIDTH = 96

# 中文星期（自绘日期行用：不依赖系统 locale，Qt 的 dddd 在非中文
# Windows 上会输出 "Monday"，这里固定中文格式）
_WEEKDAY_ZH = ("一", "二", "三", "四", "五", "六", "日")


class _ClockCard:
    """单张城市时钟卡片的内部句柄（页面私有，不对外导出）。

    把一张卡涉及的所有可变控件收在一处，_on_tick 里逐个 refresh，
    避免在页面里维护 N 份平行列表（时钟/时间标签/日期标签...）导致错位。
    """

    def __init__(self, index: int, city: dict, card: CyberCard,
                 clock: CyberAnalogClock, time_lbl: QLabel,
                 date_lbl: QLabel, meta_lbl: QLabel, day_lbl: QLabel,
                 del_btn: CyberButton):
        self.index = index          # 在 service 列表中的下标（删除时按它定位）
        self.city = city            # {"name": ..., "tz": ...}
        self.card = card
        self.clock = clock
        self.time_lbl = time_lbl
        self.date_lbl = date_lbl
        self.meta_lbl = meta_lbl
        self.day_lbl = day_lbl
        self.del_btn = del_btn

    def refresh(self, now: datetime) -> None:
        """用 UTC 基准时刻刷新本卡全部动态内容。"""
        tz_key = self.city["tz"]
        moment = world_clock_service.now_in_zone(tz_key, now)

        # 表盘走时（24 小时制直接喂入，控件内部 %24 规整）
        self.clock.set_time(moment.hour, moment.minute, moment.second)
        self.time_lbl.setText(moment.strftime("%H:%M:%S"))
        # 中文日期："2026年10月19日 周一"（固定中文，不随系统 locale 变）
        self.date_lbl.setText(
            f"{moment.year}年{moment.month}月{moment.day}日 周{_WEEKDAY_ZH[moment.weekday()]}"
        )

        # 元信息：IANA 时区键 + UTC 偏移
        offset_text = world_clock_service.zone_offset_label(tz_key, now)
        self.meta_lbl.setText(f"{tz_key} · {offset_text}")

        # 相对本机日期的提示：只有相差 ±1 天才显示，
        # 国际日期变更线附近会出现 ±1 以外的大幅差异，那时不显示避免误读
        shift = world_clock_service.day_shift(tz_key, now)
        day_map = {1: "明天", -1: "昨天"}
        self.day_lbl.setText(day_map.get(shift, ""))


class WorldClockPage(PageBase):
    """「世界时钟」页：多时区表盘卡片网格 + 添加/删除/恢复默认。"""

    page_id = "world_clock"
    page_title = ""  # 由 nav token 动态获取
    page_icon = "nav_about"  # 复用既有导航图标资产，不新增图片资源

    def __init__(self):
        # UI 引用必须在 super().__init__() 之前声明：
        # PageBase.__init__ 内部会调 build_content（见 sites_page 同惯例）
        self._clock_cards: list[_ClockCard] = []   # 当前网格内的卡片句柄
        self._tick_timer: QTimer | None = None     # on_enter 创建 / on_leave 停
        self._local_lbl: QLabel | None = None      # 顶部"本地时间"参照行
        self._grid_layout: QGridLayout | None = None
        self._empty_hint: QLabel | None = None

        super().__init__()
        self.page_title = self._copy("nav.world_clock", "世界时钟")

    # ══════════════════════════════
    #  生命周期：走表只在页面可见时进行
    # ══════════════════════════════

    def on_enter(self):
        """进入页面：重读数据（外部改动即时反映）+ 启动心跳。"""
        self._reload()
        if self._tick_timer is None:
            timer = QTimer(self)
            timer.setInterval(_TICK_MS)
            timer.timeout.connect(self._on_tick)
            self._tick_timer = timer
        self._tick_timer.start()
        self._on_tick()  # 立即刷一次，避免进入后 1 秒才出现时间

    def on_leave(self):
        """离开页面：停表（下次进入重新 start，自动立即刷新）。"""
        if self._tick_timer is not None:
            self._tick_timer.stop()

    # ══════════════════════════════
    #  页面构建
    # ══════════════════════════════

    def build_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(self._spacing("md", 12))

        # ── 顶部说明 + 本机参照行 ──
        header = QHBoxLayout()
        header.setSpacing(self._spacing("sm", 8))

        desc = QLabel(
            self._copy(
                "world_clock.desc",
                "北京时间默认展示，可添加世界上其他地区的时钟；时间自动处理夏令时。",
            )
        )
        self._style(desc, color="text.secondary", font_size="sm")
        desc.setWordWrap(True)
        header.addWidget(desc, stretch=1)

        self._local_lbl = QLabel("")
        self._style(
            self._local_lbl,
            color="text.tertiary",
            font_size="sm",
            raw="font-family: monospace;",
        )
        self._local_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header.addWidget(self._local_lbl)
        layout.addLayout(header)

        # ── 操作行：恢复默认 + 添加城市 ──
        action_row = QHBoxLayout()
        action_row.setSpacing(self._spacing("sm", 8))
        action_row.addStretch()

        reset_btn = CyberButton(
            self._copy("world_clock.reset_btn", "恢复默认"),
            variant="outlined",
        )
        reset_btn.setFixedWidth(_BTN_RESET_WIDTH)
        reset_btn.setToolTip(
            self._copy("world_clock.reset_tip", "只保留默认的北京时间")
        )
        reset_btn.clicked.connect(self._on_reset)
        action_row.addWidget(reset_btn)

        add_btn = CyberButton(
            self._copy("world_clock.add_btn", "+ 添加城市"),
            variant="solid",
        )
        add_btn.setFixedWidth(_BTN_ADD_WIDTH)
        add_btn.clicked.connect(self._on_add)
        action_row.addWidget(add_btn)
        layout.addLayout(action_row)

        # ── 时钟卡片网格（2 列，左起自上而下）──
        self._grid_layout = QGridLayout()
        self._grid_layout.setSpacing(self._spacing("md", 12))
        # 两列同权重，卡片均分内容区宽度
        self._grid_layout.setColumnStretch(0, 1)
        self._grid_layout.setColumnStretch(1, 1)
        layout.addLayout(self._grid_layout)

        # 空列表占位（用户删光所有时钟后出现）
        self._empty_hint = QLabel(
            self._copy(
                "world_clock.empty_hint",
                "还没有任何时钟，点击右上角「添加城市」开始。",
            )
        )
        self._style(self._empty_hint, color="text.tertiary", font_size="sm")
        self._empty_hint.setVisible(False)
        layout.addWidget(self._empty_hint)

        layout.addStretch()
        return container

    # ══════════════════════════════
    #  网格渲染
    # ══════════════════════════════

    def _reload(self) -> None:
        """从 service 读全量数据并重建卡片（单一数据源，不做内存缓存）。"""
        if self._grid_layout is None:
            return
        # ── 清空旧卡片 ──
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            old = item.widget()
            if old is not None:
                # setParent(None) 立即断开 QObject 父子关系（takeAt 只移出
                # 布局、不断父子），再延迟释放，避免重建瞬间旧卡片仍在子树
                old.setParent(None)
                old.deleteLater()
        self._clock_cards.clear()

        cities = world_clock_service.load_cities()
        for index, city in enumerate(cities):
            row, col = divmod(index, _GRID_COLUMNS)
            self._grid_layout.addWidget(
                self._make_clock_card(index, city), row, col
            )

        if self._empty_hint is not None:
            self._empty_hint.setVisible(len(cities) == 0)

        # 数据变化后立即用当前时刻刷新一次，不等下一个心跳
        self._on_tick()

    def _make_clock_card(self, index: int, city: dict) -> CyberCard:
        """构建单张城市时钟卡：表盘 + 数字时间 + 日期 + 时区元信息 + 删除。"""
        card = CyberCard()
        hl = QHBoxLayout()
        hl.setContentsMargins(16, 14, 16, 14)
        hl.setSpacing(self._spacing("md", 12))

        # ── 左：模拟表盘 ──
        clock = CyberAnalogClock()
        clock.setFixedSize(_CLOCK_SIZE, _CLOCK_SIZE)
        hl.addWidget(clock)

        # ── 中：城市名 + 数字时间 + 日期 + 元信息 ──
        info = QVBoxLayout()
        info.setSpacing(2)

        # 城市名：面板标题级字号 + 强调色（用户自取的别名）
        name_lbl = QLabel(city["name"])
        self._style(name_lbl, color="accent.primary", font_size="md_lg")
        info.addWidget(name_lbl)

        # 数字时间：统计数值级字号，等宽字体保证秒位跳动不抖
        time_lbl = QLabel("--:--:--")
        self._style(
            time_lbl,
            color="text.primary",
            font_size="xxl",
            raw="font-family: monospace;",
        )
        info.addWidget(time_lbl)

        # 日期：本地化中文格式（_ClockCard.refresh 内填充）
        date_lbl = QLabel("")
        self._style(date_lbl, color="text.secondary", font_size="sm")
        info.addWidget(date_lbl)

        # 元信息行：IANA 时区键 + UTC 偏移 + 相对日期提示
        meta_row = QHBoxLayout()
        meta_row.setSpacing(self._spacing("xs", 4))
        meta_lbl = QLabel("")
        self._style(meta_lbl, color="text.tertiary", font_size="sm",
                    raw="font-family: monospace;")
        meta_row.addWidget(meta_lbl)
        # 相对日期提示（明天/昨天）：平时为空串但保留占位，避免出现时布局跳动
        day_lbl = QLabel("")
        self._style(day_lbl, color="semantic.warning", font_size="sm")
        meta_row.addWidget(day_lbl)
        meta_row.addStretch()
        info.addLayout(meta_row)

        hl.addLayout(info, stretch=1)

        # ── 右：删除（二次确认，同常用网站页交互）──
        del_btn = CyberButton(
            self._copy("world_clock.delete_btn", "删 除"),
            variant="semantic.danger",
        )
        del_btn.setFixedWidth(_BTN_DELETE_WIDTH)
        del_btn.clicked.connect(lambda: self._on_delete_clicked(index, del_btn))
        hl.addWidget(del_btn, alignment=Qt.AlignmentFlag.AlignTop)

        card.content_layout().addLayout(hl)

        handle = _ClockCard(index, city, card, clock, time_lbl,
                            date_lbl, meta_lbl, day_lbl, del_btn)
        self._clock_cards.append(handle)
        return card

    # ══════════════════════════════
    #  心跳：每秒换算并分发
    # ══════════════════════════════

    def _on_tick(self) -> None:
        """每秒触发：以 UTC 为基准给每张卡 + 本机参照行刷新。"""
        now = datetime.now(timezone.utc)
        for handle in self._clock_cards:
            handle.refresh(now)
        if self._local_lbl is not None:
            local = now.astimezone()
            self._local_lbl.setText(
                self._copy(
                    "world_clock.local_ref",
                    "本地 {time} · {utc}",
                    time=local.strftime("%H:%M:%S"),
                    utc=world_clock_service.local_offset_label(now),
                )
            )

    # ══════════════════════════════
    #  交互：添加 / 删除 / 恢复默认
    # ══════════════════════════════

    def _on_add(self) -> None:
        """打开添加对话框；校验与落盘由 service 完成（经 validator 注入）。"""
        # 默认选中"尚未添加的首个目录时区"：避免打开对话框就落在
        # 已添加的北京上（一确定就报重复），也避免落在分组标题行
        existing = {city["tz"] for city in world_clock_service.load_cities()}
        preselect = next(
            (tz for _name, tz, _region in world_clock_service.TIMEZONE_CATALOG
             if tz not in existing),
            "",
        )
        dlg = CyberWorldClockAddDialog(
            catalog=world_clock_service.TIMEZONE_CATALOG,
            validator=self._validate_and_add,
            preselect_tz=preselect,
            parent=self,
        )
        if dlg.exec() == CyberWorldClockAddDialog.DialogCode.Accepted:
            self._reload()

    def _validate_and_add(self, name: str, tz: str) -> tuple[bool, str]:
        """供对话框调用：调 service 校验+落盘，原因码映射为中文文案。

        Returns:
            (True, "") 成功；(False, 可展示文案) 失败，对话框保持打开。
        """
        ok, reason = world_clock_service.add_city(name, tz)
        if ok:
            return True, ""
        message_map = {
            world_clock_service.REASON_EMPTY_NAME:
                self._copy("world_clock.err_name_empty", "请填写显示名称"),
            world_clock_service.REASON_BAD_TIMEZONE:
                self._copy("world_clock.err_bad_timezone", "请选择有效时区"),
            world_clock_service.REASON_DUPLICATE:
                self._copy("world_clock.err_duplicate", "该时区的时钟已在列表中"),
        }
        return False, message_map.get(reason, str(reason))

    def _on_delete_clicked(self, index: int, btn: CyberButton) -> None:
        """删除二次确认：首次点击按钮变红提示，3 秒内再点才真正删除。

        QTimer 的 parent 设为按钮本身——卡片重建时按钮销毁，
        定时器随之自动停止，避免回调操作已销毁控件。
        """
        if not getattr(btn, "_cyber_confirming", False):
            btn._cyber_confirming = True
            btn.setText(self._copy("world_clock.confirm_delete", "确认删除？"))
            timer = QTimer(btn)
            timer.setSingleShot(True)
            timer.timeout.connect(
                lambda b=btn: self._cancel_delete_confirm(b)
            )
            timer.start(_DELETE_CONFIRM_MS)
            return

        world_clock_service.remove_city(index)
        self._reload()

    def _cancel_delete_confirm(self, btn: CyberButton) -> None:
        """3 秒内未二次点击：按钮还原为普通删除态。"""
        btn._cyber_confirming = False
        btn.setText(self._copy("world_clock.delete_btn", "删 除"))

    def _on_reset(self) -> None:
        """恢复默认（只留北京）：会丢弃用户已添加的全部时钟，弹窗确认。"""
        reply = QMessageBox.question(
            self,
            self._copy("world_clock.reset_btn", "恢复默认"),
            self._copy(
                "world_clock.reset_confirm",
                "将清空你添加的所有时钟，只保留默认的北京时间。确定继续？",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        world_clock_service.reset_cities()
        self._reload()
