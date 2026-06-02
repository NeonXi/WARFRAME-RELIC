"""修复背景图功能区样式问题"""

import re

# 读取 management_panel.py
with open('core/management_panel.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复日志面板 QTextEdit 的背景色（使用条件化背景）
old_log_style = '''        log_area = QTextEdit()
        log_area.setReadOnly(True)
        log_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {theme.panel_deeper}; color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px; padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {theme.panel_bg}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.border}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)'''

new_log_style = '''        log_area = QTextEdit()
        log_area.setReadOnly(True)
        log_area.setObjectName("LogArea")
        log_area.setStyleSheet(f"""
            QTextEdit#LogArea {{
                color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 4px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                font-size: 11px; padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {theme.panel_bg}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.border}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)'''

content = content.replace(old_log_style, new_log_style)

# 修复日志面板按钮的背景色
old_btn_style = '''        btn_close_log.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.card_bg}; color: {theme.text_dim};
                border: 1px solid {theme.border}; border-radius: 4px;
                padding: 6px; font-size: 12px;'''

new_btn_style = '''        btn_close_log.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.get_panel_bg_color(180)}; color: {theme.text_dim};
                border: 1px solid {theme.border}; border-radius: 4px;
                padding: 6px; font-size: 12px;'''

content = content.replace(old_btn_style, new_btn_style)

# 保存修改
with open('core/management_panel.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("management_panel.py 已修复")

# 现在修复样式表中日志区域的样式
with open('core/stylesheet.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在有背景图时添加日志区域的半透明背景
old_bg_style = '''/* 5. 兼容 QMainWindow */
QMainWindow#MainWindow {
    background-image: url("{escaped_path}");
    background-repeat: no-repeat;
    background-position: center center;
    background-size: cover;
}
"""'''

new_bg_style = '''/* 5. 日志区域 - 半透明背景 */
QTextEdit#LogArea {
    background-color: rgba(5, 5, 20, {panel_alpha});
}

/* 6. 兼容 QMainWindow */
QMainWindow#MainWindow {
    background-image: url("{escaped_path}");
    background-repeat: no-repeat;
    background-position: center center;
    background-size: cover;
}
"""'''

content = content.replace(old_bg_style, new_bg_style)

# 保存修改
with open('core/stylesheet.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("stylesheet.py 已修复")
