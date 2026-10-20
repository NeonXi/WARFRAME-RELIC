"""
[L-Service] RivenCalcService — 紫卡数值计算（纯逻辑层）

依赖: Python 标准库(json / pathlib) + core.paths
禁止: PySide6 / QtWidgets / QtGui / QtCore（纯逻辑层）
返回: dict / list / float / str（绝不返回 Qt 对象）

计算模型（与 docs/紫卡基准数值.xlsx 一致）:
    最终数值 = 基础数值 × 倾向值 × 修正系数 × 浮动系数
    - 基础数值: 词条在特定武器类型下的基准值（来自 riven_base.json）
    - 倾向值:   由玩家填写的武器紫卡倾向（如 1.35，最多两位小数）
    - 修正系数: 由词条布局决定，分「正面系数 pos」与「负面系数 neg」
                （2正 / 2正1负 / 3正 / 3正1负 四种布局）
    - 浮动系数: 紫卡词条数值的高低浮动，下限 0.9、上限 1.1

布局与系数（layouts）:
    "2正"    : pos=0.99,   neg=0      （无负面槽）
    "2正1负" : pos=1.2375, neg=-0.495 （含负面槽）
    "3正"    : pos=0.75,   neg=0      （无负面槽）
    "3正1负" : pos=0.9375, neg=-0.75  （含负面槽）

词条分两组输出:
    - 正面词条: 用 pos 系数计算（若该布局 neg=0 则仅此一组）
    - 负面词条: 用 neg 系数计算（仅当 neg≠0 时存在，即含负面槽的布局）

数值格式（与页面约定一致，不在此层拼界面，只产出字符串）:
    - "%" 单位: 结果视为「×1.0 = 100%」的量纲，格式化时 ×100 并带 "%"，
               正数前置 "+"（如 "+187.9%"），负数自然带 "-"（如 "-82.0%"），
               保留 1 位小数。
    - "n"  单位: 纯数字（连击持续时间 / 初始连击 / 穿透 / 范围），
               保留 2 位小数，不带 "%"。

注意「后坐力」在源表里基值为负（-0.9）：公式对正负两组统一处理
（value = base × coef × disposition × float），符号由 base 与 coef 自然
决定 —— 正面组得到「后坐力降低（负）」、负面组得到「后坐力升高（正）」，
无需特判，与游戏内「正面减后坐力、负面加后坐力」一致。

数据文件 riven_base.json 为只读资源（resource_dir），打包随包分发、
运行期绝不写入。

词条合并说明（2026-10-20）:
    源表里 冰冻/毒素/电击/火焰 四个元素伤害词条基础数值完全一致，
    冲击/切割/穿刺 三个物理伤害词条也一致，因此在 riven_base.json 中
    合并为「属性伤害」「物理伤害」两条，并新增「异常状态伤害」
    （基础数值与「触发几率」相同）。
    例外：手枪的「冲击」原值为 1.188（与切割/穿刺的 1.1997 不同），
    因此单独保留「冲击伤害」一条，且仅手枪有值、其余武器为 null
    （该词条只在选择手枪时出现）。
    注意: docs/紫卡基准数值.xlsx 仍保留原始拆分词条，若需重新生成
    JSON，合并规则需在生成脚本中复现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.paths import resource_dir

# ── 常量 ──

_FILE_NAME = "riven_base.json"

# 结果排序：按「最高值绝对值」降序，让最值钱的词条排在前面
# 结果数值的字段名（页面与测试均依赖此契约）
RESULT_KEY_NAME = "name"
RESULT_KEY_UNIT = "unit"
RESULT_KEY_MIN = "min"
RESULT_KEY_MAX = "max"
RESULT_KEY_MIN_STR = "min_str"
RESULT_KEY_MAX_STR = "max_str"

# 数值精度：% 单位 1 位小数，n 单位 2 位小数
_PCT_DECIMALS = 1
_NUM_DECIMALS = 2

# 模块级缓存（数据文件只读，加载一次即可）
_data_cache: Optional[dict] = None


# ── 数据加载 ──


def _data_path() -> Path:
    """只读资源路径（随包分发，绝不写入）。"""
    return resource_dir() / _FILE_NAME


def load_data() -> dict:
    """读取紫卡基础数值数据；结果模块级缓存，失败抛异常由调用方处理。

    缓存策略：数据文件为静态只读资源，仅首次调用读盘，之后复用同一 dict。
    测试可通过 ``reload_data()`` 强制刷新。
    """
    global _data_cache
    if _data_cache is None:
        with open(_data_path(), "r", encoding="utf-8") as f:
            _data_cache = json.load(f)
    return _data_cache


def reload_data() -> dict:
    """强制重新读盘（主要用于测试隔离或数据源热更新）。"""
    global _data_cache
    _data_cache = None
    return load_data()


# ── 只读查询接口 ──


def list_weapon_types() -> list[str]:
    """返回全部武器类型（步枪/霰弹枪/手枪/空战/近战）。"""
    return list(load_data()["weapon_types"])


def list_layouts() -> list[str]:
    """返回布局顺序（带负面槽的排在后，符合「先纯正面再带负面直觉）。"""
    return list(load_data()["layout_order"])


def get_layout(layout: str) -> Optional[dict]:
    """返回某布局的系数 dict {"pos": float, "neg": float}，未知布局返回 None。

    返回的是浅拷贝：内部 _data_cache 是模块级共享对象，直接返回引用
    会让调用方有机会改坏缓存（如误写 layout["pos"] = 0）。
    """
    layout_def = load_data()["layouts"].get(layout)
    return dict(layout_def) if layout_def is not None else None


def float_range() -> tuple[float, float]:
    """返回浮动系数 (min, max) = (0.9, 1.1)。"""
    fr = load_data()["float"]
    return float(fr["min"]), float(fr["max"])


# ── 数值格式化（纯函数） ──


def format_value(value: float, unit: str) -> str:
    """按单位格式化单个计算结果。

    Args:
        value: 已乘完 base×disposition×coef×float 的最终量纲值
        unit:  "%" 表示百分比量纲（×100 + %，1 位小数，正加 "+"）；
               其它任意值视为纯数字（2 位小数，无 "%"）

    Returns:
        展示字符串，如 "+187.9%" / "-82.0%" / "3.06" / "2.80"
    """
    # 消除浮点符号零（-0.0 在视觉上应与 0.0 一致）
    if abs(value) < 1e-12:
        value = 0.0
    if unit == "%":
        scaled = value * 100.0
        text = f"{scaled:.{_PCT_DECIMALS}f}%"
        # 正数显式补 "+"（负数本身带 "-"，零不加符号）
        if scaled > 0:
            return "+" + text
        return text
    return f"{value:.{_NUM_DECIMALS}f}"


# ── 核心计算 ──


def _compute_group(
    attributes: list[dict],
    weapon_type: str,
    disposition: float,
    coef: float,
) -> list[dict]:
    """计算某一组（正面或负面）词条的结果行。

    仅纳入该武器类型下存在基础数值（非 None）的词条；
    结果按「最高值绝对值」降序排序。

    Args:
        attributes: 数据文件中的 attributes 列表
        weapon_type: 当前武器类型
        disposition: 玩家填写的倾向值
        coef: 本组系数（正面用 pos，负面用 neg）

    Returns:
        结果行列表，每行含 name/unit/min/max/min_str/max_str
    """
    lo, hi = float_range()
    rows: list[dict] = []
    for attr in attributes:
        base = attr["values"].get(weapon_type)
        if base is None:
            # 该武器类型无此词条（如 后坐力 对 近战 无数据）→ 跳过
            continue
        min_val = base * disposition * coef * lo
        max_val = base * disposition * coef * hi
        rows.append({
            RESULT_KEY_NAME: attr["name"],
            RESULT_KEY_UNIT: attr["unit"],
            RESULT_KEY_MIN: min_val,
            RESULT_KEY_MAX: max_val,
            RESULT_KEY_MIN_STR: format_value(min_val, attr["unit"]),
            RESULT_KEY_MAX_STR: format_value(max_val, attr["unit"]),
        })
    # 按最高值绝对值降序（最值钱/影响最大的排前）
    rows.sort(key=lambda r: abs(r[RESULT_KEY_MAX]), reverse=True)
    return rows


def compute(weapon_type: str, disposition: float, layout: str) -> dict:
    """计算紫卡在某武器/倾向/布局下的全部词条上下限。

    Args:
        weapon_type: 武器类型（须为 list_weapon_types() 之一）
        disposition: 倾向值（玩家填写，任意浮点；调用方负责范围校验）
        layout: 布局（须为 list_layouts() 之一）

    Returns:
        {
            "weapon_type": str,
            "disposition": float,
            "layout": str,
            "has_negative": bool,   # 是否含负面槽（neg≠0）
            "positive": [行...],     # 正面词条结果（始终非空）
            "negative": [行...],     # 负面词条结果（has_negative 为假时为空）
        }

    未知武器类型 / 布局时，对应组退化为空列表（不抛异常），
    便于页面在非法组合下优雅清空表格。
    """
    data = load_data()
    attributes = data["attributes"]
    layout_def = data["layouts"].get(layout)

    positive_rows: list[dict] = []
    negative_rows: list[dict] = []
    has_negative = False

    if layout_def is not None and weapon_type in data["weapon_types"]:
        pos_coef = float(layout_def["pos"])
        neg_coef = float(layout_def["neg"])
        has_negative = neg_coef != 0.0
        positive_rows = _compute_group(attributes, weapon_type, disposition, pos_coef)
        if has_negative:
            negative_rows = _compute_group(attributes, weapon_type, disposition, neg_coef)

    return {
        "weapon_type": weapon_type,
        "disposition": disposition,
        "layout": layout,
        "has_negative": has_negative,
        "positive": positive_rows,
        "negative": negative_rows,
    }
