"""
[L2] TriggersPage — 辅助触发器配置页面

依赖: widgets/, core.trigger_config (纯数据层)
职责: 增删改辅助触发器(鼠标/键盘钩子 + 动作链),即时生效并热重载

数据层: core/trigger_config.py
引擎:   core.trigger_manager.py

遵循 ui-framework-design.md 规范:
  - Token 驱动(颜色/字号/间距/文案全部从 Token 获取)
  - Copy Token 驱动(所有用户可见文字通过 _copy() 获取)
  - 继承原生控件 + 最小化自绘
  - 使用 core/widgets/ 下的赛博风格组件

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.trigger_config, core.trigger_manager, PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接)
           任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止直接读写 triggers.json → 走 trigger_config.get() / save()
- ✗ 禁止在 Page 内安装 keyboard 钩子 → 调 trigger_manager.reload()
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space
- ✗ 禁止用户可见文案硬编码 → 必须 _copy() 取自 tokens

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5。
"""

from __future__ import annotations

import sys
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.pages.base_page import PageBase
from core.widgets.line_edit import CyberLineEdit
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.combo_box import CyberComboBox
from core.widgets.hotkey_edit import HotkeyEdit
from core.widgets.toggle_switch import CyberToggleSwitch
from core.widgets.trigger_status_bar import TriggerStatusBar
from core.widgets.crosshair_picker import CrosshairPicker
from core.tokens.manager import TokenManager
from core.trigger_config import (
    load_triggers, save_triggers,
    create_blank_trigger, create_blank_action,
    TRIGGER_INPUT_TYPES,
    MOUSE_BUTTONS, MOUSE_BUTTON_VALUES,
    ACTION_TYPES, ACTION_TYPE_VALUES,
    MOUSE_CLICK_BUTTONS, MOUSE_CLICK_VALUES,
    format_trigger_summary,
)



# ============================================================
#  UI 层日志（与 trigger_manager.py 统一格式）
# ============================================================

def _ui_log(msg: str, tag: str = "UI"):
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[TRIGGER][{tag}] {ts} | {msg}", file=sys.stderr, flush=True)


# 注意: 原 _TriggerStatusBar / _CrosshairPicker 内嵌类已迁移到 core/widgets/
# 原因: §6.5 禁止 Page 内嵌自定义控件


# ============================================================
#  TriggersPage
# ============================================================

