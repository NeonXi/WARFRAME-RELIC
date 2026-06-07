"""
统一数据库更新编排模块 (data_pipeline.py)

将项目中所有数据库更新操作统一编排为一个流水线，通过单一入口触发。

流水线:
  1. Git 稀疏检出源数据    — 从 3 个上游仓库拉取 JSON 数据到 external/
  2. 构建统一数据库        — build_warframe_db.py → warframe.db (25 张表)
  3. 拉取 WM 价格 (可选)   — warframe.market 实时价格 → warframe.db

用法:
  from data.data_pipeline import DataPipelineWorker
  worker = DataPipelineWorker()
  worker.step_changed.connect(...)
  worker.log.connect(...)
  worker.progress_pct.connect(...)
  worker.finished.connect(...)
  threading.Thread(target=worker.run, daemon=True).start()
"""

import time
from pathlib import Path

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

# ============================================================
# 路径常量
# ============================================================
DATA_DIR = Path(__file__).resolve().parent
WARFRAME_DB_PATH = DATA_DIR / "warframe.db"

# ============================================================
# Worker 类
# ============================================================

if _HAS_PYQT:

    class DataPipelineWorker(QObject):
        """后台线程：按依赖顺序执行数据库更新。。

        信号:
            step_changed(int, str): 当前步骤 (步骤号, 描述)
            log(str, str): 日志消息 (level, msg)
            progress_pct(int): 总体进度百分比 (0-100)
            progress_detail(str, int, int): 子步骤进度 (stage, current, total)
            finished(dict): 完成 (汇总结果)
            error(str): 致命错误
            repo_progress(str, int, str): 分仓库进度 (repo_name, pct, status_text)
        """

        step_changed = pyqtSignal(int, str)
        log = pyqtSignal(str, str)
        progress_pct = pyqtSignal(int)
        progress_detail = pyqtSignal(str, int, int)
        repo_progress = pyqtSignal(str, int, str)
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, skip_download: bool = False,
                      close_connections_fn=None):
            """
            Args:
                skip_download: 如果源数据已存在且最新，跳过下载步骤
                close_connections_fn: 构建完成前调用，关闭应用缓存的数据库连接
            """
            super().__init__()
            self._cancelled = False
            self._skip_download = skip_download
            self._close_connections_fn = close_connections_fn

        def cancel(self):
            self._cancelled = True

        def _emit_log(self, level: str, msg: str):
            if not self._cancelled:
                print(f"[PIPELINE] [{level.upper()}] {msg}")
                self.log.emit(level, msg)

        def _emit_step(self, step: int, desc: str):
            if not self._cancelled:
                print(f"[PIPELINE] [STEP {step}] {desc}")
                self.step_changed.emit(step, desc)

        def _emit_progress(self, pct: int):
            if not self._cancelled:
                print(f"[PIPELINE] [PROGRESS] {pct}%")
                self.progress_pct.emit(pct)

        def _step_progress(self, stage: str, cur: int, total: int):
            if not self._cancelled:
                print(f"[PIPELINE] [DETAIL] {stage}: {cur}/{total}")
                self.progress_detail.emit(stage, cur, total)

        def run(self):
            """执行完整流水线。"""
            results = {}
            start_time = time.time()

            try:
                # ============================================================
                # 基础数据模式: 源数据 → warframe.db
                # ============================================================
                total_steps = 2
                step_num = 0

                # ============================================================
                # 步骤 1: 拉取源数据（3 个上游仓库 → external/）
                # ============================================================
                step_num += 1
                self._emit_log("info", "=" * 50)
                self._emit_log("info", f"[{step_num}/{total_steps}] 拉取源数据")
                self._emit_step(step_num, "拉取源数据")

                step_pct_start = int((step_num - 1) / total_steps * 100)
                step_pct_end = int(step_num / total_steps * 100)

                download_ok = self._run_step_download(step_pct_start, step_pct_end)
                results["download"] = "ok" if download_ok else "failed"

                if not download_ok:
                    self._emit_log("error", "=" * 50)
                    self._emit_log("error", "源数据拉取失败，请检查网络后重试")
                    self._emit_log("error", "=" * 50)
                    results["success"] = False
                    results["error"] = "源数据拉取失败"
                    results["elapsed"] = time.time() - start_time
                    self.finished.emit(results)
                    return

                # ============================================================
                # 步骤 2: 构建统一数据库 warframe.db
                # ============================================================
                step_num += 1
                self._emit_log("info", "")
                self._emit_log("info", f"[{step_num}/{total_steps}] 构建统一数据库 (warframe.db)")
                self._emit_step(step_num, "构建统一数据库")

                step2_pct_start = int((step_num - 1) / total_steps * 100)
                step2_pct_end = int(step_num / total_steps * 100)

                build_stats = self._run_step_build_db(step2_pct_start, step2_pct_end)
                results["build"] = build_stats

                # ============================================================
                # 完成
                # ============================================================
                elapsed = time.time() - start_time
                self._emit_progress(100)
                self._emit_log("ok", "")
                self._emit_log("ok", "=" * 50)
                self._emit_log("ok", f"数据更新完成! 总耗时: {elapsed:.0f}s")
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

        # ============================================================
        # 步骤实现
        # ============================================================

        def _run_step_download(self, pct_start: int, pct_end: int) -> bool:
            """步骤1: 拉取源数据（3 个上游仓库稀疏检出）。返回是否成功。"""
            try:
                import sys
                scripts_dir = Path(__file__).parent.parent / "scripts"
                sys.path.insert(0, str(scripts_dir))

                from pull_warframe_items import (
                    init_sparse_checkout, update_existing,
                    init_drop_data_sparse_checkout, update_drop_data_existing,
                    init_i18n_sparse_checkout, update_i18n_existing,
                )

                def _wfcd_log(level: str, msg: str):
                    self._emit_log(level, msg)

                def _wfcd_progress(*args):
                    if len(args) == 1 and isinstance(args[0], int):
                        step_local_pct = args[0]
                        global_pct = pct_start + int(step_local_pct / 100 * (pct_end - pct_start))
                        self._emit_progress(global_pct)
                    elif len(args) == 3:
                        stage, cur, total = args
                        self.progress_detail.emit(stage, cur, total)

                # 三组稀疏检出配置
                # output_dir 统一指向 external/ 下的稀疏检出目录（与 build_warframe_db.py 一致）
                external_dir = Path(__file__).parent.parent / "external"
                sparse_repos = [
                    ("warframe-items", "遗物/物品", "warframe-items_sparse",
                     ["Relics.json", "i18n.json", "All.json"],
                     external_dir / "warframe-items_sparse" / "data" / "json",
                     init_sparse_checkout, update_existing),
                    ("warframe-drop-data", "掉落数据", "warframe-drop-data_sparse",
                     ["all.json"],
                     external_dir / "warframe-drop-data_sparse" / "data",
                     init_drop_data_sparse_checkout, update_drop_data_existing),
                    ("warframe-public-export-plus", "翻译数据", "warframe-i18n_sparse",
                     ["dict.en.json", "dict.zh.json"],
                     external_dir / "warframe-i18n_sparse",
                     init_i18n_sparse_checkout, update_i18n_existing),
                ]

                from core.proxy_config import get_sorted_mirrors, resolve_url

                all_ok = True
                for repo_idx, (repo_key, repo_name, repo_dir_name, files, output_dir, init_fn, update_fn) in enumerate(sparse_repos):
                    self._emit_log("info", f"")
                    self._emit_log("info", f"--- {repo_name}: {repo_dir_name} ---")
                    repo_dir = Path(__file__).parent.parent / "external" / repo_dir_name

                    self.repo_progress.emit(repo_name, 0, "准备中...")

                    sorted_mirrors = get_sorted_mirrors(repo_key)

                    is_update = repo_dir.exists() and (repo_dir / ".git").exists()
                    if is_update:
                        self._emit_log("info", f"仓库已存在，删除后重新初始化...")
                        self.repo_progress.emit(repo_name, 0, "删除旧仓库...")

                    self._emit_log("info", f"拉取仓库（{len(sorted_mirrors)} 个代理可用）...")
                    ok = False
                    for mirror_idx, (mirror_idx_orig, mirror_template) in enumerate(sorted_mirrors):
                        if self._cancelled:
                            break
                        clone_url = resolve_url(repo_key, mirror_template)
                        if not clone_url:
                            self._emit_log("warn", f"  代理 [{mirror_idx_orig}] 无法解析，跳过")
                            continue

                        self._emit_log("info", f"  尝试代理 [{mirror_idx_orig}] ({mirror_idx + 1}/{len(sorted_mirrors)})")
                        self.repo_progress.emit(repo_name, int(mirror_idx / len(sorted_mirrors) * 80), f"尝试代理 [{mirror_idx_orig}]...")

                        if is_update and mirror_idx == 0:
                            ok = update_fn(
                                log_callback=_wfcd_log,
                                progress_callback=_wfcd_progress,
                                clone_url=clone_url,
                            )
                        else:
                            ok = init_fn(
                                log_callback=_wfcd_log,
                                progress_callback=_wfcd_progress,
                                clone_url=clone_url,
                            )
                        if ok:
                            from core.proxy_config import update_test_result
                            update_test_result(repo_key, mirror_idx_orig, True)
                            self._emit_log("ok", f"  ✓ 代理 [{mirror_idx_orig}] 成功")
                            self.repo_progress.emit(repo_name, 100, f"✓ 代理 [{mirror_idx_orig}] 成功")
                            break
                        else:
                            from core.proxy_config import update_test_result
                            update_test_result(repo_key, mirror_idx_orig, False)
                            self._emit_log("warn", f"  ✗ 代理 [{mirror_idx_orig}] 失败，尝试下一个...")

                    if not ok:
                        self.repo_progress.emit(repo_name, 100, "✗ 所有代理均失败")

                    if ok:
                        for f in files:
                            dest = output_dir / f
                            if dest.exists():
                                size_mb = dest.stat().st_size / (1024 * 1024)
                                self._emit_log("ok", f"  {f} ({size_mb:.1f} MB)")
                    else:
                        existing = [f for f in files if (output_dir / f).exists()]
                        if len(existing) == len(files):
                            self._emit_log("warn", f"拉取失败，使用本地缓存")
                            self.repo_progress.emit(repo_name, 100, "⚠ 使用本地缓存")
                        else:
                            missing = [f for f in files if f not in existing]
                            self._emit_log("error", f"拉取失败且缺少: {missing}")
                            all_ok = False

                return all_ok

            except Exception as e:
                self._emit_log("error", f"拉取源数据失败: {e}")
                import traceback
                self._emit_log("error", traceback.format_exc())
                return False

        def _run_step_build_db(self, pct_start: int, pct_end: int) -> dict:
            """步骤2: 构建统一数据库 warframe.db。"""
            from data.build_warframe_db import build
            from data.build_market_items import build_market_items

            def _build_log(msg: str):
                self._emit_log("info", msg)

            def _build_progress(stage: str, cur: int, total: int):
                self._step_progress(stage, cur, total)
                if total > 0:
                    # build_warframe_db 内部有 6 个子步骤
                    global_pct = pct_start + int(cur / total * (pct_end - pct_start))
                    self._emit_progress(min(global_pct, pct_end))

            stats = build(
                log_callback=_build_log,
                progress_callback=_build_progress,
                skip_wm=True,  # WM 物品列表在单独步骤中拉取
                close_connections_fn=self._close_connections_fn,
            )
            self._emit_log("ok", f"  items: {stats.get('items', 0):,} 条")
            self._emit_log("ok", f"  relics: {stats.get('relics', 0):,} 个")
            self._emit_log("ok", f"  relic_rewards: {stats.get('relic_rewards', 0):,} 条")
            self._emit_log("ok", f"  game_translations: {stats.get('game_translations', 0):,} 条")

            # 构建 market_items 表（从 items 表本地生成，不依赖 WM API）
            self._emit_log("info", "  构建 market_items 表...")
            mi_result = build_market_items(
                log_callback=lambda msg: self._emit_log("info", f"    {msg}"),
            )
            stats['market_items'] = mi_result.get('inserted', 0)
            self._emit_log("ok", f"  market_items: {stats['market_items']:,} 条")

            self._emit_log("ok", f"  耗时: {stats.get('elapsed_sec', 0):.1f}s")
            return stats


