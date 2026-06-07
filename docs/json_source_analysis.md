# WARFRAME-RELIC JSON 源文件深度解析

> 本文档深度分析 `external/` 目录下所有 JSON 源文件的嵌套结构、字段含义和数据关系。

---

## 目录

1. [warframe-items / All.json](#1-warframe-items--alljson)
2. [warframe-items / Relics.json](#2-warframe-items--relicsjson)
3. [warframe-items / i18n.json](#3-warframe-items--i18njson)
4. [warframe-drop-data / all.json](#4-warframe-drop-data--alljson)
5. [warframe-i18n / dict.en.json & dict.zh.json](#5-warframe-i18n--dictenjson--dictzhjson)
6. [跨文件关联关系](#6-跨文件关联关系)

---

## 1. warframe-items / All.json

**路径**: `external/warframe-items_sparse/data/json/All.json`
**类型**: 数组 (Array)
**长度**: 16,629 条
**说明**: Warframe 全物品数据库，包含游戏中所有可获取物品的完整信息。

### 1.1 顶层结构

```
All.json ─── Array[16629]
              ├── [0] { Item Object }
              ├── [1] { Item Object }
              └── ...
```

每个元素是一个物品对象，通过 `type` 字段区分物品类型。共有 **357 种不同的字段组合**，这是因为不同类型的物品拥有不同的属性集。

### 1.2 通用字段（所有物品共有）

| 字段 | 类型 | 说明 |
|------|------|------|
| `uniqueName` | string | 游戏内部唯一标识符，格式如 `/Lotus/Types/...` |
| `name` | string | 物品英文名称 |
| `type` | string | 物品类型（见下方类型列表） |
| `category` | string | 物品分类（如 Warframes、Mods、Relics 等） |
| `tradable` | boolean | 是否可交易 |
| `masterable` | boolean | 是否可精通 |

### 1.3 可选通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 物品描述文本 |
| `imageName` | string | 物品图片文件名（如 `Ash.png`） |
| `excludeFromCodex` | boolean | 是否从图鉴中排除 |
| `showInInventory` | boolean | 是否在库存中显示 |
| `patchlogs` | Array | 历史更新日志列表 |
| `drops` | Array | 掉落来源列表 |

### 1.4 物品类型 (type) 完整列表

共 **80+ 种** type，按重要性分类：

#### 战甲与同伴
| type | 说明 | 数量级 |
|------|------|--------|
| `Warframe` | 战甲 | ~90 |
| `Archwing` | 天翼 | ~10 |
| `Sentinel` | 守护 | ~30 |
| `Pets` | 宠物 | ~20 |
| `Conservation Prey` | 保育动物 | ~30 |

#### 武器
| type | 说明 | 数量级 |
|------|------|--------|
| `Rifle` | 步枪 | ~70 |
| `Shotgun` | 霰弹枪 | ~30 |
| `Pistol` | 手枪 | ~50 |
| `Dual Pistols` | 双手枪 | ~20 |
| `Melee` | 近战武器 | ~130 |
| `Bow` | 弓 | ~15 |
| `Sniper` | 狙击枪 | ~10 |
| `Launcher` | 发射器 | ~15 |
| `Throwing` | 投掷武器 | ~10 |
| `Exalted Weapon` | 显赫武器 | ~15 |
| `Arch-Gun` | 天翼枪 | ~15 |
| `Arch-Melee` | 天翼近战 | ~10 |
| `Companion Weapon` | 同伴武器 | ~20 |
| `Railjack Turret` | 火星战舰炮塔 | ~5 |
| `Amp` | 操控器 | ~10 |

#### Mod
| type | 说明 | 数量级 |
|------|------|--------|
| `Warframe Mod` | 战甲 Mod | ~300 |
| `Rifle Mod` / `Primary Mod` | 步枪 Mod | ~150 |
| `Shotgun Mod` | 霰弹 Mod | ~80 |
| `Secondary Mod` | 副武器 Mod | ~100 |
| `Melee Mod` | 近战 Mod | ~150 |
| `Pistol Mod` | 手枪 Mod | ~80 |
| `Companion Mod` | 同伴 Mod | ~100 |
| `Archwing Mod` | 天翼 Mod | ~40 |
| `Arch-Gun Mod` | 天翼枪 Mod | ~20 |
| `Arch-Melee Mod` | 天翼近战 Mod | ~15 |
| `K-Drive Mod` | 滑板 Mod | ~10 |
| `Stance Mod` | 架式 Mod | ~40 |
| `Parazon Mod` | 寄生刀 Mod | ~10 |
| `Plexus Mod` | 火星战舰 Mod | ~20 |
| `Posture Mod` | 姿态 Mod | ~10 |
| `Mod Set Mod` | Mod 套装 | ~15 |
| `Transmutation Mod` | 转换 Mod | ~5 |
| `Melee Riven Mod` | 近战裂罅 Mod | ~5 |
| `Kitgun Riven Mod` | 工坊枪裂罅 Mod | ~3 |
| `Companion Weapon Riven Mod` | 同伴武器裂罅 Mod | ~3 |
| `Arch-Gun Riven Mod` | 天翼枪裂罅 Mod | ~3 |

#### 虚空遗物
| type | 说明 | 数量级 |
|------|------|--------|
| `Relic` | 遗物 | ~3000 |

#### 资源与材料
| type | 说明 | 数量级 |
|------|------|--------|
| `Resource` | 资源 | ~200 |
| `Alloy` | 合金 | ~20 |
| `Gem` / `Cut Gem` | 宝石 | ~20 |
| `Fish` | 鱼 | ~30 |
| `Fish Part` | 鱼部件 | ~30 |
| `Fish Bait` | 鱼饵 | ~10 |
| `Eidolon Shard` | 夜灵碎片 | ~10 |
| `Ayatan Star` | 雅塔星 | ~5 |
| `Ayatan Sculpture` | 雅塔雕塑 | ~20 |
| `Pet Resource` | 宠物资源 | ~10 |
| `Pet Parts` | 宠物部件 | ~20 |

#### 外观与装饰
| type | 说明 | 数量级 |
|------|------|--------|
| `Glyph` | 徽章 | ~5000+ |
| `Skin` / `Skins` | 皮肤 | ~300+ |
| `Sigil` | 纹章 | ~200+ |
| `Syandana` | 披饰 | ~100 |
| `Color Palette` | 调色板 | ~20 |
| `Fur Color` / `Fur Pattern` | 毛色/毛纹 | ~20 |
| `Captura` | 截图工具 | ~10 |
| `Emotes` | 表情 | ~30 |
| `Note Packs` | 音符包 | ~10 |
| `Ship Decoration` | 飞船装饰 | ~50 |
| `Theme Background` / `Theme Sound` / `Themes` | 主题 | ~10 |

#### 制造与组件
| type | 说明 | 数量级 |
|------|------|--------|
| `Key` | 钥匙 | ~30 |
| `Gear` | 装备 | ~40 |
| `Specter` | 幽灵 | ~10 |
| `Extractor` | 采集机 | ~10 |
| `Ship Segment` | 飞船模块 | ~10 |
| `Zaw Component` | Zaw 组件 | ~30 |
| `Kitgun Component` | 工坊枪组件 | ~30 |
| `K-Drive Component` | 滑板组件 | ~10 |
| `Equipment Adapter` | 装备适配器 | ~10 |
| `Focus Lens` | 专精透镜 | ~10 |
| `Focus Way` | 专精路径 | ~5 |
| `Boosters` | 加速器 | ~5 |

#### Arcane
| type | 说明 | 数量级 |
|------|------|--------|
| `Arcane` | 秘奥 | ~30 |
| `Warframe Arcane` | 战甲秘奥 | ~30 |
| `Primary Arcane` | 主武器秘奥 | ~10 |
| `Secondary Arcane` | 副武器秘奥 | ~10 |
| `Melee Arcane` | 近战秘奥 | ~10 |
| `Bow Arcane` | 弓秘奥 | ~5 |
| `Operator Arcane` | 操控者秘奥 | ~20 |
| `Amp Arcane` | 操控器秘奥 | ~15 |
| `Zaw Arcane` | Zaw 秘奥 | ~10 |

#### 其他
| type | 说明 | 数量级 |
|------|------|--------|
| `Misc` | 杂项 | ~200+ |
| `Node` | 星图节点 | ~250+ |
| `Nightwave Challenge` | 电波之夜挑战 | ~15 |
| `Conservation Tag` | 保育标签 | ~30 |
| `Medallion` | 勋章 | ~10 |
| `Orbiter` | 轨道飞行器 | ~5 |
| `Simulacrum` | 模拟室 | ~5 |
| `Pet Collar` | 宠物项圈 | ~5 |
| `Arcade Minigame Unlock` | 街机小游戏解锁 | ~5 |
| `Tektolyst Artifact Mod` | 特克托利斯特神器 Mod | ~5 |

### 1.5 主要物品类型的嵌套结构

#### Warframe（战甲）

```
{
  "uniqueName": "/Lotus/Powersuits/Ninja/Ninja",
  "name": "Ash",
  "description": "...",
  "type": "Warframe",
  "category": "Warframes",
  "tradable": false,
  "masterable": true,

  // ── 属性 ──
  "health": 455,              // 生命值
  "shield": 270,              // 护盾
  "armor": 105,               // 护甲
  "stamina": 3,               // 耐力
  "power": 100,               // 能量
  "sprintSpeed": 1.15,        // 冲刺速度
  "masteryReq": 0,            // 精通需求
  "passiveDescription": "...", // 被动技能描述

  // ── 极性与光环 ──
  "aura": "madurai",          // 光环极性
  "polarities": ["naramon", "madurai"],  // 槽位极性列表
  "exilusPolarity": "naramon",           // Exilus 极性（可选）
  "productCategory": "Suits",            // 产品分类

  // ── 技能 ──
  "abilities": [               // 4个技能
    {
      "uniqueName": "/Lotus/Powersuits/Ninja/Abilities/GlaiveAbility",
      "name": "Shuriken",
      "description": "...",
      "imageName": "NinjaStar.png"
    },
    ...
  ],
  "exalted": ["..."],          // 显赫武器 uniqueName 列表（可选）

  // ── 制造 ──
  "buildPrice": 25000,         // 制造费用（信用点）
  "buildTime": 259200,         // 制造时间（秒）
  "skipBuildTimePrice": 50,    // 跳过制造时间费用（白金）
  "buildQuantity": 1,          // 制造数量
  "consumeOnBuild": true,      // 制造时是否消耗蓝图
  "components": [              // 制造组件
    {
      "uniqueName": "...",
      "name": "Blueprint",
      "description": "...",
      "itemCount": 1,
      "imageName": "blueprint.png",
      "tradable": false,
      "drops": []              // 掉落来源
    },
    ...
  ],

  // ── 市场与Vault ──
  "marketCost": 375,           // 市场白金价格（可选）
  "bpCost": 25000,             // 蓝图信用点价格（可选）
  "vaulted": true,             // 是否已入库（Prime战甲）
  "vaultDate": "2020-06-29",   // 入库日期（可选）
  "estimatedVaultDate": "...",  // 预计入库日期（可选）

  // ── 其他 ──
  "color": 0,                  // 颜色标识
  "sex": "Male",               // 性别
  "conclave": true,            // 是否可用于竞技场
  "introduced": "2013-04-12",  // 引入日期（可选）
  "releaseDate": "2013-04-12", // 发布日期（可选）
  "patchlogs": [...],          // 更新日志
  "imageName": "Ash.png",
  "wikiAvailable": true,
  "wikiaUrl": "https://warframe.fandom.com/wiki/Ash",
  "wikiaThumbnail": "..."
}
```

#### Rifle / Shotgun / Pistol / Bow / Sniper / Launcher（枪械类武器）

```
{
  "uniqueName": "...",
  "name": "...",
  "type": "Rifle",
  "category": "Primary",
  "tradable": true,
  "masterable": true,

  // ── 基础属性 ──
  "masteryReq": 10,            // 精通需求
  "productCategory": "LongGuns",  // 产品分类
  "slot": 0,                   // 装备槽位
  "noise": "Alarming",         // 噪音级别
  "trigger": "Auto",           // 触发类型
  "fireRate": 8.33,            // 射速
  "accuracy": 15.4,            // 精准度
  "magazineSize": 60,          // 弹夹容量
  "reloadTime": 2,             // 换弹时间
  "multishot": 1,              // 多重射击

  // ── 伤害属性 ──
  "totalDamage": 30,           // 总伤害
  "damage": 30,                // 基础伤害
  "damagePerShot": [30, 0, 0, ...],  // 每击伤害数组（各伤害类型）
  "criticalChance": 0.12,      // 暴击率
  "criticalMultiplier": 1.6,   // 暴击倍率
  "procChance": 0.12,          // 触发率
  "disposition": 1.15,         // 裂罅倾向
  "omegaAttenuation": 1.15,    // 裂罅衰减系数

  // ── 攻击模式 ──
  "attacks": [                 // 攻击模式列表
    {
      "name": "...",
      "crit_chance": 0.12,
      "crit_mult": 1.6,
      "status_chance": 0.12,
      "shot_type": "Hit-Scan",
      "speed": 0,
      "charge_time": 0,
      "damage": { "impact": 3, "puncture": 3.6, "slash": 23.4 },
      "pellet": { "name": "...", "count": 1 }
    }
  ],

  // ── 标签与极性 ──
  "tags": ["Tenno", "Prime"],  // 标签
  "polarities": ["naramon"],   // 槽位极性
  "exilusPolarity": "madurai", // Exilus 极性（可选）

  // ── 制造 ──
  "buildPrice": 15000,
  "buildTime": 43200,
  "skipBuildTimePrice": 35,
  "buildQuantity": 1,
  "consumeOnBuild": true,
  "components": [...],
  "marketCost": 265,           // 市场白金价格（可选）
  "bpCost": 15000,             // 蓝图信用点价格（可选）

  // ── 其他 ──
  "isPrime": true,
  "vaulted": true,             // 是否已入库（Prime武器）
  "sentinel": false,           // 是否为守护武器（可选）
  "introduced": "...",
  "releaseDate": "...",
  "patchlogs": [...],
  "drops": [...],
  "imageName": "...",
  "wikiAvailable": true,
  "wikiaUrl": "...",
  "wikiaThumbnail": "..."
}
```

#### Melee（近战武器）

```
{
  // ... 通用字段同上 ...

  // ── 近战专属属性 ──
  "blockingAngle": 55,         // 格挡角度
  "comboDuration": 5,          // 连击持续时间
  "followThrough": 0.6,        // 穿透力
  "range": 2.5,               // 攻击范围
  "windUp": 0.5,              // 蓄力时间
  "stancePolarity": "madurai", // 架式极性
  "heavyAttackDamage": 180,    // 重击伤害
  "slamAttack": 180,           // 猛击伤害
  "slamRadialDamage": 60,     // 猛击范围伤害
  "slamRadius": 8,            // 猛击范围
  "heavySlamAttack": 360,     // 重猛击伤害
  "heavySlamRadialDamage": 360,
  "heavySlamRadius": 8,

  "attacks": [...],            // 攻击模式
  "tags": [...],
  "polarities": [...],
  "components": [...],
  // ...
}
```

#### Mod（所有 Mod 类型）

```
{
  "uniqueName": "...",
  "name": "...",
  "type": "Warframe Mod",
  "category": "Mods",
  "tradable": true,
  "masterable": true,

  // ── Mod 专属属性 ──
  "baseDrain": 6,              // 基础消耗
  "fusionLimit": 5,            // 融合上限（等级上限）
  "polarity": "madurai",       // 极性
  "rarity": "Rare",            // 稀有度：Common / Uncommon / Rare / Legendary / Riven
  "compatName": "WARFRAME",    // 兼容类型
  "isPrime": false,            // 是否 Prime Mod
  "isAugment": false,          // 是否 Augment Mod
  "isExilus": false,           // 是否 Exilus Mod（可选）
  "isUtility": false,          // 是否工具 Mod（可选）
  "modSet": "...",             // 所属 Mod 套装（可选）
  "transmutable": true,        // 是否可转换

  // ── 等级属性 ──
  "levelStats": [              // 每级属性列表
    { "stats": ["+10% Ability Strength"] },
    { "stats": ["+20% Ability Strength"] },
    ...
  ],

  // ── 其他 ──
  "drops": [                   // 掉落来源
    {
      "type": "Mission",
      "location": "Venus/Unda (Defense)",
      "rarity": "Uncommon",
      "chance": 7.52
    }
  ],
  "introduced": "...",
  "releaseDate": "...",
  "patchlogs": [...],
  "imageName": "...",
  "wikiAvailable": true,
  "wikiaUrl": "...",
  "wikiaThumbnail": "..."
}
```

#### Relic（遗物）

```
{
  "uniqueName": "/Lotus/Types/Game/Projections/T4VoidProjectionESilver",
  "name": "Axi A1 Exceptional",
  "description": "An artifact containing Orokin secrets...",
  "type": "Relic",
  "category": "Relics",
  "tradable": true,
  "masterable": false,

  // ── 遗物专属属性 ──
  "vaulted": true,             // 是否已入库
  "locations": [],             // 获取地点
  "rewards": [                 // 6个奖励物品
    {
      "rarity": "Uncommon",    // 稀有度：Common / Uncommon / Rare
      "chance": 13,            // 掉落概率（百分比）
      "item": {
        "name": "Akstiletto Prime Barrel",
        "uniqueName": "/Lotus/Types/...",
        "warframeMarket": {    // Warframe Market 信息
          "id": "573b804a0ec44a47787a6916",
          "urlName": "akstiletto_prime_barrel"
        }
      }
    },
    ...
  ],
  "marketInfo": {              // Warframe Market 遗物信息
    "id": "6054dd685221e30057500f63",
    "urlName": "axi_a1_relic"
  },

  "patchlogs": [...]           // 更新日志（可选）
}
```

#### Node（星图节点）

```
{
  "uniqueName": "...",
  "name": "Apollodorus (Mercury)",
  "type": "Node",
  "category": "Node",
  "tradable": false,
  "masterable": false,

  // ── 节点专属属性 ──
  "factionIndex": 0,           // 阵营索引
  "masteryReq": 0,             // 精通需求
  "minEnemyLevel": 1,          // 最低敌人等级
  "maxEnemyLevel": 5,          // 最高敌人等级
  "missionIndex": 7,           // 任务索引
  "nodeType": 0,               // 节点类型
  "systemIndex": 0,            // 星系索引
  "systemName": "Mercury"      // 星系名称
}
```

### 1.6 共享嵌套结构

#### `drops` 数组（掉落来源）

```
"drops": [
  {
    "type": "Mission",         // 掉落类型：Mission / Enemy / Boss
    "location": "Venus/Unda",  // 掉落地点
    "rarity": "Uncommon",      // 稀有度
    "chance": 7.52             // 掉落概率（百分比）
  }
]
```

#### `components` 数组（制造组件）

```
"components": [
  {
    "uniqueName": "...",
    "name": "Blueprint",
    "description": "...",
    "itemCount": 1,            // 所需数量
    "imageName": "blueprint.png",
    "tradable": false,
    "masterable": false,
    "drops": [...]             // 该组件的掉落来源
  }
]
```

#### `patchlogs` 数组（更新日志）

```
"patchlogs": [
  {
    "name": "Update 32.2.0: Lua's Prey",
    "date": "2022-11-30T16:01:46Z",
    "url": "https://forums.warframe.com/topic/...",
    "additions": "",           // 新增内容
    "changes": "",             // 变更内容
    "fixes": "..."             // 修复内容
  }
]
```

---

## 2. warframe-items / Relics.json

**路径**: `external/warframe-items_sparse/data/json/Relics.json`
**类型**: 数组 (Array)
**长度**: 3,020 条
**说明**: All.json 的子集，仅包含 `type === "Relic"` 的物品。结构与 All.json 中的 Relic 完全一致。

### 2.1 字段组合

| 数量 | 字段集 |
|------|--------|
| 2,772 | category, description, imageName, locations, marketInfo, masterable, name, rewards, tradable, type, uniqueName, vaulted |
| 137 | 同上 + drops |
| 104 | 同上 + patchlogs（无 drops） |
| 5 | excludeFromCodex + patchlogs（无 marketInfo/vaulted） |
| 2 | excludeFromCodex（无 marketInfo/vaulted/patchlogs） |

### 2.2 遗物命名规则

遗物名称格式：`{时代} {编号} {品质}`

- **时代 (tier)**: Lith / Meso / Neo / Axi
- **编号**: 字母+数字组合（如 A1, B2, C3）
- **品质 (state)**: Intact / Exceptional / Flawless / Radiant

示例：`Axi A1 Exceptional` = Axi 时代 A1 号 瑕疵品质

### 2.3 rewards 结构

每个遗物包含 **6 个奖励物品**：

```
"rewards": [
  {
    "rarity": "Common",        // Common: 25.33% (Intact) / 14.67% (Radiant)
    "chance": 25.33,           // 掉落概率
    "item": {
      "name": "...",
      "uniqueName": "...",
      "warframeMarket": { "id": "...", "urlName": "..." }
    }
  },
  // 3 个 Common + 2 个 Uncommon + 1 个 Rare
]
```

概率分布（Intact → Radiant）：
- Common: 25.33% → 14.67%（3个）
- Uncommon: 11% → 20%（2个）
- Rare: 2% → 10.34%（1个）

---

## 3. warframe-items / i18n.json

**路径**: `external/warframe-items_sparse/data/json/i18n.json`
**类型**: 对象 (Object)
**键数**: 16,629（与 All.json 物品数一致）
**说明**: All.json 中所有物品的多语言翻译数据，以 `uniqueName` 为键。

### 3.1 顶层结构

```
i18n.json ─── Object
  ├── "/Lotus/Types/Ship/AdvancedResourceDrone": { Translations }
  ├── "/Lotus/Types/Ship/AdvancedUcResourceDrone": { Translations }
  └── ...
```

### 3.2 翻译对象结构

```
{
  "de": { "name": "...", "description": "..." },   // 德语
  "fr": { "name": "...", "description": "..." },   // 法语
  "it": { "name": "...", "description": "..." },   // 意大利语
  "ko": { "name": "...", "description": "..." },   // 韩语
  "es": { "name": "...", "description": "..." },   // 西班牙语
  "zh": { "name": "...", "description": "..." },   // 简体中文
  "ru": { "name": "...", "description": "..." },   // 俄语
  "ja": { "name": "...", "description": "..." },   // 日语
  "pl": { "name": "...", "description": "..." },   // 波兰语
  "pt": { "name": "...", "description": "..." },   // 葡萄牙语
  "tc": { "name": "...", "description": "..." },   // 繁体中文
  "th": { "name": "...", "description": "..." },   // 泰语
  "tr": { "name": "...", "description": "..." },   // 土耳其语
  "uk": { "name": "...", "description": "..." }    // 乌克兰语
}
```

每种语言包含 `name`（名称翻译）和 `description`（描述翻译）两个字段。

### 3.3 与 All.json 的关联

```
All.json[i].uniqueName  ←→  i18n.json[uniqueName].zh.name
```

通过 `uniqueName` 可将物品数据与其中文翻译关联。

---

## 4. warframe-drop-data / all.json

**路径**: `external/warframe-drop-data_sparse/data/all.json`
**类型**: 对象 (Object)
**顶层键数**: 19
**说明**: 游戏中所有掉落数据的完整汇总，包括任务奖励、遗物奖励、Mod 掉落、敌人掉落等。

### 4.1 顶层结构

```
all.json ─── Object
  ├── "missionRewards"        // 任务奖励
  ├── "relics"                // 遗物掉落
  ├── "transientRewards"      // 临时奖励（仲裁、入侵等）
  ├── "modLocations"          // Mod 掉落位置
  ├── "enemyModTables"        // 敌人 Mod 掉落表
  ├── "blueprintLocations"    // 蓝图掉落位置
  ├── "enemyBlueprintTables"  // 敌人蓝图掉落表
  ├── "sortieRewards"        // 突击奖励
  ├── "keyRewards"           // 钥匙奖励
  ├── "cetusBountyRewards"   // 希图斯赏金奖励
  ├── "solarisBountyRewards" // 索拉里斯赏金奖励
  ├── "deimosRewards"        // 火卫二奖励
  ├── "zarimanRewards"       // 扎里曼奖励
  ├── "entratiLabRewards"    // 英择谛实验室奖励
  ├── "hexRewards"           // Hex 奖励
  ├── "syndicates"           // 集团奖励
  ├── "resourceByAvatar"     // 按头像的资源
  ├── "sigilByAvatar"        // 按头像的纹章
  └── "additionalItemByAvatar" // 按头像的额外物品
```

### 4.2 missionRewards（任务奖励）

最复杂的嵌套结构，按星球 → 节点 → 任务模式 → 轮换分层：

```
"missionRewards" ─── Object
  ├── "Mercury" ─── Object           // 星球
  │   ├── "Apollodorus" ─── Object   // 节点
  │   │   ├── "gameMode": "Survival"  // 游戏模式
  │   │   ├── "isEvent": false        // 是否为活动任务
  │   │   └── "rewards" ─── Object    // 奖励
  │   │       ├── "A": [Reward, ...]  // A 轮奖励
  │   │       ├── "B": [Reward, ...]  // B 轮奖励
  │   │       └── "C": [Reward, ...]  // C 轮奖励
  │   ├── "Lares" ─── { ... }
  │   └── ...
  ├── "Venus" ─── { ... }
  └── ...
```

**注意**: 非轮换任务（如捕获、歼灭）的 `rewards` 直接是数组，而非 `{A, B, C}` 对象。

#### Reward 对象

```
{
  "_id": "e8a7b33288fc508c52d159564b29ace4",  // 唯一ID
  "itemName": "Morphic Transformer",            // 物品名称
  "rarity": "Rare",                             // 稀有度
  "chance": 5.64                                // 掉落概率（百分比）
}
```

轮换任务的 Reward 额外包含 `rotation` 字段：

```
{
  "_id": "...",
  "rotation": "A",              // 轮换：A / B / C
  "itemName": "...",
  "rarity": "Rare",
  "chance": 9
}
```

### 4.3 relics（遗物掉落）

```
"relics" ─── Array
  └── {
    "tier": "Axi",              // 时代：Lith / Meso / Neo / Axi
    "relicName": "A1",          // 遗物编号
    "state": "Intact",          // 品质：Intact / Exceptional / Flawless / Radiant
    "rewards": [                // 6个奖励
      {
        "_id": "...",
        "itemName": "Akstiletto Prime Barrel",
        "rarity": "Uncommon",
        "chance": 11            // 掉落概率
      }
    ],
    "_id": "..."
  }
```

### 4.4 transientRewards（临时奖励）

仲裁、入侵等非固定任务的奖励：

```
"transientRewards" ─── Array
  └── {
    "_id": "...",
    "objectiveName": "Arbitrations",  // 目标名称
    "rewards": [
      {
        "_id": "...",
        "rotation": "A",       // 轮换（可选）
        "itemName": "...",
        "rarity": "Rare",
        "chance": 9
      }
    ]
  }
```

### 4.5 modLocations（Mod 掉落位置）

```
"modLocations" ─── Array
  └── {
    "_id": "...",
    "modName": "Target Acquired",   // Mod 名称
    "enemies": [                     // 掉落该 Mod 的敌人
      {
        "_id": "...",
        "enemyName": "Tusk Thumper Bull",
        "enemyModDropChance": 15,    // 敌人 Mod 掉落率（百分比）
        "rarity": "Uncommon",
        "chance": 12.5               // 该 Mod 在掉落中的概率
      }
    ]
  }
```

### 4.6 enemyModTables（敌人 Mod 掉落表）

```
"enemyModTables" ─── Array
  └── {
    "_id": "...",
    "enemyName": "Scaldra Screamer",
    "ememyModDropChance": "100.00",  // 注意：原文拼写错误 "ememy"
    "enemyModDropChance": "100.00",  // 正确拼写（两个字段同时存在）
    "mods": [
      {
        "_id": "...",
        "modName": "Arcane Truculence",
        "rarity": "Uncommon",
        "chance": 12.5
      }
    ]
  }
```

### 4.7 其他顶层键的结构

| 键 | 结构 | 说明 |
|------|------|------|
| `blueprintLocations` | 同 modLocations | 蓝图掉落位置 |
| `enemyBlueprintTables` | 同 enemyModTables | 敌人蓝图掉落表 |
| `sortieRewards` | `[{ _id, itemName, rarity, chance }]` | 突击奖励池 |
| `keyRewards` | `[{ _id, keyName, rewards }]` | 钥匙任务奖励 |
| `cetusBountyRewards` | `[{ _id, bountyLevel, rewards }]` | 希图斯赏金 |
| `solarisBountyRewards` | 同上 | 索拉里斯赏金 |
| `deimosRewards` | 同上 | 火卫二赏金 |
| `zarimanRewards` | 同上 | 扎里曼赏金 |
| `entratiLabRewards` | 同上 | 英择谛实验室赏金 |
| `hexRewards` | 同上 | Hex 赏金 |
| `syndicates` | `[{ _id, syndicateName, rewards }]` | 集团奖励 |

---

## 5. warframe-i18n / dict.en.json & dict.zh.json

**路径**: `external/warframe-i18n_sparse/dict.en.json` / `dict.zh.json`
**类型**: 对象 (Object)
**键数**: en: 35,381 / zh: 35,381
**说明**: 游戏内文本的纯翻译字典，以游戏内部语言键为键，翻译后的字符串为值。

### 5.1 结构

```
dict.zh.json ─── Object
  ├── "/Lotus/Language/1999/10000HollarsName": "10,000 霍币储藏箱"
  ├── "/Lotus/Language/1999/1999HubName": "霍瓦尼亚中央商场"
  ├── "/Lotus/Language/1999/1999MapName": "霍瓦尼亚"
  ├── "/Lotus/Language/1999/1999NodeA": "传承种收割"
  └── ... (35,381 条)
```

### 5.2 特点

- **纯字符串值**：与 i18n.json 不同，这里的值是纯字符串，不是 `{name, description}` 对象
- **键名格式**：`/Lotus/Language/...`，是游戏引擎的语言资源路径
- **覆盖范围更广**：包含 UI 文本、任务描述、星图节点名等，远超物品翻译
- **en/zh 键集一致**：两个文件的键完全对应

### 5.3 与其他文件的关联

此字典的键与 All.json 中的 `uniqueName` 不直接对应。它主要用于翻译游戏 UI 和界面文本，而非物品名称。物品翻译应使用 `i18n.json`。

---

## 6. 跨文件关联关系

### 6.1 核心关联图

```
                    uniqueName
All.json ──────────────────────→ i18n.json
  [i].uniqueName ─────────────→ i18n.json[uniqueName].zh.name
  [i].uniqueName ─────────────→ i18n.json[uniqueName].zh.description

                    itemName
all.json ─────────────────────→ All.json
  relics[i].rewards[j].itemName → All.json 中查找 name 匹配的物品
  modLocations[i].modName      → All.json 中查找 name 匹配的 Mod

                    uniqueName
All.json (Relic) ─────────────→ all.json (relics)
  name: "Axi A1 Exceptional"  → tier="Axi", relicName="A1", state="Exceptional"

                    /Lotus/Language/...
dict.zh.json ─────────────────→ 游戏UI文本翻译（独立使用）
```

### 6.2 关联方式总结

| 源文件 | 目标文件 | 关联键 | 说明 |
|--------|----------|--------|------|
| All.json | i18n.json | `uniqueName` | 物品 → 多语言翻译 |
| all.json | All.json | `itemName` / `modName` | 掉落物品 → 物品详情 |
| All.json (Relic) | all.json (relics) | name ↔ tier+relicName+state | 遗物详情 ↔ 遗物掉落 |
| dict.zh.json | 游戏UI | `/Lotus/Language/...` | 独立的UI翻译字典 |

### 6.3 数据冗余与差异

1. **遗物数据冗余**: All.json 和 Relics.json 中的遗物数据完全重复，Relics.json 是 All.json 的 `type === "Relic"` 过滤子集
2. **遗物奖励数据差异**: All.json 中 Relic 的 `rewards` 包含 `warframeMarket` 信息，而 all.json 中 relics 的 `rewards` 使用 `_id` 且无 `warframeMarket`
3. **翻译数据差异**: i18n.json 提供物品级的 `{name, description}` 翻译，dict.zh.json 提供更广泛的 UI 文本翻译，两者覆盖范围不同
4. **掉落数据互补**: All.json 的 `drops` 字段与 all.json 的 `modLocations`/`enemyModTables` 存在数据重叠但格式不同

---

## 附录：字段值枚举

### 稀有度 (rarity)
- `Common` — 常见
- `Uncommon` — 罕见
- `Rare` — 稀有
- `Legendary` — 传说
- `Riven` — 裂罅

### 极性 (polarity)
- `madurai` — Madurai（V）
- `vazarin` — Vazarin（D）
- `naramon` — Naramon（—）
- `zenurik` — Zenurik（=）
- `umbra` — Umbra（U）
- `penjaga` — Penjaga（Y，同伴）
- `unairu` — Unairu（R）

### 遗物时代 (tier)
- `Lith` — 丽斯（第1时代）
- `Meso` — 美索（第2时代）
- `Neo` — 新纪（第3时代）
- `Axi` — 阿克西（第4时代）

### 遗物品质 (state)
- `Intact` — 完好
- `Exceptional` — 瑕疵
- `Flawless` — 无暇
- `Radiant` — 光辉

### 触发类型 (trigger)
- `Auto` — 全自动
- `Semi-Auto` — 半自动
- `Burst` — 点射
- `Charge` — 蓄力
- `Duplex` — 双发
- `Held` — 持续
