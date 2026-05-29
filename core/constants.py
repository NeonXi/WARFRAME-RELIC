"""
WARFRAME-RELIC 共享常量
统一管理颜色、阈值、尺寸等全局配置。
颜色由 data/theme.json 驱动，ThemeConfig 单例负责加载/重载。

模块级变量使用 _ThemeProxy 属性代理，自动跟随 theme 单例变化，
无需手动调用 _sync_module_globals()。
"""
import json
import os
from pathlib import Path


# ============================================================
# 主题配置单例
# ============================================================

class ThemeConfig:
    """主题配色管理器（单例模式）。
    
    使用方式：
        theme = ThemeConfig()           # 获取单例
        theme.cyber_yellow              # 直接访问属性
        theme.reload()                  # 热重载（从 theme.json）
        theme.save(modified_dict)       # 保存到 theme.json
        theme.reset()                   # 删除 theme.json 恢复默认
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
            cls._instance._load()
        return cls._instance

    # ---- 加载 / 重载 ----

    @property
    def _theme_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / 'data' / 'theme.json'

    def _load(self):
        """加载配色：先设默认值，再用 theme.json 覆盖。"""
        # 默认值（Cyberpunk 2077 主题）
        self._data = {
            "cyber_yellow": "#F7E300", "cyber_cyan": "#00F0FF",
            "cyber_magenta": "#FF0090", "cyber_orange": "#FF6600",
            "cyber_red": "#FF0044", "cyber_green": "#00FF88",
            "cyber_blue": "#4488FF",
            "dark_bg": "#0A0A0A", "panel_bg": "#0F0F1A",
            "card_bg": "#15152A", "border": "#2A2A4A",
            "text": "#CCDDFF", "text_dim": "#667799",
            "color_vaulted": "#00FF88", "color_available": "#FF0044",
            "color_unknown": "#667788",
            "color_gold": "#F7E300", "color_silver": "#00F0FF",
            "color_copper": "#FF0090",
            "log_ok": "#00FF88", "log_warn": "#FF6600",
            "log_error": "#FF0044", "log_info": "#00F0FF",
            "log_debug": "#667799",
            "overlay_bg_rgba": [10, 10, 20, 220],
            "overlay_selection_overlay_rgba": [5, 5, 20, 140],
            "overlay_status_bg_rgba": [5, 5, 15, 200],
            "overlay_crosshair_color": "#00F0FF",
            "overlay_selection_border": "#F7E300",
            "btn_default_bg": "#15152A", "btn_default_text": "#F7E300",
            "btn_default_border": "#F7E300",
            "btn_hover_bg": "#1A1A3A", "btn_hover_text": "#00F0FF",
            "btn_hover_border": "#00F0FF",
            "btn_pressed_bg": "#0A0A1A",
            "btn_disabled_bg": "#0F0F1A", "btn_disabled_text": "#444466",
            "btn_disabled_border": "#2A2A3A",
            "primary_bg": "#1A2A4A", "primary_text": "#F7E300",
            "primary_border": "#F7E300",
            "primary_hover_bg": "#2A3A5A", "primary_hover_border": "#00F0FF",
            "primary_disabled_bg": "#0F0F1A", "primary_disabled_text": "#444466",
            "primary_disabled_border": "#2A2A3A",
            "danger_text": "#FF0044", "danger_border": "#FF0044",
            "danger_hover_bg": "#2A0A14", "danger_hover_text": "#FF4477",
            "success_text": "#00FF88", "success_border": "#00FF88",
            "success_hover_bg": "#0A2A1A", "success_hover_text": "#44FFAA",
            "brand_bilibili": "#FB7299", "brand_bilibili_hover": "#FF8DB0",
            "brand_github": "#58A6FF", "brand_github_hover": "#79C0FF",
            "label_default": "#AABBCC",
            "panel_darkest": "#0A0A14", "panel_deeper": "#060612",
            "progress_gradient_start": "#F7E300",
            "progress_gradient_mid": "#00F0FF",
            "progress_gradient_end": "#FF0090",
            "log_timestamp": "#666666",
            "fetch_manual_hint": "#FFAA33", "fetch_error_color": "#FF4444",
        }
        self._apply_file_overrides()
        self._build_derived()
        self._loaded = True

    def _apply_file_overrides(self):
        """从 theme.json 覆盖已知 key。"""
        try:
            if self._theme_path.exists():
                with open(self._theme_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                for k in self._data:
                    if k in file_data:
                        self._data[k] = file_data[k]
        except Exception:
            pass  # 加载失败则用默认值

    def _build_derived(self):
        """从 _data 构建派生属性（RGBA 元组、日志映射等）。"""
        d = self._data
        # 便捷别名：直接用 data 的 key 作为属性名
        for k, v in d.items():
            setattr(self, k, v)

        # RGBA 元组
        self.overlay_bg_rgba = tuple(d["overlay_bg_rgba"])
        self.overlay_selection_overlay_rgba = tuple(d["overlay_selection_overlay_rgba"])
        self.overlay_status_bg_rgba = tuple(d["overlay_status_bg_rgba"])

        # 日志颜色映射
        self.log_color_map = {
            "ok": d["log_ok"], "warn": d["log_warn"],
            "error": d["log_error"], "info": d["log_info"],
            "debug": d["log_debug"],
        }
        self._loaded = True

    def reload(self):
        """热重载：重新读取 theme.json 并重建所有属性。"""
        self._load()

    def to_dict(self) -> dict:
        """返回当前配色字典的副本。"""
        return dict(self._data)

    def save(self, changes: dict) -> bool:
        """将修改合并到内存并写入 theme.json（仅保存修改过的键，增量存储）。"""
        valid = {k: v for k, v in changes.items() if k in self._data}
        if not valid:
            return False
        # 先加载已有增量数据，再合并新修改
        existing = {}
        try:
            if self._theme_path.exists():
                with open(self._theme_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
        except Exception:
            pass
        existing.update(valid)
        # 更新内存
        self._data.update(valid)
        self._build_derived()
        try:
            os.makedirs(self._theme_path.parent, exist_ok=True)
            with open(self._theme_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def reset(self):
        """删除 theme.json 并恢复默认配色。"""
        try:
            os.remove(self._theme_path)
        except Exception:
            pass
        self._data = {}
        self._load()

    def __getattr__(self, name):
        """属性代理：未定义属性时从 _data 字典取值。"""
        if name.startswith('_'):
            raise AttributeError(name)
        if '_data' in self.__dict__ and name in self._data:
            return self._data[name]
        raise AttributeError(f"'ThemeConfig' has no attribute '{name}'")


# 全局单例（其他模块通过 import theme 访问）
theme = ThemeConfig()


# ============================================================
# _ThemeProxy: 属性代理，自动跟随 theme 单例变化
# ============================================================

class _ThemeProxy:
    """模块级变量代理 —— 访问时自动从 theme 单例读取最新值。
    
    使用方式：
        from core.constants import CYBER_YELLOW
        print(CYBER_YELLOW)  # 每次访问都从 theme.cyber_yellow 取值
    
    替换了旧的「一次性赋值 + _sync_module_globals()」模式。
    """
    __slots__ = ('_attr',)

    def __init__(self, attr: str):
        object.__setattr__(self, '_attr', attr)

    # ---- 值解析 ----
    def _value(self):
        return getattr(theme, self._attr)

    # ---- 属性委托：所有属性访问（含 str 方法）转发到实际值 ----
    def __getattribute__(self, name):
        if name in ('_attr', '_value', '__class__', '__dict__'):
            return object.__getattribute__(self, name)
        return getattr(object.__getattribute__(self, '_value')(), name)

    # ---- 双下划线魔术方法 ----
    def __repr__(self):
        return repr(self._value())

    def __str__(self):
        return str(self._value())

    def __eq__(self, other):
        return self._value() == other

    def __hash__(self):
        return hash(self._value())

    def __bool__(self):
        return bool(self._value())

    def __getitem__(self, index):
        return self._value()[index]

    def __len__(self):
        return len(self._value())

    def __contains__(self, item):
        return item in self._value()

    def __iter__(self):
        return iter(self._value())


def _proxy(attr: str):
    """创建 _ThemeProxy 实例。"""
    return _ThemeProxy(attr)


# ============================================================
# 模块级别名（自动代理，无需手动同步）
# ============================================================

CYBER_YELLOW  = _proxy('cyber_yellow')
CYBER_CYAN    = _proxy('cyber_cyan')
CYBER_MAGENTA = _proxy('cyber_magenta')
CYBER_ORANGE  = _proxy('cyber_orange')
CYBER_RED     = _proxy('cyber_red')
CYBER_GREEN   = _proxy('cyber_green')
CYBER_BLUE    = _proxy('cyber_blue')
CYBER_DARK_BG  = _proxy('dark_bg')
CYBER_PANEL_BG = _proxy('panel_bg')
CYBER_CARD_BG  = _proxy('card_bg')
CYBER_BORDER   = _proxy('border')
CYBER_TEXT     = _proxy('text')
CYBER_TEXT_DIM = _proxy('text_dim')

COLOR_VAULTED   = _proxy('color_vaulted')
COLOR_AVAILABLE = _proxy('color_available')
COLOR_UNKNOWN   = _proxy('color_unknown')
FALLBACK_COLOR  = _proxy('color_unknown')

COLOR_GOLD   = _proxy('color_gold')
COLOR_SILVER = _proxy('color_silver')
COLOR_COPPER = _proxy('color_copper')

LOG_COLOR_MAP = _proxy('log_color_map')

OVERLAY_BG_COLOR = _proxy('overlay_bg_rgba')
OVERLAY_SELECTION_OVERLAY = _proxy('overlay_selection_overlay_rgba')
OVERLAY_STATUS_BG = _proxy('overlay_status_bg_rgba')
OVERLAY_CROSSHAIR_COLOR = _proxy('overlay_crosshair_color')
OVERLAY_SELECTION_BORDER = _proxy('overlay_selection_border')

BTN_DEFAULT_BG = _proxy('btn_default_bg')
BTN_DEFAULT_TEXT = _proxy('btn_default_text')
BTN_DEFAULT_BORDER = _proxy('btn_default_border')
BTN_HOVER_BG = _proxy('btn_hover_bg')
BTN_HOVER_TEXT = _proxy('btn_hover_text')
BTN_HOVER_BORDER = _proxy('btn_hover_border')
BTN_PRESSED_BG = _proxy('btn_pressed_bg')
BTN_DISABLED_BG = _proxy('btn_disabled_bg')
BTN_DISABLED_TEXT = _proxy('btn_disabled_text')
BTN_DISABLED_BORDER = _proxy('btn_disabled_border')

PRIMARY_BG = _proxy('primary_bg')
PRIMARY_TEXT = _proxy('primary_text')
PRIMARY_BORDER = _proxy('primary_border')
PRIMARY_HOVER_BG = _proxy('primary_hover_bg')
PRIMARY_HOVER_BORDER = _proxy('primary_hover_border')
PRIMARY_DISABLED_BG = _proxy('primary_disabled_bg')
PRIMARY_DISABLED_TEXT = _proxy('primary_disabled_text')
PRIMARY_DISABLED_BORDER = _proxy('primary_disabled_border')

DANGER_TEXT = _proxy('danger_text')
DANGER_BORDER = _proxy('danger_border')
DANGER_HOVER_BG = _proxy('danger_hover_bg')
DANGER_HOVER_TEXT = _proxy('danger_hover_text')

SUCCESS_TEXT = _proxy('success_text')
SUCCESS_BORDER = _proxy('success_border')
SUCCESS_HOVER_BG = _proxy('success_hover_bg')
SUCCESS_HOVER_TEXT = _proxy('success_hover_text')

BRAND_BILIBILI = _proxy('brand_bilibili')
BRAND_BILIBILI_HOVER = _proxy('brand_bilibili_hover')
BRAND_GITHUB = _proxy('brand_github')
BRAND_GITHUB_HOVER = _proxy('brand_github_hover')

LABEL_DEFAULT = _proxy('label_default')
PANEL_DARKEST = _proxy('panel_darkest')
PANEL_DEEPER = _proxy('panel_deeper')
PROGRESS_GRADIENT_START = _proxy('progress_gradient_start')
PROGRESS_GRADIENT_MID = _proxy('progress_gradient_mid')
PROGRESS_GRADIENT_END = _proxy('progress_gradient_end')
LOG_TIMESTAMP = _proxy('log_timestamp')
FETCH_MANUAL_HINT = _proxy('fetch_manual_hint')
FETCH_ERROR_COLOR = _proxy('fetch_error_color')


# ============================================================
# 向后兼容：旧 API 函数
# ============================================================

def get_theme() -> dict:
    """获取当前主题字典的副本。"""
    return theme.to_dict()


def save_theme(data: dict) -> bool:
    """保存主题到 theme.json，返回是否成功。"""
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
OCR_TEXT_SCORE = 0.35
OCR_BOX_THRESH = 0.2
OCR_UPSCALE_MIN_WIDTH = 900

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
