# WARFRAME-RELIC v3.4

<p align="center">
  <b>Warframe 遗物实时 OCR 辅助工具 · 赛博朋克2077风格</b>
</p>

<p align="center">
  截取游戏画面 → OCR 识别遗物名称 → 半透明覆盖层标注出入库状态 & Prime 部件 & 实时市价
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/license-GPLv3-blue" alt="License">
  <img src="https://img.shields.io/badge/version-3.4-yellow" alt="Version">
</p>

---

## ✨ 功能

- **🔍 OCR 遗物识别** — 基于 RapidOCR，框选或全屏截图后自动识别所有遗物名称
- **📦 出入库状态** — 颜色标注每个遗物是否可获取（绿色=出库 / 红色=入库）
- **🗂️ 遗物内容查询** — 显示每个遗物包含的 Prime 部件，按稀有度用金银铜色区分 + 悬浮窗详情
- **💰 实时市价查询** — Warframe.Market 实时白金价格（加权参考/最低/中位），并行并发查询
- **🔤 中英翻译** — OCR 识别物品名后自动翻译（中文 ↔ 英文）
- **🖥️ 半透明覆盖层** — 无侵入标注，非框选模式鼠标穿透，不影响游戏操作
- **⌨️ 可配置全局热键** — 管理面板内随时修改快捷键，即时生效无需重启
- **🌐 一键数据更新** — 管理面板内自动从 GitHub 拉取最新掉落数据
- **📝 流式标注动画** — 结果逐条弹出，视觉效果流畅
- **🎨 三套语言预设** — 赛博朋克2077(默认) / 三体·威慑纪元 / 普通标准，管理面板内一键切换
- **🧵 主题可视化换肤** — Cyberpunk 2077 风格配色，管理面板内取色器编辑，实时预览
- **🔎 物品检索** — 管理面板内置中/英/拼音实时搜索，单击复制英文名，悬停查看掉落来源
- **📋 遗物悬浮窗** — 遗物内容查询后弹出可拖动详情窗口，金银铜色区分稀有度
- **⚡ 数据库性能优化** — 批量插入提升5-10倍速度，自动拼音完整性检查与修复
- **🛡️ Schema版本管理** — 自动检测并升级数据库结构，防止迁移失败
- **🧩 模块化架构** — v3.4 重构，热键/功能处理/入口逻辑独立模块，main.py 精简43%

---

## 🎮 使用流程

| 快捷键 | 功能 |
|:------|:---|
| `Ctrl+G`（默认） | 进入框选模式 → 拖拽选中遗物区域 → 松开自动截图识别 |
| `Ctrl+H`（默认） | 直接截取全屏进行识别（跳过框选） |
| `Ctrl+T`（默认） | 价格查询（自动4等分截图+识别+标注，需先在管理面板设置物品区域） |
| 右键 | 清除所有标注和按钮（同时隐藏悬浮窗） |
| ESC | 取消框选 |

**典型使用场景：**

1. 进入 Warframe 遗物选择界面
2. 按 `Ctrl+G`，拖拽框选遗物列表区域
3. 松开鼠标后，屏幕上方出现功能按钮
4. 点击 **「出入库查询」** 查看哪些遗物值得选
5. 点击 **「遗物内容查询」** 查看每个遗物包含的 Prime 部件（同时弹出悬浮窗）
6. 点击 **「价格查询」** 查看 WM 实时白金市价
7. 右键随时清除标注

---

## 🔧 安装与运行

### 系统要求

- Windows 10 / 11
- 网络连接（首次安装依赖时）
- 无需手动安装 Python（SETUP.bat 会自动处理）
- 建议以管理员身份运行（确保全局热键正常工作）

### 方式一：零基础启动（推荐，无需安装任何东西）

1. 克隆本项目
2. 双击 `SETUP.bat`
3. 脚本会自动：检测/安装 Python → 创建虚拟环境 → 安装依赖 → 启动程序

