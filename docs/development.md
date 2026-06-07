# WARFRAME-RELIC 开发规范

> 版本：v4.2 | 更新日期：2026-06-07

---

## 一、项目概述

WARFRAME-RELIC 是 Warframe（星际战甲）游戏辅助工具，提供遗物出入库查询、物品掉落查询、市场价格查询、中英翻译等功能。基于 PyQt6 + RapidOCR + dxcam 技术栈，以半透明覆盖层方式在游戏画面上无侵入显示结果。

### 核心功能

| 功能 | 快捷键 | 说明 |
|------|--------|------|
| 框选截图 | `Ctrl+G` | 拖拽框选区域 → 松手自动截图识别 |
| 全屏截图 | `Ctrl+H` | 直接全屏截图识别 |
| 价格查询 | `Ctrl+T` | 自动 4 等分截图 + 识别 + 标注价格 |
| 右键清除 | 右键 | 清除所有标注和按钮 |

---

## 二、目录结构

```
WARFRAME-RELIC/
├── main.py                     # 程序入口：AppCore + TriggerBridge + OCRWorker
├── dev_runner.py               # 开发模式启动器
├── requirements.txt            # Python 依赖
├── qt.conf                     # Qt 运行时配置
│
├── core/                       # 核心模块
│   ├── bootstrap.py            # 启动引导：单例检测、异常钩子、main()
│   ├── constants.py            # 全局常量和主题代理
│   ├── management_panel.py     # 管理面板主窗口（Mixin 组合）
│   ├── bg_layer.py             # 背景图层管理 Mixin
│   ├── panel_styles.py         # 内联样式刷新 Mixin
│   ├── panel_builder.py        # UI 构建 Mixin
│   ├── overlay.py              # 全屏透明覆盖层
│   ├── region_selector.py      # 区域框选器
│   ├── hotkey_manager.py       # ★ 热键管理器（Windows API RegisterHotKey + QAbstractNativeEventFilter）
│   ├── hotkey_config.py        # 热键配置读写
│   ├── hotkey_capture_button.py# 热键捕获按钮组件
│   ├── trigger_manager.py      # ★ 辅助触发器（Windows API WH_MOUSE_LL + WH_KEYBOARD_LL 低级钩子）
│   ├── mode_handlers.py        # 功能处理器（出入库/查询/翻译/价格）
│   ├── price_service.py        # 价格服务（三级查询 + 限速器）
│   ├── drop_tooltip.py         # 物品掉落来源查询
│   ├── item_info_panel.py      # 物品信息面板
│   ├── annotation.py           # 覆盖层标注绘制
│   ├── stylesheet.py           # 动态 QSS 样式表
│   ├── theme_config.py         # 主题配置引擎
│   ├── theme_fields.py         # 主题字段定义
│   ├── theme_panel.py          # 主题可视化编辑面板
│   ├── theme_proxy.py          # 主题代理
│   ├── splash_screen.py        # 启动画面
│   ├── data_center.py          # 后台数据处理中心
│   ├── json_viewer.py          # JSON 文件查看器
│   ├── proxy_config.py         # 代理配置
│   ├── proxy_mirror_dialog.py  # 代理镜像配置对话框
│   ├── update_panel.py         # 更新面板
│   ├── update_worker.py        # 更新后台线程
│   ├── word_wrap_button.py     # 自动换行按钮组件
│
├── data/                       # 数据层
│   ├── build_warframe_db.py    # ★ 统一数据库构建脚本
│   ├── build_market_items.py   # ★ market_items 表构建脚本（从 items 表本地生成，不依赖 WM API）
│   ├── warframe.db             # ★ 统一数据库（SQLite，25 张表）
│   ├── all.json                # 掉落数据副本（JSON 查看器引用）
│   ├── dict.en.json            # 英文术语（旧翻译模块引用，待迁移）
│   ├── dict.zh.json            # 中文术语（旧翻译模块引用，待迁移）
│   ├── ui_strings.py           # ★ UI 字符串路由器（S() 函数 + 预设管理）
│   ├── preset_normal.py        # ★ UI 字符串预设 — 普通风格（STRINGS 字典）
│   ├── version.py              # 版本号
│   ├── game_terms.py           # 游戏术语
│   ├── icon_loader.py          # 图标加载器
│   ├── data_pipeline.py        # ★ 数据流水线（编排 build_warframe_db.py 构建 + WM 更新）
│   ├── db_connections.py      # ★ 数据库连接注册表（集中管理缓存连接）
│   ├── wfinfo_relics.py        # ★ 遗物接口（已迁移至 warframe.db）
│   ├── item_index.py           # ★ 物品索引 + 拼音搜索（已迁移至 warframe.db）
│   ├── translator.py           # ★ 翻译接口（已迁移至 warframe.db，查询接口保留占位）
│   ├── market_items.py         # ★ 市场物品接口（已迁移至 warframe.db）
│   ├── wm_prices.py            # ★ 价格接口（已迁移至 warframe.db）
│   ├── update_db.py            # ~~已删除~~（功能由 build_warframe_db.py 替代）
│   ├── hotkeys.json            # 热键配置文件
│   ├── feature_toggles.json   # 功能开关配置
│   ├── proxy_mirrors.json      # 代理镜像配置
│   ├── item_region.json        # 物品区域配置
│   ├── language_preset.json    # 语言预设
│   ├── window_geometry.json    # 窗口位置记忆
│   ├── backgrounds/            # 背景图片
│   └── presets/                # 主题预设
│
├── recognizers/                # OCR 识别模块
│   ├── __init__.py
│   ├── base_ocr.py             # OCR 基类
│   ├── relic_name.py           # 遗物名称识别器
│   ├── item_name.py            # 物品名称识别器
│   ├── mod_name.py             # Mod 名称识别器
│   └── matcher.py              # 模糊匹配器
│
├── market_query/               # 市场查询独立模块
│   ├── main_window.py          # 市场查询主窗口
│   ├── search_widget.py        # 搜索框组件
│   ├── price_fetcher.py        # 价格获取线程
│   ├── db_updater.py           # 数据库更新工具
│   ├── wm_search.py            # WM 搜索入口
│   ├── utils.py                # 工具函数
│   ├── progress_bar.py         # 进度条组件
│   └── code_rain.py            # 代码雨动画
│
├── scripts/                    # 工具脚本
│   └── pull_warframe_items.py  # ★ 仓库拉取脚本（代理镜像自动重试）
│
├── utils/                      # 通用工具
│   └── file_io.py              # 文件 I/O 工具
│
├── assets/                     # 静态资源
│   └── icons/                  # SVG 图标
│
├── icon/                       # 第三方图标库
│
├── tests/                      # 测试
│
├── docs/                       # 文档
│   ├── database.md             # 数据库文档
│   ├── development.md          # 本文件：开发规范
│   ├── json_source_analysis.md # JSON 源文件解析
│   └── price_algorithm.md      # 价格算法设计
│
└── external/                   # 外部数据源（gitignore，脚本拉取）
    ├── warframe-items_sparse/
    ├── warframe-drop-data_sparse/
    └── warframe-i18n_sparse/
```

