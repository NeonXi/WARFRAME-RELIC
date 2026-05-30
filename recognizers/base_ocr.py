"""
统一 OCR 管线基类

提取三个识别器（RelicNameRecognizer / ItemNameRecognizer / ModNameRecognizer）
的公共样板代码：
  - RapidOCR 初始化
  - 图片上采样
  - OCR 结果迭代（去空、垃圾过滤）
  - 坐标缩放
  - 垂直相邻行合并（处理跨行文本）
  - 耗时统计

子类只需实现 _build_lines() 返回 [(text, box), ...]，即可复用完整管线。
"""

import time
import re
import numpy as np
import cv2
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from core.constants import OCR_TEXT_SCORE, OCR_BOX_THRESH, OCR_UPSCALE_MIN_WIDTH, OCR_UPSCALE_SCALE


class BaseOCR:
    """OCR 管线基类。子类覆盖以下钩子即可自定义行为。"""

    # ---- 子类可覆盖的配置 ----

    # 垃圾文本过滤正则（每个识别器不同）
    TRASH_PATTERN: re.Pattern = re.compile(r'(?!)')  # 默认不过滤

    # 合并相邻行时的空格分隔符（英文用空格，中文不用）
    MERGE_SEPARATOR: str = ' '

    # 合并条件参数
    MERGE_VERTICAL_GAP_RATIO: float = 1.2   # 垂直间距 < 平均行高 * 此值
    MERGE_OVERLAP_RATIO: float = 0.3         # 水平重叠 > 此值

    def __init__(self):
        self._ocr = RapidOCR(text_score=OCR_TEXT_SCORE, box_thresh=OCR_BOX_THRESH)

    # ---- 图片工具 ----

    @staticmethod
    def _resize_fast(img: np.ndarray, scale: float) -> np.ndarray:
        """快速放大图片（PIL BILINEAR）。"""
        h, w = img.shape[:2]
        pil_img = Image.fromarray(img)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
        return np.array(pil_img)

    # ---- 框工具 ----

    @staticmethod
    def _box_center_y(box) -> float:
        ys = [p[1] for p in box]
        return sum(ys) / len(ys)

    @staticmethod
    def _box_height(box) -> float:
        ys = [p[1] for p in box]
        return max(ys) - min(ys)

    @staticmethod
    def _horizontal_overlap(a, b) -> float:
        """两框在水平方向的重叠比例（以较窄框为基准）。"""
        a_xs = [p[0] for p in a]
        b_xs = [p[0] for p in b]
        a_left, a_right = min(a_xs), max(a_xs)
        b_left, b_right = min(b_xs), max(b_xs)
        inter = max(0, min(a_right, b_right) - max(a_left, b_left))
        min_w = min(a_right - a_left, b_right - b_left)
        if min_w <= 0:
            return 0.0
        return inter / min_w

    @staticmethod
    def _scale_box(box, scale: float) -> list:
        """将放大后的坐标缩放回原始尺寸。"""
        if scale == 1.0:
            return box
        return [[p[0] / scale, p[1] / scale] for p in box]

    @staticmethod
    def _merge_box(a, b) -> list:
        """取两个框的外接矩形。"""
        return [
            [min(a[0][0], b[0][0]), min(a[0][1], b[0][1])],
            [max(a[1][0], b[1][0]), min(a[0][1], b[0][1])],
            [max(a[2][0], b[2][0]), max(a[2][1], b[2][1])],
            [min(a[3][0], b[3][0]), max(a[2][1], b[2][1])],
        ]

    # ---- 行合并 ----

    def merge_adjacent_lines(
        self, candidates: list[tuple[str, list]]
    ) -> list[tuple[str, list]]:
        """合并垂直相邻的行（处理跨行名称）。

        条件: 水平重叠 > MERGE_OVERLAP_RATIO 且 垂直间距 < MERGE_VERTICAL_GAP_RATIO 倍行高。
        """
        if len(candidates) <= 1:
            return list(candidates)

        sorted_cands = sorted(candidates, key=lambda c: (c[1][0][1], c[1][0][0]))
        merged = []
        used = [False] * len(sorted_cands)

        for i in range(len(sorted_cands)):
            if used[i]:
                continue

            text_i, box_i = sorted_cands[i]
            y_top_i, y_bot_i = box_i[0][1], box_i[2][1]
            x_left_i, x_right_i = box_i[0][0], box_i[1][0]
            height_i = y_bot_i - y_top_i

            best_j = -1
            best_overlap = 0

            for j in range(i + 1, len(sorted_cands)):
                if used[j]:
                    continue

                _, box_j = sorted_cands[j]
                y_top_j, y_bot_j = box_j[0][1], box_j[2][1]
                x_left_j, x_right_j = box_j[0][0], box_j[1][0]
                height_j = y_bot_j - y_top_j

                vertical_gap = y_top_j - y_bot_i
                avg_height = (height_i + height_j) / 2

                if vertical_gap < 0 or vertical_gap > avg_height * self.MERGE_VERTICAL_GAP_RATIO:
                    continue

                overlap_left = max(x_left_i, x_left_j)
                overlap_right = min(x_right_i, x_right_j)
                overlap_width = overlap_right - overlap_left
                if overlap_width <= 0:
                    continue

                min_width = min(x_right_i - x_left_i, x_right_j - x_left_j)
                overlap_ratio = overlap_width / max(min_width, 1)

                if overlap_ratio > self.MERGE_OVERLAP_RATIO and overlap_width > best_overlap:
                    best_overlap = overlap_width
                    best_j = j

            if best_j >= 0:
                text_j, box_j = sorted_cands[best_j]
                merged_text = f"{text_i}{self.MERGE_SEPARATOR}{text_j}"
                merged_box = self._merge_box(box_i, box_j)
                merged.append((merged_text, merged_box))
                used[i] = True
                used[best_j] = True
            else:
                merged.append((text_i, box_i))
                used[i] = True

        return merged

    # ---- 核心管线 ----

    def _run_ocr(self, image: np.ndarray) -> tuple[list, float]:
        """执行 OCR 并返回原始结果列表 + 使用的 scale。"""
        h, w = image.shape[:2]
        if w > OCR_UPSCALE_MIN_WIDTH:
            scale = OCR_UPSCALE_SCALE
            big = self._resize_fast(image, scale)
        else:
            scale = 1.0
            big = image

        # 灰度化（去掉颜色干扰，保留原始纹理）
        if len(big.shape) == 3:
            gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
            gray = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        else:
            gray = big

        result, _ = self._ocr(gray)
        return (result, scale)

    def _iter_ocr_lines(self, result, scale: float) -> list[tuple[str, list]]:
        """迭代 OCR 原始结果，过滤垃圾，缩放坐标，返回 [(text, box), ...]。
        
        子类可覆盖 _filter_text(text) 来定制过滤逻辑。
        """
        lines = []
        if result is None:
            return lines

        for item in result:
            if len(item) != 3:
                continue
            box, text, score = item
            if not isinstance(text, str):
                continue
            text = text.strip()
            if not text:
                continue
            if not self._filter_text(text):
                continue

            box = self._scale_box(box, scale)
            lines.append((text, box))

        return lines

    def _filter_text(self, text: str) -> bool:
        """子类可覆盖：返回 False 过滤掉该文本行。默认使用 TRASH_PATTERN。"""
        return not self.TRASH_PATTERN.match(text)

    # ---- 子类必须实现 ----

    def recognize_all_with_boxes(self, image: np.ndarray) -> list:
        """完整识别流程（子类必须实现）。

        标准模板（子类通常只需覆写 _process_lines）：
            t0 = time.perf_counter()
            result, scale = self._run_ocr(image)
            if result is None:
                return []
            lines = self._iter_ocr_lines(result, scale)
            merged = self.merge_adjacent_lines(lines)
            final = self._process_lines(merged, scale, image)
            elapsed = (time.perf_counter() - t0) * 1000
            self._log_result(final, elapsed)
            return final
        """
        raise NotImplementedError

    def _process_lines(self, lines: list[tuple[str, list]], scale: float,
                       image: np.ndarray) -> list:
        """子类可覆盖：处理合并后的行列表，返回最终结果。"""
        return lines

    def _log_result(self, results: list, elapsed_ms: float):
        """子类可覆盖：打印识别结果日志。"""
        print(f"[OCR] {len(results)} 条结果, {elapsed_ms:.0f}ms", flush=True)