> 以后直接双击 `WARFRAME-RELIC.bat` 即可。

### 方式二：已有 Python 环境

1. 克隆本项目
2. 双击 `WARFRAME-RELIC.bat`
3. 脚本会自动：检查 Python → 创建虚拟环境 → 安装依赖 → 启动程序

### 方式三：手动启动

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 方式四：开发模式（热重载）

```bash
python dev_runner.py
```

修改任意 `.py` 文件后自动重启，方便开发调试。

### 方式五：打包版 EXE

从 [Releases](../../releases) 下载 `WARFRAME-RELIC.exe`，直接运行，无需安装 Python。

---

## 📁 项目结构

```
WARFRAME-RELIC/
├── main.py                     # 程序核心：AppCore + TriggerBridge + OCRWorker
├── core/
│   ├── bootstrap.py            # ★ 启动引导：单例检测、管理员检测、异常钩子、main()
│   ├── hotkey_manager.py       # ★ 热键管理器：注册/健康检查/自动恢复/防重入
│   ├── mode_handlers.py        # ★ 功能处理器：出入库/遗物查询/翻译/价格标注（纯函数）
│   ├── constants.py            # 共享常量
│   ├── overlay.py              # 全屏覆盖层（框选、标注、流式动画、DPI 适配）
│   ├── region_selector.py      # ★ 独立区域框选器（鼠标拖拽交互封装）
│   ├── management_panel.py     # 管理面板（物品检索/数据库/热键/主题/文案）
│   ├── price_service.py        # WM 价格服务（缓存→本地DB→实时API 三级查询）
│   ├── drop_tooltip.py         # ★ 物品掉落来源查询 + Tooltip
│   ├── hotkey_config.py        # 热键配置读写
│   ├── hotkey_capture_button.py # 热键捕获按钮组件
│   ├── stylesheet.py           # 动态 QSS 样式表生成
│   ├── theme_config.py         # 主题配置引擎（65 配色字段，预设切换）
│   ├── theme_panel.py          # 主题可视化编辑面板
│   ├── theme_fields.py         # 主题字段定义
│   ├── theme_proxy.py          # 主题属性代理
│   ├── fetch_worker.py         # 后台线程：从 GitHub 下载最新数据
│   ├── update_worker.py        # 后台线程：执行数据库更新
│   ├── update_panel.py         # 数据库更新面板
│   └── word_wrap_button.py     # 自动换行按钮组件
├── recognizers/
│   ├── relic_name.py           # 遗物名称 OCR 识别器
│   ├── item_name.py            # 物品名称 OCR 识别器
│   ├── matcher.py              # 物品名匹配引擎（4轮降级匹配 + 精炼过滤）
│   └── base_ocr.py             # OCR 管线基类
├── data/
│   ├── preset_cyberpunk2077.py # ★ 赛博朋克2077 风格文案预设（默认）
│   ├── preset_santi.py         # 三体·威慑纪元 风格文案预设
│   ├── preset_normal.py        # 普通标准 风格文案预设
│   ├── ui_strings.py           # UI 字符串路由器（预设加载/切换）
│   ├── items_i18n.py           # ★ 全物品中英对照数据库（含拼音搜索）
│   ├── wm_prices.py            # WM 价格数据库管理（拉取/写入/查询）
│   ├── wfinfo_relics.py        # 遗物数据库查询
│   ├── translation_db.py       # 翻译数据库管理（旧版）
│   ├── db_utils.py             # 数据库工具函数
│   ├── icons.py                # 图标资源管理
│   ├── icon_loader.py          # 图标加载器
│   ├── version.py              # 版本信息
│   ├── items_i18n.db           # 物品中英文对照数据库（含拼音字段）
│   ├── wm_prices.db            # WM 价格本地缓存 SQLite
│   ├── relics.db               # 遗物掉落数据库
│   ├── translation.db          # 翻译缓存（旧版）
│   ├── language_preset.json    # 语言预设配置
│   ├── feature_toggles.json    # 功能开关配置
│   └── item_region.json        # 物品区域配置
├── assets/                     # SVG 图标资源
├── DATABASE.md                 # ★ 数据库结构详细文档
├── DEVELOPMENT.md              # ★ 开发文档
├── build_exe.py                # PyInstaller 打包脚本（文件夹模式）
├── build_onefile.py            # PyInstaller 打包脚本（单文件模式）
├── dev_runner.py               # 开发热重载脚本
├── SETUP.bat                   # 零基础启动（自动安装 Python + 依赖）
├── WARFRAME-RELIC.bat          # 快捷启动批处理
├── DEV_RUN.bat                 # 开发模式启动
├── 打包.bat                    # 打包批处理
├── 打包单文件.bat               # 单文件打包批处理
├── 一键打包.bat                 # 一键打包+压缩批处理
├── git-push.bat                # Git 一键推送
├── qt.conf                     # Qt DPI 感知配置
└── requirements.txt            # Python 依赖
```