---

## 三、技术栈

| 类别 | 技术 | 版本要求 |
|------|------|----------|
| GUI 框架 | PyQt6 | >= 6.7.0 |
| 屏幕截图 | dxcam | >= 0.3.0 |
| 全局热键 | Windows API (RegisterHotKey + WH_KEYBOARD_LL) | 替代 keyboard 库，避免窗口闪烁 |
| OCR 引擎 | RapidOCR (ONNX Runtime) | rapidocr-onnxruntime |
| 图像处理 | Pillow | >= 10.0.0 |
| 数值计算 | NumPy | >= 1.26.0, < 2.0.0 |
| 拼音转换 | pypinyin | >= 0.51.0 |
| 数据库 | SQLite 3 | Python 内置 |
| 目标检测 | YOLOv5n (ultralytics) | yolov5nu.pt |

---

## 四、数据库架构

### 统一数据库：`data/warframe.db`

所有数据整合到单一 SQLite 数据库，25 张表，详见 [docs/database.md](database.md)。

**核心表关系**：

```
items (主表, 16,629 条)
 ├── item_type_attrs    (1:1)  类型专属属性
 ├── item_abilities     (1:N)  技能
 ├── item_attacks       (1:N)  攻击模式
 ├── item_components    (1:N)  制造组件
 ├── item_drops         (1:N)  掉落来源
 ├── item_patchlogs     (1:N)  更新日志
 └── item_translations  (1:N)  14 语言翻译

relics (3,014 条 = 755 遗物 × 4 精炼状态)
 └── relic_rewards      (1:N)  遗物奖励

planets → mission_nodes → mission_rewards
```

**数据源映射**：

| 源文件 | 目标表 |
|--------|--------|
| All.json (warframe-items) | items + item_type_attrs + item_abilities + item_attacks + item_components + item_drops + item_patchlogs |
| i18n.json (warframe-items) | item_translations |
| all.json (warframe-drop-data) | relics + relic_rewards + planets + mission_nodes + mission_rewards + mod_drops + enemy_mod_tables + blueprint_drops + enemy_bp_tables + sortie_rewards + bounty_rewards + transient_rewards + key_rewards + syndicate_rewards |
| dict.en/zh.json (warframe-i18n) | game_translations |
| WM API | market_items (build_market_items.py 从 items 表本地生成) |

