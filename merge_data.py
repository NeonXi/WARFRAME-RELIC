
import sqlite3
import os
from datetime import datetime

data_dir = os.path.join(os.path.dirname(__file__), 'data')
wm_items_db = os.path.join(data_dir, 'wm_items.db')
wm_prices_db = os.path.join(data_dir, 'wm_prices.db')

print('=' * 60)
print('数据合并')
print('=' * 60)

# 备份原数据库
backup_name = 'wm_prices.db.backup.%s' % datetime.now().strftime('%Y%m%d_%H%M%S')
backup_path = os.path.join(data_dir, backup_name)
import shutil
shutil.copy2(wm_prices_db, backup_path)
print('\n已备份 wm_prices.db 到: %s' % backup_name)

# 读取 wm_items.db
conn1 = sqlite3.connect(wm_items_db)
conn1.row_factory = sqlite3.Row
cursor1 = conn1.cursor()
cursor1.execute('SELECT en_name, slug FROM items')
items_data = {row['slug']: row['en_name'] for row in cursor1.fetchall()}
conn1.close()

# 连接 wm_prices.db
conn2 = sqlite3.connect(wm_prices_db)
cursor2 = conn2.cursor()

# 先查看现状
cursor2.execute('SELECT COUNT(*) FROM item_prices')
total_count = cursor2.fetchone()[0]
cursor2.execute('SELECT COUNT(*) FROM item_prices WHERE en_name IS NULL OR en_name = ""')
missing_en_name = cursor2.fetchone()[0]

print('wm_prices.db 总记录: %d' % total_count)
print('en_name 为空的记录: %d' % missing_en_name)

# 更新记录
updated = 0
added = 0
cursor2.execute('SELECT item_id, slug, en_name FROM item_prices')
for row in cursor2.fetchall():
    item_id, slug, current_en_name = row
    
    if slug in items_data:
        en_name = items_data[slug]
        if not current_en_name or current_en_name == '':
            cursor2.execute(
                'UPDATE item_prices SET en_name = ? WHERE item_id = ?',
                (en_name, item_id)
            )
            updated += 1

# 检查是否有 slug 存在于 wm_items.db 但没有在 wm_prices.db 中
cursor2.execute('SELECT slug FROM item_prices')
existing_slugs = set(row[0] for row in cursor2.fetchall())

# 对于 wm_items.db 中但 wm_prices.db 中没有的 slug，我们需要新增
new_slugs = 0
for slug, en_name in items_data.items():
    if slug not in existing_slugs:
        # 没有价格数据，我们只插入基础信息
        cursor2.execute('''
            INSERT OR IGNORE INTO item_prices 
            (item_id, slug, en_name, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (
            abs(hash(slug)) % 100000000,  # 临时 item_id
            slug,
            en_name,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        if cursor2.rowcount > 0:
            new_slugs += 1

conn2.commit()
conn2.close()

print('\n更新了 %d 条记录的 en_name' % updated)
print('新增了 %d 条记录' % new_slugs)
print('数据合并完成!')
