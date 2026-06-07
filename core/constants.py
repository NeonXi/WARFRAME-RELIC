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
