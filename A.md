# WARFRAME-RELIC 开发文档

> 版本：v3.4 | 更新日期：2026-06-02

---

## 一、项目概述

### 1.1 简介

WARFRAME-RELIC 是一个 **Warframe（星际战甲）游戏辅助工具**，基于 OCR 识别技术，通过半透明覆盖层在游戏画面上无侵入地显示辅助信息。

### 1.2 核心功能

| 功能 | 快捷键 | 说明 |
|------|--------|------|
| 框选截图 | `Ctrl+G` | 拖拽框选区域 → 松手自动截图识别 |
| 全屏截图 | `Ctrl+H` | 直接全屏截图识别 |
| 价格查询 | `Ctrl+T` | 自动4等分截图+识别+标注价格 |
| 清除标注 | 右键 | 清除所有标注和按钮 |

**截图后显示功能按钮：**

| 按钮 | 功能 | 数据来源 |
|------|------|----------|
| 出入库查询 | 标注遗物是否可获取（绿=出库/红=入库） | relics.db |
| 遗物内容查询 | 显示 Prime 部件（金银铜色区分稀有度） | relics.db |
| 价格查询 | 查询 warframe.market 实时价格 | wm_prices.db + API |
| 翻译 | 中英文双向翻译 | items_i18n.db |

### 1.3 技术栈

| 依赖 | 版本 | 用途 |
|------|------|------|
| **PyQt6** | ≥6.11.0 | GUI 框架（覆盖层、管理面板） |
| **dxcam** | ≥0.3.0 | DirectX 高速截图 |
| **keyboard** | ≥0.13.5 | 全局热键注册 |
| **rapidocr-onnxruntime** | ≥1.4.4 | OCR 引擎（离线识别） |
| **Pillow** | ≥12.0.0 | 图像处理 |
| **numpy** | ≥2.0.0 | 数组运算（截图切片） |
| **pypinyin** | ≥0.51.0 | 中文拼音转换（拼音搜索） |

---

## 二、项目结构

### 2.1 文件结构

```
WARFRAME-RELIC/
├── main.py                     # 程序入口：AppCore + TriggerBridge + OCRWorker
├── core/                       # 核心业务模块
│   ├── bootstrap.py            # 启动引导：单例检测、管理员检测、异常钩子、main()
│   ├── hotkey_manager.py       # 热键管理：注册/健康检查/自动恢复
│   ├── mode_handlers.py        # 功能处理器：四大功能（纯函数）
│   ├── overlay.py              # 全屏透明覆盖层
│   ├── region_selector.py      # 区域框选器
│   ├── management_panel.py     # 管理面板主窗口
│   ├── price_service.py        # 价格服务：三级查询
│   ├── drop_tooltip.py         # 物品掉落来源查询
│   ├── theme_config.py         # 主题配置引擎（单例，65+配色）
│   ├── theme_panel.py          # 主题可视化编辑面板
│   ├── stylesheet.py           # 动态 QSS 样式表生成
│   ├── hotkey_config.py        # 热键配置读写
│   ├── hotkey_capture_button.py # 热键捕获按钮
│   ├── constants.py            # 常量和主题
│   └── ...
├── recognizers/                # OCR 识别器
│   ├── base_ocr.py             # OCR 管线基类
│   ├── relic_name.py           # 遗物名称识别器
│   ├── item_name.py            # 物品名称识别器
│   └── matcher.py              # 4轮降级匹配引擎
├── data/                       # 数据和配置
│   ├── items_i18n.db           # 全物品中英对照（含拼音）
│   ├── relics.db               # 遗物掉落数据库
│   ├── wm_prices.db           # WM 价格缓存
│   ├── preset_*.py            # 三套文案预设
│   ├── ui_strings.py           # UI 字符串路由器
│   └── ...
├── assets/                     # SVG 图标资源
├── icon/                       # 图标资源
├── DATABASE.md                 # 数据库结构详细文档
├── README.md                   # 用户使用文档
├── requirements.txt            # Python 依赖
└── ...
```

