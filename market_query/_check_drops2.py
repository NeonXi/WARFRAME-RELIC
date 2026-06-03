import json
import sys
from collections import Counter

# Load drop index (manually)
d = json.load(open('d:/MyProgram/WARFRAME-RELIC/data/all.json', 'r', encoding='utf-8'))

# Build drop index the same way as DropSourceIndex
drop_sources = {}  # item_name.lower() -> list

def add_source(item_name, source):
    if not item_name:
        return
    key = item_name.strip().lower()
    if key not in drop_sources:
        drop_sources[key] = []
    drop_sources[key].append(source)
    import re
    stripped = re.sub(r'\s*\([^)]*\)\s*$', '', key).strip()
    if stripped and stripped != key:
        if stripped not in drop_sources:
            drop_sources[stripped] = []
        drop_sources[stripped].append(source)

# Simplified scan
for top_key, top_val in d.items():
    if top_key == 'relics':
        for relic in top_val:
            for reward in relic.get('rewards', []):
                add_source(reward.get('itemName', ''), {'st': 'relics'})
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
                                    add_source(item.get('itemName', ''), {'st': 'mission'})
    elif top_key in ('cetusBountyRewards', 'solarisBountyRewards', 'deimosRewards', 'zarimanRewards', 'entratiLabRewards', 'hexRewards'):
        for entry in top_val:
            if not isinstance(entry, dict): continue
            rewards = entry.get('rewards', {})
            if isinstance(rewards, dict):
                for rot, items in rewards.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                add_source(item.get('itemName', ''), {'st': 'bounty'})
    elif top_key in ('sortieRewards',):
        for entry in top_val:
            if isinstance(entry, dict):
                add_source(entry.get('itemName', ''), {'st': 'sortie'})
    elif top_key in ('keyRewards', 'transientRewards'):
        for entry in top_val:
            if not isinstance(entry, dict): continue
            rewards = entry.get('rewards', {})
            if isinstance(rewards, list):
                for item in rewards:
                    if isinstance(item, dict):
                        add_source(item.get('itemName', ''), {'st': top_key})
            elif isinstance(rewards, dict):
                for rot, items in rewards.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                add_source(item.get('itemName', ''), {'st': top_key})
    elif top_key == 'blueprintLocations':
        for bp in top_val:
            if isinstance(bp, dict):
                add_source(bp.get('blueprintName', bp.get('itemName', '')), {'st': 'bp'})
    elif top_key == 'enemyModTables':
        for entry in top_val:
            if isinstance(entry, dict):
                for mod in entry.get('mods', []):
                    if isinstance(mod, dict):
                        add_source(mod.get('modName', ''), {'st': 'enemyMod'})
    elif top_key == 'enemyBlueprintTables':
        for bp in top_val:
            if isinstance(bp, dict):
                add_source(bp.get('blueprintName', bp.get('itemName', '')), {'st': 'enemyBp'})
    elif top_key == 'modLocations':
        for mod in top_val:
            if isinstance(mod, dict):
                add_source(mod.get('modName', mod.get('itemName', '')), {'st': 'modLoc'})
    elif top_key == 'syndicates':
        for faction, items in top_val.items():
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, dict):
                        add_source(entry.get('item', ''), {'st': 'synd'})
    elif top_key in ('resourceByAvatar', 'sigilByAvatar', 'additionalItemByAvatar'):
        for entry in top_val:
            if isinstance(entry, dict):
                for item in entry.get('items', []):
                    if isinstance(item, dict):
                        add_source(item.get('item', ''), {'st': top_key})

print(f"Drop index: {len(drop_sources)} items")

# Now let's check specific queries
sys.path.insert(0, 'd:/MyProgram/WARFRAME-RELIC')
from data.items_i18n import suggest_items

# Test a few items the user might have issues with
test_queries = [
    'Aksomati',   # should have Prime parts
    'Soma Prime', # parts should match
    'Steel Fiber',# common mod with drops
    'Hell chamber', 
    'Intensify', 
    'Frost Prime', # prime frame parts
    'Burston Prime Stock',
    'Lex Prime Receiver',
    'Braton Prime',
    'Dual Kamas Prime',
]

print("\n=== Testing queries ===")
for q in test_queries:
    results = suggest_items(q, limit=10)
    print(f"\n--- Query: '{q}' ---")
    found_drop = 0
    no_drop = 0
    for r in results[:8]:
        en = r['en_name']
        has = 'YES' if en.lower() in drop_sources else 'NO '
        if en.lower() in drop_sources:
            found_drop += 1
        else:
            no_drop += 1
        print(f"  [{has}] en='{en}' | zh='{r['zh_name']}'")
    print(f"  => {found_drop} with drops, {no_drop} without")