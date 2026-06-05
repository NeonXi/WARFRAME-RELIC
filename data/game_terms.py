"""
游戏术语中英翻译映射表（共享模块）。

所有星球名、任务模式、稀有度、敌人名、掉落类型等术语的中英对照，
统一在此维护，供 drop_tooltip、items_i18n 等模块共用。
"""

# ============================================================
# 星球 / 天体 → 中文
# ============================================================
PLANET_CN = {
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
    "Veil Proxima": "面纱比邻星",
    "Earth Proxima": "地球比邻星",
    "Saturn Proxima": "土星比邻星",
    "Venus Proxima": "金星比邻星",
    "Neptune Proxima": "海王星比邻星",
    "Pluto Proxima": "冥王星比邻星",
}

# ============================================================
# 任务类型 → 中文
# ============================================================
GAMEMODE_CN = {
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
}

# ============================================================
# 稀有度 → 中文
# ============================================================
RARITY_CN = {
    "Common": "普通",
    "Uncommon": "罕见",
    "Rare": "稀有",
    "Legendary": "传说",
    "Ultra Rare": "超稀有",
}

# ============================================================
# 敌人名 → 中文（常用）
# ============================================================
ENEMY_CN = {
    "Vorac Crewship": "沃拉克战舰",
    "Scaldra Screamer": "Scaldra 尖啸者",
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
    "Narmer Enemy": "合一众敌人",
    "Murmur Enemy": "低语者敌人",
    "Scaldra Enemy": "Scaldra 敌人",
    "Techrot Enemy": "科技腐化敌人",
}

# ============================================================
# 掉落来源类型 → 中文
# ============================================================
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

# ============================================================
# 赏金/特殊来源完整名称 → 中文
# ============================================================
BOUNTY_CN = {
    "Cetus Bounty": "希图斯赏金",
    "Fortuna Bounty": "福尔图娜赏金",
    "Cambion Drift Bounty": "魔胎之境赏金",
    "Zariman Bounty": "扎里曼赏金",
    "Entrati Lab Bounty": "英择谛实验室赏金",
    "Höllvania Bounty": "霍瓦尼亚赏金",
    "Sortie": "突击",
    "Transient Reward": "临时奖励",
    "Void Key": "虚空钥匙",
}


# ============================================================
# 工具函数
# ============================================================

def translate_location(en_text: str) -> str:
    """将英文地点/来源名翻译为中文。

    处理格式如 "Void/Hepit" → "虚空/Hepit"
    "Void/Hepit (Survival)" → "虚空/Hepit (生存)"
    """
    if not en_text:
        return en_text

    result = en_text

    # 1. 翻译赏金/特殊来源名（完整匹配）
    for en, zh in BOUNTY_CN.items():
        if en in result:
            result = result.replace(en, zh)

    # 2. 翻译星球名
    for en, zh in PLANET_CN.items():
        if en in result:
            result = result.replace(en, zh)

    # 3. 翻译任务模式
    for en, zh in GAMEMODE_CN.items():
        if en in result:
            result = result.replace(en, zh)

    return result