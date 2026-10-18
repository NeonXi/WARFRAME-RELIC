# 代码规范审计与重构计划

> 审计日期：2026-10-19
> 依据：`.trae/rules/开发规范.md`（13 条自查卡 + §7 十二条绝对禁区）
> 范围：`core/` 下全部 108 个模块；重点复核最近 10 次提交新增的代码

---

## 一、审计口径与方法

1. **AST 静态扫描**：按目录判定层级，检查非法 import、硬编码颜色、`setStyleSheet(f"...")`、
   非 4 倍数尺寸、裸 except / `except: pass`、`__file__` 裸推导、文件头层声明。
2. **人工复核**：对扫描命中的文件逐个读源码确认，剔除误报。
3. **运行时验证**：`compileall` + 全量 import + 无头启动 AppShell（13 页注册）。

**总体结论**：项目整体结构是健康的——没有一处把硬编码颜色写进 QSS（初筛 102 条
`setStyleSheet(f"...")` 全部是 Token 拼接的误报）。真正的问题是**层依赖走捷径**、
**静默吞错**和**复制粘贴式重复**，集中在最近为「日志分析 / 快捷键开关」新增的代码里。

---

## 二、本轮已修复（P0，已完成并验证）

| # | 文件 | 问题 | 修复 |
|---|---|---|---|
| 1 | `core/services/cd_debug_log.py` → `core/logging_utils.py` | 一个纯 stdlib 日志工具放在 services/，导致 State 和 Widget 反向依赖 Service（7 处层违规） | 上移到 `core/` 根目录作为 [L0] 基础设施，更新 10 处 import |
| 2 | `core/price_service.py:198` | `os.path.dirname(__file__)` 裸推导 DB 路径 | 改走 `core.paths.ensure_user_file()`；打包后不再可能读到 `_internal` 里的旧库 |
| 3 | `core/pages/toggles_page.py` | 9 处 `except Exception: pass` 包住「保存后通知运行时」，失败时用户只看到开关已保存、实际不生效且无日志 | 新增 `_safe_apply(action, fn)`：失败打印动作名 + 堆栈；全部调用点改造 |
| 4 | `core/pages/toggles_page.py:1103` | `blockSignals(True)` 后若 `setChecked` 抛异常，`blockSignals(False)` 永不执行 → 开关永久失去响应 | 改 `try/finally`，保证信号一定恢复 |
| 5 | `core/pages/toggles_page.py:1172` | 直接访问 `pipeline._hotkey_mgr` 私有属性 | `ScreenshotPipelineService` 新增公开 `suspend_hotkeys()` / `resume_hotkeys()` |
| 6 | `core/pages/license_page.py:332` | `QTimer.singleShot(1500, lambda: btn.setText(...))`：按钮已销毁时回调抛 RuntimeError | 改为以按钮为 parent 的 `QTimer`，随控件销毁 |
| 7 | `core/pages/log_analysis_page.py:210` | 解析线程无 parent、结束后引用不置空，下次 `isRunning()` 可能访问已释放对象 | worker 以页面为 parent，新增 `_on_worker_finished` 置空 + `deleteLater` |
| 8 | `core/services/item_service.py:815-1115` | 9 个掉落来源 7 段复制粘贴，且各自 `except: pass`（表结构漂移会静默少来源） | 收敛为 `_collect` / `_collect_by`，失败记 WARNING + 堆栈；输出逐字节一致（详见 §三 P0-1） |
| 9 | `core/services/{worldstate,log_parser}_service.py` | 任务类型/裂缝纪元/派系词表各存一份，且已漂移（差 `MT_RAILJACK`） | 抽 `core/services/game_vocab.py` 单一事实源（详见 §三 P1-1） |
| 10 | `core/services/worldstate_service.py:186` | daemon 线程向已回收的 QObject emit，偶发 `RuntimeError: Signal source has been deleted` | 新增 `_emit_safely()`，只吞该 RuntimeError |
| 11 | `core/services/log_parser_service.py` + `core/pages/log_analysis_page.py` | 解析线程不可中断，退出时可能 `QThread: Destroyed while running`；且 worker 覆写了 Qt 内置 `finished` 信号 | 新增 `should_cancel` / `ParseCancelled` / `cancel()`；信号改名 `parse_finished`（详见 §三 P0-2） |

