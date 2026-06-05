"""
数据库工具模块 —— update_db.py 和 migrate_to_sqlite.py 的共用代码。
"""

import json
import os
import re
import sqlite3
import shutil

# ============================================================
# 纪元英文 → 中文映射
# ============================================================
TIER_MAP = {
    "Lith":      "古纪",
    "Meso":      "前纪",
    "Neo":       "中纪",
    "Axi":       "后纪",
    "Requiem":   "安魂",
    "Vanguard":  "先锋",
}

# ============================================================
# 数据库表结构定义
# ============================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS relics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    era TEXT NOT NULL,
    code TEXT NOT NULL,
    vaulted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS relic_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id INTEGER NOT NULL,
    part_name TEXT NOT NULL,
    rarity TEXT NOT NULL,
    chance REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relic_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id INTEGER NOT NULL,
    alias TEXT NOT NULL UNIQUE,
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_relic_parts_relic_id ON relic_parts(relic_id);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON relic_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_aliases_relic_id ON relic_aliases(relic_id);
CREATE INDEX IF NOT EXISTS idx_relics_era ON relics(era);
CREATE INDEX IF NOT EXISTS idx_relics_vaulted ON relics(vaulted);
"""


# ============================================================
# 别名生成
# ============================================================

def generate_aliases(name: str, era: str, code: str) -> list[str]:
    """为每个遗物生成所有别名变体"""
    return [
        name,                                    # 原始名称 "古纪 C7"
        f"{era} {code}",                         # 标准名   "古纪 C7"
        f"{era}{code}",                          # 无空格    "古纪C7"
        f"{era.lower()} {code.lower()}",         # 小写带空格
        f"{era.lower()}{code.lower()}",          # 小写无空格
    ]


# ============================================================
# 数据库写入辅助
# ============================================================

def open_db_write(db_path: str) -> sqlite3.Connection:
    """安全打开数据库进行写入（若被占用则写临时文件后替换）"""
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"  已删除旧数据库: {db_path}")
        except OSError as e:
            alt_path = db_path + '.new'
            print(f"  旧数据库无法删除 ({e})，将写入临时文件: {alt_path}")
            conn = sqlite3.connect(alt_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA_SQL)
            return conn

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def finalize_db(db_path: str):
    """如果写入了临时文件，尝试替换正式文件"""
    import shutil
    alt_path = db_path + '.new'
    if os.path.exists(alt_path):
        try:
            shutil.move(alt_path, db_path)
            print(f"  已替换数据库: {db_path}")
        except PermissionError:
            print(f"  ⚠ 无法替换数据库（被占用），新数据在: {alt_path}")
            print(f"  ⚠ 请关闭占用程序后手动重命名为 {os.path.basename(db_path)}")


# ============================================================
# 出入库推断（从 all.json 掉落来源）
# ============================================================

def extract_dropping_relics(alljson_path: str) -> set[str]:
    """
    从 all.json 中扫描所有掉落来源（missionRewards, bountyRewards, keyRewards 等），
    匹配格式如 "Lith C14 Relic" 的条目，提取为标准名 "古纪 C14"。

    返回：有掉落途径的遗物标准名集合（vaulted=1，出库/可获取）
    """
    if not os.path.exists(alljson_path):
        print(f"  [出入库] ⚠ all.json 不存在，无法推断出入库状态: {alljson_path}")
        return set()

    with open(alljson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    dropping_raw = set()

    def collect_relics(rewards):
        for reward in rewards:
            if isinstance(reward, dict):
                item_name = reward.get('itemName', '')
                if 'Relic' in item_name:
                    dropping_raw.add(item_name)

    def deep_search(obj):
        if isinstance(obj, dict):
            if 'rewards' in obj and isinstance(obj['rewards'], list):
                collect_relics(obj['rewards'])
            for val in obj.values():
                deep_search(val)
        elif isinstance(obj, list):
            for val in obj:
                deep_search(val)

    # 扫描除 relics 定义外的所有数据
    for top_key, top_val in data.items():
        if top_key != 'relics':
            deep_search(top_val)

    # 解析为标准名: "Lith C14 Relic" / "Lith C14 Relic (Radiant)" → "古纪 C14"
    dropping_standards = set()
    for raw in dropping_raw:
        m = re.match(r'(\w+)\s+(\S+)\s+Relic', raw)
        if m:
            tier_en = m.group(1)
            code = m.group(2)
            era_cn = TIER_MAP.get(tier_en)
            if era_cn:
                dropping_standards.add(f"{era_cn} {code}")

    print(f"  [出入库] 从掉落数据中找到 {len(dropping_standards)} 个有掉落途径的遗物 → vaulted=1 (出库)")
    return dropping_standards


# ============================================================
# 通用：all.json → DB 迁移核心逻辑
# ============================================================

def migrate_alljson_to_db(
    json_path: str,
    db_path: str,
    dropping_set: set[str] = None,
    vt_set: set[str] = None,
) -> dict:
    """
    从 all.json 迁移数据到 SQLite 数据库。

    策略：
      - 同遗物不同 state (Intact/Exceptional/Flawless/Radiant) 只保留 Intact
      - tier 英文 → 中文纪元
      - vaulted：虚空商人(2) > 出库(1) > 入库(0)
    """
    if dropping_set is None:
        dropping_set = set()
    if vt_set is None:
        vt_set = set()

    print(f"  读取源文件: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    raw_relics = data.get('relics', [])
    print(f"  原始记录: {len(raw_relics)} 条（含不同 state）")

    # 按 (tier, relicName) 去重，优先 Intact
    deduped = {}
    skipped = 0
    for item in raw_relics:
        tier = item.get('tier', '')
        relic_name = item.get('relicName', '')
        state = item.get('state', '')
        if not tier or not relic_name:
            skipped += 1
            continue
        key = (tier, relic_name)
        if key not in deduped or state == 'Intact':
            deduped[key] = item

    print(f"  去重后: {len(deduped)} 个独立遗物 (跳过 {skipped} 条无效)")

    conn = open_db_write(db_path)
    cur = conn.cursor()

    # 清空旧数据（防止旧数据库未被删除导致的 UNIQUE 冲突）
    cur.execute("DELETE FROM relic_aliases")
    cur.execute("DELETE FROM relic_parts")
    cur.execute("DELETE FROM relics")
    conn.commit()

    inserted_relics = 0
    inserted_parts = 0
    inserted_aliases = 0

    for (tier_en, code), item in sorted(deduped.items()):
        era = TIER_MAP.get(tier_en, tier_en)
        name = f"{era} {code}"

        # vaulted 状态：虚空商人 > 出库 > 入库
        if name in vt_set:
            vaulted = 2
        elif name in dropping_set:
            vaulted = 1
        else:
            vaulted = 0

        cur.execute(
            "INSERT INTO relics (name, era, code, vaulted) VALUES (?, ?, ?, ?)",
            (name, era, code, vaulted)
        )
        relic_id = cur.lastrowid
        inserted_relics += 1

        for reward in item.get('rewards', []):
            part_name = reward.get('itemName', '')
            rarity = reward.get('rarity', 'Common')
            chance = reward.get('chance', 0)
            if part_name:
                cur.execute(
                    "INSERT INTO relic_parts (relic_id, part_name, rarity, chance) VALUES (?, ?, ?, ?)",
                    (relic_id, part_name, rarity, chance)
                )
                inserted_parts += 1

        for alias in generate_aliases(name, era, code):
            try:
                cur.execute(
                    "INSERT INTO relic_aliases (relic_id, alias) VALUES (?, ?)",
                    (relic_id, alias)
                )
                inserted_aliases += 1
            except sqlite3.IntegrityError:
                pass

    conn.commit()
    conn.close()

    return {
        'relics': inserted_relics,
        'parts': inserted_parts,
        'aliases': inserted_aliases,
        'dropping': len(dropping_set),
    }


def migrate_relicsjson_to_db(json_path: str, db_path: str) -> dict:
    """
    从 relics.json 迁移数据到 SQLite 数据库（旧版格式）。
    """
    print(f"  读取源文件: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    relics_list = data.get('relics', [])
    print(f"  发现 {len(relics_list)} 条遗物记录")

    conn = open_db_write(db_path)
    cur = conn.cursor()

    inserted_relics = 0
    inserted_parts = 0
    inserted_aliases = 0

    for item in relics_list:
        name = item.get('name', '')
        era = item.get('era', '')
        code = item.get('code', '')
        parts = item.get('parts', [])
        vaulted = 1 if item.get('vaulted', False) else 0

        if not name:
            continue

        cur.execute(
            "INSERT INTO relics (name, era, code, vaulted) VALUES (?, ?, ?, ?)",
            (name, era, code, vaulted)
        )
        relic_id = cur.lastrowid
        inserted_relics += 1

        for part in parts:
            part_name = part.get('name', '')
            rarity = part.get('rarity', 'Common')
            if part_name:
                cur.execute(
                    "INSERT INTO relic_parts (relic_id, part_name, rarity, chance) VALUES (?, ?, ?, 0)",
                    (relic_id, part_name, rarity)
                )
                inserted_parts += 1

        for alias in generate_aliases(name, era, code):
            try:
                cur.execute(
                    "INSERT INTO relic_aliases (relic_id, alias) VALUES (?, ?)",
                    (relic_id, alias)
                )
                inserted_aliases += 1
            except sqlite3.IntegrityError:
                pass

    conn.commit()
    conn.close()

    return {
        'relics': inserted_relics,
        'parts': inserted_parts,
        'aliases': inserted_aliases,
        'dropping': None,
    }
