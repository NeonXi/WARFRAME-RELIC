"""
[L2] EyeMaskPage — 护眼遮罩页面

依赖: widgets/
职责: 多屏护眼遮罩管理,可选择在哪些屏幕启用遮罩(多选)

功能:
  - 全局快捷键(默认 Ctrl+J)切换所有启用屏幕的遮罩
  - 多屏支持:每屏一个独立遮罩窗口,可多选启用屏幕
  - 遮罩鼠标穿透(不抢焦点、不拦截点击)
  - 可调节遮罩不透明度
  - 配色固定为纯黑色
  - 屏幕列表可热刷新(应对屏幕热插拔)
  - 快捷键可在此页面或开关控制页面修改

注: 多选屏幕选择仅本次会话生效,重启软件恢复默认(全选所有屏幕)。

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.hotkey_config, PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接)
           任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止遮罩层拦截鼠标 → 必须 setAttribute(Qt.WA_TransparentForMouseEvents)
- ✗ 禁止快捷键硬编码 → 必须 hotkey_config.get("eye_mask")
- ✗ 禁止硬编码颜色(除固定黑色) → 必须 token
- ✗ 禁止遮罩全屏但被任务栏遮挡 → 必须 frameless + 屏幕几何正确
- ✗ 禁止硬编码尺寸 16/40/45 → 必须 space token
- ✗ 禁止直接调 TokenManager.get_qcolor → 必须 _color() / _font_size() / _spacing()

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QSlider,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication

from core.pages.base_page import PageBase
from core.hotkey_config import load_hotkeys
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.eye_mask_overlay import EyeMaskManager, DEFAULT_OPACITY
from core.widgets.eye_mask_toggle_button import EyeMaskToggleButton
from core.widgets.screen_select_button import ScreenSelectButton


# ══════════════════════════════════════════════
#  EyeMaskPage
# ══════════════════════════════════════════════

class EyeMaskPage(PageBase):
    """护眼遮罩设置页面。

    让用户配置屏幕遮罩(蒙版)的开关、透明度、可启用屏幕等参数。
    实际遮罩由 EyeMaskManager 管理多屏遮罩窗口,本页只负责参数。
    """
    page_id = "eye_mask"
    page_title = ""
    page_icon = "nav_about"

    def __init__(self):
        # 不透明度(从 widget 模块读默认值)
        self._opacity_pct = DEFAULT_OPACITY
        self._manager: EyeMaskManager | None = None

        # UI 引用(必须在 super().__init__() 之前声明,因为 build_content 在基类初始化时调用)
        self._opacity_slider: QSlider | None = None
        self._opacity_label: QLabel | None = None
        self._toggle_btn: EyeMaskToggleButton | None = None
        self._hotkey_tip: QLabel | None = None

        # 屏幕选择卡片的 UI 引用(on_enter 时刷新屏幕列表用)
        self._screen_card: CyberCard | None = None
        # screen_index -> ScreenSelectButton(屏幕勾选控件,大按钮式)
        self._screen_buttons: dict[int, ScreenSelectButton] = {}
        # 屏幕选择卡的内部 layout(用于动态增删行)
        self._screen_card_layout: QVBoxLayout | None = None
        # 已选数量提示
        self._screen_count_label: QLabel | None = None

        # 从 hotkey_config 读取当前快捷键(用户在 hotkeys 页改了立即生效)
        # 同样必须在 super().__init__() 之前,因为 build_content 内部要读 _hotkey_label
        self._hotkey_label = self._resolve_hotkey_label()

        super().__init__()
        self.page_title = self._copy("nav.eye_mask", "护眼遮罩")

    # ══════════════════════════════════
    #  辅助:快捷键标签
    # ══════════════════════════════════

    def _resolve_hotkey_label(self) -> str:
        """从 hotkey_config 读取 eye_mask 快捷键,渲染成人类可读标签。"""
        try:
            hotkeys = load_hotkeys()
            raw = hotkeys.get("eye_mask", "ctrl+j")
        except Exception:
            raw = "ctrl+j"
        # "ctrl+j" -> "Ctrl+J"
        parts = [p.capitalize() for p in raw.split("+") if p]
        return "+".join(parts) if parts else "Ctrl+J"

    # ══════════════════════════════════
    #  生命周期
    # ══════════════════════════════════

    def set_app_shell(self, shell):
        """注入 AppShell 引用并连接热键信号(必须在 AppShell 注入后调用)。"""
        super().set_app_shell(shell)
        self._connect_hotkey()

    def _connect_hotkey(self):
        """订阅 pipeline 的 eye_mask_toggled 信号(失败静默,因热键可能未注册)。"""
        try:
            pipeline = self._app_shell.pipeline
            if pipeline and hasattr(pipeline, 'eye_mask_toggled'):
                pipeline.eye_mask_toggled.connect(self._on_hotkey_toggle)
        except Exception:
            pass

    def on_enter(self):
        """页面进入时:确保 manager 就绪 + 刷新屏幕列表 + 重新连接热键。"""
        self._ensure_manager()
        self._refresh_screens_ui()
        if self._app_shell:
            self._connect_hotkey()
            # 同步最新的快捷键标签(用户可能在 hotkeys 页改过)
            new_label = self._resolve_hotkey_label()
            if new_label != self._hotkey_label:
                self._hotkey_label = new_label
                if self._hotkey_tip:
                    self._hotkey_tip.setText(
                        f"全局快捷键: {self._hotkey_label}  切换遮罩开/关"
                    )

    def on_leave(self):
        """页面离开无需特殊处理(遮罩常驻,仅切走时不响应热键也 OK)。"""
        pass

    def _ensure_manager(self):
        """确保 manager 存在,首次创建时立刻按当前所有屏幕初始化。"""
        if self._manager is None:
            self._manager = EyeMaskManager()
        # 每次进入页面都 refresh:有新屏幕热插拔进来时立刻纳入池
        self._manager.refresh_screens()
        # 默认全选所有屏幕(用户已确认:不持久化,默认全选)
        all_indices = self._manager.available_screen_indices()
        self._manager.set_enabled_screens(all_indices)
        # 同步当前不透明度到 manager
        self._manager.set_opacity(self._opacity_pct)

    # ══════════════════════════════════
    #  屏幕列表 UI
    # ══════════════════════════════════

    def _refresh_screens_ui(self):
        """重建屏幕选择卡片的行(应对屏幕热插拔)。"""
        if self._screen_card_layout is None or self._manager is None:
            return

        # 清空旧行(包含上一轮的 wrap widget + 子控件)
        while self._screen_card_layout.count():
            item = self._screen_card_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._screen_buttons.clear()

        # 重建 ① "全选/全不选"行
        self._build_screen_bulk_row()

        # 重建 ② 屏幕按钮网格(每行 2 列,响应式布局)
        self._build_screen_grid()

    def _build_screen_bulk_row(self) -> None:
        """构造"全选/全不选"快捷按钮行。"""
        if self._screen_card_layout is None:
            return
        row = QHBoxLayout()
        row.setSpacing(self._spacing("sm_md", 12))
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # 复用 CyberButton outlined 变体(规范 §6.4: 沿用现有 widget,不重造)
        btn_all = CyberButton("全选", variant="outlined")
        btn_none = CyberButton("全不选", variant="outlined")
        # 紧凑尺寸:padding 走 token
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

        # 已选数量(右侧)
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

        # 把 QHBoxLayout 包装进容器 widget
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

        # 容器 widget
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(self._spacing("sm_md", 12))
        grid.setVerticalSpacing(self._spacing("sm_md", 12))

        # 列数:固定 2 列(单屏/双屏/多屏都紧凑,适合快速操作)
        cols = 2
        enabled_set = set(self._manager.get_enabled_screens())

        for i, screen in enumerate(screens):
            idx = i
            g = screen.geometry()
            is_primary = (idx == primary_index)
            label_text = (
                f"屏幕 {idx + 1}  ·  {g.width()} × {g.height()}"
                + ("  ·  主屏" if is_primary else "")
            )
            btn = ScreenSelectButton(label_text)
            btn.set_selected(idx in enabled_set)
            btn.clicked.connect(self._on_screen_button_clicked)
            self._screen_buttons[idx] = btn
            row, col = divmod(i, cols)
            grid.addWidget(btn, row, col)

        # 等宽拉伸(只拉列,不拉行 —— 按钮 setFixedHeight 锁 44,
        # 不需要行拉伸;之前的 row_stretch 反而让 grid_widget 撑大)
        for col in range(cols):
            grid.setColumnStretch(col, 1)

        self._screen_card_layout.addWidget(grid_widget)

    def _update_screen_count_label(self) -> None:
        """更新"已选 N / 总数 M"提示。"""
        if self._screen_count_label is None:
            return
        total = len(self._screen_buttons)
        selected = sum(1 for b in self._screen_buttons.values() if b.is_selected())
        self._screen_count_label.setText(f"已选 {selected} / {total}")

    def _notify_manager(self) -> None:
        """把当前所有按钮的选中状态同步给 manager。"""
        if self._manager is None:
            return
        enabled = [idx for idx, b in self._screen_buttons.items() if b.is_selected()]
        self._manager.set_enabled_screens(enabled)
        self._update_screen_count_label()

    def _on_screen_button_clicked(self) -> None:
        """单个屏幕按钮被点击:翻转该按钮的选中状态,再通知 manager。

        注: ScreenSelectButton 不像 QCheckBox 会自动翻转状态,
        点击只发 clicked 信号,状态切换由 handler 负责(参考
        EyeMaskToggleButton 的"使用方负责翻转"约定)。
        """
        btn = self.sender()
        if isinstance(btn, ScreenSelectButton):
            btn.set_selected(not btn.is_selected())
        self._notify_manager()

    def _on_select_all(self) -> None:
        for b in self._screen_buttons.values():
            b.set_selected(True)
        self._notify_manager()

    def _on_select_none(self) -> None:
        for b in self._screen_buttons.values():
            b.set_selected(False)
        self._notify_manager()

    # ══════════════════════════════════
    #  快捷键响应
    # ══════════════════════════════════

    def _on_hotkey_toggle(self):
        if self._manager is None:
            self._ensure_manager()
        self._manager.toggle()
        self._sync_ui_from_overlay()

    # ══════════════════════════════════
    #  UI 同步
    # ══════════════════════════════════

    def _sync_ui_from_overlay(self):
        if self._toggle_btn and self._manager:
            visible = self._manager.is_visible()
            self._toggle_btn.set_on(visible)
            self._toggle_btn.setText("关闭遮罩" if visible else "开启遮罩")

    # ══════════════════════════════════
    #  透明度变更
    # ══════════════════════════════════

    def _on_opacity_changed(self, value: int):
        self._opacity_pct = value
        if self._manager:
            self._manager.set_opacity(value)
        if self._opacity_label:
            self._opacity_label.setText(f"{value}%")

    # ══════════════════════════════════
    #  页面构建
    # ══════════════════════════════════

    def build_content(self) -> QWidget:
        """构建护眼遮罩设置页(开关按钮 + 透明度滑块 + 屏幕多选)。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            self._spacing("lg", 16),
            self._spacing("md", 12),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
        )
        layout.setSpacing(self._spacing("sm_md", 13))
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        accent = self._color("accent.primary")

        # ── 标题 ──
        title = QLabel("护眼遮罩")
        title.setFont(QFont("Iceberg", self._font_size("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        # ── 描述 ──
        desc = QLabel(
            "在屏幕上覆盖一层黑色半透明遮罩，降低屏幕亮度，保护视力。\n"
            "遮罩完全穿透鼠标，不会影响正常操作。"
        )
        self._style(
            desc,
            color="text.tertiary",
            font_size="sm",
            padding=("0", "0", "0", "0", "6px", "0"),
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ── 快捷键提示 ──
        from core.tokens.manager import TokenManager as _TM
        warn_color = _TM.instance().get_qcolor("semantic.warning")
        pad_x = self._spacing("sm_md", 12)
        pad_y = self._spacing("xs", 4)

        hotkey_tip = QLabel(f"全局快捷键: {self._hotkey_label}  切换遮罩开/关")
        self._style(
            hotkey_tip,
            color="accent.primary",
            font_size="sm",
            font_weight="bold",
            background_color=f"rgba({warn_color.red()}, {warn_color.green()}, {warn_color.blue()}, 0.06)",
            border=f"1px solid rgba({warn_color.red()}, {warn_color.green()}, {warn_color.blue()}, 0.15)",
            padding=(f"{pad_y}px", f"{pad_x}px"),
        )
        radius = self._spacing("xs", 4)
        hotkey_tip.setStyleSheet(
            hotkey_tip.styleSheet() + f" border-radius: {radius}px;"
        )
        hotkey_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hotkey_tip = hotkey_tip
        layout.addWidget(hotkey_tip)

        # ══════════════════════════════════
        #  屏幕选择卡片(多选)
        # ══════════════════════════════════
        screen_card = CyberCard(title="启用屏幕", clickable=False)
        self._screen_card_layout = screen_card.content_layout()
        self._screen_card_layout.setContentsMargins(
            self._spacing("lg", 16),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
        )
        self._screen_card_layout.setSpacing(self._spacing("sm", 8))
        # 初始为空行(由 on_enter -> _refresh_screens_ui 填充)
        self._screen_card = screen_card
        layout.addWidget(screen_card)

        # ══════════════════════════════════
        #  不透明度卡片
        # ══════════════════════════════════
        opacity_card = CyberCard(title="不透明度", clickable=False)
        opacity_layout = opacity_card.content_layout()
        opacity_layout.setContentsMargins(
            self._spacing("lg", 16),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
        )
        opacity_layout.setSpacing(self._spacing("sm", 8))

        slider_row = QHBoxLayout()
        slider_row.setSpacing(self._spacing("sm_md", 12))

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(5, 80)
        self._opacity_slider.setValue(self._opacity_pct)
        self._opacity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._opacity_slider.setTickInterval(10)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)

        # 复杂 QSS(多选择器)走 raw 通道;callable 形式支持主题切换重放
        def _slider_qss():
            ac = self._color("accent.primary")
            ac2 = self._color("accent.secondary")
            t_h = self._spacing("xs", 4) + 2  # 6
            h_size = self._spacing("sm", 8) + 4  # 12
            h_radius = h_size // 2
            return (
                f"QSlider::groove:horizontal {{"
                f"  background: {self._color('components.progress.track_bg')};"
                f"  height: {t_h}px;"
                f"  border-radius: {t_h // 2}px;"
                f"}}"
                f"QSlider::handle:horizontal {{"
                f"  background: {ac};"
                f"  width: {h_size}px;"
                f"  height: {h_size}px;"
                f"  margin: -{self._spacing('xs', 4) + 1}px 0;"
                f"  border-radius: {h_radius}px;"
                f"}}"
                f"QSlider::handle:horizontal:hover {{"
                f"  background: {ac2};"
                f"}}"
                f"QSlider::sub-page:horizontal {{"
                f"  background: {ac};"
                f"  border-radius: {t_h // 2}px;"
                f"}}"
            )
        self._style(self._opacity_slider, raw=_slider_qss)
        slider_row.addWidget(self._opacity_slider, stretch=1)

        self._opacity_label = QLabel(f"{self._opacity_pct}%")
        self._style(
            self._opacity_label,
            color="accent.primary",
            font_size="md",
            font_weight="bold",
            raw="font-family: monospace;",
        )
        self._opacity_label.setFixedWidth(self._spacing("xxl", 24) + self._spacing("md", 12) + 4)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        slider_row.addWidget(self._opacity_label)

        opacity_layout.addLayout(slider_row)

        tip = QLabel("5% = 几乎透明    25% = 适中护眼    50% = 明显遮罩    80% = 深色滤镜")
        self._style(
            tip,
            color="text.tertiary",
            font_size="micro",
        )
        opacity_layout.addWidget(tip)

        layout.addWidget(opacity_card)

        # ══════════════════════════════════
        #  操作按钮
        # ══════════════════════════════════
        btn_row = QHBoxLayout()
        btn_row.setSpacing(self._spacing("sm_md", 12))
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._toggle_btn = EyeMaskToggleButton(text="开启遮罩")
        self._toggle_btn.clicked.connect(self._on_hotkey_toggle)
        btn_row.addWidget(self._toggle_btn)

        layout.addLayout(btn_row)

        layout.addStretch()

        return container
