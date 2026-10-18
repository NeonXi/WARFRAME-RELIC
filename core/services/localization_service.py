"""
[L-Service] LocalizationService — 游戏术语中英翻译服务。

依赖: Python 标准库 + sqlite3（warframe.db）
禁止: PySide6 / QtWidgets / QtGui
返回: dict / str（原始数据类型）

所有星球名、任务模式、稀有度、敌人名、掉落类型等术语的中英对照，
主数据源为 warframe.db 中的 game_translations 表，硬编码值仅作回退。
首次调用 translate_location() 时懒加载 DB 数据。

## AI 硬约束 — 修改本文件前必读
归属层:    [L-Service] (core/services/)
允许依赖:  Python 标准库 + data/* + core.hotkey_config 等纯模块
禁止依赖:  PySide6 / QtWidgets / QtGui / QtCore(Signal 除外)
           core.widgets/* / core.pages/* / core.recognizers/*
必读规范:  .trae/rules/开发规范.md §6.2

本文件相关红线:
- 禁止 import PySide6 → Service 是纯逻辑,不能碰 UI
- 禁止返回 Qt 对象 → 只能返回 dict / list / str / int / bool
- 禁止在 Service 中发信号调用 widget → 状态走 core.state / EventBus
- 禁止未捕获的 IO/网络异常冒泡 → 必须 try/except 降级
- 禁止在 Service 中持有 widget 引用

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.2。
"""

from __future__ import annotations

import logging
import re as _re
import sqlite3 as _sqlite3

logger = logging.getLogger(__name__)

# ============================================================
# 1. 硬编码字典（仅在 DB 中没有对应翻译时作为回退）
# ============================================================

_PLANET_HARDCODED = {
    "Mercury": "水星",
    "Venus": "金星",
    "Earth": "地球",
    "Mars": "火星",
    "Jupiter": "木星",
    "Saturn": "土星",
    "Uranus": "天王星",
    "Neptune": "海王星",
    "Pluto": "冥王星",
    "Eris": "阋神星",
    "Sedna": "赛德娜",
    "Lua": "月球",
    "Ceres": "谷神星",
    "Europa": "木卫二",
    "Phobos": "火卫一",
    "KuvaFortress": "赤毒要塞",
    "Kuva Fortress": "赤毒要塞",
    "Void": "虚空",
    "Deimos": "火卫二",
    "Zariman": "扎里曼号",
    "Cetus": "希图斯",
    "Solaris": "索拉里斯",
    "Cavia": "科维兽",
    "Hex": "六人组",
    "Sanctuary": "圣殿",
    "Derelict": "遗迹",
    "Duviri": "双衍王境",
    "Höllvania": "霍瓦尼亚",
    "Veil": "面纱",
    "Veil Proxima": "面纱比邻星",
    "Earth Proxima": "地球比邻星",
    "Saturn Proxima": "土星比邻星",
    "Venus Proxima": "金星比邻星",
    "Neptune Proxima": "海王星比邻星",
    "Pluto Proxima": "冥王星比邻星",
}

_GAMEMODE_HARDCODED = {
    "Survival": "生存",
    "Defense": "防御",
    "Excavation": "挖掘",
    "Capture": "捕获",
    "Exterminate": "歼灭",
    "Rescue": "救援",
    "Spy": "间谍",
    "Sabotage": "破坏",
    "Assassination": "刺杀",
    "Interception": "拦截",
    "Hijack": "劫持",
    "Infested Salvage": "感染者回收",
    "Defection": "叛逃",
    "Arena": "竞技场",
    "Disruption": "中断",
    "Orphix": "殁世机甲",
    "Void Flood": "虚空洪流",
    "Void Cascade": "虚空瀑布",
    "Void Armageddon": "虚空末日",
    "Free Roam": "自由漫游",
    "Skirmish": "前哨战",
    "Pursuit": "追击",
    "Mobile Defense": "移动防御",
    "Assault": "强袭",
    "Volatile": "爆发",
    "Mirror Defense": "镜像防御",
    "Alchemy": "炼金",
    "Netracells": "虚空锐将",
    "Void Storm": "虚空风暴",
    "Rush": "竞速",
    "Archwing": "Archwing",
    "Conclave": "武形秘仪",
    "Ascension": "升天",
    "Follie's Hunt": "Follie 的狩猎",
    "Legacyte Harvest": "Legacyte 收获",
    "Sanctuary Onslaught": "圣殿突袭",
    "Shrine Defense": "神殿防御",
    "The Circuit": "无尽回廊",
    "The Perita Rebellion": "Perita 叛乱",
    "Hard": "困难",
    "Normal": "普通",
}

