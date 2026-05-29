#!/usr/bin/env python3
"""
迁移脚本：将遗物数据导入 SQLite 数据库

支持两种数据源：
  1. relics.json  (旧版，含 vaulted 状态)
  2. all.json      (新版 WFInfo 全量数据，含 chance 掉落概率)

用法：
  python -m data.migrate_to_sqlite                        # 默认从 all.json 导入
  python -m data.migrate_to_sqlite --source relics.json   # 从 relics.json 导入
  python -m data.migrate_to_sqlite /path/to/all.json      # 指定源文件

出入库判断策略：
  - 从 all.json 中扫描所有掉落来源（missionRewards/bountyRewards等）
  - 有掉落途径的遗物 → vaulted=1（出库/绿色/可获取）
  - 无掉落途径的遗物 → vaulted=0（入库/红色/不可获取）
  - 虚空商人可购买 → vaulted=2（蓝色/可从 Baro Ki'Teer 购买）
"""

import json
import os
import re
import sqlite3
import sys


# ============================================================
# 纪元英文→中文映射
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
# 表结构定义
# ============================================================

SCHEMA_SQL = """
-- 遗物主表
CREATE TABLE IF NOT EXISTS relics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,       -- 标准名 "古纪 C7"
    era TEXT NOT NULL,               -- 纪元 "古纪"
    code TEXT NOT NULL,              -- 编号 "C7"
    vaulted INTEGER NOT NULL DEFAULT 0  -- 出入库状态 0/1
);

-- 遗物部件表
CREATE TABLE IF NOT EXISTS relic_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id INTEGER NOT NULL,
    part_name TEXT NOT NULL,         -- 物品名 "Loki Prime Chassis"
    rarity TEXT NOT NULL,            -- Rare / Uncommon / Common
    chance REAL NOT NULL DEFAULT 0,  -- 掉落概率 (%)
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

-- 别名表（用于模糊匹配/OCR容错）
CREATE TABLE IF NOT EXISTS relic_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id INTEGER NOT NULL,
    alias TEXT NOT NULL UNIQUE,      -- 各种变体名
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

-- 创建索引加速查询
CREATE INDEX IF NOT EXISTS idx_relic_parts_relic_id ON relic_parts(relic_id);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON relic_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_aliases_relic_id ON relic_aliases(relic_id);
CREATE INDEX IF NOT EXISTS idx_relics_era ON relics(era);
CREATE INDEX IF NOT EXISTS idx_relics_vaulted ON relics(vaulted);
"""


# ============================================================
# 迁移逻辑
# ============================================================

def generate_aliases(name: str, era: str, code: str) -> list[str]:
    """为每个遗物生成所有别名变体（与原 RelicDB._alias_map 逻辑一致）"""
    standard_name = f"{era} {code}"
    aliases = [
        name,                                    # 原始名称 "古纪 C7"
        standard_name,                           # 标准名   "古纪 C7"
        f"{era}{code}",                          # 无空格    "古纪C7"
        f"{era.lower()} {code.lower()}",         # 小写带空格
        f"{era.lower()}{code.lower()}",          # 小写无空格
    ]
    return aliases


