"""
[L0/L1] core.hotkey_config — 热键配置管理

职责:
- 读写 data/hotkeys.json
- 提供默认热键
- 支持 keyboard 库格式的热键字符串(如 "ctrl+t")
- 维护热键 UI 标签(HOTKEY_LABELS)

依赖: Python 标准库
被谁用: core.hotkey_manager / core.pages.toggles_page

注意: 本模块是纯数据层,无 Qt 依赖

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

import json
import os
from typing import Dict

from data.ui_strings import S


# 默认热键
DEFAULT_HOTKEYS = {
    "select": "ctrl+g",           # 框选截图
    "fullscreen": "ctrl+h",       # 全屏截图
    "eye_mask": "ctrl+j",     # 护眼遮罩 开关
    "bring_to_front": "ctrl+b",   # 窗口置顶(一次性拉到最前)
    "cd_1": "1",              # CD 辅助 技能 1
    "cd_2": "2",              # CD 辅助 技能 2
    "cd_3": "3",              # CD 辅助 技能 3
    "cd_4": "4",              # CD 辅助 技能 4
}

# 各快捷键默认启用状态（出厂默认全部启用）
DEFAULT_HOTKEY_ENABLED = {k: True for k in DEFAULT_HOTKEYS}

# hotkeys.json 中存放启用状态的子键名（与 action 名不冲突）
_ENABLED_KEY = "enabled"

# 可用的修饰键
MODIFIERS = ["ctrl", "alt", "shift", "win"]

# 热键功能说明
HOTKEY_LABELS = {
    "select": S("hotkey", "label_select"),
    "fullscreen": S("hotkey", "label_fullscreen"),
    "eye_mask": S("hotkey", "label_eye_mask"),
    "bring_to_front": S("hotkey", "label_bring_to_front"),
}


def _config_path() -> str:
    """获取配置文件路径(打包/开发环境自适应,见 core.paths)"""
    from core.paths import ensure_user_file
    return str(ensure_user_file("hotkeys.json"))


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


def _read_config_raw() -> dict:
    """读取 hotkeys.json 原始内容（损坏/不存在时返回空 dict）。"""
    path = _config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, Exception):
        return {}


def save_hotkeys(hotkeys: Dict[str, str]) -> bool:
    """保存热键配置（保留已有的 enabled 子字段，避免覆盖启用状态）。"""
    path = _config_path()
    try:
        existing = _read_config_raw()
        enabled_saved = existing.get(_ENABLED_KEY, {})
        # 只保存非默认的键（精简文件）
        to_save = {k: v for k, v in hotkeys.items() if v != DEFAULT_HOTKEYS.get(k)}
        if enabled_saved:
            to_save[_ENABLED_KEY] = enabled_saved
        with open(path, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def load_hotkey_enabled() -> Dict[str, bool]:
    """加载各快捷键的启用状态。返回 {action: bool}，缺失时默认全部启用。

    存储位置: hotkeys.json 的 "enabled" 子字段，与热键字符串同文件，
    保证修改热键和切换启用状态不会互相覆盖。
    """
    result = dict(DEFAULT_HOTKEY_ENABLED)
    data = _read_config_raw()
    enabled = data.get(_ENABLED_KEY, {})
    if isinstance(enabled, dict):
        for key in DEFAULT_HOTKEYS:
            if key in enabled:
                result[key] = bool(enabled[key])
    return result


def save_hotkey_enabled(enabled: Dict[str, bool]) -> bool:
    """保存各快捷键的启用状态（保留已有的热键字符串，避免覆盖按键配置）。"""
    path = _config_path()
    try:
        existing = _read_config_raw()
        # 保留热键字符串部分（只存非默认值，与 save_hotkeys 一致）
        hotkeys_part = {
            k: v for k, v in existing.items()
            if k in DEFAULT_HOTKEYS and isinstance(v, str) and v != DEFAULT_HOTKEYS.get(k)
        }
        hotkeys_part[_ENABLED_KEY] = {k: bool(v) for k, v in enabled.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(hotkeys_part, f, indent=2, ensure_ascii=False)
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
}

# 物品区域配置文件路径
def _item_region_config_path() -> str:
    from core.paths import ensure_user_file
    return str(ensure_user_file("item_region.json"))


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
}


def _feature_config_path() -> str:
    """获取功能开关配置文件路径(打包/开发环境自适应,见 core.paths)。"""
    from core.paths import ensure_user_file
    return str(ensure_user_file("feature_toggles.json"))


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
