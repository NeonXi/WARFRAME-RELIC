"""
统一数据库更新编排模块 (data_pipeline.py)

将项目中所有数据库更新操作统一编排为一个流水线，通过单一入口触发。
更新顺序按数据依赖关系排列：

  1. 下载 all.json (WFCD/warframe-drop-data)  — 遗物与掉落数据源
  2. 更新 relics.db       — 从 all.json 迁移遗物数据
  3. 重建 items_i18n.db    — 全物品中英对照索引（依赖 all.json）
  4. 拉取 WM 价格          — wm_items.db + wm_prices.db（warframe.market API）
  5. 构建 game_i18n.db     — 中英对照翻译库（双数据源交叉验证）

用法:
  from data.data_pipeline import DataPipelineWorker
  worker = DataPipelineWorker()
  worker.step_changed.connect(...)
  worker.log.connect(...)
  worker.progress_pct.connect(...)
  worker.finished.connect(...)
  threading.Thread(target=worker.run, daemon=True).start()
"""

import threading
import time
from pathlib import Path

from core.hotkey_config import load_github_mirror

try:
    from PyQt6.QtCore import QObject, pyqtSignal, Qt
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

# ============================================================
# 路径常量
# ============================================================
DATA_DIR = Path(__file__).resolve().parent
ALLJSON_PATH = DATA_DIR / "all.json"
RELIC_DB_PATH = DATA_DIR / "relics.db"
ITEMS_DB_PATH = DATA_DIR / "items_i18n.db"
WM_ITEMS_DB_PATH = DATA_DIR / "wm_items.db"
WM_PRICES_DB_PATH = DATA_DIR / "wm_prices.db"
GAME_I18N_DB_PATH = DATA_DIR / "game_i18n.db"

# ============================================================
# Worker 类
# ============================================================

