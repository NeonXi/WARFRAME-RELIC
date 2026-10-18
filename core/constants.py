"""
[L0/L1] core.constants — 全局共享常量

职责:
- 非主题相关的业务常量(OCR、窗口、计时等)
- 向后兼容:重新导出主题相关的所有内容(旧代码无需改动)

主题配置已重构:
    core.theme_proxy   — 模块级颜色代理常量(从 TokenManager 读)
    core.theme_config  — **已删除**(2026-06-17 整改 F1 硬编码颜色)
        旧 ThemeConfig 单例的 _DEFAULTS 字典包含大量硬编码 hex,
        新体系所有颜色都走 cyberpunk.yaml + TokenManager 单一来源。

## AI 硬约束 — 修改本文件前必读
归属层:    [L0/L1] (core/ 根目录,跨层桥接/全局管理器)
允许依赖:  视文件而定(本层可持有 widget 引用作桥接,但不实现绘制)
禁止依赖:  根目录 .py 不允许做业务实现 → 业务放 core/services/
必读规范:  .trae/rules/开发规范.md §6.7

本文件相关红线:
- 禁止根目录 .py 持有 widget 绘制逻辑 → 视觉交给 core/widgets/
- 禁止硬编码资源路径 → 必须 core.constants 取
- 禁止在根目录定义业务类 → 业务放对应层
- 禁止反向调用 UI(从 Service → Widget) → 单向数据流
- 禁止 try/except: pass 吞错 → 必须记录到日志或抛给上层

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.7,别走捷径。
"""

# ============================================================
# 应用信息(关于页展示 / 打包脚本引用,禁止在页面里硬编码)
# ============================================================
APP_NAME = "WARFRAME-RELIC"
APP_VERSION = "4.1.0"
APP_BUILD_DATE = "20261019"

# ============================================================
# 向后兼容:重新导出主题相关(旧代码无需改动)
# ============================================================
from core.theme_proxy import (
    CYBER_YELLOW, CYBER_CYAN, CYBER_MAGENTA, CYBER_ORANGE,
    CYBER_RED, CYBER_GREEN,
    CYBER_PANEL_BG, CYBER_CARD_BG, CYBER_BORDER,
    CYBER_TEXT, CYBER_TEXT_DIM,
    COLOR_VAULTED, COLOR_AVAILABLE, COLOR_UNKNOWN, FALLBACK_COLOR,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER,
    LOG_COLOR_MAP,
    OVERLAY_BG_COLOR, OVERLAY_SELECTION_OVERLAY,
    BTN_DEFAULT_BG, BTN_DEFAULT_TEXT, BTN_DEFAULT_BORDER,
    BTN_HOVER_BG, BTN_HOVER_TEXT, BTN_HOVER_BORDER,
    BTN_PRESSED_BG,
    BTN_DISABLED_BG, BTN_DISABLED_TEXT, BTN_DISABLED_BORDER,
    BRAND_BILIBILI, BRAND_BILIBILI_HOVER, BRAND_GITHUB, BRAND_GITHUB_HOVER,
    LABEL_DEFAULT, PANEL_BG, CARD_BG,
    PROGRESS_GRADIENT_START, PROGRESS_GRADIENT_MID, PROGRESS_GRADIENT_END,
    LOG_TIMESTAMP, FETCH_MANUAL_HINT, FETCH_ERROR_COLOR,
)


# ============================================================
# 向后兼容:旧 API 函数(由调用方迁移后删除)
# ============================================================

def get_theme() -> dict:
    """[已废弃] 获取当前主题字典的副本。

    新代码请直接使用::
        from core.tokens.manager import TokenManager
        TokenManager.instance().get("accent.primary")
    """
    import warnings
    warnings.warn(
        "get_theme() 已废弃,请改用 TokenManager.instance().get(token_key)",
        DeprecationWarning,
        stacklevel=2,
    )
    return _snapshot_theme()


def save_theme(data: dict) -> bool:
    """[已废弃] 保存主题(theme_config 已删除,无操作占位)。"""
    import warnings
    warnings.warn(
        "save_theme() 已废弃,主题热重载请用 TokenManager.reload_preset()",
        DeprecationWarning,
        stacklevel=2,
    )
    return True


