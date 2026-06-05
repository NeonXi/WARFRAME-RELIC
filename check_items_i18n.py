
import sqlite3
import os

data_dir = os.path.join(os.path.dirname(__file__), 'data')
items_db_path = os.path.join(data_dir, 'items_i18n.db')

conn = sqlite3.connect(items_db_path)
cursor = conn.cursor()

print('items_i18n.db 表结构:')
cursor.execute('PRAGMA table_info(items)')
for row in cursor.fetchall():
    print(row)

print('\nitems_i18n.db 前5条记录:')
cursor.execute('SELECT * FROM items LIMIT 5')
for row in cursor.fetchall():
    print(row)

conn.close()
