
import sqlite3
import os
from pathlib import Path

def analyze_database(db_path):
    print(f"\n{'='*60}")
    print(f"分析数据库: {os.path.basename(db_path)}")
    print(f"{'='*60}")
    
    file_size = os.path.getsize(db_path)
    print(f"文件大小: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = cursor.fetchall()
    
    print(f"\n表数量: {len(tables)}")
    
    for (table_name,) in tables:
        print(f"\n--- 表: {table_name} ---")
        
        # 获取行数
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        row_count = cursor.fetchone()[0]
        print(f"  行数: {row_count:,}")
        
        # 获取表结构
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        print(f"  列数: {len(columns)}")
        
        # 显示列信息
        for col in columns:
            col_id, name, ctype, notnull, default, pk = col
            pk_str = " (PK)" if pk else ""
            print(f"    {name}: {ctype}{pk_str}")
        
        # 获取索引
        cursor.execute(f"PRAGMA index_list({table_name});")
        indexes = cursor.fetchall()
        print(f"  索引数: {len(indexes)}")
        
        for idx in indexes:
            idx_seq, idx_name, unique, origin, partial = idx
            unique_str = " (UNIQUE)" if unique else ""
            cursor.execute(f"PRAGMA index_info({idx_name});")
            idx_cols = cursor.fetchall()
            col_names = ", ".join([col[2] for col in idx_cols])
            print(f"    {idx_name}: {col_names}{unique_str}")
        
        # 估算表大小（粗略）
        cursor.execute(f"SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size();")
        db_size = cursor.fetchone()[0]
        print(f"  数据库总页数大小: {db_size:,} bytes")
    
    # 获取数据库配置
    print(f"\n数据库配置:")
    cursor.execute("PRAGMA journal_mode;")
    journal_mode = cursor.fetchone()[0]
    print(f"  journal_mode: {journal_mode}")
    
    cursor.execute("PRAGMA synchronous;")
    synchronous = cursor.fetchone()[0]
    print(f"  synchronous: {synchronous}")
    
    cursor.execute("PRAGMA cache_size;")
    cache_size = cursor.fetchone()[0]
    print(f"  cache_size: {cache_size}")
    
    conn.close()
    print()

def main():
    data_dir = Path(__file__).parent / "data"
    
    db_files = list(data_dir.glob("*.db"))
    
    for db_file in sorted(db_files):
        analyze_database(str(db_file))

if __name__ == "__main__":
    main()
