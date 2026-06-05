
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.game_i18n import build_database
import sqlite3
from pathlib import Path

print("=" * 70)
print("重建翻译数据库 (使用本地文件模式)")
print("=" * 70)

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "game_i18n.db"

# 备份旧数据库
if DB_PATH.exists():
    import shutil
    backup_name = f"game_i18n.db.backup.{os.path.getmtime(DB_PATH):.0f}"
    backup_path = DATA_DIR / backup_name
    shutil.copy2(DB_PATH, backup_path)
    print(f"\n已备份旧数据库: {backup_name}")

# 重建数据库（使用本地文件模式）
print("\n开始构建翻译数据库...")
result = build_database(use_local_files=True)

print("\n" + "=" * 70)
print("构建完成!")
print("=" * 70)
print(f"结果: {result}")

# 快速验证一下新数据库
if "total" in result:
    print(f"\n验证新数据库...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM translations")
    count = cursor.fetchone()[0]
    print(f"翻译总数: {count:,} 条")
    
    cursor.execute("SELECT source, COUNT(*) FROM translations GROUP BY source")
    sources = cursor.fetchall()
    print("\n数据来源:")
    for src, cnt in sources:
        print(f"  {src}: {cnt:,} 条")
    
    # 检查是否还有问题的 Projection 翻译
    cursor.execute("""
        SELECT key, en, zh FROM translations 
        WHERE key LIKE '%Projection%' AND key LIKE '%Types%'
        LIMIT 10
    """)
    bad_left = cursor.fetchall()
    print(f"\n检查剩余的问题翻译: 找到 {len(bad_left)} 条")
    if bad_left:
        for key, en, zh in bad_left[:5]:
            print(f"  {key}")
    
    conn.close()

print("\n完成!")
