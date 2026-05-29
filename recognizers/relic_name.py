import re
import time
import numpy as np
from rapidocr_onnxruntime import RapidOCR


class RelicNameRecognizer:
    """从遗物选择界面截图中识别所有遗物名称"""

    RELIC_PATTERN = re.compile(
        r'(古纪|前纪|中纪|后纪|安魂|先锋)[\s.,，。、]*([A-TV-Z0-9]\d+)'
    )

    TRASH_PATTERN = re.compile(r'^[xX]\d+$|^$$.*[$$】]$|^不装备遗物$')

    OCR_FIX_MAP = str.maketrans({
        '\u2018': 'L', '\u2019': 'L',
        ',': 'L', '|': 'I', ';': 'L',
    })

    def __init__(self):
        self._ocr = RapidOCR(text_score=0.35, box_thresh=0.2)

    @staticmethod
    def _fix_ocr_number(code: str) -> str:
        if code and code[0].isdigit():
            mapping = {'0': 'O', '1': 'I', '5': 'S', '8': 'B'}
            code = mapping.get(code[0], code[0]) + code[1:]
        return code

    @staticmethod
    def _resize_fast(img: np.ndarray, scale: float) -> np.ndarray:
        import cv2
        h, w = img.shape[:2]
        return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)

    def recognize_all_with_boxes(self, image: np.ndarray) -> list[tuple[str, list]]:
        t0 = time.perf_counter()

        h, w = image.shape[:2]
        if w > 900:
            scale = 1.5
            big = self._resize_fast(image, scale)
        else:
            scale = 1.0
            big = image

        result, _ = self._ocr(big)
        if result is None:
            return []

        relics = []
        for item in result:
            # ★ 兼容 RapidOCR 不同返回格式：(box,text,score) / (text,score) / 其他
            if len(item) == 3:
                box, text, score = item
            elif len(item) == 2:
                # 可能是 (text, score) 格式，跳过无框结果
                continue
            else:
                continue

            if not isinstance(text, str):
                continue
            text = text.strip()
            if self.TRASH_PATTERN.match(text):
                continue

            cleaned = text.translate(self.OCR_FIX_MAP)
            matches = self.RELIC_PATTERN.findall(cleaned)

            for era, code in matches:
                code = self._fix_ocr_number(code)
                name = f"{era} {code}"
                scaled_box = [[p[0] / scale, p[1] / scale] for p in box] if scale != 1.0 else box
                relics.append((name, scaled_box))

        elapsed = (time.perf_counter() - t0) * 1000
        print(f"[OCR] {len(relics)} 条遗物, {elapsed:.0f}ms")
        return relics
