# Warframe 统一数据库文档

> 数据库文件：`data/warframe.db`（SQLite 3，约 124 MB）
> 构建脚本：`data/build_warframe_db.py`

---

## 概述

`warframe.db` 是从多个 JSON 源文件整合而成的统一数据库，包含 Warframe 游戏中的全量物品、遗物、掉落、翻译等数据。

### 数据源

| 源文件 | 来源仓库 | 说明 |
|--------|----------|------|
| `All.json` | warframe-items | 全量物品数据（16,629 条） |
| `i18n.json` | warframe-items | 物品多语言翻译（14 种语言，232,568 条） |
| `all.json` | warframe-drop-data | DE 官方掉落数据 |
| `dict.en.json` / `dict.zh.json` | warframe-i18n | 游戏术语翻译（35,381 条） |

### 统计

- **25 张表**，总计约 **399,711 条记录**
- 14 种语言翻译（de / es / fr / it / ja / ko / pl / pt / ru / tc / th / tr / uk / zh）
- 755 个去重遗物（36 个出库，719 个入库）
- 外键关联 + 级联删除，50+ 索引优化查询

---

## 表结构详解

### 一、核心物品表（5 张）

#### 1. items — 全物品主表

全量物品数据的主表，每条记录对应一个唯一的游戏物品。

| 字段 | 类型 | 说明 |
|------|------|------|
| `unique_name` | TEXT PK | 游戏内部唯一标识，如 `/Lotus/Weapons/Tenno/LongGuns/SapientPrimary/SapientPrimaryWeapon` |
| `name` | TEXT NOT NULL | 英文名称 |
| `zh_name` | TEXT | 中文名称（从 i18n 回填） |
| `type` | TEXT NOT NULL | 物品类型（Warframe / Primary / Melee / Mod / Glyph 等） |
| `category` | TEXT | 分类（All / Melee / Primary / Mods 等） |
| `tradable` | INTEGER | 是否可交易（0/1） |
| `masterable` | INTEGER | 是否可专精（0/1） |
| `is_prime` | INTEGER | 是否 Prime 版本（0/1） |
| `description` | TEXT | 英文描述 |
| `description_zh` | TEXT | 中文描述（从 i18n 回填） |
| `image_name` | TEXT | 图片文件名 |
| `exclude_from_codex` | INTEGER | 是否从图鉴排除（0/1） |
| `show_in_inventory` | INTEGER | 是否在库存显示（0/1，默认 1） |
| `build_price` | INTEGER | 制造价格（星币） |
| `build_time` | INTEGER | 制造时间（秒） |
| `skip_build_time_price` | INTEGER | 加速制造费用（白金） |
| `build_quantity` | INTEGER | 制造数量（默认 1） |
| `consume_on_build` | INTEGER | 制造时是否消耗（0/1，默认 1） |
| `market_cost` | INTEGER | 商店售价（白金） |
| `bp_cost` | INTEGER | 蓝图售价（白金） |
| `introduced` | TEXT | 引入版本信息 |
| `release_date` | TEXT | 发布日期 |
| `wikia_url` | TEXT | Wiki 页面 URL |
| `wiki_available` | INTEGER | Wiki 是否可用（0/1） |

**索引**：name / zh_name / type / category / tradable / is_prime

**记录数**：16,629

---

#### 2. item_type_attrs — 类型专属属性表

不同类型物品的扩展属性，以 JSON 格式存储。每种物品类型有不同的属性集。

| 字段 | 类型 | 说明 |
|------|------|------|
| `unique_name` | TEXT PK | 关联 items.unique_name |
| `type` | TEXT NOT NULL | 物品类型 |
| `attrs` | TEXT NOT NULL | JSON 格式的类型专属属性 |

**常见 type 及其 attrs 内容**：

| type | attrs 示例字段 |
|------|----------------|
| Warframe | health, shield, armor, energy, sprintSpeed, stancePolarity |
| Primary / Secondary | noiseLevel, accuracy, magazineSize, reloadTime, fireRate, ammo |
| Melee | stancePolarity, totalDamage, blockAngle, comboDuration, slamAttack |
| Mod | baseDrain, fusionLimit, polarity, compatibilityTags |
| Arcane | rarity, attunementCost |
| Relic | tier, relicName, vaulted |
| Node | systemIndex, systemName, masteryReq, missionIndex, factionIndex |

