# WARFRAME-RELIC v3.0

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
  <img src="https://img.shields.io/badge/version-3.0-yellow" alt="Version">
</p>

---

## ✨ 功能

- **🔍 OCR 遗物识别** — 基于 RapidOCR，框选或全屏截图后自动识别所有遗物名称
- **📦 出入库状态** — 颜色标注每个遗物是否可获取（绿色=出库 / 红色=入库）
- **🗂️ 遗物内容查询** — 显示每个遗物包含的 Prime 部件，按稀有度用金银铜色区分
- **💰 实时市价查询** — Warframe.Market 实时白金价格（加权参考/最低/中位），并行并发查询
- **🖥️ 半透明覆盖层** — 无侵入标注，非框选模式鼠标穿透，不影响游戏操作
- **⌨️ 可配置全局热键** — 管理面板内随时修改快捷键，即时生效无需重启
- **🌐 一键数据更新** — 管理面板内自动从 GitHub 拉取最新掉落数据
- **📝 流式标注动画** — 结果逐条弹出，视觉效果流畅
- **🎨 三套语言预设** — 赛博朋克2077(默认) / 三体·威慑纪元 / 普通标准，管理面板内一键切换
- **🧵 主题可视化换肤** — Cyberpunk 2077 风格配色，管理面板内取色器编辑，实时预览

---

## 🎮 使用流程

| 快捷键 | 功能 |
|:------|:---|
| `Ctrl+G`（默认） | 进入框选模式 → 拖拽选中遗物区域 → 松开自动截图识别 |
| `Ctrl+H`（默认） | 直接截取全屏进行识别（跳过框选） |
| `Ctrl+Shift+G`（默认） | 打开管理面板（更新数据库 / 修改热键 / 换肤 / 切换文案预设） |
| 右键 | 清除所有标注和按钮 |
| ESC | 取消框选 |

**典型使用场景：**

1. 进入 Warframe 遗物选择界面
2. 按 `Ctrl+G`，拖拽框选遗物列表区域
3. 松开鼠标后，屏幕上方出现功能按钮
4. 点击 **「出入库查询」** 查看哪些遗物值得选
5. 点击 **「遗物内容查询」** 查看每个遗物包含的 Prime 部件
6. 点击 **「价格查询」** 查看 WM 实时白金市价
7. 右键随时清除标注

---

## 🔧 安装与运行

### 系统要求

