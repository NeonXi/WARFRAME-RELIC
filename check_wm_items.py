
import sqlite3
import os

data_dir = os.path.join(os.path.dirname(__file__), 'data')
wm_items_db = os.path.join(data_dir, 'wm_items.db')

if not os.path.exists(wm_items_db):
    print('wm_items.db 不存在')
else:
    print('=' * 60)
    print('wm_items.db 结构分析')
    print('=' * 60)
    
    conn = sqlite3.connect(wm_items_db)
    cursor = conn.cursor()
    
    # 获取表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    print(f'\n表数量: {len(tables)}')
    
    for (table_name,) in tables:
        print(f'\n--- 表: {table_name} ---')
        
        # 获取行数
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f'  行数: {count}')
        
        # 获取列
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = cursor.fetchall()
        print(f'  列数: {len(cols)}')
        for col in cols:
            print(f'    {col[1]} ({col[2]})')
        
        # 显示前几行
        print(f'  前 3 条数据:')
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
        rows = cursor.fetchall()
        for row in rows:
            print(f'    {row}')
    
    conn.close()