### 2.2 模块依赖图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户操作                              │
│                   (热键/点击/框选)                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     main.py (AppCore)                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │ HotkeyManager   │  │ ModeHandlers    │  │ OCRWorker   │  │
│  │ (core/)         │  │ (core/)         │  │ (QThread)   │  │
│  └─────────────────┘  └─────────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
┌─────────────────────────────────────────────────────────────┐
│                        服务层                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────┐ │
│  │ Overlay    │  │ RegionSel. │  │ PriceSvc   │  │ Matcher │ │
│  └────────────┘  └────────────┘  └────────────┘  └────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                        数据层                               │
│  items_i18n.db  │  relics.db  │  wm_prices.db  │  JSON配置  │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块详解

### 3.1 AppCore — 中央控制器

**文件：** `main.py`

**职责：** 协调截图 → OCR → 查询 → 标注全流程。

**核心组件：**

| 组件 | 类型 | 作用 |
|------|------|------|
| `_camera` | `dxcam` | DirectX 高速截图 |
| `_overlay` | `Overlay` | 全屏透明覆盖层 |
| `_relic_ocr` | `RelicNameRecognizer` | 遗物名称 OCR |
| `_item_ocr` | `ItemNameRecognizer` | 物品名称 OCR |
| `_relic_db` | `RelicDB` | 遗物数据库 |
| `_bridge` | `TriggerBridge` | 热键→Qt信号桥接 |
| `_hotkey_mgr` | `HotkeyManager` | 热键管理器（委托） |

**核心状态：**

```python
self._last_frame = None      # 最近截图帧（numpy array）
self._last_region = None      # 最近截图区域
self._last_relics = []       # OCR缓存：遗物结果
self._last_items = []         # OCR缓存：物品结果
self._ocr_thread = None       # 当前OCR线程
```

**启动流程：**

```
main()
  → bootstrap.ensure_singleton()     # 单例检测
  → bootstrap.ensure_admin()         # 管理员检测
  → bootstrap.install_crash_handlers() # 异常钩子
  → QApplication 创建
  → AppCore(app) 创建
  → core.run()
      → _init_db()
      → _bind_events()
      → _hotkey_mgr.register_initial()   # 委托HotkeyManager
      → _show_panel_on_start()
      → _hotkey_health_timer.start()     # 30秒热键心跳
      → app.exec()
```

### 3.2 HotkeyManager — 热键管理

**文件：** `core/hotkey_manager.py`

**职责：** 封装所有热键逻辑，职责单一。

**公开接口：**

| 方法 | 说明 |
|------|------|
| `register_initial()` | 启动时从配置文件加载并注册热键 |
| `on_config_changed(new_hotkeys)` | 用户修改热键后重新注册 |
| `health_check()` → bool | 诊断热键健康状态 |
| `auto_recover()` | 30秒心跳：检测异常自动恢复 |
| `force_reset()` | 紧急重置：用硬编码默认值强制重注册 |
| `clear()` | 注销所有热键（退出时调用） |

### 3.3 ModeHandlers — 功能处理器

**文件：** `core/mode_handlers.py`

**职责：** 四大功能处理为纯函数，避免循环依赖。

**导出函数：**

| 函数 | 功能 |
|------|------|
| `handle_check_status()` | 出入库状态查询 |
| `handle_query_parts()` | 遗物内容查询 |
| `handle_translate()` | 中英翻译 |
| `handle_query_price()` | 价格查询 |
| `render_price_annotations()` | 价格标注渲染 |
| `strip_refinement()` | 去除精炼标签 |

### 3.4 Bootstrap — 启动引导

**文件：** `core/bootstrap.py`

**职责：** 系统级入口逻辑，与业务完全解耦。

**导出函数：**

| 函数 | 说明 |
|------|------|
| `ensure_singleton()` | Windows Mutex 单例检测 |
| `ensure_admin()` | 管理员权限检测 |
| `install_crash_handlers()` | 全局异常钩子 |
| `main()` | 程序主入口 |

### 3.5 Overlay — 全屏覆盖层

**文件：** `core/overlay.py`

**职责：** 全屏透明 QWidget，三种状态。

| 状态 | 鼠标穿透 | 功能 |
|------|----------|------|
| 空闲 | ✓ 穿透 | 仅显示标注文字 |
| 框选 | ✗ 拦截 | RegionSelector 处理拖拽 |
| 标注 | 穿透（按钮不穿透） | 显示结果 + 功能按钮 |

**标注系统：**
- `show_annotations()` — 一次性显示
- `show_annotations_stream()` — 流式逐条动画（可配 interval_ms / batch_size）

### 3.6 RegionSelector — 区域框选器

