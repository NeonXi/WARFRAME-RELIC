# WARFRAME-RELIC 开发文档

> 版本：v3.4 | 更新日期：2026-06-02

## 一、项目概述

WARFRAME-RELIC 是一个 Warframe（星际战甲）游戏辅助工具，基于 OCR 识别技术，提供遗物出入库状态查询、物品市场价格查询、中英翻译等功能。采用 PyQt6 + RapidOCR + dxcam 技术栈，以半透明覆盖层的方式在游戏画面上无侵入显示结果。

### 核心功能

| 功能 | 快捷键 | 说明 |
|------|--------|------|
| 框选截图 | `Ctrl+G` | 拖拽框选区域 → 松手自动截图识别 |
| 全屏截图 | `Ctrl+H` | 直接全屏截图识别 |
| 价格查询 | `Ctrl+T` | 自动4等分截图+识别+标注价格 |
| 右键清除 | 右键 | 清除所有标注和按钮 |

截图后显示功能按钮，用户可选择：
- **出入库查询** — 标注遗物当前是否可获取（绿色出库/红色入库）
- **遗物内容查询** — 显示遗物内含部件及稀有度（金银铜色区分）
- **价格查询** — 查询 warframe.market 实时市场价格
- **翻译** — 中英文双向翻译

---

## 二、项目架构

### 2.1 文件结构（v3.4 重构后）

```
WARFRAME-RELIC/
├── main.py                     # 程序核心：AppCore + TriggerBridge + OCRWorker
├── core/                       # 核心模块
│   ├── bootstrap.py            # ★ 启动引导：单例检测、管理员检测、异常钩子、main()
│   ├── hotkey_manager.py       # ★ 热键管理器：注册/健康检查/自动恢复/防重入
│   ├── mode_handlers.py        # ★ 功能处理器：出入库/遗物查询/翻译/价格标注（纯函数）
│   ├── overlay.py              # 全屏透明覆盖层（标注、按钮、流式动画）
│   ├── region_selector.py      # ★ 独立区域框选器（封装鼠标交互）
│   ├── management_panel.py     # 管理面板主窗口（搜索/数据库/热键/主题）
│   ├── price_service.py        # 价格服务（三级查询 + 限速器）
│   ├── drop_tooltip.py         # ★ 物品掉落来源查询
│   ├── hotkey_config.py        # 热键配置读写
│   ├── hotkey_capture_button.py # 热键捕获按钮组件
│   ├── stylesheet.py           # 动态 QSS 样式表
│   ├── theme_config.py         # 主题配置引擎
│   ├── theme_fields.py         # 主题字段定义
│   ├── theme_panel.py          # 主题可视化编辑面板
│   ├── theme_proxy.py          # 主题属性代理
│   ├── update_panel.py         # 数据库更新面板
│   ├── fetch_worker.py         # 后台下载线程
│   ├── update_worker.py        # 后台更新线程
│   ├── word_wrap_button.py     # 自动换行按钮
│   └── constants.py            # 颜色/常量/主题
├── recognizers/                # 识别器
│   ├── base_ocr.py             # OCR 管线基类
│   ├── relic_name.py           # 遗物名称 OCR 识别器
│   ├── item_name.py            # 物品名称 OCR 识别器
│   └── matcher.py              # 物品匹配引擎（4轮降级匹配）
├── data/                       # 数据和配置
│   ├── items_i18n.py           # 全物品中英对照数据库管理
│   ├── wfinfo_relics.py        # 遗物数据库查询
│   ├── wm_prices.py            # WM 价格数据库管理
│   ├── translation_db.py       # 翻译数据库（旧版）
│   ├── db_utils.py             # 数据库工具函数
│   ├── ui_strings.py           # UI 字符串路由器
│   ├── icons.py                # 图标资源管理
│   ├── icon_loader.py          # 图标加载器
│   ├── version.py              # 版本信息
│   ├── preset_cyberpunk2077.py # 赛博朋克2077文案预设
│   ├── preset_santi.py         # 三体·威慑纪元文案预设
│   ├── preset_normal.py        # 普通标准文案预设
│   ├── language_preset.json    # 语言预设配置
│   ├── feature_toggles.json    # 功能开关配置
│   ├── hotkeys.json            # 热键配置文件
│   ├── item_region.json        # 物品区域配置文件
│   ├── items_i18n.db           # 物品中英对照数据库（含拼音）
│   ├── relics.db               # 遗物掉落数据库
│   ├── wm_prices.db            # WM 价格缓存数据库
│   ├── translation.db          # 翻译缓存（旧版）
│   └── all_items.json          # WFInfo 全量掉落数据
├── assets/                     # SVG 图标资源
├── icon/                       # 图标资源
├── DATABASE.md                 # ★ 数据库结构详细文档
├── README.md                   # 用户使用文档
├── requirements.txt            # Python 依赖
├── dev_runner.py               # 开发热重载脚本
├── build_exe.py                # PyInstaller 打包（文件夹模式）
├── build_onefile.py            # PyInstaller 打包（单文件模式）
├── SETUP.bat                   # 零基础启动脚本
├── WARFRAME-RELIC.bat          # 快捷启动批处理
├── DEV_RUN.bat                 # 开发模式批处理
└── 打包.bat / 打包单文件.bat / 一键打包.bat  # 打包批处理
```

