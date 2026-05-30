"""
离线调试脚本：测试 OCR 识别器

用法：
  1. 运行主程序，框选物品区域截一张图
  2. 运行本脚本查看识别结果
"""
import os
from PIL import Image
import numpy as np
from rapidocr_onnxruntime import RapidOCR
from recognizers.relic_name import RelicNameRecognizer
from recognizers.item_name import ItemNameRecognizer

debug_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
img_path = os.path.join(debug_dir, 'last_capture.png')

if not os.path.exists(img_path):
    print("没找到截图！请先运行主程序截一张图。")
    exit()

img = Image.open(img_path).convert("RGB")
frame = np.array(img)[:, :, ::-1]  # RGB → BGR
h, w = frame.shape[:2]
print(f"截图尺寸: {w}x{h}")

# ============================================================
# 1. 物品识别
# ============================================================
print("\n" + "=" * 50)
print("─── 物品名识别 ───")
item_ocr = ItemNameRecognizer()
items = item_ocr.recognize_all_with_boxes(frame)
for name, box, variants in items:
    print(f"  {name}")
    if variants:
        print(f"    纠错候选: {variants}")

# ============================================================
# 2. 原始 OCR（调试用）
# ============================================================
print("\n" + "=" * 50)
print("─── 原始 OCR 全部文本 ───")
ocr = RapidOCR()
result, _ = ocr(frame)
if result:
    for box, text, score in result:
        print(f"  [{score:.2f}] {text}")
else:
    print("  (无)")

print("\n完成！")
