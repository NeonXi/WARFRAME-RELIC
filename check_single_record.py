
import sqlite3
import os

data_dir = os.path.join(os.path.dirname(__file__), 'data')
wm_prices_db = os.path.join(data_dir, 'wm_prices.db')

conn = sqlite3.connect(wm_prices_db)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute('SELECT * FROM item_prices')
rows = cursor.fetchall()

print('wm_prices.db 中的记录:')
for row in rows:
    print(dict(row))

conn.close()
