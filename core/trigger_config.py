"""
[L0/L1] core.trigger_config — 辅助触发器配置

职责:
- 读写 data/triggers.json
- 定义触发器数据模型和选项枚举
- 提供默认配置、加载、保存、验证

数据模型设计原则:
- 使用纯 dict 结构(非 dataclass),方便 JSON 序列化和 UI 直接绑定
- 动作采用 list[dict] 有序列表,支持多动作串联
- 每个动作的 "type" 字段决定解析方式,新增动作类型只需扩展 ACTION_TYPES

依赖: Python 标准库
被谁用: core.trigger_manager / core.pages.triggers_page

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
import copy


# ============================================================
# 常量定义 — 触发输入类型
# ============================================================

TRIGGER_INPUT_TYPES = ["mouse", "keyboard"]
TRIGGER_INPUT_LABELS = {
    "mouse": "鼠标按键",
    "keyboard": "键盘按键",
}

MOUSE_BUTTONS = [
    ("left_press",    "左键 按下"),
    ("left_release",  "左键 抬起"),
    ("right_press",   "右键 按下"),
    ("right_release", "右键 抬起"),
    ("middle_press",  "中键 按下"),
    ("middle_release","中键 抬起"),
    ("side1_press",   "鼠标4键 按下"),   # XBUTTON1(侧键1,常为浏览器后退)
    ("side1_release", "鼠标4键 抬起"),
    ("side2_press",   "鼠标5键 按下"),   # XBUTTON2(侧键2,常为浏览器前进)
    ("side2_release", "鼠标5键 抬起"),
]

# 简写映射：旧配置兼容（"left"/"right"/"middle" → 默认为按下）
MOUSE_BUTTON_LEGACY_MAP = {
    "left":   "left_press",
    "right":  "right_press",
    "middle": "middle_press",
    "side1":  "side1_press",
    "side2":  "side2_press",
}

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
    """获取触发器配置文件路径(打包/开发环境自适应,见 core.paths)。"""
    from core.paths import ensure_user_file
    return str(ensure_user_file("triggers.json"))


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
        raw_btn = ti.get("button", "right_press")
        # 兼容旧配置简写
        btn_key = MOUSE_BUTTON_LEGACY_MAP.get(raw_btn, raw_btn)
        btn_label = dict(MOUSE_BUTTONS).get(btn_key, raw_btn)
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
        raw_btn = ti.get("button", "right_press")
        # 兼容旧简写 → 转为完整格式
        result["trigger_input"]["button"] = MOUSE_BUTTON_LEGACY_MAP.get(raw_btn, raw_btn)
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