### 旧数据库（已删除）

以下旧数据库文件已清理，数据已合并到 warframe.db：
- ~~`relics.db`~~ → 合并到 relics + relic_rewards 表
- ~~`item_index.db`~~ → 合并到 items + item_translations 表
- ~~`translator.db`~~ → 合并到 game_translations 表
- ~~`market_items.db`~~ → 合并到 market_items 表

**禁止引用旧数据库：** 任何代码不得再引用上述已废弃的 `.db` 文件。所有业务数据统一从 `warframe.db` 查询。

**例外：** `wm_prices.db` 是价格缓存数据库，由 `wm_prices.py` 管理，因数据量大且独立更新频率高，允许独立存在。

### items 表字段映射

旧字段 → 新字段（从 item_index.db 迁移时需注意）：
- `en_name` → `name`
- `is_tradable` → `tradable`
- `id` → `rowid`（无显式 id 列）

查询示例：
```python
conn.execute("SELECT rowid AS id, name AS en_name, zh_name, category, tradable AS is_tradable FROM items")
```

### 旧模块迁移状态

| 旧模块 | 状态 | 说明 |
|--------|------|------|
| `wfinfo_relics.py` | ✅ 已迁移 | 已改为查询 warframe.db relics 表 |
| `item_index.py` | ✅ 已迁移 | 已改为查询 warframe.db items + item_translations，支持拼音搜索、遗物过滤 |
| `translator.py` | ✅ 已迁移 | 已改为查询 warframe.db game_translations 表 |
| `wm_prices.py` | ✅ 已迁移 | 已改为查询 warframe.db items 表匹配 |
| `market_items.py` | ✅ 已迁移 | 已改为查询 warframe.db market_items 表 |
| `build_market_items.py` | ✅ 新增 | 从 items 表本地构建 market_items 表（不依赖 WM API） |
| `matcher.py` | ✅ 已迁移 | 已改为查询/写入 warframe.db items 表 |
| `data_pipeline.py` | ✅ 已迁移 | 已编排 build_warframe_db.py 流水线 |
| `update_db.py` | ✅ 已删除 | 功能已由 build_warframe_db.py 替代 |

---

## 五、核心架构

### 5.1 启动流程

采用**延迟初始化 + 后台静默加载**策略，将重型组件推迟到界面显示后异步加载，用户感知启动时间 < 0.5s。

#### 整体时序

```
DEV_RUN.bat / WARFRAME-RELIC.bat
    ↓
bootstrap.main()
    ├── 单例检测 (Windows Mutex)
    ├── 管理员权限检测
    ├── 全局异常钩子注册
    ├── QApplication 创建
    │
    ├── AppCore.__init__()          ← 同步：仅初始化轻量 UI 组件
    │   ├── Overlay 创建并 show()
    │   ├── ManagementPanel 创建（不显示）
    │   ├── RelicDB 对象创建（不加载）
    │   ├── _camera = None          ← 延迟
    │   ├── _relic_ocr = None       ← 延迟
    │   ├── _item_ocr = None        ← 延迟
    │   ├── _camera_ready = False   ← 就绪守卫
    │   └── _ocr_ready = False      ← 就绪守卫
    │
    ├── AppCore.run()
    │   ├── _bind_events()           信号/热键绑定
    │   ├── _hotkey_mgr.register_initial()  (Windows API RegisterHotKey)
    │   ├── aboutToQuit → _shutdown
    │   │
    │   ├── QTimer(100ms) → _show_panel_on_start     ★ 面板显示
    │   │   ├── panel._fix_initial_size()
    │   │   ├── panel.show() + raise_() + activateWindow()
    │   │   └── SplashScreen 启动动画
    │   │
    │   ├── QTimer(300ms) → _print_startup_info      ★ 日志输出
    │   │   └── 输出快捷键列表、功能提示、数据库状态到日志面板
    │   │
    │   └── QTimer(500ms) → _lazy_init_background     ★ 后台加载
    │       └── daemon 线程 "LazyInitWorker" → _load()
    │           │
    │           ├── [日志] 正在初始化摄像头 (dxcam)...
    │           ├── _create_camera_with_retry()        重试机制（最多 N 次）
    │           ├── _camera_ready = True
    │           └── [日志] ✔ 摄像头初始化完成
    │           │
    │           ├── [日志] 正在加载遗物 OCR 模型...
    │           ├── RelicNameRecognizer()              加载 ONNX 模型
    │           ├── [日志] 正在加载物品 OCR 模型...
    │           ├── ItemNameRecognizer()                加载 ONNX 模型
    │           ├── _ocr_ready = True
    │           └── [日志] ✔ OCR 引擎初始化完成 (遗物 + 物品)
    │           │
    │           ├── [日志] 正在加载数据库...
    │           ├── RelicDB.load()                      读取 warframe.db
    │           └── [日志] ✔ 数据库已就绪 — X 个遗物 | 出库 X | 入库 X
    │               （或 warn: 数据库未加载，请在管理面板中更新数据）
    │           │
    │           └── [日志] ═══ 所有组件加载完成，程序就绪 ═══
    │
    └── app.exec()                   进入 Qt 事件循环
```

