"""
WARFRAME 物品数据库更新工具
提供智能的可交易状态修正功能
"""

import sqlite3
import os

class ItemDatabaseUpdater:
    """智能数据库更新器"""
    
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'warframe.db')
        self.db_path = db_path
        
    def connect(self):
        """连接数据库"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def analyze_tradable_status(self):
        """分析当前数据库中可能有误的可交易状态"""
        conn = self.connect()
        cursor = conn.cursor()
        
        # 找出可能被错误标记为不可交易的物品
        cursor.execute("""
            SELECT en_name, zh_name, slug, is_tradable 
            FROM items 
            WHERE is_tradable = 0
              AND (
                en_name LIKE '%Barrel%' OR en_name LIKE '%Receiver%' OR en_name LIKE '%Stock%' OR
                en_name LIKE '%Blueprint%' OR en_name LIKE '%Set%' OR
                zh_name LIKE '%枪管%' OR zh_name LIKE '%枪机%' OR zh_name LIKE '%枪托%' OR
                zh_name LIKE '%蓝图%' OR zh_name LIKE '%一套%'
              )
            ORDER BY en_name
        """)
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def fix_tradable_status(self, dry_run=True):
        """自动修正可交易状态"""
        conn = self.connect()
        cursor = conn.cursor()
        
        # 规则1: 武器部件（枪管、枪机、枪托）应该可交易
        rule1_query = """
            UPDATE items 
            SET is_tradable = 1 
            WHERE is_tradable = 0
              AND (en_name LIKE '%Barrel%' OR en_name LIKE '%Receiver%' OR en_name LIKE '%Stock%'
                   OR zh_name LIKE '%枪管%' OR zh_name LIKE '%枪机%' OR zh_name LIKE '%枪托%')
        """
        
        # 规则2: 蓝图应该可交易
        rule2_query = """
            UPDATE items 
            SET is_tradable = 1 
            WHERE is_tradable = 0
              AND (en_name LIKE '%Blueprint%' OR zh_name LIKE '%蓝图%')
        """
        
        # 规则3: 套装应该可交易
        rule3_query = """
            UPDATE items 
            SET is_tradable = 1 
            WHERE is_tradable = 0
              AND (en_name LIKE '%Set%' OR zh_name LIKE '%一套%')
        """
        
        if dry_run:
            # 只统计不执行
            cursor.execute("""
                SELECT COUNT(*) 
                FROM items 
                WHERE is_tradable = 0
                  AND (en_name LIKE '%Barrel%' OR en_name LIKE '%Receiver%' OR en_name LIKE '%Stock%'
                       OR zh_name LIKE '%枪管%' OR zh_name LIKE '%枪机%' OR zh_name LIKE '%枪托%')
            """)
            rule1_count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM items 
                WHERE is_tradable = 0
                  AND (en_name LIKE '%Blueprint%' OR zh_name LIKE '%蓝图%')
            """)
            rule2_count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM items 
                WHERE is_tradable = 0
                  AND (en_name LIKE '%Set%' OR zh_name LIKE '%一套%')
            """)
            rule3_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'rule1_weapon_parts': rule1_count,
                'rule2_blueprints': rule2_count,
                'rule3_sets': rule3_count,
                'total': rule1_count + rule2_count + rule3_count
            }
        
        else:
            # 执行修复
            cursor.execute(rule1_query)
            rule1_count = cursor.rowcount
            
            cursor.execute(rule2_query)
            rule2_count = cursor.rowcount
            
            cursor.execute(rule3_query)
            rule3_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return {
                'rule1_weapon_parts': rule1_count,
                'rule2_blueprints': rule2_count,
                'rule3_sets': rule3_count,
                'total': rule1_count + rule2_count + rule3_count
            }
    
    def update_database_from_api(self, api_data):
        """从 API 数据更新数据库，并自动应用修正规则"""
        conn = self.connect()
        cursor = conn.cursor()
        
        for item in api_data:
            # 先插入/更新数据
            cursor.execute("""
                INSERT OR REPLACE INTO items 
                (slug, en_name, zh_name, is_tradable, zh_pinyin)
                VALUES (?, ?, ?, ?, ?)
            """, (
                item.get('slug', ''),
                item.get('en_name', ''),
                item.get('zh_name', ''),
                item.get('is_tradable', 0),
                item.get('zh_pinyin', '')
            ))
        
        conn.commit()
        
        # 应用修正规则
        fix_result = self.fix_tradable_status(dry_run=False)
        
        conn.close()
        return fix_result
    
    def get_statistics(self):
        """获取数据库统计信息"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM items")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM items WHERE is_tradable = 1")
        tradable = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM items WHERE zh_name != ''")
        with_zh = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM items WHERE zh_pinyin != ''")
        with_pinyin = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_items': total,
            'tradable_items': tradable,
            'with_chinese_name': with_zh,
            'with_pinyin': with_pinyin
        }


def main():
    """命令行工具入口"""
    updater = ItemDatabaseUpdater()
    
    print("=" * 60)
    print("WARFRAME 物品数据库更新工具")
    print("=" * 60)
    
    # 显示当前统计
    stats = updater.get_statistics()
    print("\n当前数据库统计:")
    print(f"  总物品数: {stats['total_items']}")
    print(f"  可交易物品: {stats['tradable_items']}")
    print(f"  有中文名称: {stats['with_chinese_name']}")
    print(f"  有拼音字段: {stats['with_pinyin']}")
    
    # 分析问题
    print("\n分析可能有误的可交易状态...")
    problems = updater.analyze_tradable_status()
    print(f"找到 {len(problems)} 个可能被错误标记的物品")
    
    if problems:
        print("\n预览前10个问题物品:")
        for i, item in enumerate(problems[:10]):
            en_name, zh_name, slug, is_tradable = item
            print(f"  {i+1}. {zh_name} ({en_name})")
    
    # 模拟修复
    print("\n模拟修复（不实际执行）:")
    fix_result = updater.fix_tradable_status(dry_run=True)
    print(f"  规则1-武器部件: {fix_result['rule1_weapon_parts']} 个")
    print(f"  规则2-蓝图: {fix_result['rule2_blueprints']} 个")
    print(f"  规则3-套装: {fix_result['rule3_sets']} 个")
    print(f"  总计: {fix_result['total']} 个")
    
    # 询问是否执行修复
    if fix_result['total'] > 0:
        confirm = input("\n是否执行修复? (y/n): ").strip().lower()
        if confirm == 'y':
            print("\n正在执行修复...")
            result = updater.fix_tradable_status(dry_run=False)
            print(f"已修复 {result['total']} 个物品")
            
            # 更新统计
            stats = updater.get_statistics()
            print("\n修复后统计:")
            print(f"  总物品数: {stats['total_items']}")
            print(f"  可交易物品: {stats['tradable_items']}")


if __name__ == '__main__':
    main()