### 2.2 架构分层

```
┌─────────────────────────────────────────────────┐
│  UI 层 (PyQt6)                                  │
│  Overlay + ManagementPanel + RelicTooltip       │
├─────────────────────────────────────────────────┤
│  业务层                                          │
│  AppCore (main.py) — 中央控制器                  │
│  ├── HotkeyManager (hotkey_manager.py) — 热键   │
│  └── mode_handlers (mode_handlers.py) — 功能    │
├─────────────────────────────────────────────────┤
│  服务层                                          │
│  PriceService / RegionSelector / DropSourceIndex │
├─────────────────────────────────────────────────┤
│  入口层                                          │
│  bootstrap.py — 单例/管理员/异常钩子/main()     │
├─────────────────────────────────────────────────┤
│  数据层 (SQLite)                                 │
│  items_i18n.db / relics.db / wm_prices.db       │
└─────────────────────────────────────────────────┘
```

### 2.3 v3.4 架构重构说明

v3.4 将原本 1430 行的 `main.py` 拆分为 4 个文件：

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | ~813 | `AppCore` + `TriggerBridge` + `OCRWorker`（截图/OCR线程/分发） |
| `core/hotkey_manager.py` | ~213 | 热键注册/更新/健康检查/自动恢复/防重入 |
| `core/mode_handlers.py` | ~242 | 四大功能：出入库查询、遗物内容查询、翻译、价格标注（纯函数） |
| `core/bootstrap.py` | ~200 | 入口：单例检测、管理员检测、异常钩子、`main()` |

**设计原则**：
- `HotkeyManager` 封装所有热键逻辑，`AppCore` 通过委托调用
- `mode_handlers` 作为纯函数模块，接收状态参数，避免循环依赖
- `bootstrap` 处理所有系统级入口逻辑，与业务逻辑解耦

---

## 三、核心模块详解

### 3.1 AppCore (`main.py`) — 中央控制器

`AppCore` 是所有业务逻辑的中心协调者，管理整个生命周期。

**组件持有：**

| 组件 | 类型 | 作用 |
|------|------|------|
| `_camera` | `dxcam` | DirectX 高速截图 |
| `_overlay` | `Overlay` | 全屏透明覆盖层 |
| `_management_panel` | `ManagementPanel` | 设置面板主窗口 |
| `_relic_ocr` | `RelicNameRecognizer` | 遗物名称 OCR |
| `_item_ocr` | `ItemNameRecognizer` | 物品名称 OCR |
| `_relic_db` | `RelicDB` | 遗物数据库 |
| `_bridge` | `TriggerBridge` | 热键→Qt信号桥接 |
| `_hotkey_mgr` | `HotkeyManager` | ★ 热键管理器（委托） |

**核心状态变量：**

```python
self._last_frame = None       # 最近一次截图帧（numpy array）
self._last_region = None      # 最近一次截图区域（逻辑坐标）
self._last_relics = []        # OCR 缓存：遗物结果
self._last_items = []         # OCR 缓存：物品结果
self._last_texts = []         # OCR 缓存：文本结果
self._ocr_thread = None       # 当前 OCR 线程
self._ocr_lock = threading.Lock()  # OCR 线程锁
```

**启动流程（简化）：**

