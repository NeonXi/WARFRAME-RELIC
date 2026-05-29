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

vaulted 字段含义：
  - 0 = 入库（不可获取）
  - 1 = 出库（可获取，有掉落途径）
  - 2 = 虚空商人（暂未实现）

所有查询走 DB → data/wfinfo_relics.py (RelicDB)
"""

import json
import os
import sys
from pathlib import Path

from data.db_utils import (
    TIER_MAP, SCHEMA_SQL,
    generate_aliases,
    extract_dropping_relics,
    migrate_alljson_to_db,
    migrate_relicsjson_to_db,
    open_db_write,
    finalize_db,
)


# ============================================================
# 公开 API（供 management_panel.py 调用）
# ============================================================

def update_from_alljson(json_path: str, db_path: str) -> dict:
    """从 all.json 更新数据库。"""
    dropping_set = extract_dropping_relics(json_path)
    return migrate_alljson_to_db(json_path, db_path, dropping_set)


def update_from_relicsjson(json_path: str, db_path: str) -> dict:
    """从 relics.json 更新数据库（旧版格式）。"""
    return migrate_relicsjson_to_db(json_path, db_path)


# 保持旧函数名兼容（management_panel.py 使用）
_open_db_write = open_db_write
_finalize_db = finalize_db


# ============================================================
# CLI 入口
# ============================================================

def main():
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir / 'data'
    default_all = data_dir / 'all.json'
    default_relics = data_dir / 'relics.json'
    default_db = data_dir / 'relics.db'

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
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                test = json.load(f)
            if 'relics' in test and isinstance(test['relics'], list):
                item = test['relics'][0] if test['relics'] else {}
                if 'relicName' in item and 'state' in item:
                    stats = update_from_alljson(json_path, db_path)
                    finalize_db(db_path)
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
                    stats = update_from_relicsjson(json_path, db_path)
                    finalize_db(db_path)
                    _print_summary(stats, db_path)
                    return
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

    print(f"[错误] 无法识别文件格式: {json_path}")
    print("  支持: all.json (WFInfo 全量数据) 或 relics.json (旧版遗物数据)")
    sys.exit(1)


def _print_summary(stats: dict, db_path: str):
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
