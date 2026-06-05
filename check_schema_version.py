
import sqlite3
import os

data_dir = os.path.join(os.path.dirname(__file__), "data")
db_path = os.path.join(data_dir, "items_i18n.db")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("检查 items_i18n.db 的 schema 版本:")
try:
    cursor.execute("SELECT value FROM items_meta WHERE key='schema_version'")
    version = cursor.fetchone()
    if version:
        print(f"当前 schema 版本: {version[0]}")
    else:
        print("没有找到 schema_version 记录")
except Exception as e:
    print(f"错误: {e}")

print("\n检查 items 表的列:")
cursor.execute("PRAGMA table_info(items)")
columns = cursor.fetchall()
for col in columns:
    col_id, name, ctype, notnull, default, pk = col
    print(f"  {name}")

conn.close()
