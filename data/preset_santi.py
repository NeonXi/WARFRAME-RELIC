"""
Three-Body / Deterrence Era language preset.
"""

STRINGS = {

    # ── 窗口标题 ──
    "window_title": {
        "management_panel": "WARFRAME-RELIC · 智子级遗物认知矩阵（威慑纪元控制中枢）",
    },

    # ── 主标题 ──
    "title": {
        "management_panel": "WARFRAME-RELIC · 智子级遗物认知矩阵（威慑纪元控制中枢）",
    },

    # ── 按钮文字 ──
    "button": {
        "exit": "广播终止信号 · 关闭小宇宙",
        "reset_state": "⟳ 归零者协议 · 量子态坍缩",
        "reload_hotkeys": "⭮ 重新注册引力波天线阵列",
        "fetch_github": "阶梯计划 · 从三体世界拉取数据 (GitHub)",
        "browse_file": "指定本地二维箔数据载体...",
        "update_db": "执行光墓写入序列",
        "update_tutorial": "文明操作手册",
        "open_data_dir": "访问四维空间碎片存储泡",
        "update_from_local": "从本地二维箔执行数据解压缩",
        "update_from_network": "通过量子中继信道拉取数据",
        "toggle_detail_expand": "展开低维展开视图",
        "toggle_detail_collapse": "折叠低维展开视图",
        "save_hotkeys": "思想钢印 · 固化热键映射",
        "reset_default": "文明重启 · 回退至威慑纪元基准态",
        "custom_theme": "⬡ 视觉皮层参数（强相互作用材料配色）",
        "bilibili_home": "Bilibili 引力波广播站 →",
        "github_repo": "GitHub 文明档案馆 →",
        "close_log_panel": "关闭智子监控日志视窗",
        "search_clear": "清空检索缓存区",
        "apply_preset": "应用面壁者预设方案",
        "save_theme": "思想钢印 · 固化视觉参数",
        "refresh_preview": "刷新预渲染（智子实时模拟）",
        "mode_check_status": "⊞ 遗物出/入库态判定（光墓查询）",
        "mode_query_parts": "◎ 遗物内含物逆向解析（破壁人协议）",
        "mode_query_price": "⟐ 跨维度市场价值评估（黑暗森林定价）",
        "mode_translate": "⬢ 跨语种符号学映射（智子翻译）",
        "upload_bg": "上传背景图",
        "clear_bg": "清除背景图",
        "fetch_prices": "启动 warframe.market 黑暗森林市场探测",
        "open_market_query": "实时挂单查询",
    },

    # ── 导航标签 ──
    "nav": {
        "nav_toggles":  "功能模态",
        "nav_status":   "数据状态",
        "nav_db_center":    "数据管理",
        "nav_trans":    "翻译库",
        "nav_items":    "物品查询",
        "nav_prices":   "价格数据",
        "nav_hotkeys":  "热键映射",
        "nav_theme":    "主题换肤",
        "nav_about":    "关于",
        "nav_reset":    "紧急协议",
        "nav_preset":   "语言预设",
    },

    # ── 分组标题 ──
    "group": {
        "recovery": "⎅ 归零者紧急协议（异常态恢复）",
        "data_overview": "数据总览",
        "db_center": "阶梯计划 · 数据库管理中心",
        "translation_db": "智子翻译知识库（中英符号映射）",
        "items_i18n": "全文明物品多语种索引库",
        "wm_prices": "⟐ 黑暗森林市场价格波动数据",
        "hotkey_settings": "引力波天线阵列（热键映射）",
        "feature_toggles": "⬢ 后降维功能模态开关矩阵",
        "theme": "主题换肤",
        "lang_preset": "语言风格 · 文案预设",
        "about_author": "关于面壁者/执剑人",
    },

    # ── 统计标签 ──
    "stat_label": {
        "relics_summary": "遗物数据库",
        "relic_vault": "出入库状态",
        "trans_summary": "翻译数据库",
        "items_summary": "全物品索引",
        "db_size": "四维碎片存储泡占用",
        "last_update": "最近一次阶梯计划同步时间戳",
        "trans_total": "智子翻译映射对总数",
        "items_total": "全文明物品实体数",
        "items_has_cn": "地球文明语种覆盖数",
        "items_weapon": "武器类别聚合统计（恒星级/行星级）",
        "price_total": "已定价物品数（黑暗森林博弈定价）",
        "price_has_sell": "有效加权卖价条目",
        "price_has_weighted": "疑似二向箔压价行为检出",
    },
    # ── 统计数值格式化 ──
    "stat_fmt": {
        "count_items": "{count} 个实体（已降维）",
        "db_size_kb": "{size:.1f} KiB",
        "trans_count": "{count} 组智子映射对",
        "cat_detail": "{cat}: {count}",
        "relics_summary": "{relics} 遗物 | {parts} 部件 | {aliases} 别名",
        "relic_vault": "出库 {available} | 入库 {vaulted} | 虚空商人 {voidtrader}",
        "trans_summary": "{total} 条翻译 | {size:.1f} KiB",
        "items_summary": "{total} 物品（中文 {has_cn}） | {size:.1f} KiB",
    },

    # ── 状态概要 ──
    "status": {
        "translation_db": "智子翻译库: --",
        "items_db": "全文明物品索引: --",
        "translation_db_fmt": "智子翻译库: {total} 组映射对 | {size:.1f} KiB",
        "translation_db_none": "智子翻译库: 尚未展开（未启动智子）",
        "translation_db_error": "智子翻译库: 智子自检异常（数据完整性校验失败）",
        "items_db_fmt": "全文明物品索引: {total} 个实体（地球文明覆盖 {has_cn}） | {size:.1f} KiB",
        "items_db_none": "全文明物品索引: 尚未展开（未启动智子）",
        "items_db_error": "全文明物品索引: 智子自检异常（数据完整性校验失败）",
        "db_not_exist": "光墓未初始化（数据仓库不存在）",
        "db_corrupted": "光墓完整性异常（智子检测到量子态衰退）: {error}",
        "db_no_permission": "光墓访问权限不足（面壁者权限未授权）: {error}",
        "placeholder": "--",
        "trans_summary_none": "翻译库: 尚未构建",
        "trans_summary_error": "翻译库: 数据异常",
        "items_summary_none": "全物品索引: 尚未构建",
        "items_summary_error": "全物品索引: 数据异常",
        "done": "执行完毕（威慑纪元时间线正常）",
    },

    # ── 提示文字 ──
    "hint": {
        "recovery": "触发「归零者协议」将执行完整的量子态坍缩恢复序列：\n"
                     "  ① 终止所有智子展开（OCR 线程）\n"
                     "  ② 清除降维采样缓存 + 引力波标注 + 功能模态按钮\n"
                     "  ③ 退出二向箔框选模式，恢复智子屏蔽场（鼠标穿透）\n"
                     "  ④ 重新初始化水滴探测器（摄像头）\n"
                     "  ⑤ 强制重新注册引力波天线阵列（硬编码默认值，不依赖配置文件）\n"
                     "  ⑥ 重置 hotkeys.json 至威慑纪元基准态\n"
                     "  ⑦ 同步刷新控制中枢面板快捷键显示\n"
                     "  ⑧ 输出智子自检报告\n\n"
                     "此操作不会影响：主题配色、功能开关、语言预设、数据库。\n"
                     "若引力波天线阵列失活、图形界面陷入黑域死锁态，请立即触发此协议。",
        "bottom_tip": "智子提示: 输入 Ctrl+Shift+G 指令序列可唤出此威慑纪元控制中枢 | Ctrl+G 触发二向箔降维采样",
        "data_source_relic": "原始数据源: 来自 WFCD 文明档案馆的 all.json + i18n.json\n本地数据库: 从原始数据源派生的 SQLite 光墓数据\n点击「阶梯计划」自动下载并智子清洗，或手动指定本地二维箔后写入",
        "data_source_trans": "数据来源: WFCD 文明档案馆（warframe-items 项目，All.json 与 i18n.json 双文件精确关联算法）",
        "data_source_items": "数据来源: WFCD warframe-items All.json + i18n.json\n自动跟随智子翻译知识库 / 数据库管理中心同步更新",
        "data_source_wm": "数据来源: warframe.market API v2 端点（黑暗森林博弈定价体系）\n仅采集卖价数据，内嵌反二向箔压价权重算法\n偏离中位数 >30% 的低价标记为黑暗森林恶意打击行为，权重衰减至 0.1\n加权参考价 = Σ(价格×权重) / Σ权重\n建议每恒星级周期（数小时）执行一次市场探测以保持时效性",
        "hotkey_format": "输入格式: ctrl+g / alt+shift+f 等。修改后思想钢印即时生效，无需重启小宇宙。",
        "hotkey_placeholder": "例如 ctrl+g",
        "theme_tip": "点击色块触发拾色器（强相互作用材料色谱选择）→ 智子实时模拟预渲染 → 思想钢印固化",
        "items_search_placeholder": "地球语种→三体语种符号映射 · 三体语种→地球语种符号映射（单击结果条目复制英文标识符）",
        "items_search_default": "输入英文标识符或中文语义标签启动智子检索...",
        "items_query_title": "物品标识符查询（智子双语语义索引）",
        "items_search_error": '<span style="color:#ff4444;">智子检索管道异常，请检查光墓数据完整性</span>',
        "items_no_translation": "(尚未建立地球文明语义映射)",
        "about_author": "面壁者/执剑人: NeonXi (B站引力波节点: MichaelJackso2)",
        "version": "WARFRAME-RELIC · 智子认知矩阵引擎 v1.0（威慑纪元）",
    },

    # ── 数据库管理中心 ──
    "db_center": {
        "source_title": "原始数据源",
        "local_db_title": "本地数据库",
        "source_all": "all.json",
        "source_i18n": "i18n.json",
        "source_status_ok": "✓",
        "source_status_missing": "✗ 未找到",
        "db_file_fmt": "{name}  {size}  {mtime}",
    },

    # ── 搜索结果 ──
    "search": {
        "no_match": '智子在现有光墓索引空间中未检索到与 "{query}" 匹配的实体（可能存在于未知文明维度）',
        "copied": "已复制至智子共享缓存区（剪贴板）: {name}",
        "mode_en2cn": "地球→三体 语义映射 | 检索到 {total} 个候选实体（精确:{exact} 前缀:{prefix} 模糊:{contain}）",
        "mode_cn2en": "三体→地球 语义映射 | 检索到 {total} 个候选实体（精确:{exact} 前缀:{prefix} 模糊:{contain}）",
        "mode_result": "找到 {total} 个结果（精确:{exact} 前缀:{prefix} 模糊:{contain}）",
    },

    # ── 热键编辑 ──
    "hotkey": {
        "not_empty": "输入缓存区不可为空（引力波天线参数缺失）",
        "format_error": "格式不符合引力波编码规范",
        "format_error_title": "引力波编码校验未通过",
        "format_error_msg": "请修正红色提示的热键绑定格式。\n\n符合规范的引力波编码: ctrl+g / alt+shift+f / ctrl+shift+g",
        "save_success": "思想钢印固化成功",
        "save_success_msg": "热键映射表已通过思想钢印写入持久化存储泡，即时生效！",
        "save_failed": "思想钢印固化失败",
        "save_failed_msg": "无法写入持久化存储泡，请检查四维碎片空间容量和访问权限。",
        "reset_confirm_title": "确认文明重启（回退至威慑纪元基准态）",
        "reset_confirm_msg": "确定要将引力波天线阵列回退至威慑纪元出厂默认态吗？\n\n区域降维采样: {select}\n全域降维采样: {fullscreen}\n控制中枢: {panel}",
        "reset_done_title": "已归零",
        "reset_done_msg": "引力波天线阵列已重置为威慑纪元出厂默认态。",
        "label_select": "区域降维采样（二向箔局部打击）",
        "label_fullscreen": "全域降维采样（二向箔全覆盖打击）",
        "label_panel": "威慑纪元控制中枢面板",
        "label_query_price": "跨维度市场价值评估（黑暗森林博弈）",
    },

    # ── 退出 ──
    "exit": {
        "confirm_title": "广播终止信号确认",
        "confirm_msg": "确定要向全宇宙广播终止信号，关闭 WARFRAME-RELIC 智子认知矩阵引擎的小宇宙吗？\n\n终止后，所有降维采样管道和引力波天线将停止工作。\n三体世界将与你失去联系。",
    },

    # ── 日志面板 ──
    "log": {
        "panel_title": "智子监控日志视窗（引力波实时观测）",
        "waiting": "智子待命中，等待执剑人操作指令...",
    },

    # ── 主题面板 ──
    "theme": {
        "panel_title": "⬡ 强相互作用材料视觉皮层参数",
        "preset_label": "面壁者预设方案：",
        "no_changes": "智子未检测到差异化的视觉参数修改。请先调整强相互作用材料配色。",
        "no_changes_preview": "请先点击色块修改颜色，再触发智子实时模拟。",
        "prompt_title": "智子提示",
        "saved_to": "视觉参数已通过思想钢印保存至「{name}」，方案已自动切换。",
        "saved": "视觉参数已通过思想钢印固化至「{name}」，图形界面已由智子实时刷新！",
        "save_failed": "思想钢印固化失败：无法写入强相互作用材料配置文件。",
        "reset_confirm_title": "回退至威慑纪元默认视觉参数",
        "reset_confirm_msg": "确定要将当前「{name}」恢复为威慑纪元出厂默认值吗？\n\n当前所有修改将永久坍缩至量子基态。",
        "reset_done_title": "已恢复至威慑纪元基准态",
        "reset_done_msg": "「{name}」已恢复为威慑纪元出厂默认值。",
        "preset_applied": "已应用面壁者预设视觉参数：{name}",
        "preset_failed": "面壁者预设方案应用失败（可能遭遇智子封锁）",
        "color_pick_title": "选择强相互作用材料颜色 - {key}",
        "opacity": "透明度",
        "blur": "模糊度",
        "panel_overlay": "面板遮罩",
        "select_bg_title": "选择背景图片",
        "bg_uploaded": "背景图上传成功",
        "bg_upload_failed": "背景图上传失败",
        "bg_cleared": "背景图已清除",
        "expand_detail": "展开四维参数面板",
        "collapse_detail": "折叠四维参数面板",
    },

    # ── 覆盖层 / Overlay ──
    "overlay": {
        "mode_selected": "▸ 执剑人选择了功能模态: {mode}",
        "relics_found": "智子级水滴探测器检测到 {count} 个遗物实体 — 请选择后续操作模态：",
        "screenshot_done": "二向箔降维采样完成 — 请选择后续操作模态：",
        "selection_cancelled": "二向箔打击已取消（区域降维采样取消）",
        "region_saved": "二向箔打击区域已锁定: [{l},{t}] → [{r},{b}]  ({w}×{h})",
        "region_too_small": "二向箔打击区域面积不足 ({w}×{h})，请重新划定降维范围",
        "please_select_first": "请先通过 Ctrl+G 指令发射二向箔划定降维采样区域",
        "screenshot_failed": "二向箔发射失败（降维采样失败）",
        "fullscreen_failed": "全域二向箔打击失败",
        "no_relics_found": "水滴探测器未检测到遗物实体 — 如需识别Mod请选择：",
        "no_results": "无可用的智子识别结果，请重新执行二向箔降维采样",
        "ocr_waiting": "水滴探测器正在以强相互作用力扫描...请稍候",
        "ocr_recognizing": "智子展开中…正在对二维平面执行光学字符识别",
        "no_mods_found": "水滴探测器未检测到 Mod 实体，请重新执行降维采样",
        "screenshot_expired": "二向箔降维数据已量子退相干，请重新执行降维采样",
        "mod_translate_failed": "智子翻译失败（Mod 符号映射异常）",
        "selection_status_idle": "移动光标至目标区域，按住左键发射二向箔，右键/ESC 取消打击",
        "selection_status_pressed": "二向箔已发射 [{x},{y}]，正在划定降维范围...",
        "selection_status_dragging": "二向箔展开中... 当前降维区域 {w}×{h}",
        "selection_status_released": "二向箔打击完成，正在固化降维采样区域...",
        "annotations_shown": "智子已渲染 {count} 个标注元素（右键清除·黑暗森林广播中止）",
        "query_summary": "遗物内含物逆向解析（破壁人协议）: {total}个实体 | 匹配成功 {matched}个",
        "query_summary_fmt": "遗物内含物逆向解析（破壁人协议）: {total}个实体 | 匹配成功 {matched}个 | 未匹配: {unmatched}",
        "query_legend": "\n(●金=稀有  ◈银=罕见  ◦铜=常见  绿=出库态（威慑纪元）  红=入库态（光墓）)",
        "mod_result": "Mod 识别（智子级）: {total}个候选 | 匹配 {matched}个 (右键清除)",
        "fullscreen_info": "全域二向箔降维采样 ({w}x{h})",
        "item_recognizing": "智子正在扫描物品实体...",
        "no_items_found": "水滴探测器未检测到可交易物品实体",
        "price_query_title": "⟐ 黑暗森林市场价值评估: {total}个实体 | 匹配 {matched}个",
        "price_na": "无市场数据（未进入黑暗森林博弈）",
        "price_weighted_fmt": "{weighted}p",
        "price_detail_fmt": "{name}\n  {zh}\n  加权参考价: {weighted}p | 最低: {min}p | 中位: {median}p",
        "price_item_fmt": "{name}\n  {zh}\n  {price_info}",
        "price_no_match": "未匹配（不在黑暗森林数据库中）",
        "no_features_enabled": "所有功能模态均已禁用（面壁者已关闭全部智子模块），请在控制中枢中启用",
        "please_screenshot_first": "请先执行二向箔降维采样操作",
        "no_relics_detected": "水滴探测器以强相互作用力扫描后未检测到遗物实体",
        "no_items_detected": "水滴探测器未检测到物品实体（可能已被智子屏蔽）",
        "no_text_detected": "智子未在二维平面检测到可识别文本",
        "translate_failed": "智子跨语种映射失败（三体世界通讯中断）",
        "translate_summary": "智子翻译（跨语种符号学映射）: {total}个实体 | 匹配成功 {matched}个 (右键清除)",
        "price_query_summary": "黑暗森林市场评估: {total}个实体 | 有价格数据 {with_price}个",
        "price_query_scanning": "正在扫描物品区域并查询价格...",
        "relic_no_parts_info": "{name}\n  (光墓中未找到部件信息·可能已被归零者清除)",
        "relic_vaulted": "出库",
        "relic_available": "入库",
        "item_price_detail_fmt": "{display_name}\n  加权参考价: {weighted}p\n  最低: {sell_min}p\n  中位: {sell_median}p",
        "item_no_price_fmt": "{display_name}\n  无黑暗森林博弈数据",
        "item_no_match_fmt": "{ocr_text}\n  未匹配（未知文明实体）",
        "translate_label_fmt": "{zh_name}\n  {en_name}",
    },

    # ── 日志消息 ──
    "log_msg": {
        "startup": "智子认知矩阵引擎已展开（威慑纪元启动）",
        "startup_select": "{hk:<16}→ 区域降维采样模式（二向箔松手自动触发智子扫描）",
        "startup_fullscreen": "{hk:<16}→ 全域降维采样模式（跳过区域划定，直接二向箔全覆盖打击）",
        "startup_panel": "{hk:<16}→ 打开威慑纪元控制中枢（光墓写入/智子状态监测）",
        "startup_query_price": "{hk:<16}→ 跨维度市场价值评估（黑暗森林博弈，自动四象限降维采样）",
        "startup_right_click": "右键          → 取消二向箔打击 / 清除智子标注 / 关闭功能模态选择",
        "startup_mode_hint": "降维采样后弹出功能模态选择按钮（可在威慑纪元控制中枢开关）：",
        "startup_mode_check": "  [遗物出/入库态判定]    — 标注遗物名称（绿=出库（威慑纪元） 红=入库（光墓））",
        "startup_mode_query": "  [遗物内含物逆向解析]   — 匹配遗物对应的 Prime 部件（破壁人协议·带颜色）",
        "startup_mode_price": "  [跨维度市场价值评估]   — 识别物品名称并查询 warframe.market 黑暗森林博弈价格",
        "startup_mode_translate": "  [跨语种符号学映射]     — 智子识别英文文本并翻译为中文",
        "startup_db_info": "[WFInfo 光墓数据] 总计 {total} 个遗物 | 威慑纪元 {available} | 光墓 {vaulted}",
        "reset_done": "归零者协议执行完毕 — 量子态已完全坍缩恢复:\n"
                       "  智子展开已终止 | 降维数据已清除 | 引力波天线已重注册 | "
                       "水滴探测器已重初始化 | hotkeys.json 已重置 | 面板 UI 已同步",
        "reset_start": "正在执行归零者协议（完整量子态坍缩恢复序列）...",
        "hotkeys_reloaded": "引力波天线阵列已重新注册",
    },

    # ── 数据更新 ──
    "update": {
        "confirm_update_title": "确认执行光墓写入序列",
        "confirm_update_msg": "将从以下二维箔数据载体执行光墓写入:\n{source}\n\n目标光墓: {target}\n\n此操作将覆盖现有光墓数据。确认继续？",
        "file_not_found_title": "二维箔数据载体未找到",
        "file_not_found_msg": "找不到数据文件（可能已被智子销毁）:\n{path}",
        "fetch_confirm_title": "阶梯计划 · 从三体世界拉取数据",
        "fetch_confirm_msg": "将通过量子中继信道从 GitHub 获取最新数据:\n\n  all.json (掉落数据)\n  i18n.json (多语言翻译，自动清洗)\n\n保存到: {save_path}\n下载完成后将自动执行光墓写入序列。\n\n确认启动阶梯计划？",
        "browse_dialog_title": "选择 WFInfo 二维箔数据文件",
        "browse_filter": "JSON 文件 (*.json);;所有文件 (*.*)",
        "source_current": "当前二维箔: {path}",
        "source_not_found": "all.json 未找到（阶梯计划载荷丢失）: {path}",
        "updating_db": "正在执行光墓写入序列...",
        "update_complete": "光墓写入完成！",
        "update_success": "光墓写入成功！\n  遗物: {relics} | 部件: {parts} | 别名: {aliases}\n  威慑纪元: {dropping} | 光墓: {vaulted}",
        "update_failed": "光墓写入失败（可能遭遇智子封锁）",
        "update_error": "光墓写入异常（量子退相干）: {msg}",
        "download_success": "阶梯计划成功！",
        "download_failed": "阶梯计划失败（量子中继信道中断）",
        "download_complete": "阶梯计划完成，正在自动执行光墓写入序列...",
        "download_starting": "正在启动阶梯计划（量子中继信道连接中）...",
        "trans_confirm_title": "更新智子翻译知识库",
        "trans_confirm_msg": "将重建智子跨语种符号映射知识库。\n\n数据源: {source}\n用途: 遗物部件名英→中符号映射\n注: 主源失败将自动切换到备用量子中继信道。\n\n确认继续？",
        "trans_updating": "智子正在展开，准备翻译数据...",
        "trans_done": "智子翻译知识库更新完成！（智子展开面积已达上限）",
        "trans_failed": "智子翻译知识库更新失败（遭遇智子盲区）",
        "trans_error": "更新失败: {msg}",
        "trans_success_log": "智子翻译知识库更新成功！共 {total} 组中英文映射对。\n数据源: {source}",
        "waiting_start": "智子待命中，等待阶梯计划启动...",
        "preparing": "智子展开中...正在准备",
        "reading_data": "正在读取二维箔数据并写入光墓，请耐心等待（这可能需要一个恒星级时间周期）...",
        "items_rebuilding": "  ◷ 正在自动更新全文明物品多语种索引库（智子扫描中）...",
        "items_rebuilt": "  ✔ 全文明物品光墓已更新: {total} 个实体",
        # 日志面板内联文本
        "log_start_update": "========== 开始执行光墓写入序列 ==========",
        "log_data_source": "  二维箔数据源: {path}",
        "log_target_db": "  目标光墓: {path}",
        "log_update_done_line": "━━━━━━━━━━━━━━━━━━━━━━━━（智子自检通过）",
        "log_update_done": "  ✔ 光墓写入完成",
        "log_relics_total": "遗物总数: {count} 个（已降维至光墓）",
        "log_parts_total": "部件总数: {count} 个",
        "log_aliases_total": "别名总数: {count} 个",
        "log_dropping": "威慑纪元（可获取）: {count} 个",
        "log_vaulted": "光墓（不可获取）: {count} 个",
        "log_update_finished": "========== 光墓写入完成（威慑纪元时间戳已更新） ==========",
        "log_trans_start": "========== 开始更新智子翻译数据库 ==========",
        "log_trans_done": "  ✔ 智子翻译数据库更新完成",
        "log_trans_source": "数据源: {source}",
        "log_trans_total": "总条目: {count} 条（智子映射对）",
        "log_trans_cat": "{cat}: {count} 条",
        "log_trans_finished": "========== 智子翻译库更新完成 ==========",
        "log_trans_failed_line": "========== 更新失败（智子盲区） ==========",
        "log_trans_error": "  ✘ 失败: {msg}",
        "log_fetch_failed_line": "========== 阶梯计划失败 ==========",
        "log_manual_guide_title": "  ━━━━━━ 手动阶梯计划指引 ━━━━━━",
        "log_manual_step1": "  ① 浏览器打开（量子中继信道）: {url}",
        "log_manual_step2": "  ② 右键另存为 all.json，放入 data 四维碎片存储泡",
        "log_manual_step3": "  ③ 点击「指定本地二维箔」选中该文件，再点「光墓写入序列」",
        "downloading_pct": "阶梯计划进行中... 载荷已传输 {pct}%",
        "downloading_pct_wait": "阶梯计划进行中... 载荷已传输 {pct}%，请耐心等待量子中继信道",
        "updating_db_detail": "光墓写入: {msg}",
        "fetch_step_1": "正在解析 GitHub 文明档案馆坐标，检测量子中继信道可用性...",
        "fetch_step_2": "正在展开智子解析 DNS，查找 raw.githubusercontent.com 的引力波信号源...",
        "fetch_step_3": "正在建立 HTTPS 量子纠缠安全连接（TCP + TLS 握手协议）...",
        "fetch_step_4": "正在获取文件元信息（二维箔尺寸、数据类型）...",
        "fetch_step_5": "正在通过量子中继信道下载 all.json 数据文件...",
        "fetch_step_6": "正在验证 JSON 数据格式完整性（智子自检协议）...",
        "fetch_step_7": "正在保存文件到本地 data 四维碎片存储泡...",
    },

    # ── 教程文本 ──
    "tutorial": {
        "trans_title": "智子翻译数据库更新教程（文明操作手册）",
        "trans_content": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  中英文翻译数据库 更新教程（智子翻译知识库）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "本数据库使用 WFCD/warframe-items 项目提供的游戏数据，\n"
            "数据源地址（三体文明档案馆）：\n"
            "  https://github.com/WFCD/warframe-items\n\n"
            "需要以下两个二维箔数据文件：\n"
            "  ① All.json   — 所有物品的完整数据（~15MB）\n"
            "  ② i18n.json  — 物品多语言翻译数据（~2MB）\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法一：阶梯计划自动展开（推荐）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "在「数据库管理中心」点击「阶梯计划」按钮，\n"
            "智子将自动展开下载 all.json 和 i18n.json，\n"
            "并自动清洗 i18n.json（仅保留中英文），\n"
            "完成后会自动构建智子翻译知识库和全文明物品索引。\n\n"
            "如果 GitHub 量子中继信道访问较慢，建议先使用 Watt Toolkit\n"
            "(https://steampp.net/) 加速量子中继信道后再操作。\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法二：手动获取二维箔文件\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "① 获取 All.json（物品数据二维箔）：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json\n\n"
            "② 获取 i18n.json（翻译数据二维箔）：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/i18n.json\n\n"
            "③ 将获取到的两个文件重命名为：\n"
            "     all_items.json\n"
            "     i18n.json\n\n"
            "④ 放入以下四维碎片存储泡：\n"
            "     {data_dir}\n\n"
            "⑤ 回到本程序，点击本区域「从本地二维箔更新」按钮\n"
            "   即可完成构建。\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "智子提示\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• all_items.json 和 i18n.json 放入 data 存储泡后，\n"
            "  智子翻译库和全文明物品数据库将同步更新。\n\n"
            "• 仅在阶梯计划失败或量子中继信道不畅时，才需要\n"
            "  按照方法二手动获取二维箔文件。\n\n"
            "• 如果浏览器无法打开 GitHub 链接，建议先安装\n"
            "  Watt Toolkit 加速量子中继信道后再试。\n"
        ),
        "relic_title": "阶梯计划 · 数据库管理中心 · 操作手册",
        "relic_content": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  数据库管理中心 操作手册（阶梯计划）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "本中心负责管理以下二维箔数据：\n\n"
            "  ▸ all.json  — 遗物掉落数据（warframe-drop-data）\n"
            "  ▸ i18n.json — 物品多语言翻译数据（warframe-items）\n\n"
            "点击「阶梯计划」会同时下载并处理这两个二维箔，\n"
            "其中 i18n.json 会由智子自动清洗（仅保留中英文），\n"
            "然后自动执行光墓写入序列。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法一：阶梯计划自动拉取（推荐）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "点击「阶梯计划 · 从三体世界拉取数据」按钮，智子将自动：\n"
            "  ① 下载 all.json（掉落数据二维箔）\n"
            "  ② 下载 i18n.json（翻译数据二维箔）\n"
            "  ③ 智子清洗 i18n.json（仅保留 zh/en 语言）\n"
            "  ④ 格式化保存两个二维箔\n"
            "  ⑤ 自动执行光墓写入序列\n\n"
            "如果 GitHub 量子中继信道访问较慢，建议先使用 Watt Toolkit\n"
            "(https://steampp.net/) 加速量子中继信道后再操作。\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法二：手动获取二维箔\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "① 获取 all.json（掉落数据二维箔）：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data/all.json\n\n"
            "② 获取 i18n.json（翻译数据二维箔）：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/i18n.json\n\n"
            "③ 将获取到的二维箔放入以下四维碎片存储泡：\n"
            "   {data_dir}\n\n"
            "④ 回到本程序，点击「指定本地二维箔」选中 all.json，\n"
            "   再点击「光墓写入序列」即可。\n\n"
            "   i18n.json 放入后会自动被智子翻译库构建流程识别。\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "智子提示\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• 使用「阶梯计划」最方便，一键完成所有操作。\n\n"
            "• 仅在阶梯计划失败或量子中继信道不畅时，才需要手动获取。\n\n"
            "• 如果浏览器无法打开 GitHub 链接，建议先安装\n"
            "  Watt Toolkit 加速量子中继信道后再试。\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
    },

    # ── 功能开关 ──
    "feature_toggle": {
        "label_check_status": "遗物出/入库态判定（光墓查询）",
        "desc_check_status": "识别遗物名称后，查询该遗物是否已入库/出库",
        "label_query_parts": "遗物内含物逆向解析（破壁人协议）",
        "desc_query_parts": "解析遗物中包含的所有奖励部件及稀有度",
        "label_query_price": "跨维度市场价值评估（黑暗森林博弈）",
        "desc_query_price": "查询部件在 warframe.market 上的实时市场价格",
        "label_translate": "跨语种符号学映射（智子翻译）",
        "desc_translate": "将截图中的英文文本翻译为中文显示",
        "hint": "关闭后，二向箔降维采样时将不再显示对应功能模态按钮。\n修改即时生效（思想钢印瞬时固化）。",
        "saved": "功能开关已通过思想钢印固化",
        "save_failed": "功能开关思想钢印固化失败（遭遇智子封锁）",
    },

    # ── warframe.market 价格 ──
    "price": {
        "no_items_title": "全文明物品光墓不存在",
        "no_items_msg": "请先构建全文明物品中英对照光墓数据库，\n再启动黑暗森林市场探测。",
        "fetch_confirm_title": "启动黑暗森林市场探测",
        "fetch_confirm_msg": "将从 warframe.market API 拉取最新卖价数据（黑暗森林博弈定价）。\n\n仅拉取卖价，含反二向箔压价权重机制\n偏离中位数 >30% 的低价视为黑暗森林恶意打击，权重降为 0.1\n\n速率限制: 每秒 3 个请求（避免触发黑暗森林打击预警）\n预计耗时: 约 10-15 分钟（恒星级时间尺度）\n\n确认启动黑暗森林探测？",
        "fetch_done": "黑暗森林市场探测完成！",
        "fetch_done_title": "探测完成",
        "fetch_done_msg": "黑暗森林市场探测完成！\n\n总计: {total} 个物品\n有加权卖价: {with_sell}\n检测到疑似二向箔压价: {with_weighted}\n异常低价次数: {total_abnormal}\n耗时: {elapsed:.0f}s（地球时间）",
        "fetch_failed_title": "黑暗森林探测失败",
        "fetch_failed_msg": "黑暗森林市场探测失败（可能暴露了坐标）:\n{error}\n\n请检查量子中继信道连接后重试。",
    },

    # ── 主题字段标签（theme_fields.py 中 THEME_FIELDS 使用）──
    "theme_field": {
        "cyber_yellow": "标题/高亮文字（恒星级信号）",
        "cyber_cyan": "数据/数值文字（智子信息流）",
        "cyber_magenta": "装饰品红（强相互作用辉光）",
        "cyber_orange": "警告提示色（黑暗森林警报）",
        "cyber_red": "错误/入库标注（光墓警戒）",
        "cyber_green": "成功/出库标注（威慑纪元绿）",
        "panel_bg": "页面底色（二维平面基态）",
        "card_bg": "输入框/卡片底色（小宇宙内壁）",
        "border": "所有边框线（强相互作用力场边界）",
        "text": "正文/日志文字（智子可读信息）",
        "text_dim": "提示/次要文字（引力波弱信号）",
        "label_default": "统计标签文字（智子标注色）",
        "panel_darkest": "最深底色（光墓/日志区）",
        "panel_deeper": "次深底色（智子代码框）",
        "panel_overlay_rgb": "面板遮罩色",
        "color_unknown": "遗物未知标注（未探索文明维度）",
        "color_gold": "金部件·稀有（恒星级品质）",
        "color_silver": "银部件·罕见（行星级品质）",
        "color_copper": "铜部件·常见（卫星级品质）",
        "btn_default_bg": "普通按钮 背景（二维箔底色）",
        "btn_default_text": "普通按钮 文字（智子可读）",
        "btn_default_border": "普通按钮 边框（力场边界）",
        "btn_hover_bg": "普通按钮 悬停背景（智子感应区）",
        "btn_hover_text": "普通按钮 悬停文字（引力波增强）",
        "btn_hover_border": "普通按钮 悬停边框（力场增强）",
        "btn_pressed_bg": "普通按钮 按下背景（强相互作用压缩）",
        "btn_disabled_bg": "禁用按钮 背景（智子盲区）",
        "btn_disabled_text": "禁用按钮 文字（不可观测）",
        "btn_disabled_border": "禁用按钮 边框（力场消失）",
        "primary_bg": "蓝色主按钮 背景（水滴探测器色）",
        "primary_text": "蓝色主按钮 文字",
        "primary_border": "蓝色主按钮 边框（水滴外壳）",
        "primary_hover_bg": "蓝色主按钮 悬停背景（水滴加速）",
        "primary_hover_border": "蓝色主按钮 悬停边框（水滴机动）",
        "danger_text": "红色危险按钮 文字（二向箔发射警告）",
        "danger_border": "红色危险按钮 边框（二向箔力场）",
        "danger_hover_bg": "红色危险按钮 悬停背景（二向箔预热）",
        "danger_hover_text": "红色危险按钮 悬停文字（二向箔待发射）",
        "success_text": "绿色成功按钮 文字（归零完成）",
        "success_border": "绿色成功按钮 边框（归零力场）",
        "success_hover_bg": "绿色成功按钮 悬停背景（归零预热）",
        "success_hover_text": "绿色成功按钮 悬停文字（归零就绪）",
        "brand_bilibili": "B站链接 默认色（引力波广播站）",
        "brand_bilibili_hover": "B站链接 悬停色（引力波信号增强）",
        "brand_github": "GitHub链接 默认色（文明档案馆）",
        "brand_github_hover": "GitHub链接 悬停色（档案馆照明增强）",
        "overlay_crosshair_color": "截图准星（水滴瞄准系统）",
        "overlay_selection_border": "截图框选边框（二向箔打击边界）",
        "progress_gradient_start": "进度条 左端色（阶梯计划启动）",
        "progress_gradient_mid": "进度条 中间色（阶梯计划巡航）",
        "progress_gradient_end": "进度条 右端色（阶梯计划到达）",
        "fetch_manual_hint": "下载提示色（手动阶梯计划指引）",
        "fetch_error_color": "下载失败色（阶梯计划中断）",
        "price_sell": "卖价文字色（黑暗森林博弈·卖）",
        "price_buy": "买价文字色（黑暗森林博弈·买）",
        "price_median": "中位价文字色（黑暗森林博弈·中位）",
    },
    "theme_cat": {
        "main_color": "界面主色（智子视觉皮层）",
        "panel_bg": "面板背景（二维平面底色）",
        "relic_status": "遗物状态（光墓/威慑纪元）",
        "part_rarity": "部件稀有度（恒星级/行星级/卫星级）",
        "log_color": "日志颜色（智子监控）",
        "btn_style": "按钮样式（强相互作用材料）",
        "brand": "外链品牌（引力波广播站）",
        "overlay": "游戏覆盖层（二向箔打击界面）",
    },

}


# ============================================================
# 便捷访问函数
# ============================================================
