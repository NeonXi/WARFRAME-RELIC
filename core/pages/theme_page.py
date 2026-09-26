"""
[L2] ThemePage — 主题换肤页面。

依赖: widgets/, sections/theme_edit_section.py, sections/theme_bg_section.py
职责: 预设切换 + 自定义颜色编辑

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.theme_proxy, PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接), 任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止在 Page 内改主题色 → 走 TokenManager.reload_preset()
- ✗ 禁止硬编码颜色(主题相关) → 必须 token / space
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5,别走捷径。
"""


from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSlider, QFileDialog, QDialog,
)
from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtGui import QFont

from pathlib import Path

from core.pages.base_page import PageBase
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.image_crop_dialog import CyberImageCropDialog


class _NoWheelFilter(QObject):
    """吞掉 QSlider 滚轮事件的事件过滤器(防止误触改值)。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True  # 拦截,不传给滑块
        return False


class ThemePage(PageBase):
    """主题换肤页面。

    提供配色预设切换(Cyberpunk/Daylight/Custom)与实时预览。
    切换时调用 core.theme_proxy 重新加载 Token,触发全 App 主题刷新。
    """
    page_id = "theme"
    page_title = ""  # 由 nav token 动态获取
    page_icon = "nav_theme"

    def __init__(self):
        # UI 引用(必须在 super().__init__() 之前声明,
        # 因为 PageBase.__init__ 内部会调 build_content)
        self._opacity_slider: QSlider | None = None
        self._opacity_label: QLabel | None = None
        self._opacity_pct: int = 100  # 默认占位,on_enter 时从 service 覆盖

        # 背景图卡片控件
        self._bg_file_label: QLabel | None = None
        self._bg_opacity_slider: QSlider | None = None
        self._bg_opacity_label: QLabel | None = None
        self._bg_blur_slider: QSlider | None = None
        self._bg_blur_label: QLabel | None = None
        # 全局沉浸模式控件
        self._immersive_cb: QCheckBox | None = None
        self._immersive_slider: QSlider | None = None
        self._immersive_val_label: QLabel | None = None
        # 沉浸底色预设切换按钮(主题色 / 纯黑)
        self._imm_color_theme_btn: CyberButton | None = None
        self._imm_color_black_btn: CyberButton | None = None

        self._wheel_filter = _NoWheelFilter()  # 无 parent,在 super().__init__ 之前创建
        super().__init__()
        self.page_title = self._copy("nav.theme", "主题换肤")

    def build_content(self) -> QWidget:
        """构建主题换肤页(配色预设卡片 + 实时预览)。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(16)

        # ── 标题 ──
        title = QLabel(self._copy("theme.title", "外观与主题"))
        title.setFont(QFont("Iceberg", self._font_size("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        # ══════════════════════════════════
        #  预设主题卡片(第一个 — 全局风格切换)
        # ══════════════════════════════════
        preset_card = CyberCard(title=self._copy("theme.card_preset", "预设主题"))
        preset_layout = preset_card.content_layout()
        preset_layout.setContentsMargins(
            self._spacing("lg", 16),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
            self._spacing("lg", 16),
        )
        preset_layout.setSpacing(self._spacing("sm", 8))

        preset_row = QHBoxLayout()
        preset_row.setSpacing(self._spacing("sm_md", 12))

        # 当前预设(从 ui_prefs 读取)
        from core.services.ui_prefs import load_theme_preset
        self._current_preset = load_theme_preset()

        self._preset_cyber_btn = CyberButton(
            text="赛博朋克",
            variant="solid" if self._current_preset == "cyberpunk" else "outlined",
        )
        self._preset_glass_btn = CyberButton(
            text="玻璃拟态",
            variant="solid" if self._current_preset == "glassmorphism" else "outlined",
        )
        self._preset_cyber_btn.clicked.connect(lambda: self._on_preset_clicked("cyberpunk"))
        self._preset_glass_btn.clicked.connect(lambda: self._on_preset_clicked("glassmorphism"))

        preset_row.addWidget(self._preset_cyber_btn)
        preset_row.addWidget(self._preset_glass_btn)
        preset_row.addStretch()
        preset_layout.addLayout(preset_row)

        preset_tip = QLabel(self._copy(
            "theme.tip_preset",
            "切换后全局生效,部分控件可能需要切换页面后完全刷新"
        ))
        self._style(preset_tip, color="text.tertiary", font_size="micro")
        preset_layout.addWidget(preset_tip)

        layout.addWidget(preset_card)

        # ══════════════════════════════════
        #  界面透明度卡片(第二个 — 最常用的视觉调整)
        # ══════════════════════════════════
        opacity_card = CyberCard(title=self._copy("theme.card_window_opacity", "界面透明度"))
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
        self._opacity_slider.setRange(30, 100)
        self._opacity_slider.setValue(self._opacity_pct)
        self._opacity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._opacity_slider.setTickInterval(10)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self._opacity_slider.installEventFilter(self._wheel_filter)

        # QSS 走 callable 注册,切换预设时由 on_theme_change 自动重放
        self._style(self._opacity_slider, raw=self._slider_qss)
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

        tip = QLabel(self._copy(
            "theme.tip_window_opacity",
            "30% = 几乎透明   100% = 完全不透明   (仅主窗口,不影响悬浮窗)",
        ))
        self._style(
            tip,
            color="text.tertiary",
            font_size="micro",
        )
        opacity_layout.addWidget(tip)

        layout.addWidget(opacity_card)

        # ══════════════════════════════════
        #  背景图片卡片(自定义壁纸 + 透明度/模糊度)
        # ══════════════════════════════════
        from core.services.background_service import BackgroundService
        bg_svc = BackgroundService.instance()

        bg_card = CyberCard(title=self._copy("theme.card_background", "背景图片"))
        bg_layout = bg_card.content_layout()
        bg_layout.setContentsMargins(16, 16, 16, 16)
        bg_layout.setSpacing(10)

        # 第一行:选择 / 清除 按钮 + 当前文件名
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        select_btn = CyberButton(
            text=self._copy("theme.btn_select_bg", "选择图片"), variant="solid"
        )
        select_btn.clicked.connect(self._on_select_bg)
        btn_row.addWidget(select_btn)

        clear_btn = CyberButton(
            text=self._copy("theme.btn_clear_bg", "清除"), variant="ghost"
        )
        clear_btn.clicked.connect(self._on_clear_bg)
        btn_row.addWidget(clear_btn)

        self._bg_file_label = QLabel(
            Path(bg_svc.source).name if bg_svc.source
            else self._copy("theme.bg_none", "未设置")
        )
        self._style(self._bg_file_label, color="text.tertiary", font_size="sm")
        btn_row.addWidget(self._bg_file_label, stretch=1)
        bg_layout.addLayout(btn_row)

        # 透明度滑块(0-100)
        self._bg_opacity_slider, self._bg_opacity_label = self._make_bg_slider_row(
            bg_layout,
            self._copy("theme.bg_opacity", "透明度"),
            bg_svc.opacity,
        )
        self._bg_opacity_slider.valueChanged.connect(bg_svc.request_opacity)
        self._bg_opacity_slider.sliderReleased.connect(bg_svc.commit)

        # 模糊度滑块(0-100)
        self._bg_blur_slider, self._bg_blur_label = self._make_bg_slider_row(
            bg_layout,
            self._copy("theme.bg_blur", "模糊度"),
            bg_svc.blur,
        )
        self._bg_blur_slider.valueChanged.connect(bg_svc.request_blur)
        self._bg_blur_slider.sliderReleased.connect(bg_svc.commit)

        # ── 全局沉浸模式（开关 + 沉浸强度）──
        self._immersive_cb = QCheckBox(
            self._copy(
                "theme.cb_immersive",
                "全局沉浸模式（导航栏和卡片透出壁纸）",
            )
        )
        self._immersive_cb.setChecked(bg_svc.immersive)
        self._immersive_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style(
            self._immersive_cb,
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
                f"QCheckBox:hover {{ color: {self._color('accent.secondary')}; }}"
            ),
        )
        self._immersive_cb.toggled.connect(bg_svc.set_immersive)
        bg_layout.addWidget(self._immersive_cb)

        # ── 沉浸底色：主题色 / 纯黑 二选一 ──
        # 与「仅钢铁之路 / 仅普通」筛选按钮一致:蓝色描边(off) + 黄色实心(on)
        color_row = QHBoxLayout()
        color_row.setSpacing(self._spacing("sm_md", 12))

        color_cap = QLabel(self._copy("theme.immersive_color", "沉浸底色"))
        self._style(color_cap, color="text.secondary", font_size="sm")
        # 48px 容纳 4 个中文字(sm 字号),与下方「沉浸强度」标签同宽对齐
        # (旧值 28px 会截断成「沉浸颜」)
        color_cap.setFixedWidth(48)
        color_row.addWidget(color_cap)

        cur_mode = bg_svc.immersive_color
        self._imm_color_theme_btn = CyberButton(
            text=self._copy("theme.immersive_color_theme", "主题色"),
            variant="solid" if cur_mode == "theme" else "outlined",
        )
        self._imm_color_black_btn = CyberButton(
            text=self._copy("theme.immersive_color_black", "纯黑"),
            variant="solid" if cur_mode == "black" else "outlined",
        )
        self._imm_color_theme_btn.clicked.connect(
            lambda: self._on_immersive_color_clicked("theme")
        )
        self._imm_color_black_btn.clicked.connect(
            lambda: self._on_immersive_color_clicked("black")
        )
        color_row.addWidget(self._imm_color_theme_btn)
        color_row.addWidget(self._imm_color_black_btn)
        color_row.addStretch()
        bg_layout.addLayout(color_row)

        self._immersive_slider, self._immersive_val_label = \
            self._make_bg_slider_row(
                bg_layout,
                self._copy("theme.immersive_strength", "沉浸强度"),
                bg_svc.immersive_strength,
            )
        self._immersive_slider.valueChanged.connect(
            bg_svc.request_immersive_strength
        )
        self._immersive_slider.sliderReleased.connect(bg_svc.commit)
        # 沉浸关闭时滑块禁用 + 数值标签灰显(用户可感知不可调节)
        self._sync_immersive_slider(bg_svc.immersive)

        # 文件名跟随服务状态更新(滑块值不回设,避免与用户拖动打架)
        bg_svc.background_changed.connect(self._on_background_changed)
        # 沉浸状态变化：同步本页开关/滑块可用性
        bg_svc.immersive_changed.connect(self._on_immersive_prefs_changed)

        bg_tip = QLabel(self._copy(
            "theme.tip_background",
            "选择图片后可裁剪想要的区域；窗口改变比例时会围绕选区自动适应；更换图片会删除旧图片文件",
        ))
        self._style(bg_tip, color="text.tertiary", font_size="micro")
        bg_layout.addWidget(bg_tip)

        layout.addWidget(bg_card)

        # ── 启动设置 ──
        startup_card = CyberCard(title=self._copy("theme.card_startup", "启动设置"))
        startup_layout = startup_card.content_layout()
        startup_layout.setContentsMargins(16, 28, 16, 16)
        startup_layout.setSpacing(12)

        # 开启动画开关
        splash_row = QHBoxLayout()
        splash_row.setSpacing(10)

        splash_cb = QCheckBox(self._copy("theme.label_splash", "显示开启动画 (像素 RELIC)"))
        splash_cb.setChecked(True)
        splash_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        # 复杂 QSS(多选择器)走 raw 通道
        self._style(
            splash_cb,
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
                f"QCheckBox:hover {{ color: {self._color('accent.secondary')}; }}"
            ),
        )
        splash_row.addWidget(splash_cb)

        preview_btn = CyberButton(text=self._copy("theme.btn_preview", "预览"), variant="ghost")
        preview_btn.setFixedWidth(60)
        preview_btn.setToolTip(self._copy("theme.tip_preview", "预览开启动画效果"))
        preview_btn.clicked.connect(lambda: self._preview_splash())
        splash_row.addWidget(preview_btn)

        splash_row.addStretch()
        startup_layout.addLayout(splash_row)

        layout.addWidget(startup_card)

        # ── 像素字体编辑器 ──
        editor_card = CyberCard(title=self._copy("theme.card_pixel_font", "像素字体编辑器"))
        editor_layout = editor_card.content_layout()
        editor_layout.setContentsMargins(12, 24, 12, 12)
        editor_layout.setSpacing(8)

        try:
            from core.widgets.pixel_font_editor import PixelFontEditorPanel
            editor_panel = PixelFontEditorPanel()
            editor_layout.addWidget(editor_panel)
        except Exception as e:
            import traceback
            # 控制台输出完整错误信息（供开发调试）
            print(f"[ThemePage] 像素字体编辑器加载失败: {e}", flush=True)
            traceback.print_exc()
            # UI 仅显示简短提示，不暴露内部细节
            err_lbl = QLabel(self._copy("theme.err_load_failed", "加载失败: {error}", error=str(e)))
            self._style(err_lbl, color="semantic.warning", font_size="sm")
            err_lbl.setWordWrap(True)
            editor_layout.addWidget(err_lbl)

        layout.addWidget(editor_card)

        layout.addStretch()

        return container

    # ════════════════════════════════════
    #  背景图卡片辅助
    # ════════════════════════════════════

    def _make_bg_slider_row(
        self,
        parent_layout,
        caption: str,
        initial: int,
    ) -> tuple[QSlider, QLabel]:
        """构建一行「标题 + 滑块(0-100) + 数值」，返回 (滑块, 数值标签)。"""
        row = QHBoxLayout()
        row.setSpacing(12)

        cap_lbl = QLabel(caption)
        self._style(cap_lbl, color="text.secondary", font_size="sm")
        cap_lbl.setFixedWidth(48)
        row.addWidget(cap_lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(int(initial))
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(10)
        slider.installEventFilter(self._wheel_filter)

        # QSS 走 callable 注册,切换预设时由 on_theme_change 自动重放
        self._style(slider, raw=self._slider_qss)
        row.addWidget(slider, stretch=1)

        val_label = QLabel(str(int(initial)))
        self._style(
            val_label,
            color="accent.primary",
            font_size="md",
            font_weight="bold",
            raw="font-family: monospace;",
        )
        val_label.setFixedWidth(36)
        val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(val_label)

        # 数值标签随滑块实时更新（外部业务连接由调用方另行添加）
        slider.valueChanged.connect(lambda v: val_label.setText(str(v)))

        parent_layout.addLayout(row)
        return slider, val_label

    def _on_select_bg(self) -> None:
        """打开文件对话框 → 裁剪对话框 → 导入背景原图。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._copy("theme.dlg_select_bg", "选择背景图片"),
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return

        # 主窗口宽高比（锁定比例裁剪用；取不到时给个常见值）
        win = self.window()
        ratio = (
            win.width() / win.height()
            if win is not None and win.height() > 0 else 1.4
        )

        dlg = CyberImageCropDialog(
            path, window_ratio=ratio, default_locked=True, parent=self
        )
        if not dlg.is_valid:
            print("[ThemePage] 图片无法加载或格式不支持", flush=True)
            return
        if dlg.exec() != QDialog.DialogCode.Accepted:
            # 用户取消：不产生任何改动
            return

        from core.services.background_service import BackgroundService
        ok = BackgroundService.instance().import_image(
            path, list(dlg.crop_rect) if dlg.crop_rect else None
        )
        if not ok:
            print("[ThemePage] 背景图设置失败:格式不支持或复制失败", flush=True)

    def _on_clear_bg(self) -> None:
        """清除背景图。"""
        from core.services.background_service import BackgroundService
        BackgroundService.instance().clear_background()

    def _on_background_changed(
        self, source: str, crop, opacity: int, blur: int
    ) -> None:
        """服务状态变化：更新文件名标签。"""
        if self._bg_file_label is not None:
            self._bg_file_label.setText(
                Path(source).name if source
                else self._copy("theme.bg_none", "未设置")
            )

    def _sync_immersive_slider(self, enabled: bool) -> None:
        """同步沉浸强度滑块/数值标签的可用状态。

        沉浸关闭时滑块禁用,数值标签一并灰显(text.tertiary),
        与滑块 QSS 的 :disabled 伪状态一起给用户明确的「不可调节」感知。
        """
        if self._immersive_slider is not None:
            self._immersive_slider.setEnabled(enabled)
        if self._immersive_val_label is not None:
            self._style(
                self._immersive_val_label,
                color="accent.primary" if enabled else "text.tertiary",
                font_size="md",
                font_weight="bold",
                raw="font-family: monospace;",
            )

    def _on_immersive_prefs_changed(
        self, enabled: bool, strength: int, color_mode: str = "theme"
    ) -> None:
        """沉浸状态变化：同步开关勾选与强度滑块可用状态。

        外部（启动恢复/其它页面操作）引发的变化才需要这里同步；
        blockSignals 包住 setChecked，避免再次触发 set_immersive。
        签名与 BackgroundService.immersive_changed(bool, int, str) 对齐。
        """
        if self._immersive_cb is not None:
            self._immersive_cb.blockSignals(True)
            self._immersive_cb.setChecked(enabled)
            self._immersive_cb.blockSignals(False)
        self._sync_immersive_slider(enabled)

    def _on_immersive_color_clicked(self, mode: str) -> None:
        """沉浸底色按钮被点击：调服务切换 + 立即同步按钮 variant。

        立即同步避免等信号往返,提供即时视觉反馈；
        服务发的 immersive_color_changed 信号会被 AppShell 接收刷新 UI。
        """
        from core.services.background_service import BackgroundService
        BackgroundService.instance().set_immersive_color(mode)
        if self._imm_color_theme_btn is not None:
            self._imm_color_theme_btn.variant = (
                "solid" if mode == "theme" else "outlined"
            )
        if self._imm_color_black_btn is not None:
            self._imm_color_black_btn.variant = (
                "solid" if mode == "black" else "outlined"
            )

    def _on_preset_clicked(self, preset_name: str) -> None:
        """预设主题按钮被点击:统一走 ThemeManager.switch_preset。

        ThemeManager 内部: load_preset → save → emit theme_changed,
        AppShell 订阅信号后自动 refresh_theme(所有页面 on_theme_change
        重放 QSS 配方,滑块/复选框颜色一并刷新)。
        """
        from core.theme_manager import ThemeManager

        ok = ThemeManager.instance().switch_preset(preset_name)
        if not ok:
            print(f"[ThemePage] 切换预设失败: {preset_name}", flush=True)
            return

        self._current_preset = preset_name

        # 更新按钮选中状态
        if self._preset_cyber_btn is not None:
            self._preset_cyber_btn.variant = (
                "solid" if preset_name == "cyberpunk" else "outlined"
            )
        if self._preset_glass_btn is not None:
            self._preset_glass_btn.variant = (
                "solid" if preset_name == "glassmorphism" else "outlined"
            )

    def _slider_qss(self) -> str:
        """滑块 QSS 构建器(含 :disabled 灰显)。

        以 callable 形式注册进 _style(raw=...),切换预设时由
        PageBase.on_theme_change() 重放,无需手动刷新。
        禁用态灰显用于沉浸强度滑块(沉浸关闭时禁用)。
        """
        accent = self._color("accent.primary")
        disabled = self._color("text.tertiary")
        track_h = self._spacing("xs", 4) + 2
        handle_size = self._spacing("sm", 8) + 4
        handle_radius = handle_size // 2
        return (
            f"QSlider::groove:horizontal {{"
            f"  background: {self._color('components.progress.track_bg')};"
            f"  height: {track_h}px;"
            f"  border-radius: {track_h // 2}px;"
            f"}}"
            f"QSlider::handle:horizontal {{"
            f"  background: {accent};"
            f"  width: {handle_size}px;"
            f"  height: {handle_size}px;"
            f"  margin: -{self._spacing('xs', 4) + 1}px 0;"
            f"  border-radius: {handle_radius}px;"
            f"}}"
            f"QSlider::handle:horizontal:hover {{"
            f"  background: {self._color('accent.secondary')};"
            f"}}"
            f"QSlider::sub-page:horizontal {{"
            f"  background: {accent};"
            f"  border-radius: {track_h // 2}px;"
            f"}}"
            f"QSlider::handle:horizontal:disabled {{"
            f"  background: {disabled};"
            f"}}"
            f"QSlider::sub-page:horizontal:disabled {{"
            f"  background: {disabled};"
            f"}}"
        )

    def on_enter(self):
        """进入主题页:从 ui_prefs.json 读最新透明度,同步滑块位置。

        用 blockSignals 包住 setValue,避免 on_enter 的同步触发
        _on_opacity_changed(否则会把刚读出来的值再写一次,虽然内容相同)。
        """
        try:
            from core.services.ui_prefs import load_window_opacity
            saved = load_window_opacity()
        except Exception:
            saved = 100

        self._opacity_pct = saved
        if self._opacity_slider is not None:
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(saved)
            self._opacity_slider.blockSignals(False)
        if self._opacity_label is not None:
            self._opacity_label.setText(f"{saved}%")

        # 同步背景图卡片(文件名/透明度/模糊度)
        try:
            from core.services.background_service import BackgroundService
            bg = BackgroundService.instance()
            for slider, val in (
                (self._bg_opacity_slider, bg.opacity),
                (self._bg_blur_slider, bg.blur),
            ):
                if slider is not None:
                    slider.blockSignals(True)
                    slider.setValue(val)
                    slider.blockSignals(False)
            if self._bg_opacity_label is not None:
                self._bg_opacity_label.setText(str(bg.opacity))
            if self._bg_blur_label is not None:
                self._bg_blur_label.setText(str(bg.blur))
            self._on_background_changed(
                bg.source, bg.crop, bg.opacity, bg.blur
            )

            # 同步沉浸模式控件（勾选/滑块值/可用性/数值）
            if self._immersive_cb is not None:
                self._immersive_cb.blockSignals(True)
                self._immersive_cb.setChecked(bg.immersive)
                self._immersive_cb.blockSignals(False)
            if self._immersive_slider is not None:
                self._immersive_slider.blockSignals(True)
                self._immersive_slider.setValue(bg.immersive_strength)
                self._immersive_slider.blockSignals(False)
            self._sync_immersive_slider(bg.immersive)
            if self._immersive_val_label is not None:
                self._immersive_val_label.setText(
                    str(bg.immersive_strength)
                )
            # 同步沉浸底色按钮选中状态
            mode = bg.immersive_color
            if self._imm_color_theme_btn is not None:
                self._imm_color_theme_btn.variant = (
                    "solid" if mode == "theme" else "outlined"
                )
            if self._imm_color_black_btn is not None:
                self._imm_color_black_btn.variant = (
                    "solid" if mode == "black" else "outlined"
                )
        except Exception:
            pass

    def _on_opacity_changed(self, value: int) -> None:
        """滑块拖动:实时调主窗口透明度 + 落盘到 ui_prefs.json。

        行为:
          - 调 AppShell.apply_window_opacity()(主窗口立即变透明)
          - 调 save_window_opacity()(立即写盘,无需重启)
        限制:
          - 30 以下 / 100 以上都会被 apply_window_opacity 自动钳制
          - 若 _app_shell 还没注入(罕见),只写盘不动 UI
        """
        self._opacity_pct = value
        if self._opacity_label is not None:
            self._opacity_label.setText(f"{value}%")
        if self._app_shell is not None:
            self._app_shell.apply_window_opacity(value)
        try:
            from core.services.ui_prefs import save_window_opacity
            save_window_opacity(value)
        except Exception:
            pass  # 写盘失败不阻塞 UI 调整

    def _preview_splash(self) -> None:
        """预览开启动画。"""
        print("[ThemePage] 预览按钮被点击", flush=True)
        try:
            from core.widgets.splash_screen import CyberSplashScreen
            parent = self.window()  # AppShell QMainWindow
            print("[ThemePage] 创建 CyberSplashScreen (embedded)...", flush=True)

            def _on_finished():
                if self._preview_splash_instance:
                    self._preview_splash_instance.close()
                    self._preview_splash_instance.deleteLater()
                    self._preview_splash_instance = None

            self._preview_splash_instance = CyberSplashScreen(
                parent=parent, enabled=True, on_finished=_on_finished)
            self._preview_splash_instance.setGeometry(
                0, 0, parent.width(), parent.height())
            self._preview_splash_instance.show()
            print("[ThemePage] splash.show() 已调用", flush=True)
        except Exception as e:
            print(f"[ThemePage] 预览失败: {e}", flush=True)
