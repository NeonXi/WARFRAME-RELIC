#!/usr/bin/env python3
"""
数据库更新脚本 —— 从 WFInfo 数据文件更新 relics.db

支持的数据源：
  - all.json      (推荐) WFInfo 全量数据，含掉落概率(chance)，自动从掉落来源推断出入库状态
  - relics.json   (备用) 旧版遗物数据，含显式 vaulted 字段

用法：
  python update_db.py                          # 默认从 data/all.json 更新
  python update_db.py /path/to/all.json        # 指定 all.json 路径
  python update_db.py /path/to/relics.json     # 指定 relics.json 路径
  python update_db.py --source all             # 显式指定数据源类型

工作流程：
  1. 读取源 JSON 文件
  2. 提取遗物信息（名称、纪元、编号、部件、概率、出入库状态）
  3. 生成别名（用于 OCR 容错匹配）
  4. 写入 data/relics.db（SQLite）
  5. 输出统计摘要

数据库表结构：
  - relics        遗物主表 (id, name, era, code, vaulted)
  - relic_parts   部件表   (id, relic_id, part_name, rarity, chance)
  - relic_aliases 别名表   (id, relic_id, alias)

vaulted 字段含义：
  - 0 = 入库（不可获取）
  - 1 = 出库（可获取，有掉落途径）

注：虚空商人(Baro Ki'Teer)功能暂未实现，相关遗物按入库处理。

所有查询走 DB → data/wfinfo_relics.py (RelicDB)
"""

import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

# ============================================================
# 常量
# ============================================================

# 纪元英文 → 中文映射
TIER_MAP = {
    "Lith":      "古纪",
    "Meso":      "前纪",
    "Neo":       "中纪",
    "Axi":       "后纪",
    "Requiem":   "安魂",
    "Vanguard":  "先锋",
}

# 数据库表结构
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
    """为每个遗物生成所有别名变体（与 RelicDB._alias_map 逻辑一致）"""
    return [
        name,                                    # 原始名称 "古纪 C7"
        f"{era} {code}",                         # 标准名   "古纪 C7"
        f"{era}{code}",                          # 无空格    "古纪C7"
        f"{era.lower()} {code.lower()}",         # 小写带空格
        f"{era.lower()}{code.lower()}",          # 小写无空格
    ]


# ============================================================
# 出入库推断（从 all.json 掉落来源）
# ============================================================

# 虚空商人 (Baro Ki'Teer) 可能出售的遗物列表
# 数据来源: 从 all.json 的 keyRewards 或其他奖励中检测 voidTrader 相关条目，
# 以及支持从独立 voidtrader_relics.json 文件加载
VOIDTRADER_RELICS: set[str] = set()


def _load_voidtrader_relics(data_dir: str = None) -> set[str]:
    """
    加载虚空商人遗物列表。

    1. 优先从 data/voidtrader_relics.json 加载（手动维护或自动获取）
    2. 其次从 all.json 中检测与 voidTrader 相关的条目

    返回：虚空商人可购买的遗物标准名集合（vaulted=2）
    """
    global VOIDTRADER_RELICS

    # 方式1: 从独立配置文件加载
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    vt_file = os.path.join(data_dir, 'voidtrader_relics.json')

    if os.path.exists(vt_file):
        try:
            with open(vt_file, 'r', encoding='utf-8') as f:
                vt_data = json.load(f)
            if isinstance(vt_data, list):
                VOIDTRADER_RELICS = set(vt_data)
                print(f"  [虚空商人] 从 voidtrader_relics.json 加载 {len(VOIDTRADER_RELICS)} 个虚空商人遗物")
                return VOIDTRADER_RELICS
        except Exception as e:
            print(f"  [虚空商人] ⚠ 加载 voidtrader_relics.json 失败: {e}")

    return set()