**记录数**：6,907

---

#### 3. item_abilities — 技能表

Warframe 和 Archwing 的技能数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `unique_name` | TEXT NOT NULL | 关联 items.unique_name |
| `ability_index` | INTEGER NOT NULL | 技能序号（0-3） |
| `ability_unique` | TEXT | 技能内部标识 |
| `name` | TEXT NOT NULL | 技能名称 |
| `description` | TEXT | 技能描述 |
| `image_name` | TEXT | 技能图标 |

**唯一约束**：(unique_name, ability_index)

**记录数**：501

---

#### 4. item_attacks — 攻击模式表

武器的攻击模式数据，一把武器可以有多个攻击模式。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `unique_name` | TEXT NOT NULL | 关联 items.unique_name |
| `attack_index` | INTEGER NOT NULL | 攻击模式序号 |
| `attack_name` | TEXT | 攻击名称（如 "Rocket Impact"） |
| `crit_chance` | REAL | 暴击率（百分比） |
| `crit_mult` | REAL | 暴击倍率 |
| `status_chance` | REAL | 触发率（百分比） |
| `shot_type` | TEXT | 射击类型（Projectile / HitScan / Throw 等） |
| `speed` | REAL | 攻击速度 / 射速 |
| `charge_time` | REAL | 蓄力时间（秒） |
| `damage_json` | TEXT | 伤害分布 JSON，如 `{"impact": 35, "puncture": 10}` |
| `pellet_count` | INTEGER | 弹丸数量（默认 1） |

**唯一约束**：(unique_name, attack_index)

**记录数**：1,779

---

#### 5. item_components — 制造组件表

物品的制造配方，记录每个物品需要哪些组件。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `parent_name` | TEXT NOT NULL | 父物品 unique_name |
| `component_name` | TEXT NOT NULL | 组件名称（如 "Blueprint" / "Neuroptics"） |
| `component_unique` | TEXT | 组件 unique_name |
| `item_count` | INTEGER | 所需数量（默认 1） |
| `tradable` | INTEGER | 组件是否可交易（0/1） |
| `image_name` | TEXT | 组件图标 |

**记录数**：5,969

---

### 二、物品关联表（3 张）

#### 6. item_drops — 物品掉落来源表

物品的掉落来源信息（来自 All.json 的 drops[] 字段）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `unique_name` | TEXT NOT NULL | 关联 items.unique_name |
| `drop_type` | TEXT | 掉落类型 |
| `location` | TEXT NOT NULL | 掉落位置/来源 |
| `rarity` | TEXT | 稀有度（Common / Uncommon / Rare） |
| `chance` | REAL | 掉落概率（百分比） |

**记录数**：44,700

---

#### 7. item_patchlogs — 更新日志表

物品的版本更新记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `unique_name` | TEXT NOT NULL | 关联 items.unique_name |
| `patch_name` | TEXT | 更新名称（如 "Veilbreaker: Update 32"） |
| `patch_date` | TEXT | 更新日期（ISO 格式） |
| `patch_url` | TEXT | 更新公告 URL |
| `additions` | TEXT | 新增内容 |
| `changes` | TEXT | 变更内容 |
| `fixes` | TEXT | 修复内容 |

**记录数**：32,129

---

#### 8. item_translations — 多语言翻译表

物品名称和描述的 14 种语言翻译。

| 字段 | 类型 | 说明 |
|------|------|------|
| `unique_name` | TEXT NOT NULL | 关联 items.unique_name |
| `lang` | TEXT NOT NULL | 语言代码（de / es / fr / it / ja / ko / pl / pt / ru / tc / th / tr / uk / zh） |
| `name` | TEXT | 该语言的物品名称 |
| `description` | TEXT | 该语言的物品描述 |

**主键**：(unique_name, lang)

**支持语言**：de（德语）/ es（西班牙语）/ fr（法语）/ it（意大利语）/ ja（日语）/ ko（韩语）/ pl（波兰语）/ pt（葡萄牙语）/ ru（俄语）/ tc（繁体中文）/ th（泰语）/ tr（土耳其语）/ uk（乌克兰语）/ zh（简体中文）

**记录数**：232,568（每种语言约 16,612 条）

---

### 三、遗物表（2 张）

#### 9. relics — 遗物表

