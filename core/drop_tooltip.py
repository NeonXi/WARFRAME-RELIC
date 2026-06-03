"""
掉落来源悬浮提示模块 —— 独立功能，方便删除回滚。

从 data/all.json 构建物品→掉落来源的内存索引，
为搜索结果提供鼠标悬停的掉落来源 Tooltip（中文显示）。

用法:
    from core.drop_tooltip import DropSourceIndex

    idx = DropSourceIndex()          # 构建索引（首次约 0.5s）
    sources = idx.query("Soma")      # 查询物品掉落来源
    # → [{"location": "水星 - Apollodorus (生存)", "rarity": "Common", "chance": 50, "rotation": "A"}, ...]
    tooltip_html = idx.format_tooltip(sources)  # 生成 HTML tooltip

集成方式（management_panel.py）:
    - 在 _do_items_search() 中给每个 QListWidgetItem 设置 tooltip
    - 或使用 QEvent.ToolTip + event() 动态生成
"""

import json
import os
import re
from typing import Optional

# ============================================================
# 星球 → 中文（节点保持英文）
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
    "KuvaFortress": "赤毒要塞",
    "Void": "虚空",
    "Deimos": "火卫二",
    "Zariman": "扎里曼号",
    "Cetus": "希图斯",
    "Solaris": "索拉里斯",
    "Cavia": "科维兽",
    "Hex": "六人组",
    "Sanctuary": "圣殿",
    "Derelict": "遗迹",
}

# 任务类型 → 中文
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

# 稀有度中文
RARITY_CN = {
    "Common": "普通",
    "Uncommon": "罕见",
    "Rare": "稀有",
    "Legendary": "传说",
    "Ultra Rare": "超稀有",
}

# 敌人名 → 中文（常用）
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

# 掉落类型中文
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


