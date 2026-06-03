"""修复国际化字符串缺失问题"""

import os

# 需要添加的字符串
button_strings = {
    "upload_bg": "上传背景图",
    "clear_bg": "清除背景图"
}

theme_strings = {
    "opacity": "透明度",
    "blur": "模糊度",
    "select_bg_title": "选择背景图片",
    "bg_uploaded": "背景图上传成功",
    "bg_upload_failed": "背景图上传失败",
    "bg_cleared": "背景图已清除"
}

# 更新三个预设文件
preset_files = [
    "data/preset_normal.py",
]

for file_path in preset_files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 在 button 部分添加新键
    content = content.replace(
        '"refresh_preview": "刷新预览",',
        '"refresh_preview": "刷新预览",\n        "upload_bg": "上传背景图",\n        "clear_bg": "清除背景图",'
    )
    
    # 在 theme 部分添加新键
    content = content.replace(
        '"color_pick_title": "选择颜色 - {field}",',
        '"color_pick_title": "选择颜色 - {field}",\n        "opacity": "透明度",\n        "blur": "模糊度",\n        "select_bg_title": "选择背景图片",\n        "bg_uploaded": "背景图上传成功",\n        "bg_upload_failed": "背景图上传失败",\n        "bg_cleared": "背景图已清除",'
    )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"{file_path} 更新完成")

print("所有预设文件已更新")