#### 日志面板输出示例

面板显示后，日志区按顺序输出以下信息：

```
[时间]  WARFRAME-RELIC 已启动                    ← _print_startup_info
[时间]  框选截图: Ctrl+G
[时间]  全屏截图: Ctrl+H
[时间]  价格查询: Ctrl+T
[时间]  右键清除所有标注
[时间]  选择功能模式后自动识别 ...
[时间]    [C] 出入库状态查询
[时间]    [Q] 遗物内容查询
[时间]    [$] 市场价格查询
[时间]    [T] 中英翻译
[时间]  数据库后台加载中...                        ← 此时后台线程尚未完成
[时间]  正在初始化摄像头 (dxcam)...                 ← _lazy_init_background 开始
[时间]  ✔ 摄像头初始化完成
[时间]  正在加载遗物 OCR 模型...
[时间]  正在加载物品 OCR 模型...
[时间]  ✔ OCR 引擎初始化完成 (遗物 + 物品)
[时间]  正在加载数据库...
[时间]  ✔ 数据库已就绪 — 755 个遗物 | 出库 400 | 入库 355
[时间]  ═══ 所有组件加载完成，程序就绪 ═══
```

#### 就绪守卫机制

后台加载期间，用户操作可能触发未就绪组件。所有功能入口点均设有**就绪守卫**：

| 入口方法 | 守卫条件 | 未就绪时的行为 |
|----------|----------|----------------|
| `_on_hotkey()` | `_camera_ready` / `_ocr_ready` | 日志提示"正在初始化"，直接 return |
| `_on_selection_done()` | `_camera_ready` | Overlay 显示"摄像头正在初始化"，2s 自动隐藏 |
| `_do_fullscreen_screenshot()` | `_camera_ready` | 同上 |

**设计原则**：
- 守卫检查在业务逻辑之前，确保不会访问 `None` 对象
- 提示友好，告知用户原因而非静默失败
- 不阻塞线程，立即返回等待下次操作

#### 关键设计决策

| 决策 | 原因 |
|------|------|
| UI 先于重型组件 | 用户感知启动时间从 4~8s 降至 < 0.5s |
| daemon 线程加载 | 程序退出时线程自动终止，无需额外清理 |
| 每步独立日志 | 用户可实时看到加载进度，而非黑盒等待 |
| print → self._log | 所有状态统一输出到日志面板，控制台与面板同步 |
| QTimer 错开执行 | 100ms 显示面板 → 300ms 打印日志 → 500ms 后台加载，避免拥堵 |

### 5.2 OCR 识别流程

```
快捷键触发 → 清除所有状态 → 截图(dxcam) → 显示功能按钮
    ↓ 用户选择功能
OCR 识别(RapidOCR) → 模糊匹配(matcher) → 数据库查询 → 覆盖层标注
```

### 5.3 管理面板架构

`ManagementPanel` 使用 Mixin 模式组合：

```python
class ManagementPanel(BgLayerMixin, PanelStylesMixin, PanelBuilderMixin, QWidget):
    # BgLayerMixin: 背景图层管理
    # PanelStylesMixin: 内联样式刷新
    # PanelBuilderMixin: UI 构建
```

### 5.4 后台数据处理中心

`DataCenterWindow` 独立窗口，包含 4 个一级导航：
- **数据链路** — 数据源 → 解析 → 存储的可视化流程
- **数据表** — 数据库表列表、表结构、数据查询
- **JSON 查看器** — 源文件格式化展示 + 搜索定位
- **操作日志** — 构建和更新日志

---

## 六、编码规范

### 6.1 Python 风格

