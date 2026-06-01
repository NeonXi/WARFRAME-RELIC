"""
功能模式处理器 —— 从 AppCore 拆分出来的四大功能处理逻辑。

职责：
- 出入库状态查询 (_handle_check_status)
- 遗物内容查询 (_handle_query_parts)
- 翻译 (_handle_translate)
- 价格查询标注 (_handle_query_price, _render_price_annotations)

所有处理器接收 AppCore 的必要状态作为参数，避免循环依赖。
"""

from core.constants import (
    COLOR_VAULTED, COLOR_AVAILABLE, COLOR_UNKNOWN,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER, FALLBACK_COLOR,
)
from core.price_service import (
    price_to_color, build_display_name, format_price_annotation,
)
from core.annotation import Annotation
from recognizers.item_name import match_and_price, match_and_translate
from data.ui_strings import S


# ---- 精炼标签过滤正则 ----
import re

_REFINEMENT_RE = re.compile(
    r'\s*[\[(（]?\s*(完好|无瑕|卓越|光辉|INTACT|EXCEPTIONAL|FLAWLESS|RADIANT)\s*[\])）]?\s*$',
    re.IGNORECASE
)


def strip_refinement(name: str) -> str:
    """去除遗物名称末尾的精炼标签，返回基础名称。"""
    return _REFINEMENT_RE.sub('', name).strip()


# ================================================================
# 出入库状态查询
# ================================================================

def handle_check_status(last_relics, relic_db, last_region, dpi, overlay):
    """出入库查询：识别遗物 → 标注出入库状态。"""
    annotations = []

    for name, box in last_relics:
        base_name = strip_refinement(name)
        sx = int(last_region[0] + box[0][0] / dpi)
        sy = int(last_region[1] + box[0][1] / dpi - 28)
        info = relic_db.find(base_name)
        if info:
            if info.get('vaulted', False):
                color, label = COLOR_VAULTED, f"{base_name} [{S('overlay', 'relic_vaulted')}]"
            else:
                color, label = COLOR_AVAILABLE, f"{base_name} [{S('overlay', 'relic_available')}]"
        else:
            color, label = COLOR_UNKNOWN, f"{base_name} [?]"
        annotations.append(Annotation.create(label, sx, sy, duration_ms=8000, color=color))

    overlay.show_annotations_stream(
        annotations, auto_hide_ms=8000, interval_ms=30, batch_size=2)
    overlay.display(
        S.format("overlay", "annotations_shown", count=len(annotations)), auto_hide_ms=5000)


# ================================================================
# 遗物内容查询
# ================================================================

def handle_query_parts(last_relics, relic_db, last_region, dpi, overlay):
    """遗物内容查询：匹配遗物内容 → 标注掉落物品 + 稀有度颜色。"""
    annotations = []
    matched = 0
    unmatched_names = []

    for name, box in last_relics:
        base_name = strip_refinement(name)
        sx = int(last_region[0] + box[0][0] / dpi)
        sy = int(last_region[1] + box[0][1] / dpi - 28)
        info = relic_db.find(base_name)
        if not info:
            unmatched_names.append(base_name)
            annotations.append(
                Annotation.create(S.format("overlay", "relic_no_parts_info", name=base_name),
                                  sx, sy, duration_ms=10000, color=FALLBACK_COLOR))
            continue

        matched += 1
        parts = info.get('parts', [])
        vaulted = info.get('vaulted', False)
        status_color = COLOR_VAULTED if vaulted else COLOR_AVAILABLE
        status = S("overlay", "relic_vaulted") if vaulted else S("overlay", "relic_available")

        lines = [f"{base_name} [{status}]"]
        line_colors = [status_color]
        sorted_parts = sorted(parts, key=lambda p: p.get('chance', 0))
        chances = sorted(set(p.get('chance', 0) for p in sorted_parts))
        extra_lines, extra_colors = _map_rarity_colors(chances, sorted_parts)
        lines.extend(extra_lines)
        line_colors.extend(extra_colors)
        label = "\n".join(lines)
        annotations.append(Annotation.create(label, sx, sy, duration_ms=10000, color=status_color, line_colors=line_colors))

    overlay.show_annotations_stream(
        annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

    total = len(last_relics)
    if unmatched_names:
        summary = S.format("overlay", "query_summary_fmt",
            total=total, matched=matched, unmatched=', '.join(unmatched_names))
    else:
        summary = S.format("overlay", "query_summary", total=total, matched=matched)
    summary += S("overlay", "query_legend")
    overlay.display(summary, auto_hide_ms=6000)

    return matched, total, unmatched_names


def _map_rarity_colors(chances, sorted_parts):
    """根据概率排名分配稀有度颜色。"""
    if len(chances) >= 3:
        chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_SILVER, chances[2]: COLOR_COPPER}
    elif len(chances) == 2:
        chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_COPPER}
    else:
        chance_to_color = {chances[0]: COLOR_SILVER}

    lines, colors = [], []
    for p in sorted_parts:
        ch = p.get('chance', 0)
        clr = chance_to_color.get(ch, COLOR_SILVER)
        prefix = "●" if ch == chances[0] else ("◦" if len(chances) > 1 and ch == chances[-1] else "◈")
        lines.append(f"  {prefix} {p['name']}")
        colors.append(clr)
    return lines, colors


