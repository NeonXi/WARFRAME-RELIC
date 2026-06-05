
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
I18N_JSON_PATH = DATA_DIR / "i18n.json"

print("=" * 70)
print("检查 i18n.json 中的错误翻译")
print("=" * 70)

with open(I18N_JSON_PATH, 'r', encoding='utf-8') as f:
    i18n = json.load(f)

count = 0
bad_entries = []

for key, val in i18n.items():
    if "Projection" in key and isinstance(val, dict) and "zh" in val:
        zh_name = val.get("zh", {}).get("name", "") if isinstance(val.get("zh"), dict) else val.get("zh", "")
        if "遗物" in zh_name or "Relic" in zh_name:
            bad_entries.append((key, zh_name))
            count += 1
            if count <= 20:
                print(f"\n[{count}] {key}")
                print(f"  ZH: {zh_name}")

print(f"\n" + "=" * 70)
print(f"共找到 {len(bad_entries)} 条可能有问题的翻译!")

# 看看 dict.zh.json 和 dict.en.json 中是否有这些 key
print("\n检查 public-export-plus 数据源中是否有这些 key...")
dict_zh_path = DATA_DIR / "dict.zh.json"
dict_en_path = DATA_DIR / "dict.en.json"

if dict_zh_path.exists() and dict_en_path.exists():
    with open(dict_zh_path, 'r', encoding='utf-8') as f:
        dict_zh = json.load(f)
    with open(dict_en_path, 'r', encoding='utf-8') as f:
        dict_en = json.load(f)
    
    in_dict = 0
    not_in_dict = 0
    for key, _ in bad_entries[:30]:  # 只检查前 30 条
        if key in dict_zh and key in dict_en:
            in_dict += 1
        else:
            not_in_dict += 1
    
    print(f"  在 public-export-plus 中存在: {in_dict} 条")
    print(f"  只在 i18n.json 中存在: {not_in_dict} 条")
