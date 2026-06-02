"""
WARFRAME-RELIC UI 字符串 — 普通版（标准模式）
简洁直白的文字风格，适合日常使用。
"""

STRINGS = {

    # ── 窗口标题 ──
    "window_title": {
        "management_panel": "WARFRAME-RELIC · 遗物管理控制台",
    },

    # ── 主标题 ──
    "title": {
        "management_panel": "WARFRAME-RELIC · 遗物管理控制台",
    },

    # ── 按钮文字 ──
    "button": {
        "exit": "退出程序",
        "reset_state": "紧急重置 · 恢复默认状态",
        "reload_hotkeys": "重新注册快捷键",
        "fetch_github": "从 GitHub 拉取最新数据",
        "browse_file": "选择本地数据文件...",
        "update_db": "更新数据库",
        "update_tutorial": "使用说明",
        "open_data_dir": "打开数据目录",
        "update_from_local": "从本地文件更新",
        "update_from_network": "从网络拉取更新",
        "toggle_detail_expand": "展开详情",
        "toggle_detail_collapse": "收起详情",
        "save_hotkeys": "保存快捷键设置",
        "reset_default": "恢复默认",
        "custom_theme": "自定义主题配色",
        "bilibili_home": "Bilibili 主页",
        "github_repo": "GitHub 仓库",
        "close_log_panel": "关闭日志面板",
        "search_clear": "清空",
        "apply_preset": "应用预设方案",
        "save_theme": "保存",
        "refresh_preview": "刷新预览",
        "upload_bg": "上传背景图",
        "clear_bg": "清除背景图",
        "mode_check_status": "遗物出入库状态查询",
        "mode_query_parts": "遗物内含物查询",
        "mode_query_price": "市场价格查询",
        "mode_translate": "英文翻译",
        "fetch_prices": "拉取 warframe.market 价格数据",
    },

    # ── 导航标签 ──
    "nav": {
        "nav_toggles":  "功能开关",
        "nav_status":   "数据状态",
        "nav_relic":    "遗物更新",
        "nav_trans":    "翻译库",
        "nav_items":    "物品查询",
        "nav_prices":   "价格数据",
        "nav_hotkeys":  "快捷键",
        "nav_theme":    "主题换肤",
        "nav_preset":   "语言预设",
        "nav_about":    "关于",
        "nav_reset":    "紧急重置",
    },

    # ── 分组标题 ──
    "group": {
        "recovery": "紧急恢复（异常状态重置）",
        "db_status": "数据库健康状态",
        "relic_update": "遗物数据库同步",
        "translation_db": "翻译数据库（中英文对照）",
        "items_i18n": "全物品多语言索引库",
        "wm_prices": "warframe.market 价格数据",
        "hotkey_settings": "快捷键设置",
        "feature_toggles": "截图后功能开关",
        "theme": "主题换肤",
        "about_author": "关于作者",
    },

    # ── 统计标签 ──
    "stat_label": {
        "relics_total": "遗物总数",
        "parts_total": "Prime 部件总数",
        "aliases_total": "别名映射条目数",
        "vaulted": "入库（已绝版）",
        "available": "出库（可获取）",
        "voidtrader": "虚空商人可交易",
        "db_size": "数据库大小",
        "last_update": "最近更新时间",
        "trans_total": "翻译条目总数",
        "items_total": "全物品总数",
        "items_has_cn": "有中文名数量",
        "items_weapon": "武器分类统计",
        "price_total": "已定价物品数",
        "price_has_sell": "有效卖价条目数",
        "price_has_weighted": "检测到异常低价",
    },
    "stat_fmt": {
        "count_items": "{count} 个",
        "db_size_kb": "{size:.1f} KiB",
        "trans_count": "{count} 条",
        "cat_detail": "{cat}: {count}",
    },

    # ── 状态概要 ──
    "status": {
        "translation_db": "翻译库: --",
        "items_db": "全物品索引: --",
        "translation_db_fmt": "翻译库: {total} 条 | {size:.1f} KiB",
        "translation_db_none": "翻译库: 尚未构建",
        "translation_db_error": "翻译库: 数据异常（完整性校验失败）",
        "items_db_fmt": "全物品索引: {total} 个（有中文名 {has_cn}） | {size:.1f} KiB",
        "items_db_none": "全物品索引: 尚未构建",
        "items_db_error": "全物品索引: 数据异常（完整性校验失败）",
        "db_not_exist": "数据库不存在",
        "db_corrupted": "数据库异常: {error}",
        "db_no_permission": "数据库访问权限不足: {error}",
        "placeholder": "--",
        "done": "操作完成",
    },

    # ── 提示文字 ──
    "hint": {
        "recovery": "点击下方按钮将执行完整的异常恢复流程：\n"
                    "  ① 终止所有后台识别线程\n"
                    "  ② 清除截图缓存 + 标注 + 功能按钮\n"
                    "  ③ 退出框选模式，恢复鼠标穿透\n"
                    "  ④ 重新初始化摄像头\n"
                    "  ⑤ 强制重新注册所有快捷键（硬编码默认值，不依赖配置文件）\n"
                    "  ⑥ 重置 hotkeys.json 配置文件\n"
                    "  ⑦ 同步刷新控制台面板快捷键显示\n"
                    "  ⑧ 输出健康诊断报告\n\n"
                    "此操作不会影响：主题配色、功能开关、语言预设、数据库。\n"
                    "当快捷键失效、界面卡死或识别异常时，请立即点击此按钮。",
        "bottom_tip": "提示: 按 Ctrl+Shift+G 打开此控制台 | Ctrl+G 框选截图",
        "data_source_relic": "数据来源: WFCD warframe-drop-data 项目\n如果自动拉取失败，可以手动下载 all.json 后点击「选择本地数据文件」→「更新数据库」",
        "data_source_trans": "数据来源: WFCD warframe-items 项目（All.json + i18n.json 双文件关联算法）",
        "data_source_items": "数据来源: WFCD warframe-items All.json + i18n.json\n随翻译库 / 遗物数据库自动同步更新",
        "data_source_wm": "数据来源: warframe.market API v2\n仅采集卖价数据，内嵌反压价权重算法\n偏离中位数 >30% 的低价权重降为 0.1\n加权参考价 = Σ(价格×权重) / Σ权重\n建议每数小时拉取一次以保持数据时效性",
        "hotkey_format": "输入格式: ctrl+g / alt+shift+f 等。修改后即时生效，无需重启。",
        "hotkey_placeholder": "例如 ctrl+g",
        "theme_tip": "点击色块可调色 → 实时预览 → 点击保存",
        "items_search_placeholder": "输入中文/英文/拼音关键词搜索物品（单击结果复制英文名）",
        "items_search_default": "输入中文/英文/拼音关键词开始搜索...",
        "items_query_title": "物品名称查询（中/英/拼音）",
        "items_search_error": '<span style="color:#ff4444;">查询异常，请检查数据库完整性</span>',
        "items_no_translation": "(暂无中文名)",
        "about_author": "作者: NeonXi (B站: MichaelJackso2)",
        "version": "WARFRAME-RELIC v1.0",
    },

    # ── 搜索结果 ──
    "search": {
        "no_match": '未找到与 "{query}" 匹配的物品',
        "copied": "已复制到剪贴板: {name}",
        "mode_result": "找到 {total} 个结果（精确:{exact} 前缀:{prefix} 模糊:{contain}）",
    },

    # ── 热键编辑 ──
    "hotkey": {
        "not_empty": "不能为空",
        "format_error": "格式不正确",
        "format_error_title": "快捷键格式错误",
        "format_error_msg": "请修正红色提示的快捷键设置。\n\n正确格式示例: ctrl+g / alt+shift+f / ctrl+shift+g",
        "save_success": "保存成功",
        "save_success_msg": "快捷键已保存，即时生效！",
        "save_failed": "保存失败",
        "save_failed_msg": "无法写入配置文件，请检查磁盘空间和权限。",
        "reset_confirm_title": "确认恢复默认快捷键",
        "reset_confirm_msg": "确定要恢复默认快捷键吗？\n\n框选截图: {select}\n全屏截图: {fullscreen}",
        "reset_done_title": "已恢复",
        "reset_done_msg": "快捷键已恢复为默认值。",
        "label_select": "框选截图",
        "label_fullscreen": "全屏截图",
        "label_query_price": "价格查询（自动4等分截图）",
    },

    # ── 退出 ──
    "exit": {
        "confirm_title": "确认退出",
        "confirm_msg": "确定要退出 WARFRAME-RELIC 吗？\n\n退出后所有截图和识别功能将停止工作。",
    },

    # ── 日志面板 ──
    "log": {
        "panel_title": "运行日志",
        "waiting": "等待操作指令...",
    },

    # ── 主题面板 ──
    "theme": {
        "panel_title": "⬡ 主题配色设置",
        "preset_label": "预设方案：",
        "no_changes": "未检测到颜色修改。请先调整色块。",
        "no_changes_preview": "请先点击色块修改颜色，再刷新预览。",
        "prompt_title": "提示",
        "saved_to": "配色已保存至「{name}」，方案已自动切换。",
        "saved": "配色已保存至「{name}」，界面已刷新！",
        "save_failed": "保存失败：无法写入配置文件。",
        "reset_confirm_title": "恢复默认配色",
        "reset_confirm_msg": "确定要将「{name}」恢复为默认值吗？\n\n所有修改将丢失。",
        "reset_done_title": "已恢复",
        "reset_done_msg": "「{name}」已恢复为默认值。",
        "preset_applied": "已应用预设配色：{name}",
        "preset_failed": "预设方案应用失败",
        "color_pick_title": "选择颜色 - {field}",
        "opacity": "透明度",
        "blur": "模糊度",
        "panel_overlay": "面板遮罩",
        "select_bg_title": "选择背景图片",
        "bg_uploaded": "背景图上传成功",
        "bg_upload_failed": "背景图上传失败",
        "bg_cleared": "背景图已清除",
        "expand_detail": "展开详细设置",
        "collapse_detail": "收起详细设置",
    },

    # ── 覆盖层 / Overlay ──
    "overlay": {
        "mode_selected": "已选择功能: {mode}",
        "relics_found": "检测到 {count} 个遗物 — 请选择后续操作：",
        "screenshot_done": "截图完成 — 请选择后续操作：",
        "selection_cancelled": "框选已取消",
        "region_saved": "截图区域已锁定: [{l},{t}] → [{r},{b}]  ({w}×{h})",
        "region_too_small": "截图区域过小 ({w}×{h})，请重新框选",
        "please_select_first": "请先按 Ctrl+G 框选截图区域",
        "screenshot_failed": "截图失败",
        "fullscreen_failed": "全屏截图失败",
        "no_relics_found": "未检测到遗物 — 如需识别Mod请选择：",
        "no_results": "没有可用的识别结果，请重新截图",
        "ocr_waiting": "OCR 正在扫描...请稍候",
        "ocr_recognizing": "OCR 识别中...",
        "no_mods_found": "未检测到 Mod，请重新截图",
        "screenshot_expired": "截图数据已过期，请重新截图",
        "mod_translate_failed": "Mod 翻译失败",
        "selection_status_idle": "移动光标至目标区域，按住左键框选，右键/ESC 取消",
        "selection_status_pressed": "框选起点 [{x},{y}]，拖动选择区域...",
        "selection_status_dragging": "框选中... 当前区域 {w}×{h}",
        "selection_status_released": "框选完成，正在锁定截图区域...",
        "annotations_shown": "已显示 {count} 个标注（右键清除）",
        "query_summary": "遗物内含物查询: {total}个 | 匹配成功 {matched}个",
        "query_summary_fmt": "遗物内含物查询: {total}个 | 匹配成功 {matched}个 | 未匹配: {unmatched}",
        "query_legend": "\n(●金=稀有  ◈银=罕见  ◦铜=常见  绿=出库  红=入库)",
        "mod_result": "Mod 识别: {total}个 | 匹配 {matched}个 (右键清除)",
        "fullscreen_info": "全屏截图 ({w}x{h})",
        "item_recognizing": "正在识别物品...",
        "no_items_found": "未检测到可交易物品",
        "price_query_title": "市场价格查询: {total}个 | 匹配 {matched}个",
        "price_na": "无价格数据",
        "price_weighted_fmt": "{weighted}p",
        "price_detail_fmt": "{name}\n  {zh}\n  加权参考价: {weighted}p | 最低: {min}p | 中位: {median}p",
        "price_item_fmt": "{name}\n  {zh}\n  {price_info}",
        "price_no_match": "未匹配（不在价格数据库中）",
        "no_features_enabled": "所有功能均已禁用，请在控制台中启用",
        "please_screenshot_first": "请先执行截图操作",
        "no_relics_detected": "OCR 扫描后未检测到遗物",
        "no_items_detected": "未检测到物品",
        "no_text_detected": "未检测到可识别文本",
        "translate_failed": "翻译失败",
        "translate_summary": "翻译: {total}个 | 匹配成功 {matched}个 (右键清除)",
        "price_query_scanning": "正在扫描物品区域并查询价格...",
        "price_query_summary": "价格查询: {total}个 | 有价格数据 {with_price}个",
        "relic_no_parts_info": "{name}\n  (未找到部件信息)",
        "relic_vaulted": "出库",
        "relic_available": "入库",
        "item_price_detail_fmt": "{display_name}\n  加权参考价: {weighted}p\n  最低: {sell_min}p\n  中位: {sell_median}p",
        "item_no_price_fmt": "{display_name}\n  无价格数据",
        "item_no_match_fmt": "{ocr_text}\n  未匹配",
        "translate_label_fmt": "{zh_name}\n  {en_name}",
    },

    # ── 日志消息 ──
    "log_msg": {
        "startup": "WARFRAME-RELIC 已启动",
        "startup_select": "{hk:<16}→ 框选截图模式（松手自动触发识别）",
        "startup_fullscreen": "{hk:<16}→ 全屏截图模式（跳过框选，直接全屏识别）",
        "startup_query_price": "{hk:<16}→ 价格查询（自动4等分截图+识别+标注）",
        "startup_right_click": "右键          → 取消框选 / 清除标注 / 关闭功能选择",
        "startup_mode_hint": "截图后将弹出功能选择按钮（可在控制台中开关）：",
        "startup_mode_check": "  [出入库查询]     — 标注遗物名称（绿=出库 红=入库）",
        "startup_mode_query": "  [内含物查询]     — 匹配遗物对应的 Prime 部件",
        "startup_mode_price": "  [市场价格查询]   — 识别物品并查询 warframe.market 价格",
        "startup_mode_translate": "  [英文翻译]       — 识别英文文本并翻译为中文",
        "startup_db_info": "[WFInfo 数据库] 共 {total} 个遗物 | 出库 {available} | 入库 {vaulted}",
        "reset_done": "紧急重置完成 — 识别已终止 | 缓存已清除 | 摄像头已重初始化 | 快捷键已重注册 | 配置文件已重置 | 面板已同步",
        "reset_start": "正在执行完整异常恢复流程...",
        "hotkeys_reloaded": "快捷键已重新注册",
    },

    # ── 数据更新 ──
    "update": {
        "confirm_update_title": "确认更新数据库",
        "confirm_update_msg": "将从以下数据文件更新数据库:\n{source}\n\n目标数据库: {target}\n\n此操作将覆盖现有数据。确认继续？",
        "file_not_found_title": "文件未找到",
        "file_not_found_msg": "找不到数据文件:\n{path}",
        "fetch_confirm_title": "从 GitHub 拉取数据",
        "fetch_confirm_msg": "将从 GitHub 下载最新 all.json:\n\n{url}\n\n保存到: {save_path}\n下载完成后将自动更新数据库。\n\n确认开始下载？",
        "browse_dialog_title": "选择 WFInfo 数据文件",
        "browse_filter": "JSON 文件 (*.json);;所有文件 (*.*)",
        "source_current": "当前数据源: {path}",
        "source_not_found": "all.json 未找到: {path}",
        "updating_db": "正在更新数据库...",
        "update_complete": "数据库更新完成！",
        "update_success": "数据库更新成功！\n  遗物: {relics} | 部件: {parts} | 别名: {aliases}\n  出库: {dropping} | 入库: {vaulted}",
        "update_failed": "数据库更新失败",
        "update_error": "数据库更新异常: {msg}",
        "download_success": "下载成功！",
        "download_failed": "下载失败（网络连接中断）",
        "download_complete": "下载完成，正在自动更新数据库...",
        "download_starting": "正在启动下载（连接 GitHub）...",
        "trans_confirm_title": "更新翻译数据库",
        "trans_confirm_msg": "将重建中英文翻译数据库。\n\n数据源: {source}\n用途: 遗物部件名英→中翻译\n注: 主源失败将自动切换到备用源。\n\n确认继续？",
        "trans_updating": "正在准备翻译数据...",
        "trans_done": "翻译数据库更新完成！",
        "trans_failed": "翻译数据库更新失败",
        "trans_error": "更新失败: {msg}",
        "trans_success_log": "翻译数据库更新成功！共 {total} 条。\n数据源: {source}",
        "waiting_start": "等待操作启动...",
        "preparing": "准备中...",
        "reading_data": "正在读取数据并写入数据库，请耐心等待...",
        "items_rebuilding": "  ◷ 正在自动更新全物品索引库...",
        "items_rebuilt": "  ✔ 全物品索引已更新: {total} 个",
        "log_start_update": "========== 开始更新数据库 ==========",
        "log_data_source": "  数据源: {path}",
        "log_target_db": "  目标数据库: {path}",
        "log_update_done_line": "━━━━━━━━━━━━━━━━━━━━━━━━（校验通过）",
        "log_update_done": "  ✔ 数据库更新完成",
        "log_relics_total": "遗物总数: {count} 个",
        "log_parts_total": "部件总数: {count} 个",
        "log_aliases_total": "别名总数: {count} 个",
        "log_dropping": "出库（可获取）: {count} 个",
        "log_vaulted": "入库（不可获取）: {count} 个",
        "log_update_finished": "========== 数据库更新完成 ==========",
        "log_trans_start": "========== 开始更新翻译数据库 ==========",
        "log_trans_done": "  ✔ 翻译数据库更新完成",
        "log_trans_source": "数据源: {source}",
        "log_trans_total": "总条目: {count} 条",
        "log_trans_cat": "{cat}: {count} 条",
        "log_trans_finished": "========== 翻译库更新完成 ==========",
        "log_trans_failed_line": "========== 更新失败 ==========",
        "log_trans_error": "  ✘ 失败: {msg}",
        "log_fetch_failed_line": "========== 下载失败 ==========",
        "log_manual_guide_title": "  ━━━━━━ 手动下载指引 ━━━━━━",
        "log_manual_step1": "  ① 浏览器打开: {url}",
        "log_manual_step2": "  ② 右键另存为 all.json，放入 data 目录",
        "log_manual_step3": "  ③ 点击「选择本地数据文件」选中该文件，再点「更新数据库」",
        "downloading_pct": "下载中... 已完成 {pct}%",
        "downloading_pct_wait": "下载中... 已完成 {pct}%，请耐心等待",
        "updating_db_detail": "数据库更新: {msg}",
        "fetch_step_1": "正在解析 GitHub 地址，检测网络连接...",
        "fetch_step_2": "正在解析 DNS，查找 raw.githubusercontent.com...",
        "fetch_step_3": "正在建立 HTTPS 安全连接（TCP + TLS 握手）...",
        "fetch_step_4": "正在获取文件元信息（大小、类型）...",
        "fetch_step_5": "正在下载 all.json 数据文件...",
        "fetch_step_6": "正在验证 JSON 数据格式完整性...",
        "fetch_step_7": "正在保存文件到本地 data 目录...",
    },

    # ── 教程文本 ──
    "tutorial": {
        "trans_title": "翻译数据库更新教程",
        "trans_content": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  中英文翻译数据库 更新教程\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "本数据库使用 WFCD/warframe-items 项目提供的游戏数据，\n"
            "数据源地址：\n"
            "  https://github.com/WFCD/warframe-items\n\n"
            "需要以下两个数据文件：\n"
            "  ① All.json   — 所有物品的完整数据（~15MB）\n"
            "  ② i18n.json  — 物品多语言翻译数据（~2MB）\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法一：自动下载（推荐）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "点击本区域「从网络拉取更新」按钮，\n"
            "程序将自动下载并构建数据库。\n\n"
            "如果 GitHub 访问较慢，建议先使用 Watt Toolkit\n"
            "(https://steampp.net/) 加速网络后再操作。\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法二：手动获取文件\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "① 获取 All.json（物品数据）：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json\n\n"
            "② 获取 i18n.json（翻译数据）：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/i18n.json\n\n"
            "③ 将获取到的两个文件重命名为：\n"
            "     all_items.json\n"
            "     i18n.json\n\n"
            "④ 放入以下目录：\n"
            "     {data_dir}\n\n"
            "⑤ 回到本程序，点击本区域「从本地文件更新」按钮\n"
            "   即可完成构建。\n\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚐ 提示\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• all_items.json 和 i18n.json 放入 data 目录后，\n"
            "  翻译库和全物品数据库将同步更新。\n\n"
            "• 仅在自动下载失败或网络不畅时，才需要\n"
            "  按照方法二手动获取文件。\n\n"
            "• 如果浏览器无法打开 GitHub 链接，建议先安装\n"
            "  Watt Toolkit 加速网络后再试。\n"
        ),
        "relic_title": "数据更新教程",
        "relic_content": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏚ WARFRAME-RELIC 数据更新教程\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "本程序使用 WFCD/warframe-drop-data 项目提供的游戏数据，\n"
            "数据源地址：\n"
            "https://github.com/WFCD/warframe-drop-data\n\n"
            "由于 GitHub 在国内可能较慢或不稳定，\n"
            "建议使用以下任一方式获取数据文件：\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法一：使用 Watt Toolkit (原名 Steam++) 加速\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Watt Toolkit 是一款免费、开源、跨平台的网络加速工具，\n"
            "可以稳定加速 GitHub 访问，完全免费无广告。\n\n"
            "① 下载安装\n"
            "   官网：https://steampp.net/\n"
            "   也可在微软应用商店搜索「Watt Toolkit」安装。\n\n"
            "② 启用 GitHub 加速\n"
            "   - 打开 Watt Toolkit\n"
            "   - 点击左侧「网络加速」\n"
            "   - 在「平台加速」选项卡中勾选「GitHub」\n"
            "   - 点击右上角「一键加速」按钮\n\n"
            "③ 启动加速后，再点击本程序的「从 GitHub 拉取」按钮\n"
            "   即可流畅获取 all.json 数据文件。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "方法二：手动获取（无需任何工具）\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "① 在浏览器中打开以下链接：\n"
            "   https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data/all.json\n\n"
            "② 右键 → 另存为（或 Ctrl+S），将文件保存为 all.json\n\n"
            "③ 将获取好的 all.json 放入以下目录：\n"
            "   {data_dir}\n\n"
            "④ 回到本程序，在「手动数据更新」区域点击「更新数据库」即可。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚐ 提示：如果浏览器也无法打开该链接，建议先使用方法一\n"
            "   安装 Watt Toolkit 加速网络后再获取。\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
    },

    # ── 功能开关 ──
    "feature_toggle": {
        "label_check_status": "遗物出入库状态查询",
        "desc_check_status": "识别遗物名称后，查询该遗物是否已入库/出库",
        "label_query_parts": "遗物内含物查询",
        "desc_query_parts": "解析遗物中包含的所有奖励部件及稀有度",
        "label_query_price": "市场价格查询",
        "desc_query_price": "查询部件在 warframe.market 上的实时市场价格",
        "label_translate": "英文翻译",
        "desc_translate": "将截图中的英文文本翻译为中文显示",
        "hint": "关闭后，截图时将不再显示对应功能按钮。\n修改即时生效。",
        "saved": "功能开关已保存",
        "save_failed": "功能开关保存失败",
    },

    # ── warframe.market 价格 ──
    "price": {
        "no_items_title": "全物品数据库不存在",
        "no_items_msg": "请先构建全物品中英文对照数据库，\n再拉取市场价格。",
        "fetch_confirm_title": "确认拉取市场价格",
        "fetch_confirm_msg": "将从 warframe.market API 拉取最新卖价数据。\n\n仅拉取卖价，含反压价权重机制\n偏离中位数 >30% 的低价权重降为 0.1\n\n速率限制: 每秒 3 个请求\n预计耗时: 约 10-15 分钟\n\n确认开始拉取？",
        "fetch_done": "市场价格拉取完成！",
        "fetch_done_title": "拉取完成",
        "fetch_done_msg": "市场价格拉取完成！\n\n总计: {total} 个物品\n有加权卖价: {with_sell}\n检测到异常低价: {with_weighted}\n异常低价次数: {total_abnormal}\n耗时: {elapsed:.0f}s",
        "fetch_failed_title": "拉取失败",
        "fetch_failed_msg": "市场价格拉取失败:\n{error}\n\n请检查网络连接后重试。",
    },

    # ── 主题字段标签（theme_fields.py 中 THEME_FIELDS 使用）──
    "theme_field": {
        "cyber_yellow": "标题/高亮文字",
        "cyber_cyan": "数据/数值文字",
        "cyber_magenta": "装饰品红色",
        "cyber_orange": "警告提示色",
        "cyber_red": "错误/入库标注",
        "cyber_green": "成功/出库标注",
        "cyber_blue": "辅助蓝色",
        "dark_bg": "窗口背景",
        "panel_bg": "页面底色",
        "card_bg": "输入框/卡片底色",
        "border": "所有边框线",
        "text": "正文/日志文字",
        "text_dim": "提示/次要文字",
        "label_default": "统计标签文字",
        "panel_darkest": "最深底色（日志区）",
        "panel_deeper": "次深底色（代码框）",
        "color_vaulted": "遗物出库标注",
        "color_available": "遗物入库标注",
        "color_unknown": "遗物未知标注",
        "color_gold": "金部件·稀有",
        "color_silver": "银部件·罕见",
        "color_copper": "铜部件·常见",
        "log_ok": "日志 [成功]",
        "log_warn": "日志 [警告]",
        "log_error": "日志 [错误]",
        "log_info": "日志 [信息]",
        "log_debug": "日志 [调试]",
        "log_timestamp": "日志 时间戳",
        "btn_default_bg": "普通按钮 背景",
        "btn_default_text": "普通按钮 文字",
        "btn_default_border": "普通按钮 边框",
        "btn_hover_bg": "普通按钮 悬停背景",
        "btn_hover_text": "普通按钮 悬停文字",
        "btn_hover_border": "普通按钮 悬停边框",
        "btn_pressed_bg": "普通按钮 按下背景",
        "btn_disabled_bg": "禁用按钮 背景",
        "btn_disabled_text": "禁用按钮 文字",
        "btn_disabled_border": "禁用按钮 边框",
        "primary_bg": "蓝色主按钮 背景",
        "primary_text": "蓝色主按钮 文字",
        "primary_border": "蓝色主按钮 边框",
        "primary_hover_bg": "蓝色主按钮 悬停背景",
        "primary_hover_border": "蓝色主按钮 悬停边框",
        "primary_disabled_bg": "蓝色主按钮 禁用背景",
        "primary_disabled_text": "蓝色主按钮 禁用文字",
        "primary_disabled_border": "蓝色主按钮 禁用边框",
        "danger_text": "红色危险按钮 文字",
        "danger_border": "红色危险按钮 边框",
        "danger_hover_bg": "红色危险按钮 悬停背景",
        "danger_hover_text": "红色危险按钮 悬停文字",
        "success_text": "绿色成功按钮 文字",
        "success_border": "绿色成功按钮 边框",
        "success_hover_bg": "绿色成功按钮 悬停背景",
        "success_hover_text": "绿色成功按钮 悬停文字",
        "brand_bilibili": "B站链接 默认色",
        "brand_bilibili_hover": "B站链接 悬停色",
        "brand_github": "GitHub链接 默认色",
        "brand_github_hover": "GitHub链接 悬停色",
        "overlay_crosshair_color": "截图准星",
        "overlay_selection_border": "截图框选边框",
        "progress_gradient_start": "进度条 左端色",
        "progress_gradient_mid": "进度条 中间色",
        "progress_gradient_end": "进度条 右端色",
        "fetch_manual_hint": "下载提示色",
        "fetch_error_color": "下载失败色",
        "price_sell": "卖价文字色",
        "price_buy": "买价文字色",
        "price_median": "中位价文字色",
    },
    "theme_cat": {
        "main_color": "界面主色",
        "panel_bg": "面板背景",
        "relic_status": "遗物状态",
        "part_rarity": "部件稀有度",
        "log_color": "日志颜色",
        "btn_style": "按钮样式",
        "brand": "外链品牌",
        "overlay": "游戏覆盖层",
    },

}
