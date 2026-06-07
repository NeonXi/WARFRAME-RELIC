"""
掉落来源悬浮提示模块 —— 独立功能，方便删除回滚。

从 warframe.db 统一数据库构建物品→掉落来源的内存索引，
为搜索结果提供鼠标悬停的掉落来源 Tooltip（中文显示）。

用法:
    from core.drop_tooltip import get_index

    idx = get_index()                # 获取全局索引（懒加载）
    sources = idx.query("Soma")      # 查询物品掉落来源
    tooltip_html = idx.format_tooltip(sources, "Soma")
"""

import os
import re
import sqlite3
from typing import Optional

from data.game_terms import (
    PLANET_CN, GAMEMODE_CN, RARITY_CN, ENEMY_CN, SOURCE_TYPE_CN
)
from core.theme_proxy import (
    CYBER_CYAN, CYBER_ORANGE, CYBER_RED, CYBER_GREEN, CYBER_YELLOW,
    CYBER_CARD_BG, CYBER_TEXT_DIM, COLOR_GOLD, COLOR_ENEMY, COLOR_PURPLE,
    MUTED_TEXT, SUBTLE_BORDER, LIGHT_TEXT,
)


class DropSourceIndex:
    """物品 → 掉落来源 内存索引。

    从 warframe.db 一次性加载所有掉落表并构建倒排索引，后续查询 O(1)。
    """

    def __init__(self, db_path: str = None):
        self._sources: dict[str, list[dict]] = {}  # item_name.lower() → [source, ...]
        self._built = False
        self._db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'data', 'warframe.db'
        )

    # ---- 构建 ----

    def ensure_built(self):
        """确保索引已构建（幂等）。"""
        if self._built:
            return
        self._build()

    def _build(self):
        """从 warframe.db 构建倒排索引。"""
        if not os.path.exists(self._db_path):
            print(f"[DropTooltip] warframe.db 不存在: {self._db_path}")
            self._built = True
            return

        try:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
        except Exception as e:
            print(f"[DropTooltip] 数据库打开失败: {e}")
            self._built = True
            return

        # ── 1. 遗物奖励 ──
        self._load_relic_rewards(conn)

        # ── 2. 任务奖励 ──
        self._load_mission_rewards(conn)

        # ── 3. 突击奖励 ──
        self._load_sortie_rewards(conn)

        # ── 4. 赏金奖励 ──
        self._load_bounty_rewards(conn)

        # ── 5. 临时/钥匙奖励 ──
        self._load_transient_rewards(conn)
        self._load_key_rewards(conn)

        # ── 6. Mod 掉落 ──
        self._load_mod_drops(conn)
        self._load_enemy_mod_tables(conn)

        # ── 7. 蓝图掉落 ──
        self._load_blueprint_drops(conn)
        self._load_enemy_bp_tables(conn)

        # ── 8. 集团奖励 ──
        self._load_syndicate_rewards(conn)

        # ── 9. 物品掉落（item_drops，All.json 原始 drops） ──
        self._load_item_drops(conn)

        conn.close()
        self._built = True
        print(f"[DropTooltip] 索引构建完成: {len(self._sources)} 个物品有掉落来源")

    # ---- 内部：添加来源 ----

    def _add_source(self, item_name: str, source: dict):
        if not item_name:
            return
        key = item_name.strip().lower()
        if key not in self._sources:
            self._sources[key] = []
        self._sources[key].append(source)

        # 去掉 (XXX) 后缀注册别名
        stripped = re.sub(r'\s*\([^)]*\)\s*$', '', key).strip()
        if stripped and stripped != key:
            if stripped not in self._sources:
                self._sources[stripped] = []
            self._sources[stripped].append(source)

        # "xxx blueprint" → 同时注册 "xxx"
        if key.endswith(' blueprint'):
            base = key[:-len(' blueprint')].strip()
            if base and base != key:
                if base not in self._sources:
                    self._sources[base] = []
                self._sources[base].append(source)

    # ---- 各表加载 ----

    def _load_relic_rewards(self, conn):
        """遗物奖励: relics + relic_rewards"""
        try:
            rows = conn.execute("""
                SELECT r.tier, r.relic_name, r.state, rr.item_name, rr.rarity, rr.chance
                FROM relic_rewards rr
                JOIN relics r ON rr.relic_id = r.id
            """).fetchall()
            for row in rows:
                tier = row['tier'] or ''
                name = row['relic_name'] or ''
                state = row['state'] or ''
                label = f"{tier} {name} 遗物"
                if state:
                    label += f" ({state})"
                self._add_source(row['item_name'], {
                    'location': label,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'source_type': 'relics',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载遗物奖励失败: {e}")

    def _load_mission_rewards(self, conn):
        """任务奖励: planets + mission_nodes + mission_rewards"""
        try:
            rows = conn.execute("""
                SELECT p.name AS planet, mn.node_name, mn.game_mode,
                       mr.item_name, mr.rarity, mr.chance, mr.rotation
                FROM mission_rewards mr
                JOIN mission_nodes mn ON mr.node_id = mn.id
                JOIN planets p ON mn.planet_id = p.id
            """).fetchall()
            for row in rows:
                planet_cn = PLANET_CN.get(row['planet'], row['planet'] or '')
                gm_cn = GAMEMODE_CN.get(row['game_mode'], row['game_mode'] or '')
                location = f"{planet_cn} - {row['node_name']} ({gm_cn})"
                self._add_source(row['item_name'], {
                    'location': location,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'rotation': row['rotation'] or '',
                    'source_type': 'missionRewards',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载任务奖励失败: {e}")

    def _load_sortie_rewards(self, conn):
        """突击奖励"""
        try:
            rows = conn.execute("""
                SELECT item_name, rarity, chance FROM sortie_rewards
            """).fetchall()
            cn_src = SOURCE_TYPE_CN.get('sortieRewards', '突击奖励')
            for row in rows:
                self._add_source(row['item_name'], {
                    'location': cn_src,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'source_type': 'sortieRewards',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载突击奖励失败: {e}")

    def _load_bounty_rewards(self, conn):
        """赏金奖励"""
        try:
            rows = conn.execute("""
                SELECT source, bounty_level, item_name, rarity, chance, rotation
                FROM bounty_rewards
            """).fetchall()
            for row in rows:
                source_cn = SOURCE_TYPE_CN.get(row['source'], row['source'] or '')
                level = row['bounty_level'] or '?'
                location = f"{source_cn} Lv{level}"
                self._add_source(row['item_name'], {
                    'location': location,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'rotation': row['rotation'] or '',
                    'source_type': row['source'] or 'bountyRewards',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载赏金奖励失败: {e}")

    def _load_transient_rewards(self, conn):
        """临时奖励"""
        try:
            rows = conn.execute("""
                SELECT objective_name, item_name, rarity, chance, rotation
                FROM transient_rewards
            """).fetchall()
            for row in rows:
                self._add_source(row['item_name'], {
                    'location': row['objective_name'] or '',
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'rotation': row['rotation'] or '',
                    'source_type': 'transientRewards',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载临时奖励失败: {e}")

    def _load_key_rewards(self, conn):
        """钥匙奖励"""
        try:
            rows = conn.execute("""
                SELECT key_name, item_name, rarity, chance, rotation
                FROM key_rewards
            """).fetchall()
            for row in rows:
                self._add_source(row['item_name'], {
                    'location': row['key_name'] or '',
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'rotation': row['rotation'] or '',
                    'source_type': 'keyRewards',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载钥匙奖励失败: {e}")

    def _load_mod_drops(self, conn):
        """Mod 掉落（modLocations 视角）"""
        try:
            rows = conn.execute("""
                SELECT mod_name, enemy_name, rarity, chance, enemy_mod_drop_chance
                FROM mod_drops
            """).fetchall()
            for row in rows:
                enemy_cn = ENEMY_CN.get(row['enemy_name'], row['enemy_name'] or '')
                location = f"敌人: {enemy_cn}"
                drop_chance = row['enemy_mod_drop_chance']
                if drop_chance:
                    location += f" (Mod掉落率 {drop_chance}%)"
                self._add_source(row['mod_name'], {
                    'location': location,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'source_type': 'modLocations',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载Mod掉落失败: {e}")

    def _load_enemy_mod_tables(self, conn):
        """敌人 Mod 掉落表"""
        try:
            rows = conn.execute("""
                SELECT enemy_name, mod_name, rarity, chance, enemy_mod_drop_chance
                FROM enemy_mod_tables
            """).fetchall()
            for row in rows:
                enemy_cn = ENEMY_CN.get(row['enemy_name'], row['enemy_name'] or '')
                location = f"敌人: {enemy_cn}"
                drop_chance = row['enemy_mod_drop_chance']
                if drop_chance:
                    location += f" (Mod掉落率 {drop_chance}%)"
                self._add_source(row['mod_name'], {
                    'location': location,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'source_type': 'enemyModTables',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载敌人Mod表失败: {e}")

    def _load_blueprint_drops(self, conn):
        """蓝图掉落（blueprintLocations 视角）"""
        try:
            rows = conn.execute("""
                SELECT blueprint_name, enemy_name, rarity, chance, enemy_bp_drop_chance
                FROM blueprint_drops
            """).fetchall()
            for row in rows:
                enemy_cn = ENEMY_CN.get(row['enemy_name'], row['enemy_name'] or '')
                location = f"敌人: {enemy_cn}"
                drop_chance = row['enemy_bp_drop_chance']
                if drop_chance:
                    location += f" (掉落概率 {drop_chance}%)"
                self._add_source(row['blueprint_name'], {
                    'location': location,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'source_type': 'blueprintLocations',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载蓝图掉落失败: {e}")

    def _load_enemy_bp_tables(self, conn):
        """敌人蓝图掉落表"""
        try:
            rows = conn.execute("""
                SELECT enemy_name, blueprint_name, rarity, chance, enemy_bp_drop_chance
                FROM enemy_bp_tables
            """).fetchall()
            for row in rows:
                enemy_cn = ENEMY_CN.get(row['enemy_name'], row['enemy_name'] or '')
                location = f"敌人: {enemy_cn}"
                drop_chance = row['enemy_bp_drop_chance']
                if drop_chance:
                    location += f" (掉落概率 {drop_chance}%)"
                self._add_source(row['blueprint_name'], {
                    'location': location,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'source_type': 'enemyBlueprintTables',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载敌人蓝图表失败: {e}")

    def _load_syndicate_rewards(self, conn):
        """集团奖励"""
        try:
            rows = conn.execute("""
                SELECT syndicate_name, item_name, rarity, chance, rotation
                FROM syndicate_rewards
            """).fetchall()
            for row in rows:
                location = f"购买: {row['syndicate_name']}"
                self._add_source(row['item_name'], {
                    'location': location,
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 100,
                    'rotation': row['rotation'] or '',
                    'source_type': 'syndicates',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载集团奖励失败: {e}")

    def _load_item_drops(self, conn):
        """物品掉落（items.drops[] 的规范化数据）"""
        try:
            rows = conn.execute("""
                SELECT unique_name, drop_type, location, rarity, chance
                FROM item_drops
            """).fetchall()
            for row in rows:
                self._add_source(row['location'], {
                    'location': row['location'] or '',
                    'rarity': row['rarity'] or '',
                    'chance': row['chance'] or 0,
                    'source_type': row['drop_type'] or 'item_drops',
                })
        except Exception as e:
            print(f"[DropTooltip] 加载物品掉落失败: {e}")

    # ---- 查询 ----

    def query(self, item_name: str, max_sources: int = 20) -> list[dict]:
        """查询物品的掉落来源。

        Returns:
            [{location, rarity, chance, rotation?, source_type}, ...]
            按 chance 降序排列
        """
        self.ensure_built()

        if not item_name:
            return []

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
    def _cn_source(src_type: str) -> str:
        return SOURCE_TYPE_CN.get(src_type, src_type)

    def format_tooltip(self, sources: list[dict], item_name: str = "") -> str:
        """将掉落来源格式化为 HTML tooltip，赛博朋克深色风格。"""
        if not sources:
            return (
                f"<div style='background:{CYBER_CARD_BG}; padding:8px;'>"
                f"<b style='color:{CYBER_CYAN};'>{self._escape_html(item_name)}</b><br>"
                f"<span style='color:{CYBER_TEXT_DIM}; font-size:11px;'>暂无掉落来源数据</span></div>"
            )

        # 按 source_type 分组
        by_type: dict[str, list] = {}
        for s in sources:
            st = s.get('source_type', '')
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(s)

        type_colors = {
            'relics':      COLOR_GOLD,
            'missionRewards': CYBER_CYAN,
            'bountyRewards': CYBER_ORANGE,
            'cetusBountyRewards': CYBER_ORANGE,
            'solarisBountyRewards': CYBER_ORANGE,
            'deimosRewards': CYBER_ORANGE,
            'zarimanRewards': CYBER_ORANGE,
            'entratiLabRewards': CYBER_ORANGE,
            'hexRewards': CYBER_ORANGE,
            'sortieRewards': CYBER_RED,
            'keyRewards': CYBER_GREEN,
            'transientRewards': COLOR_PURPLE,
            'blueprintLocations': CYBER_CYAN,
            'enemyModTables': COLOR_ENEMY,
            'enemyBlueprintTables': COLOR_ENEMY,
            'modLocations': COLOR_ENEMY,
            'syndicates': CYBER_YELLOW,
            'item_drops': MUTED_TEXT,
        }

        parts = []
        parts.append(
            f"<div style='background:{CYBER_CARD_BG}; border-radius:8px; overflow:hidden;'>"
        )
        parts.append(
            f"<div style='background:{CYBER_CARD_BG}; padding:8px 12px; "
            f"border-bottom:1px solid {SUBTLE_BORDER};'>"
            f"<span style='color:{CYBER_CYAN}; font-size:14px; font-weight:bold;'>"
            f"{self._escape_html(item_name)}</span>"
            f"<span style='color:{CYBER_TEXT_DIM}; font-size:10px; margin-left:8px;'>"
            f"掉落来源 ({sum(len(v) for v in by_type.values())} 条)</span>"
            f"</div>"
        )
        parts.append(
            f"<div style='background:{CYBER_CARD_BG}; padding:6px 12px 8px 12px;'>"
        )

        for st, items in by_type.items():
            cn_st = self._cn_source(st)
            accent = type_colors.get(st, CYBER_TEXT_DIM)

            parts.append(
                f"<div style='margin-top:6px; margin-bottom:2px;'>"
                f"<span style='display:inline-block; width:3px; height:12px; "
                f"background:{accent}; border-radius:2px; margin-right:6px; "
                f"vertical-align:middle;'></span>"
                f"<span style='color:{accent}; font-size:12px; font-weight:bold; "
                f"vertical-align:middle;'>{self._escape_html(cn_st)}</span>"
                f"<span style='color:{CYBER_TEXT_DIM}; font-size:10px; margin-left:4px; "
                f"vertical-align:middle;'>({len(items)})</span>"
                f"</div>"
            )

            for item in items[:8]:
                loc = item.get('location', '?')
                rarity = item.get('rarity', '')
                chance = item.get('chance', 0)
                rotation = item.get('rotation', '')

                if chance > 0 and chance < 100:
                    chance_str = f"{chance:.1f}%"
                elif chance >= 100:
                    chance_str = "必定"
                else:
                    chance_str = ""

                rot_tag = ""
                if rotation:
                    rot_tag = (
                        f"<span style='display:inline-block; background:{SUBTLE_BORDER}; "
                        f"color:{MUTED_TEXT}; font-size:10px; padding:1px 5px; "
                        f"border-radius:3px; margin-left:4px;'>轮次{rotation}</span>"
                    )

                extra = ""
                if chance_str and rot_tag:
                    extra = f" -- <span style='color:{MUTED_TEXT};'>{chance_str}</span> {rot_tag}"
                elif chance_str:
                    extra = f" -- <span style='color:{MUTED_TEXT};'>{chance_str}</span>"
                elif rot_tag:
                    extra = f" -- {rot_tag}"

                parts.append(
                    f"<div style='padding:2px 0 2px 12px; font-size:12px; "
                    f"white-space:nowrap;'>"
                    f"<span style='color:{LIGHT_TEXT};'>{self._escape_html(loc)}</span>"
                    f"{extra}"
                    f"</div>"
                )

        parts.append("</div>")
        parts.append("</div>")
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
    idx = DropSourceIndex()
    idx.ensure_built()

    tests = ["Soma", "Frost Prime Blueprint", "Steel Fiber", "Serration", "Parry"]
    for name in tests:
        sources = idx.query(name, max_sources=10)
        print(f"\n{'='*60}")
        print(idx.format_tooltip(sources, name))
        if not sources:
            print("  (无掉落数据)")
