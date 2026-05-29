import os
from PIL import Image
import numpy as np
from rapidocr_onnxruntime import RapidOCR
from recognizers.relic_name import RelicNameRecognizer

debug_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
img_path = os.path.join(debug_dir, 'last_capture.png')

if not os.path.exists(img_path):
    print("没找到截图！")
    exit()

img = Image.open(img_path).convert("RGB")
frame = np.array(img)[:, :, ::-1]

# 原始 OCR 输出
print("─── 原始 OCR ───")
ocr = RapidOCR()
result, _ = ocr(frame)
if result:
    for box, text, score in result:
        print(f"  {text}  ({score:.2f})")
else:
    print("  (无)")

# 新版识别器
print("─── 新版识别器 ───")
r = RelicNameRecognizer()
relics = r.recognize_all_with_boxes(frame)
for name, box in relics:
    print(f"  {name}")
