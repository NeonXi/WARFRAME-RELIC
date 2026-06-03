"""
主题编辑字段定义

THEME_FIELDS — 管理面板中每个可编辑色块的元信息（json_key, 标签, 类别）
标签字符串从 data.ui_strings 中读取。
"""

from data.ui_strings import S

# ============================================================
# 主题编辑字段定义
# ============================================================

THEME_FIELDS = [
    # (json_key, 通俗标签, 类别)
    # ---- 霓虹主色 (6) ----
    ("cyber_yellow",    S("theme_field", "cyber_yellow"),    S("theme_cat", "main_color")),
    ("cyber_cyan",      S("theme_field", "cyber_cyan"),      S("theme_cat", "main_color")),
    ("cyber_magenta",   S("theme_field", "cyber_magenta"),   S("theme_cat", "main_color")),
    ("cyber_orange",    S("theme_field", "cyber_orange"),    S("theme_cat", "main_color")),
    ("cyber_red",       S("theme_field", "cyber_red"),       S("theme_cat", "main_color")),
    ("cyber_green",     S("theme_field", "cyber_green"),     S("theme_cat", "main_color")),
    # ---- 面板背景 (9) ----
    ("panel_bg",        S("theme_field", "panel_bg"),        S("theme_cat", "panel_bg")),
    ("card_bg",         S("theme_field", "card_bg"),         S("theme_cat", "panel_bg")),
    ("panel_darkest",   S("theme_field", "panel_darkest"),   S("theme_cat", "panel_bg")),
    ("panel_deeper",    S("theme_field", "panel_deeper"),    S("theme_cat", "panel_bg")),
    ("border",          S("theme_field", "border"),          S("theme_cat", "panel_bg")),
    ("text",            S("theme_field", "text"),            S("theme_cat", "panel_bg")),
    ("text_dim",        S("theme_field", "text_dim"),        S("theme_cat", "panel_bg")),
    ("label_default",   S("theme_field", "label_default"),   S("theme_cat", "panel_bg")),
    ("panel_overlay_rgb", S("theme_field", "panel_overlay_rgb"), S("theme_cat", "panel_bg")),
    # ---- 遗物状态 (1) ----
    ("color_unknown",   S("theme_field", "color_unknown"),   S("theme_cat", "relic_status")),
    # ---- 稀有度 (3) ----
    ("color_gold",      S("theme_field", "color_gold"),      S("theme_cat", "part_rarity")),
    ("color_silver",    S("theme_field", "color_silver"),    S("theme_cat", "part_rarity")),
    ("color_copper",    S("theme_field", "color_copper"),    S("theme_cat", "part_rarity")),
    # ---- 按钮样式 (24) ----
    ("btn_default_bg",       S("theme_field", "btn_default_bg"),       S("theme_cat", "btn_style")),
    ("btn_default_text",     S("theme_field", "btn_default_text"),     S("theme_cat", "btn_style")),
    ("btn_default_border",   S("theme_field", "btn_default_border"),   S("theme_cat", "btn_style")),
    ("btn_hover_bg",         S("theme_field", "btn_hover_bg"),         S("theme_cat", "btn_style")),
    ("btn_hover_text",       S("theme_field", "btn_hover_text"),       S("theme_cat", "btn_style")),
    ("btn_hover_border",     S("theme_field", "btn_hover_border"),     S("theme_cat", "btn_style")),
    ("btn_pressed_bg",       S("theme_field", "btn_pressed_bg"),       S("theme_cat", "btn_style")),
    ("btn_disabled_bg",      S("theme_field", "btn_disabled_bg"),      S("theme_cat", "btn_style")),
    ("btn_disabled_text",    S("theme_field", "btn_disabled_text"),    S("theme_cat", "btn_style")),
    ("btn_disabled_border",  S("theme_field", "btn_disabled_border"),  S("theme_cat", "btn_style")),
    ("primary_bg",           S("theme_field", "primary_bg"),           S("theme_cat", "btn_style")),
    ("primary_text",         S("theme_field", "primary_text"),         S("theme_cat", "btn_style")),
    ("primary_border",       S("theme_field", "primary_border"),       S("theme_cat", "btn_style")),
    ("primary_hover_bg",     S("theme_field", "primary_hover_bg"),     S("theme_cat", "btn_style")),
    ("primary_hover_border", S("theme_field", "primary_hover_border"), S("theme_cat", "btn_style")),
    ("danger_text",       S("theme_field", "danger_text"),       S("theme_cat", "btn_style")),
    ("danger_border",     S("theme_field", "danger_border"),     S("theme_cat", "btn_style")),
    ("danger_hover_bg",   S("theme_field", "danger_hover_bg"),   S("theme_cat", "btn_style")),
    ("danger_hover_text", S("theme_field", "danger_hover_text"), S("theme_cat", "btn_style")),
    ("success_text",      S("theme_field", "success_text"),      S("theme_cat", "btn_style")),
    ("success_border",    S("theme_field", "success_border"),    S("theme_cat", "btn_style")),
    ("success_hover_bg",  S("theme_field", "success_hover_bg"),  S("theme_cat", "btn_style")),
    ("success_hover_text",S("theme_field", "success_hover_text"),S("theme_cat", "btn_style")),
    # ---- 品牌色 (4) ----
    ("brand_bilibili",       S("theme_field", "brand_bilibili"),       S("theme_cat", "brand")),
    ("brand_bilibili_hover", S("theme_field", "brand_bilibili_hover"), S("theme_cat", "brand")),
    ("brand_github",         S("theme_field", "brand_github"),         S("theme_cat", "brand")),
    ("brand_github_hover",   S("theme_field", "brand_github_hover"),   S("theme_cat", "brand")),
    # ---- 覆盖层 (7) ----
    ("overlay_crosshair_color", S("theme_field", "overlay_crosshair_color"), S("theme_cat", "overlay")),
    ("overlay_selection_border", S("theme_field", "overlay_selection_border"), S("theme_cat", "overlay")),
    ("progress_gradient_start", S("theme_field", "progress_gradient_start"), S("theme_cat", "overlay")),
    ("progress_gradient_mid",   S("theme_field", "progress_gradient_mid"),   S("theme_cat", "overlay")),
    ("progress_gradient_end",   S("theme_field", "progress_gradient_end"),   S("theme_cat", "overlay")),
    ("fetch_manual_hint", S("theme_field", "fetch_manual_hint"), S("theme_cat", "overlay")),
    ("fetch_error_color", S("theme_field", "fetch_error_color"), S("theme_cat", "overlay")),
]
