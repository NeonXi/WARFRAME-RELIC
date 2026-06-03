import json

d = json.load(open('d:/MyProgram/WARFRAME-RELIC/data/all.json', 'r', encoding='utf-8'))

# Find all Frost items in drops
print("=== All 'Frost' items in all.json ===")
all_frost = set()
for top_key, top_val in d.items():
    def scan(obj, key_name='itemName'):
        if isinstance(obj, dict):
            name = obj.get(key_name, '')
            if name and 'frost' in name.lower():
                all_frost.add(name)
            for v in obj.values():
                scan(v, key_name)
        elif isinstance(obj, list):
            for item in obj:
                scan(item, key_name)
    scan(top_val)
    # For mod lists
    if top_key in ('enemyModTables', 'modLocations'):
        for entry in top_val:
            if isinstance(entry, dict):
                for mod in entry.get('mods', []):
                    if isinstance(mod, dict):
                        name = mod.get('modName', '')
                        if name and 'frost' in name.lower():
                            all_frost.add(name)
    # For syndicates
    if top_key in ('syndicates', 'resourceByAvatar', 'sigilByAvatar', 'additionalItemByAvatar'):
        for k, items in top_val.items() if isinstance(top_val, dict) else []:
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, dict):
                        name = entry.get('item', '')
                        if name and 'frost' in name.lower():
                            all_frost.add(name)

for name in sorted(all_frost):
    print(f"  {name}")

# Now check items_i18n results
import sys
sys.path.insert(0, 'd:/MyProgram/WARFRAME-RELIC')
from data.items_i18n import suggest_items

print("\n=== suggest_items('Frost Prime') results ===")
results = suggest_items('Frost Prime', limit=15)
for r in results:
    print(f"  en='{r['en_name']}' | category='{r['category']}'")

# Let's also check what "Frost Prime Helmet" maps to in items_i18n
print("\n=== Check: What is 'Frost Prime Helmet' in items_i18n? ===")
import sqlite3
conn = sqlite3.connect('d:/MyProgram/WARFRAME-RELIC/data/items_i18n.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM items WHERE zh_name LIKE '%Frost%Prime%头盔%' OR en_name LIKE '%Frost%Prime%Helmet%' OR en_name LIKE '%Frost%Prime%Neuroptics%'")
for row in cur.fetchall():
    print(f"  id={row['id']} en='{row['en_name']}' zh='{row['zh_name']}' category='{row.get('category', '')}'")
cur.execute("SELECT * FROM items WHERE zh_name LIKE '%Frost%Prime%系统%' OR en_name LIKE '%Frost%Prime%Systems%'")
for row in cur.fetchall():
    print(f"  id={row['id']} en='{row['en_name']}' zh='{row['zh_name']}' category='{row.get('category', '')}'")
conn.close()