# WARFRAME-RELIC

<p align="center">
  <b>Warframe 遗物实时 OCR 辅助工具</b>
</p>

<p align="center">
  截取游戏画面 → OCR 识别遗物名称 → 半透明覆盖层标注出入库状态 & Prime 部件
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/license-GPLv3-blue" alt="License">
</p>

---

## ✨ 功能

- **🔍 OCR 遗物识别** — 基于 RapidOCR，框选或全屏截图后自动识别所有遗物名称
- **📦 出入库状态** — 颜色标注每个遗物是否可获取（绿色=出库 / 红色=入库 / 蓝色=虚空商人）
- **🗂️ 遗物内容查询** — 显示每个遗物包含的 Prime 部件，按稀有度用金银铜色区分
- **🖥️ 半透明覆盖层** — 无侵入标注，不拦截鼠标事件，不影响游戏操作
- **⌨️ 可配置全局热键** — 随时修改快捷键，即时生效无需重启
- **🌐 一键数据更新** — 管理面板内自动从 GitHub 拉取最新掉落数据
- **📝 流式标注动画** — 结果逐条弹出，视觉效果流畅

---

## 🎮 使用流程

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+G`（默认） | 进入框选模式 → 拖拽选中遗物区域 → 松开自动截图识别 |
| `Ctrl+H`（默认） | 直接截取全屏进行识别（跳过框选） |
| `Ctrl+Shift+G`（默认） | 打开管理面板（更新数据库 / 修改热键 / 查看日志） |

**典型使用场景：**

1. 进入 Warframe 遗物选择界面
2. 按 `Ctrl+G`，拖拽框选遗物列表区域
3. 松开鼠标后，屏幕上方出现功能按钮
4. 点击 **「出入库查询」** 查看哪些遗物值得选
5. 点击 **「遗物内容查询」** 查看每个遗物包含的 Prime 部件
6. 右键随时清除标注

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
├── main.py                  # 程序入口（AppCore 类，协调各模块）
├── core/
│   ├── overlay.py           # 全屏覆盖层（框选、标注、流式动画、DPI 适配）
│   ├── management_panel.py  # 管理面板（数据库更新、热键配置、日志）
│   ├── hotkey_config.py     # 热键配置读写
│   ├── fetch_worker.py      # 后台线程：从 GitHub 下载最新数据
│   └── update_worker.py     # 后台线程：执行数据库更新
├── recognizers/
│   └── relic_name.py        # 遗物名称 OCR 识别器（RapidOCR + 正则匹配 + 纠错）
├── data/
│   ├── relics.db            # SQLite 本地数据库（自动生成）
│   ├── all.json             # WFInfo 全量掉落数据
│   ├── wfinfo_relics.py     # 数据库查询接口（四级匹配查找）
│   ├── db_utils.py          # 数据库公共工具（表结构、别名、迁移逻辑）
│   └── migrate_to_sqlite.py # JSON → SQLite 迁移
├── update_db.py             # 数据库更新工具（自动推断出入库状态）
├── build_exe.py             # PyInstaller 打包脚本
├── test_recognizer.py       # OCR 识别器测试脚本
├── dev_runner.py            # 开发热重载脚本
├── SETUP.bat                # 零基础启动（自动安装 Python + 依赖）
├── WARFRAME-RELIC.bat       # 日常启动批处理
├── git-push.bat             # Git 一键推送
├── 打包.bat                 # 一键打包批处理
├── qt.conf                  # Qt DPI 感知配置
└── requirements.txt         # Python 依赖
```

### 技术栈

| 依赖 | 用途 |
|------|------|
| **PyQt6** | GUI 框架（覆盖层窗口、管理面板） |
| **dxcam** | 高性能屏幕截图（Windows DXGI） |
| **keyboard** | 全局热键注册 |
| **rapidocr-onnxruntime** | OCR 引擎（离线识别，无需联网） |
| **opencv-python** | RapidOCR 图像预处理依赖 |
| **Pillow** | 调试截图保存 |

---

## 📦 打包

```bash
# 双击运行
打包.bat

# 或命令行
python build_exe.py
```

打包输出：`dist/WARFRAME-RELIC.exe`（单文件，无需 Python 环境）

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
- **修改方式**：管理面板 → 快捷键设置 → 直接编辑 → 点击保存
- **格式**：`修饰键+普通键`，如 `ctrl+g`、`alt+shift+f`

### 框选区域记忆

- 上次框选的区域坐标自动保存到 `%APPDATA%/WARFRAME-RELIC/config.json`
- 下次启动自动加载

### 调试

- 每次截图自动保存到 `%APPDATA%/WARFRAME-RELIC/debug/last_capture.png`
- 运行 `python test_recognizer.py` 可对上次截图做 OCR 对比测试

---

## ❓ 常见问题

**Q: 首次启动很慢？**
A: RapidOCR 首次加载 ONNX 模型需要下载（自动缓存在本地），后续启动会很快。

**Q: 需要管理员权限吗？**
A: 键盘钩子（keyboard 库）在部分系统上需要管理员权限才能正常捕获全局热键。如果热键无响应，请尝试以管理员身份运行。

**Q: 数据库如何更新？**
A: 管理面板中点击「自动更新」，程序从 GitHub 拉取最新 WFInfo 数据。也可以手动选择本地 `all.json` 导入。

**Q: OCR 识别不准怎么办？**
A: 识别器内置了常见 OCR 混淆字符的纠错映射（如 O↔0, I↔1, 5↔S），大部分情况能自动修正。如果截图区域太小，程序会自动放大 1.5 倍处理。

**Q: 覆盖层挡住游戏操作？**
A: 非框选模式下覆盖层会穿透鼠标事件，不影响游戏操作。框选期间覆盖层才拦截鼠标。

---

## 🏗️ 工作原理

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  热键触发     │ ──→ │  屏幕截图     │ ──→ │  OCR 识别    │
│  keyboard     │     │  dxcam       │     │  RapidOCR    │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  覆盖层标注   │ ←── │  功能选择     │ ←── │  数据库查询   │
│  PyQt6       │     │  出入库/部件  │     │  SQLite      │
└──────────────┘     └──────────────┘     └──────────────┘
```

- 截图后**立即显示功能按钮**（不等 OCR 完成）
- OCR 在后台线程异步执行，完成后自动更新结果
- 四级匹配查找（别名 → 精确 → 模糊 → 纠错），最大限度容错

---

## 🙏 致谢

- 游戏数据来源：[WFCD/warframe-drop-data](https://github.com/WFCD/warframe-drop-data)
- OCR 引擎：[RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)
- 截图库：[ra1nty/DXcam](https://github.com/ra1nty/DXcam)

---

## 📄 License

GNU General Public License v3.0
