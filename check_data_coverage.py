
import sqlite3
import os

data_dir = os.path.join(os.path.dirname(__file__), 'data')
wm_items_db = os.path.join(data_dir, 'wm_items.db')
wm_prices_db = os.path.join(data_dir, 'wm_prices.db')

print('=' * 60)
print('数据覆盖情况检查')
print('=' * 60)

# 读取 wm_items.db
conn1 = sqlite3.connect(wm_items_db)
conn1.row_factory = sqlite3.Row
cursor1 = conn1.cursor()
cursor1.execute('SELECT en_name, slug FROM items')
items_data = {row['en_name']: row['slug'] for row in cursor1.fetchall()}
conn1.close()
print(f'\nwm_items.db: {len(items_data)} 条记录')

# 读取 wm_prices.db
conn2 = sqlite3.connect(wm_prices_db)
conn2.row_factory = sqlite3.Row
cursor2 = conn2.cursor()
cursor2.execute('SELECT en_name, slug FROM item_prices')
prices_data = {row['en_name']: row['slug'] for row in cursor2.fetchall()}
conn2.close()
print(f'wm_prices.db: {len(prices_data)} 条记录')

# 检查差异
missing_in_prices = set(items_data.keys()) - set(prices_data.keys())
print(f'\nwm_prices.db 缺少 wm_items.db 中的 {len(missing_in_prices)} 条记录')
if len(missing_in_prices) &lt;= 20:
    for name in missing_in_prices:
        print(f'  - {name} (slug: {items_data[name]})')
else:
    print(f'  前 20 条:')
    for name in list(missing_in_prices)[:20]:
        print(f'  - {name}')

extra_in_prices = set(prices_data.keys()) - set(items_data.keys())
print(f'\nwm_prices.db 有而 wm_items.db 没有的 {len(extra_in_prices)} 条记录')
if len(extra_in_prices) &lt;= 20:
    for name in extra_in_prices:
        print(f'  - {name}')
else:
    print(f'  前 20 条:')
    for name in list(extra_in_prices)[:20]:
        print(f'  - {name}')
