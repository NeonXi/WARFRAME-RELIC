
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "game_i18n.db"

print("=" * 70)
print("验证翻译数据库修复结果")
print("=" * 70)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. 检查是否还有 /Lotus/Types/ 开头的 key
cursor.execute("SELECT COUNT(*) FROM translations WHERE key LIKE '/Lotus/Types/%'")
types_count = cursor.fetchone()[0]
print(f"\n1. /Lotus/Types/ 开头的翻译条目: {types_count:,} 条")

if types_count > 0:
    print("  前 5 条:")
    cursor.execute("SELECT key, en, zh FROM translations WHERE key LIKE '/Lotus/Types/%' LIMIT 5")
    for key, en, zh in cursor.fetchall():
        print(f"    {key}")

# 2. 检查正常的 /Lotus/Language/ 开头的 key
cursor.execute("SELECT COUNT(*) FROM translations WHERE key LIKE '/Lotus/Language/%'")
lang_count = cursor.fetchone()[0]
print(f"\n2. /Lotus/Language/ 开头的翻译条目: {lang_count:,} 条")

# 3. 检查 Projection 相关的翻译
cursor.execute("""
    SELECT key, en, zh FROM translations 
    WHERE key LIKE '%Projection%' 
    ORDER BY key
""")
proj_results = cursor.fetchall()
print(f"\n3. 包含 'Projection' 的翻译: {len(proj_results)} 条")
if proj_results:
    print("  前 5 条:")
    for key, en, zh in proj_results[:5]:
        print(f"    {key}")
        print(f"      EN: {en}")
        print(f"      ZH: {zh}")

conn.close()
print("\n" + "=" * 70)
print("验证完成! ✅")
