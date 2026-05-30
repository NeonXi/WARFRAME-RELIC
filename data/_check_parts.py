import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('data/all_items.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Check for component/part items
categories = {}
for item in data:
    cat = item.get('category', 'Unknown')
    categories[cat] = categories.get(cat, 0) + 1

print("=== All categories ===")
for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {cnt}")

# Check if there's a "components" or "parts" field in items
print("\n=== Items with 'components' field ===")
count = 0
for item in data:
    if 'components' in item:
        count += 1
        if count <= 3:
            print(f"  {item.get('name')}: {len(item['components'])} components")
            for c in item['components'][:3]:
                print(f"    - {c.get('uniqueName', '?')}: {c.get('name', '?')}")

print(f"  Total items with components: {count}")

# Check for component names
print("\n=== Component name samples ===")
component_names = set()
for item in data:
    if 'components' in item:
        for c in item['components']:
            component_names.add(c.get('name', ''))
    if len(component_names) >= 30:
        break

for n in sorted(component_names)[:20]:
    print(f"  {n}")
