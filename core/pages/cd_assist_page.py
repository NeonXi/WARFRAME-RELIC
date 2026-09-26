"""
[L2] core.pages.cd_assist_page — CD 辅助显示 设置页

═══════════════════════════════════════════════════════════════════════
依赖图(严格自上而下,下层不能反向依赖)
═══════════════════════════════════════════════════════════════════════
  core.pages.base_page     ← PageBase(抽象基类)
       ↓
  core.pages.cd_assist_page ← 本文件
       ↓ 允许依赖
  core.widgets.card / button / toggle_switch / screen_select_button
  core.widgets.cd_assist_overlay (Manager + Overlay)
  core.services.cd_assist_service (CdAssistService 单例)
  core.tokens.manager (通过 PageBase / _tm 间接)
       ↓ 禁止依赖
  core.services.* 反向禁止 / core.widgets 反向禁止 / 任何 IO

═══════════════════════════════════════════════════════════════════════
职责
═══════════════════════════════════════════════════════════════════════
  - 4 个技能(N=1..4)各自设置秒数(0-300,step=0.5)
  - 4 个技能各自设置"提醒阈值"(0-60,step=0.5,0=关闭,快到时间闪烁)
  - 启用屏幕(多选,默认全选,会话级)
  - 全局开关(关闭后按键 1/2/3/4 不再触发)
  - 按键 1/2/3/4 触发后,屏幕中心显示对应 cell 的倒计时(1 位小数)
  - 显示位置(X/Y 偏移,±2000px,持久化到 data/cd_assist_pos.json)

═══════════════════════════════════════════════════════════════════════
数据流
═══════════════════════════════════════════════════════════════════════
  UI (QDoubleSpinBox / QSlider / ScreenSelectButton / CyberToggleSwitch)
    ↓ valueChanged / clicked
  CdAssistPage._on_*_changed
    ↓
  CdAssistService (单例,纯逻辑)
    ↓ countdown_tick / state_changed
  CdAssistManager → CdAssistOverlay (多屏悬浮窗)
    ↓ update_cells / set_offset
  Win32 透明窗口(屏幕中心 + 偏移)

═══════════════════════════════════════════════════════════════════════
i18n key 列表(命名空间 cd_assist.*)
═══════════════════════════════════════════════════════════════════════
  cd_assist.desc                  页面描述
  cd_assist.btn.select_all        全选
  cd_assist.btn.select_none       全不选
  cd_assist.btn.clear_all         清除所有
  cd_assist.btn.reset_center      重置居中
  cd_assist.label.primary         主屏
  cd_assist.label.skill           技能 {n}
  cd_assist.label.reminder        提醒
  cd_assist.label.off             关(reminder value=0 时显示)
  cd_assist.label.enable          启用 CD 辅助显示
  cd_assist.label.x_offset        X 偏移
  cd_assist.label.y_offset        Y 偏移
  cd_assist.unit.seconds          秒
  cd_assist.card.skill.title      技能秒数设置
  cd_assist.card.skill.tip        (整段 tip 文字)
  cd_assist.card.screen.title     启用屏幕
  cd_assist.card.toggle.title     全局开关
  cd_assist.card.toggle.tip       关闭后...
  cd_assist.card.position.title   显示位置
  cd_assist.card.position.tip     调整倒计时...
  cd_assist.card.status.title     当前倒计时
  cd_assist.card.status.tip       按下 1/2/3/4 键后...
  cd_assist.screen.label          屏幕 {n} · {w} × {h}{primary}
  cd_assist.screen.primary_suffix · 主屏
  cd_assist.screen.selected_count 已选 {selected} / {total}
  cd_assist.hotkey.item           技能 {n}: {key}
  cd_assist.hotkey.sep            /  / /
  cd_assist.status.skill_active   技能 {n}: {sec}s
  cd_assist.status.skill_idle     技能 {n}: ·
  cd_assist.status.sep            · (状态文字分隔符)

═══════════════════════════════════════════════════════════════════════
层级 / 开发规范要点
═══════════════════════════════════════════════════════════════════════
  ✓ 文件在 core/pages/(L2 层,只能依赖 widgets/ + services/)
  ✓ 颜色全部走 token(grep 验证 0 个 #XXXXXX)
  ✓ 用户可见字符串全部走 i18n(_copy)
  ✓ 尺寸全部 4 倍数(16/32/36/44/...)
  ✓ setStyleSheet 集中到 _apply_spin_style(等 CyberSpinBox 出现后再切换)
  ✓ 没碰 services/ 反向依赖 widgets
  ✓ 没硬编码颜色
  ✓ 继承 PageBase 抽象基类
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QSlider, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication

from core.pages.base_page import PageBase
from core.widgets.card import CyberCard
from core.widgets.button import CyberButton
from core.widgets.toggle_switch import CyberToggleSwitch
from core.widgets.screen_select_button import ScreenSelectButton
from core.services.cd_assist_service import (
    CdAssistService, SKILL_COUNT,
    POS_OFFSET_MIN, POS_OFFSET_MAX,
    SKILL_DURATION_MIN, SKILL_DURATION_MAX,
    SKILL_REMINDER_MIN, SKILL_REMINDER_MAX,
    SKILL_STEP,
)
from core.widgets.cd_assist_overlay import CdAssistManager


class _NoWheelSlider(QSlider):
    """QSlider 子类,禁用滚轮调节。

    默认 QSlider 滚轮 ±1 调节,容易误触(用户滚鼠标想滚动页面时,焦点在 slider
    上就会改位置)。这里重写 wheelEvent 直接吞掉事件,什么都不做。

    设计依据:开发规范「5.5 事件处理必须 super()」是针对已有功能的扩展;
    本类**故意不调** super().wheelEvent(),是已声明的设计意图(禁用滚轮)。
    """

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        """吞掉滚轮事件:接受但不处理(从而让 QSlider 不响应)。"""
        event.accept()


class _NoWheelSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox 子类,禁用滚轮调节。

    与 _NoWheelSlider 同理:滚轮容易误触(尤其嵌在页面滚动区域时),
    直接吞掉事件,禁止滚轮改数值。
    """

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        """吞掉滚轮事件:接受但不处理(从而让 QDoubleSpinBox 不响应)。"""
        event.accept()