def _extract_voidtrader_relics(alljson_path: str) -> set[str]:
    """
    从 all.json 中扫描虚空商人相关的遗物。
    检测方式：在 keyRewards、transientRewards 等中搜索包含 'Void Trader'/'Baro' 等关键词的条目。

    返回：虚空商人可购买的遗物标准名集合（vaulted=2）
    """
    if not os.path.exists(alljson_path):
        return set()

    with open(alljson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    vt_raw = set()

    def collect_relics_from_rewards(rewards, parent_key=""):
        for reward in rewards:
            if isinstance(reward, dict):
                item_name = reward.get('itemName', '')
                if 'Relic' in item_name:
                    vt_raw.add(item_name)

    def deep_search_vt(obj, parent_key=""):
        if isinstance(obj, dict):
            # 检查 key 名是否包含 voidTrader 相关关键词
            for k, v in obj.items():
                key_lower = k.lower()
                if any(kw in key_lower for kw in ('voidtrader', 'void_trader', 'void trader', 'baro')):
                    if isinstance(v, dict) and 'rewards' in v and isinstance(v['rewards'], list):
                        collect_relics_from_rewards(v['rewards'], k)
                    elif isinstance(v, list):
                        collect_relics_from_rewards(v, k)
                deep_search_vt(v, k)
        elif isinstance(obj, list):
            for val in obj:
                deep_search_vt(val)

    # 扫描整个数据结构
    for top_key, top_val in data.items():
        key_lower = top_key.lower()
        if any(kw in key_lower for kw in ('voidtrader', 'void_trader', 'void trader', 'baro')):
            deep_search_vt(top_val, top_key)
        elif top_key != 'relics':
            deep_search_vt(top_val, top_key)

    # 解析为标准名
    vt_standards = set()
    for raw in vt_raw:
        m = re.match(r'(\w+)\s+(\S+)\s+Relic', raw)
        if m:
            tier_en = m.group(1)
            code = m.group(2)
            era_cn = TIER_MAP.get(tier_en)
            if era_cn:
                vt_standards.add(f"{era_cn} {code}")

    if vt_standards:
        print(f"  [虚空商人] 从 all.json 中找到 {len(vt_standards)} 个虚空商人遗物 → vaulted=2")
    return vt_standards


def _extract_dropping_relics(alljson_path: str) -> set[str]:
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
# 迁移: all.json → DB
# ============================================================

def update_from_alljson(json_path: str, db_path: str) -> dict:
    """
    从 all.json 更新数据库。

    all.json 结构:
      { "relics": [{tier, relicName, state, rewards: [{itemName, rarity, chance}]}, ...] }

    策略：
      - 同遗物不同 state (Intact/Exceptional/Flawless/Radiant) 只保留 Intact
      - tier 英文 → 中文纪元
      - vaulted：综合三种来源决定
        · 1 = 出库（有常规掉落途径）
        · 2 = 虚空商人（可从 Baro Ki'Teer 购买，优先级最高）
        · 0 = 入库（不可获取）
    """
    dropping_set = _extract_dropping_relics(json_path)

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

    # 写入数据库
    conn = _open_db_write(db_path)
    cur = conn.cursor()

    inserted_relics = 0
    inserted_parts = 0
    inserted_aliases = 0

    for (tier_en, code), item in sorted(deduped.items()):
        era = TIER_MAP.get(tier_en, tier_en)
        name = f"{era} {code}"

        # 决定 vaulted 状态
        if name in dropping_set:
            vaulted = 1  # 出库（可获取）
        else:
            vaulted = 0  # 入库（不可获取，含虚空商人）

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


# ============================================================
# 迁移: relics.json → DB
# ============================================================

def update_from_relicsjson(json_path: str, db_path: str) -> dict:
    """
    从 relics.json 更新数据库（旧版格式，含显式 vaulted 字段）。

    relics.json 结构:
      { "relics": [{name, era, code, vaulted, parts: [{name, rarity}]}, ...] }

    vaulted 字段支持：
      - 0 = 入库
      - 1 = 出库
      - 2 = 虚空商人
    """
    print(f"  读取源文件: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    relics_list = data.get('relics', [])
    print(f"  发现 {len(relics_list)} 条遗物记录")

    conn = _open_db_write(db_path)
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


# ============================================================
# 数据库写入辅助
# ============================================================

def _open_db_write(db_path: str) -> sqlite3.Connection:
    """安全打开数据库进行写入（若被占用则写临时文件后替换）"""
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"  已删除旧数据库: {db_path}")
        except PermissionError:
            alt_path = db_path + '.new'
            print(f"  旧数据库被占用，将写入临时文件: {alt_path}")
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


def _finalize_db(db_path: str):
    """如果写入了临时文件，尝试替换正式文件"""
    alt_path = db_path + '.new'
    if os.path.exists(alt_path):
        try:
            shutil.move(alt_path, db_path)
            print(f"  已替换数据库: {db_path}")
        except PermissionError:
            print(f"  ⚠ 无法替换数据库（被占用），新数据在: {alt_path}")
            print(f"  ⚠ 请关闭占用程序后手动重命名为 {os.path.basename(db_path)}")


# ============================================================
# CLI 入口
# ============================================================

def main():
    # 确定项目目录
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir / 'data'
    default_all = data_dir / 'all.json'
    default_relics = data_dir / 'relics.json'
    default_db = data_dir / 'relics.db'

    # 解析参数
    args = sys.argv[1:]
    json_path = None

    if '--source' in args:
        idx = args.index('--source')
        src = args[idx + 1] if idx + 1 < len(args) else 'all'
        if src in ('all', 'all.json'):
            json_path = str(default_all)
        elif src in ('relics', 'relics.json'):
            json_path = str(default_relics)
        else:
            json_path = src
    elif args:
        arg = args[0]
        if os.path.isabs(arg) or '/' in arg or '\\' in arg:
            json_path = arg
        elif arg in ('all', 'all.json'):
            json_path = str(default_all)
        elif arg in ('relics', 'relics.json'):
            json_path = str(default_relics)
        else:
            json_path = arg
    else:
        # 默认：优先 all.json，其次 relics.json
        if default_all.exists():
            json_path = str(default_all)
        elif default_relics.exists():
            json_path = str(default_relics)
        else:
            print("[错误] 未找到数据源文件。请将 all.json 或 relics.json 放到 data/ 目录，或指定路径。")
            print("用法: python update_db.py [all.json | relics.json | /path/to/file]")
            sys.exit(1)

    if not os.path.exists(json_path):
        print(f"[错误] 文件不存在: {json_path}")
        sys.exit(1)

    db_path = str(default_db)

    print("=" * 56)
    print("  Warframe 遗物数据库更新工具")
    print("=" * 56)
    print(f"  数据源: {json_path}")
    print(f"  目标库: {db_path}")
    print()

    # 判断数据源类型并执行迁移
    is_alljson = 'all.json' in os.path.basename(json_path).lower() or 'all' == os.path.basename(json_path)
    is_relicsjson = 'relics.json' in os.path.basename(json_path).lower() or 'relics' == os.path.basename(json_path)

    if is_alljson or (not is_relicsjson):
        # 尝试作为 all.json 处理
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                test = json.load(f)
            if 'relics' in test and isinstance(test['relics'], list):
                item = test['relics'][0] if test['relics'] else {}
                if 'relicName' in item and 'state' in item:
                    # 确认为 all.json 格式
                    stats = update_from_alljson(json_path, db_path)
                    _finalize_db(db_path)
                    _print_summary(stats, db_path)
                    return
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

    if is_relicsjson or not is_alljson:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                test = json.load(f)
            if 'relics' in test and isinstance(test['relics'], list):
                item = test['relics'][0] if test['relics'] else {}
                if 'name' in item and 'era' in item and 'parts' in item:
                    # 确认为 relics.json 格式
                    stats = update_from_relicsjson(json_path, db_path)
                    _finalize_db(db_path)
                    _print_summary(stats, db_path)
                    return
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

    print(f"[错误] 无法识别文件格式: {json_path}")
    print("  支持: all.json (WFInfo 全量数据) 或 relics.json (旧版遗物数据)")
    sys.exit(1)


def _print_summary(stats: dict, db_path: str):
    """打印迁移结果摘要"""
    print()
    print("=" * 56)
    print("  [OK] 更新完成!")
    print("=" * 56)
    print(f"  遗物数: {stats['relics']}")
    print(f"  部件数: {stats['parts']}")
    print(f"  别名数: {stats['aliases']}")
    if stats.get('dropping') is not None:
        dropping_count = stats['dropping']
        vaulted_count = stats['relics'] - dropping_count
        print(f"  出库:   {dropping_count} (有掉落途径)")
        print(f"  入库:   {vaulted_count} (无掉落途径)")
    print(f"  DB大小: {os.path.getsize(db_path):,} bytes")
    print(f"  数据库: {db_path}")
    print()
    print("  程序启动时将自动加载最新数据。无需额外操作。")
    print()


if __name__ == '__main__':
    main()