- 遵循 PEP 8，行宽 120
- 使用 type hints（Python 3.10+ 语法，如 `list[str]` 而非 `List[str]`）
- 模块级文档字符串说明职责
- 函数/方法文档字符串说明参数和返回值

### 6.2 命名约定

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块/变量/函数 | snake_case | `hotkey_manager`, `load_hotkeys()` |
| 类 | PascalCase | `ManagementPanel`, `DataRepository` |
| 常量 | UPPER_SNAKE | `DEFAULT_HOTKEYS`, `DB_PATH` |
| 私有成员 | 前缀 `_` | `_db_path`, `_switch_tab()` |
| Qt 信号 | snake_case | `db_updated`, `theme_changed` |
| Qt 槽 | `_on_` 前缀 | `_on_open_data_center()` |

### 6.3 PyQt6 规范

- 信号定义在类顶部，紧跟类文档字符串之后
- 使用 `pyqtSignal` 定义信号，类型注解清晰
- UI 构建方法以 `_build_` 前缀命名
- 事件处理方法以 `_on_` 前缀命名
- 长时间操作使用 `QThread` 或 `QTimer.singleShot` 避免阻塞 UI

### 6.4 数据库规范

- 所有数据库操作使用 `sqlite3` 标准库
- 连接时启用 `PRAGMA journal_mode=WAL` 和 `PRAGMA foreign_keys=ON`
- 使用参数化查询，禁止字符串拼接 SQL
- 数据库路径统一通过 `DataRepository` 访问
- 构建完成后执行 `VACUUM` 压缩

### 6.5 UI 字符串规范

**核心原则：所有 UI 中展示的文本必须通过 `S()` 函数调用，禁止硬编码中文字符串。**

#### 架构

```
data/ui_strings.py          ← 路由器：S() 函数 + 预设管理 API
data/preset_normal.py       ← 预设文件：STRINGS 字典（普通风格）
data/preset_xxx.py          ← 预设文件：其他风格（可扩展）
data/language_preset.json   ← 配置：记录当前活跃预设
```

#### 调用方式

```python
from data.ui_strings import S

# 基本用法：S("分类", "键名")
label.setText(S("button", "exit"))           # → "退出程序"
btn.setText(S("management", "update_base_data"))  # → "更新基础数据"

# 格式化字符串：S.format("分类", "键名", **kwargs)
text = S.format("log_msg", "startup_db_info", total=755, available=400, vaulted=355)

# 缺失键时返回 ??category.key?? 格式的占位符，便于发现遗漏
```

#### 预设文件结构

`preset_normal.py` 中定义 `STRINGS` 字典，按功能分类组织：

```python
STRINGS = {
    "window_title": { ... },      # 窗口标题
    "title": { ... },             # 标题
    "button": { ... },            # 通用按钮
    "group": { ... },             # 分组标题
    "feature_toggle": { ... },    # 功能开关（含动态键 desc_{key} / label_{key}）
    "stat_label": { ... },        # 统计标签
    "status": { ... },            # 状态文本
    "hint": { ... },              # 提示信息
    "overlay": { ... },           # 覆盖层
    "log": { ... },               # 日志面板
    "log_msg": { ... },           # 日志消息
    "hotkey": { ... },            # 热键设置
    "exit": { ... },              # 退出确认
    "update": { ... },            # 更新相关
    "tutorial": { ... },          # 教程
    "theme": { ... },             # 主题设置
    "theme_field": { ... },       # 主题字段名
    "theme_cat": { ... },         # 主题分类名
    "data_center": { ... },       # 数据中心
    "json_viewer": { ... },       # JSON 查看器
    "proxy_mirror": { ... },      # 代理镜像
    "hotkey_capture": { ... },    # 热键录制
    "splash": { ... },            # 启动画面
    "management": { ... },        # 管理面板
}
```

#### 新增 UI 文本的步骤

1. 在 `data/preset_normal.py` 对应分类下添加键值对
2. 在代码中通过 `S("分类", "键名")` 调用
3. 如需新分类，在 `STRINGS` 字典中添加顶层键

#### 动态键约定

部分模块使用动态拼接键名（如功能开关），需确保键名与代码中的数据键一致：

```python
# hotkey_config.py 中 DEFAULT_FEATURE_TOGGLES 的键为 check_status / query_parts / translate
# preset_normal.py 中对应 label_check_status / desc_check_status 等
btn.setText(f"{S('feature_toggle', f'label_{key}')}\n{S('feature_toggle', f'desc_{key}')}")
```

#### 禁止事项

