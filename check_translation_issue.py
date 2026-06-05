
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "game_i18n.db"
I18N_JSON_PATH = DATA_DIR / "i18n.json"

print("=" * 70)
print("翻译数据库问题检查")
print("=" * 70)

# 1. 先看看数据库里有问题的数据
print("\n[1/3] 检查数据库中的 Void Projection 相关数据...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 查询包含 "VoidProjection" 或 "Projections" 的数据
cursor.execute("""
    SELECT key, en, zh, source FROM translations 
    WHERE key LIKE '%Projection%' OR key LIKE '%projection%'
    LIMIT 30
""")
results = cursor.fetchall()

for key, en, zh, source in results:
    print(f"\n  Key: {key}")
    print(f"  EN:  {en}")
    print(f"  ZH:  {zh}")
    print(f"  Src: {source}")

# 2. 检查 i18n.json 文件是否有问题
print("\n" + "=" * 70)
print("[2/3] 检查本地 i18n.json 文件...")
if I18N_JSON_PATH.exists():
    print(f"读取 i18n.json ({I18N_JSON_PATH.stat().st_size:,} bytes)...")
    try:
        with open(I18N_JSON_PATH, 'r', encoding='utf-8') as f:
            i18n = json.load(f)
        
        # 查找 i18n.json 中的相关数据
        print(f"\ni18n.json 共有 {len(i18n):,} 条记录")
        count = 0
        for key, val in i18n.items():
            if "Projection" in key or "projection" in key:
                print(f"\n  i18n[{key}] = {val}")
                count += 1
                if count >= 10:
                    break
    except Exception as e:
        print(f"读取 i18n.json 失败: {e}")
else:
    print("i18n.json 不存在")

# 3. 检查 dict.zh.json 和 dict.en.json
print("\n" + "=" * 70)
print("[3/3] 检查本地 dict.zh.json 和 dict.en.json...")

for file in ["dict.zh.json", "dict.en.json"]:
    path = DATA_DIR / file
    if path.exists():
        print(f"\n{file}: 存在 ({path.stat().st_size:,} bytes)")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            
            # 查找相关数据
            count = 0
            for key, val in d.items():
                if "Projection" in key or "projection" in key:
                    print(f"  [{key}] = {val}")
                    count += 1
                    if count >= 5:
                        break
        except Exception as e:
            print(f"  读取失败: {e}")
    else:
        print(f"\n{file}: 不存在")

print("\n" + "=" * 70)
conn.close()
