import sqlite3

# Check items_i18n.db structure
conn = sqlite3.connect('../data/items_i18n.db')
cursor = conn.cursor()

# Get table info
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in items_i18n.db:")
for table in tables:
    print(f"  - {table[0]}")

# Get columns for items table
cursor.execute("PRAGMA table_info(items);")
columns = cursor.fetchall()
print("\nColumns in 'items' table:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

# Check sample data
cursor.execute("SELECT zh_name, en_name FROM items LIMIT 5;")
print("\nSample data:")
for row in cursor.fetchall():
    print(f"  {row[0]} -> {row[1]}")

# Count records
cursor.execute("SELECT COUNT(*) FROM items;")
count = cursor.fetchone()[0]
print(f"\nTotal items in database: {count}")

conn.close()