所有遗物数据，同一遗物的 4 个精炼状态各占一行。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `tier` | TEXT NOT NULL | 纪元（Lith / Meso / Neo / Axi） |
| `relic_name` | TEXT NOT NULL | 遗物编号（如 "A1" / "C7"） |
| `state` | TEXT NOT NULL | 精炼状态（Intact / Exceptional / Flawless / Radiant） |
| `vaulted` | INTEGER | 是否入库（0=出库，1=入库） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**唯一约束**：(tier, relic_name, state)

**vaulted 判定逻辑**：从 All.json 中遗物类物品的 `vaulted` 字段提取，同一遗物 4 个 state 共享 vaulted 状态。

**统计**：3,014 行 = 755 个去重遗物 × 4 个状态（36 个出库，719 个入库）

**索引**：tier / vaulted / (tier, relic_name)

---

#### 10. relic_rewards — 遗物奖励表

每个遗物精炼状态下可能开出的物品。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `relic_id` | INTEGER NOT NULL | 关联 relics.id |
| `item_name` | TEXT NOT NULL | 物品英文名称 |
| `item_unique` | TEXT | 物品 unique_name |
| `rarity` | TEXT NOT NULL | 稀有度（Common / Uncommon / Rare） |
| `chance` | REAL NOT NULL | 掉落概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |
| `wm_url_name` | TEXT | Warframe Market URL 标识 |

**掉落概率参考**（Intact / Radiant）：

| 稀有度 | Intact | Radiant |
|--------|--------|---------|
| Common ×3 | 25.33% | 20.00% |
| Uncommon ×2 | 11.00% | 16.67% |
| Rare ×1 | 2.00% | 10.00% |

**记录数**：18,086

---

### 四、任务掉落表（3 张）

#### 11. planets — 星球表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `name` | TEXT NOT NULL UNIQUE | 星球名称（Mercury / Venus / Earth 等） |

**记录数**：24

---

#### 12. mission_nodes — 任务节点表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `planet_id` | INTEGER NOT NULL | 关联 planets.id |
| `node_name` | TEXT NOT NULL | 节点名称（如 "Apollodorus"） |
| `game_mode` | TEXT | 游戏模式（Survival / Defense / Excavation 等） |
| `is_event` | INTEGER | 是否为活动节点（0/1） |

**唯一约束**：(planet_id, node_name)

**记录数**：431

---

#### 13. mission_rewards — 任务奖励表

任务节点的掉落奖励，含轮次（A/B/C）信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `node_id` | INTEGER NOT NULL | 关联 mission_nodes.id |
| `rotation` | TEXT | 轮次（A / B / C） |
| `item_name` | TEXT NOT NULL | 物品名称 |
| `item_unique` | TEXT | 物品 unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 掉落概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：10,287

---

### 五、Mod 掉落表（2 张）

#### 14. mod_drops — Mod 掉落表

按 Mod 维度查看哪些敌人掉落该 Mod。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `mod_name` | TEXT NOT NULL | Mod 名称 |
| `mod_unique` | TEXT | Mod unique_name |
| `enemy_name` | TEXT NOT NULL | 敌人名称 |
| `enemy_mod_drop_chance` | REAL | 敌人 Mod 掉落总概率（百分比） |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 该 Mod 在掉落中的概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：6,494

---

#### 15. enemy_mod_tables — 敌人 Mod 掉落表

按敌人维度查看该敌人掉落哪些 Mod。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `enemy_name` | TEXT NOT NULL | 敌人名称 |
| `enemy_mod_drop_chance` | REAL | 敌人 Mod 掉落总概率（百分比） |
| `mod_name` | TEXT NOT NULL | Mod 名称 |
| `mod_unique` | TEXT | Mod unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 该 Mod 在掉落中的概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**与 mod_drops 的区别**：两者数据来源相同（all.json modLocations），但视角不同。mod_drops 以 Mod 为主键查询，enemy_mod_tables 以敌人为主键查询。

**记录数**：6,517

---

### 六、蓝图掉落表（2 张）

#### 16. blueprint_drops — 蓝图掉落表

