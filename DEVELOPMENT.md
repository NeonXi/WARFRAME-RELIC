# WARFRAME-RELIC 开发文档

> 版本：v3.2 | 更新日期：2026-06-01

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

### 2.1 文件结构

```
WARFRAME-RELIC/
├── main.py                     # 程序入口（AppCore 中央控制器）
├── core/                       # 核心模块
│   ├── overlay.py              # 全屏透明覆盖层（标注、按钮、流式动画）
│   ├── region_selector.py      # ★ 独立区域框选器（封装鼠标交互）
│   ├── management_panel.py     # 管理面板主窗口（搜索/数据库/热键/主题）
│   ├── price_service.py        # 价格服务（三级查询 + 限速器）
│   ├── relic_tooltip.py        # ★ 遗物内容悬浮窗
│   ├── drop_tooltip.py         # ★ 物品掉落来源查询
│   ├── hotkey_config.py        # 热键配置管理
│   ├── hotkey_capture_button.py # 热键捕获按钮组件
│   ├── stylesheet.py           # 动态 QSS 样式表
│   ├── theme_config.py         # 主题配置引擎
│   ├── theme_fields.py         # 主题字段定义
│   ├── theme_panel.py          # 主题可视化编辑面板
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
│   ├── ui_strings.py           # UI 字符串路由器
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
│   └── all_items.json          # WFInfo 全量掉落数据
├── DATABASE.md                 # ★ 数据库结构详细文档
├── README.md                   # 用户使用文档
├── requirements.txt            # Python 依赖
├── main.py                     # 入口
├── dev_runner.py               # 开发热重载脚本
├── build_exe.py                # PyInstaller 打包（文件夹模式）
├── build_onefile.py            # PyInstaller 打包（单文件模式）
└── 打包.bat / 打包单文件.bat   # 打包批处理
```

### 2.2 架构分层

```
┌─────────────────────────────────────────────────┐
│  UI 层 (PyQt6)                                  │
│  Overlay + ManagementPanel + RelicTooltip       │
├─────────────────────────────────────────────────┤
│  业务层 (AppCore)                                │
│  截图 → OCR → 匹配 → 查询 → 标注               │
├─────────────────────────────────────────────────┤
│  服务层                                         │
│  PriceService / RegionSelector / DropSourceIndex │
├─────────────────────────────────────────────────┤
│  数据层 (SQLite)                                 │
│  items_i18n.db / relics.db / wm_prices.db       │
└─────────────────────────────────────────────────┘
```

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

**启动流程：**
```
main()
  → 单例检测（Windows Mutex）
  → 管理员权限检测
  → 安装全局异常钩子（crash_log.txt）
  → 创建 QApplication
  → 创建 AppCore(app)
  → core.run()
      → _init_db()           # 加载 relics.db
      → _bind_events()       # 绑定信号/槽
      → _register_initial_hotkeys()  # 注册全局热键
      → _print_startup_info()
      → _show_panel_on_start()       # 显示管理面板
      → _hotkey_health_timer.start() # 30秒热键心跳检测
      → app.exec()            # 进入 Qt 事件循环
```

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

### 3.2 RegionSelector (`core/region_selector.py`) — ★ 新增模块

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

### 3.3 Overlay (`core/overlay.py`) — 覆盖层

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

### 3.4 ManagementPanel (`core/management_panel.py`) — 管理面板

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

**★ 物品检索（新增）：**
- 支持中文、英文、拼音三种输入方式
- 实时联想（`suggest_items()`）
- 单击结果复制英文名到剪贴板
- 悬停显示掉落来源 Tooltip（`DropSourceIndex`）

### 3.5 RelicTooltip (`core/relic_tooltip.py`) — ★ 新增模块

遗物内容悬浮窗，在 overlay 上显示可拖动的半透明窗口。

**功能：**
- 显示识别到的遗物及其包含的部件
- 按稀有度着色（金银铜）
- 出入库状态标识
- 可拖动（拖标题栏移动）
- 赛博朋克深色风格
- 右键清除时自动隐藏