```
main()
  → bootstrap.ensure_singleton()     # Windows Mutex 单例检测
  → bootstrap.ensure_admin()         # 管理员权限检测
  → bootstrap.install_crash_handlers() # 全局异常钩子
  → QApplication 创建
  → AppCore(app) 创建
  → core.run()
      → _init_db()
      → _bind_events()
      → _hotkey_mgr.register_initial()   # ★ 委托 HotkeyManager
      → _show_panel_on_start()
      → _hotkey_health_timer.start()     # 30秒热键心跳
      → app.exec()
```

### 3.2 HotkeyManager (`core/hotkey_manager.py`) — ★ 新增模块

从 `AppCore` 拆分出来的热键管理逻辑，职责单一。

**公开接口：**

| 方法 | 说明 |
|------|------|
| `register_initial()` | 启动时从配置文件加载并注册热键 |
| `on_config_changed(new_hotkeys)` | 用户修改热键后重新注册 |
| `health_check()` → bool | 诊断热键健康状态 |
| `auto_recover()` | 30秒心跳：检测到异常自动恢复 |
| `force_reset()` | 紧急重置：用硬编码默认值强制重注册 |
| `clear()` | 注销所有热键（退出时调用） |

**热键注册流程（`_register()`）：**

```
1. 权限检查 → 非管理员弹 warning
2. 逐个清除旧热键
3. unhook_all() 兜底
4. 逐键注册（最多3次重试，失败回退到默认值）
5. 全部失败 → 用硬编码默认值紧急恢复
6. health_check() 诊断
```

### 3.3 Mode Handlers (`core/mode_handlers.py`) — ★ 新增模块

四大功能处理为纯函数，接收 `AppCore` 的状态作为参数，避免循环依赖。

**导出函数：**

| 函数 | 功能 | 参数 |
|------|------|------|
| `handle_check_status(last_relics, relic_db, region, dpi, overlay)` | 出入库状态查询 | 遗物列表 + 数据库 + 区域 + DPI + 覆盖层 |
| `handle_query_parts(last_relics, relic_db, region, dpi, overlay)` | 遗物内容查询 | 同上 |
| `handle_translate(last_items, region, dpi, overlay)` | 翻译 | 物品列表 + 区域 + DPI + 覆盖层 |
| `handle_query_price(last_items, region, dpi, overlay)` | 价格查询 | 同上 |
| `render_price_annotations(matched, region, dpi, overlay)` | 价格标注渲染 | 匹配结果 + 区域 + DPI + 覆盖层 |
| `strip_refinement(name)` → str | 去除精炼标签 | 遗物名称字符串 |

### 3.4 Bootstrap (`core/bootstrap.py`) — ★ 新增模块

系统级入口逻辑，与业务完全解耦。

**导出函数：**

| 函数 | 说明 |
|------|------|
| `ensure_singleton()` → bool | Windows Mutex 单例检测 |
| `ensure_admin()` → bool | 管理员权限检测 + 弹窗提示 |
| `install_crash_handlers()` | 安装全局异常钩子 + atexit 清理 |
| `main()` | 程序主入口函数 |

**main() 执行流程：**

```python
def main():
    ensure_singleton()        # 单例检测
    ensure_admin()            # 管理员检测
    install_crash_handlers()  # 异常钩子
    app = QApplication()
    app.setStyleSheet(...)    # 全局 ToolTip 样式
    core = AppCore(app)
    core.run()
```

### 3.5 RegionSelector (`core/region_selector.py`)

独立的区域框选器，从 Overlay 中解耦出来，职责单一。

**设计原则：**
- 不依赖 Overlay 的业务逻辑
- 不依赖 main.py 的截图逻辑
- 仅负责：显示框选界面 → 用户拖拽 → 返回区域坐标

**坐标体系：**

```python
region_info = {
    'logical':  (left, top, right, bottom),     # Qt 逻辑坐标
    'physical': (left, top, right, bottom),     # 屏幕物理坐标（dxcam 用）
    'physical_xywh': {'x': int, 'y': int, 'w': int, 'h': int},  # 物理 xywh
    'dpi_scale': float,                         # DPI 缩放比例
}
```

**回调机制：**

```python
selector.set_callback(
    callback=on_region_selected,   # 框选完成
    on_cancelled=on_cancelled,     # 框选取消（ESC/右键）
)
```

**复用场景：**
- 默认框选截图（`AppCore._on_region_selection_for_screenshot`）
- 物品区域设置（`AppCore._on_item_region_select`）

### 3.6 Overlay (`core/overlay.py`) — 覆盖层