def _build_vaulted_from_drops(alljson_path: str) -> set[str]:
    """
    从 all.json 中提取所有有掉落途径的遗物名。
    策略：扫描 missionRewards / bountyRewards / keyRewards 等所有含 rewards 的数据，
    匹配格式如 "Lith C14 Relic" 的条目，提取为标准名 "古纪 C14"。

    返回：有掉落途径的遗物标准名集合（这些视为 vaulted=1，出库/可获取）。
    """
    if not os.path.exists(alljson_path):
        print(f"[警告] all.json 不存在，无法推断出入库状态: {alljson_path}")
        return set()

    with open(alljson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 收集所有掉落途径中的遗物名
    dropping_raw = set()

    def collect(drops):
        for reward in drops:
            if isinstance(reward, dict):
                name = reward.get('itemName', '')
                if 'Relic' in name:
                    dropping_raw.add(name)

    def deep_search(obj):
        if isinstance(obj, dict):
            if 'rewards' in obj and isinstance(obj['rewards'], list):
                collect(obj['rewards'])
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

    print(f"[出入库] 从 all.json 掉落数据中找到 {len(dropping_standards)} 个有掉落途径的遗物")
    return dropping_standards


def migrate(json_path: str, db_path: str) -> dict:
    """
    旧版迁移：relics.json → relics.db
    返回统计信息字典
    """
    print(f"[迁移] 读取源文件: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    relics_list = data.get('relics', [])
    print(f"[迁移] 发现 {len(relics_list)} 条遗物记录")

    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"[迁移] 已删除旧数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)

    inserted_relics = 0
    inserted_parts = 0
    inserted_aliases = 0
    cur = conn.cursor()

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
        'source_file': json_path,
        'db_file': db_path,
        'relics': inserted_relics,
        'parts': inserted_parts,
        'aliases': inserted_aliases,
    }


def migrate_from_alljson(json_path: str, db_path: str, dropping_set: set[str] = None, vt_set: set[str] = None) -> dict:
    """
    新版迁移：all.json → relics.db

    all.json 结构:
      [{tier: "Axi", relicName: "A1", state: "Intact", rewards: [{itemName, rarity, chance}, ...]}, ...]

    策略：
      - 同遗物不同 state (Intact/Exceptional/Flawless/Radiant) 只取 Intact 的 rewards
      - tier 英文映射为中文纪元
      - 标准名格式: "{中文纪元} {编号}"  如 "后纪 A1"
      - vaulted 状态：虚空商人(2) > 有掉落途径(1) > 无掉落途径(0)
      - 不需要遗物自身的掉落信息，只要遗物内的物品信息
    """
    if dropping_set is None:
        dropping_set = set()
    if vt_set is None:
        vt_set = set()

    print(f"[迁移] 读取源文件: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    raw_relics = data.get('relics', [])
    print(f"[迁移] 发现 {len(raw_relics)} 条遗物记录（含不同 state）")

    # 按 (tier, relicName) 去重，只保留 Intact 状态
    deduped = {}  # key: (tier, relicName) → item
    skipped = 0
    for item in raw_relics:
        tier = item.get('tier', '')
        relic_name = item.get('relicName', '')
        state = item.get('state', '')
        if not tier or not relic_name:
            skipped += 1
            continue
        key = (tier, relic_name)
        # 优先保留 Intact，若无则保留第一个遇到的
        if key not in deduped or state == 'Intact':
            deduped[key] = item

    print(f"[迁移] 去重后 {len(deduped)} 个独立遗物 (跳过 {skipped} 条无效记录)")

    # 准备数据库（若被占用则写入临时文件后替换）
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"[迁移] 已删除旧数据库: {db_path}")
        except PermissionError:
            db_path_new = db_path + '.new'
            print(f"[迁移] 旧数据库被占用，将写入临时文件: {db_path_new}")
            # 后面写入完成后再尝试替换
            pass

    actual_db_path = db_path
    if os.path.exists(db_path):
        actual_db_path = db_path + '.new'

    conn = sqlite3.connect(actual_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)

    inserted_relics = 0
    inserted_parts = 0
    inserted_aliases = 0
    cur = conn.cursor()

    for (tier_en, code), item in sorted(deduped.items()):
        era = TIER_MAP.get(tier_en, tier_en)  # 英文纪元→中文
        name = f"{era} {code}"

        # vaulted 状态：虚空商人 > 出库 > 入库
        if name in vt_set:
            vaulted = 2  # 虚空商人可购买
        elif name in dropping_set:
            vaulted = 1  # 出库/可获取
        else:
            vaulted = 0  # 入库/不可获取

        # 插入遗物主表
        cur.execute(
            "INSERT INTO relics (name, era, code, vaulted) VALUES (?, ?, ?, ?)",
            (name, era, code, vaulted)
        )
        relic_id = cur.lastrowid
        inserted_relics += 1

        # 插入部件（rewards）
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

        # 插入别名
        for alias in generate_aliases(name, era, code):
            try:
                cur.execute(
                    "INSERT INTO relic_aliases (relic_id, alias) VALUES (?, ?, ?)",
                    (relic_id, alias)
                )
                inserted_aliases += 1
            except sqlite3.IntegrityError:
                pass

    conn.commit()
    conn.close()

    # 如果写入了临时文件，尝试替换
    if actual_db_path != db_path:
        try:
            import shutil
            shutil.move(actual_db_path, db_path)
            print(f"[迁移] 已替换数据库: {db_path}")
        except PermissionError:
            print(f"[警告] 无法替换数据库文件（被占用），新数据已写入: {actual_db_path}")
            print(f"[警告] 请关闭占用程序后手动将 {actual_db_path} 重命名为 {os.path.basename(db_path)}")

    return {
        'source_file': json_path,
        'db_file': db_path,
        'relics': inserted_relics,
        'parts': inserted_parts,
        'aliases': inserted_aliases,
        'voidtrader': len(vt_set),
    }


# ============================================================
# CLI 入口
# ============================================================

def main():
    data_dir = os.path.dirname(os.path.abspath(__file__))
    default_all = os.path.join(data_dir, 'all.json')
    default_relics = os.path.join(data_dir, 'relics.json')
    default_db = os.path.join(data_dir, 'relics.db')

    # 解析参数
    args = sys.argv[1:]
    source = None
    if '--source' in args:
        idx = args.index('--source')
        source = args[idx + 1] if idx + 1 < len(args) else 'all.json'
    elif args:
        source = args[0]
    else:
        source = 'all.json'  # 默认从 all.json 导入

    # 确定源文件路径
    if source in ('all.json', 'all'):
        json_path = default_all
    elif source in ('relics.json', 'relics'):
        json_path = default_relics
    elif os.path.isabs(source):
        json_path = source
    else:
        json_path = os.path.join(data_dir, source)

    if not os.path.exists(json_path):
        print(f"[错误] 源文件不存在: {json_path}")
        sys.exit(1)

    # 执行迁移
    if 'all.json' in json_path.lower():
        # 从 all.json 掉落数据中推断出入库状态
        dropping_set = _build_vaulted_from_drops(json_path)
        stats = migrate_from_alljson(json_path, default_db, dropping_set)
    else:
        stats = migrate(json_path, default_db)

    # 输出结果
    print(f"\n{'='*50}")
    print(f"[OK] 迁移完成！")
    print(f"{'='*50}")
    print(f"  源文件: {stats['source_file']}")
    print(f"  目标库: {stats['db_file']}")
    print(f"  遗物数: {stats['relics']}")
    print(f"  部件数: {stats['parts']}")
    print(f"  别名数: {stats['aliases']}")

    db_size = os.path.getsize(default_db)
    print(f"  DB大小: {db_size:,} bytes")
    print(f"\nRelicDB 现在将自动使用 relics.db")


if __name__ == '__main__':
    main()