def reload_theme() -> dict:
    """[已废弃] 重新加载主题(theme_config 已删除,仅占位)。"""
    import warnings
    warnings.warn(
        "reload_theme() 已废弃,主题热重载请用 TokenManager.reload_preset()",
        DeprecationWarning,
        stacklevel=2,
    )
    return _snapshot_theme()


def _sync_module_globals():
    """[已废弃] 保留兼容性空函数(_ThemeProxy 已自动代理,无需手动同步)。"""
    pass


def _snapshot_theme() -> dict:
    """[内部] 从 TokenManager 汇总当前 token,用于旧 API 向后兼容。

    实现要点:
      1. **映射关系** —— 旧 theme_config 的 key(如 "cyber_yellow")
         映射到 token yaml 里的对应 key(如 "alias.accent.primary")。
         映射表是稳定的,主题切换时仅值变化,key 集合不变。
      2. **单一来源** —— 所有颜色值都从 TokenManager 读,
         没有任何硬编码 hex 字面量,符合 F1 颜色规范。
      3. **小写 key 风格** —— 沿用旧 theme_config 的小写下划线 key 命名,
         方便旧代码 `theme.get("cyber_yellow")` 无缝切换。

    Returns:
        dict[str, str] —— key=旧 key,value=解析后的 hex 字符串
    """
    tm = TokenManager.instance()
    return {
        "cyber_yellow":       tm.get("alias.accent.primary"),
        "cyber_cyan":         tm.get("alias.accent.secondary"),
        "cyber_magenta":      tm.get("alias.accent.tertiary"),
        "cyber_orange":       tm.get("alias.semantic.warning"),
        "cyber_red":          tm.get("alias.semantic.danger"),
        "cyber_green":        tm.get("alias.semantic.success"),
        "panel_bg":           tm.get("alias.bg.base"),
        "card_bg":            tm.get("alias.bg.raised"),
        "border":             tm.get("alias.border.default"),
        "text":               tm.get("alias.text.primary"),
        "text_dim":           tm.get("alias.text.tertiary"),
        "color_unknown":      tm.get("raw.game.unknown"),
        "color_gold":         tm.get("raw.game.gold"),
        "color_silver":       tm.get("raw.game.silver"),
        "color_copper":       tm.get("raw.game.copper"),
        "btn_default_bg":     tm.get("alias.bg.raised"),
        "btn_default_text":   tm.get("alias.accent.primary"),
        "btn_default_border": tm.get("alias.accent.primary"),
        "btn_hover_bg":       tm.get("alias.bg.raised"),
        "btn_hover_text":     tm.get("alias.accent.secondary"),
        "btn_hover_border":   tm.get("alias.accent.secondary"),
        "btn_pressed_bg":     tm.get("alias.bg.base"),
        "btn_disabled_bg":    tm.get("alias.bg.raised"),
        "btn_disabled_text":  tm.get("alias.text.disabled"),
        "btn_disabled_border": tm.get("alias.border.subtle"),
        "brand_bilibili":     tm.get("raw.external.bilibili"),
        "brand_bilibili_hover": tm.get("raw.external.bilibili_hover"),
        "brand_github":       tm.get("raw.external.github"),
        "brand_github_hover": tm.get("raw.external.github_hover"),
        "label_default":      tm.get("alias.text.secondary"),
        "progress_gradient_start": tm.get("raw.brand.yellow"),
        "progress_gradient_mid":   tm.get("raw.brand.red"),
        "progress_gradient_end":   tm.get("raw.brand.cyan"),
        "subtle_border":      tm.get("alias.border.subtle"),
        "muted_text":         tm.get("alias.text.tertiary"),
        "light_text":         tm.get("alias.text.primary"),
        "color_black":        tm.get("alias.text.inverse"),
        "color_dark_gray":    tm.get("alias.text.disabled"),
        "color_enemy":        tm.get("alias.semantic.danger"),
        "color_purple":       tm.get("alias.accent.tertiary"),
        "link_color":         tm.get("alias.semantic.info"),
        "status_online":      tm.get("alias.semantic.success"),
        "status_ingame":      tm.get("alias.semantic.info"),
        "status_offline":     tm.get("alias.text.disabled"),
        "status_away":        tm.get("alias.semantic.warning"),
        "json_boolean":       tm.get("alias.accent.tertiary"),
        "fetch_manual_hint":  tm.get("alias.semantic.warning"),
        "fetch_error_color":  tm.get("alias.semantic.danger"),
    }