全屏透明 QWidget，三种状态：

| 状态 | 鼠标穿透 | 功能 |
|------|----------|------|
| 空闲 | ✓ 穿透 | 仅显示标注文字 |
| 框选 | ✗ 拦截 | RegionSelector 处理鼠标拖拽 |
| 标注 | 穿透（按钮不穿透） | 显示结果 + 功能按钮 |

**标注系统：**
- `show_annotations()` — 一次性显示全部
- `show_annotations_stream()` — 流式逐条动画（可配 interval_ms / batch_size）
- 支持多行文本 + 逐行颜色

**框选委托：**
- 框选交互完全委托给 `RegionSelector`
- `Overlay.paintEvent()` → `RegionSelector.paint()`

### 3.7 ManagementPanel (`core/management_panel.py`) — 管理面板

主窗口，启动即显示，关闭面板 = 退出程序。

**功能分区：**

| 标签页 | 功能 |
|--------|------|
| 数据库 | 遗物数据库状态 / 自动更新 / 手动导入 |
| 翻译数据 | items_i18n.db 状态 / 重建 |
| 价格数据 | wm_prices.db 状态 / 物品区域设置 |
| ★ 物品检索 | 中/英/拼音实时搜索 + 掉落来源悬浮提示 |
| 快捷键 | 热键捕获 / 修改 / 重置 |
| 功能开关 | 截图后显示哪些功能按钮 |
| 主题换肤 | 取色器编辑 / 预设切换 |
| 文案风格 | 赛博朋克/三体/普通 一键切换 |
| 日志 | 实时运行日志 |

**★ 物品检索：**
- 支持中文、英文、拼音三种输入方式
- 实时联想（`suggest_items()`）
- 单击结果复制英文名到剪贴板
- 悬停显示掉落来源 Tooltip（`DropSourceIndex`）

### 3.8 PriceService (`core/price_service.py`) — 价格服务

三级查询策略：

```
query_price(en_name)
  → L1: 内存缓存（最快）
  → L2: wm_prices.db SQLite（较快）
  → L3: warframe.market API（慢，需联网）
      → 解析 JSON 响应
      → 更新缓存 + 数据库
      → 返回价格
```

**限速器：** 令牌桶算法，控制 API 请求频率。

**价格着色：**

```python
def price_to_color(price, quality):
    # 精确匹配 + 高价 → 金色
    # 模糊匹配 + 有价格 → 银色
    # 无价格 → 灰色
```

### 3.9 Matcher (`recognizers/matcher.py`) — 匹配引擎

4 轮降级匹配策略：

```
match_items(ocr_texts)
  对每个 OCR 文本：
    第1轮: 精确匹配 en_name（大小写不敏感）
    第2轮: 前缀匹配
    第3轮: 包含匹配（纠错候选 variants）
    第4轮: 部件蓝图直通（自动补全 Prime）
```

**★ 精炼过滤：**
- 过滤遗物精炼版本（Intact/Exceptional/Flawless/Radiant）
- 只保留基础遗物名称（如 "Lith A1 Radiant" → "Lith A1 Relic"）

### 3.10 items_i18n (`data/items_i18n.py`) — 中英对照数据库

**★ 拼音搜索：**
- 新增 `zh_pinyin` 字段
- 使用 `pypinyin` 库生成拼音
- 支持拼音搜索（全拼+首字母）
- Schema 自动迁移（旧数据库自动添加字段并回填拼音）

**数据来源（三层融合）：**
1. WFCD 官方数据（GitHub）
2. AdminRoc 社区数据
3. 程序运行时增量补充（部件直通机制）

---

## 四、数据流

### 4.1 框选截图流程

```
Ctrl+G → TriggerBridge.fired('select')
  → AppCore._on_hotkey('select')
    → overlay.start_selection()
      → RegionSelector.start()
        → 鼠标拖拽框选
        → 释放鼠标 → callback(region_info)
          → AppCore._on_region_selection_for_screenshot()
            → _on_selection_done()
              → camera.grab(region)
              → _after_screenshot(frame, logical)
                → 保存 debug 截图
                → overlay.show_mode_buttons(enabled_modes)
```

### 4.2 功能按钮点击流程