**文件：** `core/region_selector.py`

**职责：** 独立封装鼠标拖拽交互，可复用。

**复用场景：**
- 默认框选截图（Ctrl+G）
- 物品区域设置（Ctrl+T 价格查询）

**坐标体系：**

```python
region_info = {
    'logical':  (left, top, right, bottom),     # Qt 逻辑坐标
    'physical': (left, top, right, bottom),     # 屏幕物理坐标（dxcam 用）
    'physical_xywh': {'x': int, 'y': int, 'w': int, 'h': int},
    'dpi_scale': float,                         # DPI 缩放比例
}
```

### 3.7 PriceService — 价格服务

**文件：** `core/price_service.py`

**职责：** 三级查询策略，并发限速。

```
query_price(en_name)
  → L1: 内存缓存（最快）
  → L2: wm_prices.db SQLite（较快）
  → L3: warframe.market API（慢，需联网）
      → 解析 JSON → 更新缓存 + 数据库 → 返回价格
```

**限速器：** 令牌桶算法，控制 API 请求频率。

### 3.8 Matcher — 匹配引擎

**文件：** `recognizers/matcher.py`

**职责：** 4 轮降级匹配。

```
match_items(ocr_texts)
  对每个 OCR 文本：
    第1轮: 精确匹配 en_name（大小写不敏感）
    第2轮: 前缀匹配
    第3轮: 包含匹配（纠错候选 variants）
    第4轮: 部件蓝图直通（自动补全 Prime）
```

**精炼过滤：** 过滤遗物精炼版本（Intact/Exceptional/Flawless/Radiant）。

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
          → camera.grab(region)
          → overlay.show_mode_buttons(enabled_modes)
```

### 4.2 功能按钮点击流程

```
用户点击按钮 → overlay.mode_selected.emit(mode)
  → AppCore._on_mode_selected(mode)
    → 检查 OCR 缓存
    → 有缓存 → 直接 _execute_mode(mode)
    → 无缓存 → _start_ocr() → OCRWorker.run() → finished.emit()
      → _execute_mode(mode) → mode_handlers.handle_xxx()
```

### 4.3 价格查询快捷键流程（Ctrl+T）

```
Ctrl+T → AppCore._on_hotkey('query_price')
  → _do_price_query()
    → 加载物品区域配置
    → 计算4等分坐标
    → camera.grab(完整区域) # 一次截图
    → numpy切片分4份
    → 逐份 OCR 识别
    → match_and_price()
    → render_price_annotations()
```

### 4.4 数据流程图

```
┌──────────────────────────────────────────────────────────────┐
│  ⌨️ 热键触发 (keyboard)                                     │
├──────────────────────────────────────────────────────────────┤
│  📷 屏幕截图 (dxcam)                                         │
├──────────────────────────────────────────────────────────────┤
│  🎯 显示功能按钮 (用户点击)                                   │
├──────────────────────────────────────────────────────────────┤
│  🔍 OCR 异步识别 (RapidOCR / QThread)                        │
├──────────────────────────────────────────────────────────────┤
│  📦 出入库 → 🗂️ 遗物内容 → 🔤 翻译 → 💰 价格                 │
├──────────────────────────────────────────────────────────────┤
│  🖥️ 覆盖层输出 (PyQt6 流式动画)                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 五、线程安全

| 机制 | 实现 | 说明 |
|------|------|------|
| OCR 线程 | `QThread` + `finished` 信号 | 超时 2s 强制终止 |
| 价格查询 | `ThreadPoolExecutor` | 最多 4 路并发 |
| 截图竞态 | 防重入 500ms 间隔 | `_screenshot_lock` |
| 退出清理 | `aboutToQuit` → `_shutdown()` | 统一释放资源 |
| 热键心跳 | 30 秒定时器 → `auto_recover()` | 自动恢复失效热键 |

---

## 六、配置系统

### 6.1 数据库

| 数据库 | 路径 | 用途 |
|--------|------|------|
| `items_i18n.db` | `data/` | 全物品中英对照（含拼音搜索） |
| `relics.db` | `data/` | 遗物掉落表 |
| `wm_prices.db` | `data/` | WM 价格缓存 |

### 6.2 配置文件

