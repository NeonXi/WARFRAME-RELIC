# WARFRAME-RELIC 开发文档

> 版本：v2.0  
> 作者：NeonXi (B站: MichaelJackso2)  
> 最后更新：2026-05-31

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈](#2-技术栈)
3. [项目结构总览](#3-项目结构总览)
4. [架构设计](#4-架构设计)
5. [核心模块详解](#5-核心模块详解)
   - [5.1 入口 & 核心控制器 (main.py)](#51-入口--核心控制器-mainpy)
   - [5.2 覆盖层系统 (overlay.py)](#52-覆盖层系统-overlaypy)
   - [5.3 管理面板 (management_panel.py)](#53-管理面板-management_panelpy)
   - [5.4 数据更新 & 日志 (update_panel.py)](#54-数据更新--日志-update_panelpy)
   - [5.5 主题配色系统](#55-主题配色系统)
   - [5.6 文案预设系统](#56-文案预设系统)
   - [5.7 OCR 识别系统](#57-ocr-识别系统)
   - [5.8 物品匹配引擎 (matcher.py)](#58-物品匹配引擎-matcherpy)
   - [5.9 价格查询系统 (price_service.py)](#59-价格查询系统-price_servicepy)
   - [5.10 数据库模块](#510-数据库模块)
   - [5.11 快捷键系统 (hotkey_config.py)](#511-快捷键系统-hotkey_configpy)
   - [5.12 样式表生成 (stylesheet.py)](#512-样式表生成-stylesheetpy)
   - [5.13 后台 Worker 线程](#513-后台-worker-线程)
6. [数据层详解](#6-数据层详解)
7. [配色系统深度剖析](#7-配色系统深度剖析)
8. [线程安全与并发](#8-线程安全与并发)
9. [配置与持久化](#9-配置与持久化)
10. [构建与打包](#10-构建与打包)
11. [开发工具](#11-开发工具)
12. [常见开发任务](#12-常见开发任务)
13. [模块依赖关系图](#13-模块依赖关系图)
14. [性能优化记录](#14-性能优化记录)

---

## 1. 项目概述

**WARFRAME-RELIC** 是一个 Windows 桌面辅助工具，专为游戏《Warframe》设计。它通过 DirectX 屏幕截图 + RapidOCR 文字识别，自动识别遗物选择界面中的遗物名称，并查询其出入库状态、Prime 部件内容和 warframe.market 实时价格，以半透明覆盖层的形式显示在游戏画面上。

### 核心功能

| 功能 | 说明 | 版本 |
|------|------|------|
| 框选截图识别 | 热键触发后拖拽框选区域，松手自动截图 OCR | v1.0 |
| 全屏截图识别 | 跳过框选，直接截全屏进行识别 | v1.0 |
| 出入库查询 | 绿色标注出库（可获取）遗物，红色标注入库（不可获取）遗物 | v1.0 |
| 遗物内容查询 | 显示每个遗物包含的 Prime 部件，金/银/铜色区分稀有度 | v1.0 |
| 价格查询 | 识别物品名称 → warframe.market API 实时查询 → 加权定价 | v2.0 |
| 翻译功能 | OCR 识别英文文本并翻译为中文 | v2.0 |
| 热键可配置 | 管理面板内可视化修改快捷键，即时生效 | v1.0 |
| 一键数据更新 | 从 GitHub 自动拉取最新 WFCD 掉落数据 | v1.0 |
| 配色换肤 | 3 套预设（赛博朋克/白天/自定义），可视化编辑色块 | v1.0 |
| 文案风格切换 | 3 套文案预设（赛博朋克2077/三体·威慑纪元/普通·标准） | v2.0 |
| 功能开关 | 截图后显示哪些功能按钮，可独立开关 | v2.0 |

### 典型数据流

```
热键触发 → dxcam 截图 → RapidOCR 异步识别 → 功能按钮弹出
                                                  ↓
                                          用户选择功能
                                                  ↓
                                  数据库查询 → 覆盖层流式标注
```

---

## 2. 技术栈

| 依赖 | 版本 | 用途 |
|------|------|------|
| **Python** | 3.10+ | 运行环境 |
| **PyQt6** | ≥6.11.0 | GUI 框架（覆盖层窗口、管理面板） |
| **dxcam** | ≥0.3.0 | 高性能 DirectX 屏幕截图 |
| **keyboard** | ≥0.13.5 | 全局热键注册 |
| **rapidocr-onnxruntime** | ≥1.4.4 | OCR 引擎（离线识别，ONNX 推理） |
| **Pillow** | ≥12.0.0 | 调试截图保存 |
| **numpy** | ≥2.0.0 | 图像数据处理 |

### 外部数据源

| 数据源 | 说明 | 用途 |
|--------|------|------|
| [WFCD/warframe-drop-data](https://github.com/WFCD/warframe-drop-data) | 遗物掉落数据 | `all.json` → `relics.db` |
| [WFCD/warframe-items](https://github.com/WFCD/warframe-items) | 全物品数据 | `all_items.json` + `i18n.json` → `items_i18n.db`（辅助源） |
| AdminRoc 中英翻译 | 16907 条中英对照（最全） | `zh_en_dict.json` → `items_i18n.db`（★ 主数据源） |
| [warframe.market API](https://api.warframe.market/v2) | 实时交易价格 | → `wm_prices.db` |

**数据优先级**：`zh_en_dict.json`（16907 条，最全）> `all_items.json`（15729 条，含详细属性）> `i18n.json`（翻译补充）

---

## 3. 项目结构总览

```
WARFRAME-RELIC/
├── main.py                         # ★ 程序入口 + AppCore 核心控制器
├── dev_runner.py                   # 开发热重载运行器
├── build_exe.py                    # PyInstaller 打包脚本（onedir 文件夹模式）
├── build_onefile.py                # PyInstaller 打包脚本（onefile 单文件模式）
├── test_recognizer.py              # OCR 识别测试脚本
├── debug_monitor.py                # 调试监控脚本
├── debug_ocr_visual.py             # OCR 可视化调试脚本
├── test_4split_ocr.py              # 4等分截图测试脚本
├── qt.conf                         # Qt DPI 感知配置
├── requirements.txt                # Python 依赖声明
├── core/                           # ★ 核心逻辑模块
│   ├── __init__.py                 # 空（包标记）
│   ├── constants.py                # 业务常量 + 主题兼容层（re-export）
│   ├── theme_config.py             # ★ ThemeConfig 单例引擎（配色核心）
│   ├── theme_proxy.py              # ★ _ThemeProxy 颜色代理（75+ 个常量）
│   ├── theme_fields.py             # 主题编辑字段定义（65 个色块元信息）
│   ├── theme_panel.py              # 主题配色侧滑面板（色块编辑/预设切换）
│   ├── management_panel.py         # ★ 管理面板主窗口（委托子面板）
│   ├── update_panel.py             # 数据更新 & 日志面板
│   ├── update_worker.py            # 数据库更新后台 Worker
│   ├── fetch_worker.py             # GitHub 下载后台 Worker（7 步进度）
│   ├── overlay.py                  # ★ 全屏覆盖层（框选/标注/按钮/流式动画）
│   ├── stylesheet.py               # QSS 样式表动态生成
│   ├── hotkey_config.py            # 快捷键配置读写
│   ├── hotkey_capture_button.py    # 热键捕获按钮控件
│   ├── item_info_panel.py          # 物品信息面板（翻译+价格）
│   ├── price_service.py            # ★ 价格查询服务（缓存/DB/API 三层 + 并行）
│   └── word_wrap_button.py         # 自动换行按钮控件
├── recognizers/                    # OCR 识别 & 物品匹配模块
│   ├── __init__.py                 # 空（包标记）
│   ├── base_ocr.py                 # OCR 基类（RapidOCR 封装）
│   ├── item_name.py                # ★ 物品名称 OCR 识别器
│   ├── relic_name.py               # ★ 遗物名称 OCR 识别器
│   ├── mod_name.py                 # MOD 名称 OCR 识别器
│   └── matcher.py                  # ★ 物品匹配引擎（4 轮降级匹配）
├── data/                           # 数据 & 配置目录
│   ├── __init__.py                 # 数据模块标记
│   ├── all.json                    # WFInfo 全量掉落数据源（~6MB）
│   ├── all.json.bak                # 数据源备份
│   ├── all_items.json              # WFCD 全物品数据（~47MB，辅助源）
│   ├── i18n.json                   # WFCD 多语言翻译数据
│   ├── zh_en_dict.json             # ★ 中英对照字典（~1MB，主数据源）
│   ├── relics.db                   # ★ SQLite 遗物数据库（~616KB）
│   ├── items_i18n.db               # ★ 全物品中英对照数据库（~8MB）
│   ├── items_i18n.py               # ★ 全物品数据库构建/查询模块
│   ├── wm_prices.db                # warframe.market 价格数据库
│   ├── wm_prices.py                # 价格拉取/查询模块
│   ├── translation.db              # 翻译数据库（旧版，已被 items_i18n.db 替代）
│   ├── translation_db.py           # 翻译库构建模块
│   ├── wfinfo_relics.py            # ★ RelicDB 查询模块（四级匹配）
│   ├── db_utils.py                 # 数据库工具函数（表结构/别名/迁移）
│   ├── hotkeys.json                # 快捷键持久化配置
│   ├── feature_toggles.json        # 功能开关配置
│   ├── item_region.json            # 物品区域配置
│   ├── ui_strings.py               # ★ UI 字符串路由器（文案预设管理）
│   ├── language_preset.json        # ★ 语言预设配置
│   ├── preset_cyberpunk2077.py     # ★ 赛博朋克 2077 风格文案预设（默认）
│   ├── preset_santi.py             # 三体·威慑纪元风格文案预设
│   ├── preset_normal.py            # 普通·标准模式文案预设
│   └── presets/                    # ★ 配色预设目录
│       ├── _active.json            # 当前活动预设 ID
│       ├── cyberpunk.json          # 赛博朋克配色（用户修改版）
│       ├── daylight.json           # 白天模式配色（用户修改版）
│       └── custom.json             # 自定义配色
├── SETUP.bat                       # 零基础一键安装启动
├── WARFRAME-RELIC.bat              # 日常启动批处理
├── DEV_RUN.bat                     # 开发模式启动批处理
├── 打包.bat                        # 一键打包批处理
├── 打包单文件.bat                  # 单文件EXE打包批处理
├── 一键打包.bat                    # 一键打包+压缩批处理
├── git-push.bat                    # Git 一键推送
└── README.md                       # 用户文档
```

### 文件大小参考

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | ~900 | 入口 + AppCore 核心控制器 |
| `core/overlay.py` | ~750 | 全屏覆盖层（框选/标注/按钮/动画/4等分框线） |
| `core/management_panel.py` | ~1700 | 管理面板主窗口（含语言预设切换） |
| `core/update_panel.py` | ~700 | 数据更新 & 日志子面板 |
| `core/theme_config.py` | ~440 | 主题配色单例引擎 |
| `core/theme_panel.py` | ~410 | 主题配色侧滑面板 |
| `core/theme_proxy.py` | ~150 | 颜色代理（75+ 个常量） |
| `core/theme_fields.py` | ~80 | 色块字段定义 |
| `core/stylesheet.py` | ~155 | QSS 样式表生成 |
| `core/hotkey_config.py` | ~130 | 快捷键配置 |
| `core/price_service.py` | ~370 | 价格查询服务（缓存/DB/API + 并行） |
| `core/fetch_worker.py` | ~232 | GitHub 下载 Worker |
| `core/update_worker.py` | ~30 | 数据库更新 Worker |
| `core/constants.py` | ~92 | 业务常量 + 兼容层 |
| `recognizers/item_name.py` | ~821 | ★ 物品名称 OCR 识别器 |
| `recognizers/matcher.py` | ~500 | ★ 物品匹配引擎（4 轮降级） |
| `recognizers/relic_name.py` | ~83 | 遗物名称 OCR 识别器 |
| `recognizers/base_ocr.py` | ~150 | OCR 基类 |
| `recognizers/mod_name.py` | ~100 | MOD 名称识别器 |
| `data/items_i18n.py` | ~730 | ★ 全物品数据库构建/查询 |
| `data/wm_prices.py` | ~900 | 价格拉取/查询模块 |
| `data/translation_db.py` | ~500 | 翻译库构建模块 |
| `data/wfinfo_relics.py` | ~208 | SQLite 遗物查询模块 |
| `data/db_utils.py` | ~337 | 数据库工具 |
| `data/ui_strings.py` | ~155 | UI 字符串路由器 |
| `build_exe.py` | ~540 | 打包脚本 |
| `build_onefile.py` | ~400 | 单文件打包脚本 |
| `dev_runner.py` | ~258 | 开发热重载 |

---

## 4. 架构设计

### 4.1 整体架构

项目采用 **中心化控制** 架构，`AppCore`（位于 `main.py`）作为中央控制器，协调各模块：

```
┌──────────────────────────────────────────────────────┐
│                     AppCore                          │
│                  (中央控制器)                          │
│                                                      │
│  管理：截图 → OCR → 查询 → 标注 全流程                │
│  管理：热键注册/反注册/动态更新                         │
│  管理：线程生命周期（OCR 线程）                         │
│  管理：各模块间的信号/回调绑定                          │
└──────┬───────┬────────┬──────────┬──────────────────┘
       │       │        │          │
       ▼       ▼        ▼          ▼
   Overlay  OCR识别  数据库查询  ManagementPanel
  (覆盖层)  (Rapid) (SQLite)    (管理窗口)
```

### 4.2 设计模式

| 模式 | 应用位置 | 说明 |
|------|---------|------|
| **单例** | `ThemeConfig`, `PriceService` | 全局唯一管理器 |
| **属性代理** | `_ThemeProxy` | 模块级颜色常量自动跟随主题变化 |
| **委托/组合** | `ManagementPanel` → `ThemePanel` / `UpdatePanel` | 管理面板将子功能委托给专用面板 |
| **观察者** | `pyqtSignal` | Qt 信号/槽实现事件驱动 |
| **Worker 线程** | `OCRWorker` / `FetchWorker` / `UpdateWorker` | 耗时操作放入后台线程 |
| **路由器** | `ui_strings.py` `S()` | 根据活动预设路由到对应文案 |

### 4.3 模块分层

```
┌─────────────────────────────────────────┐
│            表现层 (UI)                   │
│  overlay.py  management_panel.py        │
│  theme_panel.py  update_panel.py        │
│  stylesheet.py                          │
├─────────────────────────────────────────┤
│            业务逻辑层                     │
│  main.py (AppCore)                      │
│  price_service.py                       │
│  hotkey_config.py                       │
├─────────────────────────────────────────┤
│            识别/数据层                    │
│  item_name.py (OCR)                     │
│  relic_name.py (OCR)                    │
│  matcher.py (物品匹配)                   │
│  wfinfo_relics.py (RelicDB)            │
│  items_i18n.py  wm_prices.py           │
├─────────────────────────────────────────┤
│            基础设施层                     │
│  theme_config.py  theme_proxy.py        │
│  theme_fields.py  constants.py          │
│  ui_strings.py (文案路由器)              │
│  fetch_worker.py  update_worker.py      │
└─────────────────────────────────────────┘
```

---

## 5. 核心模块详解

### 5.1 入口 & 核心控制器 (`main.py`)

**文件路径**: `main.py`  
**行数**: ~900 行

#### 关键类

##### `TriggerBridge(QObject)`

键盘热键事件到 Qt 信号系统的桥接器。

```python
class TriggerBridge(QObject):
    fired = pyqtSignal(str)  # 发射热键动作名: "select" | "fullscreen" | "panel" | "query_price"
```

- `keyboard` 库的回调运行在非 Qt 线程中，不能直接操作 UI
- `TriggerBridge` 通过信号将事件安全地传递到 Qt 主线程
- 防重入：同一 action 500ms 内不可重复触发

##### `OCRWorker(QObject)`

后台 OCR 识别工作线程。

```python
class OCRWorker(QObject):
    finished = pyqtSignal(list)  # 完成后发射: [(name, box), ...]
    def run(self):
        # 在线程中执行 OCR，完成后发射 finished 信号
```

##### `AppCore` — 核心控制器

协调截图 → OCR → 查询 → 标注全流程的中央控制器。

**关键方法**:

| 方法 | 说明 |
|------|------|
| `run()` | 启动流程：初始化 DB → 绑定事件 → 注册热键 → 进入事件循环 |
| `do_screenshot()` | 框选区域截图 → 启动异步 OCR |
| `do_screenshot_fullscreen()` | 全屏截图 → 清除旧标注 → 启动异步 OCR |
| `_do_price_query()` | ★ 价格查询快捷键：显示4等分框线 → 延迟截图 → 识别 → 查价 |
| `_do_price_query_capture()` | ★ 截图+OCR+匹配+查价（含进度反馈） |
| `_render_price_direct()` | 渲染价格标注到覆盖层 |
| `_start_ocr_async()` | 创建 QThread + OCRWorker，启动异步识别 |
| `_on_ocr_finished()` | OCR 完成回调：更新 UI 标签，处理待执行模式 |
| `on_mode_selected()` | 用户点击功能按钮 → 等待/执行功能 |
| `_cleanup_ocr_thread()` | 安全退出 OCR 线程（带超时强制终止） |

**价格查询流程**（v2.0 优化后）：

```
1. 显示4等分框线 (600ms) → 等待 (800ms)
2. 逐张截图 (4次, ~60ms)
3. OCR识别 + 进度反馈 (4次, ~800ms)
   "⟐ 正在识别第 X/4 个物品..."
4. 匹配+查价 + 进度反馈
   "⟐ 正在查询 N 个物品的价格..."
   缓存 → 本地DB → 实时API (并发, max 4 workers)
5. 渲染标注 (15ms, 一次显示全部)
```

**DPI 处理**:

- `qt.conf` 中设置 `dpiawareness=0` 使 Qt 使用逻辑坐标
- dxcam 返回物理像素坐标
- `_dpi_scale` 用于两者之间的转换

---

### 5.2 覆盖层系统 (`overlay.py`)

**文件路径**: `core/overlay.py`  
**行数**: ~750 行

全屏透明覆盖层，三种工作状态，是整个项目的视觉输出核心。

#### 三种状态

| 状态 | 鼠标穿透 | 功能 |
|------|---------|------|
| **空闲** | 穿透 | 只显示标注和按钮，不干扰游戏操作 |
| **框选** | 不穿透 | 拦截鼠标事件，允许拖拽框选区域 |
| **标注** | 穿透 | 按钮不穿透，标注区域穿透 |

#### 关键功能模块

**1. 鼠标穿透控制**

使用 Qt `WA_TransparentForMouseEvents` 属性实现精细控制：
- 窗口+label → 穿透
- 按钮 → 永远不穿透

**2. 框选模式**

- `start_selection()` — 进入框选：禁用穿透、设十字光标、启动 60fps 鼠标追踪
- `_track_mouse()` — 每 16ms 检测：左键按下/拖拽/松开，右键/ESC 取消
- `_finish_selection()` — 保存区域到 `%APPDATA%/WARFRAME-RELIC/config.json`

**3. 4等分区域框线**

- `show_split_regions()` — 显示红/绿/蓝/紫四色矩形框 + "子图1"~"子图4" 标签
- 价格查询前短暂显示，帮助用户确认截图区域

**4. 功能按钮**

截图完成后立即显示（不等 OCR），点击发射 `mode_selected` 信号。

**5. 标注系统**

支持多种标注格式（向后兼容）：

```python
# 3 元组: (text, x, y)                         → 默认色 + 自动隐藏
# 4 元组: (text, x, y, color)                   → 指定色 + 自动隐藏
# 5 元组: (text, x, y, expire_ms, color)        → 完全自定义
# 6 元组: (text, x, y, expire_ms, color, [line_colors]) → 多行分别着色
```

**6. 流式标注动画**

```python
def show_annotations_stream(self, annotations, auto_hide_ms=5000, interval_ms=30, batch_size=2):
```

- 使用 `QTimer` 定时逐批弹出标注
- 价格查询使用 `interval_ms=15, batch_size=全部` 以加速显示

**7. 绘制系统**

`paintEvent()` 负责所有视觉渲染：
- **框选状态**: 半透明遮罩 + 顶部状态栏 + 准星/选区矩形 + 4等分框线
- **标注状态**: 半透明深色背景 + 2077 风格左边框装饰条 + 多行着色文本

**8. 右键清除**

通过 Win32 `GetAsyncKeyState(VK_RBUTTON)` 检测右键：
- 清除所有标注 + 隐藏功能按钮 + 清除 label 文字

---

### 5.3 管理面板 (`management_panel.py`)

**文件路径**: `core/management_panel.py`  
**行数**: ~1700 行

独立窗口，通过热键 `Ctrl+Shift+G` 唤起。采用 **委托模式**。

#### 布局结构

```
┌──────────────────────────────────────────────────────────┐
│  WARFRAME-RELIC 管理面板                                  │
├────────────────────┬──────────────┬───────────────────────┤
│  左侧主面板 (可滚动) │  日志面板     │  主题配色侧滑面板       │
│                    │  (420px 宽)  │  (0~320px 动画宽度)   │
│  ┌──────────────┐  │              │                       │
│  │ 功能开关      │  │  运行日志    │  预设方案下拉框          │
│  │ 紧急重置      │  │  步骤指示    │  色块编辑区              │
│  │ 数据库状态    │  │  下载进度    │  保存/恢复/刷新按钮      │
│  │ 遗物数据更新  │  │  日志详情    │                       │
│  │ 翻译库更新    │  │              │                       │
│  │ 物品检索      │  │              │                       │
│  │ 价格数据      │  │              │                       │
│  │ 快捷键设置    │  │              │                       │
│  │ 语言风格      │  │              │                       │
│  │ 自定义配色    │  │              │                       │
│  │ 关于作者      │  │              │                       │
│  └──────────────┘  │              │                       │
│  底部提示 / 退出    │              │                       │
└────────────────────┴──────────────┴───────────────────────┘
```

#### 功能区块

| 区块 | 说明 |
|------|------|
| 功能开关 | 4 个功能模块的独立开关（出入库/内含物/价格/翻译） |
| 紧急重置 | 恢复默认状态（8步恢复流程） |
| 数据库状态 | 多项统计 + 进度条 |
| 遗物数据更新 | 从 GitHub 拉取 / 本地文件导入 |
| 翻译库更新 | 中英文翻译数据库构建 |
| 物品检索 | 中英文双向搜索 |
| 价格数据 | warframe.market 价格同步 + 设置截图区域 |
| 快捷键设置 | 5 个热键输入框 + 格式校验 + 保存/重置 |
| 语言风格 | ★ 文案预设切换（赛博朋克2077/三体/普通） |
| 自定义配色 | 按钮触发侧滑面板 |
| 关于作者 | 作者信息 + B站/GitHub 链接 |

#### 信号发射

```python
db_updated = pyqtSignal(str)        # 数据库更新完成
hotkeys_changed = pyqtSignal(dict)  # 快捷键变更
theme_changed = pyqtSignal()        # 主题变更
```

---

### 5.4 数据更新 & 日志 (`update_panel.py`)

**文件路径**: `core/update_panel.py`  
**行数**: ~700 行

管理数据拉取（GitHub）、数据库更新、日志输出三大功能。

#### 数据拉取流程（7步精细化进度）

```
1. 解析目标地址 → 2. DNS解析 → 3. 建立HTTPS连接
→ 4. 获取文件信息 → 5. 下载数据(带百分比) → 6. 验证JSON → 7. 保存文件
```

#### 日志系统

日志类型与颜色映射：
| log_type | 图标 | 用途 |
|----------|------|------|
| `ok` | ✓ | 成功操作 |
| `warn` | ⚠ | 警告信息 |
| `error` | ✗ | 错误信息 |
| `info` | (空格) | 一般信息 |

---

### 5.5 主题配色系统

配色系统由 4 个文件组成：

| 文件 | 职责 |
|------|------|
| `core/theme_config.py` | **ThemeConfig 单例**：配色加载/保存/预设切换/派生属性 |
| `core/theme_proxy.py` | **_ThemeProxy 代理**：75+ 个模块级颜色常量，自动跟随主题 |
| `core/theme_fields.py` | **THEME_FIELDS 列表**：65 个色块的元信息（键名/标签/类别） |
| `core/theme_panel.py` | **ThemePanel**：侧滑面板 UI，色块编辑/预设切换/动画 |

详见 [第 7 节：配色系统深度剖析](#7-配色系统深度剖析)。

---

### 5.6 文案预设系统

**文件**: `data/ui_strings.py`（路由器）+ `data/preset_*.py`（预设文件）

#### 三套文案预设

| 预设 ID | 名称 | 文件 | 风格 |
|---------|------|------|------|
| `cyberpunk2077` | 赛博朋克2077 · 夜之城（默认） | `preset_cyberpunk2077.py` | 霓虹暗夜、神经端口、黑市行情 |
| `santi` | 三体 · 威慑纪元 | `preset_santi.py` | 智子认知矩阵、黑暗森林博弈 |
| `normal` | 普通 · 标准模式 | `preset_normal.py` | 简洁直白 |

#### 使用方式

```python
from data.ui_strings import S, set_language_preset
# 获取文案
label.setText(S("button", "exit"))
# 切换预设
set_language_preset("cyberpunk2077")
```

#### 架构

```
language_preset.json (active + presets 元信息)
        │
        ▼
ui_strings.py (路由器: 加载活跃预设 → STRINGS 全局字典)
        │
        ├── preset_cyberpunk2077.py  (默认)
        ├── preset_santi.py
        └── preset_normal.py
        │
        ▼
S("category", "key")  → 从 STRINGS[category][key] 取值
S.format("category", "key", **kw) → 格式化后返回
```

#### 管理面板切换

管理面板从 `language_preset.json` 读取预设列表，自动生成下拉框。切换时：
1. `set_language_preset(preset_id)` 更新 STRINGS 全局字典
2. `_rebuild_ui_for_preset()` 遍历 `_text_registry` 刷新所有控件文字
3. 刷新窗口标题、数据标签、按钮等

---

### 5.7 OCR 识别系统

#### 物品名称识别 (`recognizers/item_name.py`)

**行数**: ~821 行

从屏幕截图中 OCR 识别物品英文名，生成纠错候选列表。

**核心流程**：
1. `_group_by_slot()` — 按位置分组（2D 网格聚类）
2. `_process_slots()` — 遍历分组结果，提取英文名 + 特征词
3. `_fix_ocr_confusions()` — 模糊修复 OCR 常见错误（如 PNme→Prime）
4. 输出 `[(en_name, box, [variants]), ...]`

**关键设计**：
- 仅战甲模式追加 "Blueprint" 后缀（武器和守护不追加）
- Levenshtein 编辑距离 + 滑窗匹配模糊修复
- 多 OCR 候选生成纠错列表

#### 遗物名称识别 (`recognizers/relic_name.py`)

**行数**: ~83 行

使用 RapidOCR (ONNX Runtime) 进行离线文字识别。

**正则匹配模式**: `(古纪|前纪|中纪|后纪|安魂|先锋)[\s.,，。、]*([A-TV-Z0-9]\d+)`

**OCR 纠错**: 字符替换映射 + 数字→字母修正

---

### 5.8 物品匹配引擎 (`matcher.py`)

**文件路径**: `recognizers/matcher.py`  
**行数**: ~500 行

将 OCR 识别的英文名匹配到 `items_i18n.db` 数据库。

#### 4 轮降级匹配

```
OCR 英文文本 → _match_one_item()
    │
    ├── 第1轮: 精确匹配 → en_name == ocr_text
    ├── 第2轮: 模糊匹配 → 单词合理性 + 编辑距离容错
    ├── 第3轮: 纠错候选 → 对 OCR 纠错后的 variants 逐个尝试
    └── 第4轮: 部件蓝图直通 → _is_warframe_part() 判断
        ├── 构造虚拟条目（en_name + zh_name 拼接）
        ├── 实时查 warframe.market API 获取价格
        └── ★ 自动写入 items_i18n.db（下次可精确匹配，自愈机制）
```

#### 关键设计

- `_upsert_part_to_db()` — 部件直通发现的新物品自动写入 DB，实现自愈
- `match_and_price()` — 匹配 + 查价一站式接口
- `_try_variants()` — 单词覆盖率检查防止前缀误匹配

---

### 5.9 价格查询系统 (`price_service.py`)

**文件路径**: `core/price_service.py`  
**行数**: ~370 行

#### 三层查询架构

```
query_price(en_name, match_quality)
    │
    ├── 1. 内存缓存 (TTL=30s)
    │
    ├── 2. 本地 DB (wm_prices.db, en_name 直接查询)
    │
    └── 3. 实时 API (warframe.market API v2, timeout=3s)
```

#### 并行批量查询（v2.0 优化）

`query_prices_batch()` 使用 `ThreadPoolExecutor` 并发查询：
- 缓存命中 + 本地DB命中 → 同步处理（毫秒级）
- 需要实时API的物品 → 并发（max 4 workers）
- **效果**: 4个物品最坏从 ~12秒 降到 ~3秒

#### 反压价权重算法

- 偏离中位数 >30% 的低价视为异常，权重降至 0.1
- 加权参考价 = Σ(价格×权重) / Σ权重

#### 价格颜色映射

| 价格区间 | 颜色 | 含义 |
|---------|------|------|
| ≥50p | 绿色 | 高价 |
| ≥20p | 金色 | 中价 |
| <20p | 黄色 | 低价 |
| 无数据 | 铜色 | 无价格 |
| 未匹配 | 灰色 | 未知 |

---

### 5.10 数据库模块

#### RelicDB (`data/wfinfo_relics.py`)

SQLite 遗物数据库查询封装，线程安全。

**四级查询匹配**：

| 级别 | 方法 | 说明 |
|------|------|------|
| 1 | 别名精确匹配 | `relic_aliases` 表精确查找 |
| 2 | 主表精确匹配 | `relics.name` 精确查找 |
| 3 | 忽略空格大小写 | 去空格 + 小写后匹配 |
| 4 | 正则模糊匹配 | 统一易混淆字符后匹配 |

**线程安全**: 双重检查锁定（DCL）保护连接生命周期

#### 全物品数据库 (`data/items_i18n.py`)

从 `zh_en_dict.json`（主数据源，16907条）+ `all_items.json`（辅助源）+ `i18n.json`（翻译补充）构建。

**数据优先级**: `zh_en_dict.json` > `all_items.json` > `i18n.json`

#### 价格数据库 (`data/wm_prices.py`)

warframe.market 价格数据管理。

**关键设计**：
- `en_name` 列直接查询（不依赖 item_id JOIN，解决 ID 不匹配问题）
- `--fetch` 命令拉取全量价格数据
- `get_price()` 三层匹配：en_name 精确 → LIKE 模糊 → JOIN 兼容

---

### 5.11 快捷键系统 (`hotkey_config.py`)

**文件路径**: `core/hotkey_config.py`  
**行数**: ~130 行

#### 默认热键

```python
DEFAULT_HOTKEYS = {
    "select":       "ctrl+g",           # 框选截图
    "fullscreen":   "ctrl+h",           # 全屏截图
    "panel":        "ctrl+shift+g",     # 管理面板
    "query_price":  "ctrl+shift+p",     # 价格查询
}
```

#### 格式验证

- 至少 1 个修饰键 + 1 个普通键
- 修饰键: ctrl, alt, shift, win
- 普通键不能是修饰键

#### 热键注册机制

1. 反注册所有旧热键
2. 遍历动作映射，使用 `keyboard.add_hotkey()` 注册新热键
3. 热键回调通过 `TriggerBridge.fired` 信号发射到 Qt 主线程

---

### 5.12 样式表生成 (`stylesheet.py`)

**文件路径**: `core/stylesheet.py`  
**行数**: ~155 行

动态生成 Qt QSS 样式表，所有颜色值从 `ThemeConfig` 单例读取。

**按钮样式角色**:

| QSS ObjectName | 用途 | 对应颜色键 |
|---------------|------|-----------|
| `primaryBtn` | 蓝色主按钮 | `primary_*` |
| `actionBtn` | 普通操作按钮 | `btn_default_*` |
| `dangerBtn` | 红色危险按钮 | `danger_*` |
| `successBtn` | 绿色成功按钮 | `success_*` |

---

### 5.13 后台 Worker 线程

#### FetchWorker (`core/fetch_worker.py`)

从 GitHub 下载 `all.json` 的后台线程，7 步精细化进度反馈。

#### UpdateWorker (`core/update_worker.py`)

数据库更新后台线程（轻量）。

---

## 6. 数据层详解

### 6.1 数据文件说明

| 文件 | 大小 | 说明 |
|------|------|------|
| `data/all.json` | ~6MB | WFInfo 全量掉落数据 |
| `data/all_items.json` | ~47MB | WFCD 全物品数据 |
| `data/i18n.json` | ~5MB | WFCD 多语言翻译 |
| `data/zh_en_dict.json` | ~1MB | ★ 主数据源（16907 条） |
| `data/relics.db` | ~616KB | SQLite 遗物数据库 |
| `data/items_i18n.db` | ~8MB | ★ 全物品中英对照数据库 |
| `data/wm_prices.db` | ~368KB | warframe.market 价格数据库 |
| `data/translation.db` | ~6MB | 翻译数据库（旧版） |
| `data/hotkeys.json` | <1KB | 快捷键配置 |
| `data/feature_toggles.json` | <1KB | 功能开关配置 |
| `data/language_preset.json` | <1KB | 语言预设配置 |

### 6.2 全物品数据库构建流程

```
zh_en_dict.json (主数据源，16907 条)
    │  ★ 第一优先级
    ▼
all_items.json (辅助数据源，补充 category/tradable 等属性)
    │
    ▼
i18n.json (翻译补充，~657 条额外物品)
    │
    ▼
items_i18n.db (~17564 个物品)
    ├── items (主表)
    └── items_meta (元信息)
```

### 6.3 物品匹配流程（4 轮降级）

见 [5.8 物品匹配引擎](#58-物品匹配引擎-matcherpy)

---

## 7. 配色系统深度剖析

### 7.1 系统架构

```
ThemeConfig (单例)
    │
    ├── _data: dict      ← 当前所有颜色值
    ├── _active_preset   ← "cyberpunk"/"daylight"/"custom"
    ├── _DEFAULTS        ← 出厂默认值 (Cyberpunk 2077)
    │
    ├── theme.cyber_yellow  → __getattr__ 代理到 _data
    ├── theme.save(dict)    → 保存 + 自动切换预设
    ├── theme.reload()      → 热重载
    ├── theme.reset()       → 恢复出厂默认
    └── theme.apply_preset()→ 切换预设
            │
            ▼
_ThemeProxy (属性代理)
    │
    └── 75+ 个模块级常量:
        CYBER_YELLOW = _proxy('cyber_yellow')
        COLOR_VAULTED = _proxy('color_vaulted')
        ...
        每次访问都从 theme 实时取值，无需手动同步
```

### 7.2 65 个配色字段（按类别）

| 类别 | 字段数 | 示例 |
|------|--------|------|
| 界面主色 | 7 | `cyber_yellow`, `cyber_cyan`, `cyber_magenta` |
| 面板背景 | 8 | `dark_bg`, `panel_bg`, `card_bg`, `border` |
| 遗物状态 | 3 | `color_vaulted`, `color_available`, `color_unknown` |
| 部件稀有度 | 3 | `color_gold`, `color_silver`, `color_copper` |
| 日志颜色 | 6 | `log_ok`, `log_warn`, `log_error` |
| 按钮样式 | 22 | `btn_default_*`, `primary_*`, `danger_*`, `success_*` |
| 外链品牌 | 4 | `brand_bilibili`, `brand_github` |
| 游戏覆盖层 | 8 | `overlay_*_rgba`, `progress_gradient_*` |
| 价格颜色 | 3 | `price_sell`, `price_buy`, `price_median` |

### 7.3 预设系统

| 预设 ID | 名称 | 说明 |
|---------|------|------|
| `cyberpunk` | 赛博朋克 2077（推荐） | 霓虹暗色主题，默认配色 |
| `daylight` | 白天模式 | 白色基调 |
| `custom` | 自定义配色 | 用户专属配色 |

**修改保护**: 在内置预设中修改颜色后，自动切换为 `custom` 预设，保护内置预设不被污染。

### 7.4 属性访问机制

```python
# ThemeConfig.__getattr__ 代理到 _data
theme.cyber_yellow  →  theme._data["cyber_yellow"]

# _ThemeProxy 每次访问都实时读取
CYBER_YELLOW  →  getattr(theme, 'cyber_yellow')  # 实时！
```

---

## 8. 线程安全与并发

### 8.1 线程模型

```
┌─────────────────────────────────────────┐
│             Qt 主线程 (事件循环)           │
│  - UI 渲染 (Overlay / ManagementPanel)   │
│  - 信号/槽处理                            │
├─────────────────────────────────────────┤
│         OCR 后台线程 (QThread)             │
│  - RapidOCR 文字检测 + 识别               │
├─────────────────────────────────────────┤
│     Fetch 后台线程 (threading.Thread)     │
│  - urllib 下载 + JSON 校验               │
├─────────────────────────────────────────┤
│     Update 后台线程 (threading.Thread)    │
│  - SQLite 写入操作                        │
├─────────────────────────────────────────┤
│     价格查询线程池 (ThreadPoolExecutor)    │
│  - 并发 HTTP API 请求 (max 4 workers)     │
└─────────────────────────────────────────┘
```

### 8.2 安全措施

| 场景 | 措施 | 位置 |
|------|------|------|
| 截图竞态 | `threading.Lock` | `AppCore._process_frame()` |
| OCR 线程冲突 | 启动前安全退出上一轮 | `AppCore._start_ocr_async()` |
| OCR 线程超时 | `thread.wait(2000)` + `thread.terminate()` 兜底 | `AppCore._cleanup_ocr_thread()` |
| 数据库连接 | `threading.Lock` 双重检查锁定 | `RelicDB._get_conn()` |
| 热键连按 | 防重入窗口 500ms | `TriggerBridge` |
| 退出清理 | `aboutToQuit` → `_shutdown()` 统一释放 | `AppCore.run()` |
| 价格缓存 | `threading.Lock` 保护 | `PriceService` |

---

## 9. 配置与持久化

### 9.1 配置文件一览

| 文件 | 位置 | 格式 | 读写模块 |
|------|------|------|---------|
| 配色预设 | `data/presets/*.json` | JSON | `theme_config.py` |
| 活动预设 | `data/presets/_active.json` | JSON | `theme_config.py` |
| 快捷键 | `data/hotkeys.json` | JSON | `hotkey_config.py` |
| 功能开关 | `data/feature_toggles.json` | JSON | `main.py` |
| 物品区域 | `data/item_region.json` | JSON | `main.py` |
| 语言预设 | `data/language_preset.json` | JSON | `ui_strings.py` |
| 框选区域 | `%APPDATA%/WARFRAME-RELIC/config.json` | JSON | `overlay.py` |
| 调试截图 | `%APPDATA%/WARFRAME-RELIC/debug/last_capture.png` | PNG | `main.py` |

---

## 10. 构建与打包

### 10.1 开发模式运行

```bash
# 直接启动
python main.py

# 热重载模式（修改 .py 后自动重启）
python dev_runner.py

# 单次运行
python dev_runner.py --once --stdout
```

### 10.2 打包为 EXE

**打包脚本**:

| 脚本 | 产物 | 说明 |
|------|------|------|
| `build_exe.py` | `dist/WARFRAME-RELIC/` (文件夹) | onedir 模式，启动快 |
| `build_onefile.py` | `dist/WARFRAME-RELIC.exe` (单文件) | onefile 模式，分发方便 |

**排除策略**:
- 排除 rapidocr-onnxruntime 拉进来的无关大包：`torch`, `scipy`, `pandas` 等
- 排除用不到的 PyQt6 子模块：`QtWebEngine`, `QtMultimedia`, `QtBluetooth` 等 30+ 个
- 保留核心：`QtCore`, `QtGui`, `QtWidgets`

### 10.3 批处理文件

| 文件 | 功能 |
|------|------|
| `SETUP.bat` | 检测/安装 Python → 创建 venv → 安装依赖 → 启动 |
| `WARFRAME-RELIC.bat` | 检查环境 → 启动程序 |
| `DEV_RUN.bat` | 开发模式启动 |
| `打包.bat` | 执行 `build_exe.py` 打包 |
| `打包单文件.bat` | 执行 `build_onefile.py` 单文件打包 |
| `一键打包.bat` | 打包 + 压缩为 .zip |
| `git-push.bat` | Git add → commit → push |

---

## 11. 开发工具

### 11.1 OCR 测试工具

```bash
python test_recognizer.py          # 遗物识别测试
python debug_ocr_visual.py         # OCR 可视化调试
python test_4split_ocr.py          # 4等分截图测试
```

### 11.2 调试监控

```bash
python debug_monitor.py            # 调试监控
```

### 11.3 崩溃日志

`dev_runner.py` 监听模式下，子进程崩溃时自动写入 `crash_log.txt`。

---

## 12. 常见开发任务

### 12.1 添加新的文案预设

1. 创建 `data/preset_xxx.py`，定义 `STRINGS` 字典
2. 在 `data/language_preset.json` 中添加预设元信息
3. 管理面板自动识别新预设

### 12.2 添加新的配色字段

1. 在 `core/theme_config.py` 的 `_DEFAULTS` 字典中添加默认值
2. 在 `core/theme_fields.py` 的 `THEME_FIELDS` 列表中添加字段元信息
3. 在 `core/theme_proxy.py` 中添加对应的代理常量
4. 在 `core/constants.py` 的 re-export 列表中添加

### 12.3 添加新的热键

1. 在 `core/hotkey_config.py` 的 `DEFAULT_HOTKEYS` 中添加
2. 在 `HOTKEY_LABELS` 中添加中文标签
3. 在 `main.py` 的 `_handle_trigger()` 中添加处理逻辑
4. 在 `_register_hotkeys()` 的 `action_map` 中添加映射

### 12.4 修改 OCR 识别参数

在 `core/constants.py` 中修改：
```python
OCR_TEXT_SCORE = 0.35       # 文本置信度阈值
OCR_BOX_THRESH = 0.2        # 检测框阈值
OCR_UPSCALE_MIN_WIDTH = 900 # 触发放大的最小截图宽度
```

---

## 13. 模块依赖关系图

```
main.py
├── core/overlay.py
│   └── core/constants.py (颜色常量)
│       ├── core/theme_config.py (ThemeConfig 单例)
│       └── core/theme_proxy.py (_ThemeProxy)
├── core/management_panel.py
│   ├── core/constants.py
│   ├── core/stylesheet.py
│   ├── core/hotkey_config.py
│   ├── core/theme_fields.py
│   ├── core/theme_panel.py
│   ├── core/update_panel.py
│   │   ├── core/update_worker.py
│   │   └── core/fetch_worker.py
│   └── data/ui_strings.py (文案路由器)
│       ├── data/preset_cyberpunk2077.py (默认)
│       ├── data/preset_santi.py
│       └── data/preset_normal.py
├── core/price_service.py
│   └── data/wm_prices.py
├── recognizers/item_name.py
├── recognizers/matcher.py
│   └── data/items_i18n.py
├── recognizers/relic_name.py
├── data/wfinfo_relics.py (RelicDB)
└── core/hotkey_config.py
```

**关键设计原则**:
- `theme_config.py` 是**叶子模块**，不依赖任何项目内模块
- `theme_proxy.py` 只依赖 `theme_config.py`
- `constants.py` 作为**兼容层**，从上述两个模块 re-export
- `ui_strings.py` 是**文案路由器**，从 preset 文件加载字符串
- 数据层 (`data/`) 与核心逻辑层 (`core/`) 互相独立

---

## 14. 性能优化记录

### v2.0 优化

| 优化项 | 优化前 | 优化后 | 效果 |
|--------|--------|--------|------|
| 价格查询并行化 | 串行 API（4个物品 ~12s） | 线程池并发（~3s） | **节省 ~9s** |
| 框线等待时间 | 2200ms | 800ms | **节省 1.4s** |
| 流式标注动画 | 40ms/条，逐条 | 15ms，全部一次 | **瞬间显示** |
| OCR 进度反馈 | 无 | "正在识别第 X/4 个..." | 用户体验↑ |
| 价格查询进度反馈 | 无 | "正在查询 N 个物品的价格..." | 用户体验↑ |
| Blueprint 后缀修复 | 武器/守护错误追加 | 仅战甲追加 | 正确性↑ |
| 价格DB en_name查询 | 依赖ID JOIN（0匹配） | en_name直接查询 | 正确性↑ |

---

## 附录

### A. OCR 识别结果格式

```python
# recognize_all_with_boxes() 返回值
[("古纪 C7", [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]), ...]
```

### B. 标注数据格式

```python
(text, x, y, expire_ms, color, [line_colors])
```

### C. 坐标系统

- **物理像素**: dxcam 返回的坐标
- **逻辑坐标**: Qt 使用的坐标，受 DPI 缩放影响
- **转换**: `physical = logical × dpi_scale`

### D. 价格查询格式

```
物品中文名
  加权参考价: 19.4p
  最低: 15p
  中位: 18p
```

---

> 文档版本: 2.0 | 最后更新: 2026-05-31  
> 如发现文档与代码不一致，请以代码为准，并更新本文档。
