"""
遗物名称识别器

从遗物选择界面截图中识别所有遗物名称（自适应中/英文）。

重构后继承 BaseOCR，消除重复的 OCR 样板代码。
"""

import re
import time
import numpy as np

from recognizers.base_ocr import BaseOCR

# 英文纪元 → 中文纪元映射
_EN_TIER_MAP = {
    "Lith":     "古纪",
    "Meso":     "前纪",
    "Neo":      "中纪",
    "Axi":      "后纪",
    "Requiem":  "安魂",
    "Vanguard": "先锋",
}


class RelicNameRecognizer(BaseOCR):
    """从遗物选择界面截图中识别所有遗物名称（自适应中/英文）。"""

    # ---- 正则 ----

    # 中文纪元正则: 古纪 C7 / 古纪 A12
    CN_PATTERN = re.compile(
        r'(古纪|前纪|中纪|后纪|安魂|先锋)[\s.,，。、]*([A-Za-z0-9]{2,3})')

    # 英文纪元正则: Lith C7 Relic / LithC7Relic / Lith A12 Relic 等
    EN_PATTERN = re.compile(
        r'(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s*([A-Za-z0-9]{2,3})\s*Relic',
        re.IGNORECASE)

    # 垃圾文本过滤
    TRASH_PATTERN = re.compile(
        r'^[xX]\d+$|^$$.*[$$】]$|^不装备遗物$|^(?:无|没有|No)\s*(?:遗物|Relic)', re.IGNORECASE)

    # 品质标签清理：OCR 可能把 "Relic [Radiant]" 识别成一行
    QUALITY_PATTERN = re.compile(
        r'\s*[\[(](?:Radiant|Flawless|Exceptional|Intact)[\])]',
        re.IGNORECASE)

    OCR_FIX_MAP = str.maketrans({
        '\u2018': 'L', '\u2019': 'L', ',': 'L', '|': 'I', ';': 'L',
    })

    # ---- OCR → 标准代码修复映射 ----
    _DIGIT_TO_ALPHA = str.maketrans({
        '0': 'O', '1': 'I', '2': 'Z', '5': 'S', '6': 'G', '8': 'B',
    })
    _ALPHA_TO_DIGIT = str.maketrans({
        'O': '0', 'o': '0',
        'I': '1', 'i': '1', 'L': '1', 'l': '1', 'T': '1', 't': '1',
        'Z': '2', 'z': '2',
        'S': '5', 's': '5',
        'G': '6', 'g': '9',
        'B': '8', 'b': '8',
    })

    _VALID_CODE = re.compile(r'^[A-Z]\d{1,2}$')

    # ---- OCR 修复方法 ----

    @classmethod
    def _fix_ocr_number(cls, code: str) -> str:
        """将 OCR 识别出的代码修复为标准格式：[A-Z]\\d{1,2}。"""
        if not code or len(code) < 2 or len(code) > 3:
            return code

        chars = list(code)
        chars[0] = chars[0].upper().translate(cls._DIGIT_TO_ALPHA)
        for i in range(1, len(chars)):
            if not chars[i].isdigit():
                chars[i] = chars[i].translate(cls._ALPHA_TO_DIGIT)

        result = ''.join(chars)
        if not cls._VALID_CODE.match(result):
            return code
        return result

    @classmethod
    def _pre_fix_text(cls, text: str) -> str:
        """在正则匹配前做预修复，处理 OCR 粘连/误识别场景。"""
        result = re.sub(r'(?<!\s)(Relic)', r' \1', text, flags=re.IGNORECASE)

        def _split_era_code(m):
            return f"{m.group(1)} {m.group(2)}"

        result = re.sub(
            r'(Lith|Meso|Neo|Axi|Requiem|Vanguard)([A-Za-z0-9]{2,3})',
            _split_era_code,
            result, flags=re.IGNORECASE)

        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _clean_text(self, text: str) -> str:
        """清理 OCR 文本：移除品质标签、修复常见 OCR 错误。"""
        text = self.QUALITY_PATTERN.sub('', text)
        text = text.translate(self.OCR_FIX_MAP)
        return text.strip()

    # ---- 匹配 ----

    def _try_match(self, text: str, box) -> list[tuple[str, list]]:
        """尝试匹配单条文本，返回 [(中文名, box), ...]。

        注意：box 已由 _iter_ocr_lines 缩放回原始尺寸，无需再次缩放。
        """
        cleaned = self._clean_text(text)
        if not cleaned:
            return []

        def _match_one(attempt: str) -> list[tuple[str, list]]:
            res = []
            # 1) 中文纪元匹配
            cn_matches = self.CN_PATTERN.findall(attempt)
            if cn_matches:
                for era, code in cn_matches:
                    code = self._fix_ocr_number(code)
                    name = f"{era} {code}"
                    res.append((name, box))
                return res

            # 2) 英文纪元匹配
            en_matches = self.EN_PATTERN.findall(attempt)
            for era_en, code in en_matches:
                era_en_title = era_en.title()
                era_cn = _EN_TIER_MAP.get(era_en_title)
                if not era_cn:
                    continue
                code = self._fix_ocr_number(code)
                name = f"{era_cn} {code}"
                res.append((name, box))
            return res

        results = _match_one(cleaned)
        if not results:
            pre_fixed = self._pre_fix_text(cleaned)
            if pre_fixed != cleaned:
                results = _match_one(pre_fixed)
        return results

    # ---- 主识别流程 ----

    def recognize_all_with_boxes(self, image: np.ndarray) -> list[tuple[str, list]]:
        t0 = time.perf_counter()

        # -- 管线：OCR → 过滤 → 匹配 --
        result, scale = self._run_ocr(image)
        if result is None:
            return []

        lines = self._iter_ocr_lines(result, scale)

        # 调试日志
        raw_texts = [t for t, _ in lines]
        print(f"[OCR] 原始识别 {len(raw_texts)} 行: {raw_texts}", flush=True)

        # 逐行匹配（box 已缩放）
        matched = []
        unmatched = []
        for text, box in lines:
            hits = self._try_match(text, box)
            if hits:
                matched.extend(hits)
            else:
                unmatched.append((text, box))

        # 合并相邻未匹配行
        if unmatched:
            print(f"[OCR] 未匹配行 ({len(unmatched)}): {[t for t, _ in unmatched]}", flush=True)
            unmatched.sort(key=lambda x: self._box_center_y(x[1]))
            merged_set = set()

            for i in range(len(unmatched)):
                if i in merged_set:
                    continue
                text_i, box_i = unmatched[i]

                for j in range(i + 1, len(unmatched)):
                    if j in merged_set:
                        continue
                    text_j, box_j = unmatched[j]

                    cy_i = self._box_center_y(box_i)
                    cy_j = self._box_center_y(box_j)
                    h_i = self._box_height(box_i)
                    h_j = self._box_height(box_j)
                    gap = abs(cy_j - cy_i)
                    max_h = max(h_i, h_j)
                    if max_h <= 0:
                        continue

                    if gap > max_h * 2.0:
                        continue
                    if self._horizontal_overlap(box_i, box_j) < 0.2:
                        continue

                    combined = f"{text_i} {text_j}"
                    hits = self._try_match(combined, box_i)
                    if hits:
                        matched.extend(hits)
                        merged_set.add(i)
                        merged_set.add(j)
                        print(f"[OCR] 合并行: '{text_i}' + '{text_j}' → '{combined}'", flush=True)
                        break

                    combined2 = f"{text_j} {text_i}"
                    hits2 = self._try_match(combined2, box_j)
                    if hits2:
                        matched.extend(hits2)
                        merged_set.add(i)
                        merged_set.add(j)
                        print(f"[OCR] 合并行: '{text_j}' + '{text_i}' → '{combined2}'", flush=True)
                        break

            still_unmatched = [unmatched[i][0] for i in range(len(unmatched)) if i not in merged_set]
            if still_unmatched:
                print(f"[OCR] 最终未匹配: {still_unmatched}", flush=True)

        elapsed = (time.perf_counter() - t0) * 1000
        print(f"[OCR] 结果: {len(matched)} 条遗物, {elapsed:.0f}ms", flush=True)
        return matched