- **禁止**在 UI 代码中直接写中文字符串：`QLabel("未设置")` → `QLabel(S("management", "price_not_set"))`
- **禁止**在 QMessageBox 标题中硬编码：`QMessageBox.warning(self, "更新失败", ...)` → `QMessageBox.warning(self, S("management", "update_failed"), ...)`
- **禁止**在按钮文本中硬编码：`QPushButton("刷新")` → `QPushButton(S("data_center", "btn_refresh"))`
- **禁止**在 placeholder 中硬编码：`setPlaceholderText("值")` → `setPlaceholderText(S("data_center", "placeholder_value"))`

### 6.6 文件组织

- 一个模块一个文件，文件名与主类/功能对应
- 超过 500 行的文件考虑拆分（Mixin 模式）
- `core/` 放界面和业务逻辑
- `data/` 放数据访问和构建逻辑
- `recognizers/` 放 OCR 识别相关
- `scripts/` 放一次性工具脚本
- `docs/` 放文档

### 6.7 配色规范

**核心原则：UI 代码中严禁硬编码十六进制颜色值，所有颜色必须通过配色系统获取。**

#### 配色系统架构

```
core/theme_config.py   → ThemeConfig 单例，管理配色加载/保存/预设切换
core/theme_proxy.py    → 模块级代理常量，自动跟随主题变化
core/theme_fields.py   → 主题编辑器字段定义
```

#### 使用方式

```python
# 方式一：导入代理常量（推荐，自动跟随主题变化）
from core.theme_proxy import CYBER_YELLOW, COLOR_GOLD
f"color: {CYBER_YELLOW};"

# 方式二：通过 theme 单例访问
from core.constants import theme
f"color: {theme.cyber_yellow};"
```

#### 传给 QColor 的注意事项

`_ThemeProxy` 对象不能直接传给 `QColor()`，必须先转 `str()`：

```python
# 正确 ✓
QColor(str(CYBER_YELLOW))

# 错误 ✗（会抛出 TypeError）
QColor(CYBER_YELLOW)
```

#### 可用颜色常量

| 常量 | 默认值 | 用途 |
|------|--------|------|
| **霓虹主色** | | |
| `CYBER_YELLOW` | #FFE600 | 主强调色 |
| `CYBER_CYAN` | #00FFFF | 次强调色 |
| `CYBER_MAGENTA` | #FF0099 | 品红 |
| `CYBER_ORANGE` | #FF7700 | 橙色 |
| `CYBER_RED` | #FF0055 | 红色/危险 |
| `CYBER_GREEN` | #00FF99 | 绿色/成功 |
| **面板** | | |
| `CYBER_PANEL_BG` | #08081A | 面板背景 |
| `CYBER_CARD_BG` | #0E0E24 | 卡片背景 |
| `CYBER_BORDER` | #FF0055 | 边框 |
| `CYBER_TEXT` | #E8ECFF | 主文字 |
| `CYBER_TEXT_DIM` | #6677AA | 暗淡文字 |
| **遗物状态** | | |
| `COLOR_VAULTED` | = CYBER_RED | 已入库 |
| `COLOR_AVAILABLE` | = CYBER_GREEN | 可获取 |
| `COLOR_UNKNOWN` | #556688 | 未知 |
| **稀有度** | | |
| `COLOR_GOLD` | #FFD700 | 金色/罕见 |
| `COLOR_SILVER` | #00FFFF | 银色/常见 |
| `COLOR_COPPER` | #FF7700 | 铜色/普通 |
| **辅助色** | | |
| `SUBTLE_BORDER` | #1a1a3a | 微弱分割线 |
| `MUTED_TEXT` | #8E9CB2 | 次要文字 |
| `LIGHT_TEXT` | #C8D0E0 | 亮色文字 |
| `COLOR_BLACK` | #000000 | 纯黑 |
| `COLOR_DARK_GRAY` | #666666 | 深灰 |
| `COLOR_ENEMY` | #FF6B6B | 敌人掉落 |
| `COLOR_PURPLE` | #E066FF | 瞬时奖励 |
| `LINK_COLOR` | #5dade2 | 超链接 |
| **在线状态** | | |
| `STATUS_ONLINE` | #00ff88 | 在线 |
| `STATUS_INGAME` | #00d9ff | 游戏中 |
| `STATUS_OFFLINE` | #666666 | 离线 |
| `STATUS_AWAY` | #ffaa00 | 离开 |
| **按钮** | | |
| `BTN_DEFAULT_BG/TEXT/BORDER` | | 默认按钮 |
| `BTN_HOVER_BG/TEXT/BORDER` | | 悬停按钮 |
| `BTN_PRESSED_BG` | | 按下按钮 |
| `BTN_DISABLED_BG/TEXT/BORDER` | | 禁用按钮 |