```
用户点击按钮 → overlay.mode_selected.emit(mode)
  → AppCore._on_mode_selected(mode)
    → 检查 OCR 缓存
    → 有缓存 → 直接 _execute_mode(mode)
    → 无缓存 → _start_ocr(ocr_type, callback)
        → OCRWorker.run() in QThread
        → finished.emit(results)
        → _on_ocr_done(results, ocr_type, callback)
          → 缓存结果
          → callback(results)
            → _execute_mode(mode)
              → mode_handlers.handle_check_status()   # 出入库
              → mode_handlers.handle_query_parts()    # 部件查询
              → mode_handlers.handle_query_price()    # 价格查询
              → mode_handlers.handle_translate()      # 翻译
```

### 4.3 价格查询快捷键流程（Ctrl+T）

```
Ctrl+T → AppCore._on_hotkey('query_price')
  → _do_price_query()
    → load_item_region()  # 加载物品区域配置
    → 计算4等分坐标
    → overlay.show_split_regions()  # 显示4等分框线
    → _do_price_query_capture()
      → camera.grab(完整区域)  # 一次截图，避免连续 grab 返回 None
      → numpy 切片分4份
      → 逐份 OCR 识别
      → match_and_price()  # 匹配+查价
      → mode_handlers.render_price_annotations()  # 直接渲染价格标注
```

### 4.4 紧急排障流程（_on_reset）

```
管理面板点击"紧急排障" → AppCore._on_reset()
  1. 终止所有后台线程（OCR）
  2. 清空所有缓存数据
  3. 清除 Overlay 所有视觉元素
  4. 退出框选模式
  5. 恢复鼠标穿透
  6. HotkeyManager.force_reset() 强制重新注册快捷键（默认值）
  7. 重置 hotkeys.json
  8. 摄像头健康检查
  9. 同步管理面板 UI
  10. 健康诊断 + 日志报告
```

---

## 五、线程安全

| 机制 | 实现 | 说明 |
|------|------|------|
| OCR 线程 | `QThread` + `finished` 信号 | 超时 2s 强制终止 |
| 价格查询 | `ThreadPoolExecutor` | 最多 4 路并发 |
| 截图竞态 | `_screenshot_lock`（隐式） | 防重入 500ms 间隔 |
| 退出清理 | `aboutToQuit` → `_shutdown()` | 统一释放资源 |
| 热键心跳 | 30 秒定时器 → `HotkeyManager.auto_recover()` | 自动检测+恢复失效热键 |

---

## 六、文案预设系统

### 6.1 架构设计

三套独立文案文件，管理面板一键切换，即时生效：

```
language_preset.json → ui_strings.py (路由器)
  ├── preset_cyberpunk2077.py  (默认，赛博朋克2077)
  ├── preset_santi.py          (三体·威慑纪元)
  └── preset_normal.py         (普通标准)
```

**核心组件：**

| 组件 | 文件 | 职责 |
|------|------|------|
| 路由器 | `data/ui_strings.py` | 提供 `S("category", "key")` 访问接口，管理预设加载和切换 |
| 配置文件 | `data/language_preset.json` | 保存当前激活的预设 ID |
| 预设文件 | `data/preset_*.py` | 定义 `STRINGS` 字典，包含所有 UI 文本 |

**预设文件结构：**

```python
STRINGS = {
    "category": {
        "key": "文案内容",
        "key_with_placeholder": "文案 {var} 内容",
    },
    ...
}
```

**使用方式：**

```python
from data.ui_strings import S, set_language_preset

# 获取文本
text = S("button", "exit")  # 返回："退出程序"

# 格式化文本
text = S.format("stat", "count", number=42)  # 返回："42 个"

# 切换预设
set_language_preset("cyberpunk2077")  # 切换到赛博朋克2077版（默认）
set_language_preset("santi")          # 切换到三体版
set_language_preset("normal")         # 切换到普通版
```

### 6.2 工作原理

1. **初始化加载**：程序启动时从 `language_preset.json` 读取当前激活的预设 ID，加载对应的 `preset_*.py` 文件中的 `STRINGS` 字典到全局变量。

2. **访问文本**：通过 `S("category", "key")` 访问文本，如果 key 不存在则返回 `??category.key??` 占位符。

3. **切换预设**：调用 `set_language_preset(preset_id)` 时：
   - 加载新预设的 `STRINGS` 字典
   - 更新全局 `STRINGS` 变量
   - 保存新预设 ID 到 `language_preset.json`
   - 触发 UI 刷新（通过 `_rebuild_ui_for_preset()`）

