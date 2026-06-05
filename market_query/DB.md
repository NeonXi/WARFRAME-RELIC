# WARFRAME-RELIC 数据库文档

## 概述

market_query 使用本地 SQLite 数据库存储物品信息，支持离线搜索与快速查询。数据库文件位于 `data/` 目录。

## 库文件清单

| 数据库 | 路径 | 用途 |
|--------|------|------|
| **wm_items.db** | `data/wm_items.db` | 主数据库：物品名称、Slug、可交易状态 |

## wm_items.db 主数据库

### 表结构：`items`

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| **id** | INTEGER | PK | 自增 | 主键 |
| **slug** | TEXT | NOT NULL | - | warframe.market 物品唯一标识（如 `bite`） |
| **en_name** | TEXT | - | - | 英文名称 |
| **zh_name** | TEXT | - | - | 中文名称 |
| **game_ref** | TEXT | - | - | 游戏内引用 ID |
| **item_type** | TEXT | - | - | 物品类型 |
| **is_tradable** | INTEGER | - | 1 | 是否可交易（0=否, 1=是） |
| **is_prime** | INTEGER | - | 0 | 是否为 Prime 物品 |
| **zh_pinyin** | TEXT | - | - | 中文拼音（用于拼音搜索） |
| **original_is_tradable** | INTEGER | - | - | 原始可交易状态（修正前） |

### 索引建议

```sql
-- 搜索加速
CREATE INDEX IF NOT EXISTS idx_en_name ON items(en_name);
CREATE INDEX IF NOT EXISTS idx_zh_pinyin ON items(zh_pinyin);
CREATE INDEX IF NOT EXISTS idx_is_tradable ON items(is_tradable);
```

### 查询示例

```sql
-- 搜索：中文/英文/拼音模糊匹配
SELECT * FROM items 
WHERE (zh_name LIKE '%咬%' OR en_name LIKE '%bite%' OR zh_pinyin LIKE '%bite%')
AND is_tradable = 1
ORDER BY 
    CASE WHEN zh_name LIKE '%一套%' OR en_name LIKE '%Set%' THEN 0 ELSE 1 END,
    CASE WHEN zh_name LIKE '%蓝图%' OR en_name LIKE '%Blueprint%' THEN 0 ELSE 1 END,
    zh_name
LIMIT 20;

-- 通过英文名查找 Slug
SELECT slug FROM items WHERE en_name = 'Bite';

-- 统计信息
SELECT 
    COUNT(*) AS total,
    SUM(CASE WHEN is_tradable = 1 THEN 1 ELSE 0 END) AS tradable,
    SUM(CASE WHEN zh_name != '' THEN 1 ELSE 0 END) AS with_zh,
    SUM(CASE WHEN zh_pinyin != '' THEN 1 ELSE 0 END) AS with_pinyin
FROM items;
```

### 搜索排除规则

搜索时自动排除以下非交易装饰品类：

| 类别 | 中文关键词 | 英文关键词 |
|------|-----------|-----------|
| 浮印 | 浮印 | Glyph |
| 外观 | 外观 | Skin |
| 皮肤 | - | Animation |
| 头盔 | - | Helmet |
| 遗物 | 遗物 | - |
| 摇头娃娃 | 摇头娃娃 | - |
| 披饰 | 披饰 | - |
| 站姿 | 站姿 | - |

### 可交易状态修正规则

`db_updater.py` 使用以下规则自动修正被错误标记的 `is_tradable` 字段：

| 规则 | 匹配条件 | 操作 |
|------|---------|------|
| 武器部件 | 名称含 Barrel/Receiver/Stock/枪管/枪机/枪托 | 设为可交易 |
| 蓝图 | 名称含 Blueprint/蓝图 | 设为可交易 |
| 套装 | 名称含 Set/一套 | 设为可交易 |

## 数据生成流程

```
WM API (items list)
    ↓
sqlite 写入 wm_items.db
    ↓
db_updater 修正 is_tradable
    ↓
zh_pinyin 生成（pypinyin 库）
    ↓
最终可用数据库
```

## 维护建议

1. **定期更新**：每次 WM 大版本更新后，重新同步数据库
2. **验证可交易状态**：新物品入库后运行 `db_updater.py` 检查修正
3. **备份**：更新前备份 `wm_items.db`，防止数据丢失
4. **索引维护**：数据库体积增大后，建议添加上述索引以提升查询性能