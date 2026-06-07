"""
热键配置管理模块
- 读写 data/hotkeys.json
- 提供默认热键
- 支持 keyboard 库格式的热键字符串
"""

import json
import os
from pathlib import Path
from typing import Dict

from data.ui_strings import S


# 默认热键
DEFAULT_HOTKEYS = {
    "select": "ctrl+g",           # 框选截图
    "fullscreen": "ctrl+h",       # 全屏截图
    "query_price": "ctrl+t",  # 价格查询（4等分截图+识别+标注）
}

# 可用的修饰键
MODIFIERS = ["ctrl", "alt", "shift", "win"]

# 热键功能说明
HOTKEY_LABELS = {
    "select": S("hotkey", "label_select"),
    "fullscreen": S("hotkey", "label_fullscreen"),
    "query_price": S("hotkey", "label_query_price"),
}


def _config_path() -> str:
    """获取配置文件路径"""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "hotkeys.json")


def load_hotkeys() -> Dict[str, str]:
    """加载热键配置，如果文件不存在或损坏则返回默认值"""
    path = _config_path()
    if not os.path.exists(path):
        return dict(DEFAULT_HOTKEYS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 合并默认值：用户可能只改了部分热键
        result = dict(DEFAULT_HOTKEYS)
        if isinstance(data, dict):
            for key in DEFAULT_HOTKEYS:
                if key in data and isinstance(data[key], str) and data[key].strip():
                    result[key] = data[key].strip().lower()
        return result
    except (json.JSONDecodeError, Exception):
        return dict(DEFAULT_HOTKEYS)


def save_hotkeys(hotkeys: Dict[str, str]) -> bool:
    """保存热键配置"""
    path = _config_path()
    try:
        # 只保存非默认的键（精简文件）
        to_save = {k: v for k, v in hotkeys.items() if v != DEFAULT_HOTKEYS.get(k)}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def validate_hotkey(hotkey_str: str) -> bool:
    """验证热键字符串格式是否合法"""
    if not hotkey_str or not hotkey_str.strip():
        return False

    hk = hotkey_str.strip().lower()
    parts = hk.split("+")

    # 至少需要 1 个修饰键 + 1 个普通键
    if len(parts) < 2:
        return False

    # 最后一个必须是普通键（非修饰键）
    main_key = parts[-1]
    if main_key in MODIFIERS:
        return False

    # 修饰键必须合法
    for p in parts[:-1]:
        if p not in MODIFIERS:
            return False

    return True


# ============================================================
# 功能开关配置（截图后显示哪些功能按钮）
# ============================================================

DEFAULT_FEATURE_TOGGLES = {
    "check_status": True,    # 出入库查询
    "query_parts": True,     # 遗物内容查询
    "translate": False,      # 翻译英文（默认关闭）
}

# 物品区域配置文件路径
def _item_region_config_path() -> str:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "item_region.json")


def _load_item_regions_raw() -> dict:
    """加载完整的物品区域配置（含所有槽位和选中状态）。"""
    path = _item_region_config_path()
    default = {"active": "1", "regions": {"1": None, "2": None, "3": None}}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容旧格式: 直接是 {'x','y','w','h'}
        if isinstance(data, dict) and all(k in data for k in ('x', 'y', 'w', 'h')):
            return {"active": "1", "regions": {"1": data, "2": None, "3": None}}
        # 新格式
        if isinstance(data, dict) and "regions" in data:
            if "active" not in data:
                data["active"] = "1"
            for k in ("1", "2", "3"):
                if k not in data["regions"]:
                    data["regions"][k] = None
            return data
    except Exception:
        pass
    return default


def _save_item_regions_raw(data: dict) -> bool:
    """保存完整的物品区域配置。"""
    path = _item_region_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def load_item_region() -> dict | None:
    """加载当前选中的物品区域。返回 {'x','y','w','h'} 或 None。"""
    cfg = _load_item_regions_raw()
    active = cfg.get("active", "1")
    return cfg["regions"].get(active)


def load_all_item_regions() -> dict:
    """加载所有物品区域配置（含 active 和 regions）。"""
    return _load_item_regions_raw()


def get_active_region_key() -> str:
    """获取当前选中的区域槽位 key: '1', '2', '3'。"""
    return _load_item_regions_raw().get("active", "1")


def save_item_region(region: dict, slot: str = "1") -> bool:
    """保存物品区域到指定槽位。

    Args:
        region: {'x','y','w','h'} 或 None（清除）
        slot: '1', '2', '3'
    """
    cfg = _load_item_regions_raw()
    cfg["regions"][slot] = region
    return _save_item_regions_raw(cfg)


def clear_item_region(slot: str = "1") -> bool:
    """清除指定槽位的物品区域。"""
    return save_item_region(None, slot)


def set_active_region(slot: str) -> bool:
    """切换当前选中的物品区域槽位。

    Args:
        slot: '1', '2', '3'
    """
    if slot not in ("1", "2", "3"):
        return False
    cfg = _load_item_regions_raw()
    cfg["active"] = slot
    return _save_item_regions_raw(cfg)

def _get_feature_toggle_label(key: str) -> str:
    """动态获取功能开关标签（跟随语言预设）。"""
    try:
        from data.ui_strings import S
        return S("feature_toggle", f"label_{key}")
    except Exception:
        pass
    return {
        "check_status": "出入库查询",
        "query_parts": "遗物内容查询",
        "translate": "自动翻译",
    }.get(key, key)


def get_feature_toggle_labels() -> dict:
    """获取功能开关标签字典（动态读取）。"""
    return {k: _get_feature_toggle_label(k) for k in DEFAULT_FEATURE_TOGGLES}


# 向后兼容的模块级变量（懒加载）
FEATURE_TOGGLE_LABELS = {k: "" for k in DEFAULT_FEATURE_TOGGLES}

FEATURE_TOGGLE_REQUIRES = {
    # 每个功能需要什么 OCR 类型
    "check_status": "relic",
    "query_parts": "relic",
    "query_price": "item",
    "translate": "text",
}


def _feature_config_path() -> str:
    """获取功能开关配置文件路径。"""
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "feature_toggles.json")


def load_feature_toggles() -> dict:
    """加载功能开关配置，不存在则返回默认值。"""
    path = _feature_config_path()
    if not os.path.exists(path):
        return dict(DEFAULT_FEATURE_TOGGLES)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = dict(DEFAULT_FEATURE_TOGGLES)
        if isinstance(data, dict):
            for key in DEFAULT_FEATURE_TOGGLES:
                if key in data:
                    result[key] = bool(data[key])
        return result
    except (json.JSONDecodeError, Exception):
        return dict(DEFAULT_FEATURE_TOGGLES)


def save_feature_toggles(toggles: dict) -> bool:
    """保存功能开关配置。"""
    path = _feature_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(toggles, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False