class CdAssistPage(PageBase):
    """CD 辅助显示 设置页面。

    ─────────────────────────────────────────────────────────────────
    功能简表
    ─────────────────────────────────────────────────────────────────
      卡片 1: 技能秒数设置(4 行,每行 [技能 N] [时长] [提醒])
              + 「清除所有」按钮(归零全部)
      卡片 2: 启用屏幕(多选 + 全选/全不选快捷 + 主屏标记)
      卡片 3: 全局开关(关闭后按键 1/2/3/4 不再触发)
      卡片 4: 显示位置(X/Y 偏移滑动条,±2000px,持久化)
      卡片 5: 当前倒计时(按键后实时显示)

    ─────────────────────────────────────────────────────────────────
    数据流(自上而下)
    ─────────────────────────────────────────────────────────────────
      UI (QDoubleSpinBox / QSlider / ScreenSelectButton / CyberToggleSwitch)
        ↓ valueChanged / clicked
      CdAssistPage._on_*_changed
        ↓
      CdAssistService (单例,纯逻辑)
        ↓ countdown_tick signal
      CdAssistManager → CdAssistOverlay (多屏悬浮窗)
        ↓ update_cells / set_offset
      Win32 透明窗口(屏幕中心 + 偏移)

    ─────────────────────────────────────────────────────────────────
    生命周期
    ─────────────────────────────────────────────────────────────────
      on_enter:
        - 确保 service 已就绪(单例)
        - 确保 manager 已就绪 + refresh_screens
        - 绑定 service.countdown_tick → manager.show/update_cells/hide
        - 绑定 pipeline.cd_assist_triggered → service.start_skill
        - 同步 UI 状态(从 service.get_state)
      on_leave:
        - 保持 service 运行(用户期望按键继续生效)
        - 不再重新绑定(避免重复连接)
      close (via app_shell):
        - 触发 service.shutdown() 卸载钩子

    ─────────────────────────────────────────────────────────────────
    近期变更(增量日志)
    ─────────────────────────────────────────────────────────────────
      v0.5: 加显示位置调节(QSlider + 重置 + JSON 持久化)
      v0.4: 加提醒功能(reminder spin + 闪烁 + 变色)
      v0.3: 加状态预览卡片(原"测试显示"已删除)
      v0.2: 修复 QFrame 导入缺失 / 头部描述加 i18n / 卡片编号规范化
      v0.1: 初版 4 技能 + 屏选择 + 总开关
    """

    page_id = "cd_assist"
    page_title = ""
    page_icon = "nav_triggers"

    def __init__(self) -> None:
        # ── 引用(必须在 super().__init__() 前声明) ──
        self._service: CdAssistService | None = None
        self._manager: CdAssistManager | None = None

        # 4 个 QDoubleSpinBox: 时长 + 提醒
        self._duration_spins: list[QDoubleSpinBox] = []
        self._duration_labels: list[QLabel] = []
        self._reminder_spins: list[QDoubleSpinBox] = []
        self._reminder_labels: list[QLabel] = []

        # 总开关
        self._toggle: CyberToggleSwitch | None = None

        # 屏幕选择(复用 eye_mask_page 的模式)
        self._screen_card: CyberCard | None = None
        self._screen_card_layout: QVBoxLayout | None = None
        self._screen_buttons: dict[int, ScreenSelectButton] = {}
        self._screen_count_label: QLabel | None = None

        # 状态标签(显示 4 个技能的"剩余/总秒数" — 让用户感知到按了 1/2/3/4 正在生效)
        self._status_label: QLabel | None = None

        # 显示位置: X/Y 偏移滑动条 + 数值标签
        self._x_offset_slider: QSlider | None = None
        self._x_value_label: QLabel | None = None
        self._y_offset_slider: QSlider | None = None
        self._y_value_label: QLabel | None = None

        # 热键标签缓存(在 build_content 里 resolve,用于 tip 展示)
        self._hotkey_labels: list[str] = []

        super().__init__()
        self.page_title = self._copy("nav.cd_assist", "CD 辅助显示")

    # ══════════════════════════════════
    #  生命周期
    # ══════════════════════════════════

    def set_app_shell(self, shell):
        """注入 AppShell 引用并连接热键(必须在 AppShell 注入后调用)。"""
        super().set_app_shell(shell)
        self._connect_pipeline()

    def _connect_pipeline(self):
        """订阅 pipeline.cd_assist_triggered → service.start_skill。"""
        try:
            pipeline = self._app_shell.pipeline
            if pipeline and hasattr(pipeline, 'cd_assist_triggered'):
                # 用一个 wrapper 避免重复连接(可能在多次 set_app_shell 调用)
                if not getattr(self, '_pipeline_bound', False):
                    pipeline.cd_assist_triggered.connect(self._on_pipeline_triggered)
                    self._pipeline_bound = True
        except Exception:
            pass

    def _on_pipeline_triggered(self, skill_idx: int) -> None:
        """热键触发的回调 → 转给 service。"""
        if self._service is None:
            self._ensure_service()
        self._service.start_skill(skill_idx)

    def on_enter(self):
        """进入页面:确保 service / manager 就绪,刷新屏幕列表,绑定 service→manager。"""
        self._ensure_service()
        self._ensure_manager()
        self._refresh_screens_ui()
        self._bind_service_to_manager()
        if self._app_shell:
            self._connect_pipeline()
        # 同步 UI
        self._sync_ui_from_state()

    def on_leave(self):
        """离开页面:保持 service 运行(用户期望按键继续生效),只断 pipeline 触发,避免 on_enter 重复连接。"""
        pass

    def _ensure_service(self) -> None:
        """确保 service 就绪(单例)。"""
        if self._service is None:
            self._service = CdAssistService.instance()
        # 启动 QElapsedTimer(用于倒计时推进)
        # service 自己会在 start_skill 时 start()

    def _ensure_manager(self) -> None:
        """确保 manager 就绪。

        重要: CdAssistManager 现在是单例,由 app_shell._start_cd_assist_hook()
        在启动时创建并注入到 service。这里只是**复用**同一个实例,刷新屏幕列表。
        """
        # 复用 app_shell 创建的单例(保证与 service.view 同一个对象)
        self._manager = CdAssistManager.instance()
        self._manager.refresh_screens()
        # 不在这里重置 enabled_screens —— 保留用户的设置 / 上次状态
        # (app_shell 启动时已默认全选,用户切页后也保留)

    def _bind_service_to_manager(self) -> None:
        """service → manager 的信号转发(仅在第一次绑定)。"""
        if self._service is None or self._manager is None:
            return
        if getattr(self, '_service_bound', False):
            return
        self._service.countdown_tick.connect(self._on_service_tick)
        self._service.enabled_changed.connect(self._on_service_enabled_changed)
        self._service.enabled_screens_changed.connect(
            self._on_service_screens_changed
        )
        self._service_bound = True

    # ══════════════════════════════════
    #  service → manager / UI 同步
    # ══════════════════════════════════

    def _on_service_tick(self, payload: dict) -> None:
        """service 每 tick 把 payload 推给 manager(由 manager 决定显隐/更新 cell)。"""
        if self._manager is None:
            return
        if not self._service.is_enabled():
            return
        if not payload:
            # 无任何活动:hide
            self._manager.hide()
        else:
            # 有活动:show + 更新 cell
            self._manager.show(payload)
        # 同步状态文字
        self._update_status_label(payload)

    def _on_service_enabled_changed(self, on: bool) -> None:
        """总开关变化:关闭时 manager 清空 + 同步 UI。"""
        if self._manager is not None:
            if on:
                # 打开时不需要立即 show(等 tick 触发)
                pass
            else:
                self._manager.hide()
                self._manager.clear_cells()
        if self._toggle is not None:
            self._silent_set(self._toggle, "setChecked", on)
        if self._status_label is not None:
            self._status_label.setText("")

    def _on_service_screens_changed(self, indices: list) -> None:
        """service 启用屏幕变化:同步 manager + 同步 UI 屏幕按钮。"""
        if self._manager is not None:
            self._manager.set_enabled_screens(indices)
        enabled_set = set(indices)
        for idx, btn in self._screen_buttons.items():
            self._silent_set(btn, "set_selected", idx in enabled_set)
        self._update_screen_count_label()

    def _update_status_label(self, payload: dict) -> None:
        """更新 4 个技能的当前状态文字(在卡片底部一行)。

        payload 格式 (service 新版发出):
          {"0": {"r": 4.5, "m": True}, ...}

        用户可见文字走 i18n,key 见 cd_assist.status.*。
        """
        if self._status_label is None:
            return
        if not payload:
            self._status_label.setText("")
            return
        # i18n 模板(带占位符 {n} / {sec})
        skill_active_tpl = self._copy(
            "cd_assist.status.skill_active", "技能 {n}: {sec}s"
        )
        skill_idle_tpl = self._copy(
            "cd_assist.status.skill_idle", "技能 {n}: ·"
        )
        parts = []
        for i in range(SKILL_COUNT):
            key = str(i)
            if key in payload:
                v = float(payload[key].get("r", 0))
                if v > 0:
                    parts.append(skill_active_tpl.format(n=i + 1, sec=f"{v:.1f}"))
                else:
                    parts.append(skill_idle_tpl.format(n=i + 1))
        # 装饰分隔符(不影响 i18n)
        sep = self._copy("cd_assist.status.sep", "  ·  ")
        self._status_label.setText(sep.join(parts))

    # ══════════════════════════════════
    #  屏幕选择 UI(复用 eye_mask_page 模式)
    # ══════════════════════════════════

    def _refresh_screens_ui(self):
        """重建屏幕选择卡片的行(应对屏幕热插拔)。"""
        if self._screen_card_layout is None or self._manager is None:
            return

        while self._screen_card_layout.count():
            item = self._screen_card_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._screen_buttons.clear()
        self._build_screen_bulk_row()
        self._build_screen_grid()

    def _build_screen_bulk_row(self) -> None:
        """构造"全选/全不选"快捷按钮行。"""
        if self._screen_card_layout is None:
            return
        row = QHBoxLayout()
        row.setSpacing(self._spacing("sm_md", 12))
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_all = CyberButton(
            self._copy("cd_assist.btn.select_all", "全选"),
            variant="outlined",
        )
        btn_none = CyberButton(
            self._copy("cd_assist.btn.select_none", "全不选"),
            variant="outlined",
        )
        pad_y = self._spacing("xs", 4)
        pad_x = self._spacing("md", 12)
        for b in (btn_all, btn_none):
            self._style(
                b,
                color="accent.primary",
                font_size="sm",
                font_weight="bold",
                padding=(f"{pad_y}px", f"{pad_x}px"),
            )
            b.setMinimumHeight(self._spacing("height.btn_sm", 32))
        btn_all.clicked.connect(self._on_select_all)
        btn_none.clicked.connect(self._on_select_none)
        row.addWidget(btn_all)
        row.addWidget(btn_none)

        self._screen_count_label = QLabel()
        self._style(
            self._screen_count_label,
            color="text.tertiary",
            font_size="sm",
        )
        self._screen_count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self._screen_count_label, stretch=1)

        wrap = QWidget()
        wrap.setLayout(row)
        self._screen_card_layout.addWidget(wrap)
        self._update_screen_count_label()

    def _build_screen_grid(self) -> None:
        """构造屏幕按钮网格(每行 2 列,大按钮便于快速点击)。"""
        if self._screen_card_layout is None or self._manager is None:
            return
        screens = QGuiApplication.screens()
        primary_idx = QGuiApplication.primaryScreen()
        try:
            primary_index = screens.index(primary_idx)
        except ValueError:
            primary_index = 0
        if not screens:
            return

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(self._spacing("sm_md", 12))
        grid.setVerticalSpacing(self._spacing("sm_md", 12))

        cols = 2
        enabled_set = set(self._manager.get_enabled_screens())

        # i18n 模板
        screen_label_tpl = self._copy(
            "cd_assist.screen.label",
            "屏幕 {n}  ·  {w} × {h}{primary}",
        )
        primary_suffix = self._copy(
            "cd_assist.screen.primary_suffix", "  ·  主屏"
        )

        for i, screen in enumerate(screens):
            g = screen.geometry()
            is_primary = (i == primary_index)
            label_text = screen_label_tpl.format(
                n=i + 1,
                w=g.width(),
                h=g.height(),
                primary=(primary_suffix if is_primary else ""),
            )
            btn = ScreenSelectButton(label_text)
            btn.set_selected(i in enabled_set)
            btn.clicked.connect(self._on_screen_button_clicked)
            self._screen_buttons[i] = btn
            row, col = divmod(i, cols)
            grid.addWidget(btn, row, col)

        for col in range(cols):
            grid.setColumnStretch(col, 1)

        self._screen_card_layout.addWidget(grid_widget)

    def _update_screen_count_label(self) -> None:
        if self._screen_count_label is None:
            return
        total = len(self._screen_buttons)
        selected = sum(1 for b in self._screen_buttons.values() if b.is_selected())
        tpl = self._copy(
            "cd_assist.screen.selected_count", "已选 {selected} / {total}"
        )
        self._screen_count_label.setText(
            tpl.format(selected=selected, total=total)
        )

    def _notify_manager_screens(self) -> None:
        if self._manager is None:
            return
        enabled = [idx for idx, b in self._screen_buttons.items() if b.is_selected()]
        self._manager.set_enabled_screens(enabled)
        self._update_screen_count_label()

    def _set_screens_selection(self, predicate) -> None:
        """按 predicate(idx, btn) -> bool 批量设置每个屏幕按钮的选中状态。

        统一「全选/全不选/单按钮切换」三种场景:全选 = lambda i,b: True,
        全不选 = lambda i,b: False,切换 = lambda i,b: not b.is_selected() if i==target else b.is_selected()。
        设置完自动通知 manager + 更新计数标签。
        """
        for idx, btn in self._screen_buttons.items():
            btn.set_selected(bool(predicate(idx, btn)))
        self._notify_manager_screens()

    def _on_screen_button_clicked(self) -> None:
        """单个屏幕按钮点击: 切换自身状态,其他不变。"""
        btn = self.sender()
        if btn is None:
            return
        self._set_screens_selection(lambda i, b: not b.is_selected() if b is btn else b.is_selected())

    def _on_select_all(self) -> None:
        """全选所有屏幕按钮。"""
        self._set_screens_selection(lambda i, b: True)

    def _setup_card_layout(self, layout, *, spacing_key: str = "sm", spacing_default: int = 8) -> None:
        """统一卡片内容布局:16px 四边 + 8/4 间距。

        page 里 5 个卡片重复 6 行 setContentsMargins + 1 行 setSpacing,
        抽到这里避免遗漏和未来漂移。
        """
        m = self._spacing("lg", 16)
        layout.setContentsMargins(m, m, m, m)
        layout.setSpacing(self._spacing(spacing_key, spacing_default))

    def _on_select_none(self) -> None:
        """全不选所有屏幕按钮。"""
        self._set_screens_selection(lambda i, b: False)

    # ══════════════════════════════════
    #  UI 同步 / 回调
    # ══════════════════════════════════

    @staticmethod
    def _silent_set(widget, attr: str, value) -> None:
        """临时屏蔽 widget 的信号,设置值后恢复。

        等价于:
            widget.blockSignals(True)
            widget.<attr>(value)
            widget.blockSignals(False)

        用 try/finally 保证异常时信号也会被恢复(避免永久屏蔽)。
        """
        widget.blockSignals(True)
        try:
            getattr(widget, attr)(value)
        finally:
            widget.blockSignals(False)

    def _sync_ui_from_state(self) -> None:
        """从 service.get_state 同步所有 UI 控件。"""
        if self._service is None:
            return
        state = self._service.get_state()
        # 4 个时长 spinbox
        for i, spin in enumerate(self._duration_spins):
            self._silent_set(spin, "setValue", state["durations"][i])
        # 4 个提醒 spinbox(默认 0 = 关闭)
        for i, spin in enumerate(self._reminder_spins):
            self._silent_set(spin, "setValue", state.get("reminders", [0.0] * SKILL_COUNT)[i])
        # 总开关
        if self._toggle is not None:
            self._silent_set(self._toggle, "setChecked", state["enabled"])
        # 屏
        enabled_set = set(state["enabled_screens"])
        for idx, btn in self._screen_buttons.items():
            self._silent_set(btn, "set_selected", idx in enabled_set)
        # 显示位置偏移(滑动条 + 数值标签)
        if self._x_offset_slider is not None:
            self._silent_set(self._x_offset_slider, "setValue", state.get("x_offset", 0))
        if self._x_value_label is not None:
            self._x_value_label.setText(f"{state.get('x_offset', 0):+d} px")
        if self._y_offset_slider is not None:
            self._silent_set(self._y_offset_slider, "setValue", state.get("y_offset", 0))
        if self._y_value_label is not None:
            self._y_value_label.setText(f"{state.get('y_offset', 0):+d} px")
        self._update_screen_count_label()

    def _on_duration_changed(self, idx: int, spin) -> None:
        """QDoubleSpinBox 变化 → service.set_skill_duration。

        注: 不依赖 self.sender()(PySide6 lambda 调用链中 sender() 经常返回 None),
        而是通过闭包直接捕获 spinbox 引用(规范做法)。
        """
        if self._service is None:
            return
        self._service.set_skill_duration(idx, spin.value())

    def _on_reminder_changed(self, idx: int, spin) -> None:
        """QDoubleSpinBox 变化 → service.set_skill_reminder(0 = 关闭提醒)。"""
        if self._service is None:
            return
        self._service.set_skill_reminder(idx, spin.value())

    def _on_clear_all_durations(self) -> None:
        """『清除所有』按钮回调: 4 个技能的 duration + reminder 全部归零。

        直接 setValue(0.0) 触发 spinbox 的 valueChanged → 走 lambda →
        _on_duration_changed / _on_reminder_changed → service.set_skill_*,
        UI 与 service 状态自动同步。
        """
        for spin in self._duration_spins:
            spin.setValue(0.0)
        for spin in self._reminder_spins:
            spin.setValue(0.0)

    # ══════════════════════════════════
    #  显示位置 - UI 构建 / 回调
    # ══════════════════════════════════

    def _build_offset_row(
        self, parent_layout, label_text: str, on_change
    ) -> tuple[QSlider, QLabel]:
        """构造一行位置偏移控件: [label] [slider] [数值标签]。

        返回 (slider, value_label),供调用方存到 self._x_offset_slider / _x_value_label。
        滑动条灵敏度 1px(singleStep),Page Up/Down 步 10px,带刻度方便定位。
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self._spacing("sm", 8))

        # label(固定宽度,跟技能设置对齐)
        label = QLabel(label_text)
        label.setFixedWidth(self._spacing("height.btn_lg", 44))
        self._style(
            label,
            color="text.secondary",
            font_size="sm",
            font_weight="bold",
        )
        label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        row.addWidget(label)

        # 滑动条(水平,灵敏度 1px,带刻度;用 _NoWheelSlider 禁用滚轮误触)
        slider = _NoWheelSlider(Qt.Orientation.Horizontal)
        slider.setRange(POS_OFFSET_MIN, POS_OFFSET_MAX)
        slider.setSingleStep(1)            # 键盘左右键 1px
        slider.setPageStep(10)             # Page Up/Down 10px
        slider.setTickInterval(500)        # 每 500px 一个刻度(-2000..2000 共 8 段)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setMinimumWidth(self._spacing("height.btn_lg", 44) * 4)
        slider.valueChanged.connect(on_change)
        row.addWidget(slider, stretch=1)

        # 数值标签(只读,显示当前值如 "+123 px" / "-45 px")
        value_label = QLabel("0 px")
        value_label.setMinimumWidth(self._spacing("height.btn_lg", 44) * 2)
        self._style(
            value_label,
            color="text.primary",
            font_size="md",
        )
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(value_label)

        parent_layout.addLayout(row)
        return slider, value_label

    def _make_offset_handler(self, side: str):
        """生成 X/Y 滑动条的回调闭包。

        side: 'x' 或 'y' —— 哪个轴被拖动了,另一个轴从对应 slider 读取。
        """
        def handler(val: int) -> None:
            if self._service is None:
                return
            if side == "x":
                x, y = int(val), (self._y_offset_slider.value() if self._y_offset_slider is not None else 0)
                if self._x_value_label is not None:
                    self._x_value_label.setText(f"{x:+d} px")
            else:
                x, y = (self._x_offset_slider.value() if self._x_offset_slider is not None else 0), int(val)
                if self._y_value_label is not None:
                    self._y_value_label.setText(f"{y:+d} px")
            self._service.set_position_offset(x, y)
        return handler

    def _on_reset_position(self) -> None:
        """重置居中按钮:X/Y 都归零。

        直接 slider.setValue(0) 触发 valueChanged → 调 _make_offset_handler
        → service.set_position_offset → 数值标签自动更新。
        """
        if self._x_offset_slider is not None:
            self._x_offset_slider.setValue(0)
        if self._y_offset_slider is not None:
            self._y_offset_slider.setValue(0)

    def _on_toggle_changed(self, on: bool) -> None:
        """总开关变化 → service.set_enabled。"""
        if self._service is None:
            return
        self._service.set_enabled(on)

    # ══════════════════════════════════
    #  构建 UI
    # ══════════════════════════════════

    def build_content(self) -> QWidget:
        """构建页面内容(PageBase 在初始化时调用)。"""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            self._spacing("lg", 16),
            self._spacing("md", 12),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
        )
        layout.setSpacing(self._spacing("sm_md", 12))
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # ── 标题 ──
        # ★ 用 self._copy 立即解析(不能读 self.page_title,因为 build_content
        #   在 super().__init__() 里被调,此时 self.page_title 还没赋值,会是 "")
        title = QLabel(self._copy("nav.cd_assist", "CD 辅助显示"))
        title.setFont(QFont("Iceberg", self._font_size("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        # ── 描述 ──
        desc = QLabel(
            self._copy(
                "cd_assist.desc",
                "为游戏内 4 个技能键(1/2/3/4)提供屏幕中央的倒计时显示。",
            )
        )
        self._style(
            desc,
            color="text.tertiary",
            font_size="sm",
            padding=("0", "0", "12px", "0"),
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ══════════════════════════════════
        #  卡片 1:总开关
        # ══════════════════════════════════
        toggle_card = CyberCard(
            title=self._copy("cd_assist.card.toggle.title", "全局开关"),
            clickable=False,
        )
        tlayout = toggle_card.content_layout()
        self._setup_card_layout(tlayout)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(self._spacing("sm_md", 12))
        toggle_label = QLabel(
            self._copy("cd_assist.label.enable", "启用 CD 辅助显示")
        )
        self._style(toggle_label, color="text.primary", font_size="md", font_weight="bold")
        toggle_row.addWidget(toggle_label)
        toggle_row.addStretch(1)

        # CyberToggleSwitch 自身没有 i18n 文字(空 label 就够)
        # 初值跟随 service（UI 构建时 service 通常已在 on_enter 先行就绪）；
        # on_enter 的 _sync_ui_from_state 仍会兜底再同步一次
        _init_on = self._service.is_enabled() if self._service is not None else False
        self._toggle = CyberToggleSwitch("", checked=_init_on, on_off=True)
        self._toggle.toggled.connect(self._on_toggle_changed)
        toggle_row.addWidget(self._toggle)
        tlayout.addLayout(toggle_row)

        toggle_tip = QLabel(
            self._copy(
                "cd_assist.card.toggle.tip",
                "关闭后,按键 1/2/3/4 不再触发屏幕中心倒计时。",
            )
        )
        self._style(toggle_tip, color="text.tertiary", font_size="sm")
        toggle_tip.setWordWrap(True)
        tlayout.addWidget(toggle_tip)

        layout.addWidget(toggle_card)

        # ══════════════════════════════════
        #  卡片 2:技能秒数设置
        # ══════════════════════════════════
        duration_card = CyberCard(
            title=self._copy("cd_assist.card.skill.title", "技能秒数设置"),
            clickable=False,
        )
        dlayout = duration_card.content_layout()
        self._setup_card_layout(dlayout, spacing_key="xs", spacing_default=4)

        # ★ 全局快捷键说明合并到 tip(原头部那行挪到这里,符合"头部简洁"原则)
        self._resolve_hotkey_labels()
        # i18n: 单项 hotkey 模板 + 分隔符
        hotkey_item_tpl = self._copy(
            "cd_assist.hotkey.item", "技能 {n}: {key}"
        )
        hotkey_sep = self._copy("cd_assist.hotkey.sep", "  /  ")
        hotkey_text = hotkey_sep.join(
            hotkey_item_tpl.format(n=i + 1, key=lbl)
            for i, lbl in enumerate(self._hotkey_labels)
        )
        # i18n: 整段 tip(用 {hotkeys} 占位符,运行时填入)
        tip = QLabel(
            self._copy(
                "cd_assist.card.skill.tip",
                "为每个技能设置持续秒数(0-300,步长 0.5)。0 = 不参与倒计时(按下仅闪一下 ·)。\n"
                "提醒秒数 = 倒计时剩多少秒时高亮闪烁提醒(0 = 关闭)。\n"
                "全局快捷键: {hotkeys}",
            ).format(hotkeys=hotkey_text)
        )
        self._style(tip, color="text.tertiary", font_size="sm")
        tip.setWordWrap(True)
        dlayout.addWidget(tip)

        # ★ 改为竖排: 每个技能一行(label + spin 紧贴),行间用分隔线分组
        # 之前用 QGridLayout 横排 2 列,技能1的输入框和"技能2"字样只隔 12px,
        # 视觉上无法分辨"技能1的输入框在哪 / 技能2的字样在哪"。
        # 现在: 竖排 + 分隔线,每个技能是一组,组之间一眼能区分。
        for i in range(SKILL_COUNT):
            # 组与组之间: 顶部细线分隔
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setFixedHeight(1)
                sep_color = self._tm.get("alias.border.subtle")
                sep.setStyleSheet(f"background-color: {sep_color}; border: none;")
                dlayout.addSpacing(self._spacing("sm", 8))
                dlayout.addWidget(sep)
                dlayout.addSpacing(self._spacing("sm", 8))

            # 一行: [技能 N] [输入框] [+stretch]
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(self._spacing("sm", 8))  # label ↔ spin 紧贴

            label = QLabel(self._copy("cd_assist.label.skill", "技能 {n}").format(n=i + 1))
            # 固定 label 宽度,4 个对齐成列
            label.setFixedWidth(self._spacing("height.btn_lg", 44))
            self._style(label, color="text.secondary", font_size="sm", font_weight="bold")
            label.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            row.addWidget(label)

            spin = _NoWheelSpinBox()
            spin.setRange(SKILL_DURATION_MIN, SKILL_DURATION_MAX)
            spin.setSingleStep(SKILL_STEP)
            spin.setDecimals(1)
            spin.setSuffix(self._copy("cd_assist.unit.seconds", " 秒"))
            spin.setValue(0.0)
            spin.setMinimumHeight(self._spacing("height.btn_sm", 32))
            spin.setMaximumWidth(self._spacing("height.btn_lg", 44) + 80)  # 不要太宽
            # ★ 样式集中到 _apply_spin_style(以后有 CyberSpinBox mixin 再切换)
            self._apply_spin_style(spin)
            spin.valueChanged.connect(
                lambda _v, idx=i, s=spin: self._on_duration_changed(idx, s)
            )
            self._duration_spins.append(spin)
            self._duration_labels.append(label)
            row.addWidget(spin)

            # ★ 新增: 提醒输入框(与时长 spin 紧贴,组内同 row)
            # 显示 "关" 当值为 0(specialValueText),用户不用猜 0 啥意思
            reminder_label = QLabel(self._copy("cd_assist.label.reminder", "提醒"))
            self._style(reminder_label, color="text.tertiary", font_size="xs")
            reminder_label.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            )
            self._reminder_labels.append(reminder_label)
            row.addSpacing(self._spacing("sm", 8))
            row.addWidget(reminder_label)

            reminder_spin = _NoWheelSpinBox()
            reminder_spin.setRange(SKILL_REMINDER_MIN, SKILL_REMINDER_MAX)
            reminder_spin.setSingleStep(SKILL_STEP)
            reminder_spin.setDecimals(1)
            reminder_spin.setSuffix(self._copy("cd_assist.unit.seconds", " 秒"))
            reminder_spin.setSpecialValueText(
                self._copy("cd_assist.label.off", "关")
            )  # value=0 时显示"关"而不是"0.0 秒"
            reminder_spin.setValue(0.0)
            reminder_spin.setMinimumHeight(self._spacing("height.btn_sm", 32))
            reminder_spin.setMaximumWidth(self._spacing("height.btn_lg", 44) + 60)
            # ★ 用 warning 橙色边框暗示"提醒"语义(border_token 切到 warning)
            self._apply_spin_style(reminder_spin, border_token="alias.semantic.warning")
            reminder_spin.valueChanged.connect(
                lambda _v, idx=i, s=reminder_spin: self._on_reminder_changed(idx, s)
            )
            self._reminder_spins.append(reminder_spin)
            row.addWidget(reminder_spin)

            # 右侧留白,让 spin 不会撑满整行(视觉更透气)
            row.addStretch()

            dlayout.addLayout(row)

        # ── 清除所有按钮(归零 4 个技能的 duration + reminder) ──
        dlayout.addSpacing(self._spacing("sm", 8))
        clear_row = QHBoxLayout()
        clear_row.setContentsMargins(0, 0, 0, 0)
        clear_row.addStretch(1)  # 按钮右对齐
        clear_btn = CyberButton(
            self._copy("cd_assist.btn.clear_all", "清除所有"),
            variant="outlined",
        )
        clear_btn.setMinimumHeight(self._spacing("height.btn_sm", 32))
        clear_btn.clicked.connect(self._on_clear_all_durations)
        clear_row.addWidget(clear_btn)
        dlayout.addLayout(clear_row)

        layout.addWidget(duration_card)

        # ══════════════════════════════════
        #  卡片 3:启用屏幕
        # ══════════════════════════════════
        screen_card = CyberCard(
            title=self._copy("cd_assist.card.screen.title", "启用屏幕"),
            clickable=False,
        )
        self._screen_card_layout = screen_card.content_layout()
        self._setup_card_layout(self._screen_card_layout)
        layout.addWidget(screen_card)

        # ══════════════════════════════════
        #  卡片 4:显示位置(X/Y 偏移)
        # ══════════════════════════════════
        pos_card = CyberCard(
            title=self._copy("cd_assist.card.position.title", "显示位置"),
            clickable=False,
        )
        playout = pos_card.content_layout()
        self._setup_card_layout(playout)

        pos_tip = QLabel(
            self._copy(
                "cd_assist.card.position.tip",
                "调整倒计时在屏幕中的位置(相对屏幕中心的偏移像素)。\n"
                "+X = 向右,-X = 向左,+Y = 向下,-Y = 向上。0 = 屏幕中心。\n"
                "调节立即生效,自动保存。",
            )
        )
        self._style(pos_tip, color="text.tertiary", font_size="sm")
        pos_tip.setWordWrap(True)
        playout.addWidget(pos_tip)

        # X 偏移 行: [X 偏移] [slider] [数值]
        self._x_offset_slider, self._x_value_label = self._build_offset_row(
            playout,
            self._copy("cd_assist.label.x_offset", "X 偏移"),
            self._make_offset_handler("x"),
        )
        # Y 偏移 行: [Y 偏移] [slider] [数值]
        self._y_offset_slider, self._y_value_label = self._build_offset_row(
            playout,
            self._copy("cd_assist.label.y_offset", "Y 偏移"),
            self._make_offset_handler("y"),
        )

        # 重置居中按钮(右对齐)
        pos_reset_row = QHBoxLayout()
        pos_reset_row.setContentsMargins(0, 0, 0, 0)
        pos_reset_row.addStretch(1)
        pos_reset_btn = CyberButton(
            self._copy("cd_assist.btn.reset_center", "重置居中"),
            variant="outlined",
        )
        pos_reset_btn.setMinimumHeight(self._spacing("height.btn_sm", 32))
        pos_reset_btn.clicked.connect(self._on_reset_position)
        pos_reset_row.addWidget(pos_reset_btn)
        playout.addLayout(pos_reset_row)

        layout.addWidget(pos_card)

        # ══════════════════════════════════
        #  卡片 5:状态预览(按键后实时显示当前倒计时)
        # ══════════════════════════════════
        status_card = CyberCard(
            title=self._copy("cd_assist.card.status.title", "当前倒计时"),
            clickable=False,
        )
        slayout = status_card.content_layout()
        self._setup_card_layout(slayout)
        status_tip = QLabel(
            self._copy(
                "cd_assist.card.status.tip",
                "按下 1/2/3/4 键后,这里会显示各技能的剩余秒数(屏幕中心也会同步显示)。",
            )
        )
        self._style(status_tip, color="text.tertiary", font_size="sm")
        status_tip.setWordWrap(True)
        slayout.addWidget(status_tip)
        self._status_label = QLabel("")
        self._style(
            self._status_label,
            color="accent.primary",
            font_size="md",
            font_weight="bold",
        )
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setMinimumHeight(self._spacing("height.btn_lg", 44))
        slayout.addWidget(self._status_label)
        layout.addWidget(status_card)

        return content

    # ══════════════════════════════════
    #  样式辅助 — 集中 setStyleSheet,降低重复
    # ══════════════════════════════════

    def _apply_spin_style(
        self,
        spin: QDoubleSpinBox,
        border_token: str = "alias.border.subtle",
    ) -> None:
        """集中 QDoubleSpinBox 的样式(暂用 setStyleSheet,因为没有 CyberSpinBox mixin)。

        所有颜色走 token,不硬编码。
        背景:沉浸黑色模式时覆写为纯黑(走 PageBase 的
        ``_resolve_immersive_bg_str`` helper);
        边框 / 文字 / 选中色保持原 token,不接入。
        border_token 默认 subtle,提醒输入框可切到 "alias.semantic.warning"(橙色)。

        TODO: 等 core/widgets/cyber_spin_box.py(继承 QDoubleSpinBox + Mixin)完成后
              切换到 CyberSpinBox,本方法可删除。
        """
        text = self._tm.get("alias.text.primary")
        # 背景:沉浸黑色模式时覆写为纯黑
        bg = self._resolve_immersive_bg_str("alias.bg.raised", 1.0)
        border = self._tm.get(border_token)
        accent = self._tm.get("alias.accent.primary")
        spin.setStyleSheet(
            f"QDoubleSpinBox {{"
            f"  color: {text};"
            f"  background: {bg};"
            f"  border: 1px solid {border};"
            f"  padding: 2px 8px;"
            f"  selection-background-color: {accent};"
            f"}}"
        )

    def cyber_refresh_immersive_style(self) -> None:
        """沉浸模式 / 颜色预设变化时由 AppShell 调用。

        重新应用时长 / 提醒 QDoubleSpinBox 的 QSS,以应用最新沉浸底色。
        提醒输入框用 warning 橙色边框(与创建时保持一致)。
        """
        for spin in self._duration_spins:
            self._apply_spin_style(spin)  # 默认 border_token = alias.border.subtle
        for spin in self._reminder_spins:
            self._apply_spin_style(spin, border_token="alias.semantic.warning")

    def _resolve_hotkey_labels(self) -> None:
        """从 hotkey_config 拉 4 个 cd_N 的快捷键标签(用户在 hotkeys 页改了立即生效)。"""
        try:
            from core.hotkey_config import load_hotkeys
            hotkeys = load_hotkeys()
        except Exception:
            hotkeys = {}
        out = []
        for i in range(SKILL_COUNT):
            key = f"cd_{i + 1}"
            raw = hotkeys.get(key, str(i + 1))
            parts = [p.capitalize() for p in raw.split("+") if p]
            out.append("+".join(parts) if parts else str(i + 1))
        self._hotkey_labels = out
