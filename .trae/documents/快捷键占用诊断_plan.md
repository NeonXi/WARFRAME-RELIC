# 快捷键占用诊断功能 实施计划

## 一、需求与背景

用户按下 Ctrl+H（全屏截图）完全无反应。运行时实测定位根因：

- 软件关闭后，`RegisterHotKey(ctrl+h)` 仍返回失败、错误码 **1409（ERROR_HOTKEY_ALREADY_REGISTERED）**——该组合被另一个常驻程序全局占用（用户已自行确认是 OBS）。
- 对照组 ctrl+g 在软件关闭后可注册、运行时被本软件注册，链路本身正常。
- 现有 `hotkey_manager._register()` 注册失败后只 `print` 到 console.log，**3 次重试 + 回退默认值全部失败后，UI 上没有任何提示**；用户无从知道"键没注册上"，表现为"按了没反应、不知道怎么办"。

**目标**：让程序能自动检测每个全局快捷键的注册状态，在「功能开关」页可视化呈现，并在用户改键时即时预检占用，把"无反应"从无头案变成可见、可操作的提示。

## 二、已验证的技术结论（探测原理）

1. **注册即检测**：`RegisterHotKey` 返回 0 且 `GetLastError()==1409` ⇔ 该组合已被其他线程/程序注册。这是最权威的占用判定，不需要模拟按键。
2. **同线程同组合即使热键 ID 不同也返回 1409**（实测）→ 探测时必须区分"被本软件另一个功能占用"（内部冲突）与"被外部程序占用"，两阶段判定：
   - 先查本进程当前注册表（内存映射），判定内部冲突；
   - 再用临时 ID 调 `RegisterHotKey` 试探：成功→立即注销→空闲；1409→外部占用。
3. **MOD_NOREPEAT 不参与冲突判定**（实测带/不带均能检出占用），探测结果可靠。
4. **Windows 无 API 可反查"某热键被哪个进程占用"** → 不做占用程序自动识别，改为给出排查指引（关闭可疑程序后重新检测 / 直接改键）。
5. `cd_1..cd_4` 走 WH_KEYBOARD_LL 低级钩子（观察者模式，不独占按键），不存在 RegisterHotKey 占用问题，**检测范围仅 4 个键**：select / fullscreen / eye_mask / bring_to_front。

## 三、用户已确认的决策

| 决策点 | 结论 |
|---|---|
| 功能范围 | 状态灯 + 「重新检测」按钮 + 改键即时预检（不含端到端按键向导） |
| 改键检出占用 | 红色警告但**仍允许保存**（用户可能稍后关闭占用程序） |
| 附带旧 bug | 一并修正 MOD_NOREPEAT 参数错位 |
| 启动时被占用 | 不弹窗，进入「功能开关」页红灯可见 |

## 四、现状关键事实（调研结论）

