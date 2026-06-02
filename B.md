# WARFRAME-RELIC

Warframe 遗物辅助工具 — 基于 OCR 的实时信息叠加层

---

## 功能介绍

本工具通过 OCR 自动识别屏幕上的遗物名称，并为 Warframe 玩家实时标注以下信息：

| 功能 | 说明 |
|------|------|
| **出入库状态** | 用颜色区分当前遗物是否已入库（红 = 已入库，绿 = 可用） |
| **遗物内容查询** | 显示遗物内含的所有 Prime 配件，按稀有度着色（金/银/铜） |
| **实时价格查询** | 查询 Warframe.Market 上的白金币价格（最低/加权/中位数） |
| **中英互译** | 自动翻译物品名称（中文 ↔ 英文） |
| **跨语种符号学映射** | 混合语言界面下的物品识别与翻译 |
| **流式动画** | 查询结果逐行动画展示 |
| **透明悬浮层** | 非侵入式叠加层，未操作时鼠标可穿透 |
| **一键数据更新** | 通过管理面板从 GitHub 拉取最新掉落数据 |
| **三大语言预设** | 赛博朋克 2077 / 三体·威慑纪元 / 普通 |
| **主题自定义** | 65 种颜色字段可调，实时预览 |
| **拼音搜索** | 管理面板支持中文、英文、拼音模糊搜索 |

---

## 使用方法

### 典型工作流程

1. 进入 Warframe 的遗物选择界面
2. 按 `Ctrl+G`（默认），在屏幕上拖动框选遗物列表区域
3. 松开鼠标 → 功能按钮出现在屏幕顶部
4. 点击按钮执行对应功能：

| 按钮 | 功能 |
|------|------|
| 出入库查询 | 标注哪些遗物已入库 |
| 遗物内容查询 | 显示遗物内含的 Prime 配件（同时弹出悬浮详情窗口） |
| 跨语种符号学映射 | 中英互译（如已启用） |
| 价格查询（手动） | 查询选中区域的物品价格 |

5. 右键点击随时清除所有标注

### 快捷键一览

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+G` | 进入区域选择模式，拖动选择遗物区域后自动截取 |
| `Ctrl+H` | 直接全屏截取（跳过区域选择） |
| `Ctrl+T` | 价格查询（需先在管理面板设置物品区域） |
| 右键 | 清除所有标注 |
| ESC | 取消区域选择 |

> **提示**：所有快捷键可在管理面板中自定义修改，实时生效。

---

## 安装与运行

### 方式一：零配置（推荐）

双击 `SETUP.bat` — 自动安装 Python 及所有依赖项

### 方式二：快速启动

双击 `WARFRAME-RELIC.bat`

### 方式三：手动安装

```bash
cd d:\MyProgram\WARFRAME-RELIC
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 方式四：开发者模式（热重载）

```bash
python dev_runner.py
```

### 方式五：打包 EXE

从 Releases 下载预编译版本，双击运行

---

## 配置说明

### 配置文件

| 文件 | 作用 |
|------|------|
| `data/hotkeys.json` | 用户自定义快捷键 |
| `data/presets/*.json` | 主题预设文件 |
| `data/language_preset.json` | 当前语言预设 |
| `data/feature_toggles.json` | 功能开关 |
| `data/item_region.json` | 价格查询的物品区域 |
| `%APPDATA%/WARFRAME-RELIC/config.json` | 上次选择区域记忆 |

### 数据更新

在 **管理面板** 中点击「自动更新」从 GitHub 拉取最新掉落数据，或手动导入 `all.json`。

---

## 技术栈

| 依赖 | 用途 |
|------|------|
| PyQt6 | GUI 框架（悬浮窗、管理面板） |
| dxcam | 高性能屏幕采集（Windows DXGI） |
| keyboard | 全局快捷键注册 |
| rapidocr-onnxruntime | 离线 OCR 引擎 |
| Pillow / numpy | 图像处理 |
| pypinyin | 中文拼音转换（拼音搜索） |

---

## 系统要求

- Windows 10 / Windows 11
- 以**管理员权限**运行（快捷键功能需要）
- Python 3.10+

---

## 项目结构

```
d:\MyProgram\WARFRAME-RELIC\
  main.py                 # 应用入口，AppCore 核心协调器
  core/
    bootstrap.py          # 单例检查、管理员检查、全局异常钩子
    hotkey_manager.py     # 快捷键注册、健康检查、自动恢复
    mode_handlers.py      # 纯函数：查状态/查内容/翻译/查价格
    overlay.py           # 全屏透明悬浮层（3种状态）
    region_selector.py    # 独立区域选择器（鼠标拖动交互）
    management_panel.py   # 管理面板（物品/数据库/快捷键/主题）
    price_service.py      # 三层价格查询（缓存→SQLite→API）
  recognizers/            # OCR 引擎：遗物名/物品名/MOD 名
  data/
    relics.db             # 遗物数据库
    wm_prices.db          # Warframe.Market 价格缓存
    items_i18n.db         # 物品中英对照
    preset_*.py          # 语言/UI 预设
```

---

## 数据流向

```
快捷键触发
    ↓
屏幕截取 (dxcam)
    ↓
后台线程 OCR 识别
    ↓
根据当前模式执行：
  ├─ 出入库查询  → 颜色标注（红=入库，绿=可用）
  ├─ 遗物内容查询 → 显示配件（按稀有度着色）
  ├─ 翻译        → 中英互译
  └─ 价格查询    → 三层查询 → 标注白金币价格
    ↓
PyQt6 透明窗口叠加输出
```

---

## 许可证

MIT License