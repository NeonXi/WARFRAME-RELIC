"""
全局样式表生成模块。
使用 ThemeConfig 单例动态生成 QSS，供管理面板和所有弹窗复用。
支持背景图、透明度、模糊度设置。
"""
import os
from core.theme_config import theme


class StyleSheetBuilder:
    """样式表生成器（带分层缓存机制）"""
    
    _base_cache = {}  # 基础样式缓存（不包含背景图）
    _bg_cache = {}    # 背景图样式缓存
    
    @classmethod
    def build_stylesheet(cls, force_refresh: bool = False) -> str:
        """生成完整的Qt样式表，带分层缓存机制。
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            完整的QSS样式表字符串
        """
        # 生成基础缓存键（不包含 opacity/blur）
        base_key = f"{theme.active_preset}_{theme.background_enabled}"
        
        # ★ 背景缓存键使用整数档位（0-100），避免浮点精度导致缓存 miss
        opacity_level = int(round(theme.background_opacity * 100))
        bg_key = f"{base_key}_{opacity_level}_{theme.background_blur}"
        
        # 获取或生成基础样式（不包含背景图）
        if force_refresh or base_key not in cls._base_cache:
            t = theme
            style = cls._build_base(t)
            style += cls._build_group_box(t)
            style += cls._build_labels(t)
            style += cls._build_buttons(t)
            style += cls._build_progress_bar(t)
            style += cls._build_separator(t)
            cls._base_cache[base_key] = style
        
        # 获取或生成背景样式（只包含背景图相关）
        if force_refresh or bg_key not in cls._bg_cache:
            if theme.background_enabled and theme.background_image_path:
                cls._bg_cache[bg_key] = cls._build_background_style(
                    theme.background_image_path, 
                    theme.background_opacity, 
                    theme.background_blur,
                    theme
                )
            else:
                cls._bg_cache[bg_key] = ""
        
        # 组合返回
        return cls._base_cache[base_key] + cls._bg_cache[bg_key]
    
    @classmethod
    def _build_base(cls, t) -> str:
        """构建基础样式"""
        # 无背景图时使用主题的深色背景
        return f"""
QWidget {{
    color: {t.text};
    font-family: "Microsoft YaHei";
    font-size: 13px;
}}
/* 管理面板背景（无背景图时使用主题色）*/
QWidget#ManagementPanel {{
    background-color: {t.panel_darkest};
}}
/* 内容层背景（无背景图时使用主题色）*/
QWidget#ContentLayer {{
    background-color: {t.panel_bg};
}}
/* 内容层下的所有控件 */
QWidget#ContentLayer > QWidget,
QWidget#ContentLayer > QFrame,
QWidget#ContentLayer > QScrollArea,
QWidget#ContentLayer > QListWidget,
QWidget#ContentLayer > QWidget > QGroupBox,
QWidget#ContentLayer > QScrollArea > QWidget > QGroupBox {{
    background-color: {t.panel_bg};
}}
"""
    
    @classmethod
    def _build_group_box(cls, t) -> str:
        """构建分组框样式"""
        return f"""
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
"""
    
    @classmethod
    def _build_labels(cls, t) -> str:
        """构建标签样式"""
        return f"""
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
"""
    
    @classmethod
    def _build_buttons(cls, t) -> str:
        """构建按钮样式"""
        base_btn = f"""
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
"""
        
        primary_btn = f"""
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
    background-color: {t.btn_disabled_bg};
    color: {t.btn_disabled_text};
    border-color: {t.btn_disabled_border};
}}
"""
        
        action_btn = f"""
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
"""
        
        danger_btn = f"""
QPushButton#dangerBtn {{
    border-color: {t.danger_border};
    color: {t.danger_text};
}}
QPushButton#dangerBtn:hover {{
    background-color: {t.danger_hover_bg};
    color: {t.danger_hover_text};
}}
"""
        
        success_btn = f"""
QPushButton#successBtn {{
    border-color: {t.success_border};
    color: {t.success_text};
}}
QPushButton#successBtn:hover {{
    background-color: {t.success_hover_bg};
    color: {t.success_hover_text};
}}
"""
        
        return base_btn + primary_btn + action_btn + danger_btn + success_btn
    
    @classmethod
    def _build_progress_bar(cls, t) -> str:
        """构建进度条样式"""
        return f"""
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
"""
    
    @classmethod
    def _build_separator(cls, t) -> str:
        """构建分隔线样式"""
        return f"""
QFrame#sep {{
    background-color: {t.border};
    max-height: 1px;
}}
"""
    
    @classmethod
    def _build_background_style(cls, image_path: str, opacity: float, blur: int, t=None) -> str:
        """构建背景图样式（分层架构）
        
        架构：ManagementPanel (QGridLayout 0,0 同格叠加)
        - BgImagePlaceholder: 承载背景图
        - OpacityOverlay: 纯色遮罩（opacity 变化时只更新这一层）
        - ContentLayer: 完全透明，承载所有 UI 控件
        
        Args:
            image_path: 背景图路径
            opacity: 透明度 (0.0-1.0)
            blur: 模糊度 (0-50)
            t: ThemeConfig 实例（用于获取 panel_overlay_rgb）
            
        Returns:
            背景图QSS样式
        """
        # 处理路径转义
        escaped_path = os.path.normpath(image_path).replace('\\', '/')
        
        # 计算遮罩层透明度
        overlay_alpha = int(opacity * 200)
        
        # 功能区半透明背景（略深，便于阅读）
        panel_alpha = int(opacity * 180)
        
        # 面板遮罩 RGB 颜色（跟随预设）
        if t is None:
            t = theme
        rgb = t._data.get("panel_overlay_rgb", [5, 5, 20])
        overlay_rgb = f"{rgb[0]}, {rgb[1]}, {rgb[2]}"
        
        return f"""
/* ===== 分层架构样式（有背景图时覆盖基础样式）===== */

/* 0. 管理面板透明，让背景层显示 */
QWidget#ManagementPanel {{
    background-color: transparent;
}}

/* 1. 背景图占位层 - 承载背景图 */
QWidget#BgImagePlaceholder {{
    background-image: url("{escaped_path}");
    background-repeat: no-repeat;
    background-position: center center;
    /* background-size 由管理面板动态计算设置 */
}}

/* 1.5. 不透明度遮罩层 - 纯色覆盖 */
QWidget#OpacityOverlay {{
    background-color: rgba({overlay_rgb}, {overlay_alpha});
}}

/* 2. 内容层 - 完全透明 */
QWidget#ContentLayer {{
    background-color: transparent;
    border: none;
}}

/* 3. 内容层下的所有直接子部件 - 半透明背景 */
QWidget#ContentLayer > QWidget,
QWidget#ContentLayer > QFrame,
QWidget#ContentLayer > QScrollArea,
QWidget#ContentLayer > QListWidget {{
    background-color: rgba({overlay_rgb}, {panel_alpha});
    border: none;
}}

/* 4. 功能区容器 - 略深的半透明背景 */
QWidget#ContentLayer > QWidget > QGroupBox,
QWidget#ContentLayer > QScrollArea > QWidget > QGroupBox,
QWidget#ContentLayer > QWidget > QGroupBox > QWidget {{
    background-color: rgba({overlay_rgb}, {panel_alpha});
}}

/* 5. 兼容 QMainWindow */
QMainWindow#MainWindow {{
    background-color: transparent;
}}
"""
    
    @classmethod
    def build_dialog_button_style(cls) -> str:
        """弹窗OK按钮样式"""
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
    
    @classmethod
    def clear_cache(cls):
        """清除样式表缓存"""
        cls._base_cache.clear()
        cls._bg_cache.clear()


# 模块级函数（保持向后兼容）
def build_stylesheet() -> str:
    """基于当前主题配色，生成完整的Qt样式表。"""
    return StyleSheetBuilder.build_stylesheet()


def build_dialog_button_style() -> str:
    """弹窗OK按钮样式。"""
    return StyleSheetBuilder.build_dialog_button_style()