**验证结果**：`compileall` 通过；108/108 模块 import 通过；无头启动 13 页全部注册（BOOT OK）。
层依赖违规从 8 处降到 1 处（见 P1-2）。

---

## 三、待重构清单

### P0 — 正确性 / 数据可靠性

#### P0-1 ✅ 已完成（2026-10-19）`item_service.py` 掉落来源查询：7 段复制粘贴 + 9 处静默吞错

**改造内容**
- 新增两个局部助手：
  - `_collect(label, sql, params, mapper)` —— 统一执行 + 映射 + **失败记 WARNING（含表名、物品名、堆栈）**
  - `_collect_by(label, unique_col, name_col, sql_template, mapper)` —— 统一「unique_name 精确优先 / 名称模糊兜底」分支
- 9 个来源（item_drops / relic_rewards / mission_rewards / bounty_rewards / sortie_rewards /
  syndicate_rewards / blueprint_drops / enemy_bp_tables / transient+key_rewards）全部收敛到助手，
  每段只剩「列名 + SQL + mapper」。
- 顺带把同文件另外 4 处会掩盖真实数据问题的吞错改为 `logger.warning(..., exc_info=True)`：
  中文翻译缓存构建、db_meta 读取、遗物入库状态查询、遗物掉落途径查询。
  保留 2 处合理兜底（连接关闭失败、zh_pinyin 列缺失的 schema 降级），均有注释说明。

**验证**
- 改造前后对 13 个用例（含 unique_name 路径、max_results=None、不存在的物品）调用
  `get_drop_sources()`，输出 **741 条记录、87925 字节，SHA256 完全一致**。
- 破坏性验证：复制数据库并 `DROP TABLE sortie_rewards` 后调用，仍返回 605 条其它来源，
  同时输出 `WARNING ... 掉落来源查询失败 [sortie_rewards] item='Forma Blueprint': no such table`。
- 回归：`pytest` 149 passed；无头启动 13 页正常。
- 规模：`get_drop_sources` 内 `except: pass` 由 7 处降为 0；文件内由 15 处降为 2 处（均为合理兜底）。

> 遗留：该方法仍有 301 行（9 个来源 + 助手）。若要进一步缩短，可把 SQL+mapper 提成模块级
> 声明式表（`[(label, unique_col, name_col, sql, mapper), ...]`），属 P2 可选优化。

#### P0-2 ✅ 已完成（2026-10-19）日志解析线程在退出时仍在跑

**改造内容**
- `LogParserService.parse(log_path, should_cancel=None)` 与 `_parse_missions(...)` 新增可选
  取消回调；主循环每 `_CANCEL_CHECK_EVERY = 2000` 行调用一次，命中即抛 `ParseCancelled`。
- 新增 `ParseCancelled` 异常：与「解析失败」语义分离，`parse()` 显式 re-raise，
  不会被通用 `except` 吞成 `None`（否则 UI 会误报"文件格式错误"）。
- `_ParseWorker`：
  - 新增 `cancel()` + `threading.Event`，并在 `__init__` 里连接 `QCoreApplication.aboutToQuit`
    → 程序退出时自动置取消标志（worker 销毁时 Qt 自动断开，无需手工清理）。
  - **把 `finished = QtSignal(object)` 改名为 `parse_finished`** —— 原写法遮蔽了
    `QThread.finished`（Qt 自己的"线程结束"信号），两种语义混在一起是隐患。
  - 新增 `cancelled` 信号；页面收到后只把状态改成「解析已取消」，不提示失败。
- 新增 `tests/test_log_parser.py`（4 个用例）：正常解析字段、文件不存在、可取消、
  不传回调时行为不变。

**实测**
| 场景 | 结果 |
|---|---|
| 15.4MB / 22 万行完整解析 | 0.50s |
| 解析中途取消（0.3s 后置标志） | 0.307s 内退出，线程 `isRunning=False` |
| `aboutToQuit → cancel` 端到端 | 只收到 `cancelled` 信号，`wait()` 成功，无残留线程 |
| 回归 | `pytest` **153 passed**（149 + 4 新增）；13 页启动正常 |