# ============================================================
# 状态概要
# ============================================================

def get_pipeline_summary() -> dict:
    """获取当前数据文件状态的概要信息。"""
    external_dir = DATA_DIR.parent / "external"
    wfcd_dir = external_dir / "warframe-items_sparse" / "data" / "json"
    drop_dir = external_dir / "warframe-drop-data_sparse" / "data"
    i18n_dir = external_dir / "warframe-i18n_sparse"

    info = {
        # 源数据文件
        "All.json": (wfcd_dir / "All.json").exists(),
        "Relics.json": (wfcd_dir / "Relics.json").exists(),
        "i18n.json": (wfcd_dir / "i18n.json").exists(),
        "all.json": (drop_dir / "all.json").exists(),
        "dict.en.json": (i18n_dir / "dict.en.json").exists(),
        "dict.zh.json": (i18n_dir / "dict.zh.json").exists(),
        # 统一数据库
        "warframe.db": WARFRAME_DB_PATH.exists(),
    }

    sizes = {}
    for name, path in [
        ("All.json", wfcd_dir / "All.json"),
        ("Relics.json", wfcd_dir / "Relics.json"),
        ("i18n.json", wfcd_dir / "i18n.json"),
        ("all.json", drop_dir / "all.json"),
        ("dict.en.json", i18n_dir / "dict.en.json"),
        ("dict.zh.json", i18n_dir / "dict.zh.json"),
        ("warframe.db", WARFRAME_DB_PATH),
    ]:
        if path.exists():
            sizes[name] = path.stat().st_size

    info["sizes"] = sizes
    return info