### 技术栈

| 依赖 | 用途 |
|:------|:---|
| **PyQt6** | GUI 框架（覆盖层窗口、管理面板） |
| **dxcam** | 高性能屏幕截图（Windows DXGI，带重试） |
| **keyboard** | 全局热键注册 |
| **rapidocr-onnxruntime** | OCR 引擎（离线识别，无需联网） |
| **Pillow** | 图像处理与调试截图保存 |
| **numpy** | 数组运算（截图切片） |
| **pypinyin** | ★ 中文拼音转换（拼音搜索） |

---

## 🏗️ 架构设计

### 数据流

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  热键触发     │ ──→ │  屏幕截图     │ ──→ │  OCR 识别    │
│  keyboard     │     │  dxcam       │     │  RapidOCR    │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  覆盖层标注   │ ←── │  功能选择     │ ←── │  数据查询     │
│  PyQt6       │     │ 出入库/部件/  │     │  SQLite+WM   │
│              │     │ 价格查询/翻译 │     │  API         │
└──────────────┘     └──────────────┘     └──────────────┘
```

- 截图后**立即显示功能按钮**（不等 OCR 完成）
- OCR 在后台 `QThread` 异步执行，完成后通过信号通知主线程
- 用户可在 OCR 完成前点击功能按钮，结果自动延迟执行
- 价格查询采用 **三级策略**：内存缓存 → 本地 SQLite → 实时 WM API（ThreadPoolExecutor 并发，最多4路并行）

### 核心模块（v3.4 重构后）

| 模块 | 职责 |
|:------|:---|
| `AppCore` (main.py) | 中央控制器，协调截图→OCR→查询→标注全流程 |
| `HotkeyManager` (hotkey_manager.py) | ★ 热键管理：注册/更新/健康检查/自动恢复/防重入 |
| `Mode Handlers` (mode_handlers.py) | ★ 四大功能纯函数：出入库/遗物查询/翻译/价格标注 |
| `Bootstrap` (bootstrap.py) | ★ 入口逻辑：单例检测/管理员检测/异常钩子/main() |
| `Overlay` (overlay.py) | 全屏透明覆盖层，三种状态：空闲(穿透)/框选(拦截)/标注(穿透+按钮不穿透) |
| `RegionSelector` | ★ 独立框选模块，封装鼠标拖拽交互，可复用 |
| `ManagementPanel` | 管理窗口：物品检索/数据库/热键/主题换肤/文案预设/日志 |
| `PriceService` | 价格查询服务：缓存→DB→API 三级查询，ThreadPoolExecutor 并发 |
| `Matcher` | 物品名匹配引擎，OCR结果→匹配→价格查询一体化，含精炼过滤 |
| `DropSourceIndex` | ★ 物品掉落来源索引，生成 HTML Tooltip |
| `ThemeConfig` | 主题单例，65 个配色字段，多套预设切换 |
| `UIStrings` | 文案路由器，三套语言预设独立管理，运行时可切换 |

### 线程安全

- **OCR 线程**：`QThread` + `finished` 信号自动清理，带超时强制终止
- **价格查询**：`ThreadPoolExecutor` 并发，结果按 index 归位，线程安全
- **截图竞态**：热键防重入 500ms 间隔
- **退出清理**：`aboutToQuit` 信号触发 `_shutdown()` 统一释放资源
- **热键心跳**：30 秒定时器 → `HotkeyManager.auto_recover()` 自动检测+恢复失效热键

### 文案预设系统

```
language_preset.json ──→ ui_strings.py (路由器)
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
  preset_cyberpunk2077.py  preset_santi.py   preset_normal.py
  (赛博朋克2077·默认)      (三体·威慑纪元)    (普通标准)