# ================================================================
# 翻译
# ================================================================

def handle_translate(last_items, last_region, dpi, overlay):
    """翻译：OCR 文本 → 匹配数据库 → 标注中文名。"""
    if not last_items:
        overlay.display(S("overlay", "no_text_detected"), auto_hide_ms=3000)
        return

    translated = match_and_translate(last_items)
    if not translated:
        overlay.display(S("overlay", "translate_failed"), auto_hide_ms=3000)
        return

    annotations = []
    print(f"[显示-翻译] ===== 渲染 {len(translated)} 条翻译标注 =====", flush=True)
    for item in translated:
        en_name = item.get('en_name', item.get('ocr_text', ''))
        zh_name = item.get('zh_name', '')
        quality = item.get('match_quality', 'none')
        box = item['box']
        sx = int(last_region[0] + box[0][0] / dpi)
        sy = int(last_region[1] + box[0][1] / dpi - 28)

        if quality == 'exact':
            color = COLOR_AVAILABLE
        elif quality in ('prefix', 'contains'):
            color = COLOR_VAULTED
        else:
            color = COLOR_UNKNOWN

        label = S.format("overlay", "translate_label_fmt", zh_name=zh_name, en_name=en_name) if (zh_name and zh_name != en_name) else en_name

        print(f"[显示-翻译] OCR=\"{item.get('ocr_text')}\" | 匹配=\"{en_name}\" | zh=\"{zh_name}\" | "
              f"quality={quality} | 坐标=({sx},{sy}) | 显示文字=\"{label}\"", flush=True)

        annotations.append(Annotation.create(label, sx, sy, duration_ms=10000, color=color))

    overlay.show_annotations_stream(
        annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

    matched = sum(1 for t in translated if t.get('match_quality', 'none') != 'none')
    overlay.display(
        S.format("overlay", "translate_summary", total=len(translated), matched=matched),
        auto_hide_ms=6000)

    return len(translated), matched


# ================================================================
# 价格查询
# ================================================================

def handle_query_price(last_items, last_region, dpi, overlay):
    """价格查询：匹配数据库 → 查价格 → 渲染覆盖层。"""
    if not last_items:
        return

    matched = match_and_price(last_items)
    if not matched:
        overlay.display(S("overlay", "no_items_detected"), auto_hide_ms=3000)
        return

    render_price_annotations(matched, last_region, dpi, overlay)

    total = len(matched)
    with_price = sum(1 for m in matched if m.get('price') and m['price'].get('sell_weighted') is not None)
    realtime_count = sum(1 for m in matched if m.get('_price_source') == 'realtime')
    msg = S.format("overlay", "price_query_summary", total=total, with_price=with_price)
    if realtime_count > 0:
        msg += f" (实时 {realtime_count})"
    overlay.display(msg, auto_hide_ms=8000)

    return total, with_price, realtime_count


def render_price_annotations(matched, last_region, dpi, overlay):
    """渲染价格标注到 overlay。"""
    annotations = []
    print(f"[显示-价格] ===== 渲染 {len(matched)} 条价格标注 =====", flush=True)
    for item in matched:
        box = item['box']
        sx = int(last_region[0] + box[0][0] / dpi)
        sy = int(last_region[1] + box[0][1] / dpi - 28)

        quality = item['match_quality']
        price = item.get('price')

        color = price_to_color(price, quality)
        label = format_price_annotation(item)

        if price and price.get('sell_weighted') is not None:
            price_str = f'sell_weighted={price["sell_weighted"]}'
        else:
            price_str = str(price)
        display_name = build_display_name(item)
        print(f"[显示-价格] OCR=\"{item['ocr_text']}\" | 匹配=\"{item.get('matched_name', '')}\" | "
              f"显示=\"{display_name}\" | quality={quality} | price={price_str} | "
              f"坐标=({sx},{sy}) | 标注=\"{label}\"", flush=True)

        annotations.append(Annotation.create(label, sx, sy, duration_ms=15000, color=color))

    overlay.show_annotations_stream(
        annotations, auto_hide_ms=15000, interval_ms=40, batch_size=1)
