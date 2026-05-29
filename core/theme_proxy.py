"""
WARFRAME-RELIC 主题颜色代理
- _ThemeProxy: 属性代理类，自动跟随 theme 单例变化
- 模块级颜色常量（如 CYBER_YELLOW, BTN_DEFAULT_BG 等）

使用方式：
    from core.theme_proxy import CYBER_YELLOW
    print(CYBER_YELLOW)  # 每次访问都从 theme 实时取值
"""
from core.theme_config import theme


class _ThemeProxy:
    """模块级变量代理 —— 访问时自动从 theme 单例读取最新值。

    使用方式：
        from core.theme_proxy import CYBER_YELLOW
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
