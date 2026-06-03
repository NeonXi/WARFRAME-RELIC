# WARFRAME-RELIC Test Module 开发文档

## 概述

test_module 是一个独立的测试模块，用于验证 warframe.market 物品搜索与价格查询功能。该模块从主项目数据中读取物品信息，通过 WM API 获取实时价格，以 PyQt6 GUI 展示结果。

## 项目结构

```
test_module/
├── wm_search.py       # 入口文件，启动 GUI
├── main_window.py     # 主窗口 UI 与事件处理
├── search_widget.py   # 搜索框组件（输入+下拉建议）
├── price_fetcher.py   # 后台线程：从 WM API 获取价格
├── utils.py           # 工具函数（Slug 生成、状态映射、缓存）
├── progress_bar.py    # 自定义进度条/加载动画组件
├── db_updater.py      # 数据库维护工具（独立 CLI）
├── start.bat          # Windows 启动脚本
├── DEV.md             # 本文件：开发文档
└── DB.md              # 数据库文档
```

## 架构设计

### 数据流

```
用户输入 → SearchWidget → wm_items.db (本地查询)
          ↓
      item_selected 信号
          ↓
      MainWindow 接收 → utils.format_slug() → PriceFetcher (后台线程)
          ↓
      warframe.market API → 逐条订单 → order_received 信号
          ↓
      MainWindow 流式渲染到 QTableWidget
```

### 组件职责

| 组件 | 职责 | 关键依赖 |
|------|------|----------|
| **wm_search.py** | 应用入口，设置 sys.path | main_window |
| **main_window.py** | 主窗口布局、信号连接、生命周期管理 | search_widget, price_fetcher, progress_bar, utils |
| **search_widget.py** | 搜索框、下拉建议、键盘导航、SQLite 查询 | wm_items.db |
| **price_fetcher.py** | 后台线程、WM API 请求、订单解析、流式输出 | urllib, QThread |
| **utils.py** | Slug 解析、状态映射、LRU 缓存 | wm_items.db |
| **progress_bar.py** | 旋转加载动画、滑动进度条、脉冲效果 | QPainter |
| **db_updater.py** | 数据库可交易状态修正（独立工具） | wm_items.db |

## 核心功能

### 1. 物品搜索（search_widget.py）

- **防抖输入**：用户输入后 150ms 触发查询
- **多语言搜索**：支持中文、英文、拼音
- **过滤规则**：自动排除浮印、外观、皮肤、动画等非交易物品
- **排序优先级**：套装 > 蓝图 > 其他
- **持久连接**：使用单一 SQLite connection，避免重复创建
- **键盘导航**：↑↓ 选择，Enter 确认，Esc 关闭

### 2. 价格查询（price_fetcher.py）

- **后台线程**：通过 QThread 避免阻塞 UI
- **流式输出**：逐条发射订单信号，无需等待全部数据
- **排序规则**：游戏中 > 在线 > 离开 > 离线，同状态按价格升序
- **数量限制**：全部在线卖家 + 最多 50 个离线卖家
- **线程安全**：Lock 保护 `_stop_flag`
- **安全类型转换**：`_safe_int()` 处理所有 API 数据转换

### 3. Slug 生成（utils.py）

- **优先 DB 查询**：从 wm_items.db 直接获取 slug，无网络请求
- **LRU 缓存**：最多缓存 500 条，防止内存膨胀
- **降级策略**：DB 未命中时使用规则生成（Prime、Blueprint 变体）

### 4. 进度条（progress_bar.py）

- **LoadingSpinner**：8 点旋转动画，50 FPS
- **QProgressBar**：
  - 不确定模式（max=0）：滑动渐变条 + 尾部光晕 + 脉冲透明度
  - 确定模式（max>0）：填充渐变条（青色→绿色）

### 5. 用户交互

- **点击用户名**：复制到剪贴板
- **状态栏**：显示操作结果
- **错误处理**：优雅降级，显示错误信息

## 信号/槽机制

### SearchWidget
| 信号 | 参数 | 说明 |
|------|------|------|
| `item_selected` | `dict{id, en_name, zh_name}` | 用户选择物品 |

### PriceFetcher
| 信号 | 参数 | 说明 |
|------|------|------|
| `progress_update` | `(int, str)` | 进度百分比 + 状态文字 |
| `order_received` | `dict` | 单条订单数据 |
| `finished` | `(bool, str)` | 成功/失败 + 消息 |

## 依赖

### Python 标准库
- `sys`, `os`, `time`, `json`, `traceback`, `urllib`, `threading`, `sqlite3`, `collections`

### 第三方库
- **PyQt6**：GUI 框架（QtWidgets, QtCore, QtGui）

### 外部依赖
- **warframe.market API**：`https://api.warframe.market/v2`
- **wm_items.db**：物品名称数据库（位于 `../data/`）

## 启动方式

### Windows
```batch
# 双击运行
start.bat

# 或命令行
python wm_search.py
```

### 其他平台
```bash
python wm_search.py
```

## 维护工具

### db_updater.py - 数据库可交易状态修正

```bash
# 交互式运行
python db_updater.py

# 编程方式使用
from db_updater import ItemDatabaseUpdater
updater = ItemDatabaseUpdater()

# 分析问题
problems = updater.analyze_tradable_status()

# 执行修复
result = updater.fix_tradable_status(dry_run=False)
```

修复规则：
1. **武器部件**：Barrel/Receiver/Stock → 可交易
2. **蓝图**：Blueprint → 可交易
3. **套装**：Set → 可交易

## 注意事项

1. **WM API 频率限制**：建议每秒不超过 3 次请求
2. **网络延迟**：API 服务器在国外，正常请求耗时 10-15 秒
3. **数据库路径**：所有文件通过相对路径访问 `../data/wm_items.db`
4. **线程安全**：勿在 PriceFetcher 线程中直接操作 UI 组件
5. **样式外部化**：main_window.py 中所有样式定义为模块常量，便于维护