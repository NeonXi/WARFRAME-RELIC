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

from core.constants import (
    OCR_ENHANCE_CONTRAST, OCR_CLAHE_CLIP_LIMIT, OCR_CLAHE_GRID_SIZE,
    OCR_COLOR_FILTER_ENABLED, OCR_COLOR_FILTER_LOWER, OCR_COLOR_FILTER_UPPER,
    OCR_DEBUG_SAVE_ENABLED, OCR_DEBUG_SAVE_DIR,
)

# 锐化内核（增强文字边缘）
_SHARPEN_KERNEL = np.array([
    [0, -1, 0],
    [-1, 5, -1],
    [0, -1, 0],
], dtype=np.float32)


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

    # 颜色过滤配置（子类覆盖以启用）
    _color_filter_enabled: bool = OCR_COLOR_FILTER_ENABLED
    _color_filter_lower: tuple = OCR_COLOR_FILTER_LOWER   # HSV 下限
    _color_filter_upper: tuple = OCR_COLOR_FILTER_UPPER   # HSV 上限

    # ★ 颜色过滤后是否跳过锐化/灰度化，直接送彩色图给 OCR
    # 当颜色过滤已能清晰分离文字时，锐化+灰度化反而会损失信息
    # 当前关闭：因为颜色过滤后字符边缘有白晕，需要锐化+灰度进一步清理
    _skip_post_color_filter: bool = False

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
        self._timing = {}  # 耗时统计
    
    def _get_ocr_engine(self, image_width: int):
        """返回 OCR 引擎（统一使用主引擎）。"""
        return self._ocr

    # ---- 图片工具 ----

    @staticmethod
    def _resize_fast(img: np.ndarray, scale: float) -> np.ndarray:
        """快速放大图片（cv2 INTER_CUBIC，比 PIL BILINEAR 更快）。"""
        h, w = img.shape[:2]
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    @staticmethod
    def _enhance_contrast(img: np.ndarray) -> np.ndarray:
        """增强图像对比度：CLAHE 自适应直方图均衡化（LAB 亮度通道）。

        优化：跳过 HSV 饱和度掩码，直接 CLAHE 处理 LAB 的 L 通道。
        减少 4→2 次色彩空间转换，大幅降低 CPU 开销。
        """
        if not OCR_ENHANCE_CONTRAST:
            return img
        if len(img.shape) != 3:
            return img

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(
            clipLimit=OCR_CLAHE_CLIP_LIMIT,
            tileGridSize=(OCR_CLAHE_GRID_SIZE, OCR_CLAHE_GRID_SIZE)
        )
        l_enhanced = clahe.apply(l)

        merged = cv2.merge((l_enhanced, a, b))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    @staticmethod
    def _sharpen(img: np.ndarray) -> np.ndarray:
        """锐化图像，增强文字边缘清晰度。"""
        return cv2.filter2D(img, -1, _SHARPEN_KERNEL)

    @staticmethod
    def _filter_by_color(img: np.ndarray, lower: tuple, upper: tuple) -> np.ndarray:
        """基于 HSV 颜色范围过滤图像，与原图混合增强文字同时保留细节。
        
        Args:
            img: BGR 图像
            lower: HSV 下限 (H, S, V)
            upper: HSV 上限 (H, S, V)
        
        Returns:
            增强后的 BGR 图像
        """
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
        # 形态学操作
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)
        # 颜色过滤结果
        filtered = cv2.bitwise_and(img, img, mask=mask)
        # ★ 与原图按比例混合 (0.7原图 + 0.3过滤)
        # 既保留文字颜色增强，又不丢失背景上下文
        return cv2.addWeighted(img, 0.7, filtered, 0.3, 0)

    @staticmethod
    def _save_debug_image(stage: str, img: np.ndarray):
        """保存 OCR 中间处理图到本地（调参用）。"""
        if not OCR_DEBUG_SAVE_ENABLED:
            return
        import os
        import time
        try:
            appdata = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', OCR_DEBUG_SAVE_DIR)
            os.makedirs(appdata, exist_ok=True)
            ts = int(time.time() * 1000)
            path = os.path.join(appdata, f"ocr_{ts}_{stage}.png")
            cv2.imwrite(path, img)
            print(f"[OCR-DEBUG] 保存 {stage} -> {path}", flush=True)
        except Exception as e:
            print(f"[OCR-DEBUG] 保存失败 {stage}: {e}", flush=True)

    @staticmethod
    def _calculate_adaptive_scale(width: int, height: int) -> float:
        """根据图像尺寸计算自适应上采样倍数。

        核心策略：统一目标宽度，让所有尺寸的图放大到相近的文字像素密度。
        全屏截图(1920px)效果好的关键是文字像素足够大，
        所以让小图也放大到同样的文字密度。

        目标宽度 2400px（经验值：全屏1.25x=2400px 时 OCR 效果和速度最佳）
        - 小图(<400px): 放大到 2400px → 约 6x（文字极小，需要激进放大）
        - 中图(400-1920px): 线性插值到 2400px → 1.25x~6x
        - 大图(>1920px): 不放大或轻微放大
        """
        TARGET_WIDTH = 2400  # 目标像素宽度（平衡 OCR 精度和速度）

        if width >= TARGET_WIDTH:
            # 大图已经足够，不需要放大
            return 1.0

        # 小图和中图：放大到目标宽度
        scale = TARGET_WIDTH / width
        return min(scale, 6.0)  # 最大6倍，避免过度放大

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
        
        优化流程（精简为4步，减少冗余处理）：
        1. 自适应上采样（统一目标宽度，小图激进放大）
        2. 灰度化 + CLAHE 对比度增强（合并为一步）
        3. 锐化（增强文字边缘）
        4. OCR 识别
        """
        
        h, w = image.shape[:2]
        self._save_debug_image("00_original", image)

        # 步骤1：自适应上采样
        scale = self._calculate_adaptive_scale(w, h)
        if scale > 1.0:
            big = self._resize_fast(image, scale)
            print(f"[OCR] 自适应上采样: {w}x{h} -> {big.shape[1]}x{big.shape[0]} (scale={scale:.2f}x)", flush=True)
        else:
            big = image
        self._save_debug_image("01_upscaled", big)

        # 步骤2：颜色过滤（可选，仅保留目标颜色文字）
        if self._color_filter_enabled and len(big.shape) == 3:
            big = self._filter_by_color(big, self._color_filter_lower, self._color_filter_upper)
            print(f"[OCR] 已应用颜色过滤 HSV({self._color_filter_lower}~{self._color_filter_upper})", flush=True)
        self._save_debug_image("02_color_filtered", big)

        # 步骤3：灰度化 + CLAHE 对比度增强（合并为一步，减少色彩空间转换开销）
        if len(big.shape) == 3:
            gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        else:
            gray = big.copy()

        if OCR_ENHANCE_CONTRAST:
            clahe = cv2.createCLAHE(
                clipLimit=OCR_CLAHE_CLIP_LIMIT,
                tileGridSize=(OCR_CLAHE_GRID_SIZE, OCR_CLAHE_GRID_SIZE)
            )
            gray = clahe.apply(gray)
        self._save_debug_image("03_contrast", gray)

        # 步骤4：锐化（增强文字边缘）
        gray = self._sharpen(gray)
        self._save_debug_image("04_sharpened", gray)

        # 步骤5：OCR 识别
        ocr_engine = self._get_ocr_engine(w)

        t_ocr = time.perf_counter()
        result, _ = ocr_engine(gray)
        self._timing['ocr_inference'] = (time.perf_counter() - t_ocr) * 1000
        self._save_debug_image("05_ocr_input", gray)

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
