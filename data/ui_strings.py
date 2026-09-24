"""
[L-Service] ui_strings — UI 字符串集中管理（路由器）

依赖: Python 标准库 + core.paths
禁止: PySide6 / QtWidgets / QtGui / QtCore
职责: 所有在 UI 中展示的字符串都写在这里，方便维护和未来国际化。

使用方式：
    from data.ui_strings import S
    label.setText(S("title", "main_window"))
    button.setText(S("button", "exit"))

语言预设切换：
    from data.ui_strings import reload_strings, set_language_preset
    set_language_preset("normal")         # 切换到普通版

预设文件位于 data/ 目录下:
  - preset_normal.json         (普通直白风格)
"""

import json
import os
from pathlib import Path

from core.paths import resource_dir, user_data_dir


# ============================================================
# 预设配置
# ============================================================

def _data_dir() -> Path:
    """预设文件目录(只读资源)。"""
    return resource_dir()

def _config_path() -> Path:
    """语言预设配置文件(用户可写)。"""
    return user_data_dir() / "language_preset.json"

def _load_config() -> dict:
    path = _config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return {"active": "normal"}

def _save_config(config: dict):
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def _load_preset(preset_id: str) -> dict:
    """加载指定预设的 STRINGS 字典。"""
    preset_file = _data_dir() / f"preset_{preset_id}.json"
    if not preset_file.exists():
        return {}

    try:
        with open(preset_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ============================================================
# 初始化：加载活跃预设
# ============================================================

_config = _load_config()
_active_preset_id = _config.get("active", "normal")
STRINGS = _load_preset(_active_preset_id)

# 如果活跃预设加载失败，回退到 normal
if not STRINGS:
    STRINGS = _load_preset("normal")
    _active_preset_id = "normal"


# ============================================================
# 便捷访问函数
# ============================================================

class _StringsAccessor:
    """提供 S("category", "key") 和 S.format("category", "key", **kwargs) 的访问方式。"""

    def __getitem__(self, key):
        """S["category"] 返回子字典。"""
        return STRINGS.get(key, {})

    def __call__(self, category: str, key: str) -> str:
        """S("category", "key") 返回字符串。"""
        try:
            return STRINGS[category][key]
        except KeyError:
            return f"??{category}.{key}??"

    def format(self, category: str, key: str, **kwargs) -> str:
        """S.format("category", "key", arg1=val1, ...) 返回格式化后的字符串。"""
        try:
            template = STRINGS[category][key]
            return template.format(**kwargs)
        except KeyError:
            return f"??{category}.{key}??"

    def categories(self):
        """返回所有类别名。"""
        return list(STRINGS.keys())


S = _StringsAccessor()


# ============================================================
# 预设管理 API
# ============================================================

def get_active_preset() -> str:
    """返回当前活跃预设的 ID。"""
    return _active_preset_id

def get_preset_info() -> dict:
    """返回预设列表信息。"""
    config = _load_config()
    return config.get("presets", {})

def set_language_preset(preset_id: str) -> bool:
    """
    切换到指定语言预设。返回是否成功。
    调用后所有通过 S() 获取的字符串会立即更新。
    """
    global STRINGS, _active_preset_id

    new_strings = _load_preset(preset_id)
    if not new_strings:
        return False

    STRINGS = new_strings
    _active_preset_id = preset_id

    config = _load_config()
    config["active"] = preset_id
    _save_config(config)

    return True

def reload_strings():
    """从配置文件重新加载当前预设（用于外部修改预设文件后刷新）。"""
    global STRINGS, _active_preset_id
    config = _load_config()
    _active_preset_id = config.get("active", "normal")
    STRINGS = _load_preset(_active_preset_id)
    if not STRINGS:
        STRINGS = _load_preset("normal")
        _active_preset_id = "normal"
