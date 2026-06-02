"""
WARFRAME-RELIC 主题配色侧滑面板
- 色块编辑、预设切换、动画
- 作为 ManagementPanel 的子面板存在
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QColorDialog, QMessageBox,
    QComboBox, QSlider, QFileDialog,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

import os


class ColorSwatch(QLabel):
    """可点击的颜色色块控件"""
    color_picked = pyqtSignal(str)  # 发射 json_key
    
    def __init__(self, json_key: str, color: str):
        super().__init__("　")
        self._json_key = json_key
        self.setStyleSheet(
            f"background-color: {color}; border: none; border-radius: 2px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def mousePressEvent(self, event):
        """鼠标点击时发射信号"""
        self.color_picked.emit(self._json_key)
    
    def update_color(self, color: str):
        """更新颜色显示"""
        self.setStyleSheet(
            f"background-color: {color}; border: none; border-radius: 2px;")

from core.constants import theme, ThemeConfig
from core.theme_fields import THEME_FIELDS
from data.ui_strings import S





# ============================================================
# 主题侧滑面板
# ============================================================

class ThemePanel:
    """管理 ManagementPanel 中的主题配色侧滑面板。

    不继承 QWidget，而是管理一个嵌入到 ManagementPanel 布局中的 QWidget。
    通过回调与 ManagementPanel 通信。
    """

    PANEL_WIDTH = 320

    def __init__(self, parent_widget, on_theme_changed, add_log):
        """
        Args:
            parent_widget: ManagementPanel 实例
            on_theme_changed: 主题变更回调 (无参数)
            add_log: 日志回调 (log_type, msg)
        """
        self._parent = parent_widget
        self._on_theme_changed = on_theme_changed
        self._add_log = add_log

        self._theme_swatches = {}   # json_key → swatch QLabel
        self._theme_draft = {}      # 未保存的颜色修改
        self._expanded = False
        self._anim = None
        # 添加防抖定时器和防重叠标志位
        self._opacity_debounce_timer = None
        self._blur_debounce_timer = None
        self._opacity_applying = False
        self._blur_applying = False

        # 构建面板
        self._panel = QWidget()
        self._panel.setFixedWidth(0)
        self._panel.setStyleSheet(f"background-color: {theme.panel_darkest};")
        self._panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._build_ui()

    @property
    def widget(self):
        """返回实际的 QWidget。"""
        return self._panel

    @property
    def width(self):
        return self._panel.width()

    @property
    def is_expanded(self):
        return self._expanded

    @property
    def swatches(self):
        return self._theme_swatches

    @property
    def draft(self):
        return self._theme_draft

    # ============================================================
    # UI 构建
    # ============================================================

    def _build_ui(self):
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        self._title_lbl = QLabel(S("theme", "panel_title"))
        self._title_lbl.setStyleSheet(f"color: {theme.cyber_yellow}; font-size: 14px; font-weight: bold;")
        title_row.addWidget(self._title_lbl); title_row.addStretch()
        self._btn_close = QPushButton("✕")
        self._btn_close.setFixedSize(28, 28)
        self._btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {theme.text_dim}; border: none;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ color: {theme.cyber_red}; }}
        """)
        self._btn_close.clicked.connect(self.collapse)
        title_row.addWidget(self._btn_close)
        panel_layout.addLayout(title_row)

        # ── 预设主题一键切换 ──
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        self._preset_label = QLabel(S("theme", "preset_label"))
        self._preset_label.setStyleSheet(f"color: {theme.text}; font-size: 12px;")
        preset_row.addWidget(self._preset_label)

        self._preset_combo = QComboBox()
        self._preset_combo.wheelEvent = lambda e: e.ignore()  # 禁用滚轮切换
        self._preset_combo.setMinimumHeight(26)
        for pid, pinfo in ThemeConfig.PRESETS.items():
            self._preset_combo.addItem(pinfo["name"], pid)
        current_preset_name = theme.current_preset_name()
        idx = self._preset_combo.findText(current_preset_name)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.card_bg}; color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 3px;
                padding: 2px 8px; font-size: 12px;
            }}
            QComboBox:hover {{ border-color: {theme.cyber_yellow}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {theme.card_bg}; color: {theme.text};
                border: 1px solid {theme.border}; selection-background-color: {theme.cyber_cyan};
            }}
        """)
        preset_row.addWidget(self._preset_combo, 1)

        self._btn_apply_preset = QPushButton(S("button", "apply_preset"))
        self._btn_apply_preset.setObjectName("primaryBtn")
        self._btn_apply_preset.clicked.connect(self._on_apply_preset)
        preset_row.addWidget(self._btn_apply_preset)
        panel_layout.addLayout(preset_row)

        tip = QLabel(S("hint", "theme_tip"))
        tip.setStyleSheet(f"color: {theme.text_dim}; font-size: 10px;")
        tip.setWordWrap(True)
        panel_layout.addWidget(tip)

        # ── 自定义背景图 ──
        bg_group = QWidget()
        bg_group.setStyleSheet(f"background: {theme.panel_deeper}; border: 1px solid {theme.border}; border-radius: 4px;")
        bg_group_layout = QVBoxLayout(bg_group)
        bg_group_layout.setContentsMargins(8, 8, 8, 8)
        bg_group_layout.setSpacing(6)
        
        # 背景图标题
        bg_title = QLabel("自定义背景")
        bg_title.setStyleSheet(f"color: {theme.cyber_cyan}; font-weight: bold; font-size: 12px;")
        bg_group_layout.addWidget(bg_title)
        
        # 上传按钮
        self._btn_upload_bg = QPushButton(S("button", "upload_bg"))
        self._btn_upload_bg.setObjectName("actionBtn")
        self._btn_upload_bg.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.card_bg}; color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 3px;
                padding: 4px 8px; font-size: 11px;
            }}
            QPushButton:hover {{ border-color: {theme.cyber_cyan}; }}
        """)
        self._btn_upload_bg.clicked.connect(self._on_upload_background)
        bg_group_layout.addWidget(self._btn_upload_bg)
        
        # 透明度滑块
        opacity_row = QHBoxLayout()
        opacity_lbl = QLabel(S("theme", "opacity"))
        opacity_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        opacity_row.addWidget(opacity_lbl)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setSingleStep(1)           # ★ 步长=1，100个离散档位
        self._opacity_slider.setPageStep(10)             # ★ 翻页步长=10
        self._opacity_slider.setValue(int(theme.background_opacity * 100))
        self._opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {theme.panel_bg}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {theme.cyber_cyan}; width: 12px; height: 12px;
                border-radius: 6px; margin: -4px 0;
            }}
        """)
        # 创建防抖定时器（不传 parent，因为 ThemePanel 不是 QWidget）
        self._opacity_debounce_timer = QTimer()
        self._opacity_debounce_timer.setSingleShot(True)
        self._opacity_debounce_timer.timeout.connect(self._apply_opacity_change)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self._opacity_slider)
        bg_group_layout.addLayout(opacity_row)
        
        # 模糊度滑块
        blur_row = QHBoxLayout()
        blur_lbl = QLabel(S("theme", "blur"))
        blur_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")
        blur_row.addWidget(blur_lbl)
        self._blur_slider = QSlider(Qt.Orientation.Horizontal)
        self._blur_slider.setRange(0, 50)
        self._blur_slider.setValue(theme.background_blur)
        self._blur_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {theme.panel_bg}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {theme.cyber_cyan}; width: 12px; height: 12px;
                border-radius: 6px; margin: -4px 0;
            }}
        """)
        # 创建防抖定时器（不传 parent，因为 ThemePanel 不是 QWidget）
        self._blur_debounce_timer = QTimer()
        self._blur_debounce_timer.setSingleShot(True)
        self._blur_debounce_timer.timeout.connect(self._apply_blur_change)
        self._blur_slider.valueChanged.connect(self._on_blur_changed)
        blur_row.addWidget(self._blur_slider)
        bg_group_layout.addLayout(blur_row)
        
        # 清除按钮
        self._btn_clear_bg = QPushButton(S("button", "clear_bg"))
        self._btn_clear_bg.setObjectName("dangerBtn")
        self._btn_clear_bg.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {theme.cyber_red};
                border: 1px solid {theme.cyber_red}; border-radius: 3px;
                padding: 2px 8px; font-size: 10px;
            }}
            QPushButton:hover {{ background-color: rgba(255, 0, 0, 0.1); }}
        """)
        self._btn_clear_bg.clicked.connect(self._on_clear_background)
        bg_group_layout.addWidget(self._btn_clear_bg)
        
        panel_layout.addWidget(bg_group)

        # 色块滚动区
        self._build_swatches(panel_layout)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton(S("button", "save_theme"))
        self._btn_save.setObjectName("primaryBtn")
        self._btn_save.clicked.connect(self._on_save)
        self._btn_reset = QPushButton(S("button", "reset_default"))
        self._btn_reset.setObjectName("actionBtn")
        self._btn_reset.clicked.connect(self._on_reset)
        self._btn_refresh = QPushButton(S("button", "refresh_preview"))
        self._btn_refresh.setObjectName("actionBtn")
        self._btn_refresh.clicked.connect(self._on_refresh_preview)
        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_reset)
        btn_row.addWidget(self._btn_refresh)
        panel_layout.addLayout(btn_row)

    def _build_swatches(self, panel_layout):
        self._swatch_scroll = QScrollArea()
        self._swatch_scroll.setWidgetResizable(True)
        self._swatch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._swatch_scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {theme.border}; "
            f"border-radius: 4px; background: {theme.panel_deeper}; }}")

        tw = QWidget()
        self._swatch_container = tw
        tw.setStyleSheet(f"background: {theme.panel_deeper};")
        tw_layout = QVBoxLayout(tw)
        tw_layout.setSpacing(6)

        categories = {}
        for jk, lbl, cat in THEME_FIELDS:
            if cat == "外链品牌":
                continue
            categories.setdefault(cat, []).append((jk, lbl))

        data = theme.to_dict()
        for cat_name, fields in categories.items():
            cat_lbl = QLabel(f"▸ {cat_name}")
            cat_lbl.setStyleSheet(
                f"color: {theme.cyber_cyan}; font-weight: bold; font-size: 13px; padding: 4px 0;")
            tw_layout.addWidget(cat_lbl)

            row = QHBoxLayout(); row.setSpacing(4); col_count = 0
            for json_key, label in fields:
                color = data.get(json_key, theme.panel_deeper)
                item = QWidget()
                item.setMinimumWidth(64)
                item_layout = QVBoxLayout(item)
                item_layout.setContentsMargins(2, 3, 2, 3)
                item_layout.setSpacing(3)

                swatch = ColorSwatch(json_key, color)
                swatch.setFixedSize(48, 18)
                swatch.color_picked.connect(lambda k, s=swatch: self._pick_color(k, s))
                item_layout.addWidget(swatch)

                name_lbl = QLabel(label)
                name_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 12px;")
                name_lbl.setWordWrap(True)
                item_layout.addWidget(name_lbl)

                row.addWidget(item)
                row.setStretchFactor(item, 1)
                self._theme_swatches[json_key] = swatch
                col_count += 1
                if col_count >= 3:
                    tw_layout.addLayout(row)
                    row = QHBoxLayout(); row.setSpacing(4); col_count = 0
            if col_count > 0:
                row.addStretch(); tw_layout.addLayout(row)
        tw_layout.addStretch()
        self._swatch_scroll.setWidget(tw)
        panel_layout.addWidget(self._swatch_scroll, 1)

    # ============================================================
    # 色块交互
    # ============================================================

    def _pick_color(self, json_key, swatch):
        current = theme.to_dict().get(json_key, theme.panel_deeper)
        color = QColorDialog.getColor(QColor(current), self._parent,
            S.format("theme", "color_pick_title", field=json_key))
        if color.isValid():
            hex_color = color.name()
            self._theme_draft[json_key] = hex_color
            swatch.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid {theme.border}; border-radius: 2px;")

    # ============================================================
    # 刷新 / 保存 / 重置 / 预设
    # ============================================================

    def _on_refresh_preview(self):
        if not self._theme_draft:
            QMessageBox.information(self._parent, S("theme", "prompt_title"),
                S("theme", "no_changes_preview"))
            return
        prev_preset = theme.active_preset
        theme.save(self._theme_draft)
        self._sync_preset_combo(prev_preset)
        self._on_theme_changed(change_type="full")

    def _on_save(self):
        if not self._theme_draft:
            QMessageBox.information(self._parent, S("theme", "prompt_title"),
                S("theme", "no_changes"))
            return
        prev_preset = theme.active_preset
        if theme.save(self._theme_draft):
            self._theme_draft = {}
            self._sync_preset_combo(prev_preset)
            self._on_theme_changed(change_type="full")
            preset_name = theme.current_preset_name()
            if prev_preset != theme.active_preset:
                self._add_log("ok", S.format("theme", "saved_to", name=preset_name))
            else:
                self._add_log("ok", S.format("theme", "saved", name=preset_name))
        else:
            self._add_log("error", S("theme", "save_failed"))

    def _sync_preset_combo(self, prev_preset: str):
        """如果预设被自动切换了，同步下拉框显示。"""
        if theme.active_preset != prev_preset:
            idx = self._preset_combo.findData(theme.active_preset)
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)

    def _on_reset(self):
        reply = QMessageBox.question(
            self._parent, S("theme", "reset_confirm_title"),
            S.format("theme", "reset_confirm_msg", name=theme.current_preset_name()),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        theme.reset()
        self._theme_draft = {}
        self._on_theme_changed(change_type="full")
        QMessageBox.information(self._parent, S("theme", "reset_done_title"),
            S.format("theme", "reset_done_msg", name=theme.current_preset_name()))

    def _on_apply_preset(self):
        preset_id = self._preset_combo.currentData()
        if not preset_id:
            return
        preset_name = ThemeConfig.PRESETS[preset_id]["name"]
        if theme.apply_preset(preset_id):
            self._theme_draft = {}
            self._on_theme_changed(change_type="full")
            # 确保下拉框停留在当前选择的预设
            idx = self._preset_combo.findData(preset_id)
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)
            self._add_log("ok", S.format("theme", "preset_applied", name=preset_name))
        else:
            self._add_log("error", S("theme", "preset_failed"))


    # ============================================================
    # 背景图处理
    # ============================================================

    def _on_upload_background(self):
        """上传背景图"""
        file_path, _ = QFileDialog.getOpenFileName(
            self._parent,
            S("theme", "select_bg_title"),
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if file_path:
            if theme.set_background_image(file_path):
                self._add_log("ok", S("theme", "bg_uploaded"))
                self._on_theme_changed(change_type="full")
            else:
                self._add_log("error", S("theme", "bg_upload_failed"))

    def _on_clear_background(self):
        """清除背景图"""
        theme.clear_background_image()
        self._on_theme_changed(change_type="full")
        self._add_log("info", S("theme", "bg_cleared"))

    def _on_opacity_changed(self, value):
        """透明度变化（防抖）—— 值已量化为 0-100 整数"""
        self._pending_opacity = value / 100.0
        self._opacity_debounce_timer.start(80)           # ★ 80ms 防抖（缓存命中极快）

    def _apply_opacity_change(self):
        """应用透明度更改（防重叠）"""
        if self._opacity_applying:
            return
        
        self._opacity_applying = True
        try:
            if hasattr(self, '_pending_opacity'):
                # ★ 量化为 0-100 档位（确保 bg_key 缓存命中）
                theme._bg_opacity = round(max(0.0, min(1.0, self._pending_opacity)), 2)
                # 使用智能刷新策略（量化缓存命中）
                self._on_theme_changed(change_type="opacity")
                del self._pending_opacity
        finally:
            self._opacity_applying = False

    def _on_blur_changed(self, value):
        """模糊度变化（防抖）"""
        self._pending_blur = value
        self._blur_debounce_timer.start(80)              # ★ 80ms 防抖

    def _apply_blur_change(self):
        """应用模糊度更改（防重叠）"""
        if self._blur_applying:
            return
        
        self._blur_applying = True
        try:
            if hasattr(self, '_pending_blur'):
                theme._bg_blur = max(0, min(50, self._pending_blur))
                self._on_theme_changed(change_type="blur")
                del self._pending_blur
        finally:
            self._blur_applying = False

    def _on_theme_changed(self, change_type="full"):
        """主题变更回调
        
        Args:
            change_type: 变更类型
                - "full": 完整刷新（预设切换、背景图上传）
                - "opacity": 只刷新透明度相关
                - "blur": 只刷新模糊度相关
                - "color": 颜色变更（需要刷新色块）
        """
        self._on_theme_changed_internal(change_type)

    # ============================================================
    # 样式刷新
    # ============================================================

    def refresh_inline_styles(self):
        """刷新主题面板中所有颜色相关的内联样式。"""
        t = theme

        self._panel.setStyleSheet(f"background-color: {t.panel_darkest};")

        # 标题
        self._title_lbl.setStyleSheet(f"color: {t.cyber_yellow}; font-size: 14px; font-weight: bold;")

        # 预设方案标签
        self._preset_label.setStyleSheet(f"color: {t.text}; font-size: 12px;")

        # 同步预设下拉框
        current_name = theme.current_preset_name()
        idx = self._preset_combo.findText(current_name)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)

        # 关闭按钮
        self._btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {t.text_dim}; border: none;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ color: {t.cyber_red}; }}
        """)

        # 预设下拉框
        self._preset_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {t.card_bg}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 3px;
                padding: 2px 8px; font-size: 12px;
            }}
            QComboBox:hover {{ border-color: {t.cyber_yellow}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {t.card_bg}; color: {t.text};
                border: 1px solid {t.border}; selection-background-color: {t.cyber_cyan};
            }}
        """)

        # 色块滚动区
        self._swatch_scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {t.border}; "
            f"border-radius: 4px; background: {t.panel_deeper}; }}")
        self._swatch_container.setStyleSheet(f"background: {t.panel_deeper};")

    def rebuild_swatches(self):
        """刷新所有色块颜色。"""
        data = theme.to_dict()
        for json_key, swatch in self._theme_swatches.items():
            color = data.get(json_key, theme.panel_deeper)
            swatch.setStyleSheet(
                f"background-color: {color}; border: none; border-radius: 2px;")

    # ============================================================
    # 展开 / 折叠动画
    # ============================================================

    def toggle(self):
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if self._expanded:
            return
        self._expanded = True
        self._run_anim(0, self.PANEL_WIDTH)

    def collapse(self):
        if not self._expanded:
            return
        self._expanded = False
        self._run_anim(self._panel.width(), 0)

    def _run_anim(self, start_w, end_w):
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        self._anim = QPropertyAnimation(self._panel, b"minimumWidth")
        self._anim.setDuration(250)
        self._anim.setStartValue(start_w)
        self._anim.setEndValue(end_w)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)
        self._anim.start()

    def _on_anim_step(self, w):
        self._panel.setFixedWidth(w)
        self._panel.setVisible(w > 0)

    def on_resize(self, log_panel_visible):
        """动画步骤回调：同时更新父窗口宽度。"""
        extra = self._panel.width() + (420 if log_panel_visible else 0)
        self._parent.resize(580 + extra, self._parent.height())
