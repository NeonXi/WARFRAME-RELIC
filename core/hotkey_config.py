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


# 默认热键
DEFAULT_HOTKEYS = {
    "select": "ctrl+g",           # 框选截图
    "fullscreen": "ctrl+h",       # 全屏截图
    "panel": "ctrl+shift+g",     # 管理面板
}

# 可用的修饰键
MODIFIERS = ["ctrl", "alt", "shift", "win"]

# 热键功能说明
HOTKEY_LABELS = {
    "select": "框选截图识别",
    "fullscreen": "全屏截图识别",
    "panel": "管理面板",
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
