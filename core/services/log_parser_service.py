"""
[L-Service] LogParserService — Warframe 游戏日志(EE.log)解析服务

依赖: Python 标准库 + json(节点翻译表)
禁止: PySide6 / QtWidgets / QtGui / QtCore(Signal 除外,本服务纯同步无需 Signal)
返回: dict / list / int / str(原始类型,绝不返回 Qt 对象)

职责:
  - 逐行解析 EE.log,提取任务记录与统计数据
  - 翻译 SolNodeID → 节点名/派系/任务类型(复用 data/worldstate/solNodes.json)
  - 输出供「日志分析」页面消费的结构化数据(统计卡片 + 图表数据)

解析的关键日志模式:
  - Set squad mission: {"name":"SolNodeXX","voidTier":"VoidT6"}  → 节点/裂缝纪元
  - OnStateStarted, mission type=MT_SURVIVAL                       → 任务开始
  - FrameworkCmd::OpenLevel - /Lotus/Levels/PlayerShip             → 任务结束(回轨道站)
  - MISSION_REWARD_CREDITS: N                                      → 信用点奖励
  - SyndicateXP base for mission: N                                → 集团声望
  - Mission Succeeded / Mission Failed                             → 任务结果
  - AddSquadMember: 玩家名                                          → 组队成员
  - was downed by                                                  → 玩家倒地
  - DHardMissionStartTeshin                                        → 钢铁之路标记

## AI 硬约束
归属层:    [L-Service] (core/services/)
允许依赖:  json, re, time, core.paths
禁止依赖:  PySide6 / Qt / widgets / pages / data 内业务模块
必读规范:  .trae/rules/开发规范.md §6.2

本文件红线:
- ✗ 禁止 import PySide6(纯逻辑,不碰 UI)
- ✗ 禁止返回 Qt 对象
- ✗ 禁止抛异常到 UI → try/except + 返回 None/False + 日志
- ✗ 禁止 __file__ 裸推导路径 → 用 core.paths
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core import paths

_logger = logging.getLogger("core.services.log_parser")


# ── 任务类型中文映射(与 worldstate_service._MISSION_MAP 保持一致) ──
_MISSION_MAP: dict[str, str] = {
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

# ── 裂缝纪元映射 ──
_TIER_MAP: dict[str, str] = {
    "VoidT1": "古纪",
    "VoidT2": "前纪",
    "VoidT3": "中纪",
    "VoidT4": "后纪",
    "VoidT5": "安魂",
    "VoidT6": "全能",
}

# ── 派系中文映射 ──
_ENEMY_MAP: dict[str, str] = {
    "Grineer": "Grineer",
    "Corpus": "Corpus",
    "Infested": "Infested",
    "Orokin": "堕落者",
    "Sentient": "Sentient",
    "Crossfire": "交战",
    "Narmer": "Narmer",
    "Murmur": "低语者",
}


@dataclass
class MissionRecord:
    """单个任务的解析结果。"""
    node_id: str = ""              # SolNode309
    node_name: str = ""            # Yuvarium (Lua)
    mission_type: str = ""         # MT_SURVIVAL
    mission_type_name: str = ""    # 生存
    enemy: str = ""                # Orokin
    enemy_name: str = ""           # 堕落者
    start_time: float = 0.0        # 日志时间戳(秒)
    end_time: float = 0.0          # 日志时间戳(秒)
    duration_min: float = 0.0      # 时长(分钟)
    credits: int = 0               # 信用点奖励
    syndicate_xp: int = 0          # 集团声望
    success: bool = False          # 是否成功
    is_steel_path: bool = False    # 钢铁之路
    is_void_fissure: bool = False  # 虚空裂缝
    void_tier: str = ""            # VoidT6
    void_tier_name: str = ""       # 全能
    squad_members: list[str] = field(default_factory=list)
    # 运行时维护:slot -> (name, rank),用于任务进行中实时更新段位
    squad_slot_info: dict[int, tuple[str, str]] = field(default_factory=dict)
    downed_count: int = 0          # 倒地次数
    mastery_rank: str = ""         # 主机段位区间(如 "34-36")
    is_ongoing: bool = False       # 日志结束时任务仍在进行中


@dataclass
class LogAnalysisResult:
    """完整的日志分析结果(供页面消费)。"""
    missions: list[MissionRecord] = field(default_factory=list)

    # ── 汇总统计(卡片用) ──
    total_missions: int = 0
    total_duration_min: float = 0.0
    total_credits: int = 0
    total_syndicate_xp: int = 0
    success_count: int = 0
    steel_path_count: int = 0
    void_fissure_count: int = 0
    downed_total: int = 0

    # ── 图表数据 ──
    # 任务类型分布: {类型名: 数量}
    mission_type_distribution: dict[str, int] = field(default_factory=dict)
    # 派系分布: {派系名: 数量}
    enemy_distribution: dict[str, int] = field(default_factory=dict)
    # 每任务信用点: [(节点短名, 信用点)]
    credits_by_mission: list[tuple[str, int]] = field(default_factory=list)
    # 每任务时长: [(节点短名, 分钟)]
    duration_by_mission: list[tuple[str, float]] = field(default_factory=list)
    # 每任务声望: [(节点短名, 声望)]
    syndicate_by_mission: list[tuple[str, int]] = field(default_factory=list)
    # 玩家倒地次数: {玩家名: 次数}
    downed_by_player: dict[str, int] = field(default_factory=dict)

    # ── 元信息 ──
    log_path: str = ""
    log_size_mb: float = 0.0
    parse_seconds: float = 0.0


class LogParserService:
    """游戏日志解析服务(纯逻辑,无状态)。

    使用方式::

        result = LogParserService.parse("d:/.../EE.log")
        if result:
            print(result.total_missions)
    """

    # ── 预编译正则(性能关键,25MB 日志逐行匹配) ──
    _RE_LINE = re.compile(r"^(\d+\.?\d*)\s+(\w+)\s+\[(\w+)\]:\s*(.*)$")
    _RE_SQUAD = re.compile(r'Set squad mission:\s*\{.*?"name"\s*:\s*"([^"]+)"')
    _RE_VOID_TIER = re.compile(r'"voidTier"\s*:\s*"(VoidT\d)"')
    # Host loading: 主机启动任务时输出,含节点+纪元,比 Set squad mission 更可靠
    _RE_HOST_LOADING = re.compile(
        r'Host loading\s*\{.*?"voidTier"\s*:\s*"([^"]*)".*?"name"\s*:\s*"([^"]+)"'
    )
    _RE_HOST_LOADING_NAME = re.compile(r'Host loading\s*\{.*?"name"\s*:\s*"([^"]+)"')
    _RE_MISSION_TYPE = re.compile(r"OnStateStarted,\s*mission type=(\w+)")
    _RE_PLAYER_SHIP = re.compile(r"OpenLevel\s*-\s*/Lotus/Levels/(?:Proc/)?PlayerShip")
    _RE_CREDITS = re.compile(r"MISSION_REWARD_CREDITS\):\s*(\d+)")
    _RE_SYNDICATE = re.compile(r"SyndicateXP base for mission:\s*(\d+)")
    _RE_SUCCESS = re.compile(r"Mission Succeeded")
    _RE_FAILED = re.compile(r"Mission Failed")
    _RE_SQUAD_MEMBER = re.compile(r"AddSquadMember:\s*(\S+).*squadCount=(\d+)")
    _RE_DOWNED = re.compile(r"(\S+)\s+was downed by")
    _RE_STEEL_PATH = re.compile(r"DHardMissionStartTeshin")
    # 钢铁之路奥术增益图标:late join 任务没有 Host loading/MissionInfo,
    # 用此作为辅助标记(玩家装备钢铁奥术时加载)
    _RE_STEEL_ARCANE = re.compile(r"SteelPathArcanesBuff")
    # 敌人最低等级:钢铁之路模式下敌人等级 >= 100,普通模式远低于此
    _RE_ENEMY_LEVEL = re.compile(r"minEnemyLevel=(\d+)")
    # 段位: OnMasteryIconReadyN + RankXXtoYY(N=1 表示主机自己)
    _RE_MASTERY = re.compile(r"OnMasteryIconReady(\d+)\(Loaded:.*Rank(\d+)to(\d+)")

    # 节点翻译表缓存(类级,首次加载)
    _node_table: dict[str, dict] = {}

    @classmethod
    def parse(cls, log_path: str) -> Optional[LogAnalysisResult]:
        """解析日志文件,返回结构化结果。

        Args:
            log_path: EE.log 的绝对路径

        Returns:
            LogAnalysisResult(成功) / None(文件不存在或解析失败)
        """
        import time

        path = Path(log_path)
        if not path.exists():
            _logger.error("日志文件不存在: %s", log_path)
            return None

        start = time.time()
        try:
            missions = cls._parse_missions(path)
        except Exception as e:
            _logger.exception("解析日志失败: %s", e)
            return None
        parse_seconds = round(time.time() - start, 2)

        result = cls._build_result(missions, log_path, path, parse_seconds)
        return result

    # ══════════════════════════════════
    #  核心解析
    # ══════════════════════════════════

    @classmethod
    def _parse_missions(cls, path: Path) -> list[MissionRecord]:
        """逐行扫描日志,提取任务记录。

        任务边界:
          - 开始: OnStateStarted, mission type=MT_XXX
          - 结束: 下一个 OpenLevel - PlayerShip(回轨道站)
                  或下一个 OnStateStarted(新任务开始,上一个无明确结束)
        """
        missions: list[MissionRecord] = []
        current: Optional[MissionRecord] = None
        node_table = cls._get_node_table()
        last_ts: float = 0.0  # 日志最后一行的时间戳(用于进行中任务的结束时间)

        # 临时字段:等待匹配的节点/纪元/段位/队员(在 OnStateStarted 之前出现)
        pending_node_id: str = ""
        pending_void_tier: str = ""
        pending_steel_path: bool = False  # MissionInfo 中敌人等级 >= 100
        # 按 slot(1-4) 存储队员名和段位,squadCount 即 slot 编号
        pending_squad_by_slot: dict[int, str] = {}
        pending_squad_mastery: dict[int, str] = {}  # slot -> 段位范围下限

        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = cls._RE_LINE.match(line)
                if m:
                    ts = float(m.group(1))
                    _subsys = m.group(2)
                    _level = m.group(3)
                    msg = m.group(4)
                    last_ts = ts  # 更新最后时间戳
                else:
                    # 无时间戳的行(如 MissionInfo 中的 minEnemyLevel=150),
                    # 复用最后时间戳,仅处理需要的字段
                    msg = line.strip()
                    if not msg or not cls._RE_ENEMY_LEVEL.search(msg):
                        continue

                # ── 1a. Set squad mission(设置任务节点,部分任务) ──
                sm = cls._RE_SQUAD.search(msg)
                if sm:
                    pending_node_id = sm.group(1)
                    tm = cls._RE_VOID_TIER.search(msg)
                    pending_void_tier = tm.group(1) if tm else ""
                    continue

                # ── 1b. Host loading(主机启动任务,含节点+纪元,最可靠) ──
                hl = cls._RE_HOST_LOADING.search(msg)
                if hl:
                    pending_void_tier = hl.group(1)  # 可能为空字符串(非裂缝)
                    pending_node_id = hl.group(2)
                    continue
                # 部分 Host loading 可能 voidTier 字段缺失,只取 name
                hln = cls._RE_HOST_LOADING_NAME.search(msg)
                if hln and "Host loading" in msg:
                    pending_node_id = hln.group(1)
                    continue

                # ── 1c. 段位(OnMasteryIconReady{slot},slot=1为主机) ──
                # 日志只记录段位图标分组(如 Rank34to36,每3段共用一图),
                # 无法获取精确段位,直接显示段位范围(如 "34-36")
                mm = cls._RE_MASTERY.search(msg)
                if mm:
                    slot = int(mm.group(1))
                    rank_range = f"{mm.group(2)}-{mm.group(3)}"  # 如 "34-36"
                    pending_squad_mastery[slot] = rank_range
                    # 任务进行中:实时更新当前任务的队员段位
                    if current is not None and slot in current.squad_slot_info:
                        name, _old_rank = current.squad_slot_info[slot]
                        current.squad_slot_info[slot] = (name, rank_range)
                        cls._refresh_squad_members(current)
                    continue

                # ── 1d. 敌人等级(钢铁之路判定:MissionInfo 中 minEnemyLevel >= 100) ──
                el = cls._RE_ENEMY_LEVEL.search(msg)
                if el:
                    if int(el.group(1)) >= 100:
                        pending_steel_path = True
                    continue

                # ── 2. 任务开始 ──
                mt = cls._RE_MISSION_TYPE.search(msg)
                if mt:
                    new_type = mt.group(1)
                    # Railjack 等多阶段任务:若上一个任务未结束且类型相同,
                    # 视为同一任务的阶段切换,不新建任务
                    if (current is not None and current.end_time == 0.0
                            and current.mission_type == new_type):
                        continue
                    # 上一个任务如果还没结束,用当前时间作为结束时间
                    if current is not None and current.end_time == 0.0:
                        current.end_time = ts
                    # 按 slot 初始化队员+段位映射(任务进行中会实时更新)
                    slot_info: dict[int, tuple[str, str]] = {}
                    for slot, name in pending_squad_by_slot.items():
                        rank = pending_squad_mastery.get(slot, "")
                        slot_info[slot] = (name, rank)
                    current = MissionRecord(
                        node_id=pending_node_id,
                        void_tier=pending_void_tier,
                        mission_type=new_type,
                        start_time=ts,
                        squad_slot_info=slot_info,
                        is_steel_path=pending_steel_path,
                    )
                    cls._fill_node_info(current, node_table)
                    cls._refresh_squad_members(current)
                    missions.append(current)
                    # 节点/纪元/钢铁标记消费后清空;段位保留(同一会话队友段位不变)
                    pending_node_id = ""
                    pending_void_tier = ""
                    pending_steel_path = False
                    pending_squad_by_slot = {}
                    continue

                # ── 3. 回到轨道站(任务结束) ──
                if cls._RE_PLAYER_SHIP.search(msg):
                    if current is not None:
                        current.end_time = ts
                    # 回到轨道站 = 任务彻底结束,清空所有 pending 数据
                    # (新任务会重新触发 AddSquadMember / OnMasteryIconReady)
                    pending_node_id = ""
                    pending_void_tier = ""
                    pending_steel_path = False
                    pending_squad_by_slot = {}
                    pending_squad_mastery = {}
                    continue

                # ── 4. 信用点奖励 ──
                if current is not None:
                    cm = cls._RE_CREDITS.search(msg)
                    if cm:
                        current.credits = int(cm.group(1))
                        continue

                # ── 5. 集团声望 ──
                if current is not None:
                    sx = cls._RE_SYNDICATE.search(msg)
                    if sx:
                        current.syndicate_xp = int(sx.group(1))
                        continue

                # ── 6. 任务结果 ──
                if current is not None:
                    if cls._RE_SUCCESS.search(msg):
                        current.success = True
                        continue
                    if cls._RE_FAILED.search(msg):
                        current.success = False
                        continue

                # ── 7. 组队成员(大厅阶段和任务中都可能出现) ──
                sm2 = cls._RE_SQUAD_MEMBER.search(msg)
                if sm2:
                    # 清理 Warframe 客户端附加的私有区图标字符(如 \ue000)
                    raw_name = sm2.group(1)
                    name = "".join(
                        ch for ch in raw_name
                        if not (0xE000 <= ord(ch) <= 0xF8FF)  # 私有区
                        and ord(ch) >= 0x20                    # 可打印
                    ).strip().rstrip(",")
                    slot = int(sm2.group(2))  # squadCount 即 slot 编号
                    if name:
                        # 网络重连会触发重复的 AddSquadMember,
                        # 若该队员已在队伍中则忽略(不改变其 slot)
                        already_in_squad = name in pending_squad_by_slot.values()
                        if not already_in_squad:
                            pending_squad_by_slot[slot] = name
                        # 任务进行中加入的队员:更新 current 的 slot 映射
                        if current is not None:
                            # 检查是否已在 current 中(同名)
                            in_current = any(
                                n == name for n, _r in current.squad_slot_info.values()
                            )
                            if not in_current:
                                rank = pending_squad_mastery.get(slot, "")
                                current.squad_slot_info[slot] = (name, rank)
                                cls._refresh_squad_members(current)
                    continue

                # ── 8. 玩家倒地 ──
                if current is not None:
                    dm = cls._RE_DOWNED.search(msg)
                    if dm:
                        current.downed_count += 1
                        continue

                # ── 9. 钢铁之路标记 ──
                # 主标记:DHardMissionStartTeshin(Teshin 语音)
                # 辅助标记:SteelPathArcanesBuff(钢铁奥术图标,late join 任务用)
                if current is not None and (
                    cls._RE_STEEL_PATH.search(msg)
                    or cls._RE_STEEL_ARCANE.search(msg)
                ):
                    current.is_steel_path = True
                    continue

        # 收尾:最后一个任务如果没有明确结束时间(日志在任务进行中结束),
        # 用日志最后时间戳作为结束时间,并标记为进行中
        if current is not None and current.end_time == 0.0:
            current.end_time = last_ts
            current.is_ongoing = True

        # 计算时长
        for m in missions:
            if m.end_time > m.start_time:
                m.duration_min = round((m.end_time - m.start_time) / 60.0, 1)

        return missions

    @staticmethod
    def _refresh_squad_members(mission: MissionRecord) -> None:
        """根据 squad_slot_info 重新生成 squad_members 列表(按 slot 排序)。"""
        members: list[str] = []
        for slot in sorted(mission.squad_slot_info.keys()):
            name, rank = mission.squad_slot_info[slot]
            members.append(f"{name}({rank})" if rank else name)
        mission.squad_members = members

    @staticmethod
    def _fill_node_info(mission: MissionRecord, node_table: dict) -> None:
        """根据 node_id 填充节点名/派系/任务类型中文名。

        日志中节点 ID 可能带后缀(SolNode162_Alert / SolNode32_HardDaily /
        SolNode171_ActiveMission),而 solNodes.json 的 key 是纯 SolNode162,
        因此先去掉下划线后缀再查翻译表。
        """
        # 任务类型名
        mission.mission_type_name = _MISSION_MAP.get(mission.mission_type, mission.mission_type)

        # 去掉后缀: SolNode162_Alert → SolNode162
        base_id = mission.node_id.split("_")[0]
        node = node_table.get(base_id, {})
        # 显示名保留后缀信息(便于区分警报/每日)
        suffix = mission.node_id[len(base_id):]  # e.g. "_Alert"
        base_name = node.get("value", base_id)
        mission.node_name = f"{base_name}{suffix}" if suffix else base_name
        enemy = node.get("enemy", "")
        mission.enemy = enemy
        mission.enemy_name = _ENEMY_MAP.get(enemy, enemy)

        # 裂缝纪元
        if mission.void_tier:
            mission.is_void_fissure = True
            mission.void_tier_name = _TIER_MAP.get(mission.void_tier, mission.void_tier)

    # ══════════════════════════════════
    #  结果聚合
    # ══════════════════════════════════

    @classmethod
    def _build_result(
        cls,
        missions: list[MissionRecord],
        log_path: str,
        path: Path,
        parse_seconds: float,
    ) -> LogAnalysisResult:
        """从任务列表聚合出统计与图表数据。"""
        result = LogAnalysisResult(
            missions=missions,
            log_path=log_path,
            log_size_mb=round(path.stat().st_size / 1024 / 1024, 1),
            parse_seconds=parse_seconds,
        )

        if not missions:
            return result

        # 汇总
        result.total_missions = len(missions)
        result.total_duration_min = round(sum(m.duration_min for m in missions), 1)
        result.total_credits = sum(m.credits for m in missions)
        result.total_syndicate_xp = sum(m.syndicate_xp for m in missions)
        result.success_count = sum(1 for m in missions if m.success)
        result.steel_path_count = sum(1 for m in missions if m.is_steel_path)
        result.void_fissure_count = sum(1 for m in missions if m.is_void_fissure)
        result.downed_total = sum(m.downed_count for m in missions)

        # 任务类型分布
        type_dist: dict[str, int] = {}
        for m in missions:
            name = m.mission_type_name or m.mission_type
            type_dist[name] = type_dist.get(name, 0) + 1
        result.mission_type_distribution = type_dist

        # 派系分布
        enemy_dist: dict[str, int] = {}
        for m in missions:
            name = m.enemy_name or m.enemy or "未知"
            enemy_dist[name] = enemy_dist.get(name, 0) + 1
        result.enemy_distribution = enemy_dist

        # 每任务图表数据(用节点短名,截断显示)
        for m in missions:
            short = cls._short_node_name(m)
            if m.credits > 0:
                result.credits_by_mission.append((short, m.credits))
            if m.duration_min > 0:
                result.duration_by_mission.append((short, m.duration_min))
            if m.syndicate_xp > 0:
                result.syndicate_by_mission.append((short, m.syndicate_xp))

        # 玩家倒地次数(按玩家统计)
        downed_dist: dict[str, int] = {}
        for m in missions:
            # 注:日志中 was downed by 只记录了总次数,没区分玩家
            # 这里按"主机(第一个队员)"近似归属,若单人则归到玩家自己
            if m.downed_count > 0:
                owner = m.squad_members[0] if m.squad_members else "玩家"
                downed_dist[owner] = downed_dist.get(owner, 0) + m.downed_count
        result.downed_by_player = downed_dist

        return result

    @staticmethod
    def _short_node_name(m: MissionRecord) -> str:
        """生成节点短名用于图表 X 轴(避免太长)。

        格式: 任务类型名 + 节点编号
        例: 生存#162, 防御#26
        """
        # 取 SolNode 后的数字(去掉 _Alert 等后缀)
        base_id = m.node_id.split("_")[0]
        num = base_id.replace("SolNode", "") if base_id.startswith("SolNode") else base_id
        prefix = m.mission_type_name or m.mission_type
        return f"{prefix}#{num}"

    # ══════════════════════════════════
    #  节点翻译表
    # ══════════════════════════════════

    @classmethod
    def _get_node_table(cls) -> dict[str, dict]:
        """加载节点翻译表(缓存到类级)。"""
        if cls._node_table:
            return cls._node_table
        try:
            node_path = paths.resource_dir() / "worldstate" / "solNodes.json"
            with node_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # solNodes.json 结构: {SolNodeID: {value, enemy, type, ...}}
            cls._node_table = data
        except Exception as e:
            _logger.error("加载节点翻译表失败: %s", e)
            cls._node_table = {}
        return cls._node_table
