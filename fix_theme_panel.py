import re

# 读取文件
with open('core/theme_panel.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加缺失的导入
content = content.replace(
    'QComboBox,\n)',
    'QComboBox, QSlider, QFileDialog,\n)'
)

content = content.replace(
    'from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve',
    'from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal'
)

# 添加 ColorSwatch 类
color_swatch_class = '''
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

'''

content = content.replace(
    'from PyQt6.QtGui import QColor\n\nfrom core.constants',
    'from PyQt6.QtGui import QColor\n\nimport os\n\n' + color_swatch_class + 'from core.constants'
)

# 修改色块创建代码
content = content.replace(
    '''swatch = QLabel("　")
                swatch.setFixedSize(48, 18)
                swatch.setStyleSheet(
                    f"background-color: {color}; border: none; border-radius: 2px;")
                swatch.setCursor(Qt.CursorShape.PointingHandCursor)
                swatch.mousePressEvent = lambda e, k=json_key, s=swatch: self._pick_color(k, s)
                item_layout.addWidget(swatch)''',
    '''swatch = ColorSwatch(json_key, color)
                swatch.setFixedSize(48, 18)
                swatch.color_picked.connect(lambda k, s=swatch: self._pick_color(k, s))
                item_layout.addWidget(swatch)'''
)

# 修改 S.format 调用
content = content.replace(
    'S.format("theme", "color_pick_title", key=json_key)',
    'S.format("theme", "color_pick_title", field=json_key)'
)

# 在 _build_ui 方法中的 "tip" 之后、"色块滚动区" 之前添加背景图功能区
# 找到正确的位置
pattern = r'(tip.setWordWrap\(True\)\n        panel_layout.addWidget\(tip\))\n\n        # 色块滚动区'
replacement = r'\1\n\n        # ── 自定义背景图 ──\n        bg_group = QWidget()\n        bg_group.setStyleSheet(f"background: {theme.panel_deeper}; border: 1px solid {theme.border}; border-radius: 4px;")\n        bg_group_layout = QVBoxLayout(bg_group)\n        bg_group_layout.setContentsMargins(8, 8, 8, 8)\n        bg_group_layout.setSpacing(6)\n        \n        # 背景图标题\n        bg_title = QLabel("自定义背景")\n        bg_title.setStyleSheet(f"color: {theme.cyber_cyan}; font-weight: bold; font-size: 12px;")\n        bg_group_layout.addWidget(bg_title)\n        \n        # 上传按钮\n        self._btn_upload_bg = QPushButton(S("button", "upload_bg"))\n        self._btn_upload_bg.setObjectName("actionBtn")\n        self._btn_upload_bg.setStyleSheet(f"""\n            QPushButton {{\n                background-color: {theme.card_bg}; color: {theme.text};\n                border: 1px solid {theme.border}; border-radius: 3px;\n                padding: 4px 8px; font-size: 11px;\n            }}\n            QPushButton:hover {{ border-color: {theme.cyber_cyan}; }}\n        """)\n        self._btn_upload_bg.clicked.connect(self._on_upload_background)\n        bg_group_layout.addWidget(self._btn_upload_bg)\n        \n        # 透明度滑块\n        opacity_row = QHBoxLayout()\n        opacity_lbl = QLabel(S("theme", "opacity"))\n        opacity_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")\n        opacity_row.addWidget(opacity_lbl)\n        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)\n        self._opacity_slider.setRange(0, 100)\n        self._opacity_slider.setValue(int(theme.background_opacity * 100))\n        self._opacity_slider.setStyleSheet(f"""\n            QSlider::groove:horizontal {{\n                height: 4px; background: {theme.panel_bg}; border-radius: 2px;\n            }}\n            QSlider::handle:horizontal {{\n                background: {theme.cyber_cyan}; width: 12px; height: 12px;\n                border-radius: 6px; margin: -4px 0;\n            }}\n        """)\n        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)\n        opacity_row.addWidget(self._opacity_slider)\n        bg_group_layout.addLayout(opacity_row)\n        \n        # 模糊度滑块\n        blur_row = QHBoxLayout()\n        blur_lbl = QLabel(S("theme", "blur"))\n        blur_lbl.setStyleSheet(f"color: {theme.text_dim}; font-size: 11px;")\n        blur_row.addWidget(blur_lbl)\n        self._blur_slider = QSlider(Qt.Orientation.Horizontal)\n        self._blur_slider.setRange(0, 50)\n        self._blur_slider.setValue(theme.background_blur)\n        self._blur_slider.setStyleSheet(f"""\n            QSlider::groove:horizontal {{\n                height: 4px; background: {theme.panel_bg}; border-radius: 2px;\n            }}\n            QSlider::handle:horizontal {{\n                background: {theme.cyber_cyan}; width: 12px; height: 12px;\n                border-radius: 6px; margin: -4px 0;\n            }}\n        """)\n        self._blur_slider.valueChanged.connect(self._on_blur_changed)\n        blur_row.addWidget(self._blur_slider)\n        bg_group_layout.addLayout(blur_row)\n        \n        # 清除按钮\n        self._btn_clear_bg = QPushButton(S("button", "clear_bg"))\n        self._btn_clear_bg.setObjectName("dangerBtn")\n        self._btn_clear_bg.setStyleSheet(f"""\n            QPushButton {{\n                background-color: transparent; color: {theme.cyber_red};\n                border: 1px solid {theme.cyber_red}; border-radius: 3px;\n                padding: 2px 8px; font-size: 10px;\n            }}\n            QPushButton:hover {{ background-color: rgba(255, 0, 0, 0.1); }}\n        """)\n        self._btn_clear_bg.clicked.connect(self._on_clear_background)\n        bg_group_layout.addWidget(self._btn_clear_bg)\n        \n        panel_layout.addWidget(bg_group)\n\n        # 色块滚动区'

content = re.sub(pattern, replacement, content)

# 添加背景图相关方法
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

print('修复完成')
