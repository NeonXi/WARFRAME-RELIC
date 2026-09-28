# WARFRAME-RELIC UI 框架设计方案 (Design System Specification)

> 版本: 2.0 | 更新: 2026-09-29
> 目标: 基于科幻切角（Chamfered）风格，从零构建可维护、可扩展的 UI 框架
>
> **阅读指引**：
> - 想理解**设计理念与 Token 分层** → 阅读全文（§1 起）
> - 想理解**当前代码里主题如何加载/切换/刷新** → 直接看
>   [§1.6 当前主题运行时架构（权威实现说明）](#16-当前主题运行时架构权威实现说明)
> - 想**动手改一个颜色** → 看
>   [§1.7 改色实战手册](#17-改色实战手册)，预设文件头部也有「改色速查索引」
> - 文档矛盾时以 `.trae/rules/开发规范.md` 为准，其次本文档

---

## 目录

1. [设计原则](#1-设计原则)
   - **1.6 [当前主题运行时架构（权威实现说明）](#16-当前主题运行时架构权威实现说明)** ← 主题加载/切换/刷新
   - **1.7 [改色实战手册](#17-改色实战手册)** ← 动手改颜色先看这里
2. [颜色系统 — Design Token 架构](#2-颜色系统--design-token-架构)
3. [空间与尺寸系统 — Design Space](#3-空间与尺寸系统--design-space)
4. [模块深度层级 — UI 架构分层](#4-模块深度层级--ui-架构分层)
5. [组件架构 — Cyber Widget 框架](#5-组件架构--cyber-widget-框架)
6. [文件结构规划](#6-文件结构规划)
7. [迁移策略](#7-迁移策略)
8. [状态管理与数据流](#8-状态管理与数据流)
9. [工程规范 — 文档体系与开发流程](#9-工程规范--文档体系与开发流程)
- 附录 A: [颜色函数规范](#附录-a颜色函数规范)
- 附录 B: [切角几何参数参考](#附录-b切角几何参数参考)
- 附录 C: [专业设计审查 — 补充设计维度](#附录-c专业设计审查--补充设计维度)
  - C.1 [交互状态完整机](#c1交互状态完整机interaction-state-machine)
  - C.2 [动效系统](#c2动效系统motion-system)
  - C.3 [可访问性](#c3可访问性accessibility)
  - C.4 [图标系统](#c4图标系统icon-system)
  - C.5 [暗/亮模式策略](#c5暗亮模式策略darklight-mode-strategy)
  - C.6 [响应式与窗口策略](#c6响应式与窗口策略responsive--window)
  - C.7 [文案与微复制](#c7文案与微复制microcopy)
  - C.8 [性能预算](#c8性能预算performance-budget)
  - C.9 [国际化布局考量](#c9国际化布局考量i18n-layout)
  - C.10 [设计走查清单](#c10设计走查清单design-review-checklist)
- 附录 E: [设计决策记录 (ADR)](#附录-e设计决策记录adr)

---

## 1. 设计原则

### 1.1 Token 驱动（Token-Driven）

所有视觉属性来源于 **Design Token**，不允许在任何业务代码中硬编码颜色值。

```
❌ painter.setPen(QColor("#00FFFF"))          // 硬编码
✅ painter.setPen(tokens.color("primary"))     // 取自 token
```

### 1.1.1 文案 Token 驱动（Copy Token-Driven）

**所有面向用户的文字字符串必须从 YAML 配置文件中的 `copy` 区段引用，严禁在代码中硬编码任何用户可见的中文/英文字符串。**

```
❌ QLabel("物品检索")                              // 硬编码
❌ CyberButton(text="保存", variant="solid")        // 硬编码
✅ QLabel(self._copy("items.title", "物品检索"))    // 从 copy token 取值
✅ CyberButton(text=self._copy("common.save", "保存"), variant="solid")
```

**规则：**
1. 所有页面标题、按钮文字、标签、提示文案、日志消息、错误信息等，必须使用 `_copy()` (PageBase) 或 `self.copy()` (CyberWidgetMixin) 获取
2. copy token 定义在 `data/presets/cyberpunk.yaml` 的 `copy` 区段下，按页面/模块分组
3. 支持模板变量替换：`self._copy("status.update_complete", "更新完成! 耗时: {elapsed}s", elapsed=5)`
4. `_copy(key, default, **kwargs)` 的 `default` 参数作为安全兜底，确保 token 缺失时 UI 仍可正常显示
5. 新增文案时必须先在 YAML 中添加对应 token，再在代码中引用

### 1.2 语义分层（Semantic Layering）

颜色定义分四层，上层自动由下层派生：

```
┌─────────────────────────────────┐
│  Layer 4: Component Tokens      │  ← 按钮背景、面板边框、卡片填充...
│    (组件专用，不可被其他层引用)    │
├─────────────────────────────────┤
│  Layer 3: Semantic Tokens       │  ← primary, success, danger, warning...
│    (全局语义，可跨组件复用)        │
├─────────────────────────────────┤
│  Layer 2: Alias / Palette       │  ← accent, neutral, surface...
│    (调色板别名，组织原始色值)      │
├─────────────────────────────────┤
│  Layer 1: Raw Values            │  ← #FFE600, #00FFFF, #08081A...
│    (原子色值，仅本层使用)         │
└─────────────────────────────────┘
```

**核心规则：Layer N 只能引用 Layer N-1 及以下的 token。**

### 1.3 继承原生控件 + 最小化自绘（不重复造轮子）

**核心原则**: 继承 Qt 原生控件，只通过 `paintEvent` 覆盖 QSS 做不到的视觉部分。Qt 已有的能力（文字渲染、光标、选中、撤销重做、复制粘贴、Tab 导航、焦点管理）全部由父类提供，绝不自己重写。

每个控件类只负责：
1. 继承最接近的原生控件（QPushButton / QLineEdit / QFrame / ...）
2. 在 `paintEvent` 中先画 QSS 做不到的部分（切角背景/外发光/角落装饰）
3. 调用 `super().paintEvent()` 或 `style().drawControl()` 让 Qt 接管剩余绘制
4. 从 Token 读取颜色和尺寸

**Qt 原生能力（直接继承，不自绘）**:

| 能力 | 来源控件 | 说明 |
|------|---------|------|
| 文字渲染（光标/选中/省略号/对齐） | QLabel, QPushButton, QLineEdit | Qt 的文本引擎远超自绘 |
| 输入编辑（键盘/撤销/复制粘贴/右键菜单） | QLineEdit, QTextEdit | 自行实现需要数百行代码 |
| 鼠标事件分发 / 焦点管理 / Tab 导航 | 所有 QWidget | 框架级能力 |
| 布局计算 / 尺寸策略 / 自适应 | QLayout 系列 | 成熟的布局系统 |
| 滚动区域 / 视口管理 | QScrollArea | 含惯性滚动、步进控制 |
| 动画引擎 | QPropertyAnimation | 与属性系统深度集成 |
| 禁用态 / 只读态 / 工具提示 | 所有 QWidget | 自动处理 |

**才需要 QPainter 自绘的部分**:

| 效果 | 为什么 QSS 做不到 |
|------|------------------|
| 切角矩形背景 (chamfered corner) | `border-radius` 只能做圆角 |
| 霓虹外发光 (outer glow) | `box-shadow` 不支持霓虹色扩散 |
| 角落装饰线 (corner marks) | 完全自定义图形 |
| 背景纹理（扫描线/网格） | QSS 无图案填充 API |
| 玻璃模糊效果 | 需要图像处理管线 |

不做：
- 不从零继承 QWidget 然后自己画所有东西
- 不重新实现光标、选中、撤销等已有能力
- 不持有全局样式表逻辑
- 不操作其他控件的样式
- 不直接读写 JSON

### 1.4 模块化与可替换性

每个层级（Token / Widget / Section / Page）都是独立可替换单元。
修改某一层的实现不影响其他层，前提是接口（信号/方法签名）不变。

> 迁移执行计划见 `docs/ui-refactor-analysis.md`。

---


## 1.5 Qt 框架选型：新旧版本差异

> **决策记录 (ADR)**: 新版本 UI 统一使用 **PySide6**，旧代码使用 PyQt6。

### 背景

项目存在两套 UI 代码：

| 版本 | Qt 框架 | 文件范围 | 状态 |
|------|---------|---------|------|
| **旧版（运行中）** | **PyQt6** | main.py, management_panel.py, overlay.py, panel_builder.py 等 ~12 个文件 | 正常运行 |
| **新版（重构中）** | **PySide6** | core/app_shell.py, core/pages/*, core/widgets/base.py, core/state/*, run_new_ui.py 等 | 开发中 |

### 规则

1. **所有新编写的文件必须使用 PySide6**
2. **从旧版迁移过来的代码片段必须将 PyQt6 改为 PySide6**
3. 迁移对照表：

| PyQt6 (旧) | PySide6 (新) |
|-----------|-------------|
| `from PyQt6.QtWidgets import ...` | `from PySide6.QtWidgets import ...` |
| `from PyQt6.QtCore import ...` | `from PySide6.QtCore import ...` |
| `from PyQt6.QtGui import ...` | `from PySide6.QtGui import ...` |
| `pyqtSignal(...)` | `Signal(...)` |
| `pyqtSlot(...)` | `Slot(...)` |
| `pyqtProperty(...)` | `Property(...)` |

4. 旧版文件（main.py / management_panel.py 等）暂不改动，等 Phase 2 逐个页面重构时统一迁移
5. requirements.txt 中同时保留两个依赖直到迁移完成

### 原因

- PySide6 是 LGPL 协议，对商业/分发更友好
- 项目设计文档（ui-framework-design.md）从一开始就规划用 PySide6
- 旧代码用 PyQt6 是历史遗留问题

---

## 1.6 当前主题运行时架构（权威实现说明）

> 本节描述**当前代码中的真实实现**（2026-09 落地），是主题加载、切换、刷新的权威说明。
> 与下方 §2 起的"设计理念"章节冲突时，以本节和源码为准。

### 1.6.1 核心组件与文件清单

| 文件 | 层 | 职责 |
|---|---|---|
| [core/theme_manager.py](file:///d:/MyProgram/WARFRAME-RELIC/core/theme_manager.py) | L1 桥接（QObject 单例） | **唯一主题切换入口**；加载预设、持久化、发射 `theme_changed` |
| [core/tokens/manager.py](file:///d:/MyProgram/WARFRAME-RELIC/core/tokens/manager.py) | L-Infrastructure | `TokenManager` 单例；`load_preset()` 读 YAML、`get()/get_qcolor()` 取 token |
| [core/tokens/resolver.py](file:///d:/MyProgram/WARFRAME-RELIC/core/tokens/resolver.py) | L-Infrastructure | `TokenResolver`；递归解析 `@引用` 与颜色函数，结果缓存 |
| [core/tokens/color_utils.py](file:///d:/MyProgram/WARFRAME-RELIC/core/tokens/color_utils.py) | L-Infrastructure | 颜色解析/转换：hex/rgba、`lighten/darken/opacity/mix` |
| [data/presets/cyberpunk.yaml](file:///d:/MyProgram/WARFRAME-RELIC/data/presets/cyberpunk.yaml) | 预设 | 赛博朋克全部颜色/尺寸/文案 |
| [data/presets/glassmorphism.yaml](file:///d:/MyProgram/WARFRAME-RELIC/data/presets/glassmorphism.yaml) | 预设 | 玻璃拟态全部颜色/尺寸/文案 |
| [core/app_shell.py](file:///d:/MyProgram/WARFRAME-RELIC/core/app_shell.py) | L0 外壳 | 订阅 `theme_changed`，驱动整窗刷新与切换渐隐动画 |
| [core/pages/base_page.py](file:///d:/MyProgram/WARFRAME-RELIC/core/pages/base_page.py) | L2 基类 | `_style()` 登记 QSS 配方，`on_theme_change()` 重放 |
| [core/widgets/base.py](file:///d:/MyProgram/WARFRAME-RELIC/core/widgets/base.py) | L4/L5 基类 | `CyberWidgetMixin`：取色、沉浸解析、主题订阅钩子 |
| [core/widgets/immersive.py](file:///d:/MyProgram/WARFRAME-RELIC/core/widgets/immersive.py) | L4 纯函数 | 沉浸底色覆写/alpha 折减的唯一实现 |
| [core/immersive_controller.py](file:///d:/MyProgram/WARFRAME-RELIC/core/immersive_controller.py) | L1 桥接 | 沉浸开关/强度/底色的编排与广播 |
| [core/services/ui_prefs.py](file:///d:/MyProgram/WARFRAME-RELIC/core/services/ui_prefs.py) | L-Service | 持久化用户偏好（含 `theme_preset` 键） |
| [core/widgets/fade_overlay.py](file:///d:/MyProgram/WARFRAME-RELIC/core/widgets/fade_overlay.py) | L4 | 主题切换时整窗交叉溶解遮罩 |

### 1.6.2 启动流程

```
AppShell.__init__
  └─ _setup_window()
       └─ ThemeManager.instance().apply_on_startup()
            ├─ 从 ui_prefs.json 读 "theme_preset"（core/services/ui_prefs.py）
            ├─ TokenManager.instance().load_preset(保存的预设名)
            │     └─ 读 data/presets/<name>.yaml → 新建 TokenResolver
            └─ 读取失败/文件缺失 → 回退 "cyberpunk"
```

- 启动时**不发射** `theme_changed`（界面首次构建本就用当前 token，无需重放）。
- `TokenResolver` 只持有当前预设数据，**无跨预设 fallback**，缓存随预设切换清空。

### 1.6.3 运行时切换流程（唯一入口）

```
ThemePage._on_preset_clicked(name)
  └─ ThemeManager.instance().switch_preset(name)
       ├─ TokenManager.load_preset(name)           # 换整包 token
       ├─ ui_prefs 持久化新预设名                   # 下次启动自动恢复
       └─ emit theme_changed(name)                 # 全局广播
            ├─ AppShell._on_theme_changed
            │     ├─ grab() 旧界面截图 → FadeOverlay 盖满窗口
            │     ├─ refresh_theme()               # 驱动 §1.6.4 三类刷新
            │     └─ FadeOverlay 260ms 渐隐         # 新主题溶入
            └─ 所有订阅方（widgets/dialog/panel）各自刷新
```

**铁律**：除 `ThemeManager` 外，任何模块**禁止**自行调
`TokenManager.load_preset()` + `save_theme_preset()` 组合。启动走
`apply_on_startup()`，切换走 `switch_preset()`。

切换动画时长由 `app_shell.py` 的 `_THEME_FADE_MS` 控制（默认 260ms）。
连点切换时，新一场会先取消上一场，全程最多一个遮罩；并有兜底定时器防止动画被刷新风暴"饿死"。

### 1.6.4 控件响应主题的三类策略

切换预设后，不同控件通过不同机制拿到新颜色：

| 类别 | 机制 | 代表 |
|---|---|---|
| **A. 自绘控件** | `paintEvent` 每次绘制时实时读 token，重绘即变色，天然响应 | button、card、panel、toggle 等所有 `CyberWidgetMixin` 子类的自绘部分 |
| **B. 页面层 QSS 配方** | `PageBase._style()` 把样式配方存到 `widget._cyber_style_props`；`on_theme_change()` 用当前 token **重放**配方。`raw=` 传 callable（lambda），重放时重新求值 | 复选框、滑块、进度条、提示框、列表等 QSS |
| **C. widgets 内联 QSS** | 订阅 `theme_changed`，重写 `cyber_refresh_style()` 重建 QSS/palette | card、line_edit、combo_box、pixel_font_editor、manual_update_dialog、proxy_dialog、log_viewer |

**`CyberWidgetMixin` 提供的统一钩子**（见 [base.py](file:///d:/MyProgram/WARFRAME-RELIC/core/widgets/base.py)）：

```python
_cyber_subscribe_theme()
    # 子类 __init__ 末尾调用：订阅 ThemeManager.theme_changed

cyber_refresh_style()
    # Mixin 上的空实现；子类按需重写以重建 QSS/palette（C 类）
```

另有一个**可选方法**（不在 Mixin 上，由需要的控件各自定义）：

```python
cyber_refresh_immersive_style()
    # 沉浸开关/强度/底色变化时，ImmersiveStyleController 用 hasattr 检测后调用。
    # 已实现：pixel_font_editor、combo_box、log_viewer、
    # cd_assist_page、triggers_page
```

### 1.6.5 沉浸底色系统（Immersive）

"沉浸"指让控件表面色随壁纸/底色风格化，包含三个可配置项（`immersive_controller.py`）：

| 配置 | 含义 |
|---|---|
| 沉浸开关 | 开启后控件底色参与覆写 |
| 沉浸强度（0-100） | 折减表面 alpha：强度越大，表面越透、越能露出壁纸 |
| 沉浸底色：**主题色 / 纯黑** | 二选一，覆写表面 RGB |

底色 token：

| 预设 | 主题色基准 | 纯黑覆写色（`surface.overlay`） |
|---|---|---|
| cyberpunk | `surface.base` 深紫黑 | `#000000` 纯黑 |
| glassmorphism | `surface.base` `#0D47A1` 深蓝 | `#0A1428` 近黑深蓝 |

**覆写原则**：`immersive.override_rgb()` **只改 RGB 不改 alpha**；
alpha 折减统一在玻璃绘制路径（`_draw_glass_bg`）和沉浸解析路径处理。
禁止在业务代码里手写"覆写 RGB + 折减 alpha"逻辑（开发规范自查卡第 13 条）。

玻璃拟态下，`_draw_glass_bg()` 内部统一执行 RGB 覆写 + 强度折减，
通过 `override_bg` 参数区分：

| `override_bg` | 适用 | 行为 |
|---|---|---|
| `True`（默认） | 容器表面（卡片/输入框/开关关闭态等） | RGB 随沉浸底色切换 |
| `False` | 强调色（按钮、开关开启态） | 保持品牌强调色，不被染黑 |

### 1.6.6 预设独立性与真实颜色数量

两套预设是**两个完全独立的 YAML 文件**，互不引用、无共享兜底：

- `load_preset()` 只加载当前文件；`resolver` 只在当前数据中查找
- 改一个预设的任何颜色，另一个预设不受影响

**关于"100 多个颜色"的澄清**（以 cyberpunk 为例实测）：

| 统计项 | 数量 |
|---|---|
| YAML 叶子 token 总数（含 space/copy） | 581 |
| 颜色相关 token | 172 |
| └ 纯引用别名 `@xxx` | 93 |
| └ 混在颜色层的数字（corner_size 等） | 27 |
| **└ 解析引用后的物理独立颜色值** | **27** |

即真正能看到的颜色只有 **27 个**（glass 为 44，其中大量是同色相透明度变体）。
其余 100 多个是语义"角色名"——这正是 Token 架构价值：
改一个 `raw.brand.yellow`，所有引用处自动跟随；而每个
`components.*` 又是独立入口，可单独调整某控件而不动全局。

### 1.6.7 已知"死 token"（改了无效）

glassmorphism 的 `components.slider.* / checkbox.* / radio.* / scrollbar.*`
（31 个子键）**没有任何代码消费**：

| 死分组 | 实际生效的颜色来源 |
|---|---|
| `components.slider.*` | `components.progress.track_bg` + `accent.*`（theme_page.py 滑块 QSS） |
| `components.checkbox.*` | `border.emphasis` / `accent.secondary`（toggles_page.py、theme_page.py） |
| `components.radio.*` | `border.*` / `accent.*` |
| `components.scrollbar.*` | app_shell.py / log_viewer.py / proxy_dialog.py 各自构建，取短 token |

这些分组在 YAML 中已用 `⚠ 死 token` 注释块标记。保留仅为未来自定义预留；
**改这些值不会产生任何界面变化**。cyberpunk 从未定义它们，功能完全正常。

---

## 1.7 改色实战手册

> 改色总原则：**先判断"想改多大范围"，再决定改哪一层。**

### 场景 1：想全局换一个色相（如品牌黄整体偏橙）

1. 打开对应预设 `data/presets/<preset>.yaml`
2. 改 `raw.brand.yellow` 的值
3. 所有引用 `alias.accent.primary` → `components.*` 的地方自动跟随
4. 无需改代码；重启或在主题页切换一次即可看到效果

### 场景 2：只想让某一种控件变色（如只改按钮、不改标题）

1. 在 YAML 中定位 `components.<控件>.*`（文件头「改色速查索引」可查）
2. 直接改该 token 值（不再是 `@引用`，而是写死的新颜色）
3. 只影响该控件，其它引用上游 token 的元素不变

### 场景 3：玻璃风想统一调整所有控件表面的透明度

1. 改 `alias.surface_fill.*` 对应档位（8 档已在注释中标明用途）
2. 所有引用该档的控件自动跟随
3. 注意：`components.card.bg` 目前是独立字面量，不在 surface_fill 内，需单独改

### 场景 4：调整沉浸模式默认底色

| 诉求 | 修改点 |
|---|---|
| 改"主题色"底色 | `raw.surface.base` |
| 改"纯黑"底色 | `raw.surface.overlay`（glass 现为 `#0A1428`） |

### 场景 5：改后没生效？排查顺序

```
1. 改的是不是 §1.6.7 的死 token？（slider/checkbox/radio/scrollbar 分组）
2. 是自绘控件 → 确认该控件 paintEvent 是否真的读了这个 token
3. 是 QSS 控件 → 确认走的是 _style(raw=callable)，切换主题时才会重放
4. 改完当前主题没触发重绘 → 切换一次预设或重启
5. 确认改的是"当前使用的预设"文件（主题页可查当前预设名）
```

### 颜色格式注意

| 格式 | 说明 |
|---|---|
| `#RRGGBB` | 标准 6 位 hex |
| `#AARRGGBB` | `rgba()` 字面量经归一化后的 8 位格式（**alpha 在前**），QColor/QSS 通用 |
| `#RRGGBBAA` | `opacity()` 函数返回格式（**alpha 在后**），与上者字节序相反，勿混用 |
| `rgba(r,g,b,a)` | 预设内书写半透明色推荐格式，解析器自动归一化 |

---



## 2. 颜色系统 — Design Token 架构

> 以下 §2 起为**设计理念层**的完整阐述（历史版本内容）；
> 当前真实运行架构以 [§1.6](#16-当前主题运行时架构权威实现说明) 为准。

### 2.1 四层 Token 模型详解

#### Layer 1: Raw Values（原始色值）

最底层的物理颜色，对应预设文件中的实际值。

```yaml
# data/presets/cyberpunk.yaml (新版格式)
raw:
  # ---- 品牌主色（6 色，来自 Warframe 配色体系）----
  brand:
    yellow:  "#FFE600"    # 主强调色（标题、主要操作）
    cyan:    "#00FFFF"    # 信息、链接、次要操作
    magenta:"#FF0099"    # 特殊标记
    orange:  "#FF7700"    # 警告、提示
    red:     "#FF0055"    # 错误、危险操作
    green:   "#00FF99"    # 成功、可用状态

  # ---- 中性色阶梯（用于文字、边框、背景）----
  neutral:
    white:   "#E8ECFF"    # 主文字
    light:   "#99AACC"    # 次要文字
    medium:  "#6677AA"    # 辅助文字 / 占位符
    dark:    "#334477"    # 禁用文字 / 弱边框
    black:   "#111122"    # 最深背景

  # ---- 表面色（Surface Colors）----
  surface:
    base:    "#08081A"    # 最底层背景（窗口/面板基底）
    raised:  "#0E0E24"    # 浮起面（卡片/弹窗）
    overlay: "#000000"    # 遮罩层（半透明使用）

  # ---- 业务语义色（游戏相关）----
  game:
    gold:    "#FFD700"    # 遗物黄金稀有度
    silver:  "#00FFFF"    # 遗物白银稀有度
    copper:  "#FF7700"    # 遗物青铜稀有度
    unknown: "#556688"    # 未知状态

  # ---- 外部品牌色 ----
  external:
    bilibili:    "#FB7299"
    bilibili_hover: "#FF8DB0"
    github:      "#58A6FF"
    github_hover: "#79C0FF"
```

#### Layer 2: Alias / Palette（调色板别名）

对 Raw 的语义化分组，方便 Layer 3 引用。

```yaml
alias:
  # 强调色系（用于需要吸引注意力的元素）
  accent:
    primary:   "@brand.yellow"     # 主强调
    secondary: "@brand.cyan"       # 次强调
    tertiary:  "@brand.magenta"    # 第三强调

  # 语义色（带明确含义）
  semantic:
    success:   "@brand.green"
    danger:    "@brand.red"
    warning:   "@brand.orange"
    info:      "@brand.cyan"

  # 中性色梯度（文字与边框）
  text:
    primary:   "@neutral.white"
    secondary: "@neutral.light"
    tertiary:  "@neutral.medium"
    disabled:  "@neutral.dark"
    inverse:   "@neutral.black"    # 深色背景上的反白文字

  border:
    subtle:    "@neutral.dark"     # 弱分隔线
    default:   "@neutral.medium"   # 普通边框
    emphasis:  "@alias.accent.primary"  # 强调边框
    focus:     "@alias.accent.secondary" # 聚焦边框

  # 背景色
  bg:
    base:      "@surface.base"
    raised:    "@surface.raised"
    overlay:   "@surface.overlay"

  # 渐变色（多色组合）
  gradient:
    progress:  ["@brand.yellow", "@brand.red", "@brand.cyan"]
```

#### Layer 3: Semantic Tokens（全局语义令牌）

面向全应用的全局语义角色，任何组件都可以引用。

```yaml
semantic:
  # ---- 全局交互状态 ----
  state:
    normal:
      bg:      "@bg.raised"
      text:    "@text.primary"
      border:  "@border.default"
    hover:
      bg:      "lighten(@bg.raised, 10%)"
      text:    "@accent.secondary"
      border:  "@accent.primary"
    pressed:
      bg:      "darken(@bg.base, 5%)"
      text:    "@accent.primary"
      border:  "@accent.secondary"
    focused:
      border:  "@border.focus"
      glow:    "@accent.secondary"        # 聚焦发光色
    disabled:
      bg:      "opacity(@bg.raised, 50%)"
      text:    "@text.disabled"
      border:  "opacity(@border.subtle, 50%)"
    selected:
      bg:      "@accent.primary"
      text:    "@bg.base"                  # 反色文字
      border:  "@accent.primary"

  # ---- 重要性等级 ----
  priority:
    high:     "@semantic.danger"
    medium:   "@semantic.warning"
    low:      "@semantic.info"
    muted:    "@text.tertiary"
```

#### Layer 4: Component Tokens（组件专用令牌）

每个组件类型独享的颜色槽位，**仅限该组件内部使用**。

```yaml
components:
  # ---- 按钮 (CyberButton) ----
  button:
    # 实心按钮（Primary Action）
    solid:
      fill:         "@accent.primary"
      text:         "@bg.base"
      border:       "@accent.primary"
      corner_size:  8                # 切角像素大小（非颜色，但归组件 token 管）
      glow_size:    6                # 外发光扩散半径
      glow_opacity: 0.4
    # 描边按钮（Secondary Action）
    outlined:
      fill:         "transparent"
      text:         "@accent.secondary"
      border:       "@accent.secondary"
      corner_size:  8
      glow_size:    4
      glow_opacity: 0.25
    # 幽灵按钮（Tertiary Action）
    ghost:
      fill:         "transparent"
      text:         "@text.secondary"
      border:       "@border.subtle"
      corner_size:  8
      glow_size:    0
    # 各状态覆盖（可选，不写则继承 semantic.state）
    solid_hover:
      fill:         "@accent.secondary"
      text:         "@bg.base"
      border:       "@accent.secondary"

  # ---- 面板容器 (CyberPanel) ----
  panel:
    bg:            "@bg.raised"
    bg_opacity:    0.92
    border:        "@border.subtle"
    border_width:  1
    corner_size:   12
    glow_color:    "@accent.secondary"
    glow_opacity:  0.08
    # 内部标题栏
    title_bar:
      bg:          "transparent"
      text:        "@accent.primary"
      underline:   "@accent.primary"
      icon_color:  "@accent.primary"
    # 角落装饰
    corner_decor:
      color:       "@accent.primary"
      length:      12
      thickness:   2

  # ---- 卡片 (CyberCard) ----
  card:
    bg:            "lighten(@bg.raised, 3%)"
    border:        "@border.default"
    border_width:  1
    corner_size:   8
    padding_h:     16
    padding_v:     12

  # ---- 对话框 (CyberDialog) ----
  dialog:
    bg:            "@bg.raised"
    bg_opacity:    0.96
    border:        "@accent.secondary"
    border_width:  1.5
    corner_size:   14
    shadow_blur:   30
    shadow_opacity: 0.4
    title_text:    "@text.primary"
    body_text:     "@text.secondary"
    close_btn:     "@components.button.outlined"

  # ---- 输入框 (CyberLineEdit) ----
  input:
    bg:            "darken(@bg.raised, 2%)"
    text:          "@accent.secondary"
    placeholder:   "@text.tertiary"
    border:        "@border.subtle"
    border_focus:  "@accent.primary"
    corner_size:   6

  # ---- 进度条 (CyberProgressBar) ----
  progress:
    track_bg:      "darken(@bg.base, 5%)"
    track_border:  "@border.subtle"
    fill_gradient: "@alias.gradient.progress"
    corner_size:   4
    text:          "@text.primary"

  # ---- 列表项 (CyberListItem) ----
  list_item:
    bg_normal:     "transparent"
    bg_hover:      "opacity(@accent.secondary, 8%)"
    bg_selected:   "@accent.primary"
    text_normal:   "@text.primary"
    text_selected: "@bg.base"
    border:        "@border.subtle"
    corner_size:   6

  # ---- 标签/徽章 (CyberLabel / Badge) ----
  label:
    text:          "@text.secondary"
    badge_bg:      "@accent.secondary"
    badge_text:    "@bg.base"
    badge_corner:  4
```

### 2.2 Token 引用解析机制

Token 使用 `@` 前缀引用其他 token，支持函数变换：

```
@brand.yellow              → 直接取值 (#FFE600)
@bg.raised                 → 别名链解析 (@surface.raised → #0E0E24)
lighten(#0E0E24, 10%)      → 亮度+10%
darken(#08081A, 5%)        → 亮度-5%
opacity(#00FFFF, 50%)      → 半透明
opacity(@accent.primary, 40%) → 组合使用
```

Python 解析器核心逻辑：

```python
class TokenResolver:
    """Token 引用解析器"""

    def __init__(self, raw_data: dict):
        self._raw = raw_data
        self._cache: dict[str, Any] = {}

    def resolve(self, key: str) -> Any:
        """递归解析 token 值，处理 @引用 和 函数变换"""
        if key in self._cache:
            return self._cache[key]

        value = self._get_raw(key)

        if isinstance(value, str):
            if value.startswith("@"):
                # 引用解析
                ref_key = value[1:]
                result = self.resolve(ref_key)
            elif self._is_function(value):
                # 函数变换: lighten/color/darken/opacity(arg, param)
                result = self._apply_func(value)
            else:
                result = value
        elif isinstance(value, list):
            result = [self.resolve_item(v) for v in value]
        else:
            result = value

        self._cache[key] = result
        return result
```

### 2.3 预设文件对比

| 维度 | 旧版 (JSON) | 新版 (YAML) |
|------|------------|------------|
| 格式 | 扁平键值对 | 四层嵌套 |
| 颜色数量 | ~54 个扁平字段 | ~80 个有层次 token |
| 关系表达 | 无（靠命名猜测） | 显式 `@` 引用 |
| 派生能力 | 无（每种状态手动写死） | 支持 lighten/darken/opacity |
| 组件绑定 | btn_default_bg 等硬绑定 | components.* 按组件隔离 |
| 可维护性 | 改一色需动多处 | 改 raw.brand.yellow 自动传播 |

### 2.4 预设文件示例（完整 cyberpunk.yaml）

```yaml
# ============================================================
# WARFRAME-RELIC 主题预设 — 赛博朋克 (Cyberpunk)
# ============================================================
_meta:
  name: "cyberpunk"
  display_name: "赛博朋克 2077"
  description: "深空黑底 + 霓虹高亮，契合 Warframe 科幻氛围"
  version: 2.0

# ── Layer 1: 原始色值 ──
raw:
  brand:
    yellow:  "#FFE600"
    cyan:    "#00FFFF"
    magenta: "#FF0099"
    orange:  "#FF7700"
    red:     "#FF0055"
    green:   "#00FF99"

  neutral:
    white:   "#E8ECFF"
    light:   "#99AACC"
    medium:  "#6677AA"
    dark:    "#334477"
    black:   "#111122"

  surface:
    base:    "#08081A"
    raised:  "#0E0E24"
    overlay: "#000000"

  game:
    gold:    "#FFD700"
    silver:  "#00FFFF"
    copper:  "#FF7700"
    unknown: "#556688"

  external:
    bilibili:      "#FB7299"
    bilibili_hover: "#FF8DB0"
    github:        "#58A6FF"
    github_hover:  "#79C0FF"

# ── Layer 2: 别名 ──
alias:
  accent:
    primary:   "@brand.yellow"
    secondary: "@brand.cyan"
    tertiary:  "@brand.magenta"

  semantic:
    success: "@brand.green"
    danger:  "@brand.red"
    warning: "@brand.orange"
    info:    "@brand.cyan"

  text:
    primary:  "@neutral.white"
    secondary: "@neutral.light"
    tertiary: "@neutral.medium"
    disabled: "@neutral.dark"
    inverse:  "@neutral.black"

  border:
    subtle:   "@neutral.dark"
    default:  "@neutral.medium"
    emphasis: "@accent.primary"
    focus:    "@accent.secondary"

  bg:
    base:     "@surface.base"
    raised:   "@surface.raised"
    overlay:  "@surface.overlay"

  gradient:
    progress: ["@brand.yellow", "@brand.red", "@brand.cyan"]

# ── Layer 3: 语义令牌 ──
semantic:
  state:
    normal:  { bg: "@bg.raised", text: "@text.primary", border: "@border.default" }
    hover:   { bg: "lighten(@bg.raised, 8%)", text: "@accent.secondary", border: "@accent.primary" }
    pressed: { bg: "darken(@bg.base, 5%)", text: "@accent.primary", border: "@accent.secondary" }
    focused: { border: "@border.focus", glow: "@accent.secondary" }
    disabled:{ bg: "opacity(@bg.raised, 50%)", text: "@text.disabled", border: "opacity(@border.subtle, 50%)" }
    selected:{ bg: "@accent.primary", text: "@bg.base", border: "@accent.primary" }

# ── Layer 4: 组件令牌 ──
components:
  button:
    solid:
      fill:         "@accent.primary"
      text:         "@bg.base"
      border:       "@accent.primary"
      corner_size:  8
      glow_size:    6
      glow_opacity: 0.35
    outlined:
      fill:         "transparent"
      text:         "@accent.secondary"
      border:       "@accent.secondary"
      corner_size:  8
      glow_size:    4
      glow_opacity: 0.20
    ghost:
      fill:         "transparent"
      text:         "@text.secondary"
      border:       "@border.subtle"
      corner_size:  8
      glow_size:    0

  panel:
    bg:            "@bg.raised"
    bg_opacity:    0.92
    border:        "@border.subtle"
    border_width:  1
    corner_size:   12
    glow_color:    "@accent.secondary"
    glow_opacity:  0.06
    title_bar:
      bg:          "transparent"
      text:        "@accent.primary"
      underline:   "@accent.primary"
      icon_color:  "@accent.primary"
    corner_decor:
      color:       "@accent.primary"
      length:      12
      thickness:   2

  dialog:
    bg:            "@bg.raised"
    bg_opacity:    0.96
    border:        "@accent.secondary"
    border_width:  1.5
    corner_size:   14
    shadow_blur:   30
    shadow_opacity: 0.35
    title_text:    "@text.primary"
    body_text:     "@text.secondary"

  card:
    bg:            "lighten(@bg.raised, 3%)"
    border:        "@border.default"
    border_width:  1
    corner_size:   8
    padding_h:     16
    padding_v:     12

  input:
    bg:            "darken(@bg.raised, 2%)"
    text:          "@accent.secondary"
    placeholder:   "@text.tertiary"
    border:        "@border.subtle"
    border_focus:  "@accent.primary"
    corner_size:   6

  progress:
    track_bg:      "darken(@bg.base, 5%)"
    track_border:  "@border.subtle"
    fill_gradient: "@gradient.progress"
    corner_size:   4
    text:          "@text.primary"

  list_item:
    bg_normal:     "transparent"
    bg_hover:      "opacity(@accent.secondary, 8%)"
    bg_selected:   "@accent.primary"
    text_normal:   "@text.primary"
    text_selected: "@bg.base"
    border:        "@border.subtle"
    corner_size:   6

  label:
    text:          "@text.secondary"
    badge_bg:      "@accent.secondary"
    badge_text:    "@bg.base"
    badge_corner:  4

  overlay:
    bg_rgba:       [8, 8, 26, 230]
    selection:     [20, 2, 40, 120]
    panel_overlay: [5, 5, 20]

  nav:
    item_bg:       "opacity(@bg.raised, 70%)"
    item_text:     "@text.tertiary"
    item_hover_bg: "@item_bg"
    item_hover_text: "@text.primary"
    item_selected_bg: "@accent.primary"
    item_selected_text: "@bg.base"
    divider:       "@border.subtle"
```

---


---

## 3. 空间与尺寸系统 — Design Space

> **设计目标**：所有交互控件高度和间距使用统一的 Space Token。


```
14, 16, 18, 20, 24, 26, 28, 30, 32, 34, 36, 38, 40, 56, 60, 64, 120, 320, 780
```

**19 种不同的高度值**，没有任何规律可言。同样的问题存在于 padding、font-size、border-radius 等所有维度。

### 3.1 设计哲学：4px 基准网格

采用 **4px 基准单位 (Base Unit = 4px)**，所有尺寸必须是 4 的倍数（或 2 的倍数用于半级）。这与 Material Design 的 8dp grid 和 Ant Design 的 4px grid 对齐。

```
基准序列:  0   4   8   12  16  20  24  32  40  48  56  64  72  80  ...
           │   │   │   │   │   │   │   │   │   │   │   │   │
           U   ×1  ×2  ×3  ×4  ×5  ×6  ×8  ×10 ×12 ×14 ×16 ×18 ×20
```

**铁律：禁止出现 4 不能整除的尺寸值。**

### 3.2 Design Space Token 定义

与颜色 Token 采用相同的四层架构，空间/尺寸也纳入统一管理：

```yaml
# ============================================================
# Design Space Tokens（空间与尺寸令牌）
# 与颜色 Token 共享同一预设文件，位于 space: 节点下
# ============================================================

space:
  # ── 间距阶梯（Spacing Scale）──
  # 用于 margin / padding / gap
  spacing:
    none:    0
    xs:      4        # 紧凑元素间距（图标与文字之间）
    sm:      8        # 相关元素组内间距
    md:      12       # 组内元素标准间距
    lg:      16       # 区块之间间距
    xl:      20       # 大区块分隔
    xxl:     24       # 页面级区块分隔
    xxxl:    32       # 章节级大间隔

  # ── 控件高度（Control Heights）──
  # 所有交互控件的高度必须取自此表
  height:
    # 输入型控件
    input_sm:     28       # 小输入框、搜索框内嵌
    input_md:     36       # 标准输入框、下拉框
    input_lg:     44       # 大输入框（如多行输入的单行高度参照）

    # 按钮型控件
    btn_sm:       28       # 小按钮（工具栏、内联操作）
    btn_md:       36       # 标准按钮（表单操作）
    btn_lg:       44       # 大按钮（主操作 CTA）
    btn_icon:     32       # 图标按钮（正方形）

    # 其他控件
    nav_item:     40       # 导航栏项
    list_item:    44       # 列表项行高
    card_min:     60       # 卡片最小高度
    toggle_sw:    24       # 开关滑块高度
    progress:     10       # 进度条厚度
    scrollbar:    10       # 滚动条宽度
    badge:        20       # 徽章高度
    tooltip_arrow: 8       # 提示箭头大小

  # ── 圆角/切角尺寸（Corner Sizes）──
  corner:
    none:         0        # 无切角（直角）
    sm:           4        # 小切角（输入框、徽章）
    md:           8        # 标准切角（按钮、卡片）
    lg:           12       # 大切角（面板、对话框）
    xl:           16       # 超大切角（主窗口装饰）

  # ── 字体排印（Typography）──
  # 字体分层策略：
  #   display → 标题/品牌文字（可选用有设计感的字体，如 Iceberg）
  #   body    → 正文/界面文字（需保证可读性，如 Century Gothic / Microsoft YaHei）
  #   mono    → 等宽/代码/数据（保持 Consolas）
  #   decorative → 特殊装饰用途（如 Monoton），仅在个别位置按需使用，不作为全局默认
  font:
    family:
      # 显示字体 — 用于标题、品牌名、导航栏、面板标题栏
      # 可替换为: "Iceberg", "Orbitron", "Audiowide" 等科技感字体
      display:     '"Microsoft YaHei", "Segoe UI", sans-serif'

      # 正文字体 — 用于按钮、卡片、表单、列表等所有 UI 文字
      # 需要良好的可读性，fallback 到系统默认无衬线
      # 可替换为: "Century Gothic", "Roboto", "Helvetica Neue" 等
      body:        '"Microsoft YaHei", "Segoe UI", sans-serif'

      # 等宽字体 — 用于版本号、数据 ID、代码片段、快捷键键名
      mono:        '"Consolas", "Courier New", monospace'

      # 装饰字体（可选）— 仅用于个别装饰性位置
      # 典型用途：Splash Screen 大字、"BETA"角标、特殊 Badge、彩蛋文字
      # 使用方式：在具体组件中按需引用 token("font.family.decorative")，不在全局默认样式中生效
      # 可选字体: "Monoton"（霓虹复古）、"Press Start 2P"（像素风）、"Ruslan Display"（赛博感）
      decorative:  'sans-serif'    # 默认占位，按需替换为实际装饰字体

    size:
      # 显示字体（标题类）
      display_lg:  24       # 主标题（窗口标题、弹窗标题）
      display_md:  20       # 二级标题（区块标题）
      display_sm:  16       # 三级标题（卡片标题）

      # 正文字体
      body_lg:     15       # 大正文（重要说明）
      body_md:     13       # 标准正文（默认字号，当前使用的 13px）
      body_sm:     12       # 小正文（辅助文字）
      body_xs:     11       # 更小（提示、注脚）

      # 标签字体
      label_md:    13       # 表单标签
      label_sm:    12       # 小标签
      caption:     10       # 说明文字（最小可读）

    weight:
      regular:     400
      medium:      500
      bold:        700

    line_height:
      tight:       1.2      # 标题
      normal:      1.5      # 正文
      relaxed:     1.75     # 宽松文本

  # ── 图标尺寸（Icon Sizes）──
  icon:
    xs:           12       # 行内小图标
    sm:           16       # 按钮/列表内图标
    md:           20       # 导航栏图标（当前使用值）
    lg:           24       # 功能按钮图标（Overlay 中使用）
    xl:           32       # 大图标（状态指示）

  # ── 边框宽度（Border Widths）──
  border:
    none:         0
    thin:         1        # 默认边框
    medium:       1.5      # 强调边框（对话框）
    thick:        2        # 装饰线、焦点环
    focus_ring:   2        # 键盘焦点外圈

  # ── 阴影（Shadows）──
  shadow:
    none:         "0 0 0 transparent"
    sm:           "0 2px 4px rgba(0,0,0,0.3)"      # 轻微浮起（卡片）
    md:           "0 4px 12px rgba(0,0,0,0.4)"     # 中等浮起（下拉菜单）
    lg:           "0 8px 24px rgba(0,0,0,0.5)"     # 强浮起（对话框、弹窗）
    glow:         "0 0 8px {color}"                 # 霓虹发光（{color} 运行时替换）

  # ── 动画时长（Durations）──
  duration:
    instant:      80       # 即时反馈（hover 颜色变化）
    fast:         150      # 快速过渡（按钮状态切换）
    normal:       250      # 标准动画（面板展开/收起）
    slow:         400      # 慢速动画（页面切换）
    glow_pulse:   2000     # 发光脉冲周期
```

### 3.3 尺寸使用规范

#### 交互控件高度对照表

| 控件类型 | 高度 Token | 像素值 | 内边距 | 使用场景 |
|---------|-----------|--------|-------|---------|
| 小按钮 | `height.btn_sm` | 28px | h:4 v:8 | 工具栏、表格内操作 |
| 标准按钮 | `height.btn_md` | 36px | h:16 v:8 | 表单提交、对话框操作 |
| 大按钮(CTA) | `height.btn_lg` | 44px | h:24 v:10 | 主要行动号召 |
| 图标按钮 | `height.btn_icon` | 32px | 全部 | 工具栏纯图标按钮 |
| 输入框(标准) | `height.input_md` | 36px | h:10 v:8 | 表单输入 |
| 导航项 | `height.nav_item` | 40px | h:12 v:10 | 侧边导航 |
| 列表项 | `height.list_item` | 44px | h:12 v:10 | 数据列表行 |

#### 间距使用规则

```
┌────────────────────────────────────────────────────┐
│                                                    │
│  ★ 元素内部 → spacing.xs (4px)                     │
│    [图标][4px]文字                                  │
│                                                    │
│  ★ 相关元素组内 → spacing.sm ~ md (8~12px)          │
│    [标签] 8px [输入框]                              │
│                                                    │
│  ★ 表单行间距 → spacing.lg (16px)                   │
│    ┌─────────────────┐                             │
│    │ 用户名 [________] │ 16px                        │
│    │ 密码   [________] │                             │
│    └─────────────────┘                             │
│                                                    │
│  ★ 功能区块间距 → spacing.xxl (24px)                │
│    ══ 快捷键配置 ═══                                │
│    24px                                             │
│    ══ 主题换肤 ═══                                  │
│                                                    │
│  ★ 页面章节间距 → spacing.xxxl (32px+)              │
│                                                    │
└────────────────────────────────────────────────────┘
```

#### 当前代码 → 新 Token 映射（修复混乱）

| 当前硬编码值 | 问题 | 应替换为 | 说明 |
|-------------|------|---------|------|
| `setMinimumHeight(780)` | 窗口级 | 窗口 min-height 不归 token 管 | 保持硬编码或放 config |

**字体大小映射**：

| 当前值 | 归类 | Token |
|--------|------|-------|
| 10px | caption | `font.size.caption` |
| 11px | body_xs | `font.size.body_xs` |
| 12px | body_sm / label_sm | `font.size.body_sm` |
| 13px | body_md（默认） | `font.size.body_md` |
| 14px | display_sm | `font.size.display_sm` |

### 3.4 Space Token 访问接口

```python
# 在 CyberWidgetMixin 或任何需要尺寸的地方
from core.tokens.manager import TokenManager

# 方式一：通过 Mixin 的静态方法（推荐，组件内部使用）
class MyWidget(CyberWidgetMixin, QPushButton):
    def __init__(self, ...):
        btn_height = self.space("height.btn_md")        # → 36
        padding_h = self.space("spacing.lg")            # → 16
        corner = self.space("corner.md")                # → 8
        font_size = self.space("font.size.body_md")     # → 13

# 方式二：通过 TokenManager 单例（非组件代码中使用）
mgr = TokenManager.get()
btn_height = mgr.resolve_space("height.btn_md")        # → 36
padding_h = mgr.resolve_space("spacing.lg")            # → 16

# ❌ 错误：旧 API（已废弃）
from core.tokens import tokens
tokens.space("height.btn_md")     # 不存在这个 API
tokens.component_specs(...)       # 不存在这个 API
```

### 3.5 与颜色 Token 的关系

Space Token 和 Color Token 是**并列的一等公民**，共同组成完整的 Design System：

```
DesignToken (设计令牌)
├── color (颜色)          ← 第 3 章已定义
│   ├── raw / alias / semantic / components
│   └── 解析器: TokenResolver
│
├── space (空间/尺寸)      ← 本章定义
│   ├── spacing / height / corner / font / icon / border / shadow / duration
│   └── 解析器: 同一个 TokenResolver（无 @引用需求，直接取值）
│
└── 两者在 YAML 中共存于同一预设文件
```

---


---

## 4. 模块深度层级 — UI 架构分层

> **核心思想**：UI 不是一堆组件的平铺集合，而是有明确深度层次的树状结构。
> 每一层有自己的职责、自己的组件集、自己的间距规则。
> 组件只能引用**同层及以下层**的 token 和组件。

### 4.1 六层模型 (L0 ~ L5)

```
L0 ┌─────────────────────────────────────────────────┐
   │              Application Shell                    │
   │         应用外壳（窗口框架 + 全局背景）             │
   │  职责: 窗口管理、背景图/模糊、全局遮罩、DPI 缩放   │
   │  组件: ManagementPanel, BgImageWidget,            │
   │        QGraphicsBlurEffect, Overlay (顶层)       │
   │  Token: surface.base, overlay.*, window_*         │
   └──────────────────────┬──────────────────────────┘
                        │ 包含
L1 ┌────────────────────▼──────────────────────────┐
   │            Navigation Shell                      │
   │         导航外壳（导航栏 + 全局控制栏）            │
   │  职责: 页面切换、全局状态指示、窗口控制按钮       │
   │  组件: CyberNavBar, CyberNavItem,                │
   │        WindowControlButtons, GlobalStatusBar     │
   │  Token: nav.*, height.nav_item, spacing.md       │
   │  规则: 固定宽度，不随内容区滚动                   │
   └──────────────────────┬──────────────────────────┘
                        │ 包含
L2 ┌────────────────────▼──────────────────────────┐
   │            Page Container                        │
   │         页面容器（内容区 + 滚动区域）              │
   │  职责: 内容布局、滚动管理、页面切换动画           │
   │  组件: QScrollArea (包装), CyberPageArea         │
   │  Token: spacing.xxl, bg.raised                  │
   │  规则: L2 内部可以滚动，L0/L1 不滚动              │
   └──────┬──────────────────────────────┬───────────┘
         │ 包含                         │ 包含
L3 ┌─────▼──────────────┐    ┌────────▼───────────┐
   │   Section Group     │    │   Section Group     │
   │   功能区块容器       │    │   功能区块容器       │
   │                     │    │                     │
   │  例: "快捷键配置"    │    │  例: "主题换肤"      │
   │      "数据总览"      │    │      "价格数据"      │
   │      "物品查询"      │    │      "关于作者"      │
   │                     │    │                     │
   │  组件: CyberSection │    │  组件: CyberSection │
   │  Token: card.*       │    │  Token: card.*      │
   │  间距: 内部 spacing.lg                       │
   └──────┬──────────────┘    └────────┬───────────┘
         │ 包含子项                     │ 包含子项
L4 ┌─────▼────────────────────────────────────────┐
   │           Component Row / Card                  │
   │        组件行 / 卡片（功能的最小独立单元）        │
   │                                                │
   │  例: 一个热键配置行                              │
   │      一个遗物状态查询结果卡                      │
   │      一个触发器配置卡                            │
   │      一个价格查询结果行                          │
   │                                                │
   │  组件: CyberCard, CyberFormRow,                │
   │        CyberListItem, CyberResultCard           │
   │  Token: list_item.*, spacing.md,               │
   │         height.list_item                        │
   │  间距: 行间距 spacing.sm                        │
   └──────┬──────────────────────┬──────────────────┘
         │ 包含原子控件            │ 包含原子控件
L5 ┌─────▼──────────┐    ┌──────▼──────────┐
   │  Atomic Widget  │    │  Atomic Widget   │
   │  原子控件        │    │  原子控件        │
   │                 │    │                  │
   │  CyberButton    │    │  CyberLineEdit   │
   │  CyberLabel     │    │  CyberToggle     │
   │  CyberBadge     │    │  CyberComboBox   │
   │  CyberIcon      │    │  CyberProgress   │
   │                 │    │                  │
   │  不可再拆分      │    │  不可再拆分       │
   │  只依赖 Token    │    │  只依赖 Token     │
   └─────────────────┘    └──────────────────┘
```

### 4.2 各层详细规格

#### L0: Application Shell（应用外壳）

| 属性 | 规格 |
|------|------|
| **职责** | 窗口生命周期、全局背景渲染、DPI 缩放、鼠标穿透 |
| **对应现有代码** | `ManagementPanel.__init__` 中的四层叠加 (`BgImageWidget` → `OpacityOverlay` → `ContentLayer`) |
| **拥有的子层** | L1 (Navigation) + L2 (Page Container) |
| **使用的组件** | `CyberPanel` (作为外壳), `QGraphicsBlurEffect` |
| **使用的 Token** | `surface.base`, `overlay.bg_rgba`, `window.min_width`, `window.min_height` |
| **不包含** | 任何业务逻辑控件 |
| **规则** | L0 本身不滚动；L0 的尺寸变化需同步到所有子层 |

#### L1: Navigation Shell（导航外壳）

| 属性 | 规格 |
|------|------|
| **职责** | 功能模块切换、全局状态显示、面包屑（如有） |
| **对应现有代码** | `_nav_list` (QListWidget, 140px 宽) + 10 个导航项 |
| **拥有的子层** | L2 (Page Container) |
| **使用的组件** | `CyberNavBar`, `CyberNavItem` |
| **使用的 Token** | `nav.*`, `height.nav_item` (40), `icon.md` (20) |
| **当前导航项清单** | 见下方 5.3 节 |
| **规则** | 固定宽度不随内容滚动；选中态由 `semantic.state.selected` 控制 |

#### L2: Page Container（页面容器）

| 属性 | 规格 |
|------|------|
| **职责** | 承载当前选中导航页的内容；提供滚动区域；管理页面切换 |
| **对应现有代码** | `_left_scroll` (QScrollArea) + 其内部的垂直流式布局 |
| **拥有的子层** | L3 (Section Group) × N |
| **使用的组件** | `QScrollArea` (原生，带 CyberScrollBar) |
| **使用的 Token** | `spacing.xxl` (24, 区块间距), `bg.raised` |
| **规则** | L2 可滚动；L2 切换时做淡入淡出动画 (`duration.normal` = 250ms) |

#### L3: Section Group（功能区块）

| 属性 | 规格 |
|------|------|
| **职责** | 将相关功能聚合为一个视觉区块（类似旧版 QGroupBox 的角色） |
| **对应现有代码** | 各 `_build_*_group()` 方法创建的 QGroupBox |
| **拥有的子层** | L4 (Component Row/Card) × N |
| **使用的组件** | `CyberSection` (继承自 CyberPanel, 带标题栏) |
| **使用的 Token** | `card.*`, `display_sm` (16, 区块标题字), `spacing.lg` (16, 内部间距) |
| **规则** | 区块间间距 = `spacing.xxl` (24)；区块内有统一的 padding |

#### L4: Component Row / Card（组件行/卡片）

| 属性 | 规格 |
|------|------|
| **职责** | 单个数据项或单个表单行的完整表达 |
| **对应现有代码** | 热键配置行、触发器卡片、物品搜索结果行、价格信息展示 |
| **拥有的子层** | L5 (Atomic Widget) × N |
| **使用的组件** | `CyberCard`, `CyberFormRow`, `CyberListItem` |
| **使用的 Token** | `list_item.*`, `height.list_item` (44), `spacing.md` (12) |
| **规则** | 行间距 = `spacing.sm` (8)；每行内部水平布局遵循 `spacing.sm` ~ `spacing.md` |

#### L5: Atomic Widget（原子控件）

| 属性 | 规格 |
|------|------|
| **职责** | 不可再拆分的最小交互单元 |
| **组件清单** | `CyberButton`, `CyberLineEdit`, `CyberLabel`, `CyberBadge`, `CyberToggle`, `CyberComboBox`, `CyberIcon`, `CyberProgressBar`, `CyberScrollBar`, `CyberCheckBox`, `CyberRadioButton` |
| **依赖** | 仅依赖 Token 系统（color + space）；不依赖任何业务逻辑 |
| **规则** | L5 组件不知道自己被用在哪一层；它只关心自己的 token 和交互状态 |

### 4.3 当前功能模块 → 层级映射

将现有的 10 个导航模块和 Overlay 分别归入正确的层级：

```
WARFRAME-RELIC 应用结构
│
├─ L0: Application Shell (ManagementPanel)
│   ├─ L1: Navigation Shell
│   │   └─ 导航项列表 (10 项):
│   │       ├─ [功能开关]   → L2: TogglesPage
│   │       ├─ [数据总览]   → L2: DbOverviewPage
│   │       ├─ [物品查询]   → L2: ItemsPage
│   │       ├─ [辅助触发器] → L2: TriggersPage
│   │       ├─ [价格数据]   → L2: PricesPage
│   │       ├─ [快捷键]     → L2: HotkeysPage
│   │       ├─ [主题换肤]   → L2: ThemePage
│   │       ├─ [紧急重置]   → L2: ResetPage
│   │       ├─ [语言预设]   → L2: PresetPage
│   │       └─ [关于作者]   → L2: AboutPage
│   │
│   └─ L2: Page Container (每个 Page 内含:)
│       │
│       ├─ L3: Section Group 示例 — [快捷键] 页面
│       │   ├─ L3: "按键绑定" Section
│       │   │   └─ L4: 热键配置行 × N (每行 = L5: Label + HotkeyCaptureButton)
│       │   ├─ L3: "辅助触发器" Section
│       │   │   └─ L4: 触发器卡片 × N
│       │   └─ L3: "操作" Section
│       │       └─ L4: 重置/保存按钮行
│       │
│       ├─ L3: Section Group 示例 — [主题换肤] 页面
│       │   ├─ L3: "预设选择" Section → L4: PresetCombo + Description
│       │   ├─ L3: "颜色编辑" Section → L4: 色块网格 (每块 = L5: ColorSwatch)
│       │   └─ L3: "背景设置" Section → L4: 图片选择 + 滑块
│       │
│       └─ L3: Section Group 示例 — [物品查询] 页面
│           ├─ L3: "搜索" Section → L4: SearchInput + ResultList
│           └─ L3: "结果详情" Section → L4: ItemInfoCards
│
├─ Overlay (独立顶级窗口, 平级于 L0)
│   ├─ L3: "功能选择" Section (模式按钮组)
│   │   └─ L4: ModeButton × N (截图中的切角按钮)
│   ├─ L3: "标注" Layer (Annotation)
│   └─ L3: "框选" Layer (RegionSelector)
│
└─ Market Query (独立进程窗口, 另一套 L0-L5)
    ├─ L1: 搜索栏
    ├─ L2: 结果列表
    └─ L3: 详情卡片
```

### 4.4 层级间的依赖规则

```
┌─────────────────────────────────────────────────┐
│              依赖方向（箭头表示"可以使用"）        │
│                                                 │
│  L0 ──────────────────────────────────────┐     │
│    │                                       │     │
│  L1 ───────────────────────────────┐       │     │
│    │                                 │       │     │
│  L2 ─────────────────────────┐       │       │     │
│    │                           │       │       │     │
│  L3 ──────────────────┐       │       │       │     │
│    │                   │       │       │       │     │
│  L4 ────────────┐     │       │       │       │     │
│    │             │     │       │       │       │     │
│  L5 (Atomic)     │     │       │       │       │     │
│    │             │     │       │       │       │     │
│    └─────────────┼─────┼───────┼───────┼───────┼─────┘
│                  │     │       │       │       │
│              可以使用  可以使用  可以使用  可以使用  │
│              L5 Token  L5+L4   L5~L3   L5~L2   全部
│                                                 │
│  ⛔ 反向禁止: L3 不能引用 L4 的概念              │
│     例: Section Group 内不能有 "行高度" 的假设    │
│         它只知道自己的 padding 和 gap             │
└─────────────────────────────────────────────────┘
```

### 4.5 每层的 Token 访问边界

| 层级 | 可读取的 Token 范围 | 不可读取 |
|------|-------------------|---------|
| **L5 Atomic** | `components.*` (自身) + `semantic.state.*` + `space.*` (全部) | 不涉及层级概念 |
| **L4 Row/Card** | L5 全部 + `components.card.*` / `components.list_item.*` + `space.*` | 不读 L3 的 section token |
| **L3 Section** | L4 全部 + `components.panel.*` / `components.card.*` + `space.*` | 不读 L2 的 page token |
| **L2 Page** | L3 全部 + `nav.*` (只读) + `space.*` | 不读 L1 的 shell token |
| **L1 Nav** | L5 全部 + `nav.*` + `space.*` | 不读 L0 的 window token |
| **L0 Shell** | 全部 Token（它是根节点） | — |


### 4.6 分层带来的核心收益

| 收益 | 说明 |
|------|------|
| **可独立开发** | 每个 Page/Section 是独立文件，可并行编写、单独测试 |
| **依赖方向明确** | 单向依赖（上层引用下层），不存在循环 import |
| **Token 边界清晰** | 每层只能访问特定范围的 Token，不会越权读取 |
| **间距自动一致** | L3 用 xxl、L4 用 sm、L5 用 xs，视觉节奏由架构保证 |
| **新人友好** | 回答"我在哪一层？"就知道该用什么组件和什么 Token |
| **可渐进替换** | 先替换一个 Page 不影响其他 Page，降低重构风险 |

---

## 5. 组件架构 — Cyber Widget 框架

### 5.1 类继承体系

```
                    ┌──────────────────────┐
                    │   QWidget (PySide6)     │
                    └──────────┬───────────┘
                               │ 继承（Qt 原生）
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼────────┐ ┌───▼───────────┐ ┌──▼────────────┐
    │ QPushButton      │ │ QLineEdit     │ │ QFrame        │
    │ (按钮原生能力)    │ │ (输入框原生)   │ │ (容器原生)     │
    └────────┬─────────┘ └──────┬────────┘ └──────┬────────┘
             │ 最小自绘           │ 最小自绘         │ 最小自绘
    ┌────────▼────────┐ ┌──────▼────────┐ ┌──────▼────────┐
    │  CyberButton     │ │  CyberInput   │ │  CyberPanel   │
    │  ─────────────  │ │  ─────────── │ │  ─────────── │
    │  • 切角背景绘制   │ │  • 切角边框   │ │  • 切角边框   │
    │  • 外发光层      │ │  • 外发光层   │ │  • 角落装饰   │
    │  • 文字: super() │ │  • 编辑: super│ │  • 子控件管理  │
    │  • 点击/禁用: Qt │ │  • 光标: Qt   │ │    : QFrame   │
    └────────┬─────────┘ └──────┬────────┘ └──────┬────────┘
             │                  │                   │
     ┌───────▼──────┐  ┌──────▼──────┐   ┌────────▼──────┐
     │ CyberToggle  │  │  CyberCard  │   │  CyberMessage  │
     │ (继承QCheckBox)│  (继承QFrame) │   │  Box (继承... )│
     └──────────────┘  └─────────────┘   └────────────────┘

关键规则:
每个组件 = Qt 原生控件(提供完整交互能力) + paintEvent 覆盖(只画切角/发光)
能 super() 就绝不自己画
```

### 5.2 CyberWidgetMixin 核心设计

```python
from PySide6.QtWidgets import QPushButton, QLineEdit, QFrame
from PySide6.QtGui import QPainter, QColor, QPolygonF, QPointF
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve
from core.tokens.manager import TokenManager  # 全局 Token 访问口


class CyberWidgetMixin:
    """赛博风格控件混入类（Mixin，非独立基类）。

    提供：
      - 切角矩形路径（缓存优化）
      - 从 Token 系统读取颜色的统一接口
      - hover/pressed/focused/disabled 状态机
      - 发光层绘制辅助方法

    设计为 Mixin 而非基类，因为每个组件继承的原生 Qt 控件不同。
    通过多重继承与 QPushButton / QLineEdit / QFrame 等组合使用。

    关键原则：能 super() 就绝不自己画。
    """

    # ── Token 读取接口（静态方法，不依赖实例状态） ──
    @staticmethod
    def token(path: str) -> str | int | float:
        """读取 Design Token 值。例如: token("bg.raised") → "#1A1A3E" """
        return TokenManager.get().resolve(path)

    @staticmethod
    def space(key: str) -> int:
        """读取空间尺寸 Token。例如: space("height.btn_md") → 36 """
        return TokenManager.get().resolve_space(key)

    # ── 状态管理 ───────────────────────────────────
    _state: str = "normal"  # normal / hover / pressed / focused / disabled

    def enterEvent(self, event): self._set_state("hover"); self.update()
    def leaveEvent(self, event): self._set_state("normal"); self.update()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._set_state("pressed")
        super().mousePressEvent(event)   # ← 让原生控件处理点击信号
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._state == "pressed":
            self._set_state("hover")
        super().mouseReleaseEvent(event) # ← 让原生控件处理释放信号
    def focusInEvent(self, event): self._set_state("focused"); self.update(); super().focusInEvent(event)
    def focusOutEvent(self, event): self._set_state("normal"); self.update(); super().focusOutEvent(event)

    def _set_state(self, new_state: str):
        old = self._state
        self._state = new_state
        if old != new_state:
            self.update()

    # ── 切角路径生成（带缓存） ─────────────────────
    def _chamfered_path(self, rect, corner_size: float) -> QPolygonF:
        """生成切角矩形路径。结果缓存到 self._path_cache。"""
        size = (rect.width(), rect.height())
        if not hasattr(self, '_path_cache') or self._cache_rect_size != size:
            c = corner_size
            path = QPolygonF([
                QPointF(rect.left() + c, rect.top()),
                QPointF(rect.right() - c, rect.top()),
                QPointF(rect.right(), rect.top() + c),
                QPointF(rect.right(), rect.bottom() - c),
                QPointF(rect.right() - c, rect.bottom()),
                QPointF(rect.left() + c, rect.bottom()),
                QPointF(rect.left(), rect.bottom() - c),
                QPointF(rect.left(), rect.top() + c),
            ])
            self._path_cache = path
            self._cache_rect_size = size
        return self._path_cache

    # ── 自绘部分：只画 QSS 做不到的 ─────────────────
    def _draw_chamfered_bg(self, painter: QPainter):
        """绘制切角背景 + 外发光。paintEvent 中最先调用此方法。"""
        bg_color = QColor(self.token(f"bg.{self._state}"))
        glow_color = QColor(self.token("accent.primary"))
        corner = self.space("corner.md")

        path = self._chamfered_path(self.rect(), corner)
        painter.fillPath(path, bg_color)

        # 外发光层（仅 hover/focused 态启用）
        if self._state in ("hover", "focused"):
            glow_color.setAlphaF(0.15)
            painter.setPen(QPen(glow_color, 1))
            painter.drawPath(path)


# ═══════════════════════════════════════════════════
#  具体组件 — 继承原生 Qt 控件 + 混入 Cyber 风格
# ═══════════════════════════════════════════════════

class CyberButton(CyberWidgetMixin, QPushButton):
    """切角按钮 — 继承 QPushButton 的所有能力，只换皮肤"""

    def __init__(self, text: str = "", parent=None):
        QPushButton.__init__(self, text, parent)  # 显式调用第一个基类
        h = self.space("height.btn_md")   # 从 token 取高度，不硬编码
        self.setFixedHeight(h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        """关键模式：先画自定义背景 → 再让 Qt 接管文字和其余部分"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ① 只画 QSS 做不到的部分：切角背景 + 外发光
        self._draw_chamfered_bg(painter)

        # ② 文字、点击态高亮、焦点环、禁用灰化...全部交给 QPushButton 原生处理
        #    包括：文字对齐、省略号、快捷键下划线、菜单箭头
        super().paintEvent(event)


class CyberInput(CyberWidgetMixin, QLineEdit):
    """切角输入框 — 继承 QLineEdit 的完整编辑能力"""

    def __init__(self, placeholder: str = "", parent=None):
        QLineEdit.__init__(self, parent)
        self.setPlaceholderText(placeholder)
        h = self.space("height.input_md")
        self.setFixedHeight(h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ① 只画切角边框 + 外发光（QSS 做不到的）
        self._draw_chamfered_bg(painter)

        # ② 光标、选中文字、输入内容、占位符...全由 QLineEdit 原生提供
        #    包括：光标闪烁、文字选中拖拽、Ctrl+A/Z/X/C/V、右键菜单、IME 输入法
        super().paintEvent(event)


class CyberPanel(CyberWidgetMixin, QFrame):
    """切角面板容器 — 继承 QFrame 的布局管理能力"""

    def __init__(self, parent=None):
        QFrame.__init__(self, parent)
        # QFrame 自动管理子控件的布局和尺寸

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ① 画切角边框 + 角落装饰线
        self._draw_chamfered_bg(painter)
        self._draw_corner_decor(painter)

        # ② 子控件渲染由 QFrame 自动完成（不需要 super() 因为 QFrame 无自身绘制）
```

### 5.3 关键设计决策说明

#### 为什么用 Mixin 而不是基类继承？

| 方案 | 优点 | 缺点 |
|------|------|------|
| 单一基类 `CyberWidgetBase(QWidget)` | 简单，所有组件共享一个父类 | **无法利用 Qt 原生控件能力**（光标/选中/撤销等） |
| 多重继承 `CyberWidgetMixin + QPushButton` | 继承原生能力 + 共享切角逻辑 | MRO 需要注意，`__init__` 需显式调用 |
| **选择** | **Mixin 模式** | — |

**核心权衡**：每个 Cyber Widget 需要继承的 Qt 原生控件不同（按钮用 QPushButton、输入框用 QLineEdit、面板用 QFrame），单一基类无法同时满足。Mixin 通过多重继承让每个组件获得"正确的原生能力" + "统一的切角皮肤"。

#### 切角路径为什么缓存？

`resizeEvent` 会频繁触发（窗口拖拽、布局调整），每次重建 8 点多边形虽然快，但在低端机器上仍可能造成卡顿。缓存以 `(width, height)` 为键，尺寸不变时直接返回。

#### Token 什么时候解析？

**启动时一次性解析完所有 token 到内存**，运行时只做字典查找。不在 paintEvent 中做字符串解析或颜色计算。

```python
# 启动时（一次）
TokenManager.get().load_preset("cyberpunk")   # 解析所有 @引用、函数变换，存入内存

# 运行时（每次 paintEvent，O(1) 查找）
color = self.token("bg.raised")   # 直接返回 QColor 或字符串
```

#### paintEvent 的执行顺序为什么重要？

每个自绘组件的 paintEvent 必须遵循固定顺序：

```
paintEvent(event):
    ① QPainter(self) + Antialiasing
    ② _draw_chamfered_bg()     ← 自绘：切角背景 + 外发光
    ③ super().paintEvent()      ← 原生：文字 / 光标 / 选中 / 边框
```

步骤 ② 和 ③ **不能颠倒**。如果先调 super() 再画背景，原生绘制的内容会被背景覆盖掉。

#### 多重继承中 super() 的行为

在 `class CyberButton(CyberWidgetMixin, QPushButton)` 中：
- `super().__init__(text, parent)` → 调用的是 QPushButton.__init__（MRO 中 QPushButton 在 Mixin 之后）
- `super().paintEvent(event)` → 调用的是 QPushButton.paintEvent
- `super().mousePressEvent(event)` → 调用的是 QPushButton.mousePressEvent（处理点击信号）

因此事件处理方法中必须调用 `super().xxxEvent()` 以保留原生行为。详见附录 B「多重继承注意事项」。

### 5.4 组件清单与优先级

| 组件 | 类名 | 用途 | 替换目标 | 优先级 |
|------|------|------|---------|--------|
| 按钮 | `CyberButton` | 所有操作按钮 | QPushButton (全局) | P0 |
| 面板 | `CyberPanel` | 容器/卡片外壳 | ManagementPanel 背景 | P0 |
| 对话框 | `CyberDialog` | 提示/确认弹窗 | QMessageBox | P0 |
| 卡片 | `CyberCard` | 列表项/信息块 | QGroupBox | P1 |
| 输入框 | `CyberLineEdit` | 文本输入 | QLineEdit | P1 |
| 进度条 | `CyberProgressBar` | 加载/进度 | QProgressBar | P1 |
| 导航项 | `CyberNavItem` | 左侧导航栏 | QListWidget item | P2 |
| 徽章 | `CyberBadge` | 状态小标签 | QLabel + stylesheet | P2 |
| 开关 | `CyberToggle` | 功能开关 | QCheckBox | P2 |
| 下拉框 | `CyberComboBox` | 选择器 | QComboBox | P3 |
| 滚动条 | `CyberScrollBar` | 滚动条 | QScrollBar | P3 |

---


---

## 6. 文件结构规划

```
core/
├── tokens/                          # ★ 新增：Token 系统（颜色 + 空间）
│   ├── __init__.py                  #   公开接口: tokens = TokenManager()
│   ├── manager.py                   #   TokenManager 单例：加载/解析/缓存/访问
│   ├── resolver.py                  #   TokenResolver: @引用解析 + 函数变换
│   ├── functions.py                 #   颜色函数: lighten/darken/opacity/mix
│   └── schema.py                    #   Token Schema 校验（确保预设完整性）
│
├── widgets/                         # ★ 新增：Cyber Widget 组件库 (L4 + L5)
│   ├── __init__.py                  #   方便导入: from core.widgets import *
│   ├── base.py                      #   CyberWidgetMixin (切角/动画/状态机)
│   ├── button.py                    #   CyberButton (solid/outlined/ghost)
│   ├── panel.py                     #   CyberPanel (容器基类, L3/L0 用)
│   ├── dialog.py                    #   CyberDialog (模态/非模态)
│   ├── card.py                      #   CyberCard (L4 列表卡片)
│   ├── section.py                   #   CyberSection (L3 功能区块容器)
│   ├── form_row.py                  #   CyberFormRow (L4 表单行)
│   ├── line_edit.py                 #   CyberLineEdit
│   ├── progress_bar.py              #   CyberProgressBar
│   ├── toggle.py                    #   CyberToggle
│   ├── badge.py                     #   CyberBadge
│   ├── nav_item.py                  #   CyberNavItem (L1 导航项)
│   ├── nav_bar.py                   #   CyberNavBar (L1 导航栏容器)
│   ├── combo_box.py                 #   CyberComboBox
│   ├── scroll_bar.py                #   CyberScrollBar
│   ├── label.py                     #   CyberLabel
│   └── icon.py                      #   CyberIcon
│
├── pages/                           # ★ 新增：L2 页面（每个导航项一个文件）
│   ├── __init__.py
│   ├── base_page.py                 #   BasePage 抽象基类
│   ├── toggles_page.py              #   功能开关页
│   ├── db_overview_page.py          #   数据总览页
│   ├── items_page.py                #   物品查询页
│   ├── triggers_page.py             #   辅助触发器页
│   ├── prices_page.py               #   价格数据页
│   ├── hotkeys_page.py              #   快捷键配置页
│   ├── theme_page.py                #   主题换肤页
│   ├── reset_page.py                #   紧急重置页
│   ├── preset_page.py               #   语言预设页
│   └── about_page.py                #   关于作者页
│
├── sections/                        # ★ 新增：L3 功能区块组件
│   ├── __init__.py
│   ├── cyber_section.py             #   CyberSection 基类
│   ├── hotkey_section.py            #   快捷键配置区块
│   ├── trigger_section.py           #   触发器配置区块
│   ├── theme_edit_section.py        #   颜色编辑区块
│   ├── theme_bg_section.py          #   背景设置区块
│   ├── db_stats_section.py          #   数据库状态区块
│   ├── item_search_section.py       #   物品搜索区块
│   ├── price_section.py             #   价格查询区块
│   ├── reset_section.py             #   紧急重置区块
│   ├── about_section.py             #   关于作者区块
│   └── preset_section.py            #   语言预设区块
│
├── theme_config.py                  # 向后兼容层（逐渐降级为薄包装）
├── stylesheet.py                    # 仅处理未替换的原生控件的最小 QSS
│
data/
├── presets/
│   ├── cyberpunk.yaml               # ★ 新版赛博朋克（含 color + space）
│   ├── daylight.yaml                # ★ 新版白天模式
│   └── custom.yaml                  # ★ 新版用户自定义
│
docs/
└── ui-framework-design.md           # ★ 本文档
```

### 6.1 模块依赖关系（无循环依赖）

```
tokens.manager          ← 入口单例，无依赖
  ├─ tokens.resolver    ← 解析引擎
  │   └─ tokens.functions ← 纯函数工具
  └─ tokens.schema      ← 校验规则

widgets.base            ← 依赖 tokens.manager
  ├─ widgets.button     ← 依赖 base
  ├─ widgets.panel      ← 依赖 base
  ├─ widgets.dialog     ← 依赖 panel
  ├─ widgets.card       ← 依赖 base
  └─ ... (其余组件)

# 以下为过渡期兼容层（Phase 3 结束后移除）:
theme_config            ← 依赖 tokens.manager (桥接旧接口)
stylesheet             ← 依赖 theme_config + widgets (混合模式)

# 旧模块（不修改，只读）:
theme_proxy             ← 依赖 theme_config (已废弃)
panel_styles           ← 依赖 theme_config (已废弃)
```

---


---

## 7. 迁移策略

> **详细内容见 `docs/ui-refactor-analysis.md`（四步走方案 + 验收标准 + 兼容映射表）。**
>
> 本设计文档只定义新系统的规范，不包含旧代码的迁移细节。
> 如需查阅"旧常量对应哪个新 Token"，请查看重构报告的 **附录 A: 兼容映射表**。

### 新系统文件与旧代码的关系

| 新文件/目录 | 对应旧文件 | 关系 |
|------------|-----------|------|
| `core/tokens/` | `core/theme_config.py` + `data/presets/*.json` | 替代：Token 系统替代单例代理 |
| `core/widgets/` | `core/panel_styles.py` 的 QSS 方法 | 替代：自绘组件替代内联样式 |
| `core/pages/` + `core/sections/` | `core/management_panel.py` 的 UI 构建 | 替代：分层架构替代巨型类 |
| `core/services/` | `core/panel_builder.py` 的纯逻辑部分 | 提取：逻辑代码原样搬入 |
| `app_shell.py` | `main.py` 的窗口创建 | 替代：新外壳替代旧窗口 |

> 迁移期间新旧文件共存，详见重构报告第六章「信号桥接方案」。

### 7.1 四阶段迁移路线

```
Phase 0: 基础设施 ────────────── Phase 1: 骨架搭建 ──── Phase 2: 页面实现 ── Phase 3: 切换清理
   │                                    │                      │                │
   ├─ Token 系统                        ├─ AppShell             ├─ 逐页替换       ├─ 切换入口
   ├─ Widget 基类                       ├─ Navigation           ├─ 新功能走新路   ├─ 清理旧代码
   ├─ 解析器 + 单元测试                  ├─ Service 层桥接       ├─ 回归验证       └─ 归档文档
   └─ 预设 YAML                          └─ 首页可运行
```

### 7.2 Phase 0：基础设施（预计 3-5 天）

**目标**：建立不依赖任何 UI 的核心能力，可独立运行和测试。

#### 交付物

| # | 交付物 | 文件位置 | 验证方式 |
|---|--------|---------|---------|
| 1 | TokenResolver 解析器 | `core/tokens/resolver.py` | 单元测试覆盖全部4层 |
| 2 | TokenManager 管理器 | `core/tokens/manager.py` | 可加载/切换预设 |
| 3 | cyberpunk.yaml 完整预设 | `data/presets/cyberpunk.yaml` | 80+ token 全部解析无误 |
| 4 | CyberWidgetMixin 基类 | `core/widgets/base.py` | pytest-qt 实例化无报错 |
| 5 | 颜色函数库（lighten/darken等）| `core/tokens/color_utils.py` | 对比手工计算值 100% 一致 |

#### 验收标准

```markdown
- [ ] `python -m pytest tests/test_tokens.py` 全部通过，覆盖率 > 80%
- [ ] TokenResolver.resolve("components.button.solid.fill") 返回正确 QColor
- [ ] @引用链深度 > 10 层时仍能正确解析（无死循环）
- [ ] lighten/darken/opacity 函数输出与设计稿色值误差 < 1%
- [ ] CyberWidgetMixin 不继承 QWidget，不能单独实例化
- [ ] CyberButton(CyberWidgetMixin, QPushButton) 可正常显示、点击、发射信号
```

#### 进入 Phase 1 的门禁条件

- 所有交付物通过验收标准
- 新代码统一使用 **PySide6**（禁止 PyQt6），无其他第三方依赖（除 PyYAML）
- 代码通过 ruff/mypy 静态检查（0 error / warning 可接受）

---

### 7.3 Phase 1：骨架搭建（预计 3-5 天）

**目标**：构建一个"能跑起来的空壳"，展示新架构的完整路径。

#### 交付物

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | **AppShell** (`app_shell.py`) | L0 外壳：标题栏 + 导航栏 + 内容区 + 状态栏 |
| 2 | **Navigation Shell** (`core/widgets/nav_bar.py`) | L1 导航栏：导航项列表 + 当前页高亮 |
| 3 | **BasePage** 抽象基类 (`pages/base_page.py`) | L2 页面基类：定义 Page 接口契约 |
| 4 | **Service 层桥接** (`services/bridge.py`) | 新旧系统数据接口适配 |
| 5 | **首页占位** (`pages/home_page.py`) | 第一个可运行的 Page（哪怕只有 "Coming Soon"） |

#### 验收标准

```markdown
- [ ] 启动应用 → 看到 AppShell 窗口（深色背景 + 标题栏 + 左侧导航 + 右侧内容区）
- [ ] 点击导航项 → 内容区切换到对应 Page（至少有首页和一个占位页）
- [ ] 导航项高亮状态与当前 Page 同步
- [ ] 窗口 resize 时，各区域按比例自适应（无布局崩溃）
- [ ] ServiceBridge 可从旧系统读取真实数据并传递给新 UI
- [ ] 关闭窗口时无 crash、无 zombie 进程
```

#### 进入 Phase 2 的门禁条件

- 应用可独立启动，不依赖旧系统主入口
- 至少 1 个完整 Page 可展示真实数据
- 内存占用 < 100MB（空壳状态）

---

### 7.4 Phase 2：逐页实现（预计 7-14 天，可与 P1 任务并行）

**目标**：按优先级逐个实现业务页面，每个 Page 独立可验收。

#### 实现顺序与依赖

```
┌─────────────────────────────────────────────────────┐
│  Wave 1（核心页面，必须先完成）                        │
│                                                     │
│  ① home_page          （首页/仪表盘 — 已在P1完成骨架） │
│  ② db_overview_page   （数据总览 — 最常用页面）        │
│  ③ items_page         （物品查询 — 核心功能）          │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Wave 2（功能页面，依赖 Wave 1 的 Section 组件）      │
│                                                     │
│  ④ prices_page        （价格数据 — 复用 item_search） │
│  ⑤ toggles_page       （功能开关 — 复用 form_row）    │
│  ⑥ triggers_page      （辅助触发器 — 复用 form_row）  │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Wave 3（辅助页面，低优先级）                          │
│                                                     │
│  ⑦ hotkeys_page       ⑧ theme_page                 │
│  ⑨ reset_page         ⑩ preset_page                │
│  ⑪ about_page                                     │
└─────────────────────────────────────────────────────┘
```

#### 每个 Page 的验收模板

每个新 Page 合入前必须满足：

```markdown
## [PageName] 验收清单

### 功能验收
- [ ] 所有 UI 元素可见且可交互
- [ ] 数据来自 Service 层（非硬编码 mock，除非 Service 未就绪）
- [ ] 用户操作产生正确的信号发射（可用 pytest-qt 验证）

### 视觉验收
- [ ] 颜色全部取自 Token（grep 确认无硬编码 #XXXXXX）
- [ ] 间距符合 Space Token 规范
- [ ] 切角/发光效果与设计稿一致（目测 + 截图对比）
- [ ] hover / pressed / focused / disabled 四态正常

### 边界情况
- [ ] 空数据状态显示友好提示（非空白或报错）
- [ ] 加载中状态有 loading 指示
- [ ] 错误状态有用户可理解的错误信息
- [ ] 窗口缩放到最小尺寸时不截断关键信息
```

---

### 7.5 Phase 3：切换与清理（预计 2-3 天）

**目标**：废弃旧系统，新系统成为唯一入口。

#### 交付物

| # | 交付物 | 风险等级 |
|---|--------|---------|
| 1 | 主入口切换为 `app_shell.py` | **高** — 不可回退点 |
| 2 | 旧代码标记 `@deprecated` | 低 |
| 3 | 配置迁移脚本（JSON → YAML） | 中 |
| 4 | 用户操作指南更新 | 低 |

#### 回滚预案

```
如果 Phase 3 上线后出现阻塞性问题：
1. main.py 中保留旧入口开关（环境变量 USE_LEGACY_UI=1）
2. 用户配置自动备份（修改前复制 .bak）
3. 回滚后新产生的配置以"新格式为主，旧格式兼容"原则合并
4. 保留旧代码至少 2 个版本周期后再删除
```

---

### 7.6 风险登记册

| ID | 风险描述 | 概率 | 影响 | 缓解措施 | 负责人 |
|----|---------|------|------|---------|--------|
| R01 | 自绘控件性能不达标（>50卡顿） | 中 | 高 | Phase 0 先做 paintEvent 性能原型；启用 QPixmapCache | 开发 |
| R02 | Token 循环引用导致解析死锁 | 低 | 高 | Resolver 加最大深度限制(默认16层)；启动时检测环 | 开发 |
| R03 | 旧代码理解偏差导致接口设计错误 | 高 | 高 | Phase 0 先写 Service 接口文档，对齐后再编码 | 开发 |
| R04 | PyQt6 在用户机器安装失败 | 中 | 高 | 提供便携版打包分发；文档写清依赖版本 | 开发 |
| R05 | 设计文档过度设计导致永远不动手 | 高 | 高 | 设定 MVP 边界：Phase 0 结束就必须有可运行产物 | PM |
| R06 | 新旧系统数据不一致 | 中 | 中 | Service 层作为唯一数据源；新旧 UI 共享同一实例 | 开发 |
| R07 | 用户不接受新 UI 风格变化 | 中 | 中 | Phase 2 提供"经典模式"开关；收集反馈迭代 | 全员 |

---

## 8. 状态管理与数据流

> **核心原则**：UI 是状态的函数。所有动态行为都可以归结为「状态变化 → UI 重绘」。
> 本章定义状态怎么存、数据怎么流、组件怎么通信。

### 8.1 三层状态模型

```
┌─────────────────────────────────────────────┐
│           Global State（全局状态）            │
│  ┌──────────┬──────────┬──────────────────┐ │
│  │ 当前主题  │ 用户偏好  │ 应用级通知队列     │ │
│  │ (Token)  │(语言/窗口)│(toast/错误提示)   │ │
│  └──────────┴──────────┴──────────────────┘ │
│         ↕ 读写：AppShell / Service 层       │
├─────────────────────────────────────────────┤
│            Page State（页面状态）             │
│  ┌──────────┬──────────┬──────────────────┐ │
│  │ 筛选条件  │ 分页游标  │ 页面级加载状态     │ │
│  │(平台筛选)│(当前页码) │(loading/error)   │ │
│  └──────────┴──────────┴──────────────────┘ │
│         ↕ 读写：BasePage / 其下属 Section    │
├─────────────────────────────────────────────┤
│        Component State（组件状态）            │
│  ┌──────────┬──────────┬──────────────────┐ │
│  │ 输入框文本 │ 下拉选中  │ 展开/折叠状态      │ │
│  │(text())  │(currentIndex)│(_expanded)   │ │
│  └──────────┴──────────┴──────────────────┘ │
│         ↕ 读写：仅该 Widget 自身             │
└─────────────────────────────────────────────┘
```

#### 各层职责与生命周期

| 层级 | 存储位置 | 生命周期 | 谁可以写 | 谁可以读 |
|------|---------|---------|---------|---------|
| **Global** | `AppState` 单例 | 应用启动 → 关闭 | AppShell, Service | 所有层 |
| **Page** | `BasePage._state` dict | Page 创建 → 销毁 | Page 本身, 其 Section | Page 及其子组件 |
| **Component** | Widget 实例属性 | Widget 创建 → 销毁 | 仅自身 | 父组件可读取（不直接修改） |

#### 核心规则

```
✅ Component 可以读取 Global 和 Page State
✅ Page 可以读写自己的 Page State + 读取 Global State
❌ Component 不可以直接修改 Global State（必须通过信号向上传递）
❌ Page A 不可以读写 Page B 的 State（跨页通信走 Service 或 EventBus）
```

### 8.2 AppState — 全局状态容器

```python
# core/state/app_state.py

from PyQt6.QtCore import QObject, pyqtSignal

class AppState(QObject):
    """全局状态单例，管理跨页面共享的状态。

    设计原则：
    - 只存"真正需要跨页面共享"的数据
    - 每个字段变化都发射信号，支持响应式更新
    - 不持有任何 UI 引用（纯数据层）
    """

    # ====== 主题相关 ======
    theme_changed = pyqtSignal(str)              # 参数: preset_name (如 "cyberpunk")
    accent_color_changed = pyqtSignal(object)     # 参数: QColor

    # ====== 用户偏好 ======
    locale_changed = pyqtSignal(str)             # 参数: locale code ("zh_CN", "en_US")
    animation_enabled_changed = pyqtSignal(bool) # 低配机禁用动画

    # ====== 全局通知 ======
    global_notification = pyqtSignal(str, str)   # 参数: (level, message) level="info"|"warning"|"error"
    data_refresh_requested = pyqtSignal()        # 任意页面请求全局数据刷新

    def __init__(self):
        super().__init__()
        self._current_theme: str = "cyberpunk"
        self._locale: str = "zh_CN"
        self._animation_enabled: bool = True

    @property
    def current_theme(self) -> str:
        return self._current_theme

    def set_theme(self, name: str):
        """切换主题预设，发射 theme_changed 信号。"""
        if name != self._current_theme:
            self._current_theme = name
            self.theme_changed.emit(name)

    # ... 其他属性的 getter/setter 同理
```

**使用方式**：

```python
# 在 AppShell 中初始化（唯一创建点）
self.app_state = AppState()

# 在任意 Page/Widget 中访问
from core.state import app_state  # 模块级单例

def on_button_click(self):
    app_state.set_theme("daylight")   # 全局自动响应
```

### 8.3 跨层通信协议 — 信号槽命名规范

为了保证跨层通信的可读性和可调试性，信号命名必须遵循以下规范：

#### 8.3.1 信号命名规则

```
格式: {方向}_{对象}_{动作}

方向前缀:
  req_   → 请求（下层向上层请求数据/操作）
  res_   → 响应（上层向下层数据回调）
  notify_→ 通知（广播，无预期接收者）

示例:
  req_refresh_data     ← Section 向 Page 请求数据刷新
  res_data_updated     ← Page 向 Section 推送新数据
  notify_theme_changed ← AppState 广播主题变更
  notify_error         ← 任意层发出错误通知
```

#### 8.3.2 各层标准信号清单

**Page → AppShell（L2 → L0）**

| 信号 | 签名 | 触发时机 |
|------|------|---------|
| `notify_title_changed` | `(str)` | 页面标题需更新状态栏 |
| `notify_status_message` | `(str)` | 底部状态栏临时消息 |
| `req_show_dialog` | `(str, dict)` | 请求弹出对话框 |

**Section → Page（L3 → L2）**

| 信号 | 签名 | 触发时机 |
|------|------|---------|
| `req_data_refresh` | `(str)` | 请求刷新某类数据 |
| `notify_filter_changed` | `(dict)` | 筛选条件变更 |
| `notify_action_triggered` | `(str, dict)` | 用户执行了某个操作 |

**Widget → Section（L4/L5 → L3）**

| 信号 | 签名 | 触发时机 |
|------|------|---------|
| `value_changed` | `(Any)` | 输入值变更（通用） |
| `action_clicked` | `(str)` | 按钮点击（参数为 action_id） |
| `validation_error` | `(str, str)` | 校验失败（字段, 错误信息） |

**AppState → All Layers（广播）**

| 信号 | 签名 | 触发时机 |
|------|------|---------|
| `notify_theme_changed` | `(str)` | 用户切换主题 |
| `notify_locale_changed` | `(str)` | 语言切换 |
| `global_notification` | `(str, str)` | 需要展示的全局通知 |

### 8.4 数据流向图

以"用户在物品查询页搜索一个遗物"为例，完整数据流：

```
用户输入 "Forma"
    │
    ▼
[CyberLineEdit]  value_changed("Forma")          ← L5 组件状态
    │
    ▼ emit
[ItemSearchSection]  req_search({"keyword": "Forma"})  ← L3 接收并转发
    │
    ▼ emit
[ItemsPage]  收到 req_search → 调用 Service          ← L2 协调层
    │
    ▼ call
[ItemService.search("Forma")]                        ← 数据层（无UI依赖）
    │  返回 list[ItemDTO]
    ▼ return
[ItemsPage]  res_items_updated(items)                 ← L2 包装结果
    │
    ▼ emit
[ItemSearchSection]  更新列表数据                       ← L3 更新视图
    │
    ▼ setModel
[CyberListView]  显示搜索结果                           ← L4 渲染
```

**关键约束**：

```
数据永远向下流动（Service → Page → Section → Widget）
事件永远向上冒泡（Widget → Section → Page → AppShell）
禁止：Widget 直接调用 Service
禁止：Page 直接操作另一个 Page 的内部控件
允许：通过 AppState 广播全局事件
允许：通过 Service 层共享数据实例
```

### 8.5 EventBus — 解耦跨组件通信

对于不需要强类型绑定的场景（如"保存按钮被点击后，多个无关组件都需要响应"），使用轻量级事件总线：

```python
# core/state/event_bus.py

from PyQt6.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    """轻量级发布-订阅事件总线。

    适用场景：
    - 一对多通知（一个事件，多个订阅者）
    - 跨层级松耦合通信（发送者不知道接收者是谁）
    - 工具类功能触发（导出、打印、日志等）

    不适用场景：
    - 频繁触发的高频事件（用直连信号更高效）
    - 需要返回值的调用（用方法调用或 Future）
    """

    # ====== 预定义事件频道 ======
    # 数据类
    data_saved = pyqtSignal(str, object)      # (source_id, data)
    data_deleted = pyqtSignal(str, str)       # (source_id, item_id)

    # UI 类
    request_close_dialog = pyqtSignal()        # 关闭当前弹窗
    request_show_loading = pyqtSignal(bool)    # 显示/隐藏全局 loading
    request_scroll_to_top = pyqtSignal(str)    # (page_id) 滚动到顶部

    # 工具类
    export_requested = pyqtSignal(str, str)    # (format, data)
    log_requested = pyqtSignal(str, str)       # (level, message)

    def subscribe(self, signal, slot):
        """订阅事件。返回一个取消订阅的函数。"""
        signal.connect(slot)
        return lambda: signal.disconnect(slot)

# 模块级单例
event_bus = EventBus()
```

**使用示例**：

```python
# 订阅者（任意位置）
from core.state import event_bus

 unsub = event_bus.subscribe(
    event_bus.data_saved,
    lambda src, data: print(f"{src} 保存了数据")
)

# 取消订阅
unsub()

# 发布者（任意位置）
event_bus.data_saved.emit("items_page", item_list)
```

### 8.6 错误处理策略

#### 8.6.1 错误分级与处理路径

| 级别 | 示例 | 处理方式 | 用户感知 |
|------|------|---------|---------|
| **L1 组件级** | 输入校验失败、颜色解析异常 | Widget 内部 try-except + 恢复默认值 | 输入框红边提示 |
| **L2 页面级** | API 返回空数据、网络超时 | Page 捕获 → 展示空状态/重试按钮 | "暂无数据，点击重试" |
| **L3 全局级** | 配置文件损坏、Service 初始化失败 | AppShell 捕获 → 弹出错误 Dialog | 模态错误对话框 |
| **L4 致命级** | PyQt6 加载失败、Python 版本不符 | main.py 捕获 → 退出 + 日志 | 控制台错误信息 |

#### 8.6.2 错误冒泡模式

```python
# ✅ 正确：每层只处理自己能处理的错误，其余向上抛

class CyberLineEdit(CyberWidgetMixin, QLineEdit):
    def validate_input(self, text):
        try:
            result = do_validation(text)
            return result
        except ValidationError as e:
            self._show_validation_error(e.message)  # L1: 自己消化
            return None

class ItemSearchSection(QFrame):
    def on_search(self, keyword):
        try:
            items = self._item_service.search(keyword)
            self.res_items_updated.emit(items)
        except NetworkError as e:
            self.req_show_retry.emit(e.message)     # L2: 向上报告
        except Exception as e:
            event_bus.log_requested.emit("ERROR", str(e))  # L3: 记录日志

class ItemsPage(BasePage):
    def handle_error(self, error_msg):
        app_state.global_notification.emit("error", error_msg)  # L3: 全局通知
```

#### 8.6.3 禁止事项

```
❌ 在 paintEvent 中 try-except 吞掉异常（会导致静默渲染错误）
❌ 用 QMessageBox 弹出非致命错误（阻塞主线程）
❌ 在 Widget 中直接 sys.exit()（应由 AppShell 决定是否退出）
❌ 异常信息包含敏感信息（文件路径、API Key 等）直接展示给用户
```

---

## 9. 工程规范 — 文档体系与开发流程

> **核心原则**：文档必须与代码同步。过时的文档比没有文档更危险。
> 本章定义项目三层文档体系的职责边界、更新规则和同步仪式。

### 9.1 三层文档定义

| 层级 | 文件 | 性质 | 更新时机 | 维护者 | 用途 |
|------|------|------|---------|--------|------|
| **A. 契约文档** | 本文件 (`ui-framework-design.md`) | 规范（该做什么） | 重大架构变更时 | PM + 架构师 | 唯一权威设计规范 |
| **B. 落地文档** | `docs/architecture.md` | 记录（实际做了什么） | 每个 Phase 完成后 | 开发者 | 真实项目快照 |
| **C. API 文档** | 代码内 docstring + 类型注解 | 参考（怎么用） | 随每次代码提交 | 开发者 | IDE 可读的接口说明 |

### 9.2 各层职责边界

#### A 层（本文件）— 只写"应该怎样"

```
✅ 写: 设计原则、Token 规范、分层规则、命名约定、迁移策略、状态管理协议
✅ 写: 架构决策理由（为什么选这个方案）
❌ 不写: 具体实现行数、临时方案、某个文件的具体内容
❌ 不写: "计划在未来实现xxx"（那是 roadmap 不是规范）
```

**何时更新本文件**：
- 新增/修改架构决策（如新增 Widget 类型、修改信号命名规范）
- 发现设计缺陷需要修正
- Phase 结束时发现落地实现证明设计需调整

#### B 层 (`docs/architecture.md`) — 只写"实际做了什么"

```
✅ 写: 当前真实文件结构（tree 命令输出）
✅ 写: 已实现的公开接口清单（方法/信号/属性签名）
✅ 写: 模块依赖关系图（实际 import 关系）
✅ 写: 与设计文档的差异记录
❌ 不写: 计划、TODO、理想状态、设计意图
```

**何时更新**：每个 Phase 验收通过后，作为该 Phase 的收尾动作。

#### C 层（代码 docstring）— 让代码自己说话

```python
class TokenResolver:
    """Design Token 引用解析器。

    支持 @引用链、lighten/darken/opacity 函数变换。
    四层模型: Raw → Alias → Semantic → Component

    Usage::
        r = TokenResolver(raw_data)
        r.resolve("components.button.solid.fill")  → QColor(#FFE600)

    See Also:
        ui-framework-design.md §2.2 Token 引用解析机制

    Raises:
        TokenResolveError: 引用不存在或超过最大深度(16层)
    """
```

### 9.3 差异追踪机制

当实际实现偏离本设计文档时，在 `docs/architecture.md` 记录：

```markdown
## 设计偏差日志

| 日期 | 设计章节 | 设计说 | 实际做了 | 原因 | 影响 |
|------|---------|--------|---------|------|------|
| 06-09 | §2.4 | corner_size 在 components 层 | 移到 space tokens | 关注点分离更合理 | 需反向更新§2.4 |
```

**规则**：
- 发现偏差时立即记录，不允许静默偏移
- 合理改进 → 下个 Phase 反向更新本文件（A层）
- 偷懒妥协 → 标记技术债务，排期修复

### 9.4 Phase 文档同步仪式

每个 Phase 验收通过后的标准收尾流程：

```
1️⃣  更新 docs/architecture.md
    ├── 替换文件结构为当前 tree 输出
    ├── 补充本阶段实现的接口清单
    └── 记录本阶段的设计偏差（如有）

2️⃣  检查是否需要反向更新 ui-framework-design.md
    ├── 有架构变更？→ 更新对应章节
    └── 无变更？→ 不动（保持稳定）

3️⃣  提交（代码 + 文档一起）
    git commit -m "Phase N complete: {做了什么}

    docs: update architecture.md (structure + interfaces)
    docs: sync design spec §X.X ({如有变更})"
```

### 9.5 入口策略

新系统使用独立入口文件 `app_shell.py`，与旧系统 `main.py` 完全隔离：

| 维度 | 旧系统 | 新系统 |
|------|--------|--------|
| 入口文件 | `main.py` | `app_shell.py` |
| 启动方式 | `python main.py` | `python app_shell.py` |
| 共享代码 | — | `core/services/`, `data/` |
| 切换方式 | Phase 3 后环境变量 `USE_LEGACY_UI=1` 可回退 | 默认入口 |

**开发期**：两个入口可独立运行，互不干扰。

---

## 附录 A: 颜色函数规范

| 函数 | 签名 | 示例 | 说明 |
|------|------|------|------|
| `lighten` | `lighten(color, percent)` | `lighten(#0E0E24, 10%)` | 提亮，percent ∈ [0, 100] |
| `darken` | `darken(color, percent)` | `darken(#0E0E24, 5%)` | 加深 |
| `opacity` | `opacity(color, alpha)` | `opacity(#00FFFF, 50%)` | 设置透明度 alpha ∈ [0, 1] |
| `mix` | `mix(color_a, color_b, weight)` | `mix(#FFF, #000, 0.3)` | 混合两色，weight ∈ [0, 1] |
| `contrast` | `contrast(color, ratio)` | `contrast(#0E0E24, 4.5)` | 调整至目标对比度 |

实现基于 HSL 色彩空间运算，避免 RGB 直接插值导致的色偏问题。

## 附录 B: 切角几何参数参考 + 多重继承注意事项

### B.1 切角几何参数参考

根据截图目测估算的参数值：

| 元素 | 切角大小 | 边框宽度 | 外发光半径 | 备注 |
|------|---------|---------|-----------|------|
| 大面板 (Dialog) | 12-14px | 1-1.5px | 0-6px | 参考图1、图5 |
| 按钮 (实心黄) | 8px | 1px | 0px | 参考图4 |
| 按钮 (描边青) | 8px | 1.5px | 4px | 参考图1、图3 |
| 卡片/列表项 | 6-8px | 1px | 0px | 参考图2、图3 |
| 输入框 | 4-6px | 1px | 0px | 推测值 |
| 导航项 | 4-6px | 0-1px | 0px | 参考图2 左侧 |

### B.2 CyberWidgetMixin 多重继承注意事项

本项目使用 **Mixin 模式** 实现组件复用，而非传统的单基类继承。这是最容易踩坑的地方，请务必理解以下规则。

#### 基本继承结构

```python
class CyberWidgetMixin:
    """赛博风格混入类 — 提供切角绘制、状态机、Token 访问能力。
    不继承 QWidget，不能单独实例化。"""

class CyberButton(CyberWidgetMixin, QPushButton):
    """切角按钮 = Mixin 的皮肤 + QPushButton 的交互能力"""

class CyberInput(CyberWidgetMixin, QLineEdit):
    """切角输入框 = Mixin 的皮肤 + QLineEdit 的编辑能力"""

class CyberPanel(CyberWidgetMixin, QFrame):
    """切角面板 = Mixin 的皮肤 + QFrame 的容器能力"""
```

#### 规则 1：__init__ 必须显式调用目标基类

**错误写法**（会导致 QPushButton 未初始化，点击无反应、文字不显示）：

```python
class CyberButton(CyberWidgetMixin, QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)   # ⚠️ 调用的是谁？
```

**正确写法**（明确指定要初始化的基类）：

```python
class CyberButton(CyberWidgetMixin, QPushButton):
    def __init__(self, text="", parent=None):
        QPushButton.__init__(self, text, parent)   # ✅ 明确初始化 QPushButton
        # Mixin 没有 __init__ 需要调用（它只有方法和类属性）
```

**原因**：`super()` 在多重继承中按 MRO（方法解析顺序）查找。Python 3 的 MRO 是 C3 线性化算法，`CyberButton` 的 MRO 为：
```
CyberButton → CyberWidgetMixin → QPushButton → QWidget → ...
```
所以 `super().__init__()` 实际调用的是 `CyberWidgetMixin.__init__`（如果存在的话），**不是** `QPushButton.__init__`。

#### 规则 2：事件处理必须调用 super()

```python
class CyberButton(CyberWidgetMixin, QPushButton):

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._set_state("pressed")
        super().mousePressEvent(event)   # ✅ 必须！让 QPushButton 处理点击信号发射

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._set_state("hover")
        super().mouseReleaseEvent(event) # ✅ 必须！让 QPushButton 处理释放信号

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return:
            self.click()                   # 回车触发点击
        super().keyPressEvent(event)      # ✅ 必须！让 QPushButton 处理快捷键

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_chamfered_bg(painter)   # ① 自绘：切角背景
        super().paintEvent(event)          # ✅ ② 必须在最后！让 QPushButton 画文字
```

**忘记调用的后果**：
- 不调 `super().mousePressEvent` → 点击按钮不会发射 `clicked` 信号
- 不调 `super().paintEvent` → 按钮上没有文字显示
- 不调 `super().keyPressEvent` → 快捷键失效

#### 规则 3：属性名冲突避免

Mixin 和 Qt 基类可能有同名属性。已知安全列表：

| 属性名 | Mixin 用途 | Qt 基类用途 | 冲突？ |
|--------|-----------|------------|-------|
| `_state` | 状态字符串 | 无 | 安全 |
| `_path_cache` | 路径缓存 | 无 | 安全 |
| `_cache_rect_size` | 缓存键 | 无 | 安全 |
| `_hovered` / `_pressed` | 状态标志 | 部分控件内部用 | **避免**，改用 `_cyber_hovered` |

**建议**：Mixin 的私有属性统一加 `_cyber_` 前缀以避免与任何 Qt 内部属性冲突。

#### 规则 4：新增组件时的模板

复制以下模板，只修改类名和继承目标：

```python
from PySide6.QtWidgets import {TARGET_QT_CLASS}
from core.widgets.base import CyberWidgetMixin

class Cyber{NAME}(CyberWidgetMixin, {TARGET_QT_CLASS}):
    """一句话描述这个组件做什么"""

    def __init__(self, {INIT_ARGS}, parent=None):
        {TARGET_QT_CLASS}.__init__(self, {PASS_INIT_ARGS}, parent)
        h = self.space("height.{SIZE_KEY}")
        self.setFixedHeight(h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_chamfered_bg(painter)
        # 如需额外自绘内容，在这里添加
        super().paintEvent(event)
```

## 附录 C: 专业设计审查 — 补充设计维度

> 本附录从 **UI 设计师** 和 **产品经理** 的双重视角，审查前 8 章未覆盖的设计盲区。
> 这些内容不直接写代码，但决定了框架的上限和长期可维护性。

### C.1 交互状态完整机（Interaction State Machine）

前文定义了 `semantic.state` 的 6 种颜色态，但一个**专业级的组件**需要的状态远不止这些：

#### C.1.1 全状态矩阵

每个交互组件应覆盖以下 **12 种状态**：

| 状态 | 触发条件 | 视觉变化 | 已有？ |
|------|---------|---------|--------|
| `default` | 初始渲染 | 基础样式 | ✅ |
| `hover` | 鼠标悬停 | 颜色/发光微变 | ✅ |
| `focused` | 键盘聚焦(Tab) | Focus Ring + 发光 | ⚠️ 只有颜色 |
| `pressed` | 鼠标按下 | 下压效果(内阴影) | ⚠️ 只有颜色 |
| `active` | 激活/选中态 | 反色填充 | ✅ |
| `disabled` | 禁用 | 降低透明度 + 去发光 | ✅ |
| `loading` | 异步操作中 | Spinner 替换文字/图标 | ❌ 缺失 |
| `error` | 校验失败 | 红色边框 + 抖动动画 | ❌ 缺失 |
| `success` | 操作成功 | 绿色闪烁后恢复 | ❌ 缺失 |
| `empty` | 无数据 | 占位图 + 提示文案 | ❌ 缺失 |
| `readonly` | 只读 | 去边框 + 背景变淡 | ❌ 缺失 |
| `drag_over` | 拖拽悬停 | 边框高亮 + 区域高亮 | ❌ 缺失 |

**缺失状态的 Token 定义**：

```yaml
components:
  button:
    # ... 已有 solid/outlined/ghost ...
    loading:
      spinner_color: "@accent.secondary"
      spinner_size:   16
      text_opacity:   0.5        # 按钮文字半透明，表示不可点
    error:
      border:       "@semantic.danger"
      border_glow:  "@semantic.danger"
      shake_offset: 4             # 抖动像素距离
    success:
      flash_color:  "@semantic.success"
      flash_duration: 600         # ms

  input:
    # ... 已有 ...
    error:
      border:       "@semantic.danger"
      error_icon:   true           # 右侧显示错误图标
      error_msg_bg: "opacity(@semantic.danger, 15%)"
    readonly:
      bg:          "opacity(@bg.raised, 70%)"
      border:      "@border.none"
      text:        "@text.disabled"

  list_item:
    empty:
      icon:        "cloud_off"     # 图标名
      text:        "暂无数据"       # 默认文案（可被调用方覆盖）
      text_color:  "@text.tertiary"
      action_text: "刷新"          # 空状态操作按钮文案
    drag_over:
      bg:          "opacity(@accent.secondary, 10%)"
      border:      "@accent.primary"
      border_style: "dashed"       # 虚线
```

#### C.1.2 状态转换规则

```
                    ┌─────────┐
                    │ default │
                    └────┬────┘
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         ┌────────┐ ┌────────┐ ┌────────┐
         │ hover  │ │focused │ │disabled│
         └───┬────┘ └───┬────┘ └────────┘
             │          │
         ┌───▼───┐  ┌──▼─────┐
         │pressed│  │active  │
         └───┬───┘  └──┬─────┘
             │         │
             ▼         ▼
        ┌────────┐ ┌────────┐
        │loading │ │success │
        └────────┘ └────────┘

特殊转换：
  • focused → error (输入校验失败)
  • any → disabled (外部禁用)
  • loading → success / error (异步完成)
  • default → empty (数据加载完成但为空)
```

**关键规则**：任何状态进入 `disabled` 后只能通过外部代码解除；`loading` 期间忽略 hover/focused/pressed。

---

### C.2 动效系统（Motion System）

前文只定义了 `duration.*` 的毫秒数，但专业动效还需要更多维度：

#### C.2.1 缓动曲线库 (Easing Catalog)

```yaml
motion:
  easing:
    # 标准曲线
    standard:    "OutCubic"       # 大多数过渡（默认）
    decelerate:  "OutQuart"       # 进入动画（元素出现）
    accelerate:  "InCubic"        # 退出动画（元素消失）
    spring:      "OutElastic(0.6, 25)"  # 弹性反馈（按钮按压回弹）

    # 特殊曲线
    sharp_in:    "InQuart"        # 强调开始（如进度条启动）
    sharp_out:   "OutQuart"       # 强调结束（如下拉展开到位）
    emphasize:   "InOutCubic"     # 两端强调（页面切换）

  # 组件级动效规格
  component:
    button:
      hover:       { duration: 80,  easing: "standard" }
      press:       { duration: 60,  easing: "decelerate" }
      focus_ring:  { duration: 150, easing: "standard" }
      glow_pulse:  { duration: 2000, easing: "InOutSine", loop: true }

    panel:
      appear:      { duration: 250, easing: "decelerate" }
      disappear:   { duration: 150, easing: "accelerate" }

    dialog:
      enter:       { duration: 250, easing: "OutBack", scale_from: 0.95 }
      exit:        { duration: 150, easing: "accelerate" }

    nav_item:
      switch:      { duration: 150, easing: "standard" }
      indicator:   { duration: 200, easing: "decelerate" }  # 滑块移动

    tooltip:
      show:        { duration: 100, easing: "decelerate", delay: 300 }  # 延迟显示
      hide:        { duration: 80,  easing: "accelerate" }

    list_item:
      appear:      { duration: 200, easing: "standard", stagger: 30 }  # 逐行入场
      hover:       { duration: 80,  easing: "standard" }

    error_shake:
      shake:       { duration: 350, easing: "InOutSine", amplitude: 4 }

    success_flash:
      flash:       { duration: 500, easing: "standard" }
```

#### C.2.2 编排规则 (Choreography)

多元素同时动画时的协调规则：

```
规则 1: 入场顺序 — 从外到内、从上到下
  L0 Shell → L1 Nav → L2 Page → L3 Sections → L4 Cards → L5 Atoms
  每层间隔 stagger = 30ms

规则 2: 退场顺序 — 与入场相反（先子后父）
  或: 整体同时退场（更快感知）

规则 3: 同级元素 — 自然交错
  列表项逐行入场 (stagger 30ms)
  表单字段从左到右、从上到下

规则 4: 功能性动画 > 装饰性动画
  loading spinner 必须立即显示
  glow pulse 可以延迟

规则 5: 用户触发 > 自动触发
  按钮 hover 响应 ≤ 100ms
  页面切换可以 200-250ms
```

#### C.2.3 减弱动效 (Reduced Motion)

```yaml
motion:
  reduced_motion:
    enabled_by: "system_preference"  # 读取 OS 设置: QGuiApplication.styleHints().useAnimationsEnabled()
    fallback:
      duration:      0               # 所有动画时长归零
      glow_loop:     false           # 关闭发光脉冲
      stagger:       0               # 取消交错入场
      dialog_scale:  false           # 对话框无缩放
      shake:         false           # 错误无抖动
      replace_with:  "opacity_crossfade"  # 用透明度渐变替代位移
```

---

### C.3 可访问性 (Accessibility)

你的工具面向 Warframe 玩家群体，可能包含视力障碍用户。以下是必须考虑的 a11y 维度：

#### C.3.1 颜色对比度标准

```yaml
a11y:
  contrast:
    # WCAG 2.1 AA 标准
    aa_normal:    4.5:1    # 正文文字（13px+）
    aa_large:     3:1      # 大号文字（18px+）或粗体
    aaa_normal:   7:1      # AAA 级别（推荐）

  # 当前 cyberpunk 预设的自查结果（需在实现时验证）
  checks:
    - pair: ["#E8ECFF", "#08081A"]    # 主文字 on 背景
      expected: "≥ 4.5:1"
      note: "浅色深底，应该达标"
    - pair: ["#FFE600", "#0E0E24"]    # 黄色按钮文字 on 按钮背景
      expected: "≥ 3:1 (large text)"
      note: "黄色 on 深蓝灰，需实测"
    - pair: ["#6677AA", "#0E0E24"]    # 弱文字 on 卡片背景
      expected: "≥ 4.5:1"
      note: "⚠️ 可能不达标！这是最常见的 a11y 问题"
    - pair: ["#444466", "#0A0A18"]    # 禁用文字 on 禁用背景
      expected: "≥ 3:1"
      note: "⚠️ 极可能不达标"

  # 不依赖颜色的信息传达
  color_independence:
    rule: "关键信息不能仅靠颜色区分"
    examples:
      - 遗物状态: 除红/绿色外，还需图标 ✓/✗ 或 文字"已入库"/"可获得"
      - 按钮主次: 除颜色差异外，还需边框粗细或大小差异
      - 错误提示: 除红色外，还需图标 + 文字说明
      - 导航选中: 除高亮背景外，还可加左侧指示条
```

#### C.3.2 键盘导航规范

```yaml
a11y:
  keyboard:
    tab_order: "逻辑顺序 = 视觉顺序（从上到下、从左到右）"
    focus_visible:
      style: "focus_ring (token: border.focus)"
      offset: 2                    # Focus ring 与控件间隙
      min_size: "覆盖整个控件 bounding box"

    shortcuts:
      escape:  "关闭弹窗/取消操作/退出模式"
      enter:   "确认默认按钮"
      tab:     "焦点移到下一控件"
      shift_tab: "焦点移到上一控件"
      arrow_ud: "列表/下拉框内移动"
      arrow_lr: "单选组/标签页内移动"

    # 焦点陷阱 (Focus Trap)
    modal_trap:
      enabled: true                # 对话框打开时 Tab 不逃逸
      auto_return: true            # Escape/关闭时焦点回到触发按钮
```

#### C.3.3 最小触控目标

即使你的应用是桌面端，也要保证足够的点击区域：

```yaml
a11y:
  target_size:
    min_tap:    32x32px           # WCAG 最小点击目标
    min_touch:  44x44px           # 移动端标准（触摸屏笔记本适用）
    recommendation: "桌面端 ≥ 28x28px，所有交互元素的 clickable area"
```

---

### C.4 图标系统 (Icon System)

当前项目有 SVG 图标散落在 [assets/icons/](../assets/icons/) 和 [icon/](../icon/) 目录，缺乏系统性管理：

#### C.4.1 图标分类与命名

```
icons/
├── ui/                    # UI 操作类图标（纯功能性）
│   ├── close.svg          #   关闭
│   ├── search.svg         #   搜索
│   ├── add.svg            #   新增
│   ├── delete.svg         #   删除
│   ├── edit.svg           #   编辑
│   ├── copy.svg           #   复制
│   ├── refresh.svg        #   刷新
│   ├── settings.svg       #   设置
│   ├── info.svg           #   信息
│   ├── warning.svg        #   警告
│   ├── error.svg          #   错误
│   ├── success.svg        #   成功
│   ├── chevron_left.svg   #   左箭头
│   ├── chevron_right.svg  #   右箭头
│   ├── chevron_up.svg     #   上箭头
│   ├── chevron_down.svg   #   下箭头
│   └── more_horiz.svg     #   更多菜单
│
├── nav/                   # 导航图标（对应 10 个导航项）
│   ├── toggles.svg
│   ├── status.svg
│   ├── items.svg
│   ├── triggers.svg
│   ├── prices.svg
│   ├── hotkeys.svg
│   ├── theme.svg
│   ├── reset.svg
│   ├── preset.svg
│   └── about.svg
│
├── action/                # Overlay 功能按钮图标
│   ├── check_status.svg
│   ├── query_parts.svg
│   ├── query_price.svg
│   └── translate.svg
│
├── game/                  # 游戏相关图标
│   ├── gold.svg           #   黄金遗物
│   ├── silver.svg         #   白银遗物
│   ├── copper.svg         #   青铜遗物
│   ├── vaulted.svg        #   已入库
│   └── available.svg      #   可获得
│
└── brand/                 # 外部品牌图标
    ├── bilibili.svg
    └── github.svg
```

#### C.4.2 图标尺寸规范

```yaml
icon_system:
  # 与 space.icon token 对齐
  sizes:
    inline:    12    # 行内图标（文字旁的小标记）
    small:     16    # 按钮内图标、列表项图标
    medium:    20    # 导航栏图标（当前默认值）
    large:     24    # 功能按钮图标（Overlay）
    xlarge:    32    # 状态指示、空状态插图

  # 视觉风格统一
  style:
    stroke_width: 1.5        # 描边宽度（线性图标）
    stroke_cap: "round"      # 圆角端点
    stroke_join: "round"     # 圆角连接
    grid_size: 24            # 设计网格基准（所有图标在 24x24 网格内设计）

  # 图标状态变体
  variants:
    color:     "{token_color}"   # 主色（跟随 token）
    dimmed:    "opacity(40%)"    # 禁用态
    active:    "{accent}"        # 激活态（不同颜色）
```

#### C.4.3 Icon Font vs SVG 选择

| 方案 | 优点 | 缺点 | 推荐 |
|------|------|------|------|
| Icon Font | 加载快、CSS 着色方便 | 无法做多色、模糊、低 DPI 锯齿 | ❌ |
| SVG 文件 | 矢量无损、支持多色、可 CSS 控制 | 需要逐一管理文件 | ✅ **采用** |
| QPixmap 内嵌 | 打包简单、无外部依赖 | 不可缩放、切角风格难适配 | ❌ |

**结论**：继续使用 SVG，但建立统一的 `IconLoader` 接口：

```python
# 统一图标访问接口（替代散落的 get_icon / get_nav_icon / get_action_icon）
from core.icons import icons

# 使用方式
icon = icons.get("ui/close", size=16, color=tokens.color("text.primary"))
nav_icon = icons.get("nav/hotkeys", size=20)
game_icon = icons.get("game/gold", size=24)
```

---

### C.5 暗/亮模式策略 (Dark/Light Mode Strategy)

你已有 cyberpunk(暗) / daylight(亮) 两个预设，但它们的关系需要明确：

#### C.5.1 不是简单的颜色反转

```
❌ 错误做法: daylight = cyberpunk 的反色（自动取反）
✅ 正确做法: daylight 是独立设计的配色方案
```

**暗→亮需要注意的差异点**：

| 维度 | Cyberpunk (暗) | Daylight (亮) | 处理策略 |
|------|---------------|--------------|---------|
| **发光效果** | 霓虹外发光是核心特征 | 发光在亮底上几乎看不见 | 亮模式下 glow_opacity 降为 0 或改为 subtle shadow |
| **玻璃拟态** | 半透明 + 模糊很有效 | 白色毛玻璃容易看起来脏 | 亮模式用实色 + 细边框代替 |
| **切角造型** | 完全保留 | 完全保留 | 这是品牌识别，不受明暗影响 |
| **文字对比** | 浅色字 on 深底（天然高对比） | 深色字 on 浅底（需注意灰色阶） | daylight 的 neutral 阶梯要重新调校 |
| **强调色使用** | 黄/青作为"光"很自然 | 黄/青在白底上可能刺眼 | 亮模式降低饱和度或改用更沉稳的色调 |
| **卡片层级** |靠亮度差异分层明显 | 亮模式下层次感弱 | 亮模式增加 border 使用和细微阴影 |

#### C.5.2 共享结构 + 差异化 surface

```yaml
# daylight.yaml 中只需要重新定义 raw 层
# alias / semantic / components / space 层全部继承自共享基类！

_meta:
  inherits: "_base"              # ★ 继承共享的结构定义
  name: "daylight"

raw:
  brand:                          # 品牌色降低饱和度
    yellow:  "#D4A000"            # 更深的金（白底上不用太亮）
    cyan:    "#0066AA"            # 更深的蓝
    magenta:"#A02060"
    orange:  "#C05000"
    red:     "#CC0033"
    green:   "#1A8040"

  neutral:                        # 反转
    white:   "#1A1A2E"           # 主文字变深
    light:   "#4A4A6A"
    medium:  "#8888AA"
    dark:    "#B0B0CC"
    black:   "#F5F6FA"           # 背景变浅

  surface:
    base:    "#F5F6FA"
    raised:  "#FFFFFF"
    overlay: "#FFFFFF"

# 亮模式的组件覆盖（仅列出与暗模式不同的部分）
components:
  panel:
    glow_opacity: 0               # 亮模式无发光
    shadow: "shadow.sm"           # 用阴影代替发光

  button:
    solid:
      glow_size: 0                # 亮模式按钮无外发光
    outlined:
      glow_size: 0

  dialog:
    shadow_blur: 40               # 亮模式加强阴影
    shadow_opacity: 0.15
```

---

### C.6 响应式与窗口策略 (Responsive & Window)

虽然是桌面应用，但仍需定义窗口行为：

#### C.6.1 窗口尺寸约束

```yaml
window:
  # ManagementPanel (主窗口)
  main:
    min_width:    900             # 最窄不能低于此值（导航140 + 内容760）
    min_height:   700
    default_width: 1100
    default_height: 800
    max_width:    null            # 不限制最大宽度（用户可拉伸）

  # Overlay (全屏覆盖层)
  overlay:
    mode: "fullscreen"            # 始终全屏

  # Dialog (对话框)
  dialog:
    min_width:    360
    max_width:    560
    width_ratio:  0.4             # 相对于父窗口的比例
    max_height:   "80vh"          # 不超过视口 80%

  # Market Query (独立窗口)
  market_query:
    min_width:    600
    min_height:   450
```

#### C.6.2 内容自适应规则

```
窗口变宽时（≥ 1200px）:
  导航栏: 保持 140px 固定宽
  内容区:  扩展并居中（max-width: 900px + 左右 margin auto）
  卡片网格: 单列 → 双列（如果内容允许）

窗口变窄时（900 ~ 1200px）:
  标准布局，内容区填满可用空间

窗口接近最小时（≈ 900px）:
  导航栏可收缩至 120px（图标-only 模式，隐藏文字）
  内容区 padding 收紧: lg → md
  按钮文字可省略（只留图标）
```

#### C.6.3 DPI / 缩放处理

```yaml
dpi:
  strategy: "logical_coordinates"  # Qt 逻辑坐标系（已在用）
  base_dpi: 96                     # 基准 DPI
  # 所有 token 值是逻辑像素，Qt 自动映射到物理像素
  # 但以下值需要在运行时乘以 scaleFactor:
  scale_aware:
    - corner_size                  # 切角随 DPI 放大
    - border_width                 # 边框随 DPI 放大
    - glow_size                    # 发光半径随 DPI 放大
    - shadow_blur                  # 模糊半径随 DPI 放大
    - icon sizes                   # 图标随 DPI 放大
  # 以下值不需要缩放（相对比例）:
  scale_fixed:
    - opacity                      # 透明度不受 DPI 影响
    - duration                     # 时长不受 DPI 影响
    - font size (Qt 字体自动处理)  # 字体由 Qt DPI 缩放管理
```

---

### C.7 文案与微复制 (Microcopy)

UI 中的每一个文字都是产品体验的一部分。需要统一的文案规范：

#### C.7.1 按钮文案约定

```
格式规则:
  ✅ 动词 + 名词    "返回挑战界面"、"确认目标"、"重新挑战"
  ✅ 纯动词        "前往"、"刷新"、"保存"、"取消"
  ✅ 动词 + 方向    "上一步"、"下一步"、"返回"
  ❌ 名词 alone    "挑战界面" (应该是 "前往挑战界面")
  ❌ 句子式        "你是否要返回?" (应该是 "确认返回")

长度限制:
  主要按钮(CTA):  2~6 个汉字
  次要按钮:       2~4 个汉字
  图标按钮:       无文字或 1~2 个汉字
  导航项:         2~4 个汉字
```

#### C.7.2 状态消息模板

```yaml
microcopy:
  empty_states:
    no_items:       "暂无物品数据，请先更新数据库"
    no_results:     "没有找到匹配的物品"
    no_triggers:    "尚未配置辅助触发器"
    no_hotkeys:     "尚未设置快捷键"

  error_states:
    network_error:  "网络连接失败，请检查代理设置"
    db_corrupt:     "数据库损坏，请在「紧急重置」中修复"
    ocr_failed:     "识别失败，请确保游戏窗口可见"
    update_failed:  "更新失败: {error_detail}"

  confirmations:
    reset_theme:    "确定要重置所有主题设置吗？此操作不可撤销。"
    clear_cache:    "确定要清除价格缓存吗？"
    exit_app:       "确定要退出 WARFRAME-RELIC 吗？"

  success_messages:
    db_updated:     "数据库更新完成，共 {count} 条记录"
    theme_saved:    "主题设置已保存"
    hotkey_saved:   "快捷键已更新: {hotkey_name}"

  loading_messages:
    fetching_price: "正在查询市场价格..."
    updating_db:    "正在更新数据库... ({percent}%)"
    recognizing:    "正在识别画面..."
```

#### C.7.3 语气指南

```
整体语气: 专业但不冷漠，有游戏氛围但不轻浮

场景语气:
  • 正常操作: 中性、简洁  → "数据库已就绪"
  • 成功反馈: 轻度积极    → "更新完成！" （不过度夸张）
  • 错误提示: 清晰、可操作  → "网络超时，点击重试" （不说"糟糕!"）
  • 危险操作: 严肃、明确    → "此操作将清除所有数据" （不加波浪号~）
  • 游戏相关: 可适度活泼    → "Tenno，准备好了吗？" （仅在 about/splash 页面）
```

---

### C.8 性能预算 (Performance Budget)

自绘组件比原生 QSS 控件更消耗 CPU/GPU，需要设定性能红线：

```yaml
performance:
  budget:
    # 帧率目标
    target_fps: 60                 # 动画期间
    static_fps: 0                  # 静态时不重绘（0 = 按需）

    # paintEvent 耗时上限
    paint_max_ms: 8                # 单次绘制不超过 8ms（留给 ~16ms/帧）
    paint_complex_widget_ms: 16    # 复杂组件（Dialog 带 blur）放宽到 16ms

    # 内存
    max_pixmap_cache_mb: 50        # 图片缓存上限
    max_path_cache_count: 200       # 切角路径缓存数量

  # 性能优化策略
  optimization:
    path_caching: true             # 切角路径缓存（已规划）
    dirty_region: true             # 只重绘变化区域（QRegion）
    update_batching: true          # 批量合并 update() 调用
    blur_fallback:                # 低端机器降级策略
      gpu_supported: "QGraphicsBlurEffect"  # GPU 加速模糊
      cpu_fallback: "downscale + simple blur"  # CPU 降采样模糊
      minimal: "semi-transparent overlay only"  # 最差情况只用半透明遮罩

    animation_throttling:
      window_minimized: "pause_all"      # 最小化时暂停所有动画
      window_background: "reduce_fps_to_10"  # 后台时降到 10fps
      low_battery: "disable_glow"        # 低电量时关闭发光效果
```

---

### C.9 国际化布局考量 (i18n Layout)

你的项目已有多语言支持 (`dict.zh.json` / `dict.en.json`)，新 UI 必须考虑文本膨胀：

#### C.9.1 文本膨胀系数

```
中文 → 英文:  文本长度约 ×1.5~2.0
中文 → 德语:  文本长度约 ×1.8~2.5 (复合词非常长)
中文 → 日语:  文本长度约 ×1.2~1.5

影响范围:
  • 按钮宽度: 中文"确认"(2字=26px) →英文"Confirm"(7字≈60px)
  • 导航栏:   中文"功能开关"(4字=52px) →英文"Toggles"(7字≈55px)
  • 对话框标题: 可能从单行变为两行
  • 表单标签:  左对齐时右侧输入框位置不一致
```

#### C.9.2 布局应对策略

```yaml
i18n_layout:
  buttons:
    min_width: 80                 # 最小按钮宽度（容纳英文）
    max_width: 200                # 最大宽度（防止过长文字）
    text_elide: "middle"          # 超长文字中间省略 "Con...rm"

  nav_items:
    width_mode: "fixed"           # 固定宽度
    text_elide: "right"           # 超长文字右侧省略
    tooltip_on_elide: true        # 省略时显示完整文字 tooltip

  dialogs:
    title_max_lines: 2            # 标题最多 2 行
    body_text: "wrap"             # 正文自动换行
    min_dialog_width: 400         # 英文环境下对话框加宽

  forms:
    label_alignment: "top"        # 标签在输入框上方（推荐，避免左右不对齐）
                                  # 如必须左对齐: label 区域预留足够宽度
```

---

### C.10 设计走查清单 (Design Review Checklist)

每次实现一个新组件或修改一个页面后，用此清单自查：

```
□ 颜色
  □ 所有颜色来自 token，无硬编码
  □ hover/focused/disabled 三态都有定义
  □ 对比度满足 WCAG AA (≥ 4.5:1 for body text)
  □ 不只靠颜色传达信息（形状/图标/文字辅助）

□ 尺寸
  □ 所有尺寸是 4 的倍数
  □ 高度取自 height.* token（不在代码里写数字）
  □ 间距符合所在层的 spacing 规则
  □ 点击区域 ≥ 28×28px

□ 交互
  □ 支持 Tab 键聚焦
  □ Focus 状态清晰可见
  □ Enter 激活默认操作，Escape 取消/关闭
  □ Disabled 态下不响应任何输入
  □ Loading 态有视觉反馈（spinner 或骨架屏）
  □ Error 态有明确的错误信息（不只是红边框）

□ 动效
  □ 过渡时长取自 duration.* token
  □ 使用了正确的缓动曲线
  □ 尊重系统的 "减弱动效" 设置
  □ 动画不会导致布局抖动（layout thrashing）

□ 层级
  □ 组件放在了正确的 L0-L5 层级
  □ 只引用了同层及以下的 token
  □ 没有越级操作其他层组件的样式

□ 文案
  □ 按钮文案是动词开头
  □ 没有暴露技术术语给最终用户
  □ 空状态有友好的引导文案
  □ 错误信息包含解决建议
  □ **所有用户可见字符串通过 _copy() / copy() 从 YAML copy token 获取**
  □ **没有硬编码的中文字符串或英文 UI 文本**

□ 性能
  □ paintEvent 内无对象分配（QColor/QPen 在外部创建）
  □ 切角路径有缓存
  □ 静态状态下不触发不必要的 repaint

□ 国际化
  □ 英文文本膨胀后不溢出/不换行异常
  □ 图标不包含文字
```

---

## 附录 E: 设计决策记录 (ADR)

> Architecture Decision Record — 记录重大设计决策及其理由，便于未来回顾。

### ADR-001: 继承原生控件 + QPainter 最小化自绘（而非全部自绘或纯 QSS）

- **日期**: 2026-06-09
- **状态**: 已采纳
- **决策**: 继承 Qt 原生控件（QPushButton / QLineEdit / QFrame 等），仅通过 `paintEvent` 覆盖 QSS 无法实现的视觉效果（切角、外发光、角落装饰）。Qt 原生能力（文字渲染、光标/选中、撤销重做、复制粘贴、Tab 导航等）全部由父类 `super()` 提供，绝不重复造轮子。
- **理由**:
  1. 目标风格的切角矩形 (chamfered corner) 是 QSS 天然无法实现的 → 需要 QPainter 补充
  2. 霓虹外发光 (outer glow) 需要多层绘制，QSS 的 box-shadow 不支持 → 需要 QPainter
  3. 角落装饰线 (corner decor marks) 是完全自定义图形 → 需要 QPainter
  4. 但 Qt 的文字引擎、输入编辑器、事件分发系统已经非常成熟，自行重写是纯粹浪费
  5. QSS 在各平台渲染不一致，但 QPainter 保证跨平台一致性
- **被否决的方案**:
  - ❌ 纯 QSS 方案：无法实现切角和发光，视觉上限锁死
  - ❌ 全部自绘（从 QWidget 零开始）：需要自己实现光标、选中、撤销、复制粘贴...开发量暴增且容易出 bug
- **架构**: 采用 Mixin 模式 — `CyberWidgetMixin` 提供切角/发光/Token 能力，通过多重继承与具体 Qt 控件组合：
  - `CyberButton(CyberWidgetMixin, QPushButton)` — 按钮能力来自 QPushButton，皮肤来自 Mixin
  - `CyberInput(CyberWidgetMixin, QLineEdit)` — 编辑能力来自 QLineEdit，皮肤来自 Mixin
  - `CyberPanel(CyberWidgetMixin, QFrame)` — 容器能力来自 QFrame，皮肤来自 Mixin
- **代价**:
  1. 需要理解 Qt 的绘制管线（style option / drawControl / PE_ / CE_ 枚举）
  2. 多重继承需要注意 MRO（方法解析顺序），`__init__` 需显式调用目标基类
  3. 失去了对原生样式的完全控制权（部分外观由 Qt 内部决定）
- **缓解措施**:
  - 通过 `CyberWidgetMixin` 统一封装通用逻辑，子类只需关注差异化
  - 核心原则："能 `super()` 就绝不自己画"作为硬性编码规范写入 `.trae/instructions.md`
  - 对于确实无法通过 `super()` 定制的细节，使用 `QProxyStyle` 做最小干预

### ADR-002: 采用 YAML 而非 JSON 作为预设格式

- **日期**: 2026-06-09
- **状态**: 已采纳
- **决策**: Design Token 预设文件使用 YAML 格式
- **理由**:
  1. 原生支持注释（JSON 不支持，对设计文件很重要）
  2. 层级嵌套更直观（四层 token 结构在 YAML 中一目了然）
  3. 更好的可读性（设计师可直接编辑）
- **兼容**: 保留 JSON 解析器用于读取旧版预设，迁移期并存

### ADR-003: 4px 基准网格而非 8px

- **日期**: 2026-06-09
- **状态**: 已采纳
- **决策**: 空间基准单位为 4px（而非 Material Design 的 8dp）
- **理由**:
  1. 你的应用是密集型工具 UI（不是移动端），需要更精细的控制粒度
  2. 8px 步进会导致按钮高度跳跃太大（32→40→48），缺少中间档
  3. 当前代码中最常见的合规值（28/32/36/40）都在 4px 网格上
  4. Ant Design、Tailwind CSS 也采用 4px 基准，证明可行性

> **旧常量→新 Token 的完整映射表已迁移至 `docs/ui-refactor-analysis.md` 附录 A。**
> 此处不再重复列出，避免两处维护的不一致风险。

---

## 附录 F: Token 错误处理策略

> 运行时调用了不存在的 token key 怎么办？本节定义统一的处理规则。

### F.1 三级降级策略

```
请求 token("bg.raised")
    │
    ▼
┌─────────────────────────┐
│  Level 1: 精确匹配      │  → 找到 "bg.raised" → 返回值 ✅
└──────────┬──────────────┘
           │ 未找到
           ▼
┌─────────────────────────┐
│  Level 2: 模糊匹配      │  → 找到 "bg.*" 的同族兄弟？
│  例: "bg.hover" 缺失    │     有 "bg.normal"/"bg.raised"
│      → 取 "bg.normal"   │     → 返回最接近的 "bg.normal" + log warning
└──────────┬──────────────┘
           │ 仍未找到
           ▼
┌─────────────────────────┐
│  Level 3: 安全回退      │  → 返回硬编码的安全默认值
│  颜色: #888888 (中性灰)  │  + log error (仅一次，不刷屏)
│  尺寸: 16 (中等值)       │
└─────────────────────────┘
```

### F.2 各级行为定义

| 级别 | 触发条件 | 返回值 | 日志行为 | 对 UI 影响 |
|------|---------|--------|---------|-----------|
| **L1 精确** | key 存在于已加载的预设中 | 实际 Token 值 | 无 | 设计师意图 |
| **L2 模糊** | key 不存在，但父路径存在 | 同组内语义最近的值 | `logging.warning()` **一次** | 功能正常，视觉略有偏差 |
| **L3 回退** | 完全不认识这个 key | 安全默认值 | `logging.error()` **一次** | 组件仍可显示，但不美观 |

### F.3 实现要求

```python
class TokenManager:
    def resolve(self, path: str) -> str | int | float:
        """解析 token 路径。遵循三级降级策略。"""

        # Level 1: 精确匹配
        if path in self._resolved_cache:
            return self._resolved_cache[path]

        # Level 2: 模糊匹配 — 取同组默认态
        parent, _, leaf = path.rpartition(".")
        if parent and parent in self._resolved_cache:
            fallback = f"{parent}.normal"   # 或 .default / .base
            if fallback in self._resolved_cache:
                logger.warning("[Token] '%s' not found, using '%s'", path, fallback)
                return self._resolved_cache[fallback]

        # Level 3: 安全回退
        logger.error("[Token] '%s' not found, using fallback", path)
        return self._get_safe_fallback(path)

    _warned_keys: set[str] = set()  # 防止同一 key 反复 warning 刷屏

    def _log_once(self, level, msg, *args):
        """每个 key 只日志一次。"""
        key = args[0] if args else msg
        if key not in self._warned_keys:
            self._warned_keys.add(key)
            logger.log(level, msg, *args)
```

### F.4 开发期 vs 生产期的区别

| 场景 | L2 行为 | L3 行为 |
|------|---------|---------|
| **开发期**（Phase 1-2）| warning 弹出 + 控制台高亮 | error 弹出 + 断言失败（帮助快速发现 typo） |
| **生产期**（Phase 3+）| 静默降级 + 后台日志 | 静默降级 + 后台日志（不中断用户体验） |

通过环境变量或配置开关控制：`TOKEN_STRICT_MODE=true` 时 L3 抛出 `TokenNotFoundError`。

---

## 附录 G: 组件视觉回归测试方案

> 自绘组件怎么验证画对了？每次修改 paintEvent 后如何确保没有画坏？

### G.1 测试层级

```
G1 单元测试（自动）→ G2 截图对比（半自动）→ G3 人工走查（手动）
```

### G1: 自动化单元测试（必须）

测试**可程序化验证**的属性：

```python
# tests/test_cyber_button.py

class TestCyberButtonGeometry:
    """验证切角几何正确性"""

    def test_chamfered_path_has_8_points(self):
        """切角矩形必须是 8 个顶点"""
        btn = CyberButton("Test")
        path = btn._chamfered_path(btn.rect(), 8)
        assert len(path) == 8

    def test_chamfered_path_corners_are_cut(self):
        """四个角确实被切掉了（不是直角）"""
        btn = CyberButton("Test")
        path = btn._chamfered_path(btn.rect(), 8)
        # 左上角的点不应该在 (0, 0)
        top_left = path.at(0)
        assert top_left.x() > 0
        assert top_left.y() == 0

    def test_button_height_from_token(self):
        """按钮高度必须来自 token，不是硬编码"""
        btn = CyberButton("Test")
        expected = TokenManager.get().resolve_space("height.btn_md")
        assert btn.height() == expected


class TestCyberButtonStates:
    """验证状态机转换"""

    def test_hover_changes_state(self):
        btn = CyberButton("Test")
        assert btn._state == "normal"
        # 模拟鼠标进入
        from PySide6.QtCore import QEvent
        btn.enterEvent(QEvent(QEvent.Type.Enter))
        assert btn._state == "hover"

    def test_token_colors_exist_for_all_states(self):
        """所有状态对应的 token 都有定义"""
        for state in ["normal", "hover", "pressed", "focused", "disabled"]:
            color = TokenManager.get().resolve(f"bg.{state}")
            assert color is not None, f"Missing token: bg.{state}"
```

**运行方式**: `pytest tests/ -v`，每次提交前必跑。

### G2: 截图对比测试（推荐，Phase 1 搭建后启用）

```python
# tests/test_visual_regression.py

import os
from PySide6.QtWidgets import QApplication
from PIL import Image  # pip install Pillow

VISUAL_BASELINE_DIR = "tests/baseline/"
VISUAL_OUTPUT_DIR = "tests/output/"

def capture_widget(widget, filename):
    """将 widget 渲染为 PNG 图片"""
    pixmap = widget.grab()
    pixmap.save(os.path.join(VISUAL_OUTPUT_DIR, filename))

def compare_images(baseline, output, threshold=0.01):
    """对比两张图片，差异超过阈值则失败"""
    img_a = Image.open(baseline)
    img_b = Image.open(output)
    diff = list(ImageChops.difference(img_a, img_b).getdata())
    different_pixels = sum(1 for p in diff if p != (0, 0, 0))
    ratio = different_pixels / (img_a.width * img_a.height)
    assert ratio < threshold, f"Visual diff: {ratio:.2%} pixels changed"

# 用法：
# 1. 首次运行: python -m tests.gen_baseline  → 生成基准截图
# 2. 之后每次: pytest tests/test_visual_regression.py  → 自动对比
# 3. 如果是有意改了样式: python -m tests.gen_baseline --update  → 更新基准
```

**注意**：截图对比在不同 OS/DPI/字体下可能不同。建议在 CI 中固定一个环境运行。

### G3: 人工走查清单（每次实现组件后必做）

完成一个组件后，按以下清单肉眼检查：

```
□ normal 态：背景色正确、文字清晰、无锯齿
□ hover 态：颜色变化平滑、无闪烁、过渡自然
□ pressed 态：有明确的按下反馈（变暗或位移）
□ disabled 态：整体灰化、文字变淡、不再响应 hover
□ focused 态：焦点环可见（Tab 聚焦后能看出来）
□ 不同尺寸(sm/md/lg)：切角比例协调、文字不溢出
□ 长文本按钮：文字省略号(...) 正确显示
□ 极窄宽度：组件最小宽度下不崩溃、布局合理
□ 高 DPI (125%, 150%)：模糊度可接受、尺寸成比例放大
□ 暗色/亮色主题切换：两个主题下都正确渲染
```