### 3.6 DropTooltip (`core/drop_tooltip.py`) — ★ 新增模块

物品掉落来源查询，构建 `all.json` → 物品→掉落来源的内存索引。

**功能：**
- 查询物品的掉落来源（星球/节点/任务类型/轮次/概率）
- 星球名中文化（如 Mercury→水星）
- 生成 HTML 格式的 Tooltip
- 在管理面板的物品检索中使用

### 3.7 PriceService (`core/price_service.py`) — 价格服务

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

### 3.8 Matcher (`recognizers/matcher.py`) — 匹配引擎

4 轮降级匹配策略：

```
match_items(ocr_texts)
  对每个 OCR 文本：
    第1轮: 精确匹配 en_name（大小写不敏感）
    第2轮: 前缀匹配
    第3轮: 包含匹配（纠错候选 variants）
    第4轮: 部件蓝图直通（自动补全 Prime）
```

**★ 精炼过滤（新增）：**
- 过滤遗物精炼版本（Intact/Exceptional/Flawless/Radiant）
- 只保留基础遗物名称（如 "Lith A1 Radiant" → "Lith A1 Relic"）

### 3.9 items_i18n (`data/items_i18n.py`) — 中英对照数据库

**★ 拼音搜索（新增）：**
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
              → _handle_check_status()    # 出入库
              → _handle_query_parts()     # 部件查询
              → _handle_query_price()     # 价格查询
              → _handle_translate()       # 翻译
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
      → _render_price_direct()  # 直接渲染价格标注
```

### 4.4 紧急排障流程（_on_reset）

```
管理面板点击"紧急排障" → AppCore._on_reset()
  1. 终止所有后台线程（OCR）
  2. 清空所有缓存数据
  3. 清除 Overlay 所有视觉元素
  4. 退出框选模式
  5. 恢复鼠标穿透
  6. 强制重新注册快捷键（默认值）
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
| 热键心跳 | 30 秒定时器 | 自动检测+恢复失效热键 |

---

## 六、文案预设系统

三套独立文案文件，管理面板一键切换，即时生效：

```
language_preset.json → ui_strings.py (路由器)
  ├── preset_cyberpunk2077.py  (默认，赛博朋克2077)
  ├── preset_santi.py          (三体·威慑纪元)
  └── preset_normal.py         (普通标准)
```

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

**自定义预设：** 创建 `data/preset_xxx.py` → 注册到 `language_preset.json` → 即时可用。

---

## 七、主题系统

`ThemeConfig` 单例管理 65 个配色字段：

| 配色组 | 字段数 | 说明 |
|--------|--------|------|
| 基础色 | 6 | 主色、强调色、背景色等 |
| 覆盖层 | 8 | 标注文字、背景、边框 |
| 面板 | 20+ | 管理面板各组件颜色 |
| 按钮 | 10+ | 按钮正常/悬停/按下状态 |
| 其他 | ~20 | 滚动条、进度条等 |

**切换方式：**
- 管理面板 → 主题换肤 → 点击色块取色 → 实时预览 → 保存
- 预设切换：赛博朋克2077 / 日光 / 自定义

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

## 十、v3.2 更新记录

| 变更 | 说明 |
|------|------|
| RegionSelector | 框选逻辑从 Overlay 解耦为独立模块 |
| RelicTooltip | 新增遗物内容悬浮窗（可拖动） |
| DropTooltip | 新增物品掉落来源查询 + Tooltip |
| 拼音搜索 | items_i18n.db 新增 zh_pinyin 字段，支持拼音搜索 |
| 精炼过滤 | matcher 自动过滤遗物精炼版本 |
| 热键简化 | 移除 panel 热键，面板改为启动即显示 |
| 价格查询热键 | `Ctrl+Shift+P` → `Ctrl+T` |
| 面板重构 | 关闭面板 = 退出程序，新增物品检索标签页 |
| 文案更新 | 三套预设同步更新（移除 panel 相关，新增拼音提示） |
