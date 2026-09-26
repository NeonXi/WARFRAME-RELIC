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

        # 辅助触发器数据
        self._triggers_data: list[dict] = []
        self._trigger_checkboxes: list[tuple[CyberToggleSwitch, int]] = []  # (toggle_switch, index_in_list)
        self._triggers_layout: Optional[QVBoxLayout] = None  # 触发器卡片的内容布局引用

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
        """加载快捷键配置。"""
        try:
            from core.hotkey_config import load_hotkeys, DEFAULT_HOTKEYS
            raw = load_hotkeys()
            # 只取本页关心的 action（按 _HOTKEY_DEFS 过滤）
            self._hotkeys_data = {
                k: raw.get(k, DEFAULT_HOTKEYS.get(k, ""))
                for k, _, _ in _HOTKEY_DEFS
            }
        except Exception as e:
            print(f"[TogglesPage] 加载热键失败: {e}", flush=True)
            self._hotkeys_data = {k: d for k, _, d in _HOTKEY_DEFS}

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
        """保存快捷键并通知管线重注册。"""
        if not self._save_hotkeys():
            return
        try:
            shell = self._get_shell()
            if shell and shell.pipeline:
                shell.pipeline.reregister_hotkeys()
        except Exception:
            pass

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

        for action_key, label_token, default_val in _HOTKEY_DEFS:
            row = self._build_hotkey_row(action_key, label_token, default_val)
            hk_layout.addLayout(row)

        layout.addWidget(hk_card)

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

        reset_btn = CyberButton(text=self._copy("common.reset", "重置"), variant="ghost")
        reset_btn.setFixedWidth(50)
        reset_btn.clicked.connect(lambda checked, k=action_key, dv=default_val: self._reset_hotkey(k, dv))
        row.addWidget(reset_btn)

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

        # ★ 内层布局：存放触发器行，on_enter 时清理重建
        self._triggers_layout = QVBoxLayout()
        self._triggers_layout.setContentsMargins(0, 0, 0, 0)
        self._triggers_layout.setSpacing(self._spacing("sm", 10))
        card_layout.addLayout(self._triggers_layout)

        self._populate_triggers_section()

        # ── 底部：前往详细配置按钮（不在内层布局中，不会被清理）──
        goto_btn = CyberButton(
            text=self._copy("toggles.trigger_goto_config", "前往详细配置"),
            variant="outlined",
        )
        goto_btn.setFixedWidth(120)
        goto_btn.clicked.connect(self._goto_triggers_page)
        card_layout.addWidget(goto_btn)

        parent_layout.addWidget(card)

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

        # ★ 从磁盘重新加载触发器数据，重建整个触发器开关区域
        self._populate_triggers_section()
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
        """恢复全局热键（退出捕获模式时调用）。"""
        try:
            shell = self._get_shell()
            if shell and shell.pipeline and shell.pipeline._hotkey_mgr:
                shell.pipeline._hotkey_mgr.register_initial()
        except Exception:
            pass