4. **UI 刷新机制**：
   - 所有需要动态更新文本的控件通过 `_reg_text(widget, category, key)` 注册到 `_text_registry`
   - 切换预设时遍历 `_text_registry`，调用 `widget.setText(S(category, key))` 更新文本
   - **注意**：显示动态数据的控件（如数据库统计值）不应注册，由专门的 `refresh_*()` 方法重新填充

### 6.3 添加新预设

1. 创建 `data/preset_xxx.py` 文件，定义 `STRINGS` 字典
2. 在 `data/language_preset.json` 中添加预设信息：
   ```json
   {
     "active": "cyberpunk2077",
     "presets": {
       "xxx": {
         "name": "预设名称",
         "desc": "预设描述"
       }
     }
   }
   ```
3. 重启程序或手动切换即可使用

### 6.4 图标与文案解耦

**重要原则**：文案预设文件中**不应包含任何图标符号**（如 Unicode 字符 ⊞、◎、⟐ 等）。

**原因**：
- 图标由 `icon_loader.py` 统一管理，通过 `ICON_MAPPINGS` 配置映射关系
- 文案只负责纯文本，图标由 UI 层从 `icon_loader` 动态获取
- 这样切换文案预设时，图标保持不变，实现真正的解耦

---

## 七、主题系统

### 7.1 架构设计

`ThemeConfig` 单例管理 65+ 个配色字段，支持多预设切换和实时预览。

**核心组件：**

| 组件 | 文件 | 职责 |
|------|------|------|
| 主题管理器 | `core/theme_config.py` | 单例 `ThemeConfig`，管理配色加载/保存/预设切换 |
| 主题字段定义 | `core/theme_fields.py` | 定义所有主题字段的元数据（名称、分类、默认值） |
| 主题编辑面板 | `core/theme_panel.py` | 可视化取色器、预设切换、实时预览 |
| 样式表生成器 | `core/stylesheet.py` | 根据当前主题生成全局 QSS 样式表 |
| 主题代理 | `core/theme_proxy.py` | 提供便捷的属性访问（`theme.cyber_yellow`） |

**预设类型：**

| 预设 ID | 名称 | 说明 |
|---------|------|------|
| `cyberpunk` | 赛博朋克2077 | 深色霓虹风格（默认） |
| `daylight` | 白天模式 | 浅色明亮风格 |
| `custom` | 自定义 | 用户自定义配色 |

### 7.2 样式刷新策略

**问题**：Qt 控件的样式分为**全局样式表**和**内联样式**两种，切换主题后需要分别刷新。

**解决方案**：

1. **全局样式表**（自动生效）：
   ```python
   self.setStyleSheet(build_stylesheet())  # 应用到整个窗口
   ```

2. **内联样式**（需手动刷新）：
   ```python
   def _refresh_inline_styles(self):
       t = theme
       self._nav_list.setStyleSheet(f"""
           QListWidget {{
               background-color: {t.panel_darkest};
               color: {t.text_dim};
           }}
       """)
   ```

**最佳实践**：
- **优先使用全局样式表**：减少内联样式的使用，降低维护成本
- **统一刷新入口**：所有样式刷新逻辑集中在 `_refresh_inline_styles()` 方法中

---

## 八、调试与开发

### 8.1 开发模式

```bash
# 热重载模式（修改 .py 自动重启）
python dev_runner.py

# 或双击
DEV_RUN.bat
```

### 8.2 调试截图

每次截图自动保存到：
```
%APPDATA%/WARFRAME-RELIC/debug/last_capture.png
```

### 8.3 崩溃日志

未捕获异常自动记录到：
```
%APPDATA%/WARFRAME-RELIC/crash_log.txt
```

### 8.4 数据库操作

```bash
# 重建全物品中英对照数据库
python data/items_i18n.py --rebuild

# 拉取全量 warframe.market 价格数据
python data/wm_prices.py --fetch

# 查看价格数据库统计
python data/wm_prices.py --stats

# 查询单个物品价格
python data/wm_prices.py --search "Braton Prime Set"

# 批量查询物品价格
python data/wm_prices.py --search-batch "Braton Prime Set,Ash Prime Chassis"

# 更新遗物掉落数据
python data/update_db.py
```

### 8.5 打包

```bash
# 文件夹模式（推荐，启动快）
python build_exe.py
# 输出: dist/WARFRAME-RELIC/

# 单文件模式（分发方便，启动慢10-15秒）
python build_onefile.py
# 输出: dist/WARFRAME-RELIC.exe
```

