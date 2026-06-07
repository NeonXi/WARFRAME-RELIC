"""
功能模式处理器 —— 从 AppCore 拆分出来的功能处理逻辑。

职责：
- 出入库状态查询 (_handle_check_status)
- 遗物内容查询 (_handle_query_parts)
- 翻译 (_handle_translate)
- 价格查询标注 V2 (_handle_query_price_v2, _render_price_annotations_v2)

所有处理器接收 AppCore 的必要状态作为参数，避免循环依赖。
"""

from core.constants import (
    COLOR_VAULTED, COLOR_AVAILABLE, COLOR_UNKNOWN,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER, FALLBACK_COLOR,
)
from core.annotation import Annotation
from recognizers.item_name import match_and_translate
from data.ui_strings import S


# ---- 精炼标签过滤正则 ----
import re

_REFINEMENT_RE = re.compile(
    r'\s*[\[(（]?\s*(完好|优良|无瑕|卓越|光辉|INTACT|EXCEPTIONAL|FLAWLESS|RADIANT)\s*[\])）]?\s*$',
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
    print(f"[诊断-出入库] last_relics={len(last_relics)}, region={last_region}, dpi={dpi}", flush=True)
    annotations = []

    for name, box in last_relics:
        base_name = strip_refinement(name)
        sx = int(last_region[0] + box[0][0] / dpi)
        sy = int(last_region[1] + box[0][1] / dpi - 28)
        info = relic_db.find(base_name)
        print(f"[诊断-出入库] name='{name}' -> base='{base_name}' -> info={'有' if info else 'None'}", flush=True)
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
# 价格查询 V2 (warframe.db 模糊搜索 + WM API 实时)
# ================================================================

def handle_query_price_v2(all_items, region_xywh, dpi, overlay):
    """新版价格查询: OCR → warframe.db 模糊搜索 → WM API 实时查询 → 标注。

    与旧版相比:
      - 不依赖旧的多数据库缓存
      - 直接从 warframe.db market_items 表模糊匹配获取 url_name
      - 通过 WM API 实时查询价格（仅游戏中卖家）
      - 显示前 10 个最低卖价

    Args:
        all_items: [(ocr_text, box, variants), ...]  - OCR 识别结果
        region_xywh: (x, y, w, h) - 截图区域
        dpi: 屏幕 DPI
        overlay: Overlay 实例
    """
    from data.market_items import batch_fuzzy_search, query_prices_batch

    if not all_items:
        overlay.display(S("overlay", "no_items_detected"), auto_hide_ms=3000)
        return 0, 0

    # Step 1: 批量模糊搜索（单 SQLite 连接，避免重复打开/关闭）
    print(f"\n[价格V2] 批量模糊搜索 {len(all_items)} 个物品...", flush=True)
    queries = [(item_name, variants) for item_name, _, variants in all_items]
    batch_results = batch_fuzzy_search(queries, limit=5)

    matched_items = []
    url_names_to_query = []

    for item_name, box, variants in all_items:
        print(f"[价格V2] 搜索: \"{item_name}\"", flush=True)
        results = batch_results.get(item_name, [])
        if not results and variants:
            # ★ 主搜索无结果时，尝试纠错候选
            for v in variants:
                if v == item_name:
                    continue
                results = batch_results.get(v, [])
                if results:
                    print(f"[价格V2]   候选 \"{v}\" 匹配成功", flush=True)
                    break
        if results:
            best = results[0]
            print(f"[价格V2]   最佳匹配: \"{best['zh_name']}\" ({best['en_name']}) "
                  f"距离={best['distance']} url={best['url_name']}", flush=True)
            matched_items.append({
                "ocr_text": item_name,
                "box": box,
                "en_name": best["en_name"],
                "zh_name": best["zh_name"],
                "url_name": best["url_name"],
                "distance": best["distance"],
                "source_relics": best.get("source_relics", []),
                "source_rarity": best.get("source_rarity", ""),
                "variants": variants,
            })
            url_names_to_query.append(best["url_name"])
        else:
            # ★ 无匹配结果 → 跳过该物品（不在遗物数据库中的物品不显示）
            print(f"[价格V2]   无匹配结果，跳过 (不在遗物数据库中)", flush=True)

    if not url_names_to_query:
        overlay.display("未能匹配到任何物品", auto_hide_ms=3000)
        return 0, 0

    # Step 2: 批量查询 WM API 价格（并发查询所有物品，无批次延迟）
    print(f"\n[价格V2] 查询 {len(url_names_to_query)} 个物品的 WM 价格...", flush=True)
    overlay.display(f"⟐ 正在查询 {len(url_names_to_query)} 个物品的实时价格...", auto_hide_ms=5000)

    prices = query_prices_batch(url_names_to_query, max_workers=4)

    # Step 3: 合并价格数据
    with_price = 0
    for item in matched_items:
        url = item.get("url_name", "")
        if url and url in prices:
            item["price"] = prices[url]
            item["match_quality"] = "exact"
            with_price += 1
            p = prices[url]
            top10_prices = [str(o["platinum"]) for o in p["top10"]]
            print(f"[价格V2] {item['zh_name']}: "
                  f"{' / '.join(top10_prices)} 卖家={p['total_ingame']}",
                  flush=True)
        elif url:
            item["match_quality"] = "no_price"
            print(f"[价格V2] {item['zh_name']}: 无价格数据", flush=True)
        else:
            item["match_quality"] = "none"
            print(f"[价格V2] {item['ocr_text']}: 未匹配", flush=True)

    # Step 4: 渲染标注
    print(f"\n[价格V2] 渲染 {len(matched_items)} 条标注...", flush=True)
    render_price_annotations_v2(matched_items, region_xywh, dpi, overlay)

    total = len(matched_items)
    overlay.display(
        S.format("overlay", "price_query_summary", total=total, with_price=with_price),
        auto_hide_ms=8000)

    return total, with_price


def render_price_annotations_v2(matched, region_xywh, dpi, overlay):
    """渲染 V2 价格标注到 overlay。

    显示格式: 中文名\n最低价(p) 共X卖家（每个价格换行）
    颜色: 绿色=低价, 黄色=中价, 红色=高价
    """
    annotations = []
    print(f"[显示-价格V2] ===== 渲染 {len(matched)} 条价格标注 =====", flush=True)

    for item in matched:
        box = item["box"]
        # ★ box 已经是全局物理坐标（OCR 坐标 + full_rx/ry），
        #   overlay 用逻辑坐标绘制，只需除以 dpi 转逻辑坐标
        sx = int(box[0][0] / dpi)
        sy = int(box[0][1] / dpi + 10)

        quality = item.get("match_quality", "none")
        price_data = item.get("price")
        zh_name = item.get("zh_name", "") or item.get("en_name", "")
        en_name = item.get("en_name", "")

        if price_data:
            top10 = price_data["top10"]
            total = price_data["total_ingame"]

            # 每个价格一行
            price_lines = [f"{o['platinum']}p" for o in top10]
            label = zh_name + "\n" + "\n".join(price_lines) + f"\n共{total}卖家"

            # 颜色: 最低价 <10p 绿色, 10-30p 黄色, >30p 红色
            min_p = top10[0]["platinum"] if top10 else 999
            if min_p < 10:
                color = COLOR_AVAILABLE  # 绿色
            elif min_p < 30:
                color = COLOR_GOLD  # 金色
            else:
                color = COLOR_VAULTED  # 红色
        else:
            if quality == "none":
                label = f"{en_name} - 未匹配"
            else:
                label = f"{zh_name} - 无价格"
            color = COLOR_UNKNOWN

        display_name = en_name
        print(f"[显示-价格V2] OCR=\"{item['ocr_text']}\" | 匹配=\"{display_name}\" | "
              f"zh=\"{zh_name}\" | quality={quality} | 坐标=({sx},{sy}) | 标注=\"{label}\"",
              flush=True)

        annotations.append(Annotation.create(
            label, sx, sy, duration_ms=15000, color=color))

    overlay.show_annotations_stream(
        annotations, auto_hide_ms=15000, interval_ms=40, batch_size=1)