> 说明：本机 15MB 日志解析仅 0.5s，风险主要出现在更慢的机器或更大的日志上；
> 取消机制把退出等待从「不可控」变成「≤ 一个检查周期（约 5ms）」。

#### P0-3 ✅ 已完成（2026-10-19）后台线程向已回收 QObject 发信号
- `worldstate_service._fetch_worker` 在 daemon 线程里直接 `signal.emit()`；
  程序退出/测试 teardown 时单例 QObject 可能先被回收，抛
  `RuntimeError: Signal source has been deleted`（测试首轮复现）。
- 新增 `_emit_safely(signal, *args)`：只吞 `RuntimeError`，其它异常照常暴露。

### P1 — 规范符合性

#### P1-1 ✅ 已完成（2026-10-19）游戏词表双份维护

**审计时确认已漂移**：`log_parser_service` 的 `_MISSION_MAP` 有 24 项，`worldstate_service`
只有 23 项——少 `MT_RAILJACK`（九重天）。这正是"靠注释保持一致"的必然结果。

**改造内容**
- 新增 `core/services/game_vocab.py`（[L-Service] 纯常量，零依赖）作为单一事实源：
  - `MISSION_TYPE_ZH`（24 项，取并集）
  - `VOID_TIER`（VoidT1~T6 → (英文, 中文)）
  - `VOID_TIER_ZH`（由 `VOID_TIER` 派生，避免二次维护）
  - `ENEMY_FACTION_ZH`
- 两个服务改为 `from core.services.game_vocab import ... as _MISSION_MAP` 别名引用，
  **所有使用点一行未改**，diff 全部集中在定义处。

**验证**
- 词表快照对比：`log_parser` 三张表 **完全一致**；`worldstate` 仅 `_MISSION_MAP`
  新增 `MT_RAILJACK`（原回落为 "Railjack"，现正确显示"九重天"），其余一致。
- 回归：`pytest` 149 passed（连续 3 轮）；无头启动 13 页正常。
- 规模：删除 84 行重复定义，新增 27 行引用 + 76 行词表模块。

**顺带修掉的偶发缺陷**
- 详见上文 §三 P0-3（`worldstate_service` daemon 线程 emit 竞态）。
- 关闭期竞态不再产生 traceback；连续 3 轮测试无脏输出。

#### P1-2 ✅ 已完成（2026-10-19）`tokens/manager.py` 的 Qt 触点

**决策：保留惰性导入，不搬迁代码。**

理由（工程判断，而非迁就现状）：
1. `get_qcolor()` 有 **51 个调用点**，全部在 pages / widgets。若把转换逻辑移出 Token 层，
   这 50 多个文件就要各自 `from PySide6.QtGui import QColor`——耦合不但没减少，反而更散。
2. 真正要守的不变量是「**import tokens 不会把 Qt 拉起来**」（单测、构建脚本能在无 Qt 进程
   里导入），而不是「文件里不出现 PySide6 字样」。函数内惰性导入恰好满足前者。
3. 这是**偶然耦合**（为了一个 3 行转换），不是本质耦合。为纯洁性付出 51 处改动，性价比为负。

**落实（把例外变成可执行的约束，而不是一句注释）**
- `core/tokens/manager.py`
  - 文件头红线改写：明确「模块顶层禁止 / `get_qcolor` 惰性导入是唯一例外」
  - 新增 `if TYPE_CHECKING: from PySide6.QtGui import QColor` 与 `-> "QColor"` 返回注解
    —— 类型信息完整，运行期仍零 Qt 依赖
- `.trae/rules/开发规范.md`
  - §6.1 原文「禁止 PySide6」与「可返回 QColor」自相矛盾，改为精确表述
  - §0 自查卡新增第 14 条：分层依赖测试必须通过
- `tests/test_layer_rules.py`
  - 5 个 AST 断言 + 1 个行为断言（共 6 个用例）
  - `test_tokens_layer_has_no_module_level_qt`：守「顶层无 Qt 导入」的语法层
  - `test_tokens_importable_without_qt`：**在屏蔽 PySide6 的子进程里真实导入 tokens**，
    证明运行期零 Qt 依赖（这是行为验证，不是语法检查）
  - 反向验证：故意查 `services → PySide6.QtCore` 能检出 4 处真实依赖，证明守卫不是空转

