"""
[L-Page] TogglesPage — 功能开关 + 快捷键配置页面。

依赖: PySide6 + data/feature_toggles.json + data/hotkeys.json + data/triggers.json
用途: 管理应用功能模块的开启/关闭状态 + 全局快捷键绑定 + 辅助触发器开关。

功能:
  - 功能开关（核心功能 / 界面行为）
  - 辅助触发器启用/禁用（同步自 triggers.json）
  - 快捷键绑定（框选截图 / 全屏截图）
  - 保存修改到 JSON 文件
  - 支持恢复默认值

数据源:
  - data/feature_toggles.json （功能开关）
  - data/triggers.json       （辅助触发器）
  - data/hotkeys.json        （快捷键）


## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.hotkey_config, core.trigger_config, data/(读), PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接)
           任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- 禁止 setStyleSheet(f-string) -> 必须用 Token 或继承自 CyberWidget
- 禁止重写 paintEvent -> 视觉交给 Widget
- 禁止直接读写 JSON -> 走 config_service / hotkey_config.save()
- 禁止快捷键硬编码 -> 必须从 DEFAULT_HOTKEYS 动态生成
- 禁止硬编码颜色 / 尺寸 -> 必须 token / space
- 禁止用户可见文案硬编码 -> 必须 _copy() 取自 tokens

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5,别走捷径。
"""
from __future__ import annotations

import json
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from core.pages.base_page import PageBase
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.toggle_switch import CyberToggleSwitch
from core.widgets.hotkey_capture_edit import HotkeyCaptureEdit
from core.tokens.manager import TokenManager
from core.trigger_config import (
    load_triggers, save_triggers,
    format_trigger_summary,
)


# ── 功能开关定义 ──
# 格式: (token_key, 默认值, 所属分组)
_TOGGLE_DEFS = [
    # ── 核心功能 ──
    ("check_status", True, "core"),
    ("query_parts",  True, "core"),
]

_GROUP_NAMES = {
    "core": "toggles.group_core",
    "ui":   "toggles.group_ui",
}

_DEFAULT_VALUES = {k: v for k, v, _ in _TOGGLE_DEFS}

# ── 快捷键定义 ──
# 动态从 DEFAULT_HOTKEYS 生成（保证 hotkey_config.py 和 UI 一致）
# 格式: (action_key, token_label, 默认值)
# token_label 形如 "hotkeys.label_select",对应 cyberpunk.yaml 中 copy.hotkeys.label_*
def _build_hotkey_defs() -> list[tuple[str, str, str]]:
    from core.hotkey_config import DEFAULT_HOTKEYS
    defs = []
    for action, default_hk in DEFAULT_HOTKEYS.items():
        token_key = f"hotkeys.label_{action}"
        defs.append((action, token_key, default_hk))
    return defs

_HOTKEY_DEFS = _build_hotkey_defs()

# 走 RegisterHotKey 全局注册、需要占用诊断的功能（cd_1..cd_4 走低级钩子，不独占按键）
from core.hotkey_manager import REGISTERED_ACTIONS as _REGISTERED_ACTIONS


# 注意: 原 _HotkeyCaptureEdit 内嵌类已迁移到 core/widgets/hotkey_capture_edit.py
# 原因: §6.5 禁止 Page 内嵌自定义控件


