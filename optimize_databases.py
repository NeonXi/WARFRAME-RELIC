
import sqlite3
import os
from pathlib import Path

def optimize_database(db_path):
    print(f"\n优化数据库: {os.path.basename(db_path)}")
    print("-" * 50)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取当前模式
    cursor.execute("PRAGMA journal_mode")
    current_mode = cursor.fetchone()[0]
    print(f"  当前 journal_mode: {current_mode}")
    
    # 设置 WAL 模式
    if current_mode != 'wal':
        cursor.execute("PRAGMA journal_mode=wal")
        result = cursor.fetchone()[0]
        print(f"  设置为: {result}")
    else:
        print(f"  已经是 WAL 模式，无需修改")
    
    # 设置其他优化配置
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-2000")  # 2000KB
    print(f"  synchronous 设置为 NORMAL")
    
    # 执行 VACUUM 来优化空间
    print(f"  执行 VACUUM 优化数据库...")
    conn.execute("VACUUM")
    conn.commit()
    print(f"  VACUUM 完成")
    
    # 显示优化后的大小
    new_size = os.path.getsize(db_path)
    print(f"  优化后大小: {new_size:,} bytes ({new_size/1024/1024:.2f} MB)")
    
    conn.close()
    print(f"  ✓ 优化完成\n")

def main():
    data_dir = Path(__file__).parent / "data"
    
    db_files = []
    for db_file in sorted(data_dir.glob("*.db")):
        db_files.append(str(db_file))
    
    print(f"找到 {len(db_files)} 个数据库文件")
    print(f"开始优化...\n")
    
    for db_path in db_files:
        optimize_database(db_path)
    
    print("=" * 50)
    print("所有数据库优化完成！")

if __name__ == "__main__":
    main()