_ENEMY_HARDCODED = {
    "Scaldra Screamer": "炽蛇军尖啸者",
    "Scaldra Dedicant": "炽蛇军献身者",
    "Scaldra Barbican": "炽蛇军守卫者",
    "Scaldra Harbinger": "炽蛇军前哨气球",
    "Scaldra Eradicator": "炽蛇军根除者",
    "Scaldra": "炽蛇军",
    "H-09 Efervon Tank": "H-09 艾弗旺坦克",
    "H-09 Apex": "H-09 王者",
    "Scaldra Enemy": "炽蛇军敌人",
    "Techrot": "科腐者",
    "Techrot Enemy": "科腐者敌人",
    "Grineer Lancer": "Grineer 枪兵",
    "Grineer Trooper": "Grineer 骑兵",
    "Grineer Butcher": "Grineer 屠夫",
    "Grineer Scorch": "Grineer 灼烧者",
    "Grineer Bombard": "Grineer 轰击者",
    "Grineer Heavy Gunner": "Grineer 重型机枪手",
    "Grineer Napalm": "Grineer 凝固汽油弹手",
    "Corpus Crewman": "Corpus 船员",
    "Corpus Prod Crewman": "Corpus 电击船员",
    "Corpus Sniper Crewman": "Corpus 狙击船员",
    "Corpus Tech": "Corpus 技师",
    "Corpus Nullifier": "Corpus 虚能船员",
    "Infested Runner": "Infested 奔跑者",
    "Infested Charger": "Infested 冲刺者",
    "Infested Leaper": "Infested 跳跃者",
    "Infested Ancient": "Infested 远古者",
    "Infested Ancient Healer": "Infested 远古治愈者",
    "Infested Ancient Disruptor": "Infested 远古干扰者",
    "Infested Toxic Ancient": "Infested 远古剧毒者",
    "Orokin Drone": "Orokin 无人机",
    "Orokin Specter": "Orokin 魅影",
    "Sentient Battalyst": "Sentient 战斗使",
    "Sentient Conculyst": "Sentient 震荡使",
    "Corrupted Lancer": "堕落枪兵",
    "Corrupted Heavy Gunner": "堕落重型机枪手",
    "Corrupted Bombard": "堕落轰击者",
    "Corrupted Nullifier": "堕落虚能者",
    "Corrupted Ancient": "堕落远古者",
    "Corrupted Crewman": "堕落船员",
    "Vorac Crewship": "沃拉克战舰",
    "Narmer Enemy": "合一众敌人",
    "Murmur Enemy": "低语者敌人",
}

_BOUNTY_HARDCODED = {
    "Cetus Bounty": "希图斯赏金",
    "Fortuna Bounty": "福尔图娜赏金",
    "Cambion Drift Bounty": "魔胎之境赏金",
    "Zariman Bounty": "扎里曼赏金",
    "Entrati Lab Bounty": "英择谛实验室赏金",
    "Höllvania Bounty": "霍瓦尼亚赏金",
    "Antivirus Bounty": "杀毒赏金",
    "Sortie": "突击",
    "Transient Reward": "临时奖励",
    "Void Key": "虚空钥匙",
}

_SUBLOCATION_HARDCODED = {
    "Caches": "储藏箱",
    "Arcana Isolation Vault": "奥术隔离库",
    "Isolation Vault": "隔离库",
    "Rotation": "轮次",
    "Rotation A": "轮次 A",
    "Rotation B": "轮次 B",
    "Rotation C": "轮次 C",
    "Rotation D": "轮次 D",
}

# ============================================================
# 2. 懒加载：首次调用时从 warframe.db 加载 EN→ZH 翻译
# ============================================================
# 数据库路径(打包/开发环境自适应,见 core.paths;首启自动复制随包初始库)
from core.paths import ensure_user_file as _ensure_db_file
_DB_PATH = _ensure_db_file("warframe.db")
_DB_LOCALE: dict[str, str] | None = None   # None = 未加载