class TriggersPage(PageBase):
    """辅助触发器配置页面。

    列出所有 trigger 任务(如开机自启动、OCR 校时、热键响应),允许启停、编辑。
    实际触发逻辑在 core/trigger_manager.py,本页只负责 UI 与数据展示。
    """
    page_id = "triggers"
    page_title = ""
    page_icon = "nav_triggers"

    def __init__(self):
        self._trigger_card_widgets: list[dict] = []

        # ScrLK 快捷总控（build_content 中创建控件）
        self._scrlk_gate_switch: CyberToggleSwitch | None = None
        self._scrlk_state_label: QLabel | None = None
        self._scrlk_gate_bound = False   # 引擎信号是否已连接（重建内容后需重连）

        super().__init__()
        self.page_title = self._copy("nav.triggers", "Triggers")

    # ════════════════════════════════════
    #  主内容构建
    # ════════════════════════════════════

    def build_content(self) -> QWidget:
        """构建辅助触发器配置页(触发器卡片列表 + 启停/编辑/删除)。"""
        _ui_log("build_content()", "UI_INIT")
        _sp = self._spacing
        _fs = self._font_size
        _co = self._color
        _cp = self._copy

        # 内容可能在 on_enter 中被整体重建：重置信号绑定标志，
        # 新控件创建后需重新连接引擎信号
        self._scrlk_gate_bound = False

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(_sp("lg", 20), _sp("sm", 8), _sp("lg", 20), _sp("lg", 20))
        layout.setSpacing(_sp("xs", 4))

        # ── 标题 ──
        title = QLabel(_cp("triggers.title", "Trigger Config"))
        title.setFont(QFont("Iceberg", _fs("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        desc = QLabel(
            _cp("triggers.desc",
                "Detect specified input then auto-execute actions (key / click / move)")
        )
        self._style(
            desc,
            color="text.tertiary",
            font_size="sm",
            padding=("0", "0", "12px", "0"),
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ── ScrLK 快捷总控行 ──
        layout.addLayout(self._build_scrlk_gate_row())
        layout.addSpacing(_sp("sm", 8))

        # ── 卡片容器 ──
        self._cards_container = QWidget()
        self._style(self._cards_container, transparent=True)
        cards_layout = QVBoxLayout(self._cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(_sp("sm", 10))
        layout.addWidget(self._cards_container)

        # ── 加载已有触发器 ──
        triggers_data = load_triggers()
        if not triggers_data:
            triggers_data = [create_blank_trigger()]

        for t in triggers_data:
            cw = self._build_trigger_card(t, cards_layout)
            cards_layout.addWidget(cw["card"])
            self._trigger_card_widgets.append(cw)

        # ── 新增按钮 ──
        btn_add = CyberButton(text=_cp("triggers.btn_add", "+ Add Trigger"), variant="ghost")
        btn_add.clicked.connect(lambda: self._on_add_trigger_card(cards_layout))
        layout.addWidget(btn_add)

        layout.addStretch()

        # 尝试绑定 ScrLK 总控（若此时引擎尚未注入，on_enter 会再试）
        self._ensure_scrlk_gate_bound()
        return container

    # ════════════════════════════════════
    #  ScrLK 快捷总控
    # ════════════════════════════════════

    def _build_scrlk_gate_row(self) -> QHBoxLayout:
        """构建 ScrLK 快捷总控行：[ON/OFF 开关] 标题+说明 … [实时灯态]。"""
        _sp = self._spacing

        row = QHBoxLayout()
        row.setSpacing(_sp("sm", 10))

        # ── ON/OFF 切角开关 ──
        self._scrlk_gate_switch = CyberToggleSwitch("", checked=False, on_off=True)
        row.addWidget(self._scrlk_gate_switch)

        # ── 标题 + 说明（纵向） ──
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        gate_title = QLabel(self._copy("triggers.scrlk_gate_title", "ScrLK 快捷总控"))
        self._style(gate_title, color="text.primary", font_size="sm_md",
                    font_weight="bold")
        text_col.addWidget(gate_title)

        gate_desc = QLabel(self._copy(
            "triggers.scrlk_gate_desc",
            "启用后，你已开启的触发器仅在 ScrLK（Scroll Lock）灯亮时生效，灯灭时全部暂停",
        ))
        self._style(gate_desc, color="text.tertiary", font_size="xs")
        gate_desc.setWordWrap(True)
        text_col.addWidget(gate_desc)

        row.addLayout(text_col, stretch=1)

        # ── 实时灯态标签（自然高度，与开关在布局内垂直居中对齐） ──
        self._scrlk_state_label = QLabel("")
        row.addWidget(self._scrlk_state_label)

        return row

    def _ensure_scrlk_gate_bound(self):
        """幂等绑定引擎信号并同步一次 UI。

        build_content 时 AppShell 可能尚未注入（页面先于外壳装配），
        此时静默跳过；on_enter 时再试，引擎就绪后即可连上。
        """
        mgr = self._find_trigger_manager()
        if mgr is None or self._scrlk_gate_switch is None:
            return
        if not self._scrlk_gate_bound:
            self._scrlk_gate_switch.toggled.connect(
                self._on_scrlk_gate_switch_toggled
            )
            mgr.scrlk_gate_changed.connect(self._on_scrlk_gate_changed)
            mgr.scrlk_state_changed.connect(self._on_scrlk_light_changed)
            self._scrlk_gate_bound = True
            _ui_log("scrlk gate signals bound", "UI_GATE")
        self._sync_scrlk_gate_ui()

    def _on_scrlk_gate_switch_toggled(self, checked: bool):
        """用户在本页拨动总控 → 引擎（持久化 + 装/卸钩子 + 广播同步另一页面）。"""
        mgr = self._find_trigger_manager()
        if mgr is None:
            _ui_log("gate toggle but TriggerManager NOT FOUND", "UI_GATE_WARN")
            return
        mgr.set_scrlk_gate(checked)
        self._sync_scrlk_gate_ui()

    def _on_scrlk_gate_changed(self, enabled: bool):
        """引擎门控变化（可能来自功能开关页）→ 静默回写本页开关。"""
        sw = self._scrlk_gate_switch
        if sw is not None:
            sw.blockSignals(True)
            sw.setChecked(bool(enabled))
            sw.blockSignals(False)
        self._sync_scrlk_gate_ui()

    def _on_scrlk_light_changed(self, _on: bool):
        """ScrLK 物理灯态变化（钩子线程信号，主线程执行）→ 刷新灯态标签。"""
        self._sync_scrlk_gate_ui()

    def _sync_scrlk_gate_ui(self):
        """按引擎当前状态刷新开关位置与灯态标签文案/颜色。"""
        if self._scrlk_gate_switch is None or self._scrlk_state_label is None:
            return
        mgr = self._find_trigger_manager()
        if mgr is None:
            return

        # 开关位置以引擎为唯一数据源（静默回写，避免回环）
        self._scrlk_gate_switch.blockSignals(True)
        self._scrlk_gate_switch.setChecked(mgr.scrlk_gate_enabled)
        self._scrlk_gate_switch.blockSignals(False)

        if not mgr.scrlk_gate_enabled:
            text = self._copy("triggers.scrlk_state_disabled", "总控未启用")
            color = "text.tertiary"
        elif mgr.scrlk_light_on:
            text = self._copy("triggers.scrlk_state_on", "ScrLK 灯亮 · 生效中")
            color = "brand.green"
        else:
            text = self._copy("triggers.scrlk_state_off", "ScrLK 灯灭 · 已暂停")
            color = "brand.red"
        self._style(self._scrlk_state_label, color=color, font_size="sm_md",
                    font_weight="bold")
        self._scrlk_state_label.setText(text)

    # ════════════════════════════════════
    #  单个触发器卡片
    # ════════════════════════════════════

    def _build_trigger_card(self, trigger_data: dict, parent_layout) -> dict:
        """构建一个完整的触发器卡片：名称 + 触发输入 + 动作列表 + 状态栏 + 删除。

        Args:
            trigger_data: 触发器配置字典。
            parent_layout: 卡片要添加到的父布局。

        Returns:
            包含所有子控件引用的 dict，供信号连接和数据读取使用。
        """
        _h = 32  # 统一行高
        _sp = self._spacing
        _fs = self._font_size
        _co = self._color
        _cp = self._copy

        card_name = trigger_data.get("name") or _cp("triggers.untitled", "Untitled")
        card = CyberCard(title=card_name)
        cl = card.content_layout()
        cl.setContentsMargins(_sp("md", 16), _sp("lg_xl", 28), _sp("md", 16), _sp("md", 16))
        cl.setSpacing(_sp("sm", 10))

        # ────────────────────────────────
        #  第 1 行：名称
        # ────────────────────────────────
        name_row = QHBoxLayout()
        name_row.setSpacing(8)

        name_label = QLabel(_cp("triggers.label_name", "Name:"))
        # 72px 容纳最长中文标签「触发器名称:」(5字+冒号,sm 字号),
        # 与下方 type_label 对齐;40px 旧值会截断成「触发器」
        name_label.setFixedWidth(72)
        name_label.setFixedHeight(_h)
        name_label.setStyleSheet(
            f"color: {_co('text.primary')}; "
            f"font-size: {_fs('sm', 12)}px;"
        )

        name_input = CyberLineEdit(placeholder=_cp("triggers.ph_name", "e.g. Quick Pickup"))
        name_input.setText(trigger_data.get("name", ""))
        name_input.setFixedHeight(_h)

        name_row.addWidget(name_label)
        name_row.addWidget(name_input, 1)
        cl.addLayout(name_row)

        # ────────────────────────────────
        #  第 2 行：触发器类型 + 输入值 + 延迟
        # ────────────────────────────────
        trigger_row = QHBoxLayout()
        trigger_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        trigger_row.setSpacing(8)

        type_label = QLabel(_cp("triggers.label_trigger", "Trigger:"))
        # 与上方 name_label 同宽(72px),两行标签左对齐
        type_label.setFixedWidth(72)
        type_label.setFixedHeight(_h)
        type_label.setStyleSheet(name_label.styleSheet())

        ti = trigger_data.get("trigger_input", {})
        current_ti_type = ti.get("type", "mouse")

        # 触发器类型下拉（mouse / keyboard）
        trigger_type_combo = CyberComboBox()
        trigger_type_combo.addItems(TRIGGER_INPUT_TYPES)
        tidx = (TRIGGER_INPUT_TYPES.index(current_ti_type)
                if current_ti_type in TRIGGER_INPUT_TYPES else 0)
        trigger_type_combo.setCurrentIndex(tidx)
        trigger_type_combo.setFixedHeight(_h)

        # 鼠标按钮选择（mouse 模式显示）
        mouse_btn_combo = CyberComboBox()
        for _btn_val, _btn_lbl in MOUSE_BUTTONS:
            mouse_btn_combo.addItem(_btn_lbl)
        current_btn = ti.get("button", "right")
        bidx = (MOUSE_BUTTON_VALUES.index(current_btn)
                if current_btn in MOUSE_BUTTON_VALUES else 1)
        mouse_btn_combo.setCurrentIndex(bidx)
        mouse_btn_combo.setFixedHeight(_h)

        # 键盘按键捕获（keyboard 模式显示）
        kb_key_input = HotkeyEdit(initial=ti.get("key", ""))
        kb_key_input.setFixedHeight(_h)

        # 延迟毫秒数
        delay_label = QLabel(_cp("triggers.label_delay", "Delay:"))
        delay_label.setFixedHeight(_h)
        delay_label.setStyleSheet(name_label.styleSheet())

        delay_spin = QSpinBox()
        delay_spin.setRange(0, 5000)
        delay_spin.setSingleStep(5)
        delay_spin.setValue(trigger_data.get("delay_ms", 10))
        delay_spin.setSuffix(" ms")
        delay_spin.setFixedWidth(100)
        delay_spin.setFixedHeight(_h)
        self._apply_form_style(delay_spin)

        # 组装触发行（先全部 addWidget，再设置显隐）
        trigger_row.addWidget(type_label)
        trigger_row.addWidget(trigger_type_combo)
        trigger_row.addWidget(mouse_btn_combo)
        trigger_row.addWidget(kb_key_input)
        trigger_row.addStretch()
        trigger_row.addWidget(delay_label)
        trigger_row.addWidget(delay_spin)
        cl.addLayout(trigger_row)

        # 显隐联动（必须在 addWidget 之后）
        mouse_btn_combo.setVisible(current_ti_type != "keyboard")
        kb_key_input.setVisible(current_ti_type == "keyboard")

        def _on_trigger_type_changed(index):
            is_kb = TRIGGER_INPUT_TYPES[index] == "keyboard"
            mouse_btn_combo.setVisible(not is_kb)
            kb_key_input.setVisible(is_kb)

        trigger_type_combo.currentIndexChanged.connect(_on_trigger_type_changed)

        # ────────────────────────────────
        #  动作列表区域
        # ────────────────────────────────
        actions_label = QLabel(_cp("triggers.label_actions", "Actions:"))
        actions_label.setStyleSheet(name_label.styleSheet())
        cl.addWidget(actions_label)

        actions_container = QWidget()
        actions_container.setStyleSheet("background-color: transparent;")
        actions_layout = QVBoxLayout(actions_container)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(self._spacing("sm", 8))
        cl.addWidget(actions_container)

        action_widgets_list: list[dict] = []
        actions_data = trigger_data.get("actions", [])
        if not actions_data:
            actions_data = [create_blank_action()]

        for act in actions_data:
            aw = self._build_action_row(act, actions_layout)
            action_widgets_list.append(aw)

        # + 添加动作按钮
        btn_add_act = CyberButton(text=_cp("triggers.btn_add_action", "+ Add Action"), variant="ghost")

        def _make_add_action():
            blank = create_blank_action()
            aw = self._build_action_row(blank, actions_layout)
            action_widgets_list.append(aw)
            self._wire_action_changes(aw, on_change_fn)
            aw["btn_del_act"].clicked.connect(
                lambda checked, a=aw, c=cw: self._on_delete_action_row(a, c)
            )
            btn_add_act.setParent(None)
            actions_layout.addWidget(btn_add_act)

        btn_add_act.clicked.connect(_make_add_action)
        actions_layout.addWidget(btn_add_act)

        # ────────────────────────────────
        #  状态栏（开关 + 摘要）
        # ────────────────────────────────
        status_bar = TriggerStatusBar()
        status_bar.set_state(
            bool(trigger_data.get("enabled", False)),
            trigger_data.get("name", ""),
            format_trigger_summary(trigger_data),
        )
        status_bar.toggled.connect(lambda checked: self._on_status_toggle(status_bar, checked))
        cl.addWidget(status_bar)

        # ── 删除按钮（红色 danger 样式）──
        del_row = QHBoxLayout()
        del_row.addStretch()
        btn_delete = CyberButton(
            text=_cp("triggers.btn_delete", "删除触发器"), variant="semantic.danger"
        )
        del_row.addWidget(btn_delete)
        cl.addLayout(del_row)

        # ────────────────────────────────
        #  变化回调（即时保存 + 更新摘要）
        # ────────────────────────────────
        def on_change_fn():
            """单卡片内编辑后的即时回调:同步标题 + 刷新状态栏摘要 + 触发数据保存。"""
            # 同步卡片标题
            new_name = name_input.text().strip()
            title_text = new_name or _cp("triggers.untitled", "Untitled")
            if card._title_bar and card._title_bar.text() != title_text:
                card._title_bar.setText(title_text)
            # 更新状态栏摘要
            self._refresh_status_bar(
                status_bar, name_input, trigger_type_combo,
                mouse_btn_combo, kb_key_input, delay_spin,
                action_widgets_list,
            )
            self._save_all_triggers()

        # 连接名称和触发器字段信号
        name_input.textChanged.connect(on_change_fn)
        trigger_type_combo.currentIndexChanged.connect(on_change_fn)
        mouse_btn_combo.currentIndexChanged.connect(on_change_fn)
        kb_key_input.captured.connect(on_change_fn)
        delay_spin.valueChanged.connect(on_change_fn)

        # 连接已有动作行的信号
        for aw in action_widgets_list:
            self._wire_action_changes(aw, on_change_fn)

        # ── 构建返回值字典 ──
        cw = {
            "card": card,
            "name_input": name_input,
            "trigger_type_combo": trigger_type_combo,
            "mouse_btn_combo": mouse_btn_combo,
            "kb_key_input": kb_key_input,
            "delay_spin": delay_spin,
            "status_bar": status_bar,
            "action_widgets": action_widgets_list,
            "btn_delete": btn_delete,
            "actions_container": actions_container,
            "btn_add_action": btn_add_act,
        }

        # 连接动作行删除按钮（cw 定义后才可引用）
        for aw in action_widgets_list:
            aw["btn_del_act"].clicked.connect(
                lambda checked, a=aw, c=cw: self._on_delete_action_row(a, c)
            )

        btn_delete.clicked.connect(lambda: self._on_delete_trigger_card(card))

        return cw

    # ════════════════════════════════════
    #  单个动作行
    # ════════════════════════════════════

    def _build_action_row(self, action_data: dict, parent_layout) -> dict:
        """构建单个响应动作行：类型下拉 + 值输入 + 删除按钮。

        根据动作类型自动切换值输入控件的显隐：
          - key         → HotkeyEdit（快捷键捕获）
          - mouse_click → QComboBox（鼠标按钮选择）
          - mouse_move  → CyberLineEdit（坐标输入）

        Args:
            action_data: 动作配置字典。
            parent_layout: 行要添加到的父布局。

        Returns:
            包含该行所有控件引用的 dict。
        """
        _h = 30  # 动作行高度略小于主表单
        _co = self._color
        _fs = self._font_size
        _cp = self._copy

        row = QHBoxLayout()
        row.setSpacing(self._spacing("sm", 8))

        # ── 动作类型下拉 ──
        type_combo = CyberComboBox()
        for _atype_val, _atype_lbl in ACTION_TYPES:
            type_combo.addItem(_atype_lbl)
        current_atype = action_data.get("type", "key")
        aidx = (ACTION_TYPE_VALUES.index(current_atype)
                if current_atype in ACTION_TYPE_VALUES else 0)
        type_combo.setCurrentIndex(aidx)
        type_combo.setFixedHeight(_h)

        # ── 按键值输入（HotkeyEdit）──
        key_value_input = HotkeyEdit(initial=action_data.get("value", ""))
        key_value_input.setFixedHeight(_h)
        key_value_input.setFixedWidth(140)

        # ── 鼠标点击值选择 ──
        click_value_combo = CyberComboBox()
        for _click_val, _click_lbl in MOUSE_CLICK_BUTTONS:
            click_value_combo.addItem(_click_lbl)
        current_click = action_data.get("value", "")
        cidx = (MOUSE_CLICK_VALUES.index(current_click)
                if current_click in MOUSE_CLICK_VALUES else 0)
        click_value_combo.setCurrentIndex(cidx)
        click_value_combo.setFixedHeight(_h)
        click_value_combo.setFixedWidth(100)

        # ── 鼠标移动坐标（只读显示 + 十字线选点按钮）──
        move_coord_label = QLabel(action_data.get("value", "") or "---")
        move_coord_label.setFixedHeight(_h)
        move_coord_label.setMinimumWidth(80)
        # 样式抽到 _apply_move_coord_style,便于沉浸黑色模式切换时重新调用
        self._apply_move_coord_style(move_coord_label)
        move_coord_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_pick_pos = CyberButton(text=_cp("triggers.btn_pick", "Pick"), variant="ghost")
        btn_pick_pos.setFixedHeight(_h)

        # ── 删除按钮（红色 danger 样式）──
        btn_del_act = CyberButton(text="✕", variant="semantic.danger")
        btn_del_act.setFixedSize(32, _h)

        # 先全部加入布局（确保 setVisible 在 addWidget 之后生效）
        row.addWidget(type_combo)
        row.addWidget(key_value_input)
        row.addWidget(click_value_combo)
        row.addWidget(move_coord_label)
        row.addWidget(btn_pick_pos)
        row.addWidget(btn_del_act)

        # 设置初始显隐（必须在 addWidget 之后）
        atype = ACTION_TYPE_VALUES[aidx] if aidx < len(ACTION_TYPE_VALUES) else "key"
        key_value_input.setVisible(atype == "key")
        click_value_combo.setVisible(atype == "mouse_click")
        move_coord_label.setVisible(atype == "mouse_move")
        btn_pick_pos.setVisible(atype == "mouse_move")

        def _on_action_type_changed(idx):
            t = ACTION_TYPE_VALUES[idx] if idx < len(ACTION_TYPE_VALUES) else "key"
            key_value_input.setVisible(t == "key")
            click_value_combo.setVisible(t == "mouse_click")
            move_coord_label.setVisible(t == "mouse_move")
            btn_pick_pos.setVisible(t == "mouse_move")

        type_combo.currentIndexChanged.connect(_on_action_type_changed)

        # 十字线选点回调
        def _on_pick_position(x: int, y: int):
            coord_text = f"{x}, {y}"
            move_coord_label.setText(coord_text)
            self._save_all_triggers()  # 即时保存

        btn_pick_pos.clicked.connect(self._open_crosshair_picker(_on_pick_position))

        parent_layout.addLayout(row)

        return {
            "type_combo": type_combo,
            "key_value_input": key_value_input,
            "click_value_combo": click_value_combo,
            "move_coord_label": move_coord_label,
            "btn_pick_pos": btn_pick_pos,
            "btn_del_act": btn_del_act,
        }

    # ════════════════════════════════════
    #  样式工具
    # ════════════════════════════════════

    def _apply_form_style(self, widget):
        """对 QSpinBox 应用统一的深色表单样式。

        沉浸黑色模式时,背景色覆写为纯黑(走 PageBase 的
        ``_resolve_immersive_bg_str`` helper,与 CyberWidgetMixin 一致);
        边框 / 文字色保持原 token,不接入。
        """
        _tm = TokenManager.instance()
        # 背景:沉浸黑色模式时覆写为纯黑
        base_bg = self._resolve_immersive_bg_str("bg.base", 1.0)
        base_border = _tm.get_qcolor("border.subtle").name()
        focus_border = _tm.get_qcolor("border.focus").name()
        text_color = _tm.get_qcolor("text.primary").name()

        base_ss = (
            f"background-color: {base_bg}; "
            f"color: {text_color}; "
            f"border: 1px solid {base_border}; "
            f"border-radius: 4px; "
            f"padding: 4px 8px;"
        )
        focus_ss = f"border: 1px solid {focus_border};"

        if isinstance(widget, QSpinBox):
            widget.setStyleSheet(
                f"QSpinBox {{ {base_ss} }} "
                f"QSpinBox:focus {{{focus_ss}}}"
            )

    def _apply_move_coord_style(self, label: QLabel) -> None:
        """对鼠标移动坐标 QLabel 应用样式(沉浸黑色模式时背景覆写为纯黑)。

        从原 _build_action_row 内联 QSS 抽出,便于沉浸模式切换时重新调用。
        """
        # 背景:沉浸黑色模式时覆写为纯黑
        bg = self._resolve_immersive_bg_str("bg.base", 1.0)
        text = self._tm.get_qcolor("text.primary").name()
        border = self._tm.get_qcolor("border.subtle").name()
        label.setStyleSheet(
            f"background-color: {bg}; color: {text}; "
            f"border: 1px solid {border}; border-radius: 4px; "
            f"padding: 4px 8px;"
        )

    def cyber_refresh_immersive_style(self) -> None:
        """沉浸模式 / 颜色预设变化时由 AppShell 调用。

        重新应用 QSpinBox 和 move_coord_label 的 QSS,以应用最新沉浸底色。
        """
        for cw in self._trigger_card_widgets:
            spin = cw.get("delay_spin")
            if isinstance(spin, QSpinBox):
                self._apply_form_style(spin)
            for aw in cw.get("action_widgets", []):
                label = aw.get("move_coord_label")
                if label is not None:
                    self._apply_move_coord_style(label)

    @staticmethod
    def _wire_action_changes(aw: dict, fn):
        """连接动作行所有变化信号到统一回调。"""
        aw["key_value_input"].captured.connect(fn)
        aw["click_value_combo"].currentIndexChanged.connect(fn)
        # mouse_move 的坐标通过十字线选点器设置，无需 textChanged 信号

    def _open_crosshair_picker(self, on_picked):
        """返回一个回调函数，点击后打开全屏十字线选点器。

        Args:
            on_picked: 坐标选中后的回调，签名为 (x, y) -> None

        Returns:
            可连接到 clicked 信号的函数。
        """
        if not hasattr(self, "_crosshair_picker"):
            self._crosshair_picker = CrosshairPicker()

        def _open():
            # 断开旧连接
            try:
                self._crosshair_picker.position_picked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._crosshair_picker.position_picked.connect(on_picked)
            self._crosshair_picker.show_overlay()

        return _open

    def _find_trigger_manager(self):
        """在组件链上查找 TriggerManager 实例。"""
        # 1) 直接用 AppShell 引用（最可靠）
        if self._app_shell is not None:
            mgr = getattr(self._app_shell, '_trigger_manager', None)
            _ui_log(f"find_mgr() | _app_shell={type(self._app_shell).__name__} | "
                    f"_trigger_manager={'FOUND' if mgr else 'NONE'} | "
                    f"running={mgr.is_running if mgr else 'N/A'}", "UI_MGR_DBG")
            if mgr is not None:
                return mgr
        else:
            _ui_log("find_mgr() | _app_shell is None", "UI_MGR_DBG")

        # 2) 回退：遍历 parent() 链
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, '_trigger_manager') and widget._trigger_manager is not None:
                return widget._trigger_manager
            widget = widget.parent()

        _ui_log("find_mgr() | NOT FOUND", "UI_MGR_WARN")
        return None

    # ════════════════════════════════════
    #  事件处理
    # ════════════════════════════════════

    def _on_add_trigger_card(self, parent_layout):
        """添加一张空白触发器卡片并立即保存(用户开箱即用)。"""
        blank = create_blank_trigger()
        cw = self._build_trigger_card(blank, parent_layout)
        parent_layout.addWidget(cw["card"])
        self._trigger_card_widgets.append(cw)
        self._save_all_triggers()

    def _on_delete_trigger_card(self, card: CyberCard):
        reply = QMessageBox.question(
            self,
            self._copy("common.confirm", "Confirm"),
            self._copy("triggers.delete_confirm", "Delete this trigger?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for i, cw in enumerate(self._trigger_card_widgets):
            if cw["card"] is card:
                self._trigger_card_widgets.pop(i)
                break

        card.hide()
        card.setParent(None)
        card.deleteLater()
        self._save_all_triggers()

    def _on_delete_action_row(self, action_widget: dict, parent_cw: dict):
        aw = action_widget
        if aw in parent_cw["action_widgets"]:
            parent_cw["action_widgets"].remove(aw)

        for ctrl in [
            aw["type_combo"], aw["key_value_input"],
            aw["click_value_combo"], aw["move_coord_label"],
            aw["btn_pick_pos"], aw["btn_del_act"],
        ]:
            if ctrl is not None:
                ctrl.hide()
                ctrl.setParent(None)
                ctrl.deleteLater()

        self._save_all_triggers()

    def _on_status_toggle(self, bar: TriggerStatusBar, checked: bool):
        """启停某条触发器:更新状态栏文字 + 立即保存。"""
        _ui_log(f"status_toggle() | trigger='{bar._name}' | "
                f"enabled={checked}", "UI_TOGGLE")
        # ★ 即时保存，对端页面（TogglesPage）在 on_enter 时从磁盘读取最新状态。
        self._save_all_triggers()

    # ════════════════════════════════════
    #  页面生命周期
    # ════════════════════════════════════

    def on_enter(self):
        """页面进入时从磁盘重新加载触发器数据，同步状态栏。

        确保在开关页面修改后，返回本页时状态栏与磁盘数据一致。
        """
        current_data = load_triggers()

        # 数量不一致 → 完全重建（由 build_content 处理，最简单的方式是重载整个页面）
        if len(current_data) != len(self._trigger_card_widgets):
            # 触发重建：移除旧内容，重新构建
            container = self.layout().itemAt(0).widget()
            if container:
                old_layout = container.layout()
                if old_layout:
                    while old_layout.count():
                        item = old_layout.takeAt(0)
                    container.setParent(None)
                    container.deleteLater()
            # 重建内容
            new_content = self.build_content()
            self.layout().addWidget(new_content)
            return

        # 数量一致 → 只同步 enabled 状态
        for i, cw in enumerate(self._trigger_card_widgets):
            bar = cw.get("status_bar")
            if bar is None:
                continue
            disk_enabled = bool(current_data[i].get("enabled", False))
            if bar._enabled != disk_enabled:
                name_input = cw.get("name_input")
                name = name_input.text().strip() if name_input else ""
                summary = self._build_summary_from_card(cw)
                bar.blockSignals(True)
                bar.set_state(disk_enabled, name, summary)
                bar.blockSignals(False)

        # ScrLK 总控：首次进页时引擎才就绪，这里补连信号并同步灯态
        self._ensure_scrlk_gate_bound()

    def on_leave(self):
        """页面离开时确保数据已持久化。"""
        self._save_all_triggers()
        _ui_log("on_leave() → 已强制保存触发器状态", "UI_LIFECYCLE")

    def _build_summary_from_card(self, cw: dict) -> str:
        """从卡片控件字典读取当前值，生成触发器摘要文本。"""
        ttc = cw.get("trigger_type_combo")
        mbc = cw.get("mouse_btn_combo")
        kbi = cw.get("kb_key_input")
        dsp = cw.get("delay_spin")
        awl = cw.get("action_widgets", [])

        ti_type = "mouse"
        if ttc is not None:
            idx = ttc.currentIndex()
            ti_type = TRIGGER_INPUT_TYPES[idx] if idx < len(TRIGGER_INPUT_TYPES) else "mouse"

        trigger_input = {"type": ti_type}
        if ti_type == "mouse" and mbc is not None:
            midx = mbc.currentIndex()
            trigger_input["button"] = (
                MOUSE_BUTTON_VALUES[midx] if midx < len(MOUSE_BUTTON_VALUES) else "right"
            )
        elif ti_type == "keyboard" and kbi is not None:
            trigger_input["key"] = kbi.value

        delay = int(dsp.value()) if dsp else 0

        actions = []
        for aw in awl:
            tc = aw.get("type_combo")
            if tc is None:
                continue
            aidx = tc.currentIndex()
            atype = ACTION_TYPES[aidx] if aidx < len(ACTION_TYPES) else "key"
            action = {"type": atype}
            if atype in ("key", "hold"):
                val_edit = aw.get("value_edit")
                action["value"] = int(val_edit.text()) if val_edit and val_edit.text().isdigit() else 1
            elif atype == "mouse_click":
                mcc = aw.get("mouse_click_combo")
                if mcc is not None:
                    mcidx = mcc.currentIndex()
                    action["button"] = (
                        MOUSE_CLICK_VALUES[mcidx] if mcidx < len(MOUSE_CLICK_VALUES) else "left"
                    )
            actions.append(action)

        return format_trigger_summary({
            "name": "",
            "enabled": True,
            "trigger_input": trigger_input,
            "delay_ms": delay,
            "actions": actions,
        })

    # ════════════════════════════════════
    #  数据持久化
    # ════════════════════════════════════

    def _save_all_triggers(self):
        """从所有卡片控件读取当前值，写入 JSON 文件。"""
        triggers = []

        for cw in self._trigger_card_widgets:
            # 名称
            name_input = cw.get("name_input")
            name = name_input.text().strip() if name_input else ""

            # 触发输入
            ttc = cw.get("trigger_type_combo")
            mbc = cw.get("mouse_btn_combo")
            kbi = cw.get("kb_key_input")
            dsp = cw.get("delay_spin")

            ti_type = "mouse"
            if ttc is not None:
                idx = ttc.currentIndex()
                ti_type = TRIGGER_INPUT_TYPES[idx] if idx < len(TRIGGER_INPUT_TYPES) else "mouse"

            trigger_input = {"type": ti_type}
            if ti_type == "mouse":
                if mbc is not None:
                    midx = mbc.currentIndex()
                    trigger_input["button"] = (
                        MOUSE_BUTTON_VALUES[midx]
                        if midx < len(MOUSE_BUTTON_VALUES) else "right"
                    )
            else:
                if kbi is not None:
                    trigger_input["key"] = kbi.value

            # 延迟
            delay_ms = int(dsp.value()) if dsp else 10

            # 动作列表
            actions = []
            for aw in cw.get("action_widgets", []):
                tc = aw.get("type_combo")
                if tc is None:
                    continue
                aidx = tc.currentIndex()
                atype = ACTION_TYPE_VALUES[aidx] if aidx < len(ACTION_TYPE_VALUES) else "key"

                value = ""
                if atype == "key":
                    kvi = aw.get("key_value_input")
                    value = kvi.value if kvi else ""
                elif atype == "mouse_click":
                    cvc = aw.get("click_value_combo")
                    if cvc is not None:
                        cidx = cvc.currentIndex()
                        value = (
                            MOUSE_CLICK_VALUES[cidx]
                            if cidx < len(MOUSE_CLICK_VALUES) else ""
                        )
                elif atype == "mouse_move":
                    mvi = aw.get("move_coord_label")
                    value = mvi.text().strip() if mvi else ""

                actions.append({"type": atype, "value": value})

            data = {
                "name": name,
                "enabled": cw["status_bar"]._enabled,
                "trigger_input": trigger_input,
                "delay_ms": delay_ms,
                "actions": actions,
            }
            triggers.append(data)

        save_triggers(triggers)

        # 通知引擎热重载（从父组件链获取 TriggerManager 引用）
        mgr = self._find_trigger_manager()
        if mgr is not None:
            mgr.reload(triggers)
            enabled_count = sum(1 for t in triggers if t.get("enabled"))
            _ui_log(f"save() | saved={len(triggers)} triggers | "
                    f"enabled={enabled_count} | reload OK", "UI_SAVE")
        else:
            _ui_log("save() | saved but TriggerManager NOT FOUND (reload skipped!)", "UI_SAVE_WARN")

    # ════════════════════════════════════
    #  状态栏刷新
    # ════════════════════════════════════

    @staticmethod
    def _refresh_status_bar(bar, name_input, trigger_type_combo,
                             mouse_btn_combo, kb_key_input, delay_spin,
                             action_widgets_list):
        """根据当前控件值更新状态栏的摘要文本。"""
        name = name_input.text().strip() if name_input else ""

        # 构造临时 trigger_data 用于 format_trigger_summary
        ti_type = "mouse"
        if trigger_type_combo is not None:
            idx = trigger_type_combo.currentIndex()
            ti_type = TRIGGER_INPUT_TYPES[idx] if idx < len(TRIGGER_INPUT_TYPES) else "mouse"

        ti = {"type": ti_type}
        if ti_type == "mouse" and mouse_btn_combo is not None:
            midx = mouse_btn_combo.currentIndex()
            ti["button"] = (
                MOUSE_BUTTON_VALUES[midx]
                if midx < len(MOUSE_BUTTON_VALUES) else "right"
            )
        elif ti_type == "keyboard" and kb_key_input is not None:
            ti["key"] = kb_key_input.value

        delay = int(delay_spin.value()) if delay_spin else 0

        actions = []
        for aw in action_widgets_list:
            tc = aw.get("type_combo")
            if tc is None:
                continue
            aidx = tc.currentIndex()
            atype = ACTION_TYPE_VALUES[aidx] if aidx < len(ACTION_TYPE_VALUES) else "key"

            value = ""
            if atype == "key":
                kvi = aw.get("key_value_input")
                value = kvi.value if kvi else ""
            elif atype == "mouse_click":
                cvc = aw.get("click_value_combo")
                if cvc is not None:
                    cidx = cvc.currentIndex()
                    value = (
                        MOUSE_CLICK_VALUES[cidx]
                        if cidx < len(MOUSE_CLICK_VALUES) else ""
                    )
            elif atype == "mouse_move":
                mvi = aw.get("move_coord_label")
                value = mvi.text().strip() if mvi else ""

            actions.append({"type": atype, "value": value})

        bar.set_state(
            bar._enabled,
            name,
            format_trigger_summary({
                "trigger_input": ti,
                "delay_ms": delay,
                "actions": actions,
            }),
        )