按蓝图维度查看哪些敌人掉落该蓝图。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `blueprint_name` | TEXT NOT NULL | 蓝图名称 |
| `blueprint_unique` | TEXT | 蓝图 unique_name |
| `enemy_name` | TEXT NOT NULL | 敌人名称 |
| `enemy_bp_drop_chance` | REAL | 敌人蓝图掉落总概率（百分比） |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 该蓝图在掉落中的概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：311

---

#### 17. enemy_bp_tables — 敌人蓝图掉落表

按敌人维度查看该敌人掉落哪些蓝图。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `enemy_name` | TEXT NOT NULL | 敌人名称 |
| `enemy_bp_drop_chance` | REAL | 敌人蓝图掉落总概率（百分比） |
| `blueprint_name` | TEXT NOT NULL | 蓝图名称 |
| `blueprint_unique` | TEXT | 蓝图 unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 该蓝图在掉落中的概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：311

---

### 七、特殊奖励表（5 张）

#### 18. sortie_rewards — 突击奖励表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `item_name` | TEXT NOT NULL | 物品名称 |
| `item_unique` | TEXT | 物品 unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 掉落概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：17

---

#### 19. bounty_rewards — 赏金奖励表

包含所有开放世界的赏金任务奖励。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `source` | TEXT NOT NULL | 来源（Cetus / Solaris / Deimos / Zariman / EntratiLab / Hex） |
| `bounty_level` | TEXT | 赏金等级 |
| `rotation` | TEXT | 轮次 |
| `item_name` | TEXT NOT NULL | 物品名称 |
| `item_unique` | TEXT | 物品 unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 掉落概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：2,221

---

#### 20. transient_rewards — 临时奖励表

仲裁、噩梦等特殊任务的奖励。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `objective_name` | TEXT NOT NULL | 目标名称（如 "Arbitrations"） |
| `rotation` | TEXT | 轮次（A / B / C） |
| `item_name` | TEXT NOT NULL | 物品名称 |
| `item_unique` | TEXT | 物品 unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 掉落概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：744

---

#### 21. key_rewards — 钥匙奖励表

钥匙任务的奖励。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `key_name` | TEXT NOT NULL | 钥匙/任务名称 |
| `rotation` | TEXT | 轮次 |
| `item_name` | TEXT NOT NULL | 物品名称 |
| `item_unique` | TEXT | 物品 unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 掉落概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：108

---

#### 22. syndicate_rewards — 集团奖励表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `syndicate_name` | TEXT NOT NULL | 集团名称（Steel Meridian / Arbiters of Hexis 等） |
| `rotation` | TEXT | 集团等级/轮次 |
| `item_name` | TEXT NOT NULL | 物品名称 |
| `item_unique` | TEXT | 物品 unique_name |
| `rarity` | TEXT | 稀有度 |
| `chance` | REAL | 掉落概率（百分比） |
| `drop_data_id` | TEXT | 掉落数据 ID |

**记录数**：1,707

---

### 八、翻译表（1 张）

#### 23. game_translations — 游戏术语翻译表

游戏内通用术语的中英文对照，来源于 warframe-i18n 仓库。

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | TEXT PK | 术语内部键 |
| `en` | TEXT NOT NULL | 英文术语 |
| `zh` | TEXT | 中文术语 |
| `category` | TEXT | 分类（如 UI / Weapons / Warframes 等） |
| `source` | TEXT | 数据来源（默认 "public-export-plus"） |

**记录数**：35,381

---

### 九、市场表（1 张）

#### 24. market_items — 市场物品映射表

Warframe Market 的物品映射，用于对接市场交易数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | Market 物品 ID |
| `slug` | TEXT NOT NULL UNIQUE | URL 标识（如 "akstiletto_prime_barrel"） |
| `en_name` | TEXT NOT NULL | 英文名称 |
| `zh_name` | TEXT | 中文名称 |
| `item_unique` | TEXT | 关联 items.unique_name |
| `item_type` | TEXT | 物品类型 |
| `is_tradable` | INTEGER | 是否可交易（0/1） |
| `is_prime` | INTEGER | 是否 Prime（0/1） |
| `zh_pinyin` | TEXT | 中文名称拼音 |

**记录数**：5,104（由 `build_market_items.py` 从 items 表中 tradable=1 的物品本地生成，不依赖 WM API）

---

### 十、元数据表（1 张）

#### 25. db_meta — 元数据表

数据库构建的元信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | TEXT PK | 键名 |
| `value` | TEXT NOT NULL | 值 |

