import json
import sqlite3
import sys
sys.path.insert(0, 'd:/MyProgram/WARFRAME-RELIC')

# Build drop index from all.json
d = json.load(open('d:/MyProgram/WARFRAME-RELIC/data/all.json', 'r', encoding='utf-8'))

drop_names = set()

def add_name(name):
    if name:
        drop_names.add(name.strip().lower())

for top_key, top_val in d.items():
    if top_key == 'relics':
        for relic in top_val:
            for reward in relic.get('rewards', []):
                add_name(reward.get('itemName', ''))
    elif top_key == 'missionRewards':
        for planet, nodes in top_val.items():
            if not isinstance(nodes, dict): continue
            for node, ndata in nodes.items():
                if not isinstance(ndata, dict): continue
                rewards = ndata.get('rewards', {})
                if isinstance(rewards, dict):
                    for rot, items in rewards.items():
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    add_name(item.get('itemName', ''))
    elif top_key in ('cetusBountyRewards', 'solarisBountyRewards', 'deimosRewards', 'zarimanRewards', 'entratiLabRewards', 'hexRewards'):
        for entry in top_val:
            if not isinstance(entry, dict): continue
            rewards = entry.get('rewards', {})
            if isinstance(rewards, dict):
                for rot, items in rewards.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                add_name(item.get('itemName', ''))
    elif top_key in ('sortieRewards',):
        for entry in top_val:
            if isinstance(entry, dict):
                add_name(entry.get('itemName', ''))
    elif top_key in ('keyRewards', 'transientRewards'):
        for entry in top_val:
            if not isinstance(entry, dict): continue
            rewards = entry.get('rewards', {})
            if isinstance(rewards, list):
                for item in rewards:
                    if isinstance(item, dict):
                        add_name(item.get('itemName', ''))
            elif isinstance(rewards, dict):
                for rot, items in rewards.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                add_name(item.get('itemName', ''))
    elif top_key == 'blueprintLocations':
        for bp in top_val:
            if isinstance(bp, dict):
                add_name(bp.get('blueprintName', bp.get('itemName', '')))
    elif top_key == 'enemyModTables':
        for entry in top_val:
            if isinstance(entry, dict):
                for mod in entry.get('mods', []):
                    if isinstance(mod, dict):
                        add_name(mod.get('modName', ''))
    elif top_key == 'enemyBlueprintTables':
        for bp in top_val:
            if isinstance(bp, dict):
                add_name(bp.get('blueprintName', bp.get('itemName', '')))
    elif top_key == 'modLocations':
        for mod in top_val:
            if isinstance(mod, dict):
                add_name(mod.get('modName', mod.get('itemName', '')))
    elif top_key == 'syndicates':
        for faction, items in top_val.items():
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, dict):
                        add_name(entry.get('item', ''))
    elif top_key in ('resourceByAvatar', 'sigilByAvatar', 'additionalItemByAvatar'):
        for entry in top_val:
            if isinstance(entry, dict):
                for item in entry.get('items', []):
                    if isinstance(item, dict):
                        add_name(item.get('item', ''))

print(f"Drop names in all.json: {len(drop_names)}")

# Get all items from items_i18n
conn = sqlite3.connect('d:/MyProgram/WARFRAME-RELIC/data/items_i18n.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT en_name FROM items")
i18n_names = set(row['en_name'].strip().lower() for row in cur.fetchall() if row['en_name'])
conn.close()

print(f"Names in items_i18n: {len(i18n_names)}")

# Find drop items NOT in i18n
drop_only = drop_names - i18n_names
print(f"\nDrop items NOT in i18n: {len(drop_only)}")

# Categorize the mismatches
print("\n=== Sample mismatches (first 50) ===")
for name in sorted(drop_only)[:50]:
    if name:
        print(f"  '{name}'")

# Find blueprint related patterns
blueprint_mismatches = [n for n in drop_only if 'blueprint' in n]
print(f"\nBlueprint-related mismatches: {len(blueprint_mismatches)}")
for name in sorted(blueprint_mismatches)[:20]:
    print(f"  '{name}'")

# Check if these exist in all_items.json
all_items = json.load(open('d:/MyProgram/WARFRAME-RELIC/data/all_items.json', 'r', encoding='utf-8'))
all_items_names = set()
for item in all_items:
    name = item.get('name', '')
    if name:
        all_items_names.add(name.strip().lower())

print(f"\nNames in all_items.json (raw): {len(all_items_names)}")

# Drop items that exist in all_items but not in items_i18n
in_all_items = drop_only & all_items_names
print(f"Drop items NOT in i18n but IN all_items.json: {len(in_all_items)}")
for name in sorted(in_all_items)[:30]:
    print(f"  '{name}'")