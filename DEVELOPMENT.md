# WARFRAME-RELIC 开发文档

> 版本：v1.0  
> 作者：NeonXi (B站: MichaelJackso2)  
> 最后更新：2026-05-30

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
   - [5.6 OCR 识别系统 (relic_name.py)](#56-ocr-识别系统-relic_namepy)
   - [5.7 数据库模块 (wfinfo_relics.py)](#57-数据库模块-wfinfo_relicspy)
   - [5.8 快捷键系统 (hotkey_config.py)](#58-快捷键系统-hotkey_configpy)
   - [5.9 样式表生成 (stylesheet.py)](#59-样式表生成-stylesheetpy)
   - [5.10 后台 Worker 线程](#510-后台-worker-线程)
6. [数据层详解](#6-数据层详解)
7. [配色系统深度剖析](#7-配色系统深度剖析)
8. [线程安全与并发](#8-线程安全与并发)
9. [配置与持久化](#9-配置与持久化)
10. [构建与打包](#10-构建与打包)
11. [开发工具](#11-开发工具)
12. [常见开发任务](#12-常见开发任务)
13. [模块依赖关系图](#13-模块依赖关系图)

---

## 1. 项目概述

**WARFRAME-RELIC** 是一个 Windows 桌面辅助工具，专为游戏《Warframe》设计。它通过 DirectX 屏幕截图 + RapidOCR 文字识别，自动识别遗物选择界面中的遗物名称，并查询其出入库状态和 Prime 部件内容，以半透明覆盖层的形式显示在游戏画面上。

### 核心功能

| 功能 | 说明 |
|------|------|
| 框选截图识别 | 热键触发后拖拽框选区域，松手自动截图 OCR |
| 全屏截图识别 | 跳过框选，直接截全屏进行识别 |
| 出入库查询 | 绿色标注出库（可获取）遗物，红色标注入库（不可获取）遗物 |
| 遗物内容查询 | 显示每个遗物包含的 Prime 部件，金/银/铜色区分稀有度 |
| 热键可配置 | 管理面板内可视化修改快捷键，即时生效 |
| 一键数据更新 | 从 GitHub 自动拉取最新 WFCD 掉落数据 |
| 配色换肤 | 3 套预设（赛博朋克/白天/自定义），可视化编辑色块 |

### 典型数据流

```
热键触发 → dxcam 截图 → RapidOCR 异步识别 → 功能按钮弹出
                                                  ↓
                                          用户选择功能
                                                  ↓
                                   RelicDB 数据库查询 → 覆盖层流式标注
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

- [WFCD/warframe-drop-data](https://github.com/WFCD/warframe-drop-data) — 遗物掉落数据（`all.json`）

---

## 3. 项目结构总览

```
WARFRAME-RELIC/
├── main.py                         # ★ 程序入口 + AppCore 核心控制器
├── dev_runner.py                   # 开发热重载运行器
├── build_exe.py                    # PyInstaller 打包脚本（5 步骤带进度）
├── test_recognizer.py              # OCR 识别测试脚本
├── update_db.py                    # 数据库更新 CLI 工具
├── qt.conf                         # Qt DPI 感知配置
├── requirements.txt                # Python 依赖声明
├── core/                           # ★ 核心逻辑模块
│   ├── __init__.py                 # 空（包标记）
│   ├── constants.py                # 业务常量 + 主题兼容层（re-export）
│   ├── theme_config.py             # ★ ThemeConfig 单例引擎（配色核心）
│   ├── theme_proxy.py              # ★ _ThemeProxy 颜色代理（75 个常量）
│   ├── theme_fields.py             # 主题编辑字段定义（65 个色块元信息）
│   ├── theme_panel.py              # 主题配色侧滑面板（色块编辑/预设切换）
│   ├── management_panel.py         # ★ 管理面板主窗口（委托子面板）
│   ├── update_panel.py             # 数据更新 & 日志面板
│   ├── update_worker.py            # 数据库更新后台 Worker
│   ├── fetch_worker.py             # GitHub 下载后台 Worker（7 步进度）
│   ├── overlay.py                  # ★ 全屏覆盖层（框选/标注/按钮）
│   ├── stylesheet.py               # QSS 样式表动态生成
│   └── hotkey_config.py            # 快捷键配置读写
├── recognizers/                    # OCR 识别模块
│   ├── __init__.py                 # 空（包标记）
│   └── relic_name.py               # ★ 遗物名称 OCR 识别器
├── data/                           # 数据 & 配置目录
│   ├── __init__.py                 # 数据模块标记
│   ├── all.json                    # WFInfo 全量掉落数据源（~6MB）
│   ├── all.json.bak                # 数据源备份
│   ├── relics.db                   # ★ SQLite 遗物数据库（~616KB）
│   ├── wfinfo_relics.py            # ★ RelicDB 查询模块（四级匹配）
│   ├── db_utils.py                 # 数据库工具函数（表结构/别名/迁移）
│   ├── migrate_to_sqlite.py        # JSON → SQLite 迁移脚本
│   ├── hotkeys.json                # 快捷键持久化配置
│   └── presets/                    # ★ 配色预设目录
│       ├── _active.json            # 当前活动预设 ID
│       ├── cyberpunk.json          # 赛博朋克配色（用户修改版）
│       ├── daylight.json           # 白天模式配色（用户修改版）
│       └── custom.json             # 自定义配色
├── SETUP.bat                       # 零基础一键安装启动
├── WARFRAME-RELIC.bat              # 日常启动批处理
├── 打包.bat                        # 一键打包批处理
├── git-push.bat                    # Git 一键推送
└── README.md                       # 用户文档
```

### 文件大小参考

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | ~557 | 入口 + AppCore 核心控制器 |
| `core/overlay.py` | ~660 | 全屏覆盖层（框选/标注/按钮/动画） |
| `core/management_panel.py` | ~632 | 管理面板主窗口 |
| `core/update_panel.py` | ~611 | 数据更新 & 日志子面板 |
| `core/theme_config.py` | ~440 | 主题配色单例引擎 |
| `core/theme_panel.py` | ~410 | 主题配色侧滑面板 |
| `core/theme_proxy.py` | ~150 | 颜色代理（75 个常量） |
| `core/theme_fields.py` | ~79 | 色块字段定义 |
| `core/stylesheet.py` | ~155 | QSS 样式表生成 |
| `core/hotkey_config.py` | ~95 | 快捷键配置 |
| `core/fetch_worker.py` | ~232 | GitHub 下载 Worker |
| `core/update_worker.py` | ~30 | 数据库更新 Worker |
| `core/constants.py` | ~92 | 业务常量 + 兼容层 |
| `recognizers/relic_name.py` | ~83 | OCR 识别器 |
| `data/wfinfo_relics.py` | ~208 | SQLite 查询模块 |
| `data/db_utils.py` | ~337 | 数据库工具 |
| `build_exe.py` | ~539 | 打包脚本 |
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
   Overlay  OCR识别  RelicDB   ManagementPanel
  (覆盖层)  (Rapid) (SQLite)   (管理窗口)
```

### 4.2 设计模式

| 模式 | 应用位置 | 说明 |
|------|---------|------|
| **单例** | `ThemeConfig` | 全局唯一配色管理器 |
| **属性代理** | `_ThemeProxy` | 模块级颜色常量自动跟随主题变化 |
| **委托/组合** | `ManagementPanel` → `ThemePanel` / `UpdatePanel` | 管理面板将子功能委托给专用面板 |
| **观察者** | `pyqtSignal` | Qt 信号/槽实现事件驱动 |
| **Worker 线程** | `OCRWorker` / `FetchWorker` / `UpdateWorker` | 耗时操作放入后台线程 |

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
│  hotkey_config.py                       │
├─────────────────────────────────────────┤
│            识别/数据层                    │
│  relic_name.py (OCR)                    │
│  wfinfo_relics.py (RelicDB)            │
│  db_utils.py                            │
├─────────────────────────────────────────┤
│            基础设施层                     │
│  theme_config.py  theme_proxy.py        │
│  theme_fields.py  constants.py          │
│  fetch_worker.py  update_worker.py      │
└─────────────────────────────────────────┘
```

---

## 5. 核心模块详解

### 5.1 入口 & 核心控制器 (`main.py`)

**文件路径**: `main.py`  
**行数**: ~557 行

#### 关键类

##### `TriggerBridge(QObject)`

键盘热键事件到 Qt 信号系统的桥接器。

```python
class TriggerBridge(QObject):
    fired = pyqtSignal(str)  # 发射热键动作名: "select" | "fullscreen" | "panel"
```

- `keyboard` 库的回调运行在非 Qt 线程中，不能直接操作 UI
- `TriggerBridge` 通过信号将事件安全地传递到 Qt 主线程

##### `OCRWorker(QObject)`

后台 OCR 识别工作线程。

```python
class OCRWorker(QObject):
    finished = pyqtSignal(list)  # 完成后发射: [(name, box), ...]

    def __init__(self, recognizer: RelicNameRecognizer, frame):
        # recognizer: OCR 识别器实例
        # frame: numpy 数组 (BGR 截图)

    def run(self):
        # 在线程中执行 OCR，完成后发射 finished 信号
```

##### `AppCore` — 核心控制器

协调截图 → OCR → 查询 → 标注全流程的中央控制器。

**关键属性**:

| 属性 | 类型 | 说明 |
|------|------|------|
| `_camera` | `dxcam.DXCamera` | DirectX 截图摄像头（output_idx=0） |
| `_overlay` | `Overlay` | 全屏透明覆盖层 |
| `_management_panel` | `ManagementPanel` | 管理面板窗口 |
| `_relic_ocr` | `RelicNameRecognizer` | OCR 识别器 |
| `_relic_db` | `RelicDB` | 数据库查询接口 |
| `_ocr_thread` | `QThread` | OCR 后台线程 |
| `_screenshot_lock` | `threading.Lock` | 截图竞态保护锁 |
| `_pending_mode` | `str` | 用户在 OCR 完成前预选的功能模式 |

**关键方法**:

| 方法 | 说明 |
|------|------|
| `run()` | 启动流程：初始化 DB → 绑定事件 → 注册热键 → 启动定时器 → 进入事件循环 |
| `do_screenshot()` | 框选区域截图 → 启动异步 OCR |
| `do_screenshot_fullscreen()` | 全屏截图 → 清除旧标注 → 启动异步 OCR |
| `_process_frame()` | 截图后：保存调试图 → 显示功能按钮 → 启动 OCR 线程 |
| `_start_ocr_async()` | 创建 QThread + OCRWorker，启动异步识别 |
| `_on_ocr_finished()` | OCR 完成回调：更新 UI 标签，处理待执行模式 |
| `on_mode_selected()` | 用户点击功能按钮 → 等待/执行功能 |
| `_handle_check_status()` | 出入库查询：遍历遗物 → 数据库查询 → 流式标注 |
| `_handle_query_parts()` | 遗物内容查询：遍历遗物 → 查询部件 → 稀有度着色 |
| `_cleanup_ocr_thread()` | 安全退出 OCR 线程（带超时强制终止） |
| `_register_hotkeys()` | 反注册旧热键 → 注册新热键 |

**DPI 处理**:

- `qt.conf` 中设置 `dpiawareness=0` 使 Qt 使用逻辑坐标
- dxcam 返回物理像素坐标
- `_dpi_scale` 用于两者之间的转换：
  ```python
  phys_x = int(logical_x * dpi_scale)
  logical_x = int(phys_x / dpi_scale)
  ```

**信号绑定**:

```python
self._overlay.on_selection_done = self.do_screenshot       # 框选完成回调
self._overlay.mode_selected.connect(self.on_mode_selected) # 功能按钮点击
self._bridge.fired.connect(self._handle_trigger)            # 热键触发
self._management_panel.db_updated.connect(self.reload_db)   # 数据库更新
self._management_panel.hotkeys_changed.connect(...)         # 热键变更
self._management_panel.theme_changed.connect(...)           # 主题变更
```

---

### 5.2 覆盖层系统 (`overlay.py`)

**文件路径**: `core/overlay.py`  
**行数**: ~660 行

全屏透明覆盖层，三种工作状态，是整个项目的视觉输出核心。

#### 三种状态

| 状态 | 鼠标穿透 | 功能 |
|------|---------|------|
| **空闲** | 穿透 | 只显示标注和按钮，不干扰游戏操作 |
| **框选** | 不穿透 | 拦截鼠标事件，允许拖拽框选区域 |
| **标注** | 穿透 | 按钮不穿透，标注区域穿透 |

#### 关键功能模块

**1. 鼠标穿透控制**

使用 Qt `WA_TransparentForMouseEvents` 属性（非 Win32 `WS_EX_TRANSPARENT`）实现精细控制：

```python
def _apply_mouse_passthrough(self, enabled: bool):
    self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
    self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
    for btn in self._mode_buttons.values():
        btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)  # 按钮永远不穿透
```

**2. 框选模式**

- `start_selection()` — 进入框选：禁用穿透、设十字光标、启动 60fps 鼠标追踪
- `_track_mouse()` — 每 16ms 检测：左键按下/拖拽/松开，右键/ESC 取消
- `_finish_selection()` — 保存区域到 `%APPDATA%/WARFRAME-RELIC/config.json`
- 使用 Win32 `GetAsyncKeyState` 检测按键（Qt 事件在透明窗口上不可靠）

**3. 功能按钮**

```python
modes = [
    ("check_status", "📋 出入库查询"),
    ("query_parts", "🔍 遗物内容查询"),
]
```

- 截图完成后立即显示（不等 OCR）
- 点击发射 `mode_selected` 信号
- 支持 `show_mode_buttons(relic_count)` 区分 OCR 完成/未完成状态

**4. 标注系统**

支持多种标注格式（向后兼容）：

```python
# 3 元组: (text, x, y)                         → 默认色 + 自动隐藏
# 4 元组: (text, x, y, color)                   → 指定色 + 自动隐藏
# 5 元组: (text, x, y, expire_ms, color)        → 完全自定义
# 6 元组: (text, x, y, expire_ms, color, [line_colors]) → 多行分别着色
```

**5. 流式标注动画**

```python
def show_annotations_stream(self, annotations, auto_hide_ms=5000, interval_ms=30, batch_size=2):
```

- 使用 `QTimer` 定时逐批弹出标注
- `interval_ms` 控制弹出间隔
- `batch_size` 控制每批弹出数量
- 产生「逐步出现」的动画感

**6. 绘制系统**

`paintEvent()` 负责所有视觉渲染：

- **框选状态**: 半透明遮罩 + 顶部状态栏 + 准星/选区矩形
- **标注状态**: 半透明深色背景 + 2077 风格左边框装饰条 + 多行着色文本

**7. 右键清除**

在 `_check_auto_hide()` 中通过 Win32 `GetAsyncKeyState(VK_RBUTTON)` 检测右键：
- 清除所有标注
- 隐藏功能按钮
- 清除 label 文字

---

### 5.3 管理面板 (`management_panel.py`)

**文件路径**: `core/management_panel.py`  
**行数**: ~632 行

独立窗口，通过热键 `Ctrl+Shift+G` 唤起。采用 **委托模式**，将子功能委托给 `ThemePanel` 和 `UpdatePanel`。

#### 布局结构

```
┌──────────────────────────────────────────────────────────┐
│  WARFRAME-RELIC 管理面板                                  │
├────────────────────┬──────────────┬───────────────────────┤
│  左侧主面板 (可滚动) │  日志面板     │  主题配色侧滑面板       │
│                    │  (420px 宽)  │  (0~320px 动画宽度)   │
│  ┌──────────────┐  │              │                       │
│  │ 数据库状态    │  │  运行日志    │  预设方案下拉框          │
│  │ 手动数据更新  │  │  步骤指示    │  色块编辑区              │
│  │ 自动数据更新  │  │  下载进度    │  保存/恢复/刷新按钮      │
│  │ 快捷键设置    │  │  日志详情    │                       │
│  │ 自定义配色    │  │              │                       │
│  │ 关于作者      │  │              │                       │
│  └──────────────┘  │              │                       │
│  底部提示 / 退出    │              │                       │
└────────────────────┴──────────────┴───────────────────────┘
```

#### 六大功能区块

| 区块 | 构建方法 | 说明 |
|------|---------|------|
| 数据库状态 | `_build_status_group()` | 8 项统计（遗物数/部件数/出入库等）+ 进度条 |
| 手动数据更新 | `_build_source_group()` | 选择本地 `all.json` → 更新数据库 |
| 自动数据更新 | `_build_action_group()` | 从 GitHub 拉取 → 自动更新数据库 |
| 快捷键设置 | `_build_hotkey_group()` | 3 个热键输入框 + 格式校验 + 保存/重置 |
| 自定义配色 | `_build_theme_group()` | 按钮触发侧滑面板 |
| 关于作者 | `_build_about_group()` | 作者信息 + B站/GitHub 链接 |

#### 子面板委托

```python
# ThemePanel — 配色侧滑面板
self._theme_panel = ThemePanel(
    parent_widget=self,
    on_theme_changed=self._on_theme_changed_internal,  # 主题变更回调
    add_log=self._add_log,                              # 日志回调
)

# UpdatePanel — 数据更新 + 日志
self._update_panel = UpdatePanel(
    parent_widget=self,
    data_dir=self._data_dir,
    db_path=self._db_path,
    add_log=self._add_log,
)
```

#### 信号发射

```python
db_updated = pyqtSignal(str)        # 数据库更新完成 → 携带 db_path
hotkeys_changed = pyqtSignal(dict)  # 快捷键变更 → 携带新热键字典
theme_changed = pyqtSignal()        # 主题变更 → 通知 AppCore 刷新 Overlay
```

#### 窗口行为

- `closeEvent()` 不关闭窗口，只隐藏（`event.ignore()`）
- 正在更新时不允许关闭
- 首次显示时自动调整尺寸

---

### 5.4 数据更新 & 日志 (`update_panel.py`)

**文件路径**: `core/update_panel.py`  
**行数**: ~611 行

管理数据拉取（GitHub）、数据库更新、日志输出三大功能。

#### 核心类: `UpdatePanel(QObject)`

不继承 QWidget，而是管理嵌入到 ManagementPanel 中的 UI 组件。

**属性注入模式**:

由于 UI 由 `ManagementPanel._build_*` 方法创建，`UpdatePanel` 通过 setter 方法接收 UI 组件引用：

```python
update_panel.set_source_label(label)
update_panel.set_progress(progress_bar, progress_text)
update_panel.set_buttons(btn_update, btn_update2, btn_fetch, btn_browse, ...)
update_panel.set_log_panel_widgets(log_panel, log_area, step_icon, step_label, ...)
update_panel.set_stat_labels(stat_labels_dict)
```

#### 数据拉取流程

```
on_fetch()
  → 弹窗确认
  → 显示日志面板
  → 创建 FetchWorker 后台线程
  → 7 步精细化进度回调:
      1. 解析目标地址
      2. DNS 解析
      3. 建立安全连接（HTTPS + TLS）
      4. 获取文件信息（Content-Length 等）
      5. 下载数据（带百分比进度）
      6. 验证 JSON 格式
      7. 保存文件（自动备份旧文件）
  → 下载成功 → 自动触发 on_update()
```

#### 数据库更新流程

```
on_update()
  → 检查 all.json 是否存在
  → 弹窗确认
  → 创建 UpdateWorker 后台线程
  → 进度回调: 读取数据 → 写入数据库 → 完成
  → 更新统计信息
  → 发射 db_updated 信号
```

#### 日志系统

```python
def _format_log_line(self, log_type: str, msg: str) -> str:
    # 格式: [HH:MM:SS] ✓/⚠/✗ message
    # 颜色由 theme.log_color_map 控制
    # 使用 HTML 富文本渲染
```

日志类型与颜色映射：
| log_type | 图标 | 颜色键 | 用途 |
|----------|------|--------|------|
| `ok` | ✓ | `log_ok` | 成功操作 |
| `warn` | ⚠ | `log_warn` | 警告信息 |
| `error` | ✗ | `log_error` | 错误信息 |
| `info` | (空格) | `log_info` | 一般信息 |

---

### 5.5 主题配色系统

> 详见 [第 7 节：配色系统深度剖析](#7-配色系统深度剖析)

配色系统由 4 个文件组成：

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/theme_config.py` | ~440 | **ThemeConfig 单例**：配色加载/保存/预设切换/派生属性 |
| `core/theme_proxy.py` | ~150 | **_ThemeProxy 代理**：75 个模块级颜色常量，自动跟随主题 |
| `core/theme_fields.py` | ~79 | **THEME_FIELDS 列表**：65 个色块的元信息（键名/标签/类别） |
| `core/theme_panel.py` | ~410 | **ThemePanel**：侧滑面板 UI，色块编辑/预设切换/动画 |

此外 `core/constants.py` 作为兼容层重新导出所有主题相关符号。

---

### 5.6 OCR 识别系统 (`relic_name.py`)

**文件路径**: `recognizers/relic_name.py`  
**行数**: ~83 行

#### 核心类: `RelicNameRecognizer`

使用 RapidOCR (ONNX Runtime) 进行离线文字识别。

**正则匹配模式**:

```python
RELIC_PATTERN = re.compile(
    r'(古纪|前纪|中纪|后纪|安魂|先锋)[\s.,，。、]*([A-TV-Z0-9]\d+)')
```

匹配 Warframe 遗物命名格式：纪元（中文）+ 字母 + 数字。例如：
- `古纪 C7` / `前纪 A12` / `中纪 N8` / `后纪 G14`

**过滤规则**:

```python
TRASH_PATTERN = re.compile(r'^[xX]\d+$|^$$.*[$$】]$|^不装备遗物$')
```

过滤无效识别结果。

**OCR 纠错**:

1. **字符替换映射**（`OCR_FIX_MAP`）: 处理 OCR 常见混淆
   ```python
   str.maketrans({'\u2018': 'L', '\u2019': 'L', ',': 'L', '|': 'I', ';': 'L'})
   ```

2. **数字→字母修正**（`_fix_ocr_number`）: 如果识别结果以数字开头，将其替换为易混淆的字母
   ```python
   {'0': 'O', '1': 'I', '5': 'S', '8': 'B'}
   ```

**图像放大策略**:

```python
if w > OCR_UPSCALE_MIN_WIDTH:  # 900px
    scale = 1.5  # 放大 1.5 倍
```

截图宽度超过 900px 时自动放大以提高 OCR 准确率。

**识别流程**:

```
1. 接收 numpy 图像数组 (BGR)
2. 判断是否需要放大 (scale = 1.5 或 1.0)
3. RapidOCR 执行文字检测 + 识别
4. 遍历识别结果:
   a. 过滤无效文本
   b. 字符替换修正
   c. 正则匹配遗物名
   d. 数字→字母修正
5. 返回 [(name, box), ...] 列表
```

---

### 5.7 数据库模块 (`wfinfo_relics.py`)

**文件路径**: `data/wfinfo_relics.py`  
**行数**: ~208 行

#### 核心类: `RelicDB`

SQLite 数据库的查询封装，线程安全。

**数据库表结构**:

```sql
-- 遗物主表
relics (id, name, era, code, vaulted)

-- 部件表（外键关联）
relic_parts (id, relic_id, part_name, rarity, chance)

-- 别名表（OCR 模糊匹配用）
relic_aliases (id, relic_id, alias)
```

其中 `vaulted` 字段含义：
- `0` = 入库（不可获取）
- `1` = 出库（可获取）
- `2` = 虚空商人可购买（功能未实现）

**四级查询匹配**（`find()` 方法）:

| 级别 | 方法 | 说明 |
|------|------|------|
| 1 | 别名精确匹配 | 在 `relic_aliases` 表中精确查找 |
| 2 | 主表精确匹配 | 在 `relics.name` 中精确查找 |
| 3 | 忽略空格大小写 | 去空格 + 小写后匹配别名 |
| 4 | 正则模糊匹配 | 统一易混淆字符（O/0→o, I/1/l→i, S/5→s, B/8→b）后匹配 |

**线程安全**:

```python
self._lock = threading.Lock()

def _get_conn(self):
    if self._conn is None:
        with self._lock:
            if self._conn is None:  # 双重检查锁定
                self._conn = sqlite3.connect(self._db_path)
                ...
    return self._conn
```

- 使用双重检查锁定（DCL）保护连接生命周期
- `invalidate()` 方法安全关闭旧连接，供数据库更新后重新打开
- SQLite 使用 WAL 模式提高并发读取性能

**关键方法**:

| 方法 | 说明 |
|------|------|
| `load()` | 检查数据库可用性 |
| `find(name)` | 四级匹配查找遗物 |
| `get_parts(name)` | 获取遗物部件列表 |
| `is_vaulted(name)` | 检查是否出库 |
| `query_many(names)` | 批量查询 |
| `stats()` | 数据库统计信息 |
| `invalidate()` | 通知外部更新，关闭连接 |
| `close()` | 关闭数据库连接 |

---

### 5.8 快捷键系统 (`hotkey_config.py`)

**文件路径**: `core/hotkey_config.py`  
**行数**: ~95 行

#### 默认热键

```python
DEFAULT_HOTKEYS = {
    "select": "ctrl+g",           # 框选截图
    "fullscreen": "ctrl+h",       # 全屏截图
    "panel": "ctrl+shift+g",     # 管理面板
}
```

#### 配置持久化

- **配置文件**: `data/hotkeys.json`
- **策略**: 只保存与默认值不同的键（精简文件）
- **容错**: 文件损坏时返回默认值

#### 格式验证

```python
def validate_hotkey(hotkey_str: str) -> bool:
    # 至少 1 个修饰键 + 1 个普通键
    # 修饰键: ctrl, alt, shift, win
    # 普通键不能是修饰键
```

#### 热键注册机制

在 `AppCore._register_hotkeys()` 中：
1. 反注册所有旧热键
2. 遍历动作映射，使用 `keyboard.add_hotkey()` 注册新热键
3. 热键回调通过 `TriggerBridge.fired` 信号发射到 Qt 主线程

---

### 5.9 样式表生成 (`stylesheet.py`)

**文件路径**: `core/stylesheet.py`  
**行数**: ~155 行

动态生成 Qt QSS 样式表，所有颜色值从 `ThemeConfig` 单例读取。

**两个生成函数**:

| 函数 | 用途 |
|------|------|
| `build_stylesheet()` | 管理面板全局样式（含 QGroupBox, QLabel, QPushButton, QProgressBar） |
| `build_dialog_button_style()` | 弹窗 OK 按钮样式 |

**按钮样式角色**:

| QSS ObjectName | 用途 | 对应颜色键 |
|---------------|------|-----------|
| `primaryBtn` | 蓝色主按钮 | `primary_*` |
| `actionBtn` | 普通操作按钮 | `btn_default_*` |
| `dangerBtn` | 红色危险按钮 | `danger_*` |
| `successBtn` | 绿色成功按钮 | `success_*` |

---

### 5.10 后台 Worker 线程

#### FetchWorker (`core/fetch_worker.py`)

从 GitHub 下载 `all.json` 的后台线程，7 步精细化进度反馈。

**信号**:

```python
step_changed = pyqtSignal(int, str)    # 当前步骤 (1~7), 步骤描述
log = pyqtSignal(str, str)             # (类型, 消息)
progress_pct = pyqtSignal(int)         # 下载进度 0~100
finished = pyqtSignal(str)             # 完成 → 携带保存路径
error = pyqtSignal(str)                # 致命错误
```

**7 步流程**:

| 步骤 | 描述 | 关键操作 |
|------|------|---------|
| 1 | 解析目标地址 | `urlparse()` |
| 2 | DNS 解析 | `socket.getaddrinfo()` |
| 3 | 建立安全连接 | HTTPS + TLS 握手，带重试（最多 2 次） |
| 4 | 获取文件信息 | Content-Length, Content-Type, Last-Modified |
| 5 | 下载数据 | 8KB 块读取，实时进度（每 20% 记录日志） |
| 6 | 验证数据格式 | `json.loads()` 校验 |
| 7 | 保存文件 | 备份旧文件 → 写入新文件 |

#### UpdateWorker (`core/update_worker.py`)

数据库更新后台线程（轻量）。

```python
class UpdateWorker(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        # 调用 update_db.update_from_alljson() → _finalize_db()
```

---

## 6. 数据层详解

### 6.1 数据文件说明

| 文件 | 大小 | 说明 |
|------|------|------|
| `data/all.json` | ~6MB | WFInfo 全量掉落数据（从 GitHub 下载） |
| `data/all.json.bak` | ~6MB | 下载前的自动备份 |
| `data/relics.db` | ~616KB | SQLite 遗物数据库（主查询源） |
| `data/hotkeys.json` | <1KB | 快捷键配置（仅保存非默认值） |
| `data/presets/_active.json` | <1KB | 当前活动配色预设 ID |
| `data/presets/cyberpunk.json` | ~2KB | 赛博朋克配色（用户修改版） |
| `data/presets/daylight.json` | ~2KB | 白天模式配色（用户修改版） |
| `data/presets/custom.json` | ~2KB | 自定义配色 |

### 6.2 数据库生成流程

```
all.json (WFCD 数据源)
    │
    ▼
update_db.py / UpdateWorker
    │
    ├── extract_dropping_relics() → 解析掉落来源，标记 vaulted=1
    ├── migrate_alljson_to_db()   → 去重 (保留 Intact) → 写入 SQLite
    └── _finalize_db()            → 替换旧数据库文件
    │
    ▼
relics.db (3 表 + 5 索引)
    ├── relics (遗物主表)
    ├── relic_parts (部件表, FK → relics)
    └── relic_aliases (别名表, FK → relics)
```

### 6.3 别名生成策略

每个遗物自动生成 5 个别名变体（`db_utils.generate_aliases()`）：

```python
[
    "古纪 C7",           # 原始名称
    "古纪 C7",           # 标准名（同上）
    "古纪C7",            # 无空格
    "古纪 c7",           # 小写带空格
    "古纪c7",            # 小写无空格
]
```

---

## 7. 配色系统深度剖析

### 7.1 系统架构

```
┌────────────────────────────────────────────────────┐
│                   ThemeConfig (单例)                 │
│                                                     │
│  内部状态:                                           │
│    _data: dict      ← 当前所有颜色值                  │
│    _active_preset: str ← "cyberpunk"/"daylight"/"custom" │
│    _DEFAULTS: dict  ← 出厂默认值 (Cyberpunk 2077)    │
│                                                     │
│  公共 API:                                           │
│    theme.cyber_yellow  → 直接属性访问 (__getattr__)  │
│    theme.save(dict)    → 保存修改 + 自动切换预设      │
│    theme.reload()      → 热重载                       │
│    theme.reset()       → 恢复出厂默认                 │
│    theme.apply_preset()→ 切换预设                     │
│    theme.to_dict()     → 导出字典副本                  │
└──────────┬─────────────────────────────────────────┘
           │
           │ 代理读取
           ▼
┌────────────────────────────────────────────────────┐
│                _ThemeProxy (属性代理)                │
│                                                     │
│  75 个模块级常量:                                    │
│    CYBER_YELLOW  = _proxy('cyber_yellow')           │
│    COLOR_VAULTED = _proxy('color_vaulted')          │
│    BTN_DEFAULT_BG = _proxy('btn_default_bg')       │
│    ...                                              │
│                                                     │
│  特性: 每次访问都从 theme 实时取值，无需手动同步       │
└────────────────────────────────────────────────────┘
```

### 7.2 65 个配色字段（按类别）

| 类别 | 字段数 | 字段示例 |
|------|--------|---------|
| 界面主色 | 7 | `cyber_yellow`, `cyber_cyan`, `cyber_magenta`, `cyber_orange`, `cyber_red`, `cyber_green`, `cyber_blue` |
| 面板背景 | 8 | `dark_bg`, `panel_bg`, `card_bg`, `border`, `text`, `text_dim`, `label_default`, `panel_darkest`, `panel_deeper` |
| 遗物状态 | 3 | `color_vaulted`, `color_available`, `color_unknown` |
| 部件稀有度 | 3 | `color_gold`, `color_silver`, `color_copper` |
| 日志颜色 | 6 | `log_ok`, `log_warn`, `log_error`, `log_info`, `log_debug`, `log_timestamp` |
| 按钮样式 | 22 | `btn_default_*` (7), `primary_*` (7), `danger_*` (4), `success_*` (4) |
| 外链品牌 | 4 | `brand_bilibili`, `brand_bilibili_hover`, `brand_github`, `brand_github_hover` |
| 游戏覆盖层 | 8 | `overlay_*_rgba` (3), `overlay_crosshair_color`, `overlay_selection_border`, `progress_gradient_*` (3), `fetch_*` (2) |

### 7.3 预设系统

**三套预设**:

| 预设 ID | 名称 | 说明 |
|---------|------|------|
| `cyberpunk` | 赛博朋克 2077（推荐） | 霓虹暗色主题，默认配色 |
| `daylight` | 白天模式 | 白色基调，适合明亮环境 |
| `custom` | 自定义配色 | 用户专属配色方案 |

**预设切换逻辑** (`apply_preset()`):

```
1. 保存当前配色到当前预设文件
2. 重新加载出厂默认值 (ThemeConfig._DEFAULTS)
3. 根据目标预设 ID:
   - cyberpunk → 加载 cyberpunk.json 覆盖
   - custom    → 加载 custom.json 覆盖
   - daylight  → 先用 PRESET_DATA 覆盖，再加载 daylight.json 覆盖
4. 更新 _active_preset → 写入 _active.json
5. 重建派生属性
```

**重要规则 — 修改保护**:

当用户在 `cyberpunk` 或 `daylight` 预设中修改颜色并保存时：
- `save()` 方法自动将 `_active_preset` 切换为 `"custom"`
- 完整配色数据写入 `custom.json`
- UI 下拉框自动同步到「自定义配色」
- 内置预设文件保持干净，不被用户修改污染

### 7.4 派生属性

`_build_derived()` 从原始数据构建派生属性：

```python
# RGBA 元组（供覆盖层使用）
self.overlay_bg_rgba = tuple(d["overlay_bg_rgba"])
self.overlay_selection_overlay_rgba = tuple(d["overlay_selection_overlay_rgba"])
self.overlay_status_bg_rgba = tuple(d["overlay_status_bg_rgba"])

# 日志颜色映射
self.log_color_map = {
    "ok": d["log_ok"], "warn": d["log_warn"],
    "error": d["log_error"], "info": d["log_info"],
    "debug": d["log_debug"],
}
```

### 7.5 属性访问机制

`ThemeConfig` 使用 `__getattr__` 代理未定义的属性到 `_data` 字典：

```python
def __getattr__(self, name):
    if name.startswith('_'):
        raise AttributeError(name)
    if '_data' in self.__dict__ and name in self._data:
        return self._data[name]
    raise AttributeError(...)
```

这样 `theme.cyber_yellow` 等价于 `theme._data["cyber_yellow"]`。

### 7.6 _ThemeProxy 代理机制

```python
class _ThemeProxy:
    __slots__ = ('_attr',)

    def __init__(self, attr: str):
        object.__setattr__(self, '_attr', attr)

    def _value(self):
        return getattr(theme, self._attr)  # 每次访问都实时读取
```

所有魔术方法（`__str__`, `__eq__`, `__hash__`, `__getitem__` 等）都转发到 `_value()`。因此：

```python
from core.constants import CYBER_YELLOW
# CYBER_YELLOW 是 _ThemeProxy('cyber_yellow') 实例
# 每次使用 CYBER_YELLOW 都从 theme.cyber_yellow 实时取值
# 主题切换后无需手动同步
```

### 7.7 向后兼容

`constants.py` 作为兼容层重新导出所有主题符号：

```python
from core.theme_config import theme, ThemeConfig
from core.theme_proxy import (
    CYBER_YELLOW, CYBER_CYAN, ...  # 75 个符号
)
```

旧代码 `from core.constants import CYBER_YELLOW` 无需任何修改。

---

## 8. 线程安全与并发

### 8.1 线程模型

```
┌─────────────────────────────────────────┐
│             Qt 主线程 (事件循环)           │
│  - UI 渲染 (Overlay / ManagementPanel)   │
│  - 信号/槽处理                            │
│  - QTimer 定时器                          │
├─────────────────────────────────────────┤
│         OCR 后台线程 (QThread)             │
│  - RapidOCR 文字检测 + 识别               │
│  - 完成后通过 finished 信号通知主线程       │
├─────────────────────────────────────────┤
│     Fetch 后台线程 (threading.Thread)     │
│  - urllib 下载 + JSON 校验 + 文件保存     │
│  - 通过 pyqtSignal 跨线程通信             │
├─────────────────────────────────────────┤
│     Update 后台线程 (threading.Thread)    │
│  - SQLite 写入操作                        │
│  - 通过 pyqtSignal 跨线程通信             │
└─────────────────────────────────────────┘
```

### 8.2 安全措施

| 场景 | 措施 | 位置 |
|------|------|------|
| 截图竞态 | `threading.Lock` — `_screenshot_lock` | `AppCore._process_frame()` |
| OCR 线程冲突 | 启动前 `_cleanup_ocr_thread()` 安全退出上一轮 | `AppCore._start_ocr_async()` |
| OCR 线程超时 | `thread.wait(2000)` + `thread.terminate()` 兜底 | `AppCore._cleanup_ocr_thread()` |
| 数据库连接 | `threading.Lock` 双重检查锁定 | `RelicDB._get_conn()` |
| 热键连按 | `_screenshot_busy` 标志位 + Lock | `AppCore.do_screenshot()` |
| 退出清理 | `aboutToQuit` → `_shutdown()` 统一释放 | `AppCore.run()` |
| 信号断开 | 清理时 `disconnect()` 防止野回调 | `AppCore._cleanup_ocr_thread()` |

### 8.3 OCR 线程生命周期

```
截图完成
  → _cleanup_ocr_thread()  [安全退出上一轮]
  → 创建 QThread + OCRWorker
  → worker.moveToThread(thread)
  → 连接信号:
      worker.finished → _on_ocr_finished
      thread.started → worker.run
      thread.finished → _on_ocr_thread_done
  → thread.start()
  → [OCR 执行中...]
  → worker.finished.emit(relics)
  → _on_ocr_finished() 处理结果
  → thread.finished 触发
  → _on_ocr_thread_done() 清理线程
```

---

## 9. 配置与持久化

### 9.1 配置文件一览

| 文件 | 位置 | 格式 | 读写模块 |
|------|------|------|---------|
| 配色预设 | `data/presets/*.json` | JSON | `theme_config.py` |
| 活动预设 | `data/presets/_active.json` | JSON | `theme_config.py` |
| 快捷键 | `data/hotkeys.json` | JSON | `hotkey_config.py` |
| 框选区域 | `%APPDATA%/WARFRAME-RELIC/config.json` | JSON | `overlay.py` |
| 调试截图 | `%APPDATA%/WARFRAME-RELIC/debug/last_capture.png` | PNG | `main.py` |

### 9.2 框选区域持久化

```python
# 保存 (overlay.py)
def _save_region(self):
    with open(self._config_path(), 'w') as f:
        json.dump({'region': list(self._saved_region)}, f)

# 加载 (overlay.py)
def _load_region(self):
    path = self._config_path()
    if os.path.exists(path):
        with open(path, 'r') as f:
            cfg = json.load(f)
            r = cfg.get('region')
            if r:
                self._saved_region = (r[0], r[1], r[2], r[3])
```

### 9.3 快捷键持久化

```python
# 只保存与默认值不同的键（精简文件）
def save_hotkeys(hotkeys):
    to_save = {k: v for k, v in hotkeys.items() if v != DEFAULT_HOTKEYS.get(k)}
    # 如果 to_save 为空，写入 {}（表示使用全部默认值）
```

---

## 10. 构建与打包

### 10.1 开发模式运行

```bash
# 直接启动
python main.py

# 热重载模式（修改 .py 后自动重启）
python dev_runner.py

# 单次运行（捕获输出）
python dev_runner.py --once --stdout
```

### 10.2 打包为 EXE

**打包脚本**: `build_exe.py` (5 步骤)

| 步骤 | 说明 |
|------|------|
| 1. 检查环境 | 验证 Python 版本和所有依赖包 |
| 2. 安装 PyInstaller | 自动安装（使用腾讯云镜像加速） |
| 3. 清理旧构建 | 删除 `build/`, `dist/`, `*.spec` |
| 4. PyInstaller 打包 | `--onedir` 模式，排除无关模块 |
| 5. 验证输出 | 检查 EXE 和文件夹大小 |

**排除策略**:
- 排除 rapidocr-onnxruntime 拉进来的无关大包：`torch`, `scipy`, `pandas` 等
- 排除用不到的 PyQt6 子模块：`QtWebEngine`, `QtMultimedia`, `QtBluetooth` 等 30+ 个
- 保留核心：`QtCore`, `QtGui`, `QtWidgets`

**输出**: `dist/WARFRAME-RELIC/WARFRAME-RELIC.exe`（文件夹分发）

### 10.3 一键操作

| 批处理文件 | 功能 |
|-----------|------|
| `SETUP.bat` | 检测/安装 Python → 创建 venv → 安装依赖 → 启动 |
| `WARFRAME-RELIC.bat` | 检查环境 → 启动程序 |
| `打包.bat` | 切换 UTF-8 编码 → 执行 `build_exe.py` |
| `git-push.bat` | Git add → commit → push |

---

## 11. 开发工具

### 11.1 OCR 测试工具

```bash
python test_recognizer.py
```

对 `%APPDATA%/WARFRAME-RELIC/debug/last_capture.png` 进行 OCR 识别并输出结果，用于调试识别准确率。

### 11.2 数据库更新 CLI

```bash
python update_db.py
```

命令行直接更新数据库，不依赖 GUI。

### 11.3 崩溃日志

`dev_runner.py` 监听模式下，子进程崩溃时自动写入 `crash_log.txt`，包含退出码和 stderr 输出。

---

## 12. 常见开发任务

### 12.1 添加新的功能按钮

1. 在 `overlay.py` 的 `_setup_buttons()` 中的 `modes` 列表添加新模式：
   ```python
   modes = [
       ("check_status", "📋 出入库查询"),
       ("query_parts", "🔍 遗物内容查询"),
       ("new_feature", "🆕 新功能"),  # 添加这行
   ]
   ```

2. 在 `main.py` 的 `on_mode_selected()` 中添加处理分支：
   ```python
   elif mode == "new_feature":
       self._handle_new_feature()
   ```

3. 实现 `_handle_new_feature()` 方法

### 12.2 添加新的配色字段

1. 在 `core/theme_config.py` 的 `_DEFAULTS` 字典中添加默认值
2. 在 `core/theme_fields.py` 的 `THEME_FIELDS` 列表中添加字段元信息
3. 在 `core/theme_proxy.py` 中添加对应的代理常量（如果需要模块级访问）
4. 在 `core/constants.py` 的 re-export 列表中添加（如果需要向后兼容）
5. 如果需要 daylight 预设的特殊值，在 `PRESET_DATA["daylight"]` 中添加

### 12.3 修改 OCR 识别参数

在 `core/constants.py` 中修改：

```python
OCR_TEXT_SCORE = 0.35       # 文本置信度阈值（提高 = 更严格）
OCR_BOX_THRESH = 0.2        # 检测框阈值
OCR_UPSCALE_MIN_WIDTH = 900 # 触发放大的最小截图宽度
```

### 12.4 添加新的热键

1. 在 `core/hotkey_config.py` 的 `DEFAULT_HOTKEYS` 中添加：
   ```python
   DEFAULT_HOTKEYS = {
       "select": "ctrl+g",
       "fullscreen": "ctrl+h",
       "panel": "ctrl+shift+g",
       "new_action": "ctrl+n",  # 添加
   }
   ```

2. 在 `HOTKEY_LABELS` 中添加中文标签

3. 在 `main.py` 的 `_handle_trigger()` 中添加处理逻辑

4. 在 `_register_hotkeys()` 的 `action_map` 中添加映射

### 12.5 主题变更时刷新 UI

主题变更的传播链：

```
ThemePanel._on_save() / _on_apply_preset()
  → theme.save() / theme.apply_preset()
  → _on_theme_changed() 回调
  → ManagementPanel._on_theme_changed_internal()
      → _rebuild_styles_and_swatches()  # 刷新管理面板
      → theme_changed.emit()             # 发射信号
  → AppCore._on_theme_changed()
      → overlay.refresh_theme()          # 刷新覆盖层
```

如需在新增的 UI 组件中响应主题变更，在 `ManagementPanel._refresh_inline_styles()` 中添加对应的样式刷新代码。

---

## 13. 模块依赖关系图

```
main.py
├── core/overlay.py
│   └── core/constants.py (颜色常量)
│       ├── core/theme_config.py (ThemeConfig 单例)
│       └── core/theme_proxy.py (_ThemeProxy)
├── core/management_panel.py
│   ├── core/constants.py (theme, ThemeConfig, reload_theme)
│   ├── core/stylesheet.py
│   │   └── core/constants.py (theme)
│   ├── core/hotkey_config.py
│   ├── core/theme_fields.py
│   ├── core/theme_panel.py
│   │   ├── core/constants.py (theme, ThemeConfig)
│   │   └── core/theme_fields.py
│   └── core/update_panel.py
│       ├── core/constants.py (theme)
│       ├── core/stylesheet.py
│       ├── core/update_worker.py
│       │   └── update_db.py
│       └── core/fetch_worker.py
├── recognizers/relic_name.py
│   └── core/constants.py (OCR 参数)
├── data/wfinfo_relics.py (RelicDB)
├── core/hotkey_config.py
└── core/constants.py (DXCAM 参数, 颜色常量)

core/theme_config.py (无项目内依赖，仅标准库)
core/theme_proxy.py
    └── core/theme_config.py (theme 单例)
core/theme_fields.py (无项目内依赖)

data/db_utils.py (无项目内依赖，仅标准库)
```

**关键设计原则**:
- `theme_config.py` 是**叶子模块**，不依赖任何项目内模块
- `theme_proxy.py` 只依赖 `theme_config.py`
- `constants.py` 作为**兼容层**，从上述两个模块 re-export
- 所有 UI 模块通过 `constants.py` 间接依赖主题系统
- 数据层 (`data/`) 与核心逻辑层 (`core/`) 互相独立

---

## 附录

### A. WFInfo 数据格式

`all.json` 中的遗物条目结构：

```json
{
  "tier": "Lith",
  "relicName": "C7",
  "state": "Intact",
  "rewards": [
    {
      "itemName": "Forma Blueprint",
      "rarity": "Common",
      "chance": 25.33
    }
  ]
}
```

### B. OCR 识别结果格式

```python
# recognize_all_with_boxes() 返回值
[
    ("古纪 C7", [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]),  # (名称, 四点坐标框)
    ("前纪 A12", [[...], [...], [...], [...]]),
    ...
]
```

### C. 标注数据格式

```python
# 完整格式 (6 元组)
(
    text,              # 标注文本（可含 \n 多行）
    x, y,              # 左上角坐标（逻辑像素）
    expire_ms,         # 过期时间偏移（毫秒）
    color,             # 主颜色
    [line_colors],     # 每行颜色列表（可选）
)
```

### D. 坐标系统

- **物理像素**: dxcam 返回的坐标，与实际屏幕像素一一对应
- **逻辑坐标**: Qt 使用的坐标，受 DPI 缩放影响
- **转换**: `physical = logical × dpi_scale`
- **DPI 缩放**: 通过 `QApplication.primaryScreen().logicalDotsPerInch() / 96` 计算

---

> 文档版本: 1.0 | 最后更新: 2026-05-30  
> 如发现文档与代码不一致，请以代码为准，并更新本文档。
