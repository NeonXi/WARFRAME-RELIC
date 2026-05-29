"""
WFInfo 遗物掉落表数据库模块
- 从 SQLite 数据库加载遗物→Prime部件映射
- 提供遗物名称查询接口
- 支持模糊匹配（处理 OCR 误识别）

数据源: relics.db (由 migrate_to_sqlite.py 从 relics.json 生成)
"""

import os
import re
import sqlite3
from typing import Optional


class RelicDB:
    """Warframe 遗物掉落表数据库 (SQLite 版本)"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__))
        self._db_path = os.path.join(data_dir, 'relics.db')
        self._conn: sqlite3.Connection | None = None
        self._loaded = False

    # ========== 连接管理 ==========

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（懒加载 + 单例）"""
        if self._conn is None:
            if not os.path.exists(self._db_path):
                print(f"[RelicDB] 数据库文件不存在: {self._db_path}")
                print("[RelicDB] 提示: 运行 python -m data.migrate_to_sqlite 生成数据库")
                raise FileNotFoundError(f"DB not found: {self._db_path}")
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ========== 加载（兼容旧接口）==========

    def load(self) -> bool:
        """检查数据库是否可用，返回是否成功"""
        try:
            conn = self._get_conn()
            cur = conn.execute("SELECT COUNT(*) FROM relics")
            count = cur.fetchone()[0]
            self._loaded = True
            print(f"[RelicDB] 已连接数据库，共 {count} 个遗物")
            return True
        except Exception as e:
            print(f"[RelicDB] 数据库加载失败: {e}")
            return False

    def ensure_loaded(self):
        """懒加载：首次查询时自动初始化"""
        if not self._loaded:
            self.load()

    # ========== 查询 ==========

    def find(self, name: str) -> Optional[dict]:
        """
        按名称查找遗物（支持模糊匹配）。
        返回 None 或 {name, era, code, parts: [{name, rarity}, ...], vaulted}
        """
        self.ensure_loaded()

        conn = self._get_conn()

        # 1. 精确匹配别名表（最快路径）
        row = conn.execute(
            "SELECT r.id, r.name, r.era, r.code, r.vaulted "
            "FROM relics r JOIN relic_aliases a ON a.relic_id = r.id "
            "WHERE a.alias = ?",
            (name,)
        ).fetchone()
        if row:
            return self._build_result(row)

        # 2. 精准匹配主表 name 字段
        row = conn.execute(
            "SELECT id, name, era, code, vaulted FROM relics WHERE name = ?",
            (name,)
        ).fetchone()
        if row:
            return self._build_result(row)

        # 3. 模糊匹配：忽略空格、大小写
        normalized = name.replace(' ', '').lower()
        row = conn.execute(
            "SELECT r.id, r.name, r.era, r.code, r.vaulted "
            "FROM relics r JOIN relic_aliases a ON a.relic_id = r.id "
            "WHERE REPLACE(a.alias, ' ', '') = ? OR REPLACE(LOWER(a.alias), ' ', '') = ?",
            (normalized, normalized)
        ).fetchone()
        if row:
            return self._build_result(row)

        # 4. 正则模糊匹配：OCR 可能混淆的字符 O↔0, I↔1, L↔1, S↔5, B↔8 等
        fuzzy_key = self._fuzzy_normalize(name)
        rows = conn.execute("SELECT alias FROM relic_aliases").fetchall()
        for r in rows:
            if self._fuzzy_normalize(r['alias']) == fuzzy_key:
                return self.find(r['alias'])  # 用精确名回查一次

        return None

    def get_parts(self, name: str) -> list[dict]:
        """获取遗物包含的 Prime 部件列表 [{name, rarity}, ...]"""
        relic = self.find(name)
        if relic:
            return relic.get('parts', [])
        return []

    def is_vaulted(self, name: str) -> bool:
        """检查遗物是否已出库（vaulted）"""
        relic = self.find(name)
        if relic:
            return relic.get('vaulted', False)
        return False

    # ========== 内部方法 ==========

    def _build_result(self, row) -> dict:
        """从 relics 行构建完整结果字典（含 parts 列表）"""
        conn = self._get_conn()
        relic_id = row['id']

        parts_rows = conn.execute(
            "SELECT part_name, rarity, chance FROM relic_parts WHERE relic_id = ? ORDER BY id",
            (relic_id,)
        ).fetchall()

        parts = [
            {'name': p['part_name'], 'rarity': p['rarity'], 'chance': p['chance']}
            for p in parts_rows
        ]

        return {
            'name': row['name'],
            'era': row['era'],
            'code': row['code'],
            'vaulted': bool(row['vaulted']),
            'parts': parts,
        }

    @staticmethod
    def _fuzzy_normalize(s: str) -> str:
        """将字符串标准化用于模糊匹配（统一易混淆字符）。

        注意：OCR 常见混淆 → 统一到同一字符，避免双向映射冲突。
        - 0/O → o（统一为小写 o）
        - 1/I/l → i（统一为小写 i）
        - 5/S → s
        - 8/B → b
        """
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
        vaulted=1 → 出库(可获取)
        vaulted=0 → 入库(不可获取)
        """
        self.ensure_loaded()
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM relics").fetchone()[0]
        vaulted = conn.execute("SELECT COUNT(*) FROM relics WHERE vaulted=1").fetchone()[0]
        aliases = conn.execute("SELECT COUNT(*) FROM relic_aliases").fetchone()[0]
        parts = conn.execute("SELECT COUNT(*) FROM relic_parts").fetchone()[0]
        return {
            'total_relics': total,
            'vaulted': vaulted,        # 出库(可获取)
            'available': total - vaulted,  # 入库(不可获取)
            'total_aliases': aliases,
            'total_parts': parts,
        }
