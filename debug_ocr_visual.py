"""
OCR 分组可视化诊断工具

用法：
  1. 运行主程序，框选物品区域截一张图
  2. 运行: python debug_ocr_visual.py
  3. 查看生成的 debug/ocr_debug.png 图片和 ocr_debug.log 日志

输出：
  - 图片上每个 OCR 文本框用不同颜色标记
  - 同一 slot 内的文本用相同颜色的矩形框住
  - 详细日志记录分组的每一步
"""
import os
import sys
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from rapidocr_onnxruntime import RapidOCR

# 设置项目路径
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

APPDATA = os.getenv('APPDATA', os.path.expanduser('~'))
DEBUG_DIR = os.path.join(APPDATA, 'WARFRAME-RELIC', 'debug')
os.makedirs(DEBUG_DIR, exist_ok=True)

IMG_PATH = os.path.join(DEBUG_DIR, 'last_capture.png')
OUT_IMG = os.path.join(DEBUG_DIR, 'ocr_debug.png')
OUT_LOG = os.path.join(DEBUG_DIR, 'ocr_debug.log')

if not os.path.exists(IMG_PATH):
    print(f"❌ 没找到截图: {IMG_PATH}")
    print("   请先运行主程序，框选区域并触发一次截图。")
    sys.exit(1)

# ============================================================
# 加载截图
# ============================================================
img = Image.open(IMG_PATH).convert("RGB")
frame = np.array(img)[:, :, ::-1]  # RGB → BGR
h, w = frame.shape[:2]
print(f"截图尺寸: {w}x{h}")

# ============================================================
# OCR 全量识别
# ============================================================
print("运行 OCR ...")
from recognizers.item_name import ItemNameRecognizer
recognizer = ItemNameRecognizer()

# 直接跑 OCR 拿到原始结果
result, scale = recognizer._run_ocr(frame)
if result is None:
    print("❌ OCR 无结果")
    sys.exit(1)

# 收集所有 OCR 行
lines = []
for item in result:
    if len(item) != 3:
        continue
    box, text, score = item
    if not isinstance(text, str):
        continue
    text = text.strip().rstrip('!?.,;:\'"\\')
    if not text:
        continue
    box = recognizer._scale_box(box, scale)
    lines.append((text, box, score))

print(f"\nOCR 原始结果: {len(lines)} 行")
for i, (text, box, score) in enumerate(lines):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    cx = sum(xs) / 4
    cy = sum(ys) / 4
    bw = max(xs) - min(xs)
    bh = max(ys) - min(ys)
    print(f"  [{i:2d}] score={score:.3f} x={cx:6.0f} y={cy:6.0f} w={bw:5.0f} h={bh:4.0f} | \"{text}\"")

# ============================================================
# 完整识别流程
# ============================================================
print("\n" + "=" * 70)
print("完整识别流程 (位置分组)")
print("=" * 70)

# 模拟策略B：直接走位置分组
from recognizers.item_name import (
    _RE_EN_NAME, _RE_TRASH, _RE_RELIC, _RE_NOT_ITEM,
    _is_valid_item_text,
)

# 过滤（使用 _is_valid_item_text，支持中英混合）
filtered_lines = []
for text, box, score in lines:
    if _RE_RELIC.search(text):
        print(f"  [过滤-遗物] \"{text}\"")
        continue
    if _RE_TRASH.search(text):
        print(f"  [过滤-垃圾] \"{text}\"")
        continue
    if _RE_NOT_ITEM.search(text):
        print(f"  [过滤-短词] \"{text}\"")
        continue
    if not _is_valid_item_text(text):
        print(f"  [过滤-非物品] \"{text}\"")
        continue
    filtered_lines.append((text, box))

print(f"\n过滤后: {len(filtered_lines)} 行")
for i, (text, box) in enumerate(filtered_lines):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    cx = sum(xs) / 4
    cy = sum(ys) / 4
    print(f"  [{i:2d}] x={cx:6.0f} y={cy:6.0f} | \"{text}\"")

if not filtered_lines:
    print("❌ 过滤后无有效行")
    sys.exit(1)

# 分组
print("\n--- 分组过程 ---")
slots = recognizer._group_by_slot(filtered_lines)

print(f"\n最终 {len(slots)} 个 slot:")
for i, (texts, box) in enumerate(slots):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    print(f"  Slot[{i}]: {texts}")
    print(f"          box: x=[{min(xs):.0f},{max(xs):.0f}] y=[{min(ys):.0f},{max(ys):.0f}]")

# ============================================================
# 生成可视化图片
# ============================================================
print("\n生成可视化图片 ...")

# 用 PIL 绘制（比 OpenCV 中文支持好）
draw_img = Image.fromarray(frame[:, :, ::-1])  # BGR → RGB
draw = ImageDraw.Draw(draw_img)

# 10 种颜色循环
COLORS = [
    (255, 50, 50), (50, 255, 50), (50, 50, 255),
    (255, 200, 0), (200, 0, 255), (0, 255, 200),
    (255, 100, 100), (100, 255, 100), (100, 100, 255),
    (255, 255, 100),
]

# 画每个 slot 的边界框
for i, (texts, box) in enumerate(slots):
    color = COLORS[i % len(COLORS)]
    pts = [(p[0], p[1]) for p in box]
    # 画矩形
    draw.rectangle([pts[0], pts[2]], outline=color, width=2)
    # 画标签
    label = f"S{i}: {' '.join(texts[:2])}"
    draw.text((pts[0][0] + 2, pts[0][1] - 14), label, fill=color)

# 画每个 OCR 文本框（用各自 slot 的颜色）
# 先重建行到 slot 的映射
line_to_slot = {}
for si, (texts, sbox) in enumerate(slots):
    for t in texts:
        for li, (lt, lb) in enumerate(filtered_lines):
            if lt == t and li not in line_to_slot:
                line_to_slot[li] = si
                break

for li, (text, box) in enumerate(filtered_lines):
    si = line_to_slot.get(li, -1)
    color = COLORS[si % len(COLORS)] if si >= 0 else (128, 128, 128)
    pts = [(p[0], p[1]) for p in box]
    draw.rectangle([pts[0], pts[2]], outline=color, width=1)
    # 小标签
    draw.text((pts[0][0], pts[0][1] - 10), f"L{li}", fill=color)

# 保存
draw_img.save(OUT_IMG)
print(f"✅ 可视化图片已保存: {OUT_IMG}")

# 保存日志
log_lines = []
log_lines.append(f"截图尺寸: {w}x{h}")
log_lines.append(f"OCR 原始: {len(lines)} 行")
log_lines.append(f"过滤后: {len(filtered_lines)} 行")
log_lines.append(f"分组结果: {len(slots)} 个 slot")
log_lines.append("")
for i, (texts, box) in enumerate(slots):
    log_lines.append(f"Slot[{i}]: {texts}")
with open(OUT_LOG, 'w', encoding='utf-8') as f:
    f.write('\n'.join(log_lines))
print(f"✅ 日志已保存: {OUT_LOG}")

print("\n完成！请查看:")
print(f"  图片: {OUT_IMG}")
print(f"  日志: {OUT_LOG}")
