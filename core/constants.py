"""
WARFRAME-RELIC 共享常量
- 非主题相关的业务常量（OCR、窗口、计时等）
- 向后兼容：重新导出主题相关的所有内容

主题配置已拆分为：
    core.theme_config  — ThemeConfig 单例、theme、预设数据
    core.theme_proxy   — _ThemeProxy、模块级颜色代理常量
"""
# ============================================================
# 向后兼容：重新导出主题相关（旧代码无需改动）
# ============================================================
from core.theme_config import theme, ThemeConfig
from core.theme_proxy import (
    CYBER_YELLOW, CYBER_CYAN, CYBER_MAGENTA, CYBER_ORANGE,
    CYBER_RED, CYBER_GREEN,
    CYBER_PANEL_BG, CYBER_CARD_BG, CYBER_BORDER,
    CYBER_TEXT, CYBER_TEXT_DIM,
    COLOR_VAULTED, COLOR_AVAILABLE, COLOR_UNKNOWN, FALLBACK_COLOR,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER,
    LOG_COLOR_MAP,
    OVERLAY_BG_COLOR, OVERLAY_SELECTION_OVERLAY, OVERLAY_STATUS_BG,
    OVERLAY_CROSSHAIR_COLOR, OVERLAY_SELECTION_BORDER,
    BTN_DEFAULT_BG, BTN_DEFAULT_TEXT, BTN_DEFAULT_BORDER,
    BTN_HOVER_BG, BTN_HOVER_TEXT, BTN_HOVER_BORDER,
    BTN_PRESSED_BG,
    BTN_DISABLED_BG, BTN_DISABLED_TEXT, BTN_DISABLED_BORDER,
    PRIMARY_BG, PRIMARY_TEXT, PRIMARY_BORDER,
    PRIMARY_HOVER_BG, PRIMARY_HOVER_BORDER,
    PRIMARY_DISABLED_BG, PRIMARY_DISABLED_TEXT, PRIMARY_DISABLED_BORDER,
    DANGER_TEXT, DANGER_BORDER, DANGER_HOVER_BG, DANGER_HOVER_TEXT,
    SUCCESS_TEXT, SUCCESS_BORDER, SUCCESS_HOVER_BG, SUCCESS_HOVER_TEXT,
    BRAND_BILIBILI, BRAND_BILIBILI_HOVER, BRAND_GITHUB, BRAND_GITHUB_HOVER,
    LABEL_DEFAULT, PANEL_DARKEST, PANEL_DEEPER,
    PROGRESS_GRADIENT_START, PROGRESS_GRADIENT_MID, PROGRESS_GRADIENT_END,
    LOG_TIMESTAMP, FETCH_MANUAL_HINT, FETCH_ERROR_COLOR,
)


# ============================================================
# 向后兼容：旧 API 函数
# ============================================================

def get_theme() -> dict:
    """获取当前主题字典的副本。"""
    return theme.to_dict()


def save_theme(data: dict) -> bool:
    """保存主题到当前预设文件，返回是否成功。"""
    return theme.save(data)


def reload_theme() -> dict:
    """热重载主题（_ThemeProxy 自动跟随，无需手动同步）。"""
    theme.reload()
    return theme.to_dict()


def _sync_module_globals():
    """保留兼容性空函数（_ThemeProxy 已自动代理，无需手动同步）。"""
    pass


# ============================================================
# 不可变常量（非主题相关）
# ============================================================

# 时间
DEFAULT_AUTO_HIDE_MS = 5000
LABEL_AUTO_HIDE_MS = 3000

# OCR
OCR_TEXT_SCORE = 0.38       # 文本置信度阈值（平衡识别率和误报）
OCR_BOX_THRESH = 0.22       # 检测框阈值
OCR_UPSCALE_MIN_WIDTH = 900 # 图片宽度 > 此值时放大
OCR_UPSCALE_SCALE = 1.4     # 上采样倍率（1.4x 平衡性能和精度）

# 自适应上采样配置（针对全屏/大图优化）
OCR_ADAPTIVE_UPSCALE_ENABLED = True      # 启用自适应上采样
OCR_ADAPTIVE_BASE_WIDTH = 1200           # 基准宽度阈值
OCR_ADAPTIVE_MAX_SCALE = 2.5             # 最大上采样倍数（防止过度放大）
OCR_ADAPTIVE_MIN_SCALE = 1.2             # 最小上采样倍数（大图至少放大1.2倍）

# 图像增强配置
OCR_ENHANCE_CONTRAST = True              # 启用对比度增强
OCR_CLAHE_CLIP_LIMIT = 2.0               # CLAHE对比度限制
OCR_CLAHE_GRID_SIZE = 8                  # CLAHE网格大小

# 动态OCR参数配置（针对不同尺寸图像）
OCR_DYNAMIC_PARAMS_ENABLED = True        # 启用动态参数调整
OCR_LARGE_IMAGE_TEXT_SCORE = 0.35        # 大图文本置信度（降低以提高召回）
OCR_LARGE_IMAGE_BOX_THRESH = 0.20        # 大图检测框阈值（降低以检测更多候选）
OCR_LARGE_IMAGE_THRESHOLD = 1500         # 判定为大图的宽度阈值

# RapidOCR引擎配置
RAPIDOCR_TEXT_SCORE = 0.35               # 文本置信度阈值
RAPIDOCR_BOX_THRESH = 0.20               # 检测框阈值
RAPIDOCR_DET_LIMIT_SIDE_LEN = 960        # 检测器最小边限制（关键！防止大图被过度缩小）
RAPIDOCR_DET_LIMIT_TYPE = "min"          # 按最小边缩放（保持宽高比）

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
