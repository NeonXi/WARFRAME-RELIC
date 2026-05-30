"""
测试脚本：截4图 + 识别物品名称（不查数据库）

模拟 _do_price_query 的核心逻辑：
  1. 加载物品区域配置 (data/item_region.json)
  2. 在屏幕上显示半透明框线（方便确认截图区域是否正确）
  3. 用 dxcam 截取4个子区域
  4. 逐个用 ItemNameRecognizer 识别物品名称
  5. 保存截图和识别结果到 debug 目录

用法：直接运行 python test_4split_ocr.py
"""
import os
import sys
import time
import json

# 性能优化
_OCR_THREADS = max(2, min(4, os.cpu_count() // 2 if os.cpu_count() else 4))
os.environ["OMP_NUM_THREADS"] = str(_OCR_THREADS)
os.environ["ORT_NUM_THREADS"] = str(_OCR_THREADS)
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"

import cv2
import ctypes
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import dxcam

from recognizers.item_name import ItemNameRecognizer


# ── 半透明框线叠加窗口（使用 Tkinter，Python 自带） ──
class RegionOverlay:
    """
    创建一个全屏半透明顶层窗口，在上面绘制截图区域框线。
    使用 Python 自带的 tkinter，无需额外依赖。
    """

    def __init__(self, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.regions = []  # [(x, y, w, h, label), ...]
        self._root = None
        self._canvas = None

    def set_regions(self, regions):
        """设置要显示的矩形区域列表 [(x, y, w, h, label), ...]"""
        self.regions = regions

    def _create_overlay(self):
        """创建并显示半透明框线窗口"""
        import tkinter as tk

        self._root = tk.Tk()
        self._root.title("截图区域框线")
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.45)
        self._root.attributes("-transparentcolor", "black")
        self._root.overrideredirect(True)  # 无边框
        self._root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")

        self._canvas = tk.Canvas(self._root, bg="black", highlightthickness=0,
                                  width=self.screen_w, height=self.screen_h)
        self._canvas.pack()

        # 颜色表
        colors = ["red", "lime", "cyan", "magenta"]

        for idx, region in enumerate(self.regions):
            rx, ry, rw, rh, label = region
            color = colors[idx % len(colors)]

            # 画矩形框（3像素宽）
            self._canvas.create_rectangle(rx, ry, rx + rw, ry + rh,
                                          outline=color, width=3, fill="")

            # 画标签
            label_h = 22
            lx, ly = rx, ry - label_h - 4
            if ly < 0:
                ly = ry + rh + 4

            # 标签背景 + 文字
            label_w = len(label) * 12 + 16
            self._canvas.create_rectangle(lx, ly, lx + label_w, ly + label_h,
                                          fill=color, outline="")
            self._canvas.create_text(lx + label_w // 2, ly + label_h // 2,
                                     text=label, fill="white",
                                     font=("Microsoft YaHei", 11, "bold"))

        self._root.update()

    def show(self, duration=5.0):
        """显示半透明框线窗口，持续 duration 秒后自动关闭"""
        import tkinter as tk
        self._create_overlay()
        print(f"[Overlay] 显示截图区域框线，{duration}秒后关闭...")
        # 用 after 定时关闭
        self._root.after(int(duration * 1000), self.close)
        self._root.mainloop()

    def close(self):
        """关闭框线窗口"""
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None


def main():
    print("=" * 60)
    print("4等分截图 + 物品名识别 测试")
    print("=" * 60)

    # ── 1. 加载物品区域配置 ──
    region_path = os.path.join(os.path.dirname(__file__), "data", "item_region.json")
    if not os.path.exists(region_path):
        print(f"[错误] 未找到物品区域配置: {region_path}")
        print("       请先在管理面板 → 价格数据 → 设置物品区域")
        return

    with open(region_path, "r", encoding="utf-8") as f:
        region_cfg = json.load(f)
    x, y, w, h = region_cfg['x'], region_cfg['y'], region_cfg['w'], region_cfg['h']
    item_w = w // 4
    print(f"[配置] 物品区域: x={x} y={y} w={w} h={h}")
    print(f"[配置] 4等分每份宽={item_w}")

    screen_w = ctypes.windll.user32.GetSystemMetrics(0)
    screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    print(f"[系统] 屏幕分辨率: {screen_w}x{screen_h}")

    # ── 2. 计算4个子区域（用于显示框线） ──
    split_regions = []
    for i in range(4):
        ix = x + i * item_w
        rx = max(0, ix)
        ry = max(0, y)
        rw = min(item_w, screen_w - rx)
        rh = min(h, screen_h - ry)
        if rw > 0 and rh > 0:
            split_regions.append((rx, ry, rw, rh, f"子图{i+1}"))
            print(f"[子图{i+1}/4] 区域: ({rx},{ry}) {rw}x{rh}")

    # ── 3. 显示半透明框线（方便确认截图区域是否正确） ──
    print(f"\n[Overlay] 将在屏幕上显示 {len(split_regions)} 个半透明框线 ...")
    print("[Overlay] 请切换到游戏画面，确认框线位置是否覆盖了物品卡片区域")
    overlay = RegionOverlay(screen_w, screen_h)
    overlay.set_regions(split_regions)
    overlay.show(duration=5.0)
    print("[Overlay] 框线已关闭，开始截图 ...")

    # ── 4. 创建摄像头 ──
    try:
        camera = dxcam.create(output_idx=0, output_color="BGR")
    except Exception as e:
        print(f"[错误] dxcam 初始化失败: {e}")
        return

    # ── 5. 初始化 OCR 识别器 ──
    print("[OCR] 初始化 ItemNameRecognizer ...")
    t_init = time.perf_counter()
    item_ocr = ItemNameRecognizer()
    print(f"[OCR] 初始化完成 ({ (time.perf_counter() - t_init)*1000:.0f}ms)")

    # ── 6. 准备输出目录 ──
    debug_dir = os.path.join(os.getenv('APPDATA'), 'WARFRAME-RELIC', 'debug')
    os.makedirs(debug_dir, exist_ok=True)

    # ── 7. 逐个子图截图 + 识别 ──
    all_results = []
    total_ocr_time = 0

    for i, (rx, ry, rw, rh, _label) in enumerate(split_regions):
        print(f"\n{'─' * 40}")
        print(f"[子图{i+1}/4] 开始处理 ...")

        # 截图 (dxcam region 格式: left, top, right, bottom)
        dxcam_region = (rx, ry, rx + rw, ry + rh)
        t_grab = time.perf_counter()
        try:
            frame = camera.grab(region=dxcam_region)
        except Exception as e:
            print(f"[子图{i+1}/4] 截图异常: {e}")
            continue
        grab_ms = (time.perf_counter() - t_grab) * 1000

        if frame is None:
            print(f"[子图{i+1}/4] 截图返回 None! (可能是区域无效或屏幕被其他程序占用)")
            continue

        print(f"[子图{i+1}/4] 截图成功: {frame.shape[1]}x{frame.shape[0]} (耗时 {grab_ms:.0f}ms)")

        # 保存截图
        save_path = os.path.join(debug_dir, f"split_{i+1}.png")
        Image.fromarray(frame[:, :, ::-1]).save(save_path)
        print(f"[子图{i+1}/4] 截图已保存: {save_path}")

        # OCR 识别
        print(f"[子图{i+1}/4] 开始 OCR 识别 ...")
        t_ocr = time.perf_counter()
        results = item_ocr.recognize_all_with_boxes(frame)
        ocr_ms = (time.perf_counter() - t_ocr) * 1000
        total_ocr_time += ocr_ms

        if results:
            for j, (name, box, variants) in enumerate(results):
                print(f"[子图{i+1}/4] 结果{j+1}: \"{name}\"")
                if variants:
                    print(f"           纠错候选: {variants}")
                # 转换为全局坐标
                global_box = [
                    [box[0][0] + rx, box[0][1] + ry],
                    [box[1][0] + rx, box[1][1] + ry],
                    [box[2][0] + rx, box[2][1] + ry],
                    [box[3][0] + rx, box[3][1] + ry],
                ]
                all_results.append({
                    'name': name,
                    'box': global_box,
                    'variants': variants,
                    'split_index': i,
                })
        else:
            print(f"[子图{i+1}/4] 未识别到物品名称")

        print(f"[子图{i+1}/4] OCR耗时: {ocr_ms:.0f}ms")

    # ── 8. 汇总结果 ──
    print(f"\n{'=' * 60}")
    print(f"识别汇总: {len(all_results)} 个物品")
    print(f"总OCR耗时: {total_ocr_time:.0f}ms")
    print(f"{'=' * 60}")

    for item in all_results:
        idx = item['split_index'] + 1
        print(f"  子图{idx}: \"{item['name']}\"")
        if item['variants']:
            print(f"         纠错: {item['variants']}")

    print(f"\n截图已保存到: {debug_dir}")
    print("完成!")


if __name__ == "__main__":
    main()