if _HAS_PYQT:

    class DataPipelineWorker(QObject):
        """后台线程：按依赖顺序执行全部数据库更新。

        信号:
            step_changed(int, str): 当前步骤 (步骤号, 描述)
            log(str, str): 日志消息 (level, msg)
            progress_pct(int): 总体进度百分比 (0-100)
            progress_detail(str, int, int): 子步骤进度 (stage, current, total)
            finished(dict): 完成 (汇总结果)
            error(str): 致命错误
        """

        step_changed = pyqtSignal(int, str)
        log = pyqtSignal(str, str)
        progress_pct = pyqtSignal(int)
        progress_detail = pyqtSignal(str, int, int)
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, skip_download: bool = False, skip_prices: bool = False,
                 prices_only: bool = False):
            """
            Args:
                skip_download: 如果 all.json 已存在且最新，跳过下载步骤
                skip_prices: 跳过市场价格拉取（用于快速更新基础数据）
                prices_only: 仅拉取市场价格（用于单独更新价格数据）
            """
            super().__init__()
            self._cancelled = False
            self._skip_download = skip_download
            self._skip_prices = skip_prices
            self._prices_only = prices_only

        def cancel(self):
            self._cancelled = True

        def _emit_log(self, level: str, msg: str):
            if not self._cancelled:
                # 同时输出到控制台和UI
                print(f"[PIPELINE] [{level.upper()}] {msg}")
                self.log.emit(level, msg)

        def _emit_step(self, step: int, desc: str):
            if not self._cancelled:
                # 同时输出到控制台和UI
                print(f"[PIPELINE] [STEP {step}] {desc}")
                self.step_changed.emit(step, desc)

        def _emit_progress(self, pct: int):
            if not self._cancelled:
                # 输出到控制台
                print(f"[PIPELINE] [PROGRESS] {pct}%")
                self.progress_pct.emit(pct)

        def _step_progress(self, stage: str, cur: int, total: int):
            if not self._cancelled:
                # 输出到控制台
                print(f"[PIPELINE] [DETAIL] {stage}: {cur}/{total}")
                self.progress_detail.emit(stage, cur, total)

        def run(self):
            """执行完整流水线。"""
            results = {}
            start_time = time.time()

            try:
                # ============================================================
                # 仅价格模式: 只拉取市场价格
                # ============================================================
                if self._prices_only:
                    self._emit_log("info", "=" * 50)
                    self._emit_log("info", "拉取 warframe.market 市场价格")
                    self._emit_log("info", "  模式: 多线程并发拉取 + 全局限速 3请求/秒")
                    self._emit_step(1, "拉取市场价格")
                    self._emit_progress(0)

                    from data.wm_prices import fetch_all_prices

                    def _price_log(level, msg):
                        level_map = {"info": "info", "ok": "ok", "warn": "warn", "error": "error"}
                        self._emit_log(level_map.get(level, "info"), msg)

                    def _price_progress(pct):
                        if not self._cancelled:
                            self._emit_progress(pct)

                    price_result = fetch_all_prices(log_cb=_price_log, progress_cb=_price_progress)
                    self._emit_log("ok", f"  总计: {price_result.get('total', 0):,} 个物品")
                    self._emit_log("ok", f"  有卖价: {price_result.get('with_sell', 0):,} 个")
                    self._emit_log("ok", f"  耗时: {price_result.get('elapsed', 0):.0f}s")
                    results["prices"] = price_result

                    elapsed = time.time() - start_time
                    self._emit_progress(100)
                    self._emit_log("ok", "")
                    self._emit_log("ok", "=" * 50)
                    self._emit_log("ok", f"市场价格拉取完成! 总耗时: {elapsed:.0f}s")
                    self._emit_log("ok", "=" * 50)
                    results["elapsed"] = elapsed
                    results["success"] = True
                    self.finished.emit(results)
                    return

                # ============================================================
                # 基础数据模式: all.json → relics.db → items_i18n.db → game_i18n.db
                # (可选跳过价格)
                # ============================================================
                total_steps = 4 if self._skip_prices else 5
                step_num = 0

                # ============================================================
                # 步骤 1: 下载 all.json
                # ============================================================
                step_num += 1
                if self._skip_download and ALLJSON_PATH.exists():
                    self._emit_log("info", f"[{step_num}/{total_steps}] 跳过下载: all.json 已存在")
                    self._emit_step(step_num, "跳过下载 (all.json 已存在)")
                    results["download"] = "skipped"
                else:
                    self._emit_log("info", "=" * 50)
                    self._emit_log("info", f"[{step_num}/{total_steps}] 下载遗物数据 (all.json)")
                    self._emit_step(step_num, "下载遗物数据 (all.json)")
                    self._emit_progress(0)

                    try:
                        from core.fetch_worker import FetchWorker
                        download_done = threading.Event()
                        download_result = {}

                        def _fetch_finished(save_path):
                            download_result["path"] = save_path
                            download_done.set()

                        def _fetch_error(msg):
                            download_result["error"] = msg
                            download_done.set()

                        worker = FetchWorker(str(ALLJSON_PATH),
                                                 mirror=load_github_mirror())
                        # 输出实际使用的下载 URL（包含镜像转换后的地址）
                        self._emit_log("info", f"  源: {worker.url}")
                        worker.finished.connect(_fetch_finished, Qt.ConnectionType.DirectConnection)
                        worker.error.connect(_fetch_error, Qt.ConnectionType.DirectConnection)
                        worker.log.connect(lambda l, m: self._emit_log(l, m), Qt.ConnectionType.DirectConnection)
                        worker.progress_pct.connect(self._emit_progress, Qt.ConnectionType.DirectConnection)
                        t = threading.Thread(target=worker.run, daemon=True)
                        t.start()
                        self._emit_log("info", "[DEBUG] 下载线程已启动，等待完成...")
                        download_done.wait(timeout=600)
                        self._emit_log("info", f"[DEBUG] download_done.wait() 返回, download_result={download_result}")

                        if "error" in download_result:
                            self._emit_log("warn", f"all.json 下载失败: {download_result['error']}")
                            self._emit_log("warn", "将尝试使用本地已有的 all.json 继续")
                            if not ALLJSON_PATH.exists():
                                raise RuntimeError(f"all.json 不存在且下载失败: {download_result['error']}")
                            results["download"] = "failed (using local)"
                        else:
                            results["download"] = "ok"
                            self._emit_log("ok", f"all.json 下载完成，保存路径: {download_result.get('path', 'unknown')}")
                    except Exception as e:
                        self._emit_log("warn", f"all.json 下载失败: {e}")
                        if not ALLJSON_PATH.exists():
                            raise RuntimeError(f"all.json 不存在且下载失败: {e}")
                        results["download"] = "failed (using local)"

                self._emit_log("info", f"[DEBUG] 步骤1完成，进入步骤2。results={results}")

                # ============================================================
                # 步骤 2: 更新 relics.db
                # ============================================================
                step_num += 1
                self._emit_log("info", "")
                self._emit_log("info", f"[{step_num}/{total_steps}] 更新遗物数据库 (relics.db)")
                self._emit_log("info", f"[DEBUG] 开始步骤2，ALLJSON_PATH={ALLJSON_PATH}, RELIC_DB_PATH={RELIC_DB_PATH}")
                self._emit_step(step_num, "更新遗物数据库")
                self._emit_progress(int(step_num / total_steps * 100))

                self._emit_log("info", "[DEBUG] 调用 update_from_alljson...")
                from update_db import update_from_alljson
                self._emit_log("info", f"[DEBUG] update_from_alljson 参数: json_path={ALLJSON_PATH}, db_path={RELIC_DB_PATH}")
                relic_stats = update_from_alljson(str(ALLJSON_PATH), str(RELIC_DB_PATH))
                self._emit_log("info", f"[DEBUG] update_from_alljson 返回: {relic_stats}")
                self._emit_log("ok", f"  遗物: {relic_stats.get('relics', 0):,} 条")
                self._emit_log("ok", f"  部件: {relic_stats.get('parts', 0):,} 条")
                self._emit_log("ok", f"  入库: {relic_stats.get('vaulted', 0):,} 条")
                results["relics"] = relic_stats

                # ============================================================
                # 步骤 3: 重建 items_i18n.db
                # ============================================================
                step_num += 1
                self._emit_log("info", "")
                self._emit_log("info", f"[{step_num}/{total_steps}] 重建全物品中英对照数据库 (items_i18n.db)")
                self._emit_step(step_num, "重建全物品索引")
                self._emit_progress(int(step_num / total_steps * 100))

                from data.items_i18n import build_all_items_db, get_db_stats
                items_stats = build_all_items_db()
                items_db_stats = get_db_stats()
                self._emit_log("ok", f"  全物品: {items_stats.get('total', 0):,} 条")
                self._emit_log("ok", f"  有中文: {items_db_stats.get('has_cn', 0):,} 条")
                self._emit_log("ok", f"  掉落来源: {items_db_stats.get('drop_sources', 0):,} 条")
                results["items"] = items_stats

                # ============================================================
                # 步骤 4: 拉取 WM 价格 (可选)
                # ============================================================
                if not self._skip_prices:
                    step_num += 1
                    self._emit_log("info", "")
                    self._emit_log("info", f"[{step_num}/{total_steps}] 拉取 warframe.market 市场价格")
                    self._emit_log("info", "  模式: 多线程并发拉取 + 全局限速 3请求/秒")
                    self._emit_step(step_num, "拉取市场价格")
                    self._emit_progress(int(step_num / total_steps * 100))

                    from data.wm_prices import fetch_all_prices

                    def _price_log(level, msg):
                        level_map = {"info": "info", "ok": "ok", "warn": "warn", "error": "error"}
                        self._emit_log(level_map.get(level, "info"), msg)

                    def _price_progress(pct):
                        if not self._cancelled:
                            mapped = int(((step_num - 1) + pct / 100) / total_steps * 100)
                            self._emit_progress(min(mapped, 100))

                    price_result = fetch_all_prices(log_cb=_price_log, progress_cb=_price_progress)
                    self._emit_log("ok", f"  总计: {price_result.get('total', 0):,} 个物品")
                    self._emit_log("ok", f"  有卖价: {price_result.get('with_sell', 0):,} 个")
                    self._emit_log("ok", f"  耗时: {price_result.get('elapsed', 0):.0f}s")
                    results["prices"] = price_result

                # ============================================================
                # 步骤 5 (或 4): 构建 game_i18n.db
                # ============================================================
                step_num += 1
                self._emit_log("info", "")
                self._emit_log("info", f"[{step_num}/{total_steps}] 构建中英对照翻译数据库 (game_i18n.db)")
                self._emit_log("info", "  数据源: public-export-plus + WFCD drop-data + WFCD items")
                self._emit_step(step_num, "构建翻译数据库")
                self._emit_progress(int(step_num / total_steps * 100))

                from data.game_i18n import build_database

                def _i18n_log(level, msg):
                    self._emit_log(level, msg)

                def _i18n_progress(stage, cur, total):
                    if not self._cancelled:
                        if total > 0:
                            mapped = int(((step_num - 1) + cur / total) / total_steps * 100)
                            self._emit_progress(min(mapped, 100))
                        self._step_progress(stage, cur, total)

                i18n_stats = build_database(
                    progress_callback=_i18n_progress,
                    log_callback=_i18n_log,
                )
                self._emit_log("ok", f"  总计: {i18n_stats.get('total', 0):,} 条")
                self._emit_log("ok", f"  中英皆有: {i18n_stats.get('both', 0):,} 条")
                results["i18n"] = i18n_stats

                # ============================================================
                # 完成
                # ============================================================
                elapsed = time.time() - start_time
                self._emit_progress(100)
                self._emit_log("ok", "")
                self._emit_log("ok", "=" * 50)
                if self._skip_prices:
                    self._emit_log("ok", f"基础数据更新完成! 总耗时: {elapsed:.0f}s")
                else:
                    self._emit_log("ok", f"全部数据库更新完成! 总耗时: {elapsed:.0f}s")
                self._emit_log("ok", "=" * 50)
                results["elapsed"] = elapsed
                results["success"] = True
                self.finished.emit(results)

            except Exception as e:
                self._emit_log("error", f"流水线执行失败: {e}")
                import traceback
                self._emit_log("error", traceback.format_exc())
                results["success"] = False
                results["error"] = str(e)
                self.error.emit(str(e))
                self.finished.emit(results)


def get_pipeline_summary() -> dict:
    """获取当前所有数据库状态的概要信息。"""
    info = {
        "all.json": ALLJSON_PATH.exists(),
        "relics.db": RELIC_DB_PATH.exists(),
        "items_i18n.db": ITEMS_DB_PATH.exists(),
        "wm_items.db": WM_ITEMS_DB_PATH.exists(),
        "wm_prices.db": WM_PRICES_DB_PATH.exists(),
        "game_i18n.db": GAME_I18N_DB_PATH.exists(),
    }

    sizes = {}
    for name, path in [
        ("all.json", ALLJSON_PATH),
        ("relics.db", RELIC_DB_PATH),
        ("items_i18n.db", ITEMS_DB_PATH),
        ("wm_items.db", WM_ITEMS_DB_PATH),
        ("wm_prices.db", WM_PRICES_DB_PATH),
        ("game_i18n.db", GAME_I18N_DB_PATH),
    ]:
        if path.exists():
            sizes[name] = path.stat().st_size

    info["sizes"] = sizes
    return info