- 真实快捷键 UI 在 [toggles_page.py](file:///d:/MyProgram/WARFRAME-RELIC/core/pages/toggles_page.py) 第三区「快捷键绑定」，行由 `_build_hotkey_row()` 构建；保存经 `_apply_hotkeys()` → `shell.pipeline.reregister_hotkeys()`。
- `on_enter()` 每次进页面会重新同步配置；`_pause_hotkeys/_resume_hotkeys` 在录键时注销/恢复全局热键。
- [hotkeys_page.py](file:///d:/MyProgram/WARFRAME-RELIC/core/pages/hotkeys_page.py) 是**无任何引用的死页面**（硬编码假数据），本次不动。
- 文案在 [preset_normal.json](file:///d:/MyProgram/WARFRAME-RELIC/data/preset_normal.json)：仅有单数 `hotkey` 段（3 个 label，缺 bring_to_front）；页面引用的 `hotkeys.*` 键空间在 JSON 中不存在，当前全靠代码默认值兜底。
- Token 齐备：`brand.green`(#00FF99) / `brand.red`(#FF0055) / `brand.orange`，语义别名 `semantic.success/danger/warning`。
- `PageBase._style()` 的样式配方会记录到 `_cyber_style_props` 并在切主题时重放，**重复调用换色安全**。
- 附带旧 bug：[hotkey_manager.py 第273行](file:///d:/MyProgram/WARFRAME-RELIC/core/hotkey_manager.py#L273) `hk_id = (hash(action) & 0x7FFF) | MOD_NOREPEAT`——MOD_NOREPEAT(0x4000) 被拼进了**热键 ID** 参数，而非 `RegisterHotKey` 的 fsModifiers 参数，故"长按不重复触发"从未生效（靠 pipeline 的 0.5 秒防重入兜底，无用户可见故障）。

## 五、文件与改动

### 1. [core/hotkey_manager.py](file:///d:/MyProgram/WARFRAME-RELIC/core/hotkey_manager.py)（L0/L1，核心）

- `_user32` 改为 `ctypes.WinDLL("user32", use_last_error=True)`，给 RegisterHotKey/UnregisterHotKey 声明 argtypes/restype，使错误码可靠。
- 新增状态原因常量：`ok` / `occupied`(外部占用,1409) / `internal`(内部冲突) / `invalid`(非法组合) / `failed`(其他异常)。
- `_register()` 改造：
  - 修正 NOREPEAT：`hk_id = hash(action) & 0x7FFF`（ID 不再带标志位），调用改为 `RegisterHotKey(None, hk_id, mod | MOD_NOREPEAT, vk)`；注销/重试/回退路径同步使用新 ID。
  - 每个 action 的最终结果（hotkey 字符串、ok、reason、error_code）写入 `self._last_report: dict[str, dict]`；入参配置存 `self._current_hotkeys: dict[str,str]` 供内部查重。
  - 1409 日志改成明确中文"被其他程序占用"。
- 新增 `probe_candidate(hk_str: str, exclude_action: str | None) -> dict`（**改键预检，不动现有注册**）：
  1. `_parse_hotkey` 解析失败 → `{ok:False, reason:"invalid"}`；
  2. 与 `exclude_action` 自身当前组合相同（没改）→ `ok`；
  3. 与 `self._current_hotkeys` 中**其他** action 组合相同 → `{ok:False, reason:"internal", conflict_action}`；
  4. 动态选取一个不与任何现有 hk_id 冲突的临时 ID（在 0x7000–0x7FFF 中挑空位，杜绝碰撞），试探注册：成功立即注销→`ok`；1409→`occupied`；其他→`failed`。
- 新增 `get_status_report() -> list[dict]`：按固定 action 顺序返回报告；`health_check()` 行为保持（auto_recover 依赖），日志补充失败原因。

### 2. [core/services/screenshot_pipeline.py](file:///d:/MyProgram/WARFRAME-RELIC/core/services/screenshot_pipeline.py)（L-Service，纯数据转发）

新增三个方法，仅返回 dict/list 原始类型（遵守 Service 不返回 Qt 对象）：

- `get_hotkey_status() -> list[dict]`：读最近一次注册报告，**无副作用**（供进页面时刷新）。
- `recheck_hotkeys() -> list[dict]`：按当前配置注销重注册一次并返回最新报告（供「重新检测」按钮）。
- `probe_hotkey_candidate(hk_str, action) -> dict`：转发 manager 的预检。

### 3. [core/pages/toggles_page.py](file:///d:/MyProgram/WARFRAME-RELIC/core/pages/toggles_page.py)（L2，UI）

- `_build_hotkey_row()`：每行在"重置"按钮前增加状态灯 `QLabel("●")`，句柄存 `self._hotkey_status_dots[action_key]`；tooltip 用原生 `setToolTip` 展示原因。三态：
  - 绿 `brand.green`=正常；红 `brand.red`=占用/冲突/失败；灰 `neutral.dark`=尚未检测。
  - 颜色一律走 `self._style(dot, color=...)`，**不新增 f-string QSS**；封装 `_set_hotkey_dot(action, report_item)` 统一刷新。
- 快捷键卡片内首行增加检测条：左侧说明文字 + 右侧「重新检测」`CyberButton(variant="ghost")`；点击 → `pipeline.recheck_hotkeys()` → 全量刷新灯与诊断条。
- `on_enter()` 末尾：`pipeline.get_hotkey_status()` 静默刷新一次（只读数，不重注册）。
- `_on_hotkey_captured()`：保存重注册后，读取该 action 报告项刷新状态灯；保存前可先调 `probe_hotkey_candidate` 得到即时提示（被占用/内部冲突时红灯与文案立即就位），**不阻止保存**。
- `_reset_hotkey()` 后同样按报告刷新。
- 现有蓝色静态提示框保留；其上方新增**默认隐藏的红色诊断条**（复用现有 tip_frame 的 `_style(raw=callable)` 模式，换用 danger token）：存在红灯项时 show，文案动态拼接（如「Ctrl+H 已被其他程序占用，按下可能无反应。可关闭占用程序（常见：OBS/录屏、输入法、QQ 等）后点重新检测，或直接改为其他组合」）；全部正常时 hide。

### 4. [data/preset_normal.json](file:///d:/MyProgram/WARFRAME-RELIC/data/preset_normal.json)（文案）

新增 `hotkeys` 段：4 个 label（select/fullscreen/eye_mask/**bring_to_front 窗口置顶**，顺带修复该键当前显示英文 action key 的瑕疵）、`btn_recheck`、`status_ok/occupied/internal/invalid/failed/unknown`、`check_hint`、`occupied_guide`。内部冲突文案用 `S.format` 模板带 `{name}` 参数。

## 六、实施步骤（依赖顺序）

1. hotkey_manager：WinDLL use_last_error + argtypes → NOREPEAT 修正 → 注册报告收集 → `probe_candidate` → `get_status_report`。
2. screenshot_pipeline：三个转发方法。
3. preset_normal.json：文案段。
4. toggles_page：状态灯 + 检测条/按钮 + 诊断条 → on_enter 刷新 → 改键/重置联动。
5. 自测与回归（见下）。

## 七、验证

- **占用实测**：启动 OBS（占 ctrl+h）→ `python dev.py --once` 启动软件 → 进功能开关页：全屏捕获行红灯、诊断条出现且 tooltip 正确；关闭 OBS → 点「重新检测」→ 转绿灯、诊断条隐藏。
- **改键预检**：录一个被占用组合→红灯警告但已保存；录空闲组合→绿灯；录成与另一功能相同的组合→内部冲突红灯，文案含冲突功能中文名。
- **重置**：点重置后灯按默认组合真实注册结果刷新。
- **NOREPEAT**：长按任一快捷键不连发（消息仅一次），短按功能正常；4 个键逐一实测各触发一次。
- **主题切换**：在功能开关页切换预设，状态灯/诊断条颜色正确重放无污染；沉浸黑色模式下外观正常。
- **规范自查**：过 `.trae/rules/开发规范.md` §0 快速自查卡 13 条；重点：无 f-string QSS、颜色/尺寸全 token、Service 返回纯数据、文件头层级声明。
- 控制台确认注册日志含每个键的成功/占用结论。

## 八、风险与处理

- **探测 ID 与业务 ID 碰撞**：不使用固定魔法值，运行时在 0x7000–0x7FFF 选取现有注册表之外的空位；试探后立即注销。
- **探测/重检测的毫秒级注销窗口**：仅发生在改键与手动检测瞬间，可能漏掉一次按键，可接受；业务键的正常使用不经过探测。
- **改 WinDLL 构造方式影响面**：use_last_error 只影响错误码读取，UnregisterHotKey 等其他调用行为不变；实施后跑全量热键冒烟。
- **`_style` 重复调用幂等性**：已确认样式配方按 key 覆盖存储、支持重放，灯色刷新安全。
- **回退默认值逻辑**：保持现状（默认组合若也被占则报告 occupied），UI 如实标红，不再静默。
