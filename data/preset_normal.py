"""
WARFRAME-RELIC UI 字符串预设 — 普通风格
所有在 UI 中展示的字符串都写在这里，方便维护和未来国际化。
"""

STRINGS = {
    # ── 窗口标题 ──
    "window_title": {
        "management_panel": "WARFRAME RELICS · 管理面板",
    },

    # ── 标题 ──
    "title": {
        "management_panel": "WARFRAME RELICS",
    },

    # ── 按钮 ──
    "button": {
        "exit": "退出程序",
        "reload_ui": "重新加载界面",
        "data_center": "后台数据中心",
        "browse_file": "浏览文件",
        "update_tutorial": "更新教程",
        "open_data_dir": "打开数据目录",
        "open_market_query": "打开市场查询",
        "save_hotkeys": "保存热键",
        "reset_default": "恢复默认",
        "reset_state": "重置状态",
        "reload_hotkeys": "重新加载热键",
        "custom_theme": "自定义主题",
        "bilibili_home": "B站主页",
        "github_repo": "GitHub 仓库",
        "close_log_panel": "关闭日志面板",
        "apply_preset": "应用预设",
        "upload_bg": "上传背景",
        "clear_bg": "清除背景",
        "save_theme": "保存主题",
        "refresh_preview": "刷新预览",
        # overlay 模式按钮
        "mode_check": "遗物鉴定",
        "mode_query": "掉落查询",
        "mode_price": "价格查询",
        "mode_translate": "翻译模式",
    },

    # ── 分组标题 ──
    "group": {
        "feature_toggles": "功能开关",
        "data_overview": "数据概览",
        "db_center": "数据库中心",
        "item_index": "物品索引",
        "wm_prices": "市场价格",
        "hotkey_settings": "热键设置",
        "recovery": "恢复",
        "theme": "主题",
        "about_author": "关于作者",
        "lang_preset": "语言风格",
    },

    # ── 功能开关 ──
    "feature_toggle": {
        "hint": "勾选启用功能，取消勾选禁用。更改后自动保存。",
        "save_failed": "功能开关保存失败",
        # 动态键: desc_{key}, label_{key} — key 对应 DEFAULT_FEATURE_TOGGLES
        "desc_check_status": "识别遗物名称后自动查询出入库状态",
        "desc_query_parts": "识别遗物名称后自动查询内含物掉落表",
        "desc_translate": "识别英文文字后自动翻译为中文",
        "label_check_status": "出入库查询",
        "label_query_parts": "遗物内容查询",
        "label_translate": "自动翻译",
    },

    # ── 统计标签 ──
    "stat_label": {
        "relics_summary": "遗物总数",
        "relic_vault": "入库/出库",
        "items_summary": "物品总数",
        "db_size": "数据库大小",
        "last_update": "上次更新",
    },

    # ── 统计格式化（S.format("stat_fmt", key, **kwargs)）──
    "stat_fmt": {
        "relics_summary": "{relics} 个遗物 / {parts} 条奖励",
        "relic_vault": "出库 {available} / 入库 {vaulted}",
        "items_summary": "{total:,} 个物品 / {has_cn:,} 条翻译 / {size:.0f} KB",
        "db_size_kb": "{size:.0f} KB",
    },

    # ── 搜索 ──
    "search": {
        "no_match": "未找到匹配「{query}」的物品",
        "mode_result": "找到 {count} 个匹配项",
        "copied": "已复制: {name}",
    },

    # ── 状态 ──
    "status": {
        "placeholder": "—",
        "db_not_exist": "未找到",
        "db_corrupted": "数据库损坏: {error}",
        "db_no_permission": "无权限访问: {error}",
        "items_summary_none": "未加载",
        "items_summary_error": "加载失败",
    },

    # ── 提示 ──
    "hint": {
        "data_source_db_center": "数据源: warframe.db (统一数据库)",
        "data_source_items": "数据源: warframe.db items 表",
        "data_source_wm": "数据源: warframe.market API",
        "items_search_placeholder": "输入物品英文名搜索...",
        "items_search_default": "输入关键词开始搜索",
        "items_search_error": "搜索出错，请检查输入",
        "items_no_translation": "无中文翻译",
        "recovery": "如果程序出现异常，可以尝试以下恢复操作。",
        "about_author": "WARFRAME 遗物助手 — 快速识别遗物、查询掉落与价格",
        "theme_tip": "选择预设后点击「应用预设」，或手动调整各项颜色。",
    },

    # ── 覆盖层 ──
    "overlay": {
        "relic_vaulted": "已入库",
        "relic_available": "可获取",
        "query_legend": "\n━━━━━━━━━━━━━━━━━━\n[ 鉴定 ] 遗物名称 | [ 查询 ] 掉落来源",
        "no_text_detected": "未检测到文字",
        "translate_failed": "翻译失败",
        "no_items_detected": "未检测到物品",
        "please_select_first": "请先框选区域",
        "screenshot_failed": "截图失败",
        "fullscreen_failed": "全屏截图失败",
        "price_query_scanning": "价格查询中...",
        "screenshot_done": "截图完成",
        "please_screenshot_first": "请先截图",
        "ocr_recognizing": "OCR 识别中...",
        "no_features_enabled": "请先在管理面板中启用功能",
        "selection_status_idle": "按住鼠标左键拖拽框选",
        "selection_status_released": "框选完成",
        "selection_cancelled": "框选已取消",
        "mode_selected": "已选择: {mode}",
        "annotations_shown": "已标注 {count} 条",
        "relic_no_parts_info": "{name} 无掉落数据",
        "query_summary": "匹配 {matched}/{total} 个遗物",
        "query_summary_fmt": "匹配 {matched}/{total} 个遗物 (未匹配: {unmatched})",
        "translate_label_fmt": "{zh_name} ({en_name})",
        "translate_summary": "翻译: {total} 个候选, 匹配 {matched} 个",
        "price_query_summary": "价格查询: {total} 个物品, {with_price} 个有价格",
    },

    # ── 日志 ──
    "log": {
        "panel_title": "操作日志",
        "waiting": "等待中...",
    },

    # ── 日志消息 ──
    "log_msg": {
        "reset_start": "正在重置状态...",
        "reset_done": "状态已重置",
        "hotkeys_reloaded": "热键已重新加载",
        "startup": "WARFRAME 遗物助手已启动",
        "startup_select": "按 {hk} 框选截图识别遗物/物品",
        "startup_fullscreen": "按 {hk} 全屏截图识别",
        "startup_query_price": "按 {hk} 查询市场价格",
        "startup_right_click": "右键点击托盘图标可打开管理面板",
        "startup_mode_hint": "可用模式:",
        "startup_mode_check": "  [ 鉴定 ] 识别遗物名称，查询掉落表",
        "startup_mode_query": "  [ 查询 ] 识别物品名称，查询掉落来源",
        "startup_mode_price": "  [ 价格 ] 识别物品名称，查询市场价格",
        "startup_mode_translate": "  [ 翻译 ] 识别文字，翻译为中文",
        "startup_db_info": "数据库: {total} 个遗物 | 出库 {available} | 入库 {vaulted}",
    },

    # ── 热键 ──
    "hotkey": {
        "label_select": "框选截图",
        "label_fullscreen": "全屏截图",
        "label_query_price": "价格查询",
        "reset_confirm_title": "确认重置",
        "reset_confirm_msg": "确定要恢复默认热键设置吗？",
        "reset_done_title": "重置完成",
        "reset_done_msg": "热键已恢复为默认设置",
    },

    # ── 退出 ──
    "exit": {
        "confirm_title": "确认退出",
        "confirm_msg": "确定要退出 WARFRAME 遗物助手吗？",
    },

    # ── 更新 ──
    "update": {
        "browse_dialog_title": "选择数据文件",
        "browse_filter": "JSON 文件 (*.json);;所有文件 (*.*)",
        "source_current": "数据源: {path}",
        "source_not_found": "数据源未找到: {path}",
    },

    # ── 教程 ──
    "tutorial": {
        "relic_title": "遗物数据更新教程",
        "relic_content": (
            "遗物数据更新流程\n\n"
            "1. 点击「更新基础数据」按钮\n"
            "   程序会自动从 WFCD 仓库拉取最新数据\n"
            "   然后构建统一数据库 warframe.db\n\n"
            "2. 如果网络不通，可以手动下载 JSON 文件\n"
            "   放置到 data 目录下，然后点击「浏览」选择文件\n\n"
            "3. 数据目录: {data_dir}\n\n"
            "4. 点击「拉取市场价格」可单独更新价格数据\n"
            "   价格来自 warframe.market API"
        ),
    },

    # ── 主题 ──
    "theme": {
        "panel_title": "主题设置",
        "preset_label": "选择预设:",
        "opacity": "背景透明度",
        "blur": "背景模糊",
        "panel_overlay": "覆盖层透明度",
        "custom_bg": "自定义背景",
        "prompt_title": "提示",
        "no_changes_preview": "没有需要预览的更改",
        "no_changes": "没有需要保存的更改",
        "select_bg_title": "选择背景图片",
        "bg_uploaded": "背景图片已设置",
        "bg_upload_failed": "背景图片设置失败",
        "bg_cleared": "背景已清除",
        "preset_failed": "预设应用失败",
        "reset_confirm_title": "确认重置",
        "reset_done_title": "重置完成",
        "save_failed": "主题保存失败",
    },

    # ── 主题字段 ──
    "theme_field": {
        "cyber_yellow": "赛博黄",
        "cyber_cyan": "赛博青",
        "cyber_magenta": "赛博品红",
        "cyber_orange": "赛博橙",
        "cyber_red": "赛博红",
        "cyber_green": "赛博绿",
        "panel_bg": "面板背景",
        "card_bg": "卡片背景",
        "border": "边框",
        "text": "文字",
        "text_dim": "暗淡文字",
        "label_default": "默认标签",
        "panel_overlay_rgb": "覆盖层",
        "color_unknown": "未知状态",
        "color_gold": "金色 (稀有)",
        "color_silver": "银色 (罕见)",
        "color_copper": "铜色 (常见)",
        "btn_default_bg": "按钮背景",
        "btn_default_text": "按钮文字",
        "btn_default_border": "按钮边框",
        "btn_hover_bg": "悬停背景",
        "btn_hover_text": "悬停文字",
        "btn_hover_border": "悬停边框",
        "btn_pressed_bg": "按下背景",
        "btn_disabled_bg": "禁用背景",
        "btn_disabled_text": "禁用文字",
        "btn_disabled_border": "禁用边框",
        "brand_bilibili": "B站品牌色",
        "brand_bilibili_hover": "B站悬停色",
        "brand_github": "GitHub 品牌色",
        "brand_github_hover": "GitHub 悬停色",
        "progress_gradient_start": "进度条起始",
        "progress_gradient_mid": "进度条中间",
        "progress_gradient_end": "进度条结束",
        "fetch_manual_hint": "手动提示色",
        "fetch_error_color": "错误色",
    },

    # ── 主题分类 ──
    "theme_cat": {
        "main_color": "主色调",
        "panel_bg": "面板",
        "relic_status": "遗物状态",
        "part_rarity": "部件稀有度",
        "btn_style": "按钮样式",
        "brand": "品牌色",
        "overlay": "覆盖层",
    },

    # ── 数据中心 ──
    "data_center": {
        "nav_data_link": "数据链路",
        "nav_db_info": "数据库信息",
        "nav_json_viewer": "JSON 查看器",
        "db_status_ok": "数据库正常",
        "db_status_missing": "数据库未找到",
        "table_list_title": "表列表",
        "schema_title": "表结构",
        "query_title": "数据查询",
        "col_table": "表名",
        "col_category": "分类",
        "col_rows": "行数",
        "col_columns": "列数",
        "col_field": "字段",
        "col_type": "类型",
        "col_notnull": "非空",
        "col_default": "默认值",
        "col_pk": "主键",
        "btn_refresh": "刷新",
        "btn_execute_query": "执行查询",
        "hint_select_table": "请先选择数据库表",
        "hint_query_ready": "就绪 — 选择表后添加筛选条件，或直接点击「执行查询」查看全部数据",
        "label_select_table": "选择表:",
        "label_filter": "筛选条件",
        "placeholder_value": "值",
        "status_ready": "就绪",
        "summary_status": "状态",
        "summary_tables": "表数",
        "summary_total_rows": "总行数",
        "summary_file_size": "文件大小",
    },

    # ── JSON 查看器 ──
    "json_viewer": {
        "search_placeholder": "搜索 key 或 value（Enter 搜索，Esc 关闭）...",
        "search_btn": "搜索",
        "info_hint": "点击 JSON 树中的节点查看详情",
    },

    # ── 代理镜像 ──
    "proxy_mirror": {
        "reset_default": "恢复默认",
        "test_connectivity": "测试连通性",
    },

    # ── 热键录制 ──
    "hotkey_capture": {
        "press_combo": "按下组合键...",
        "click_to_set": "点击设置",
    },

    # ── 启动画面 ──
    "splash": {
        "starting": "正在启动...",
    },

    # ── 管理面板 ──
    "management": {
        "price_no_region": "当前无可用区域，请先设置",
        "price_set_hint": "设置",
        "price_clear_hint": "清除",
        "price_not_set": "未设置",
        "download_source": "下载源:",
        "update_base_data": "更新基础数据",
        "fetch_market_prices": "拉取市场价格",
        "proxy_mirrors": "代理镜像",
        "hotkey_tip": "点击按钮后按下组合键即可录制，按 Esc 取消",
        "current_style": "当前风格：",
        "init_progress": "初始化...",
        "fetch_complete": "拉取完成",
        "update_complete": "更新完成",
        "update_failed": "更新失败",
        "hint": "提示",
        "close": "关闭",
        "update_base_confirm": "将按顺序执行以下步骤：\n\n1. Git 稀疏检出 WFCD 数据 (all.json + i18n.json + All.json)\n2. 构建统一数据库 warframe.db (25 张表)\n\n预计耗时: 2-3 分钟\n确认开始？",
        "fetch_prices_confirm": "将从 warframe.market API 拉取最新卖价数据。\n\n仅拉取卖价，含反压价权重机制\n偏离中位数 >30% 的低价权重降为 0.1\n\n速率限制: 每秒 3 个请求\n预计耗时: 10-15 分钟\n\n确认开始？",
    },
}
