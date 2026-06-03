import json
import os

# Load all.json
d = json.load(open('d:/MyProgram/WARFRAME-RELIC/data/all.json', 'r', encoding='utf-8'))

matches = set()

def scan_rewards(rewards, matches, keyword):
    if isinstance(rewards, dict):
        for rot, items in rewards.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and 'itemName' in item and keyword.lower() in item['itemName'].lower():
                        matches.add(item['itemName'])
    elif isinstance(rewards, list):
        for item in rewards:
            if isinstance(item, dict) and 'itemName' in item and keyword.lower() in item['itemName'].lower():
                matches.add(item['itemName'])

for top_key, top_val in d.items():
    if isinstance(top_val, dict):
        for k, v in top_val.items():
            if isinstance(v, dict):
                # missionRewards style: {planet: {node: {gameMode, rewards: {}}}}
                if 'gameMode' in v and 'rewards' in v:
                    scan_rewards(v['rewards'], matches, 'Soma')
                # Check deeply
                for k2, v2 in v.items():
                    if isinstance(v2, dict) and 'rewards' in v2:
                        scan_rewards(v2['rewards'], matches, 'Soma')
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        if 'itemName' in item and 'Soma' in item.get('itemName', ''):
                            matches.add(item['itemName'])
                        if 'modName' in item and 'Soma' in item.get('modName', ''):
                            matches.add(item['modName'])
                        if 'blueprintName' in item and 'Soma' in item.get('blueprintName', ''):
                            matches.add(item['blueprintName'])
                        if 'rewards' in item:
                            scan_rewards(item['rewards'], matches, 'Soma')
                        if 'rewards' in item:
                            scan_rewards(item['rewards'], matches, 'Soma')
    elif isinstance(top_val, list):
        for item in top_val:
            if isinstance(item, dict):
                if 'itemName' in item and 'Soma' in item.get('itemName', ''):
                    matches.add(item['itemName'])
                if 'modName' in item and 'Soma' in item.get('modName', ''):
                    matches.add(item['modName'])
                if 'rewards' in item:
                    scan_rewards(item['rewards'], matches, 'Soma')

print("=== Items in all.json containing 'Soma' ===")
for m in sorted(matches):
    print(m)

# Now check items_i18n
print("\n=== suggest_items('Soma') results ===")
import sys
sys.path.insert(0, 'd:/MyProgram/WARFRAME-RELIC')
from data.items_i18n import suggest_items
results = suggest_items('Soma', limit=20)
for r in results:
    print(f"en='{r['en_name']}' | zh='{r['zh_name']}' | cat='{r['category']}'")

# Cross reference
print("\n=== Cross-reference ===")
all_names_lower = set(m.lower() for m in matches)
for r in results:
    en = r['en_name'].lower()
    if en in all_names_lower:
        print(f"  MATCH: '{r['en_name']}' has drop data")
    else:
        print(f"  NO MATCH: '{r['en_name']}' NOT in drop data")