def _get_locale() -> dict[str, str]:
    """获取翻译字典（懒加载单例）。"""
    global _DB_LOCALE
    if _DB_LOCALE is not None:
        return _DB_LOCALE

    locale: dict[str, str] = {}
    if not _DB_PATH.exists():
        logger.warning("翻译数据库不存在: %s", _DB_PATH)
        _DB_LOCALE = locale
        return locale

    try:
        conn = _sqlite3.connect(str(_DB_PATH))
        conn.row_factory = _sqlite3.Row

        # 1) 优先加载物品表的中文名（避免 "Seeker" 被翻成 "探求者" 而非 "弹头导引"）
        for row in conn.execute(
            "SELECT DISTINCT name, zh_name FROM items "
            "WHERE name != '' AND zh_name != '' AND name != zh_name"
        ):
            en_key = row["name"].strip()
            zh_val = row["zh_name"].strip()
            if en_key and zh_val and en_key.lower() != zh_val.lower() and len(en_key) > 1:
                locale[en_key] = zh_val

        # 2) 加载 game_translations（不覆盖已有条目）
        for row in conn.execute(
            "SELECT DISTINCT en, zh FROM game_translations "
            "WHERE en != '' AND zh != '' AND en != zh "
            "AND length(en) < 120 AND length(zh) < 200"
        ):
            en_key = row["en"].strip()
            zh_val = row["zh"].strip()
            if (not en_key or not zh_val
                    or en_key.lower() == zh_val.lower()
                    or len(en_key) <= 1
                    or en_key.isdigit()):
                continue
            if en_key not in locale:
                locale[en_key] = zh_val
        conn.close()
        logger.info("翻译缓存已加载: %d 条 EN→ZH 映射", len(locale))
    except Exception:
        logger.exception("加载翻译数据库失败")
        locale = {}

    # 合并硬编码回退（仅 DB 中没有的词条）
    _ALL_HARDCODED = [
        _PLANET_HARDCODED, _GAMEMODE_HARDCODED,
        _ENEMY_HARDCODED, _BOUNTY_HARDCODED,
        _SUBLOCATION_HARDCODED,
    ]
    for _d in _ALL_HARDCODED:
        for _k, _v in _d.items():
            if _k not in locale:
                locale[_k] = _v

    _DB_LOCALE = locale
    return locale


# ============================================================
# 3. 对外暴露的字典（DB 优先，硬编码回退）
# ============================================================

def _get_dict(hardcoded: dict[str, str]) -> dict[str, str]:
    """构建对外字典：DB 值优先，hardcoded 回退。"""
    locale = _get_locale()
    return {k: locale.get(k, v) for k, v in hardcoded.items()}


PLANET_CN: dict[str, str] = {}       # 延迟初始化（首次访问时填充）
GAMEMODE_CN: dict[str, str] = {}     # 同上
ENEMY_CN: dict[str, str] = {}        # 同上
BOUNTY_CN:dict[str, str] = {}        # 同上


def _init_dicts() -> None:
    """延迟初始化公开字典。"""
    global PLANET_CN, GAMEMODE_CN, ENEMY_CN, BOUNTY_CN
    if PLANET_CN:  # 已初始化
        return
    PLANET_CN = _get_dict(_PLANET_HARDCODED)
    GAMEMODE_CN = _get_dict(_GAMEMODE_HARDCODED)
    ENEMY_CN = _get_dict(_ENEMY_HARDCODED)
    BOUNTY_CN = _get_dict(_BOUNTY_HARDCODED)


RARITY_CN = {
    "Common": "普通",
    "Uncommon": "罕见",
    "Rare": "稀有",
    "Legendary": "传说",
    "Ultra Rare": "超稀有",
}

SOURCE_TYPE_CN = {
    "missionRewards": "任务奖励",
    "bountyRewards": "赏金任务",
    "sortieRewards": "突击奖励",
    "keyRewards": "钥匙奖励",
    "transientRewards": "限时奖励",
    "blueprintLocations": "蓝图掉落",
    "enemyModTables": "敌人掉落",
    "enemyBlueprintTables": "敌人蓝图掉落",
    "modLocations": "Mod 掉落",
    "cetusBountyRewards": "希图斯赏金",
    "solarisBountyRewards": "索拉里斯赏金",
    "deimosRewards": "火卫二奖励",
    "zarimanRewards": "扎里曼奖励",
    "entratiLabRewards": "英择谛实验室奖励",
    "hexRewards": "六人组奖励",
    "syndicates": "集团兑换",
    "resourceByAvatar": "资源",
    "sigilByAvatar": "纹章",
    "additionalItemByAvatar": "附加物品",
    "relics": "遗物",
}


def translate_location(en_text: str) -> str:
    """将英文地点/来源名翻译为中文。

    主数据源为数据库 game_translations 表，硬编码值作回退。
    """
    if not en_text:
        return en_text

    # 触发字典初始化
    _init_dicts()

    locale = _get_locale()
    result = en_text

    words = _re.findall(r"[\w\'\-]+", result)
    if not words:
        return result

    candidates: list[str] = []
    for i in range(len(words)):
        for j in range(i + 1, min(i + 6, len(words) + 1)):
            candidates.append(" ".join(words[i:j]))

    candidates.sort(key=len, reverse=True)

    for phrase in candidates:
        zh = locale.get(phrase)
        if zh and phrase in result:
            result = result.replace(phrase, zh)

    return result