import re

# 读取原始文件
with open('core/theme_panel.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 tips 之后、色块滚动区之前添加背景图功能区
background_section = '''
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

'''

# 在 "色块滚动区" 之前插入背景图功能区
content = content.replace(
    '        # 色块滚动区',
    background_section + '        # 色块滚动区'
)

# 添加背景图相关的方法
background_methods = '''
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
                self._on_theme_changed()
            else:
                self._add_log("error", S("theme", "bg_upload_failed"))

    def _on_clear_background(self):
        """清除背景图"""
        theme.clear_background_image()
        self._on_theme_changed()
        self._add_log("info", S("theme", "bg_cleared"))

    def _on_opacity_changed(self, value):
        """透明度变化"""
        theme.background_opacity = value / 100.0
        self._on_theme_changed()

    def _on_blur_changed(self, value):
        """模糊度变化"""
        theme.background_blur = value
        self._on_theme_changed()

'''

# 在 "样式刷新" 之前插入背景图方法
content = content.replace(
    '    # ============================================================\n    # 样式刷新',
    background_methods + '    # ============================================================\n    # 样式刷新'
)

# 保存修改
with open('core/theme_panel.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('背景图功能区已添加')
