"""
全局样式表生成模块。
使用 ThemeConfig 单例动态生成 QSS，供管理面板和所有弹窗复用。
"""
from core.constants import theme


def build_stylesheet() -> str:
    """基于当前主题配色，生成完整的 Qt 样式表。"""
    t = theme  # ThemeConfig 单例
    return f"""
QWidget {{
    background-color: {t.panel_bg};
    color: {t.text};
    font-family: "Microsoft YaHei";
    font-size: 13px;
}}
QGroupBox {{
    border: 1px solid {t.border};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: {t.cyber_yellow};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}
QLabel {{
    color: {t.label_default};
}}
QLabel#titleLabel {{
    font-size: 18px;
    font-weight: bold;
    color: {t.cyber_yellow};
}}
QLabel#statValue {{
    color: {t.cyber_cyan};
    font-weight: bold;
}}
QLabel#statLabel {{
    color: {t.text_dim};
}}
QPushButton {{
    background-color: {t.btn_default_bg};
    color: {t.btn_default_text};
    border: 1px solid {t.btn_default_border};
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    min-height: 36px;
    text-align: center;
}}
QPushButton:hover {{
    background-color: {t.btn_hover_bg};
    border-color: {t.btn_hover_border};
    color: {t.btn_hover_text};
}}
QPushButton:pressed {{
    background-color: {t.btn_pressed_bg};
}}
QPushButton:disabled {{
    background-color: {t.btn_disabled_bg};
    color: {t.btn_disabled_text};
    border-color: {t.btn_disabled_border};
}}
QPushButton#primaryBtn {{
    background-color: {t.primary_bg};
    color: {t.primary_text};
    border: 1px solid {t.primary_border};
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    min-height: 36px;
    text-align: center;
}}
QPushButton#primaryBtn:hover {{
    background-color: {t.primary_hover_bg};
    color: {t.primary_text};
    border-color: {t.primary_hover_border};
}}
QPushButton#primaryBtn:disabled {{
    background-color: {t.primary_disabled_bg};
    color: {t.primary_disabled_text};
    border-color: {t.primary_disabled_border};
}}
QPushButton#actionBtn {{
    background-color: {t.btn_default_bg};
    color: {t.btn_default_text};
    border: 1px solid {t.btn_default_border};
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    min-height: 36px;
    text-align: center;
}}
QPushButton#actionBtn:hover {{
    background-color: {t.btn_hover_bg};
    color: {t.btn_hover_text};
    border-color: {t.btn_hover_border};
}}
QPushButton#actionBtn:disabled {{
    background-color: {t.btn_disabled_bg};
    color: {t.btn_disabled_text};
    border-color: {t.btn_disabled_border};
}}
QPushButton#dangerBtn {{
    border-color: {t.danger_border};
    color: {t.danger_text};
}}
QPushButton#dangerBtn:hover {{
    background-color: {t.danger_hover_bg};
    color: {t.danger_hover_text};
}}
QPushButton#successBtn {{
    border-color: {t.success_border};
    color: {t.success_text};
}}
QPushButton#successBtn:hover {{
    background-color: {t.success_hover_bg};
    color: {t.success_hover_text};
}}
QProgressBar {{
    border: 1px solid {t.border};
    border-radius: 3px;
    background-color: {t.card_bg};
    text-align: center;
    color: {t.cyber_yellow};
}}
QProgressBar::chunk {{
    background-color: {t.cyber_yellow};
    border-radius: 2px;
}}
QFrame#sep {{
    background-color: {t.border};
    max-height: 1px;
}}
"""


def build_dialog_button_style() -> str:
    """弹窗 OK 按钮样式。"""
    t = theme
    return f"""
QPushButton {{
    background-color: {t.card_bg};
    color: {t.cyber_yellow};
    border: 1px solid {t.cyber_yellow};
    border-radius: 4px;
    padding: 6px 24px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {t.btn_hover_bg};
    color: {t.cyber_cyan};
}}
"""
