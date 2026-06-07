"""
Warframe 遗物掉落表数据库模块
- 从统一数据库 warframe.db 加载遗物→Prime部件映射
- 提供遗物名称查询接口
- 支持模糊匹配（处理 OCR 误识别）
- 线程安全：使用 threading.Lock 保护连接生命周期

数据源: warframe.db (由 build_warframe_db.py 从 All.json + all.json 生成)
"""

import os
import re
import sqlite3
import threading
from typing import Optional


# 遗物时代英文→中文映射
_TIER_MAP = {
    'Lith': '古纪', 'Meso': '前纪', 'Neo': '中纪',
    'Axi': '后纪', 'Requiem': '安魂', 'Vanguard': '先锋',
}
_TIER_MAP_REV = {v: k for k, v in _TIER_MAP.items()}


class RelicDB:
    """Warframe 遗物掉落表数据库 (warframe.db 版本，线程安全)。"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__))
        self._db_path = os.path.join(data_dir, 'warframe.db')
        self._conn: sqlite3.Connection | None = None
        self._loaded = False
        self._lock = threading.Lock()

    # ========== 连接管理 ==========

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（懒加载 + 单例，线程安全）。

        使用 check_same_thread=False 允许跨线程访问，
        并用 threading.Lock 保护所有写操作和连接生命周期。
        """
        if self._conn is None:
            with self._lock:
                if self._conn is None:
                    if not os.path.exists(self._db_path):
                        raise FileNotFoundError(
                            f"[RelicDB] 数据库文件不存在: {self._db_path}\n"
                            f"[RelicDB] 提示: 请在管理面板中更新数据")
                    self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
                    self._conn.row_factory = sqlite3.Row
                    self._conn.execute("PRAGMA journal_mode=WAL")
                    self._conn.execute("PRAGMA foreign_keys=ON")
                    from data.db_connections import db_conn_registry
                    db_conn_registry.register("relic_db", self.close)
        return self._conn

    def close(self):
        """关闭数据库连接（线程安全）。"""
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
                self._loaded = False
        from data.db_connections import db_conn_registry
        db_conn_registry.unregister("relic_db")

    def invalidate(self):
        """通知数据库已被外部更新，下次查询时将重新打开连接。"""
        self.close()

    # ========== 加载 ==========

    def load(self) -> bool:
        """检查数据库是否可用，返回是否成功。"""
        try:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT COUNT(DISTINCT tier || ' ' || relic_name) FROM relics"
            )
            count = cur.fetchone()[0]
            self._loaded = True
            print(f"[RelicDB] 已连接数据库，共 {count} 个遗物")
            return True
        except Exception as e:
            print(f"[RelicDB] 数据库加载失败: {e}")
            return False

    def ensure_loaded(self):
        """懒加载：首次查询时自动初始化。"""
        if not self._loaded:
            self.load()

    # ========== 查询 ==========

    def find(self, name: str) -> Optional[dict]:
        """
        按名称查找遗物（支持模糊匹配）。

        支持的输入格式:
          - "Axi A1" / "Axi A1 Intact"  (英文)
          - "后纪 A1" / "后纪 A1 完好"    (中文)
          - "AxiA1" / "axia1"            (无空格/大小写不敏感)

        返回 None 或 {name, era, code, parts: [{name, rarity, chance}, ...], vaulted}
        """
        self.ensure_loaded()
        conn = self._get_conn()

        tier, relic_name, state = self._parse_name(name)
        if not tier or not relic_name:
            # 无法解析，尝试模糊匹配
            return self._fuzzy_find(name)

        # 精确匹配 tier + relic_name
        row = conn.execute(
            "SELECT id, tier, relic_name, state, vaulted FROM relics "
            "WHERE tier = ? AND relic_name = ? AND state = ?",
            (tier, relic_name, state)
        ).fetchone()
        if row:
            return self._build_result(row)

        # 尝试默认 state=Intact
        if state != 'Intact':
            row = conn.execute(
                "SELECT id, tier, relic_name, state, vaulted FROM relics "
                "WHERE tier = ? AND relic_name = ? AND state = 'Intact'",
                (tier, relic_name)
            ).fetchone()
            if row:
                return self._build_result(row)

        # 精确匹配失败，尝试模糊
        return self._fuzzy_find(name)

    def get_parts(self, name: str) -> list[dict]:
        """获取遗物包含的 Prime 部件列表 [{name, rarity, chance}, ...]"""
        relic = self.find(name)
        if relic:
            return relic.get('parts', [])
        return []

    def is_vaulted(self, name: str) -> bool:
        """检查遗物是否已入库（vaulted）"""
        relic = self.find(name)
        if relic:
            return relic.get('vaulted', False)
        return False

    # ========== 内部方法 ==========

    @staticmethod
    def _parse_name(name: str) -> tuple[str, str, str]:
        """
        解析遗物名称，返回 (tier, relic_name, state)。

        tier: Lith/Meso/Neo/Axi/Requiem
        relic_name: 如 A1, C7, V6
        state: Intact/Exceptional/Flawless/Radiant (默认 Intact)
        """
        # 中文 state 映射
        state_cn_map = {
            '完好': 'Intact', '优良': 'Exceptional',
            '无瑕': 'Flawless', '光辉': 'Radiant',
        }

        # 去除首尾空格
        name = name.strip()

        # 尝试匹配 "Tier Code State" 格式
        # 英文: "Axi A1 Intact"
        m = re.match(
            r'^(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s+([A-Za-z]\d+)\s*(Intact|Exceptional|Flawless|Radiant)?$',
            name, re.IGNORECASE
        )
        if m:
            tier = m.group(1).capitalize()
            relic_name = m.group(2).upper()
            state = m.group(3) or 'Intact'
            return tier, relic_name, state

        # 中文: "后纪 A1 光辉"
        tier_rev_pattern = '|'.join(re.escape(v) for v in _TIER_MAP_REV)
        m = re.match(
            rf'^({tier_rev_pattern})\s+([A-Za-z]\d+)\s*(完好|优良|无瑕|光辉)?$',
            name
        )
        if m:
            tier = _TIER_MAP_REV[m.group(1)]
            relic_name = m.group(2).upper()
            state = state_cn_map.get(m.group(3), 'Intact')
            return tier, relic_name, state

        # 无空格格式: "AxiA1"
        m = re.match(
            r'^(Lith|Meso|Neo|Axi|Requiem|Vanguard)([A-Za-z]\d+)$',
            name, re.IGNORECASE
        )
        if m:
            tier = m.group(1).capitalize()
            relic_name = m.group(2).upper()
            return tier, relic_name, 'Intact'

        return '', '', ''

    def _fuzzy_find(self, name: str) -> Optional[dict]:
        """模糊匹配遗物名称（OCR 容错）。"""
        conn = self._get_conn()
        fuzzy_key = self._fuzzy_normalize(name)

        # 提取可能的纪元和代码片段用于 SQL 模糊查询
        tier, relic_name = self._parse_name_fuzzy(name)

        # 策略1: 有纪元信息 → 用 LIKE 精确匹配代码
        if tier and relic_name:
            rows = conn.execute(
                "SELECT id, tier, relic_name, state, vaulted FROM relics "
                "WHERE tier = ? AND relic_name LIKE ? AND state = 'Intact'",
                (tier, f"%{relic_name}%")
            ).fetchall()
            if rows:
                return self._build_result(rows[0])

        # 策略2: 无纪元信息 → 用规范化 key 做 LIKE 匹配
        like_pattern = f"%{name.replace(' ', '%')}%"
        rows = conn.execute(
            "SELECT id, tier, relic_name, state, vaulted FROM relics "
            "WHERE state = 'Intact' "
            "AND (tier || ' ' || relic_name LIKE ? OR "
            "     tier || relic_name LIKE ?)",
            (like_pattern, like_pattern.replace(' ', ''))
        ).fetchall()

        for row in rows:
            candidates = [
                f"{row['tier']} {row['relic_name']}",
                f"{row['tier']}{row['relic_name']}",
            ]
            if any(self._fuzzy_normalize(c) == fuzzy_key for c in candidates):
                return self._build_result(row)

        return None

    @staticmethod
    def _parse_name_fuzzy(name: str) -> tuple[str, str]:
        """宽松解析遗物名称，仅提取可能的纪元和代码（容错版）。"""
        name = name.strip().replace(' ', '')
        # 尝试提取纪元前缀
        for t in _TIER_MAP:
            if name.lower().startswith(t.lower()):
                code = name[len(t):]
                if code and re.match(r'^[A-Za-z]\d+$', code):
                    return t.capitalize(), code.upper()
        return '', ''

    def _build_result(self, row) -> dict:
        """从 relics 行构建完整结果字典（含 parts 列表）。

        优化：批量预加载所有部件的英文→中文映射，避免逐部件 SQL 查询（N+1 问题）。
        """
        conn = self._get_conn()
        relic_id = row['id']

        parts_rows = conn.execute(
            "SELECT item_name, item_unique, rarity, chance FROM relic_rewards "
            "WHERE relic_id = ? ORDER BY id",
            (relic_id,)
        ).fetchall()

        if not parts_rows:
            tier = row['tier']
            relic_name = row['relic_name']
            return {
                'name': f"{tier} {relic_name}",
                'era': _TIER_MAP.get(tier, tier),
                'code': relic_name,
                'vaulted': bool(row['vaulted']),
                'parts': [],
            }

        # ★ 批量预加载：一次性查出所有部件的翻译映射（3 次 SQL 替代 N×3~5 次）
        # 注意：sqlite3.Row 不支持 .get()，用 try/except 或 in 运算符
        uniq_names = [p['item_unique'] for p in parts_rows if 'item_unique' in p.keys() and p['item_unique']]
        en_names = [p['item_name'] for p in parts_rows if 'item_name' in p.keys() and p['item_name']]

        zh_by_unique = {}
        zh_by_name = {}
        gt_map = {}

        if uniq_names:
            placeholders = ','.join('?' * len(uniq_names))
            zh_by_unique = {
                r['unique_name']: r['zh_name']
                for r in conn.execute(
                    f"SELECT unique_name, zh_name FROM items WHERE unique_name IN ({placeholders})",
                    uniq_names,
                ).fetchall()
                if r['zh_name']
            }

        if en_names:
            placeholders = ','.join('?' * len(en_names))
            zh_by_name = {
                r['name']: r['zh_name']
                for r in conn.execute(
                    f"SELECT name, zh_name FROM items WHERE name IN ({placeholders})",
                    en_names,
                ).fetchall()
                if r['zh_name']
            }
            gt_map = {
                r['en']: r['zh']
                for r in conn.execute(
                    f"SELECT en, zh FROM game_translations WHERE en IN ({placeholders})",
                    en_names,
                ).fetchall()
                if r['zh']
            }

        # 翻译部件名（使用预加载的字典，0 次 SQL）
        parts = []
        for p in parts_rows:
            display_name = self._translate_part_cached(
                p['item_name'], p['item_unique'],
                zh_by_unique, zh_by_name, gt_map,
            )
            parts.append({
                'name': display_name,
                'rarity': p['rarity'],
                'chance': p['chance'],
            })

        tier = row['tier']
        relic_name = row['relic_name']

        return {
            'name': f"{tier} {relic_name}",
            'era': _TIER_MAP.get(tier, tier),
            'code': relic_name,
            'vaulted': bool(row['vaulted']),
            'parts': parts,
        }

    @staticmethod
    def _translate_part_cached(en_name: str, unique_name: str,
                                zh_by_unique: dict, zh_by_name: dict,
                                gt_map: dict) -> str:
        """用预加载的字典翻译部件名（无 SQL 查询）。"""
        # 优先用 unique_name 精确匹配
        if unique_name and unique_name in zh_by_unique:
            return zh_by_unique[unique_name]
        # 回退1：用英文 item_name 匹配
        if en_name and en_name in zh_by_name:
            return zh_by_name[en_name]
        # 回退2：从 game_translations 查
        if en_name and en_name in gt_map:
            return gt_map[en_name]
        # 回退3：Blueprint 后缀处理
        if en_name and en_name.endswith(' Blueprint'):
            base = en_name[:-10].strip()
            if base in zh_by_name:
                return f"{zh_by_name[base]} 蓝图"
            if base in gt_map:
                return f"{gt_map[base]} 蓝图"
        return en_name

    def _translate_part(self, en_name: str, unique_name: str = '') -> str:
        """将英文部件名翻译为中文，多级回退：unique_name → item_name → game_translations → 去 Blueprint 后缀拼接"""
        try:
            conn = self._get_conn()
            # 优先用 unique_name 精确匹配 items
            if unique_name:
                row = conn.execute(
                    "SELECT zh_name FROM items WHERE unique_name = ?",
                    (unique_name,)
                ).fetchone()
                if row and row['zh_name']:
                    return row['zh_name']
            # 回退1：用英文 item_name 精确匹配 items
            if en_name:
                row = conn.execute(
                    "SELECT zh_name FROM items WHERE name = ?",
                    (en_name,)
                ).fetchone()
                if row and row['zh_name']:
                    return row['zh_name']
            # 回退2：从 game_translations 查
            if en_name:
                row = conn.execute(
                    "SELECT zh FROM game_translations WHERE en = ?",
                    (en_name,)
                ).fetchone()
                if row and row['zh']:
                    return row['zh']
            # 回退3：以 "Blueprint" 结尾的部件（如 Orthos Prime Blueprint），
            #        items/game_translations 中通常没有 Prime 部件蓝图条目，
            #        去掉后缀查基础武器名再拼接"蓝图"
            if en_name and en_name.endswith(' Blueprint'):
                base = en_name[:-10].strip()  # 去掉 " Blueprint"
                row = conn.execute(
                    "SELECT zh_name FROM items WHERE name = ?", (base,)
                ).fetchone()
                if row and row['zh_name']:
                    return f"{row['zh_name']} 蓝图"
                row = conn.execute(
                    "SELECT zh FROM game_translations WHERE en = ?", (base,)
                ).fetchone()
                if row and row['zh']:
                    return f"{row['zh']} 蓝图"
        except Exception:
            pass
        return en_name

    @staticmethod
    def _fuzzy_normalize(s: str) -> str:
        """将字符串标准化用于模糊匹配（统一易混淆字符）。"""
        return s.replace(' ', '').lower().translate(str.maketrans({
            '0': 'o', '1': 'i', '5': 's', '8': 'b',
            'l': 'i',
        }))

    # ========== 批量查询 ==========

    def query_many(self, names: list[str]) -> list[tuple[str, Optional[dict]]]:
        """批量查询多个遗物，返回 [(输入名, 查询结果), ...]"""
        return [(name, self.find(name)) for name in names]

    def stats(self) -> dict:
        """返回数据库统计信息
        vaulted=1 → 入库(不可获取)
        vaulted=0 → 出库(可获取)
        """
        self.ensure_loaded()
        conn = self._get_conn()
        # 去重统计（同一遗物有 4 个 state）
        total = conn.execute(
            "SELECT COUNT(DISTINCT tier || ' ' || relic_name) FROM relics"
        ).fetchone()[0]
        vaulted = conn.execute(
            "SELECT COUNT(DISTINCT tier || ' ' || relic_name) FROM relics WHERE vaulted = 1"
        ).fetchone()[0]
        parts = conn.execute("SELECT COUNT(*) FROM relic_rewards").fetchone()[0]
        return {
            'total_relics': total,
            'vaulted': vaulted,           # 入库(不可获取)
            'available': total - vaulted,  # 出库(可获取)
            'total_parts': parts,
        }
