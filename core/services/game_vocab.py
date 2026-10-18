"""
[L-Service] game_vocab — Warframe 游戏术语词表(纯常量,零依赖)

归属层:    [L-Service] (core/services/) — 纯数据模块,不参与业务流程
允许依赖:  无(仅 Python 内置 dict)
禁止依赖:  PySide6 / core.widgets / core.pages / core.state / 任何 IO

存在理由:
  任务类型 / 裂缝纪元这两张表原本在 `worldstate_service` 与已删除的
  `log_parser_service` 各维护一份,靠注释「与 xxx 保持一致」人肉同步,
  2026-10-19 审计时已发现漂移,故收敛为单一事实源:
  **新增/修改术语只改本文件**。

  日志分析功能已整体移除,因此派系中文表与"纪元→中文"派生表一并删除;
  如需恢复,从 git 历史取回即可。

约定:
  - 中文名优先使用游戏内官方译名
  - 查表未命中时由调用方决定回落策略(保留英文/去前缀等),
    本模块不提供 get() 包装,避免把回落策略也固化进来
"""

from __future__ import annotations

# ── 任务类型: MT_XXX → 中文 ──
MISSION_TYPE_ZH: dict[str, str] = {
    "MT_DEFENSE": "防御",
    "MT_MOBILE_DEFENSE": "移动防御",
    "MT_RESCUE": "救援",
    "MT_SURVIVAL": "生存",
    "MT_INTEL": "间谍",
    "MT_EXTERMINATION": "歼灭",
    "MT_EXTERMINATE": "歼灭",
    "MT_CAPTURE": "捕获",
    "MT_EXCAVATE": "挖掘",
    "MT_DISRUPTION": "中断",
    "MT_INTERCEPTION": "拦截",
    "MT_ASSASSINATION": "刺杀",
    "MT_HIVE": "巢袭",
    "MT_SABOTAGE": "破坏",
    "MT_ARENA": "竞技场",
    "MT_LANDSCAPE": "自由探索",
    "MT_RUSH": "追击",
    "MT_ALCHEMY": "炼金",
    "MT_CORRUPTION": "腐化",
    "MT_TERRITORY": "拦截",
    "MT_VOID_CASCADE": "虚空覆涌",
    "MT_ASSAULT": "强袭",
    "MT_ARTIFACT": "特殊任务",
    "MT_RAILJACK": "九重天",
}

# ── 裂缝纪元: VoidT1~T6 → (英文, 中文) ──
# 消费方按需取 v[0] 或 v[1]，不额外派生只含中文的字典
VOID_TIER: dict[str, tuple[str, str]] = {
    "VoidT1": ("Lith", "古纪"),
    "VoidT2": ("Meso", "前纪"),
    "VoidT3": ("Neo", "中纪"),
    "VoidT4": ("Axi", "后纪"),
    "VoidT5": ("Requiem", "安魂"),
    "VoidT6": ("Omnia", "全能"),
}