class TogglesPage(PageBase):
    """功能开关 + 快捷键配置页面。"""

    page_id = "toggles"
    page_title = ""
    page_icon = "nav_toggles"

    def __init__(self):
        from core.paths import user_data_dir
        self._toggles_path = user_data_dir() / 'feature_toggles.json'
        self._toggles_data: dict[str, bool] = {}
        self._checkboxes: dict[str, QCheckBox] = {}

        # 快捷键数据
        self._hotkeys_data: dict[str, str] = {}
        self._hotkey_edits: dict[str, HotkeyCaptureEdit] = {}
        # 各快捷键启用/禁用状态（用户可单独关闭某个快捷键）
        self._hotkey_enabled: dict[str, bool] = {}
        self._hotkey_toggles: dict[str, CyberToggleSwitch] = {}
        # 快捷键占用诊断：状态灯 {action: QLabel}、红色诊断条、重新检测按钮
        self._hotkey_status_dots: dict[str, QLabel] = {}
        self._hk_warn_frame: Optional[QFrame] = None
        self._hk_warn_label: Optional[QLabel] = None
        self._recheck_btn: Optional[CyberButton] = None

        # 辅助触发器数据
        self._triggers_data: list[dict] = []
        self._trigger_checkboxes: list[tuple[CyberToggleSwitch, int]] = []  # (toggle_switch, index_in_list)
        self._triggers_layout: Optional[QVBoxLayout] = None  # 触发器卡片的内容布局引用

        # ScrLK 快捷总控（与触发器页共享同一个 TriggerManager 信号源）
        self._scrlk_gate_switch: Optional[CyberToggleSwitch] = None
        self._scrlk_state_label: Optional[QLabel] = None
        self._scrlk_gate_bound = False

        # ★ 必须在 PageBase.__init__ 之前加载数据，
        #   因为 PageBase 内部会调用 build_content() 构建UI
        self._load_toggles()
        self._load_hotkeys()
        self._load_triggers()

        PageBase.__init__(self)

        self.page_title = self._copy("nav.toggles", "功能开关")

    # ════════════════════════════════════
    #  数据加载/保存
    # ════════════════════════════════════

    def _load_toggles(self) -> None:
        """从 JSON 文件加载功能开关。"""
        try:
            if self._toggles_path.exists():
                raw = json.loads(self._toggles_path.read_text(encoding="utf-8"))
                self._toggles_data = {
                    k: bool(v) for k, v in raw.items()
                    if isinstance(v, (bool, int))
                }
            else:
                self._toggles_data = dict(_DEFAULT_VALUES)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[TogglesPage] 加载失败，使用默认值: {e}", flush=True)
            self._toggles_data = dict(_DEFAULT_VALUES)

    def _save_toggles(self) -> bool:
        """保存当前设置到 JSON 文件。"""
        try:
            current = {}
            for key, cb in self._checkboxes.items():
                current[key] = cb.isChecked()

            # 同步内存中的开关状态（供 update_feature_toggles 使用）
            self._toggles_data = current

            self._toggles_path.write_text(
                json.dumps(current, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError as e:
            print(f"[TogglesPage] 保存失败: {e}", flush=True)
            return False

    def _load_hotkeys(self) -> None:
        """加载快捷键配置（含按键字符串 + 各快捷键启用状态）。"""
        try:
            from core.hotkey_config import (
                load_hotkeys, load_hotkey_enabled, DEFAULT_HOTKEYS,
            )
            raw = load_hotkeys()
            # 只取本页关心的 action（按 _HOTKEY_DEFS 过滤）
            self._hotkeys_data = {
                k: raw.get(k, DEFAULT_HOTKEYS.get(k, ""))
                for k, _, _ in _HOTKEY_DEFS
            }
            self._hotkey_enabled = load_hotkey_enabled()
        except Exception as e:
            print(f"[TogglesPage] 加载热键失败: {e}", flush=True)
            self._hotkeys_data = {k: d for k, _, d in _HOTKEY_DEFS}
            self._hotkey_enabled = {k: True for k, _, _ in _HOTKEY_DEFS}

    def _save_hotkeys(self) -> bool:
        """保存快捷键配置。"""
        try:
            from core.hotkey_config import load_hotkeys, save_hotkeys, DEFAULT_HOTKEYS

            # 合并：保留用户其他自定义项，更新当前编辑的
            all_hks = load_hotkeys()
            for key, edit in self._hotkey_edits.items():
                all_hks[key] = edit.value

            return save_hotkeys(all_hks)
        except Exception as e:
            print(f"[TogglesPage] 保存热键失败: {e}", flush=True)
            return False

    def _load_triggers(self) -> None:
        """从 triggers.json 加载辅助触发器列表。"""
        try:
            self._triggers_data = load_triggers()
        except Exception as e:
            print(f"[TogglesPage] 加载触发器失败: {e}", flush=True)
            self._triggers_data = []

    def _save_triggers(self) -> bool:
        """将触发器启用/禁用状态保存回 triggers.json。

        只更新 enabled 字段，不修改其他配置。
        """
        try:
            print(f"[TogglesPage] _save_triggers: 开关数={len(self._trigger_checkboxes)}", flush=True)
            for sw, idx in self._trigger_checkboxes:
                if idx < len(self._triggers_data):
                    self._triggers_data[idx]["enabled"] = sw.isChecked()
                    print(f"  [{idx}] {self._triggers_data[idx].get('name')}: enabled={sw.isChecked()}", flush=True)
            ok = save_triggers(self._triggers_data)
            print(f"[TogglesPage] _save_triggers: 保存{'成功' if ok else '失败'}", flush=True)
            return ok
        except Exception as e:
            print(f"[TogglesPage] 保存触发器失败: {e}", flush=True)
            return False

    # ════════════════════════════════════
    #  即时保存 + 通知引擎
    # ════════════════════════════════════

    def _apply_toggles(self) -> None:
        """保存功能开关并通知管线服务。"""
        if not self._save_toggles():
            return
        try:
            shell = self._get_shell()
            if shell and shell.pipeline:
                shell.pipeline.update_feature_toggles(self._toggles_data)
        except Exception:
            pass

    def _apply_hotkeys(self) -> None:
        """保存快捷键并通知管线重注册，随后刷新占用诊断状态。"""
        if not self._save_hotkeys():
            return
        try:
            shell = self._get_shell()
            if shell and shell.pipeline:
                shell.pipeline.reregister_hotkeys()
        except Exception:
            pass
        # 以重注册的真实结果刷新状态灯（被占用/冲突即使保存也如实标红）
        self._refresh_hotkey_status()

    def _save_hotkey_enabled(self) -> bool:
        """保存各快捷键启用状态到 hotkeys.json。"""
        try:
            from core.hotkey_config import save_hotkey_enabled
            return save_hotkey_enabled(self._hotkey_enabled)
        except Exception as e:
            print(f"[TogglesPage] 保存快捷键启用状态失败: {e}", flush=True)
            return False

    def _apply_hotkey_enabled(self) -> None:
        """保存启用状态并让运行时生效。

        - RegisterHotKey 路线（select/fullscreen/eye_mask/bring_to_front）：
          重注册热键，被禁用的 action 不会被注册。
        - 低层钩子路线（cd_1..cd_4）：重建 vk→skill 映射，被禁用的技能
          从映射中移除，按键不再触发倒计时。
        """
        if not self._save_hotkey_enabled():
            return
        # 1. 全局注册类快捷键：重注册（内部会跳过 disabled 的 action）
        try:
            shell = self._get_shell()
            if shell and shell.pipeline:
                shell.pipeline.reregister_hotkeys()
        except Exception:
            pass
        # 2. CD 辅助快捷键：重建钩子映射
        try:
            from core.services.cd_assist_service import CdAssistService
            CdAssistService.instance().rebuild_hotkey_mapping()
        except Exception:
            pass
        # 3. 刷新状态灯（disabled 的项会显示灰色「已禁用」）
        self._refresh_hotkey_status()

    def _apply_triggers(self) -> None:
        """保存触发器状态并通知引擎热重载。"""
        if not self._save_triggers():
            return
        try:
            shell = self._get_shell()
            if shell and hasattr(shell, 'trigger_manager') and shell.trigger_manager:
                shell.trigger_manager.reload()
                print("[TogglesPage] 触发器引擎已重载", flush=True)
        except Exception:
            pass

    # ════════════════════════════════════
    #  UI 构建
    # ════════════════════════════════════

    def build_content(self) -> QWidget:
        """构建功能开关页(运行时启用/禁用各功能模块的开关卡片)。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            self._spacing("lg", 20), self._spacing("sm", 8),
            self._spacing("lg", 20), self._spacing("lg", 20)
        )
        layout.setSpacing(self._spacing("xs", 4))

        # ── 标题 ──
        title = QLabel(self._copy("toggles.title", "功能控制面板"))
        title.setFont(QFont("Iceberg", self._font_size("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        desc = QLabel(
            self._copy("toggles.desc",
                       "开启或关闭各项功能模块，修改快捷键后需重启生效")
        )
        self._style(
            desc,
            color="text.tertiary",
            font_size="sm",
            padding=("0", "0", "12px", "0"),
        )
        layout.addWidget(desc)

        # ════════════════════
        #  第一区：功能开关
        # ════════════════════
        groups: dict[str, list[tuple]] = {}
        for key, default_val, group_id in _TOGGLE_DEFS:
            if group_id not in groups:
                groups[group_id] = []
            groups[group_id].append((key, default_val))

        for group_id, toggle_list in groups.items():
            group_label_key = _GROUP_NAMES.get(group_id, group_id)
            group_name = self._copy(group_label_key, group_id)

            card = CyberCard(title=group_name)
            card_layout = card.content_layout()
            card_layout.setContentsMargins(
                self._spacing("md", 16),
                self._spacing("lg_xl", 28),
                self._spacing("md", 16),
                self._spacing("md", 16)
            )
            card_layout.setSpacing(self._spacing("sm", 10))

            for key, _default_val in toggle_list:
                current_val = self._toggles_data.get(key, _default_val)
                row = self._build_toggle_row(key, current_val)
                card_layout.addLayout(row)

            layout.addWidget(card)

        # ════════════════════
        #  第二区：辅助触发器开关
        # ════════════════════
        self._build_triggers_card(layout)

        # ════════════════════
        #  第二点五区：CD 辅助显示 总开关
        # ════════════════════
        self._build_cd_assist_card(layout)

        # ════════════════════
        #  第三区：快捷键绑定
        # ════════════════════
        hk_card = CyberCard(title=self._copy("hotkeys.card_binding", "快捷键绑定"))
        hk_layout = hk_card.content_layout()
        hk_layout.setContentsMargins(
            self._spacing("md", 16),
            self._spacing("lg_xl", 28),
            self._spacing("md", 16),
            self._spacing("md", 16)
        )
        hk_layout.setSpacing(self._spacing("sm", 10))

        # ── 检测条：说明 + 「重新检测」按钮 ──
        check_row = QHBoxLayout()
        check_row.setSpacing(self._spacing("sm", 8))
        check_hint = QLabel(self._copy("hotkeys.check_hint", "检测快捷键是否被其他程序占用"))
        self._style(check_hint, color="text.tertiary", font_size="xs")
        check_row.addWidget(check_hint, stretch=1)

        self._recheck_btn = CyberButton(
            text=self._copy("hotkeys.btn_recheck", "重新检测"), variant="ghost")
        self._recheck_btn.setFixedWidth(88)
        self._recheck_btn.clicked.connect(self._on_recheck_clicked)
        check_row.addWidget(self._recheck_btn)
        hk_layout.addLayout(check_row)

        for action_key, label_token, default_val in _HOTKEY_DEFS:
            row = self._build_hotkey_row(action_key, label_token, default_val)
            hk_layout.addLayout(row)

        layout.addWidget(hk_card)

        # ── 占用/异常诊断条（默认隐藏，检测到异常项时显示）──
        self._hk_warn_frame = QFrame()

        def _warn_frame_qss():
            c = TokenManager.instance().get_qcolor("brand.red")
            return (
                f"QFrame {{"
                f"  background-color: rgba({c.red()}, {c.green()}, {c.blue()}, 0.06);"
                f"  border: 1px solid rgba({c.red()}, {c.green()}, {c.blue()}, 0.25);"
                f"  border-radius: {self._spacing('corner.xs', 4)}px;"
                f"  padding: {self._spacing('spacing.sm', 8)}px;"
                f"}}"
            )
        self._style(self._hk_warn_frame, raw=_warn_frame_qss)
        warn_layout = QHBoxLayout(self._hk_warn_frame)
        warn_layout.setContentsMargins(12, 8, 12, 8)

        warn_icon = QLabel("!")
        self._style(warn_icon, color="brand.red", font_size="md", font_weight="bold")
        warn_icon.setFixedWidth(20)
        warn_layout.addWidget(warn_icon)

        self._hk_warn_label = QLabel("")
        self._style(self._hk_warn_label, color="brand.red", font_size="xs")
        self._hk_warn_label.setWordWrap(True)
        warn_layout.addWidget(self._hk_warn_label, stretch=1)

        self._hk_warn_frame.hide()
        layout.addWidget(self._hk_warn_frame)

        # ── 提示 ──
        tip_frame = QFrame()
        # 复杂 QSS(rgba 透明)走 raw 通道;callable 形式支持主题切换重放
        def _tip_frame_qss():
            a = TokenManager.instance().get_qcolor("accent.primary")
            return (
                f"QFrame {{"
                f"  background-color: rgba({a.red()}, {a.green()}, {a.blue()}, 0.06);"
                f"  border: 1px solid rgba({a.red()}, {a.green()}, {a.blue()}, 0.2);"
                f"  border-radius: 4px;"
                f"  padding: {self._spacing('spacing.sm', 8)}px;"
                f"}}"
            )
        self._style(tip_frame, raw=_tip_frame_qss)
        tip_layout = QHBoxLayout(tip_frame)
        tip_layout.setContentsMargins(12, 8, 12, 8)

        tip_icon = QLabel("!")
        self._style(tip_icon, color="accent.primary", font_size="md", font_weight="bold")
        tip_icon.setFixedWidth(20)
        tip_layout.addWidget(tip_icon)

        tip_text = QLabel(
            self._copy("hotkeys.tip",
                       "提示：修改快捷键后请确认不与其他软件冲突，部分修改需要重启应用生效。"
                       "支持的修饰键：Ctrl / Alt / Shift / Win")
        )
        self._style(tip_text, color="alias.text.tertiary", font_size="xs")
        tip_text.setWordWrap(True)
        tip_layout.addWidget(tip_text, stretch=1)

        layout.addWidget(tip_frame)
        layout.addStretch()

        return container

    def _build_toggle_row(self, key: str, current_val: bool) -> QHBoxLayout:
        """构建一行功能开关。"""
        row = QHBoxLayout()
        row.setSpacing(8)

        label_text = self._copy(f"toggles.toggle_{key}", key)
        cb = QCheckBox(label_text)
        cb.setChecked(bool(current_val))
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        # 复杂 QSS(多选择器)走 raw 通道;lambda 形式支持主题切换重放
        self._style(
            cb,
            raw=lambda: (
                f"QCheckBox {{"
                f"  color: {self._color('text.primary')};"
                f"  font-size: {self._font_size('sm_md', 13)}px;"
                f"  spacing: 8px;"
                f"}}"
                f"QCheckBox::indicator {{"
                f"  width: 18px;"
                f"  height: 18px;"
                f"  border: 1.5px solid {self._color('border.emphasis')};"
                f"  border-radius: 4px;"
                f"  background: transparent;"
                f"}}"
                f"QCheckBox::indicator:checked {{"
                f"  background-color: {self._color('accent.secondary')};"
                f"  border-color: {self._color('accent.secondary')};"
                f"}}"
                f"QCheckBox::indicator:hover {{"
                f"  border-color: {self._color('accent.secondary')};"
                f"}}"
            ),
        )

        # ── 状态点（先创建，再在信号中引用）──
        status_dot = QLabel("●" if current_val else "○")
        status_dot.setStyleSheet(
            f"color: {self._color('brand.green') if current_val else self._color('neutral.dark')}; "
            f"font-size: {self._font_size('micro', 10)}px;"
        )
        status_dot.setFixedWidth(20)

        cb.stateChanged.connect(lambda state, dot=status_dot, k=key: (
            dot.setText("●" if state == Qt.CheckState.Checked.value else "○"),
            dot.setStyleSheet(
                f"color: {self._color('brand.green') if state == Qt.CheckState.Checked.value else self._color('neutral.dark')}; "
                f"font-size: {self._font_size('micro', 10)}px;"
            ),
            self._toggles_data.__setitem__(k, state == Qt.CheckState.Checked.value),
            self._apply_toggles(),
        )[-1])

        self._checkboxes[key] = cb
        row.addWidget(cb, stretch=1)
        row.addWidget(status_dot)

        return row

    def _build_hotkey_row(self, action_key: str, label_token: str, default_val: str) -> QHBoxLayout:
        """构建一行快捷键绑定。"""
        row = QHBoxLayout()
        row.setSpacing(12)

        name_lbl = QLabel(self._copy(label_token, action_key))
        name_lbl.setStyleSheet(
            f"color: {self._color('text.primary')}; "
            f"font-size: {self._font_size('sm_md', 13)}px;"
        )
        name_lbl.setMinimumWidth(140)
        row.addWidget(name_lbl)

        current_val = self._hotkeys_data.get(action_key, default_val)
        key_edit = HotkeyCaptureEdit(initial=current_val)
        key_edit.captured.connect(lambda val, k=action_key: self._on_hotkey_captured(k, val))
        # ★ 捕获模式时暂停全局热键，避免按键被热键拦截
        key_edit.capture_started.connect(self._pause_hotkeys)
        key_edit.capture_stopped.connect(self._resume_hotkeys)
        self._hotkey_edits[action_key] = key_edit
        row.addWidget(key_edit)

        # 状态灯：仅全局注册键需要占用诊断；cd_1..cd_4 走低级钩子不独占按键
        if action_key in _REGISTERED_ACTIONS:
            dot = QLabel("●")
            self._style(dot, color="neutral.dark", font_size="micro")
            dot.setFixedWidth(20)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setToolTip(self._copy("hotkeys.status_unknown", "尚未检测"))
            self._hotkey_status_dots[action_key] = dot
            row.addWidget(dot)

        reset_btn = CyberButton(text=self._copy("common.reset", "重置"), variant="ghost")
        reset_btn.setFixedWidth(50)
        reset_btn.clicked.connect(lambda checked, k=action_key, dv=default_val: self._reset_hotkey(k, dv))
        row.addWidget(reset_btn)

        # ── 启用/禁用开关（ON/OFF 模式）──
        current_enabled = self._hotkey_enabled.get(action_key, True)
        enable_switch = CyberToggleSwitch("", checked=current_enabled, on_off=True)
        enable_switch.toggled.connect(
            lambda checked, k=action_key: self._on_hotkey_enabled_toggled(k, checked)
        )
        self._hotkey_toggles[action_key] = enable_switch
        row.addWidget(enable_switch)

        row.addStretch()
        return row

    def _on_hotkey_captured(self, action_key: str, value: str):
        """热键捕获完成回调 — 即时保存。"""
        print(f"[TogglesPage] 热键 {action_key} → {value}", flush=True)
        self._hotkeys_data[action_key] = value
        self._apply_hotkeys()

    def _reset_hotkey(self, action_key: str, default_val: str):
        """重置单个热键为默认值 — 即时保存。"""
        edit = self._hotkey_edits.get(action_key)
        if edit:
            edit.value = default_val
        self._hotkeys_data[action_key] = default_val
        self._apply_hotkeys()

    def _on_hotkey_enabled_toggled(self, action_key: str, checked: bool) -> None:
        """用户切换某快捷键的启用/禁用开关 — 即时保存 + 生效。"""
        print(f"[TogglesPage] 快捷键 {action_key} 启用状态 → {checked}", flush=True)
        self._hotkey_enabled[action_key] = checked
        self._apply_hotkey_enabled()

    # ════════════════════════════════════
    #  快捷键占用诊断（状态灯 / 重新检测）
    # ════════════════════════════════════

    def _action_display_name(self, action: str) -> str:
        """快捷键功能的中文名（与卡片各行 label 同源文案）。"""
        return self._copy(f"hotkeys.label_{action}", action)

    @staticmethod
    def _format_hotkey(hk_str: str) -> str:
        """ctrl+h → CTRL + H 展示形式（复用捕获输入框的格式化）。"""
        return HotkeyCaptureEdit._format_display(hk_str or "")

    def _set_hotkey_dot(self, action: str, item: dict):
        """按注册报告项刷新单个状态灯颜色与悬浮说明。"""
        dot = self._hotkey_status_dots.get(action)
        if dot is None:
            return

        reason = item.get("reason", "unknown")
        if item.get("ok"):
            color = "brand.green"
            tip = self._copy("hotkeys.status_ok", "已就绪，按下可正常触发")
        elif reason == "disabled":
            color = "neutral.dark"
            tip = self._copy("hotkeys.status_disabled", "已禁用，按下不会触发")
        elif reason == "occupied":
            color = "brand.red"
            tip = self._copy("hotkeys.status_occupied", "已被其他程序占用，按下将无反应")
        elif reason == "internal":
            conflict = self._action_display_name(item.get("conflict_action") or "")
            color = "brand.red"
            tip = self._copy("hotkeys.status_internal",
                             "与本软件「{name}」使用了相同快捷键", name=conflict)
        elif reason == "invalid":
            color = "brand.red"
            tip = self._copy("hotkeys.status_invalid", "快捷键格式无效")
        elif reason == "failed":
            color = "brand.red"
            tip = self._copy("hotkeys.status_failed",
                             "注册失败（错误码 {code}），请重试或更换组合",
                             code=item.get("error_code"))
        else:
            color = "neutral.dark"
            tip = self._copy("hotkeys.status_unknown", "尚未检测")

        self._style(dot, color=color, font_size="micro")
        dot.setToolTip(tip)

    def _refresh_hotkey_status(self, report: Optional[list[dict]] = None):
        """按状态报告刷新全部状态灯与红色诊断条；report 为 None 时向管线拉取。"""
        if report is None:
            report = self._pull_hotkey_status()
        if not report:
            return

        bad_items: list[dict] = []
        for item in report:
            action = item.get("action")
            if action in self._hotkey_status_dots:
                self._set_hotkey_dot(action, item)
            if not item.get("ok") and item.get("reason") not in (None, "unknown", "disabled"):
                bad_items.append(item)

        if self._hk_warn_frame is None or self._hk_warn_label is None:
            return

        if bad_items:
            names = "、".join(
                f"{self._action_display_name(it.get('action'))} "
                f"{self._format_hotkey(it.get('hotkey') or '')}"
                for it in bad_items
            )
            guide = self._copy(
                "hotkeys.occupied_guide",
                "以下快捷键存在异常，按下可能无反应：{items}。可关闭占用程序（常见：OBS/录屏软件、输入法、QQ 等）后点击「重新检测」，或直接改为其他组合。",
                items=names,
            )
            self._hk_warn_label.setText(guide)
            self._hk_warn_frame.show()
        else:
            self._hk_warn_label.setText("")
            self._hk_warn_frame.hide()

    def _pull_hotkey_status(self) -> Optional[list[dict]]:
        """从截图管线读取最近一次注册状态（无管线/异常时返回 None）。"""
        try:
            shell = self._get_shell()
            if shell and shell.pipeline:
                return shell.pipeline.get_hotkey_status()
        except Exception as e:
            print(f"[TogglesPage] 读取快捷键状态失败: {e}", flush=True)
        return None

    def _on_recheck_clicked(self):
        """「重新检测」按钮：注销重注册并按最新结果刷新灯与诊断条。"""
        try:
            shell = self._get_shell()
            if not shell or not shell.pipeline:
                return
            if self._recheck_btn is not None:
                self._recheck_btn.setEnabled(False)
                self._recheck_btn.setText(self._copy("hotkeys.checking", "正在检测…"))
            report = shell.pipeline.recheck_hotkeys()
            self._refresh_hotkey_status(report)
        except Exception as e:
            print(f"[TogglesPage] 重新检测快捷键失败: {e}", flush=True)
        finally:
            if self._recheck_btn is not None:
                self._recheck_btn.setEnabled(True)
                self._recheck_btn.setText(self._copy("hotkeys.btn_recheck", "重新检测"))

    # ════════════════════════════════════
    #  辅助触发器开关区域
    # ════════════════════════════════════

    def _build_triggers_card(self, parent_layout: QVBoxLayout) -> None:
        """构建辅助触发器开关卡片，插入到父布局中。

        只创建卡片壳体和描述文字，内容由 _populate_triggers_section 填充。
        底部始终显示"前往详细配置"按钮。
        """
        group_name = self._copy("toggles.group_triggers", "辅助触发器")
        card = CyberCard(title=group_name)
        card_layout = card.content_layout()
        card_layout.setContentsMargins(
            self._spacing("md", 16),
            self._spacing("lg_xl", 28),
            self._spacing("md", 16),
            self._spacing("md", 16)
        )
        card_layout.setSpacing(self._spacing("sm", 10))

        # ★ ScrLK 快捷总控行（固定区域，不随 on_enter 重建触发器列表）
        card_layout.addLayout(self._build_scrlk_gate_row())

        # ★ 内层布局：存放触发器行，on_enter 时清理重建
        self._triggers_layout = QVBoxLayout()
        self._triggers_layout.setContentsMargins(0, 0, 0, 0)
        self._triggers_layout.setSpacing(self._spacing("sm", 10))
        card_layout.addLayout(self._triggers_layout)

        self._populate_triggers_section()
        self._ensure_scrlk_gate_bound()

        # ── 底部：前往详细配置按钮（不在内层布局中，不会被清理）──
        goto_btn = CyberButton(
            text=self._copy("toggles.trigger_goto_config", "前往详细配置"),
            variant="outlined",
        )
        goto_btn.setFixedWidth(120)
        goto_btn.clicked.connect(self._goto_triggers_page)
        card_layout.addWidget(goto_btn)

        parent_layout.addWidget(card)

    # ════════════════════════════════════
    #  ScrLK 快捷总控（与触发器页共享引擎信号，双向同步）
    # ════════════════════════════════════

    def _get_trigger_manager(self):
        """获取 TriggerManager 实例（不存在/未就绪时返回 None）。"""
        shell = self._get_shell()
        if shell and hasattr(shell, "trigger_manager") and shell.trigger_manager:
            return shell.trigger_manager
        return None

    def _build_scrlk_gate_row(self) -> QHBoxLayout:
        """构建 ScrLK 快捷总控行：[ON/OFF 开关] 标题+说明 … [实时灯态]。"""
        row = QHBoxLayout()
        row.setSpacing(self._spacing("sm", 10))

        # ── ON/OFF 切角开关 ──
        self._scrlk_gate_switch = CyberToggleSwitch("", checked=False, on_off=True)
        row.addWidget(self._scrlk_gate_switch)

        # ── 标题 + 说明（纵向） ──
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        gate_title = QLabel(
            self._copy("triggers.scrlk_gate_title", "ScrLK 快捷总控")
        )
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

    def _ensure_scrlk_gate_bound(self) -> None:
        """幂等绑定引擎信号并同步一次 UI（外壳未就绪时跳过，on_enter 补连）。"""
        mgr = self._get_trigger_manager()
        if mgr is None or self._scrlk_gate_switch is None:
            return
        if not self._scrlk_gate_bound:
            self._scrlk_gate_switch.toggled.connect(
                self._on_scrlk_gate_switch_toggled
            )
            mgr.scrlk_gate_changed.connect(self._on_scrlk_gate_changed)
            mgr.scrlk_state_changed.connect(self._on_scrlk_light_changed)
            self._scrlk_gate_bound = True
        self._sync_scrlk_gate_ui()

    def _on_scrlk_gate_switch_toggled(self, checked: bool) -> None:
        """本页拨动总控 → 引擎（持久化 + 装/卸钩子 + 广播同步触发器页）。"""
        mgr = self._get_trigger_manager()
        if mgr is None:
            return
        mgr.set_scrlk_gate(checked)
        self._sync_scrlk_gate_ui()

    def _on_scrlk_gate_changed(self, enabled: bool) -> None:
        """引擎门控变化（可能来自触发器页）→ 静默回写本页开关。"""
        sw = self._scrlk_gate_switch
        if sw is not None:
            sw.blockSignals(True)
            sw.setChecked(bool(enabled))
            sw.blockSignals(False)
        self._sync_scrlk_gate_ui()

    def _on_scrlk_light_changed(self, _on: bool) -> None:
        """ScrLK 物理灯态变化 → 刷新灯态标签。"""
        self._sync_scrlk_gate_ui()

    def _sync_scrlk_gate_ui(self) -> None:
        """按引擎当前状态刷新开关位置与灯态标签文案/颜色。"""
        if self._scrlk_gate_switch is None or self._scrlk_state_label is None:
            return
        mgr = self._get_trigger_manager()
        if mgr is None:
            return

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

    def _goto_triggers_page(self):
        """导航到触发器配置页面。"""
        if self._app_shell is not None:
            self._app_shell._switch_to("triggers")

    def _goto_cd_assist_page(self):
        """导航到 CD 辅助显示配置页面。"""
        if self._app_shell is not None:
            self._app_shell._switch_to("cd_assist")

    def _populate_triggers_section(self) -> None:
        """★ 清除旧控件并重新加载触发器数据构建开关行。

        每次 on_enter 时调用，确保 UI 与磁盘数据完全一致。
        """
        layout = self._triggers_layout
        if layout is None:
            print(f"[TogglesPage] _populate_triggers_section: layout is None, 跳过", flush=True)
            return

        print(f"[TogglesPage] _populate_triggers_section: 清除旧控件, 数据={len(self._triggers_data)}个", flush=True)
        # 清除旧控件
        self._clear_layout(layout)
        self._trigger_checkboxes.clear()

        if not self._triggers_data:
            empty_lbl = QLabel(
                self._copy("toggles.trigger_empty", "暂无触发器")
            )
            empty_lbl.setStyleSheet(
                f"color: {self._color('text.tertiary')}; "
                f"font-size: {self._font_size('sm', 12)}px;"
            )
            layout.addWidget(empty_lbl)
        else:
            for idx, trigger in enumerate(self._triggers_data):
                row = self._build_trigger_toggle_row(trigger, idx)
                layout.addLayout(row)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        """安全清空布局中的所有子控件。"""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            sub_layout = item.layout()
            if sub_layout is not None:
                TogglesPage._clear_layout(sub_layout)

    def _build_trigger_toggle_row(self, trigger: dict, idx: int) -> QHBoxLayout:
        """构建一行辅助触发器开关：[切角按钮] 名称 + 摘要 [状态点]。"""
        row = QHBoxLayout()
        row.setSpacing(10)

        name = trigger.get("name", "")
        enabled = bool(trigger.get("enabled", False))
        summary = format_trigger_summary(trigger)

        display_name = name if name else self._copy(
            "triggers.state_unnamed", "未命名"
        )
        label_text = f"{display_name}  —  {summary}"

        # ── 切角开关按钮 ──
        sw = CyberToggleSwitch(text=label_text, checked=enabled)
        sw.toggled.connect(
            lambda checked, i=idx, s=sw: self._on_trigger_clicked(i, checked, s)
        )

        self._trigger_checkboxes.append((sw, idx))
        row.addWidget(sw, stretch=1)

        # ── 状态指示点 ──
        status_dot = QLabel("●" if enabled else "○")
        dot_color = self._color("brand.green") if enabled else self._color("neutral.dark")
        status_dot.setStyleSheet(
            f"color: {dot_color}; "
            f"font-size: {self._font_size('micro', 10)}px;"
        )
        status_dot.setFixedWidth(20)
        row.addWidget(status_dot)

        # 保存 dot 引用以便回调更新
        sw._status_dot = status_dot

        return row

    def _on_trigger_clicked(self, idx: int, checked: bool, sw: CyberToggleSwitch) -> None:
        """用户点击触发器开关：更新内存 + UI + 即时保存 + 重载引擎。"""
        print(f"[TogglesPage] _on_trigger_clicked idx={idx}, checked={checked}", flush=True)
        # 更新内存数据
        if idx < len(self._triggers_data):
            self._triggers_data[idx]["enabled"] = checked
        # 更新状态点
        dot = getattr(sw, '_status_dot', None)
        if dot is not None:
            dot.setText("●" if checked else "○")
            dot_color = self._color("brand.green") if checked else self._color("neutral.dark")
            dot.setStyleSheet(
                f"color: {dot_color}; "
                f"font-size: {self._font_size('micro', 10)}px;"
            )
        # ★ 即时保存文件 + 通知引擎热重载
        self._apply_triggers()

    # ════════════════════════════════════
    #  CD 辅助显示 总开关(与 cd_assist_page 共享 service)
    # ════════════════════════════════════

    def _build_cd_assist_card(self, parent_layout) -> None:
        """构造"CD 辅助显示"总开关卡片。

        与 CdAssistPage 共享同一个 CdAssistService 单例,任何一边
        改动都会同步到另一边。
        """
        try:
            from core.services.cd_assist_service import CdAssistService
            service = CdAssistService.instance()
        except Exception as e:
            print(f"[TogglesPage] 加载 CdAssistService 失败: {e}", flush=True)
            return

        card = CyberCard(title=self._copy("nav.cd_assist", "CD 辅助显示"))
        clayout = card.content_layout()
        clayout.setContentsMargins(
            self._spacing("md", 16),
            self._spacing("lg_xl", 28),
            self._spacing("md", 16),
            self._spacing("md", 16),
        )
        clayout.setSpacing(self._spacing("sm", 10))

        # ① 标题行
        row = QHBoxLayout()
        row.setSpacing(self._spacing("sm_md", 12))
        label = QLabel("启用 CD 辅助显示")
        self._style(
            label,
            color="text.primary",
            font_size="md",
            font_weight="bold",
        )
        row.addWidget(label)
        row.addStretch(1)

        self._cd_assist_toggle = CyberToggleSwitch(
            "", checked=service.is_enabled(), on_off=True
        )
        self._cd_assist_toggle.toggled.connect(self._on_cd_assist_toggled)
        row.addWidget(self._cd_assist_toggle)
        clayout.addLayout(row)

        # ② 提示
        tip = QLabel(
            self._copy(
                "cd_assist.toggles_tip",
                "按 1/2/3/4 键在屏幕中心显示对应技能的倒计时(详细参数请到「CD 辅助显示」页设置)。",
            )
        )
        self._style(tip, color="text.tertiary", font_size="sm")
        tip.setWordWrap(True)
        clayout.addWidget(tip)

        # ③ 跳转按钮(与辅助触发器 box 的"前往详细配置"对齐,方便用户快速跳过去)
        goto_btn = CyberButton(
            text=self._copy("cd_assist.toggles_goto", "前往详细配置"),
            variant="outlined",
        )
        goto_btn.setFixedWidth(120)
        goto_btn.clicked.connect(self._goto_cd_assist_page)
        clayout.addWidget(goto_btn)

        # ④ 跟随 service 状态变化(让两个开关双向同步)
        try:
            service.enabled_changed.connect(self._on_service_enabled_changed_sync)
        except Exception:
            pass

        parent_layout.addWidget(card)

    def _on_cd_assist_toggled(self, on: bool) -> None:
        """本卡片开关变化 → service.set_enabled。"""
        try:
            from core.services.cd_assist_service import CdAssistService
            CdAssistService.instance().set_enabled(on)
        except Exception as e:
            print(f"[TogglesPage] 切换 CD 辅助总开关失败: {e}", flush=True)

    def _on_service_enabled_changed_sync(self, on: bool) -> None:
        """service 状态变化 → 同步本页 UI(不会再次触发 set_enabled,因 setChecked 不发 toggled)。"""
        if not hasattr(self, '_cd_assist_toggle') or self._cd_assist_toggle is None:
            return
        try:
            self._cd_assist_toggle.blockSignals(True)
            self._cd_assist_toggle.setChecked(on)
            self._cd_assist_toggle.blockSignals(False)
        except Exception:
            pass

    # ════════════════════════════════════
    #  操作回调
    # ════════════════════════════════════

    def on_enter(self):
        """页面进入时重新加载最新配置并重建 UI。"""
        print(f"[TogglesPage] on_enter() 开始", flush=True)
        self._load_toggles()
        self._load_hotkeys()
        self._load_triggers()
        print(f"[TogglesPage] on_enter() 触发器数据: {len(self._triggers_data)}个", flush=True)
        for t in self._triggers_data:
            print(f"  {t.get('name')}: enabled={t.get('enabled')}", flush=True)

        # 同步功能开关 checkbox 状态
        for key, cb in self._checkboxes.items():
            val = self._toggles_data.get(key, _DEFAULT_VALUES.get(key, False))
            cb.blockSignals(True)
            cb.setChecked(bool(val))
            cb.blockSignals(False)

        # 同步热键输入框状态
        for key, edit in self._hotkey_edits.items():
            val = self._hotkeys_data.get(key, "")
            edit.value = val

        # 同步快捷键启用/禁用开关状态（从磁盘读取的最新值）
        for key, sw in self._hotkey_toggles.items():
            val = self._hotkey_enabled.get(key, True)
            sw.blockSignals(True)
            sw.setChecked(bool(val))
            sw.blockSignals(False)

        # ★ 从磁盘重新加载触发器数据，重建整个触发器开关区域
        self._populate_triggers_section()

        # ScrLK 总控：首次进页时引擎才就绪，这里补连信号并同步灯态
        self._ensure_scrlk_gate_bound()

        # 静默刷新快捷键占用诊断（只读数，不触发重注册）
        self._refresh_hotkey_status()

        print(f"[TogglesPage] on_enter() 完成, 复选框数={len(self._trigger_checkboxes)}", flush=True)

    def _get_shell(self):
        """获取 AppShell 实例。"""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        for w in app.topLevelWidgets():
            if hasattr(w, 'pipeline'):
                return w
        return None

    def _pause_hotkeys(self):
        """暂停所有全局热键（进入捕获模式时调用）。"""
        try:
            shell = self._get_shell()
            if shell and shell.pipeline and shell.pipeline._hotkey_mgr:
                shell.pipeline._hotkey_mgr.clear()
        except Exception:
            pass

    def _resume_hotkeys(self):
        """恢复全局热键（退出捕获模式时调用），并刷新诊断状态。"""
        try:
            shell = self._get_shell()
            if shell and shell.pipeline and shell.pipeline._hotkey_mgr:
                shell.pipeline._hotkey_mgr.register_initial()
        except Exception:
            pass
        self._refresh_hotkey_status()
