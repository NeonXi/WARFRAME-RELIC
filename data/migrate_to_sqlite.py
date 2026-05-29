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

import os
import sys

from data.db_utils import (
    extract_dropping_relics,
    migrate_alljson_to_db,
    migrate_relicsjson_to_db,
    finalize_db,
)


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
        source = 'all.json'

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
        dropping_set = extract_dropping_relics(json_path)
        stats = migrate_alljson_to_db(json_path, default_db, dropping_set)
    else:
        stats = migrate_relicsjson_to_db(json_path, default_db)

    finalize_db(default_db)

    # 输出结果
    print(f"\n{'='*50}")
    print(f"[OK] 迁移完成！")
    print(f"{'='*50}")
    print(f"  源文件: {json_path}")
    print(f"  目标库: {default_db}")
    print(f"  遗物数: {stats['relics']}")
    print(f"  部件数: {stats['parts']}")
    print(f"  别名数: {stats['aliases']}")

    db_size = os.path.getsize(default_db)
    print(f"  DB大小: {db_size:,} bytes")
    print(f"\nRelicDB 现在将自动使用 relics.db")


if __name__ == '__main__':
    main()