**结论**：这条的产出不是「改了一行代码」，而是**把一条靠自觉的模糊规则变成了会失败的测试**。
以后再有人往 Token 层顶层写 `import PySide6`，pytest 直接红。

#### P1-3 尺寸魔数（非 4 倍数）
| 文件 | 处数 | 典型 |
|---|---|---|
| `core/widgets/pixel_font_editor.py` | 13 | `setFixedSize(22, 22)`、`setSpacing(6)` |
| `core/pages/about_page.py` | 7 | `setSpacing(10/14)`、`setContentsMargins(18,…)` |
| `core/pages/log_analysis_page.py` | 7 | `setSpacing(10/6/2)`、`setFixedWidth(90)` |
| `core/widgets/manual_update_dialog.py` | 6 | `setSpacing(14)` |
| 其它 5 个文件 | 15 | — |

建议：在 `data/presets/cyberpunk.yaml` 的 spacing 档位里补 `2xs=2 / xs=4 / sm=8 / md=12 / lg=16 / xl=24`，
统一走 `self._spacing(...)`；确实需要特例的（如图表轴宽）写成具名常量。

#### P1-4 字体名硬编码
- `"Iceberg"` 出现在 `log_analysis_page.py`（3 处）、`license_page.py`（2 处）、`about_page.py`；
  `"Consolas"` 出现在 `license_page.py`（2 处）。
- 建议：`core/fonts.py` 已有注册逻辑，补 `FONT_DISPLAY` / `FONT_MONO` 常量供全项目引用。

#### P1-5 `pixel_font_editor.py` 硬编码颜色 5 处
- `#0F0F19`、`#00C8FF`、`#1E1E2D`、`#3C3C50` 等直接写在绘制代码里，切换主题不会跟随。
- 建议：改走 `self.token_color("...")`；缺失的语义色补进两个预设 YAML。

#### P1-6 剩余 70 处 `except: pass` 需要分类处理
**合理兜底（建议保留，补一行注释说明为什么可以吞）**：
- `core/widgets/base.py`（5）— paintEvent 内 token 取色三级兜底，规范明确要求不能抛进绘制；
- `core/trigger_manager.py`（5）— 钩子回调/ScrLK 轮询，异常绝不能冒泡回 Windows 消息循环；
- `core/logging_utils.py`（3）— 日志自身写盘失败不能再抛；
- `core/services/screenshot_pipeline.py`（2）— 退出清理。

**应改为记录日志**：
- `core/price_service.py`（3）、`core/services/db_builder.py`（2）、`core/pages/theme_page.py`（2）、
  `core/widgets/cd_assist_overlay.py`（2）、`core/services/cd_hotkey_hook.py`（2）。

### P2 — 可维护性

- `log_parser_service._parse_missions` 208 行，9 个 `── N. ──` 隐式分支；
  建议改为「正则 → handler」的规则表（`[(regex, handler), ...]`），单条规则可单测。
- `log_analysis_page` 的「最近一场战斗」与「任务行」两套渲染逻辑重复度高（任务类型/时长/成员），
  建议抽 `_mission_summary_parts(m)` 复用。
- `item_name.py` 有 5 个 >90 行函数；`status_page.py` 3 个。
- `core/diagnostics/benchmark_ocr.py:27` 仍有 `__file__` 裸推导（开发工具，优先级低）。

---

## 四、建议执行顺序

1. **P0-1**（item_service 去重 + 日志）—— 影响面大但可用前后 JSON 对比验证，收益最高。
2. **P1-1**（游戏词表去重）—— 纯常量搬家，零风险。
3. **P1-3 / P1-4**（尺寸与字体收敛）—— 纯 UI 观感，可分批按页面做。
4. ~~**P0-2**（解析可取消）~~ —— 已完成，见 §三 P0-2。
5. **P2**（解析器规则表化）—— 建议在有真实 EE.log 样本时再做，配套单测。

> 说明：`pytest` 目前未安装在 venv 中，`tests/` 下 120 个用例跑不起来。
> 建议先 `pip install pytest`，否则上述重构都只能靠手工冒烟验证。