---

## 九、技术栈

| 依赖 | 版本 | 用途 |
|------|------|------|
| PyQt6 | ≥6.11.0 | GUI 框架 |
| dxcam | ≥0.3.0 | DirectX 高速截图 |
| keyboard | ≥0.13.5 | 全局热键 |
| rapidocr-onnxruntime | ≥1.4.4 | OCR 引擎 |
| Pillow | ≥12.0.0 | 图像处理 |
| numpy | ≥2.0.0 | 数组运算 |
| pypinyin | ≥0.51.0 | ★ 中文拼音转换 |

---

## 十、v3.4 更新记录

### 架构重构（模块化拆分）

| 变更 | 说明 | 文件 |
|------|------|------|
| **HotkeyManager** | 热键管理独立模块：注册/健康检查/自动恢复/防重入 | `core/hotkey_manager.py` |
| **Mode Handlers** | 四大功能处理为纯函数：出入库/遗物查询/翻译/价格标注 | `core/mode_handlers.py` |
| **Bootstrap** | 入口逻辑独立：单例检测/管理员检测/异常钩子/main() | `core/bootstrap.py` |
| **main.py 精简** | 1430行 → 813行（减少43%），聚焦 AppCore 核心控制逻辑 | `main.py` |

### 数据库性能优化（P0优先级）

| 变更 | 说明 | 文件 |
|------|------|------|
| **Schema版本管理** | 新增 `SCHEMA_VERSION` 常量，自动检测并升级旧版数据库 | `items_i18n.py` |
| **批量插入优化** | 使用 `executemany()` 替代逐条INSERT，每500条提交一次 | `items_i18n.py` |
| **拼音完整性检查** | 新增 `check_pinyin_integrity()` 函数，启动时自动检测缺失拼音 | `items_i18n.py` |
| **拼音自动修复** | 新增 `repair_pinyin_data()` 函数，批量修复缺失的拼音数据 | `items_i18n.py` |
| **命令行工具** | 添加 `--check-pinyin` / `--repair-pinyin` 命令 | `items_i18n.py` |

**性能提升：**
- 数据库重建速度：**30-60秒 → 5-10秒**（提升5-10倍）
- SQL调用次数：**17564次 → 36次**（批量插入）
- 拼音完整率：**0% → 100%**（自动修复）

### 框选交互修复

| 变更 | 说明 | 文件 |
|------|------|------|
| **Overlay状态重置** | 启动框选前重置 `_right_was_down` 和 `_ignore_right_until` | `overlay.py` |
| **RegionSelector延迟启动** | 检测到右键按下时延迟100ms启动，等待鼠标状态稳定 | `region_selector.py` |

### 打包配置优化

| 变更 | 说明 | 文件 |
|------|------|------|
| **新模块声明** | 添加 `core.bootstrap`、`core.hotkey_manager`、`core.mode_handlers` 到 hidden-import | `build_exe.py`, `build_onefile.py` |
| **pypinyin依赖声明** | 添加hidden-import确保打包后拼音功能正常 | `build_exe.py`, `build_onefile.py` |

---

## 十一、v3.3 更新记录

| 变更 | 说明 |
|------|------|
| 主题系统优化 | 修复切换预设时部分区域颜色未更新的问题 |
| 导航顺序修正 | 调整导航栏顺序与面板模块上下顺序完全一致 |
| 文案预设清理 | 移除所有预设文件中的硬编码图标符号，实现图标与文案完全解耦 |
| 图标映射优化 | 为所有导航项和功能按钮分配更合适的唯一图标 |
| 数据库状态修复 | 修复切换预设时数据库健康监测区域数据不显示的问题 |

---

## 十二、v3.2 更新记录

| 变更 | 说明 |
|------|------|
| RegionSelector | 框选逻辑从 Overlay 解耦为独立模块 |
| 拼音搜索 | items_i18n.db 新增 zh_pinyin 字段，支持拼音搜索 |
| 精炼过滤 | matcher 自动过滤遗物精炼版本 |
| 热键简化 | 移除 panel 热键，面板改为启动即显示 |
| 价格查询热键 | `Ctrl+Shift+P` → `Ctrl+T` |
| 面板重构 | 关闭面板 = 退出程序，新增物品检索标签页 |