- Windows 10 / 11
- 网络连接（首次安装依赖时）
- 无需手动安装 Python（SETUP.bat 会自动处理）

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
├── main.py                     # 程序入口（AppCore 类，协调各模块）
├── core/
│   ├── constants.py            # 共享常量
│   ├── overlay.py              # 全屏覆盖层（框选、标注、流式动画、DPI 适配）
│   ├── management_panel.py     # 管理面板（数据库更新、热键配置、主题换肤、文案预设）
│   ├── price_service.py        # WM 价格服务（缓存→本地DB→实时API 三级查询，并发并行）
│   ├── hotkey_config.py        # 热键配置读写
│   ├── hotkey_capture_button.py # 热键捕获按钮组件
│   ├── stylesheet.py           # 动态 QSS 样式表生成
│   ├── theme_config.py         # 主题配置引擎（65 配色字段，预设切换）
│   ├── theme_panel.py          # 主题可视化编辑面板
│   ├── fetch_worker.py         # 后台线程：从 GitHub 下载最新数据
│   ├── update_worker.py        # 后台线程：执行数据库更新
│   └── item_info_panel.py      # 物品详情弹出面板
├── recognizers/
│   ├── relic_name.py           # 遗物名称 OCR 识别器
│   ├── item_name.py            # 物品名称 OCR 识别器
│   ├── matcher.py              # 物品名匹配引擎（匹配+价格查询）
│   └── ...                     # 其他识别器
├── data/
│   ├── preset_cyberpunk2077.py # ★ 赛博朋克2077 风格文案预设（默认）
│   ├── preset_santi.py         # 三体·威慑纪元 风格文案预设
│   ├── preset_normal.py        # 普通标准 风格文案预设
│   ├── ui_strings.py           # UI 字符串路由器（预设加载/切换）
│   ├── language_preset.json    # 语言预设配置
│   ├── wm_prices.py            # WM 价格数据库管理（拉取/写入/查询）
│   ├── wm_prices.db            # WM 价格本地缓存 SQLite
│   ├── items_i18n.db           # 物品中英文对照数据库
│   ├── all_items.json          # WFInfo 全量掉落数据
│   ├── zh_en_dict.json         # 中英文对照词典
│   └── feature_toggles.json    # 功能开关配置
├── build_exe.py                # PyInstaller 打包脚本（文件夹模式）
├── build_onefile.py            # PyInstaller 打包脚本（单文件模式）
├── dev_runner.py               # 开发热重载脚本
├── SETUP.bat                   # 零基础启动（自动安装 Python + 依赖）
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
| **requests** | WM API 价格查询 HTTP 请求 |

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
│              │     │ 价格查询      │     │  API         │
└──────────────┘     └──────────────┘     └──────────────┘
```

- 截图后**立即显示功能按钮**（不等 OCR 完成）
- OCR 在后台 `QThread` 异步执行，完成后通过信号通知主线程
- 用户可在 OCR 完成前点击功能按钮，结果自动延迟执行
- 价格查询采用 **三级策略**：内存缓存 → 本地 SQLite → 实时 WM API（ThreadPoolExecutor 并发，最多4路并行）

### 核心模块

| 模块 | 职责 |
|:------|:---|
| `AppCore` (main.py) | 中央控制器，协调截图→OCR→查询→标注全流程 |
| `Overlay` (overlay.py) | 全屏透明覆盖层，三种状态：空闲(穿透)/框选(拦截)/标注(穿透+按钮不穿透) |
| `ManagementPanel` | 独立管理窗口：数据库/热键/主题换肤/文案预设/日志 |
| `PriceService` | 价格查询服务：缓存→DB→API 三级查询，ThreadPoolExecutor 并发 |
| `Matcher` | 物品名匹配引擎，OCR结果→匹配→价格查询一体化 |
| `ThemeConfig` | 主题单例，65 个配色字段，多套预设切换 |
| `UIStrings` | 文案路由器，三套语言预设独立管理，运行时可切换 |

### 线程安全

- **OCR 线程**：`QThread` + `finished` 信号自动清理，带超时强制终止
- **价格查询**：`ThreadPoolExecutor` 并发，结果按 index 归位，线程安全
- **截图竞态**：`AppCore._screenshot_lock` 防止热键连按时重复截图
- **退出清理**：`aboutToQuit` 信号触发 `_shutdown()` 统一释放资源

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

```sql
-- 遗物主表
relics (id, name, era, code, vaulted)
-- 部件表
relic_parts (id, relic_id, part_name, rarity, chance)
-- 别名表（OCR 模糊匹配用）
relic_aliases (id, relic_id, alias)
-- WM 价格表
wm_prices (en_name, sell_min, sell_median, weighted_avg, ...)
-- 物品中英文对照
items_i18n (item_id, zh_name, en_name, is_tradable, ...)
```

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
一键打包.bat            # 打包 → 压缩为 WARFRAME-RELIC_v3.0.0.zip
```

---

## 🔄 更新数据库

### 自动更新（推荐）

1. 按 `Ctrl+Shift+G` 打开管理面板
2. 点击 **「自动更新」**
3. 程序自动从 [WFCD/warframe-drop-data](https://github.com/WFCD/warframe-drop-data) 拉取最新数据

### 手动更新

1. 下载最新的 `all.json`
2. 在管理面板中点击 **「选择文件」** 导入

### 命令行更新

```bash
python update_db.py
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

### 框选区域记忆

- 上次框选的区域坐标自动保存到 `%APPDATA%/WARFRAME-RELIC/config.json`
- 下次启动自动加载

### 调试

- 每次截图自动保存到 `%APPDATA%/WARFRAME-RELIC/debug/last_capture.png`
- 运行 `python test_4split_ocr.py` 可对上次截图做 OCR 对比测试

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

---

## 🙏 致谢

- 游戏数据来源：[WFCD/warframe-drop-data](https://github.com/WFCD/warframe-drop-data)
- OCR 引擎：[RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)
- 截图库：[ra1nty/DXcam](https://github.com/ra1nty/DXcam)

---

## 📄 License

GNU General Public License v3.0
