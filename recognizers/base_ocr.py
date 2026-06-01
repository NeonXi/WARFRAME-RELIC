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

from core.constants import (
    OCR_UPSCALE_MIN_WIDTH, OCR_UPSCALE_SCALE,
    OCR_ADAPTIVE_UPSCALE_ENABLED, OCR_ADAPTIVE_BASE_WIDTH, 
    OCR_ADAPTIVE_MAX_SCALE, OCR_ADAPTIVE_MIN_SCALE,
    OCR_ENHANCE_CONTRAST, OCR_CLAHE_CLIP_LIMIT, OCR_CLAHE_GRID_SIZE,
    OCR_DYNAMIC_PARAMS_ENABLED, OCR_LARGE_IMAGE_TEXT_SCORE,
    OCR_LARGE_IMAGE_BOX_THRESH, OCR_LARGE_IMAGE_THRESHOLD,
)


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
        # ★ 直接使用 RapidOCR（老架构，简单可靠）
        from rapidocr_onnxruntime import RapidOCR
        from core.constants import RAPIDOCR_TEXT_SCORE, RAPIDOCR_BOX_THRESH
        from core.constants import RAPIDOCR_DET_LIMIT_SIDE_LEN, RAPIDOCR_DET_LIMIT_TYPE
        
        self._ocr = RapidOCR(
            text_score=RAPIDOCR_TEXT_SCORE,
            box_thresh=RAPIDOCR_BOX_THRESH,
            det_limit_side_len=RAPIDOCR_DET_LIMIT_SIDE_LEN,
            det_limit_type=RAPIDOCR_DET_LIMIT_TYPE
        )
        self._large_image_ocr = None  # 延迟初始化，用于大图优化
    
    def _get_ocr_engine(self, image_width: int):
        """根据图像宽度选择合适的OCR引擎。
        
        对于大图（全屏截图），使用更宽松的阈值以提高召回率。
        """
        if not OCR_DYNAMIC_PARAMS_ENABLED or image_width < OCR_LARGE_IMAGE_THRESHOLD:
            return self._ocr
        
        # 延迟初始化大图OCR引擎（更宽松的阈值）
        if self._large_image_ocr is None:
            self._large_image_ocr = self._create_large_image_engine()
        
        return self._large_image_ocr
    
    def _create_large_image_engine(self):
        """创建大图专用的 RapidOCR 引擎（更宽松的阈值）。"""
        from rapidocr_onnxruntime import RapidOCR
        from core.constants import RAPIDOCR_DET_LIMIT_SIDE_LEN, RAPIDOCR_DET_LIMIT_TYPE
        
        print(f"[OCR] 初始化大图RapidOCR引擎 (width>{OCR_LARGE_IMAGE_THRESHOLD}px)", flush=True)
        return RapidOCR(
            text_score=OCR_LARGE_IMAGE_TEXT_SCORE,
            box_thresh=OCR_LARGE_IMAGE_BOX_THRESH,
            det_limit_side_len=RAPIDOCR_DET_LIMIT_SIDE_LEN,
            det_limit_type=RAPIDOCR_DET_LIMIT_TYPE
        )

    # ---- 图片工具 ----

    @staticmethod
    def _resize_fast(img: np.ndarray, scale: float) -> np.ndarray:
        """快速放大图片（PIL BILINEAR）。"""
        h, w = img.shape[:2]
        pil_img = Image.fromarray(img)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
        return np.array(pil_img)

    @staticmethod
    def _enhance_contrast(img: np.ndarray) -> np.ndarray:
        """增强图像对比度（CLAHE自适应直方图均衡化）。
        
        适用于全屏截图等复杂背景场景，提高文字边缘清晰度。
        """
        if not OCR_ENHANCE_CONTRAST:
            return img
        
        if len(img.shape) != 3:
            return img
        
        # 转换到LAB色彩空间
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # 对L通道应用CLAHE
        clahe = cv2.createCLAHE(
            clipLimit=OCR_CLAHE_CLIP_LIMIT, 
            tileGridSize=(OCR_CLAHE_GRID_SIZE, OCR_CLAHE_GRID_SIZE)
        )
        cl = clahe.apply(l)
        
        # 合并通道并转回BGR
        merged = cv2.merge((cl, a, b))
        enhanced = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
        
        return enhanced

    @staticmethod
    def _calculate_adaptive_scale(width: int, height: int) -> float:
        """根据图像尺寸计算自适应上采样倍数。
        
        策略：
        - 小图（宽 < 900px）：不放大，保持原始质量
        - 中图（900-1920px）：线性插值 1.4x ~ 1.8x
        - 大图（> 1920px）：动态计算，确保文字像素密度足够
        """
        if not OCR_ADAPTIVE_UPSCALE_ENABLED:
            return OCR_UPSCALE_SCALE if width > OCR_UPSCALE_MIN_WIDTH else 1.0
        
        # 小图：不放大
        if width < OCR_UPSCALE_MIN_WIDTH:
            return 1.0
        
        # 中图：线性插值
        if width <= 1920:
            ratio = (width - OCR_UPSCALE_MIN_WIDTH) / (1920 - OCR_UPSCALE_MIN_WIDTH)
            scale = 1.4 + ratio * 0.4  # 1.4 ~ 1.8
            return min(scale, OCR_ADAPTIVE_MAX_SCALE)
        
        # 大图：基于基准宽度计算，确保文字不会太小
        base_scale = OCR_ADAPTIVE_BASE_WIDTH / width
        adaptive_scale = max(OCR_ADAPTIVE_MIN_SCALE, 1.0 / base_scale * 1.5)
        return min(adaptive_scale, OCR_ADAPTIVE_MAX_SCALE)

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
        """执行 OCR 并返回原始结果列表 + 使用的 scale。
        
        优化流程：
        1. 自适应上采样（根据图像尺寸动态调整放大倍数）
        2. 对比度增强（CLAHE，适用于复杂背景）
        3. 灰度化处理
        4. OCR识别
        """
        
        h, w = image.shape[:2]
        
        # 步骤1：计算自适应上采样倍数
        scale = self._calculate_adaptive_scale(w, h)
        
        if scale > 1.0:
            big = self._resize_fast(image, scale)
            print(f"[OCR] 图像尺寸 {w}x{h}, 上采样倍数 {scale:.2f}x", flush=True)
        else:
            big = image
        
        # 步骤2：对比度增强（仅对大图/全屏截图启用）
        if scale >= 1.5 and len(big.shape) == 3:
            big = self._enhance_contrast(big)
            print(f"[OCR] 已应用对比度增强", flush=True)
        
        # 步骤3：灰度化（去掉颜色干扰，保留原始纹理）
        if len(big.shape) == 3:
            gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
            gray = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        else:
            gray = big

        # 步骤4：选择合适的OCR引擎并执行识别
        ocr_engine = self._get_ocr_engine(w)
        
        result, _ = ocr_engine(gray)
        
        if scale > 1.0:
            print(f"[OCR] 识别完成，使用{'大图优化' if ocr_engine is not self._ocr else '标准'}引擎", flush=True)
        
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