**预设记录**：

| key | value 示例 | 说明 |
|-----|-----------|------|
| `build_version` | 1 | 数据库版本号 |
| `build_time` | 2026-01-01T00:00:00 | 构建时间 |
| `build_elapsed_sec` | 5.2 | 构建耗时（秒） |

**记录数**：3

---

## 表关系图

```
items (主表)
 ├── item_type_attrs    (1:1, unique_name)
 ├── item_abilities     (1:N, unique_name)
 ├── item_attacks       (1:N, unique_name)
 ├── item_components    (1:N, parent_name → unique_name)
 ├── item_drops         (1:N, unique_name)
 ├── item_patchlogs     (1:N, unique_name)
 └── item_translations  (1:N, unique_name + lang)

relics
 └── relic_rewards      (1:N, relic_id → id)

planets
 └── mission_nodes      (1:N, planet_id → id)
      └── mission_rewards (1:N, node_id → id)

独立表（无外键关联）：
  mod_drops / enemy_mod_tables
  blueprint_drops / enemy_bp_tables
  sortie_rewards / bounty_rewards / transient_rewards
  key_rewards / syndicate_rewards
  game_translations / market_items / db_meta
```

---

## 常用查询示例

### 查询遗物中包含的所有去重物品

```sql
SELECT DISTINCT item_name, item_unique
FROM relic_rewards
WHERE item_unique != ''
ORDER BY item_name;
```

### 查询某物品出现在哪些遗物中

```sql
SELECT r.tier, r.relic_name, r.state, rw.rarity, rw.chance
FROM relic_rewards rw
JOIN relics r ON rw.relic_id = r.id
WHERE rw.item_name = 'Forma Blueprint'
ORDER BY r.tier, r.relic_name, r.state;
```

### 查询所有出库遗物

```sql
SELECT DISTINCT tier, relic_name
FROM relics
WHERE vaulted = 0
ORDER BY tier, relic_name;
```

### 查询某星球的生存任务奖励

```sql
SELECT mn.node_name, mr.rotation, mr.item_name, mr.rarity, mr.chance
FROM mission_rewards mr
JOIN mission_nodes mn ON mr.node_id = mn.id
JOIN planets p ON mn.planet_id = p.id
WHERE p.name = 'Venus' AND mn.game_mode = 'Survival'
ORDER BY mn.node_name, mr.rotation, mr.chance DESC;
```

### 查询某 Mod 的掉落来源

```sql
SELECT enemy_name, enemy_mod_drop_chance, rarity, chance
FROM mod_drops
WHERE mod_name = 'Target Acquired'
ORDER BY chance DESC;
```

### 查询某物品的中文信息

```sql
SELECT i.name, i.zh_name, i.type, t.description AS zh_desc
FROM items i
LEFT JOIN item_translations t ON i.unique_name = t.unique_name AND t.lang = 'zh'
WHERE i.name LIKE '%Excalibur%';
```

### 查询 Prime 物品及其制造组件

```sql
SELECT i.name, i.zh_name, c.component_name, c.item_count, c.tradable
FROM items i
JOIN item_components c ON i.unique_name = c.parent_name
WHERE i.is_prime = 1 AND i.type = 'Warframe'
ORDER BY i.name, c.component_name;
```

---

## 构建与更新

### 构建

```bash
python data/build_warframe_db.py
```

构建过程：
1. 创建 25 张表及索引
2. 解析 All.json → items + 6 张子表
3. 解析 i18n.json → item_translations + 中文回填
4. 解析 all.json → 遗物/任务/敌人/特殊奖励 5 组
5. 解析 dict → game_translations
6. 写入元数据 + VACUUM 优化
7. 构建 market_items 表（由 `build_market_items.py` 从 items 表本地生成，不依赖 WM API）

### 数据流水线

通过 `data_pipeline.py` 统一编排，流程如下：

1. Git 稀疏检出源数据（3 个上游仓库 → external/）
2. 构建统一数据库 warframe.db（含 market_items 表）

> 市场价格通过 `core/price_service.py` 实时查询 warframe.market API，不再缓存到本地数据库。

### 数据库参数

- **journal_mode**：WAL（Write-Ahead Logging）
- **foreign_keys**：ON（启用外键约束）
- **VACUUM**：构建完成后执行，压缩数据库文件