# 延迟导入 TokenManager 避免循环依赖(constants 会被早期模块 import)
from core.tokens.manager import TokenManager


# ============================================================
# 不可变常量（非主题相关）
# ============================================================

# 时间
DEFAULT_AUTO_HIDE_MS = 5000
LABEL_AUTO_HIDE_MS = 3000

# OCR
OCR_TEXT_SCORE = 0.38       # 文本置信度阈值（平衡识别率和误报）
OCR_BOX_THRESH = 0.22       # 检测框阈值
OCR_UPSCALE_MIN_WIDTH = 50  # 图片宽度 > 此值时放大（降低到50，让小格子也放大）
OCR_UPSCALE_SCALE = 3.0     # 上采样倍率（3.0x，让小文字更清楚）

# 自适应上采样配置（已由 BaseOCR._calculate_adaptive_scale 统一管理）
OCR_ADAPTIVE_UPSCALE_ENABLED = True      # 保留开关兼容性
OCR_ADAPTIVE_BASE_WIDTH = 1200           # 保留兼容性
OCR_ADAPTIVE_MAX_SCALE = 6.0             # 最大上采样倍数
OCR_ADAPTIVE_MIN_SCALE = 1.0             # 最小上采样倍数

# 图像增强配置
OCR_ENHANCE_CONTRAST = True              # 启用对比度增强
OCR_CLAHE_CLIP_LIMIT = 3.0               # CLAHE对比度限制（提高以增强文字对比度）
OCR_CLAHE_GRID_SIZE = 8                  # CLAHE网格大小（减小以更精细）

# 颜色过滤（仅保留目标颜色文字，过滤其他颜色噪声）
OCR_COLOR_FILTER_ENABLED = False         # 默认关闭，子类按需开启
OCR_COLOR_FILTER_LOWER = (15, 40, 120)   # HSV 下限 (H, S, V)
OCR_COLOR_FILTER_UPPER = (45, 255, 255)  # HSV 上限 — 默认金色/黄色范围

# 调试：保存 OCR 中间结果图到本地（用于调参）
OCR_DEBUG_SAVE_ENABLED = False           # 设为 True 后，每步处理图都会保存到 %APPDATA%\WARFRAME-RELIC\ocr_debug\
OCR_DEBUG_SAVE_DIR = "ocr_debug"         # 相对 APPDATA 的子目录

# 动态OCR参数配置（针对不同尺寸图像）
OCR_DYNAMIC_PARAMS_ENABLED = True        # 启用动态参数调整
OCR_LARGE_IMAGE_TEXT_SCORE = 0.35        # 大图文本置信度（降低以提高召回）
OCR_LARGE_IMAGE_BOX_THRESH = 0.20        # 大图检测框阈值（降低以检测更多候选）
OCR_LARGE_IMAGE_THRESHOLD = 1500         # 判定为大图的宽度阈值

# RapidOCR引擎配置
RAPIDOCR_TEXT_SCORE = 0.15               # 文本置信度阈值（降低到0.15，提高召回率）
RAPIDOCR_BOX_THRESH = 0.10               # 检测框阈值（降低到0.10，提高召回率）
RAPIDOCR_DET_LIMIT_SIDE_LEN = 1600       # 检测器最小边限制（降低到1600，加速大图OCR）
RAPIDOCR_DET_LIMIT_TYPE = "max"          # 按最大边缩放（限制大图尺寸，加速推理）

# 按钮布局
BTN_WIDTH = 200
BTN_HEIGHT = 45
BTN_GAP = 20

# dxcam 重试
DXCAM_MAX_RETRIES = 5
DXCAM_RETRY_BASE_SLEEP = 0.5

# 覆盖层
OVERLAY_FONT = "Microsoft YaHei"
OVERLAY_FONT_SIZE = 12
OVERLAY_STATUS_HEIGHT = 36
OVERLAY_MIN_SELECTION = 20
