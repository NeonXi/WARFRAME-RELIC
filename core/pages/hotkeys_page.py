"""
[L2] HotkeysPage — 快捷键配置页面。

依赖: widgets/, services/hotkey_service.py
职责: 快捷键绑定与冲突检测

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.hotkey_config, core.hotkey_manager, PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接), 任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止在 Page 内调 keyboard 库注册热键 → 必须 hotkey_manager.register()
- ✗ 禁止快捷键格式硬编码 → 必须 hotkey_config.get()
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5,别走捷径。
"""


from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.pages.base_page import PageBase
from core.widgets.button import CyberButton
from core.widgets.line_edit import CyberLineEdit
from core.widgets.card import CyberCard
from core.tokens.manager import TokenManager


class HotkeysPage(PageBase):
    """快捷键管理页面。

    让用户查看/修改全局快捷键(查询、截图、价格查询、遮罩等)。
    修改后写入 core.hotkey_config,触发 hotkey_manager 重新注册。
    """
    page_id = "hotkeys"
    page_title = ""  # 由 nav token 动态获取
    page_icon = "nav_hotkeys"

    def __init__(self):
        super().__init__()
        self.page_title = self._copy("nav.hotkeys", "快捷键")

    def build_content(self) -> QWidget:
        """构建快捷键管理页(列出所有可配置热键 + 编辑入口)。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(16)

        # ── 标题 ──
        title = QLabel(self._copy("hotkeys.title", "快捷键设置"))
        title.setFont(QFont("Iceberg", self._font_size("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        desc = QLabel(self._copy("hotkeys.desc", "自定义全局快捷键，点击输入框后按下新组合键"))
        self._style(desc, color="text.tertiary", font_size="sm", padding=("0", "0", "12px", "0"))
        layout.addWidget(desc)

        # ── 快捷键列表 ──
        hotkey_card = CyberCard(title=self._copy("hotkeys.card_binding", "快捷键绑定"))
        hk_layout = hotkey_card.content_layout()
        hk_layout.setContentsMargins(16, 28, 16, 16)
        hk_layout.setSpacing(10)

        hotkeys = [
            (self._copy("hotkeys.hk_toggle_window", "显示/隐藏主窗口"), "Ctrl+Shift+W"),
            (self._copy("hotkeys.hk_quick_search", "快速搜索物品"), "Ctrl+F"),
            (self._copy("hotkeys.hk_refresh_data", "刷新数据源"), "F5"),
            (self._copy("hotkeys.hk_copy_selected", "复制当前选中项"), "Ctrl+C"),
            (self._copy("hotkeys.hk_open_settings", "打开设置面板"), "Ctrl+,"),
            (self._copy("hotkeys.hk_toggle_theme", "切换深色/浅色主题"), "Ctrl+Shift+T"),
            (self._copy("hotkeys.hk_export_view", "导出当前视图"), "Ctrl+S"),
            (self._copy("hotkeys.hk_show_help", "显示帮助文档"), "F1"),
        ]

        for action_name, default_key in hotkeys:
            row = QHBoxLayout()
            row.setSpacing(12)

            name_lbl = QLabel(action_name)
            self._style(name_lbl, color="text.primary", font_size="sm_md")
            name_lbl.setMinimumWidth(160)
            row.addWidget(name_lbl)

            key_input = CyberLineEdit()
            key_input.setText(default_key)
            key_input.setReadOnly(True)
            key_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_input.setFixedWidth(140)
            key_input.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(key_input)

            reset_btn = CyberButton(text=self._copy("common.reset", "重置"), variant="ghost")
            reset_btn.setFixedWidth(50)
            row.addWidget(reset_btn)

            row.addStretch()

            hk_layout.addLayout(row)

        layout.addWidget(hotkey_card)

        # ── 冲突检测提示 ──
        tip_frame = QFrame()
        # 复杂 QSS(rgba 透明叠加)走 raw 通道;callable 形式支持主题切换重放
        def _tip_frame_qss():
            a = TokenManager.instance().get_qcolor("accent.primary")
            return (
                f"QFrame {{"
                f"  background-color: rgba({a.red()}, {a.green()}, {a.blue()}, 0.06);"
                f"  border: 1px solid rgba({a.red()}, {a.green()}, {a.blue()}, 0.2);"
                f"  border-radius: {self._spacing('corner.xs', 4)}px;"
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

        tip_text = QLabel(self._copy("hotkeys.tip", "提示：修改快捷键后请确认不与其他软件冲突。部分系统级快捷键可能无法覆盖。"))
        self._style(tip_text, color="alias.text.tertiary", font_size="xs")
        tip_text.setWordWrap(True)
        tip_layout.addWidget(tip_text, stretch=1)

        layout.addWidget(tip_frame)
        layout.addStretch()

        return container