#### 新增颜色的步骤

1. 在 `core/theme_config.py` 的 `_create_defaults()` 中添加 key 和默认值
2. 在 `core/theme_proxy.py` 中添加对应的 `_proxy('key')` 常量
3. 在 `core/theme_fields.py` 的 `THEME_FIELDS` 中添加编辑器字段（如需在主题面板中编辑）

#### 禁止事项

- **禁止**在 UI 代码中直接写十六进制颜色值：`f"color: #FFE600;"` → `f"color: {CYBER_YELLOW};"`
- **禁止**将 `_ThemeProxy` 对象直接传给 `QColor()`：`QColor(CYBER_YELLOW)` → `QColor(str(CYBER_YELLOW))`
- 唯一允许硬编码颜色的地方是 `core/theme_config.py` 的 `_create_defaults()` 中的默认值定义

### 6.8 数据库连接注册表

**背景：** 应用运行期间，多个模块会缓存 SQLite 连接（如 RelicDB、SearchWidget）。当用户在应用内执行"更新基础数据"时，`build_warframe_db.py` 需要替换 `warframe.db` 文件，但被缓存的连接持有文件锁导致 `[WinError 32]` 或 `[WinError 5]`。

**解决方案：** 集中式连接注册表 `data/db_connections.py`，所有缓存连接的模块在创建连接时注册、销毁时注销，构建前一键关闭全部连接。

#### 架构

```
data/db_connections.py          ← 注册表单例（_DBConnectionRegistry）
    ├── register(name, closer)   # 注册可关闭的连接
    ├── unregister(name)         # 注销连接
    ├── close_all()              # 一键关闭所有已注册连接
    └── registered_names()       # 调试用：返回已注册名称列表
```

#### 已注册的模块

| 注册名 | 模块 | 注册位置 | 关闭方法 |
|--------|------|----------|----------|
| `relic_db` | `data/wfinfo_relics.py` | `_get_conn()` 创建连接时 | `self.close()` |
| `search_widget` | `market_query/search_widget.py` | `_get_conn()` 创建连接时 | `self.close_db()` |

#### 调用时机

```python
# 构建前（panel_builder.py _launch_pipeline）
from data.db_connections import close_all_db_connections
pipeline = DataPipelineWorker(close_connections_fn=close_all_db_connections)

# 新模块接入示例
from data.db_connections import db_conn_registry

class MyModule:
    def _get_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(DB_PATH)
            db_conn_registry.register("my_module", self._close_db)
        return self._conn

    def _close_db(self):
        if self._conn: self._conn.close(); self._conn = None
        db_conn_registry.unregister("my_module")
```

### 6.9 物品查询模块

物品搜索由 `data/item_index.py` + `market_query/search_widget.py` 实现，支持多维度匹配。

#### 搜索优先级

```
用户输入 q
  ├─ [1] 精确匹配: name/zh_name = q          → 最高权重
  ├─ [2] 前缀匹配: name/zh_name LIKE 'q%'     → 高权重
  ├─ [3] 包含匹配: name/zh_name LIKE '%q%'     → 中权重
  └─ [4] 拼音匹配: zh_pinyin LIKE '%q%'         → 低权重（仅非中文输入触发）
```

#### 拼音搜索

- 数据源：`items.zh_pinyin` 字段（由 `build_warframe_db.py` 在构建时通过 `pypinyin.lazy_pinyin` 生成）
- 仅对**非中文输入**触发拼音搜索（避免中文字符被当作拼音误匹配）
- 示例：输入 `"shaluo"` → 匹配 `"沙罗之牙 Prime"` (zh_pinyin = `"shaluozhiyazhprime"`)

#### 遗物搜索过滤

搜索遗物时，结果只保留 **Intact（完好）版本**，自动过滤 Exceptional / Flawless / Radiant：

```python
# 输入 "Axi A1" → 只返回 "Axi A1 Intact"，不返回精炼版本
# 过滤逻辑：匹配 "Era Code State" 格式 → 仅保留 State="Intact"
```

#### 遗物悬浮窗（Tooltip）

鼠标悬停在搜索结果的遗物条目上时，显示详细信息面板：