| 文件 | 路径 | 用途 |
|------|------|------|
| `hotkeys.json` | `data/` | 热键自定义配置 |
| `feature_toggles.json` | `data/` | 功能开关配置 |
| `item_region.json` | `data/` | 物品区域配置 |
| `language_preset.json` | `data/` | 文案预设配置 |
| `config.json` | `%APPDATA%/` | 框选区域持久化 |

### 6.3 文案预设系统

```
language_preset.json → ui_strings.py (路由器)
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
  preset_cyberpunk2077.py  preset_santi.py  preset_normal.py
```

**使用方式：**

```python
from data.ui_strings import S, set_language_preset

# 获取文本
text = S("button", "exit")  # 返回："退出程序"

# 切换预设
set_language_preset("cyberpunk2077")  # 赛博朋克2077（默认）
set_language_preset("santi")          # 三体·威慑纪元
set_language_preset("normal")         # 普通标准
```

### 6.4 主题系统

`ThemeConfig` 单例管理 65+ 个配色字段。

**使用方式：**

```python
from core.constants import theme

theme.cyber_yellow          # 访问属性
theme.apply_preset("daylight")  # 切换预设
theme.save(modified_dict)   # 保存修改
```

---

## 七、UI 实现

### 7.1 主要窗口

**1. Overlay — 全屏覆盖层**

| 状态 | 鼠标穿透 | 功能 |
|------|----------|------|
| 空闲 | ✓ 穿透 | 仅显示标注文字 |
| 框选 | ✗ 拦截 | 鼠标拖拽框选 |
| 标注 | 穿透（按钮不穿透） | 显示结果 + 功能按钮 |

**2. ManagementPanel — 管理面板**

启动即显示，关闭面板 = 退出程序。

| 标签页 | 功能 |
|--------|------|
| 数据库 | 遗物数据库状态/更新/导入 |
| 翻译数据 | items_i18n.db 状态/重建 |
| 价格数据 | WM 价格状态/物品区域设置 |
| 物品检索 | 中/英/拼音实时搜索 + 掉落来源 |
| 快捷键 | 热键捕获/修改/重置 |
| 功能开关 | 截图后显示哪些功能按钮 |
| 主题换肤 | 取色器编辑/预设切换 |
| 文案风格 | 赛博朋克/三体/普通切换 |
| 日志 | 实时运行日志 |

---

## 八、调试与开发

### 8.1 开发模式

```bash
# 热重载模式（修改 .py 自动重启）
python dev_runner.py
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

# 拉取全量价格数据
python data/wm_prices.py --fetch

# 更新遗物掉落数据
python data/update_db.py
```

### 8.5 打包

```bash
# 文件夹模式（推荐，启动快）
python build_exe.py

# 单文件模式（分发方便，启动慢10-15秒）
python build_onefile.py
```

---

## 九、架构设计亮点

### 9.1 v3.4 模块化重构

| 原 main.py | 拆分后 | 行数变化 |
|------------|--------|----------|
| ~1430行 | main.py ~813行 | -43% |
| — | hotkey_manager.py ~213行 | 新增 |
| — | mode_handlers.py ~242行 | 新增 |
| — | bootstrap.py ~200行 | 新增 |

### 9.2 数据库性能优化

- **批量插入优化**：SQLite executemany，提升 5-10 倍速度
- **Schema 版本自动迁移**：旧数据库自动升级
- **拼音完整性自动检查**：启动时自动修复缺失拼音

### 9.3 OCR 优化

- 自适应上采样（根据图像尺寸动态调整）
- CLAHE 对比度增强
- 大图/小图自动选择 OCR 参数
- 垂直相邻行合并（处理跨行文本）

---

## 十、版本历史

### v3.4 (2026-06-02)

| 变更 | 说明 |
|------|------|
| 架构重构 | main.py 1430行 → 813行，新增 3 个模块 |
| 数据库性能 | 批量插入提升 5-10 倍，拼音完整性检查 |
| 框选修复 | 延迟启动保护，防止误取消 |

### v3.3 (2026-06-01)

| 变更 | 说明 |
|------|------|
| 主题优化 | 修复切换预设时部分区域颜色未更新 |
| 图标解耦 | 文案预设与图标完全分离 |

### v3.2 (2026-06-01)

| 变更 | 说明 |
|------|------|
| RegionSelector | 框选逻辑独立封装 |
| 拼音搜索 | items_i18n.db 新增 zh_pinyin 字段 |
| 热键简化 | 移除 panel 热键，改为启动即显示 |