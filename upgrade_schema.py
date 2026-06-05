
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.items_i18n import _ensure_schema_version, DB_PATH
import sqlite3

print("正在升级 items_i18n.db schema...")
print(f"数据库路径: {DB_PATH}")
print()

conn = sqlite3.connect(DB_PATH)
try:
    _ensure_schema_version(conn)
    print("Schema 升级完成！")
    
    # 验证结果
    print("\n验证升级结果:")
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM items_meta WHERE key='schema_version'")
    version = cursor.fetchone()
    if version:
        print(f"当前 schema 版本: {version[0]}")
    
    cursor.execute("PRAGMA table_info(items)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"\nitems 表的列:")
    for col in columns:
        print(f"  - {col}")
    
    if 'drop_source_zh' not in columns and 'drop_source_en' not in columns:
        print("\n✅ 成功: drop_source_zh 和 drop_source_en 字段已移除！")
    else:
        print("\n❌ 失败: drop_source_zh 或 drop_source_en 字段仍然存在！")
        
finally:
    conn.commit()
    conn.close()