class DropSourceIndex:
    """物品 → 掉落来源 内存索引。

    一次性加载 all.json 并构建倒排索引，后续查询 O(1)。
    """

    def __init__(self, alljson_path: str = None):
        self._sources: dict[str, list[dict]] = {}  # item_name.lower() → [source, ...]
        self._built = False
        self._alljson_path = alljson_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'data', 'all.json'
        )
        self._zh_en: dict[str, str] = {}  # en_lower → zh 翻译缓存（从 zh_en_dict.json 加载）

    # ---- 构建 ----

    def ensure_built(self):
        """确保索引已构建（幂等）。"""
        if self._built:
            return
        self._build()

    def _build(self):
        """扫描 all.json 构建倒排索引。"""
        if not os.path.exists(self._alljson_path):
            print(f"[DropTooltip] all.json 不存在: {self._alljson_path}")
            self._built = True
            return

        # 加载 zh_en_dict.json 构建 en→zh 反向映射
        self._load_zh_en_dict()

        with open(self._alljson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 遍历每个大类
        for top_key, top_val in data.items():
            if top_key == 'relics':
                self._scan_relics(top_val)
            elif top_key in ('missionRewards',):
                self._scan_mission_rewards(top_key, top_val)
            elif top_key == 'sortieRewards':
                self._scan_flat_list(top_key, top_val)
            elif top_key in ('keyRewards', 'transientRewards'):
                self._scan_keylike_list(top_key, top_val)
            elif top_key in ('cetusBountyRewards', 'solarisBountyRewards',
                             'deimosRewards', 'zarimanRewards', 'entratiLabRewards',
                             'hexRewards'):
                self._scan_bounty_list(top_key, top_val)
            elif top_key == 'blueprintLocations':
                self._scan_blueprint_locations(top_val)
            elif top_key == 'enemyModTables':
                self._scan_enemy_mod_tables(top_val)
            elif top_key == 'enemyBlueprintTables':
                self._scan_enemy_blueprint_tables(top_val)
            elif top_key == 'modLocations':
                self._scan_mod_locations(top_val)
            elif top_key == 'syndicates':
                self._scan_syndicates(top_val)
            elif top_key in ('resourceByAvatar', 'sigilByAvatar',
                             'additionalItemByAvatar'):
                self._scan_avatar_items(top_key, top_val)

        self._built = True
        print(f"[DropTooltip] 索引构建完成: {len(self._sources)} 个物品有掉落来源")

    # ---- 翻译支持 ----

    def _load_zh_en_dict(self):
        """加载 zh_en_dict.json 构建 en→zh 映射。"""
        zh_en_path = os.path.join(
            os.path.dirname(self._alljson_path), 'zh_en_dict.json'
        )
        if not os.path.exists(zh_en_path):
            return
        try:
            with open(zh_en_path, 'r', encoding='utf-8') as f:
                pairs = json.load(f)
            for cn, en in pairs:
                self._zh_en[en.strip().lower()] = cn
            # 也合并项目内建的敌人翻译
            for en, cn in ENEMY_CN.items():
                self._zh_en[en.strip().lower()] = cn
            # 按长度降序排列 key，用于最长匹配
            self._zh_en_keys = sorted(self._zh_en.keys(), key=len, reverse=True)
        except Exception:
            pass

    def _translate_location(self, text: str) -> str:
        """翻译 location 字符串中的英文部分。

        策略：用正则找出所有英文词段，在 en→zh 字典中 O(1) 查找替换。
        按长度降序优先匹配更长的词组。
        """
        if not self._zh_en:
            return text
        # 找出所有连续的英文词段（至少2个字母）
        words = re.findall(r'[a-zA-Z][a-zA-Z\s]{1,}', text)
        if not words:
            return text
        # 按长度降序排列，先匹配长词组
        seen = set()
        replacements = []
        for w in sorted(set(words), key=len, reverse=True):
            if w in seen:
                continue
            en_lower = w.strip().lower()
            zh = self._zh_en.get(en_lower)
            if zh:
                # 标记 w 中所有子词已处理
                seen.add(w)
                replacements.append((w, zh))
        # 按原文位置降序替换（避免索引偏移）
        for en_word, zh_word in sorted(replacements, key=lambda x: len(x[0]), reverse=True):
            text = re.sub(
                r'(?<![a-zA-Z])' + re.escape(en_word) + r'(?![a-zA-Z])',
                zh_word, text, flags=re.IGNORECASE
            )
        return text

    # ---- 各类型扫描 ----

    def _add_source(self, item_name: str, source: dict):
        if not item_name:
            return
        # 翻译 location 中的英文
        if 'location' in source and self._zh_en_keys:
            source['location'] = self._translate_location(source['location'])
        key = item_name.strip().lower()
        if key not in self._sources:
            self._sources[key] = []
        self._sources[key].append(source)

        # 如果物品名带有 (XXX) 后缀（如 "Razorwing Blitz (Titania)"），
        # 同时注册去掉后缀的版本，以便中文翻译匹配
        stripped = re.sub(r'\s*\([^)]*\)\s*$', '', key).strip()
        if stripped and stripped != key:
            if stripped not in self._sources:
                self._sources[stripped] = []
            self._sources[stripped].append(source)

        # 如果物品名以 "blueprint" 结尾，同时注册去掉 "blueprint" 后缀的版本。
        # 原因：all.json 中有 "acceltra blueprint" 但 items_i18n 中只有 "Acceltra"
        # 用户从搜索结果点击 "Acceltra" 时 query("Acceltra") 无法找到掉落来源。
        if key.endswith(' blueprint'):
            base = key[:-len(' blueprint')].strip()
            if base and base != key:
                if base not in self._sources:
                    self._sources[base] = []
                self._sources[base].append(source)

    def _scan_relics(self, relics_list: list):
        """遗物及其部件掉落。"""
        for relic in relics_list:
            relic_name = relic.get('relicName', '')
            tier = relic.get('tier', '')
            state = relic.get('state', '')
            if not relic_name:
                continue
            # 遗物本身
            label = f"{tier} {relic_name} 遗物"
            if state:
                label += f" ({state})"
            for reward in relic.get('rewards', []):
                part = reward.get('itemName', '')
                if part:
                    self._add_source(part, {
                        'location': label,
                        'rarity': reward.get('rarity', ''),
                        'chance': reward.get('chance', 0),
                        'source_type': 'relics',
                    })

    def _scan_mission_rewards(self, source_type: str, mission_dict: dict):
        """任务奖励（missionRewards 结构: {planet: {node: {gameMode, rewards: {rotation: [...]}}}）"""
        for planet, nodes in mission_dict.items():
            if not isinstance(nodes, dict):
                continue
            for node_name, node_data in nodes.items():
                if not isinstance(node_data, dict):
                    continue
                gm = node_data.get('gameMode', '')
                rewards = node_data.get('rewards', {})
                if not isinstance(rewards, dict):
                    continue
                for rotation, items in rewards.items():
                    if not isinstance(items, list):
                        continue
                    planet_cn = PLANET_CN.get(planet, planet)
                    gm_cn = GAMEMODE_CN.get(gm, gm)
                    location = f"{planet_cn} - {node_name} ({gm_cn})"
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        self._add_source(item.get('itemName', ''), {
                            'location': location,
                            'rarity': item.get('rarity', ''),
                            'chance': item.get('chance', 0),
                            'rotation': rotation,
                            'source_type': source_type,
                        })

    def _scan_flat_list(self, source_type: str, item_list: list):
        """平铺物品列表（sortieRewards 等）: [{_id, itemName, rarity, chance}, ...]"""
        for entry in item_list:
            if not isinstance(entry, dict):
                continue
            self._add_source(entry.get('itemName', ''), {
                'location': self._cn_source(source_type),
                'rarity': entry.get('rarity', ''),
                'chance': entry.get('chance', 0),
                'source_type': source_type,
            })

    def _scan_keylike_list(self, source_type: str, item_list: list):
        """钥匙/限时奖励列表: [{_id, keyName/objectiveName, rewards: [...] | {rotation: [...]}}, ...]"""
        for entry in item_list:
            if not isinstance(entry, dict):
                continue
            loc_name = entry.get('keyName', entry.get('objectiveName', source_type))
            rewards = entry.get('rewards', {})
            if isinstance(rewards, list):
                # 扁平 rewards 列表（如 transientRewards）
                for item in rewards:
                    if not isinstance(item, dict):
                        continue
                    self._add_source(item.get('itemName', ''), {
                        'location': f"{loc_name}",
                        'rarity': item.get('rarity', ''),
                        'chance': item.get('chance', 0),
                        'source_type': source_type,
                    })
            elif isinstance(rewards, dict):
                # rewards 按轮次分组（如 keyRewards）
                for rotation, items in rewards.items():
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        self._add_source(item.get('itemName', ''), {
                            'location': f"{loc_name}",
                            'rarity': item.get('rarity', ''),
                            'chance': item.get('chance', 0),
                            'rotation': rotation,
                            'source_type': source_type,
                        })

    def _scan_bounty_list(self, source_type: str, item_list: list):
        """赏金任务列表: [{_id, bountyLevel, rewards: {rotation: [...]}}, ...]"""
        for entry in item_list:
            if not isinstance(entry, dict):
                continue
            loc_name = f"{self._cn_source(source_type)} Lv{entry.get('bountyLevel', '?')}"
            rewards = entry.get('rewards', {})
            if not isinstance(rewards, dict):
                continue
            for rotation, items in rewards.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    self._add_source(item.get('itemName', ''), {
                        'location': loc_name,
                        'rarity': item.get('rarity', ''),
                        'chance': item.get('chance', 0),
                        'rotation': rotation,
                        'source_type': source_type,
                    })

    def _scan_blueprint_locations(self, bp_list: list):
        """蓝图掉落（敌人掉落蓝图）。"""
        for bp in bp_list:
            if not isinstance(bp, dict):
                continue
            bp_name = bp.get('blueprintName', bp.get('itemName', ''))
            for enemy in bp.get('enemies', []):
                if not isinstance(enemy, dict):
                    continue
                enemy_name = enemy.get('enemyName', '')
                enemy_cn = ENEMY_CN.get(enemy_name, enemy_name)
                drop_chance = enemy.get('enemyBlueprintDropChance',
                                        enemy.get('enemyItemDropChance', ''))
                chance = enemy.get('chance', 0)
                location = f"敌人: {enemy_cn}"
                extra = []
                if drop_chance:
                    extra.append(f"掉落概率 {drop_chance}%")
                if extra:
                    location += f" ({', '.join(extra)})"
                self._add_source(bp_name, {
                    'location': location,
                    'rarity': enemy.get('rarity', ''),
                    'chance': chance,
                    'source_type': 'blueprintLocations',
                })

    def _scan_enemy_mod_tables(self, mod_list: list):
        """敌人 Mod 掉落表。"""
        for entry in mod_list:
            if not isinstance(entry, dict):
                continue
            enemy_name = entry.get('enemyName', '')
            enemy_cn = ENEMY_CN.get(enemy_name, enemy_name)
            drop_chance = entry.get('enemyModDropChance', entry.get('ememyModDropChance', ''))
            for mod in entry.get('mods', []):
                if not isinstance(mod, dict):
                    continue
                location = f"敌人: {enemy_cn}"
                if drop_chance:
                    location += f" (Mod掉落率 {drop_chance}%)"
                self._add_source(mod.get('modName', ''), {
                    'location': location,
                    'rarity': mod.get('rarity', ''),
                    'chance': mod.get('chance', 0),
                    'source_type': 'enemyModTables',
                })

    def _scan_enemy_blueprint_tables(self, bp_list: list):
        """敌人蓝图掉落表（结构同 blueprintLocations）。"""
        self._scan_blueprint_locations(bp_list)

    def _scan_mod_locations(self, mod_list: list):
        """Mod 来源。"""
        for mod in mod_list:
            if not isinstance(mod, dict):
                continue
            mod_name = mod.get('modName', mod.get('itemName', ''))
            for enemy in mod.get('enemies', []):
                if not isinstance(enemy, dict):
                    continue
                enemy_name = enemy.get('enemyName', '')
                enemy_cn = ENEMY_CN.get(enemy_name, enemy_name)
                chance = enemy.get('chance', 0)
                drop_chance = enemy.get('enemyModDropChance', '')
                location = f"敌人: {enemy_cn}"
                if drop_chance:
                    location += f" (Mod掉落率 {drop_chance}%)"
                self._add_source(mod_name, {
                    'location': location,
                    'rarity': enemy.get('rarity', ''),
                    'chance': chance,
                    'source_type': 'modLocations',
                })

    def _scan_syndicates(self, syndicates_dict: dict):
        """集团购买/兑换: {faction: [{item, place, standing, rarity, chance}, ...]}"""
        for faction, items in syndicates_dict.items():
            if not isinstance(items, list):
                continue
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                item_name = entry.get('item', '')
                place = entry.get('place', faction)
                standing = entry.get('standing', 0)
                location = f"购买: {place}"
                if standing:
                    location += f" ({standing} 声望)"
                self._add_source(item_name, {
                    'location': location,
                    'rarity': entry.get('rarity', ''),
                    'chance': entry.get('chance', 100),
                    'source_type': 'syndicates',
                })

    def _scan_avatar_items(self, source_type: str, avatar_list: list):
        """头像/资源掉落: [{source, items: [{item, rarity, chance}]}, ...]"""
        for entry in avatar_list:
            if not isinstance(entry, dict):
                continue
            source = entry.get('source', '')
            for item in entry.get('items', []):
                if not isinstance(item, dict):
                    continue
                item_name = item.get('item', '')
                self._add_source(item_name, {
                    'location': f"{source}",
                    'rarity': item.get('rarity', ''),
                    'chance': item.get('chance', 0),
                    'source_type': source_type,
                })

    def _scan_generic(self, source_type: str, data_obj):
        """通用扫描：深度搜索 rewards 数组。"""
        def deep_collect(obj, context=""):
            if isinstance(obj, dict):
                loc = obj.get('nodeName', obj.get('location', context))
                if 'rewards' in obj and isinstance(obj['rewards'], list):
                    for reward in obj['rewards']:
                        if isinstance(reward, dict):
                            self._add_source(reward.get('itemName', ''), {
                                'location': loc or source_type,
                                'rarity': reward.get('rarity', ''),
                                'chance': reward.get('chance', 0),
                                'source_type': source_type,
                            })
                for val in obj.values():
                    deep_collect(val, loc)
            elif isinstance(obj, list):
                for val in obj:
                    deep_collect(val, context)
        deep_collect(data_obj)

    # ---- 查询 ----

    def query(self, item_name: str, max_sources: int = 20) -> list[dict]:
        """查询物品的掉落来源。

        Args:
            item_name: 物品名（英文或中文）
            max_sources: 最多返回多少条

        Returns:
            [{location, rarity, chance, rotation?, source_type}, ...]
            按 chance 降序排列
        """
        self.ensure_built()

        if not item_name:
            return []

        # 尝试直接匹配
        key = item_name.strip().lower()
        results = self._sources.get(key, [])

        if not results:
            return []

        # 去重（相同 location 保留最高 chance）
        deduped = {}
        for r in results:
            loc_key = (r.get('location', ''), r.get('rotation', ''), r.get('rarity', ''))
            if loc_key not in deduped or r.get('chance', 0) > deduped[loc_key].get('chance', 0):
                deduped[loc_key] = r

        sorted_results = sorted(deduped.values(), key=lambda x: x.get('chance', 0), reverse=True)
        return sorted_results[:max_sources]

    # ---- 格式化 ----

    @staticmethod
    def _cn(rarity: str) -> str:
        return RARITY_CN.get(rarity, rarity)

    @staticmethod
    def _cn_source(src_type: str) -> str:
        return SOURCE_TYPE_CN.get(src_type, src_type)

    def format_tooltip(self, sources: list[dict], item_name: str = "") -> str:
        """将掉落来源格式化为 HTML tooltip，赛博朋克深色风格。

        Returns:
            适合 QToolTip.showText() 使用的 HTML 字符串
        """
        if not sources:
            return (
                f"<div style='padding:8px;'>"
                f"<b style='color:#00FFFF;'>{self._escape_html(item_name)}</b><br>"
                f"<span style='color:#6677AA; font-size:11px;'>暂无掉落来源数据</span></div>"
            )

        # 按 source_type 分组
        by_type: dict[str, list] = {}
        for s in sources:
            st = s.get('source_type', '')
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(s)

        # 分类颜色映射
        type_colors = {
            'relics':      '#FFD700',
            'missionRewards': '#00FFFF',
            'bountyRewards': '#FF7700',
            'cetusBountyRewards': '#FF7700',
            'solarisBountyRewards': '#FF7700',
            'deimosRewards': '#FF7700',
            'zarimanRewards': '#FF7700',
            'entratiLabRewards': '#FF7700',
            'hexRewards': '#FF7700',
            'sortieRewards': '#FF0055',
            'keyRewards': '#00FF99',
            'transientRewards': '#E066FF',
            'blueprintLocations': '#00FFFF',
            'enemyModTables': '#FF6B6B',
            'enemyBlueprintTables': '#FF6B6B',
            'modLocations': '#FF6B6B',
            'syndicates': '#FFE600',
            'resourceByAvatar': '#8E9CB2',
            'sigilByAvatar': '#8E9CB2',
            'additionalItemByAvatar': '#8E9CB2',
        }

        parts = []
        # ---- 头部：物品名 ----
        parts.append(
            f"<div style='background:#0E0E24; padding:8px 12px; "
            f"border-bottom:1px solid #1a1a3a;'>"
            f"<span style='color:#00FFFF; font-size:14px; font-weight:bold;'>"
            f"{self._escape_html(item_name)}</span>"
            f"<span style='color:#6677AA; font-size:10px; margin-left:8px;'>"
            f"掉落来源 ({sum(len(v) for v in by_type.values())} 条)</span>"
            f"</div>"
        )

        # ---- 内容区 ----
        parts.append(
            f"<div style='padding:6px 12px 8px 12px;'>"
        )

        for st, items in by_type.items():
            cn_st = self._cn_source(st)
            accent = type_colors.get(st, '#6677AA')

            # 分类标题行
            parts.append(
                f"<div style='margin-top:6px; margin-bottom:2px;'>"
                f"<span style='display:inline-block; width:3px; height:12px; "
                f"background:{accent}; border-radius:2px; margin-right:6px; "
                f"vertical-align:middle;'></span>"
                f"<span style='color:{accent}; font-size:12px; font-weight:bold; "
                f"vertical-align:middle;'>{self._escape_html(cn_st)}</span>"
                f"<span style='color:#6677AA; font-size:10px; margin-left:4px; "
                f"vertical-align:middle;'>({len(items)})</span>"
                f"</div>"
            )

            for item in items[:8]:
                loc = item.get('location', '?')
                rarity = item.get('rarity', '')
                chance = item.get('chance', 0)
                rotation = item.get('rotation', '')

                # 概率格式化
                if chance > 0 and chance < 100:
                    chance_str = f"{chance:.1f}%"
                elif chance >= 100:
                    chance_str = "必定"
                else:
                    chance_str = ""

                # 轮次标签
                rot_tag = ""
                if rotation:
                    rot_tag = (
                        f"<span style='display:inline-block; background:#1a1a3a; "
                        f"color:#8E9CB2; font-size:10px; padding:1px 5px; "
                        f"border-radius:3px; margin-left:4px;'>轮次{rotation}</span>"
                    )

                # 行：地点 | 概率 | 轮次
                parts.append(
                    f"<div style='padding:2px 0 2px 12px; font-size:12px; "
                    f"white-space:nowrap;'>"
                    f"<span style='color:#C8D0E0;'>{self._escape_html(loc)}</span>"
                    f"<span style='color:#8E9CB2; margin-left:8px;'>"
                    f"{chance_str}"
                    f"</span>"
                    f"{rot_tag}"
                    f"</div>"
                )

        # 底部数据来源
        parts.append(
            f"</div>"
            f"<div style='background:#0E0E24; padding:4px 12px; "
            f"border-top:1px solid #1a1a3a;'>"
            f"<span style='color:#444466; font-size:10px;'>"
            f"数据来源: WFCD warframe-drop-data</span></div>"
        )

        return "".join(parts)

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


# ============================================================
# 全局单例（懒加载）
# ============================================================
_index: Optional[DropSourceIndex] = None


def get_index() -> DropSourceIndex:
    """获取全局掉落来源索引（懒加载单例）。"""
    global _index
    if _index is None:
        _index = DropSourceIndex()
    return _index


# ============================================================
# 测试入口
# ============================================================
if __name__ == '__main__':
    import sys

    idx = DropSourceIndex()
    idx.ensure_built()

    tests = ["Soma", "Frost Prime Blueprint", "Steel Fiber", "Serration", "Parry"]
    for name in tests:
        sources = idx.query(name, max_sources=10)
        print(f"\n{'='*60}")
        print(idx.format_tooltip(sources, name))
        if not sources:
            print("  (无掉落数据)")