```
┌─────────────────────────────┐
│ ◈ Axi S20 Intact [可获取]   │  ← 标题栏（状态颜色：入库=红/可获取=绿）
├─────────────────────────────┤
│ ■ 遗物内容 (N 个部件)        │
│   ● 稀有部件   罕见 (2.0%)  │  ← COLOR_GOLD 金色
│   ◦ 常见部件   常见 (11.0%) │  ← COLOR_SILVER 银色
│   ◇ 普通部件   普通 (25.3%) │  ← COLOR_COPPER 铜色
├─────────────────────────────┤
│ ■ 掉落来源 (M 条)           │  ← 仅出库遗物显示此区域
│   任务奖励 (K 条)           │
│     金星 - 节点名 (模式) ...│
│   赏金奖励 (L 条)           │
│     地点 Lv等级 ...         │
└─────────────────────────────┘
```

实现位置：`core/panel_builder.py` 的 `_format_relic_tooltip()` 方法。

关键逻辑：
- 遗物识别：支持 `"Era Code Relic"` 和 `"Era Code Intact"` 两种格式
- 部件翻译：三级回退（items.unique_name → items.name → game_translations.en）
- 掉落来源过滤：排除 `source_type='relics'`（反向映射）和遗物自身精炼版本
- 所有颜色均从 `theme_proxy.py` 获取，禁止硬编码

---

## 七、数据更新流程

### 7.1 拉取源数据

```bash
python scripts/pull_warframe_items.py
```

从 GitHub 仓库拉取最新 JSON 数据到 `external/` 目录，支持代理镜像自动重试。

### 7.2 构建数据库

```bash
python data/build_warframe_db.py
```

构建流程：
1. 创建 25 张表及索引（含 `items.zh_pinyin` 字段 + 索引）
2. 解析 All.json → items + 6 张子表
3. 解析 i18n.json → item_translations + 中文回填
4. 生成拼音数据：遍历 items 表有中文名的条目，用 `pypinyin.lazy_pinyin` 写入 `zh_pinyin`
5. 解析 all.json → 遗物/任务/敌人/特殊奖励
6. 解析 dict → game_translations
7. 拉取 WM API → market_items（可选）
8. 跨表关联（item_unique 回填）
9. VACUUM 优化

### 7.3 数据库构建策略（文件替换）

**问题：** 应用运行时 `warframe.db` 被多个模块的缓存连接锁定，直接 `unlink()` 删除或 `os.replace()` 替换都会因文件锁失败。

**当前方案：临时文件 + copy2 覆盖**

```
构建流程:
  ① 创建 warframe.db.new（全新文件，无锁定）→ 写入所有数据
  ② conn.close()
  ③ close_all_db_connections() ← 关闭注册表中所有缓存连接
  ④ sleep(0.5s) 等待锁释放
  ⑤ shutil.copy2(.db.new, .db) ← 覆盖写入（Windows 允许覆盖被读锁定的文件）
  ⑥ 清理 .new 临时文件
```

| 操作 | Windows 行为 | 结果 |
|------|-------------|------|
| `os.replace(.new, .db)` | 先删旧再重命名，需写锁 | `[WinError 5]` 拒绝访问 |
| `shutil.copy2(.new, .db)` | 直接覆盖写入，只需读锁 | **允许** |

> **注意：** 此方案非原子性（copy 中途崩溃可能损坏文件），但文件较小（~50-100MB）且 SSD 上拷贝 < 0.5s，实际风险极低。如需更高可靠性可改用 SQLite ATTACH 方案。

### 7.4 代理镜像配置

`data/proxy_mirrors.json` 存储 GitHub 代理列表和测试结果，每个仓库独立记录上次成功的代理索引。

---

## 八、构建与发布

### 开发运行

```bash
DEV_RUN.bat
# 或
python dev_runner.py
```

### 打包发布

使用 PyInstaller 打包为 Windows 可执行文件，UPX 压缩。

---

## 九、配置文件

| 文件 | 用途 | 格式 |
|------|------|------|
| `data/hotkeys.json` | 快捷键配置 | JSON |
| `data/feature_toggles.json` | 功能开关 | JSON |
| `data/proxy_mirrors.json` | 代理镜像配置 | JSON |
| `data/item_region.json` | 物品区域配置 | JSON |
| `data/language_preset.json` | 语言预设 | JSON |
| `data/window_geometry.json` | 窗口位置记忆 | JSON |
| `data/presets/*.json` | 主题预设 | JSON |
| `qt.conf` | Qt 运行时配置 | INI |

---

## 十、调试

### 崩溃日志

崩溃信息自动记录到 `%APPDATA%/WARFRAME-RELIC/crash_log.txt`。

### OCR 调试

使用 `open_ocr_debug.ps1` 启动 OCR 调试模式。

### 后台数据中心

管理面板底部入口，可查看：
- 数据链路可视化
- 数据库表结构和数据
- JSON 源文件格式化查看 + 搜索
- 操作日志
