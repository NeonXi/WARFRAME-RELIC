"""
辅助触发器配置模块
- 读写 data/triggers.json
- 定义触发器数据模型和选项枚举
- 提供默认配置、加载、保存、验证

数据模型设计原则：
- 使用纯 dict 结构（非 dataclass），方便 JSON 序列化和 UI 直接绑定
- 动作采用 list[dict] 有序列表，支持多动作串联
- 每个动作的 "type" 字段决定解析方式，新增动作类型只需扩展 ACTION_TYPES
"""

import json
import os
import copy
from pathlib import Path
from typing import Dict, Optional


# ============================================================
# 常量定义 — 触发输入类型
# ============================================================

TRIGGER_INPUT_TYPES = ["mouse", "keyboard"]
TRIGGER_INPUT_LABELS = {
    "mouse": "鼠标按键",
    "keyboard": "键盘按键",
}

MOUSE_BUTTONS = [
    ("left",   "左键"),
    ("right",  "右键"),
    ("middle", "中键"),
    ("x1",     "侧键1 (前进)"),
    ("x2",     "侧键2 (后退)"),
]

MOUSE_BUTTON_VALUES = [b[0] for b in MOUSE_BUTTONS]


# ============================================================
# 常量定义 — 响应动作类型
# ============================================================

ACTION_TYPES = [
    ("key",         "按键"),
    ("mouse_click", "鼠标点击"),
    ("mouse_move",  "鼠标移动"),       # 移动到指定屏幕坐标
]

ACTION_TYPE_VALUES = [a[0] for a in ACTION_TYPES]

MOUSE_CLICK_BUTTONS = [
    ("left",   "左键"),
    ("right",  "右键"),
    ("middle", "中键"),
]

MOUSE_CLICK_VALUES = [b[0] for b in MOUSE_CLICK_BUTTONS]


# ============================================================
# 默认配置
# ============================================================

DEFAULT_TRIGGERS = [
    {
        "name": "快速拾取",
        "enabled": True,
        "trigger_input": {
            "type": "mouse",
            "button": "right",
            "key": "",
        },
        "delay_ms": 10,
        "actions": [
            {
                "type": "key",
                "value": "4",
            }
        ],
    },
]


def _config_path() -> str:
    """获取触发器配置文件路径。"""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "triggers.json")


def load_triggers() -> list[dict]:
    """加载触发器列表。

    Returns:
        触发器 dict 列表，每个包含 name/enabled/trigger_input/delay_ms/actions。
        文件不存在或损坏时返回默认值。
    """
    path = _config_path()
    if not os.path.exists(path):
        return _deep_copy_defaults()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [_validate_trigger(t) for t in data]
        return _deep_copy_defaults()
    except (json.JSONDecodeError, Exception):
        return _deep_copy_defaults()


def save_triggers(triggers: list[dict]) -> bool:
    """保存触发器列表到文件（原子写入，防止数据丢失）。

    Args:
        triggers: 完整的触发器列表（会覆盖文件）。
    """
    path = _config_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(triggers, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)  # 原子替换（Windows 上若目标存在则替换）
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def create_blank_trigger() -> dict:
    """创建一个空白的触发器模板（用于「新增」按钮）。"""
    return {
        "name": "",
        "enabled": False,
        "trigger_input": {
            "type": "mouse",
            "button": "right",
            "key": "",
        },
        "delay_ms": 10,
        "actions": [
            {
                "type": "key",
                "value": "",
            }
        ],
    }


def create_blank_action(action_type: str = "key") -> dict:
    """创建一个空白的动作模板。

    Args:
        action_type: 动作类型，决定 value 的语义。
    """
    return {
        "type": action_type,
        "value": "",
    }


def get_action_placeholder(action_type: str) -> str:
    """根据动作类型返回输入框的占位提示文本。"""
    return {
        "key":         "如: 4 / f / ctrl+4 / space",
        "mouse_click": "选择鼠标按钮",
        "mouse_move":  "如: 960, 540 (绝对) 或 +100, -50 (相对)",
    }.get(action_type, "")


def format_action_summary(action: dict) -> str:
    """将动作格式化为简短摘要文本（显示在开关按钮第二行）。

    Args:
        action: 单个动作 dict。

    Returns:
        如 "按键4" / "左键点击" / "移动至(960,540)"
    """
    atype = action.get("type", "")
    val = action.get("value", "")

    if atype == "key":
        return f"按键 {val}" if val else "按键 (未设置)"
    elif atype == "mouse_click":
        label = dict(MOUSE_CLICK_BUTTONS).get(val, val)
        return f"{label}点击" if val else "鼠标点击 (未设置)"
    elif atype == "mouse_move":
        return f"移动至({val})" if val else "鼠标移动 (未设置)"
    return val or "(未知)"


def format_trigger_summary(trigger: dict) -> str:
    """格式化触发器的完整摘要（触发→延迟→动作）。

    用于开关按钮的第二行文字。
    """
    ti = trigger.get("trigger_input", {})
    ti_type = ti.get("type", "mouse")
    delay = trigger.get("delay_ms", 0)
    actions = trigger.get("actions", [])

    # 触发部分
    if ti_type == "mouse":
        btn_label = dict(MOUSE_BUTTONS).get(ti.get("button", ""), "?")
        trigger_desc = f"{btn_label}"
    else:
        trigger_desc = f"键:{ti.get('key', '?')}"

    # 动作部分（取第一个动作的摘要）
    action_desc = ""
    if actions:
        action_desc = format_action_summary(actions[0])
    if len(actions) > 1:
        action_desc += f" +{len(actions)-1}"

    return f"{trigger_desc} → {delay}ms → {action_desc}"


# ============================================================
# 内部工具
# ============================================================

def _deep_copy_defaults() -> list[dict]:
    """深拷贝默认触发器列表（避免修改全局常量）。"""
    return copy.deepcopy(DEFAULT_TRIGGERS)


def _validate_trigger(t: dict) -> dict:
    """验证并补全单个触发器字典的字段（防御性编程）。

    确保即使 JSON 文件被手动编辑/版本升级后缺少字段，
    程序也不会因 KeyError 崩溃。
    """
    result = create_blank_trigger()
    result["name"] = t.get("name", "")
    result["enabled"] = bool(t.get("enabled", False))
    result["delay_ms"] = int(t.get("delay_ms", 10))

    # trigger_input
    ti = t.get("trigger_input", {})
    if isinstance(ti, dict):
        result["trigger_input"]["type"] = ti.get("type", "mouse")
        result["trigger_input"]["button"] = ti.get("button", "right")
        result["trigger_input"]["key"] = ti.get("key", "")

    # actions
    raw_actions = t.get("actions", [])
    if isinstance(raw_actions, list):
        validated = []
        for a in raw_actions:
            if isinstance(a, dict):
                action = create_blank_action(a.get("type", "key"))
                action["value"] = a.get("value", "")
                validated.append(action)
        if validated:
            result["actions"] = validated
        elif raw_actions:
            # 所有 action 都无效，保留空列表（而非回退到默认空白动作）
            result["actions"] = []

    return result
