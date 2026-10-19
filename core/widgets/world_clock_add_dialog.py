"""
[L5] CyberWorldClockAddDialog — 添加世界时钟对话框

继承: CyberWidgetMixin + QDialog
依赖: core.tokens(经 mixin), core.widgets.button/line_edit/combo_box,
      Python 标准库(datetime/zoneinfo,仅用于所选时区实时预览), PySide6
职责: 采集"显示名称 + 时区"两项输入，下拉项附带实时 UTC 偏移标签
      （如"北京 · UTC+8"，随夏令时变化自动刷新），点击确定时回调
      注入的校验器；校验失败在框内红字提示且不关闭，成功才 accept。
信号: 无（exec() 返回 Accepted 后由调用方刷新列表）

分层说明:
    本控件不 import 任何 service —— 候选时区目录以参数形式由页面注入
    （页面从 core.services.world_clock_service.TIMEZONE_CATALOG 读取），
    校验/落盘同样以 Callable 注入，签名与 CyberSiteAddDialog 保持一致:
        (名称, 时区键) -> (是否通过, 失败时的展示文案)
    预览行走秒用的是标准库 zoneinfo（纯数据换算，不经业务层），
    因此 widgets 层依然不认识"城市数据/持久化"的概念。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from core.widgets.base import CyberWidgetMixin
from core.widgets.button import CyberButton
from core.widgets.combo_box import CyberComboBox
from core.widgets.line_edit import CyberLineEdit

# 对话框固定宽度（4 的倍数；比添加网站略宽，容纳时区下拉与预览行）
_DIALOG_WIDTH = 440
# 输入框高度（与全站 md 输入一致）
_INPUT_HEIGHT = 36
# 底部操作按钮宽
_BTN_OK_WIDTH = 96
_BTN_CANCEL_WIDTH = 80
# 预览行走秒间隔（毫秒）：所选时区的"实时预览"每秒刷新
_PREVIEW_TICK_MS = 1000

# 校验器签名：(名称, 时区键) -> (是否通过, 失败时的展示文案)
CityValidator = Callable[[str, str], tuple[bool, str]]


class CyberWorldClockAddDialog(CyberWidgetMixin, QDialog):
    """添加时钟模态对话框。

    Args:
        catalog: 候选城市目录 [(展示名, 时区键, 地区分组), ...]，
            由页面从 service 的 TIMEZONE_CATALOG 传入（widget 不反向依赖）。
        validator: 可选校验/落盘回调，签名见 CityValidator。
        preselect_tz: 建议默认选中的时区键（页面传入"尚未添加的首个时区"），
            避免默认落在分组标题行、或落在已添加时区上一确定就报重复。
            找不到该时区时兜底选第一个可选项。
        parent: 父窗口。
    """

    def __init__(
        self,
        catalog: list[tuple[str, str, str]],
        validator: CityValidator | None = None,
        preselect_tz: str = "",
        parent: QWidget | None = None,
    ):
        QDialog.__init__(self, parent)
        self._validator = validator
        self._name = ""
        self._tz = ""

        self.setWindowTitle(self.copy("world_clock.dlg_title", "添加世界时钟"))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        # 对话框底色（走 palette，不用 stylesheet，参照图片裁剪对话框）
        pal = self.palette()
        pal.setColor(
            QPalette.ColorRole.Window, self.token_color("alias.bg.raised")
        )
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        text_dim = self.token_color("text.tertiary")
        danger = self.token_color("semantic.danger", "brand.red")
        accent = self.token_color("accent.primary")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── 显示名称 ──
        name_lbl = QLabel(self.copy("world_clock.dlg_name_label", "显示名称"))
        name_lbl.setStyleSheet(
            f"color: {text_dim.name()}; font-size: {self.space('font.xs', 11)}px;"
            " background: transparent; border: none;"
        )
        root.addWidget(name_lbl)

        self._name_edit = CyberLineEdit(
            placeholder=self.copy(
                "world_clock.dlg_name_ph", "例如：北京 / 家里时间 / 队友时区"
            )
        )
        self._name_edit.setFixedHeight(_INPUT_HEIGHT)
        # 名称框回车 = 点确定（时区走下拉选择，没有第二个输入框需要跳转）
        self._name_edit.returnPressed.connect(self._try_accept)
        root.addWidget(self._name_edit)

        # ── 时区下拉（按地区分组 + 分隔符）──
        tz_lbl = QLabel(self.copy("world_clock.dlg_tz_label", "时区"))
        tz_lbl.setStyleSheet(
            f"color: {text_dim.name()}; font-size: {self.space('font.xs', 11)}px;"
            " background: transparent; border: none;"
        )
        root.addWidget(tz_lbl)

        self._tz_combo = CyberComboBox()
        # 可选项登记表：(行索引, 展示名, 时区键) —— 用于给每项追加
        # "· UTC+8" 偏移标签（偏移随夏令时变化，随预览同频刷新）
        self._combo_entries: list[tuple[int, str, str]] = []
        current_region = None
        for display, tz_key, region in catalog:
            # 分组切换时插入一条视觉分隔符 + 地区名标题行；
            # 标题行不是可选时区（userData 为空且禁用），键盘也落不上去
            if region != current_region:
                if current_region is not None:
                    self._tz_combo.insertSeparator(
                        self._tz_combo.count()
                    )
                header_index = self._tz_combo.count()
                self._tz_combo.addItem(f"── {region} ──", userData="")
                # 禁用标题行：Qt 原生 combo 无分组标题，用禁用的普通项模拟
                header_item = self._tz_combo.model().item(header_index)
                if header_item is not None:
                    header_item.setFlags(
                        header_item.flags() & ~Qt.ItemFlag.ItemIsEnabled
                    )
                current_region = region
            # userData 存 IANA 时区键；展示名对用户可见
            self._tz_combo.addItem(display, userData=tz_key)
            self._combo_entries.append(
                (self._tz_combo.count() - 1, display, tz_key)
            )
        self._tz_combo.currentIndexChanged.connect(self._on_tz_changed)
        root.addWidget(self._tz_combo)

        # ── 实时预览：所选时区的当前时刻（每秒刷新）──
        self._preview_lbl = QLabel("")
        self._preview_lbl.setStyleSheet(
            f"color: {accent.name()}; font-size: {self.space('font.sm', 12)}px;"
            " background: transparent; border: none;"
        )
        root.addWidget(self._preview_lbl)

        # ── 错误提示（平时隐藏，保留占位避免按钮跳动） ──
        self._error_lbl = QLabel("")
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(
            f"color: {danger.name()}; font-size: {self.space('font.xs', 11)}px;"
            " background: transparent; border: none;"
        )
        self._error_lbl.setVisible(False)
        root.addWidget(self._error_lbl)

        # ── 底部操作 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        hint = QLabel(self.copy("world_clock.dlg_tz_hint", "时区来自 IANA 数据库，自动处理夏令时"))
        hint.setStyleSheet(
            f"color: {text_dim.name()}; font-size: {self.space('font.micro', 10)}px;"
            " background: transparent; border: none;"
        )
        bottom.addWidget(hint)
        bottom.addStretch()

        ok_btn = CyberButton(self.copy("world_clock.dlg_ok", "添 加"), variant="solid")
        cancel_btn = CyberButton(
            self.copy("world_clock.dlg_cancel", "取 消"), variant="ghost"
        )
        ok_btn.setFixedWidth(_BTN_OK_WIDTH)
        cancel_btn.setFixedWidth(_BTN_CANCEL_WIDTH)
        ok_btn.clicked.connect(self._try_accept)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(ok_btn)
        bottom.addWidget(cancel_btn)
        root.addLayout(bottom)

        # 预览走秒定时器：parent 绑定对话框，关闭时自动停止
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(_PREVIEW_TICK_MS)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self.setFixedWidth(_DIALOG_WIDTH)
        self.adjustSize()
        # 选中项兜底：分组标题行是禁用的空 data 项，不能作为默认选中；
        # 优先用调用方建议的时区，找不到则落到第一个可选项
        self._select_default_tz(preselect_tz)
        self._on_tz_changed()
        self._preview_timer.start()
        self._name_edit.setFocus()

    # ════════════════════════════════
    #  对外
    # ════════════════════════════════

    def get_data(self) -> tuple[str, str]:
        """accept 后读取用户输入 (显示名称, 时区键)。"""
        return self._name, self._tz

    # ════════════════════════════════
    #  内部
    # ════════════════════════════════

    def _selected_tz(self) -> str:
        """当前下拉选中项的时区键（地区分隔行为空串）。"""
        return str(self._tz_combo.currentData() or "")

    def _select_default_tz(self, preferred: str) -> None:
        """把默认选中项落到一个真实时区上（分组标题行不可选）。

        优先 ``preferred``（页面传来的"还没添加的首个时区"）；
        未提供/找不到时兜底选中目录里第一个可选项。
        """
        found = False
        if preferred:
            for i in range(self._tz_combo.count()):
                if str(self._tz_combo.itemData(i) or "") == preferred:
                    self._tz_combo.setCurrentIndex(i)
                    found = True
                    break
        if not found:
            for i in range(self._tz_combo.count()):
                if str(self._tz_combo.itemData(i) or ""):
                    self._tz_combo.setCurrentIndex(i)
                    break

    def _on_tz_changed(self) -> None:
        """下拉切换：立即刷新一次预览，并清理上次的错误提示。"""
        self._error_lbl.setVisible(False)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """刷新所选时区预览 + 下拉各项的 UTC 偏移标签（每秒一次）。"""
        # 先刷下拉标签：即使当前选中项是标题行（预览为空）也要跟上
        self._refresh_combo_labels()
        tz_key = self._selected_tz()
        if not tz_key:
            self._preview_lbl.setText("")
            return
        try:
            moment = datetime.now(timezone.utc).astimezone(ZoneInfo(tz_key))
        except Exception:
            # 目录数据是代码内置的，正常不会走到；兜底隐藏预览不打断对话框
            self._preview_lbl.setText("")
            return
        self._preview_lbl.setText(
            self.copy(
                "world_clock.dlg_preview",
                "当前时间：{time}（{utc}）",
                time=moment.strftime("%H:%M:%S"),
                utc=self._utc_offset_label(moment.utcoffset()),
            )
        )

    def _refresh_combo_labels(self) -> None:
        """给下拉每个可选项追加 UTC 偏移标签："北京 · UTC+8"。

        偏移随夏令时切换而变化，因此与预览行走秒同频刷新；
        文本未变化时不调 setItemText，稳态下零重绘开销。
        widget 层不 import service，时区换算用标准库 zoneinfo 就地完成。
        """
        now_utc = datetime.now(timezone.utc)
        for index, display, tz_key in self._combo_entries:
            try:
                moment = now_utc.astimezone(ZoneInfo(tz_key))
            except Exception:
                continue  # 目录数据内置，正常不可达；跳过不影响其它项
            label = f"{display} · {self._utc_offset_label(moment.utcoffset())}"
            if self._tz_combo.itemText(index) != label:
                self._tz_combo.setItemText(index, label)

    @staticmethod
    def _utc_offset_label(offset) -> str:
        """timedelta → "UTC+8" / "UTC-6" / "UTC+5:30"（整点省略分钟）。

        与页面卡片元信息行的偏移格式保持一致（service.zone_offset_label）。
        """
        if offset is None:
            return "UTC"
        total_minutes = int(offset.total_seconds() // 60)
        sign = "+" if total_minutes >= 0 else "-"
        hours, minutes = divmod(abs(total_minutes), 60)
        if minutes:
            return f"UTC{sign}{hours:02d}:{minutes:02d}"
        return f"UTC{sign}{hours}"

    def _try_accept(self) -> None:
        """点确定/名称框回车：校验通过才关闭，否则就地显示错误。"""
        name = self._name_edit.text().strip()
        tz_key = self._selected_tz()

        if not name:
            self._show_error(self.copy("world_clock.err_name_empty", "请填写显示名称"))
            self._name_edit.setFocus()
            return
        if not tz_key:
            # 选中的是地区分隔行：正常 combo 操作无法选中分隔符，
            # 键盘上下键可能落到这里，仍需拦截
            self._show_error(self.copy("world_clock.err_bad_timezone", "请选择一个有效时区"))
            return

        if self._validator is not None:
            ok, message = self._validator(name, tz_key)
            if not ok:
                self._show_error(message)
                return

        self._name, self._tz = name, tz_key
        self.accept()

    def _show_error(self, text: str) -> None:
        self._error_lbl.setText(text)
        self._error_lbl.setVisible(True)
        self.adjustSize()
