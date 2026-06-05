
import sqlite3
import os

data_dir = os.path.join(os.path.dirname(__file__), 'data')
wm_items_db = os.path.join(data_dir, 'wm_items.db')
wm_prices_db = os.path.join(data_dir, 'wm_prices.db')

print('=' * 60)
print('数据覆盖情况检查')
print('=' * 60)

# Read wm_items.db
conn1 = sqlite3.connect(wm_items_db)
conn1.row_factory = sqlite3.Row
cursor1 = conn1.cursor()
cursor1.execute('SELECT en_name, slug FROM items')
items_data = {row['en_name']: row['slug'] for row in cursor1.fetchall()}
conn1.close()
print('\nwm_items.db: %d records' % len(items_data))

# Read wm_prices.db
conn2 = sqlite3.connect(wm_prices_db)
conn2.row_factory = sqlite3.Row
cursor2 = conn2.cursor()
cursor2.execute('SELECT en_name, slug FROM item_prices')
prices_data = {row['en_name']: row['slug'] for row in cursor2.fetchall()}
conn2.close()
print('wm_prices.db: %d records' % len(prices_data))

# Check differences
missing_in_prices = set(items_data.keys()) - set(prices_data.keys())
print('\nwm_prices.db missing %d records from wm_items.db' % len(missing_in_prices))
if len(missing_in_prices) <= 20:
    for name in missing_in_prices:
        print('  - %s' % name)
else:
    print('  First 20:')
    for name in list(missing_in_prices)[:20]:
        print('  - %s' % name)

extra_in_prices = set(prices_data.keys()) - set(items_data.keys())
print('\nwm_prices.db has %d extra records' % len(extra_in_prices))