```

三套独立文案文件，管理面板内一键切换，即时生效无需重启。

### 数据库结构

详见 [DATABASE.md](DATABASE.md) — 包含完整的表结构、索引、查询 SQL、数据来源和调用链。

---

## 📦 打包

```bash
# 文件夹模式（推荐，启动快）
打包.bat               # 或: python build_exe.py
# 输出: dist/WARFRAME-RELIC/ (整个文件夹)

# 单文件模式（分发方便，启动慢10-15秒）
打包单文件.bat          # 或: python build_onefile.py
# 输出: dist/WARFRAME-RELIC.exe

# 一键打包+压缩
一键打包.bat            # 打包 → 压缩为 WARFRAME-RELIC_v3.4.0.zip
```

---

## 🔄 更新数据库

### 自动更新（推荐）

1. 打开管理面板（启动即显示）
2. 点击 **「自动更新」**
3. 程序自动从 [WFCD/warframe-drop-data](https://github.com/WFCD/warframe-drop-data) 拉取最新数据

### 手动更新

1. 下载最新的 `all.json`
2. 在管理面板中点击 **「选择文件」** 导入

### 命令行更新

```bash
python data/update_db.py
```

---

## ⚙️ 配置

### 热键配置

- **配置文件**：`data/hotkeys.json`（为空则使用默认值）
- **修改方式**：管理面板 → 快捷键设置 → 点击捕获按钮 → 按下组合键 → 保存
- **格式**：`修饰键+普通键`，如 `ctrl+g`、`alt+shift+f`

### 主题换肤

- **配置文件**：`data/presets/*.json`（主题预设文件）
- **修改方式**：管理面板 → 主题换肤 → 点击色块取色 → 实时预览 → 保存
- **预设切换**：赛博朋克2077 / 日光 / 自定义

### 文案预设切换

- **配置文件**：`data/language_preset.json`
- **修改方式**：管理面板 → 语言风格下拉框 → 选择预设即时切换
- **三套预设**：赛博朋克2077(默认) / 三体·威慑纪元 / 普通标准
- 可自行添加 `data/preset_xxx.py` 并注册到 `language_preset.json`

### 物品检索

- 管理面板 → 物品检索标签页
- 支持 **中文 / 英文 / 拼音** 三种输入方式
- 实时联想搜索，单击结果复制英文名
- 悬停查看掉落来源

### 框选区域记忆

- 上次框选的区域坐标自动保存到 `%APPDATA%/WARFRAME-RELIC/config.json`
- 下次启动自动加载

### 调试

- 每次截图自动保存到 `%APPDATA%/WARFRAME-RELIC/debug/last_capture.png`
- 崩溃日志自动记录到 `%APPDATA%/WARFRAME-RELIC/crash_log.txt`

---

## ❓ 常见问题

**Q: 首次启动很慢？**
A: RapidOCR 首次加载 ONNX 模型需要下载（自动缓存在本地），后续启动会很快。

**Q: 需要管理员权限吗？**
A: 键盘钩子（keyboard 库）在部分系统上需要管理员权限才能正常捕获全局热键。如果热键无响应，请尝试以管理员身份运行。

**Q: 数据库如何更新？**
A: 管理面板中点击「自动更新」，程序从 GitHub 拉取最新 WFInfo 数据。也可以手动选择本地 `all_items.json` 导入。

**Q: 价格数据从哪里来？**
A: 从 Warframe.Market API 实时获取。首次查询慢（需联网），之后缓存在 `wm_prices.db` 中。运行 `python data/wm_prices.py --fetch` 可预先拉取全量价格。

**Q: OCR 识别不准怎么办？**
A: 识别器内置了常见 OCR 混淆字符的纠错映射（如 O↔0, I↔1, 5↔S），大部分情况能自动修正。如果截图区域太小，程序会自动放大 1.5 倍处理。

**Q: 覆盖层挡住游戏操作？**
A: 非框选模式下覆盖层会穿透鼠标事件，不影响游戏操作。框选期间覆盖层才拦截鼠标。

**Q: dxcam 截图失败（资源无法使用）？**
A: 通常因为其他程序（OBS、SteamVR 等）占用了 DXGI 输出接口。程序内置最多 5 次重试机制，关闭冲突程序后重试即可。

**Q: 怎么切换文案风格？**
A: 管理面板 → 「语言风格 · 文案预设」下拉框 → 选择赛博朋克2077/三体/普通，即时生效。

**Q: 价格查询热键没反应？**
A: 需要先在管理面板 → 价格数据 → 设置物品区域（框选遗物选择界面中4个物品所在的一整行区域），然后按 `Ctrl+T` 即可自动4等分截图+识别+标注。

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [README.md](README.md) | 用户使用文档（本文） |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发文档（架构、数据流、模块详解） |
| [DATABASE.md](DATABASE.md) | 数据库结构文档（DDL、索引、查询SQL） |

---

## 🔄 更新日志

### v3.4 (2026-06-02)

**架构重构（模块化拆分）：**
- ✅ **HotkeyManager** — 热键管理独立模块：注册/健康检查/自动恢复/防重入（`core/hotkey_manager.py`）
- ✅ **Mode Handlers** — 四大功能处理为纯函数：出入库/遗物查询/翻译/价格标注（`core/mode_handlers.py`）
- ✅ **Bootstrap** — 入口逻辑独立：单例检测/管理员检测/异常钩子/main()（`core/bootstrap.py`）
- ✅ **main.py 精简** — 1430行 → 813行（减少43%），聚焦 AppCore 核心控制逻辑

**数据库性能优化：**
- ✅ **批量插入优化** — 重建数据库速度提升5-10倍（从30-60秒降至5-10秒）
- ✅ **Schema版本管理** — 自动检测并升级数据库结构，防止迁移失败
- ✅ **拼音完整性检查** — 启动时自动检测缺失拼音并修复
- ✅ **命令行工具** — `--check-pinyin` / `--repair-pinyin` 手动检查和修复

**框选交互修复：**
- ✅ **右键清除后首次框选异常修复** — 重置 `_right_was_down` 状态，防止误取消
- ✅ **RegionSelector延迟启动保护** — 等待鼠标状态稳定后再开始检测

**打包配置优化：**
- ✅ **pypinyin依赖声明** — 添加hidden-import确保打包后拼音功能正常
- ✅ **新模块声明** — 添加 `core.bootstrap`、`core.hotkey_manager`、`core.mode_handlers` 到打包配置

### v3.3 (2026-06-01)

详见 [DEVELOPMENT.md](DEVELOPMENT.md#十一v33-更新记录)

### v3.2 (2026-06-01)

详见 [DEVELOPMENT.md](DEVELOPMENT.md#十二v32-更新记录)

---

## 🙏 致谢

- 游戏数据来源：[WFCD/warframe-drop-data](https://github.com/WFCD/warframe-drop-data)
- OCR 引擎：[RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)
- 截图库：[ra1nty/DXcam](https://github.com/ra1nty/DXcam)

---

## 📄 License

GNU General Public License v3.0
