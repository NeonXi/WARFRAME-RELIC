"""
[L0-Build] build.py — WARFRAME-RELIC 一键打包脚本(构建工具,非运行时代码)

依赖: Python 标准库 + PyInstaller(命令行调用)
职责: onedir 打包 + 资源显式清单 + hiddenimports 自动扫描 + 自检 + 冒烟 + ZIP
必读: .trae/documents/打包EXE方案.md §4.4

用法:
    python build.py              # 完整构建 + 自检 + 冒烟
    python build.py --zip        # 构建完成后生成发行 ZIP(dist/*.zip)
    python build.py --no-smoke   # 跳过冒烟测试
    python build.py --no-clean   # 复用 PyInstaller 缓存(增量构建,更快)

设计要点:
    1. hiddenimports 自动扫描 core/ 与 data/ 全部本地模块 —— 新增文件零维护;
       覆盖 app_shell 字符串懒加载页面(core.pages.xxx:WorldstatePage)这类
       PyInstaller 静态分析看不到的模块。
    2. datas 白名单显式化 —— data/ 中的旧管线遗留(all.json / dict.*.json)
       与运行期缓存(wm_items_cache.json)不进包,省 ~14MB。
    3. --windowed:不显示 CMD 窗口(用户决策,方案 §8.1)。
    4. UPX 关闭,降低杀软误报。
    5. 入口 dev.py:frozen 分支自动跳过提权/装依赖,直接运行 Qt 应用。
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
APP_NAME = "WARFRAME-RELIC"
ENTRY = PROJECT / "dev.py"
DIST = PROJECT / "dist"
BUILD_DIR = PROJECT / "build"
APP_DIR = DIST / APP_NAME            # dist/WARFRAME-RELIC/
INTERNAL = APP_DIR / "_internal"     # dist/WARFRAME-RELIC/_internal/

# data/ 顶层不进包的 json:旧管线遗留 + 运行期缓存(首启自动生成)
_DATA_JSON_EXCLUDE = {
    "all.json",            # 6MB 旧管线遗留(运行时只读 external/ 下的同名文件)
    "dict.en.json",        # 3.8MB 旧管线遗留
    "dict.zh.json",        # 3.8MB 旧管线遗留
    "wm_items_cache.json", # 价格查询缓存,冷启动后自动重建
}

# ── 日志 ──────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def _ok(msg: str) -> None:
    print(f"[build]   OK  {msg}", flush=True)


def _fail(msg: str) -> None:
    print(f"[build]  FAIL {msg}", flush=True)


# ── 1. hiddenimports 自动扫描 ─────────────────────────────────────────

def collect_local_modules() -> list[str]:
    """扫描 core/ 与 data/ 下全部 .py → 模块名(新增文件零维护)。"""
    mods: set[str] = set()
    for pkg in ("core", "data"):
        for p in (PROJECT / pkg).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            mods.add(".".join(p.relative_to(PROJECT).with_suffix("").parts))
    return sorted(mods)


# ── 2. datas 显式清单(白名单制) ──────────────────────────────────────

def collect_datas() -> list[tuple[str, str]]:
    """返回 (源路径, 包内目标目录) 清单。"""
    datas: list[tuple[str, str]] = []

    # assets/(字体 + 图标)整目录 → _internal/assets/
    for p in sorted((PROJECT / "assets").rglob("*")):
        if p.is_file():
            datas.append((str(p), str(p.relative_to(PROJECT).parent)))

    data_dir = PROJECT / "data"

    # 顶层 json 模板(排除遗留/缓存)→ _internal/data/
    for p in sorted(data_dir.glob("*.json")):
        if p.name not in _DATA_JSON_EXCLUDE:
            datas.append((str(p), "data"))

    # 初始数据库(139MB,首启复制到用户目录)
    datas.append((str(data_dir / "warframe.db"), "data"))

    # 只读子目录:tokens 预设 + 世界状态节点翻译表
    for sub in ("presets", "worldstate"):
        for p in sorted((data_dir / sub).rglob("*")):
            if p.is_file():
                datas.append((str(p), f"data/{sub}"))

    return datas


# ── 3. PyInstaller 构建 ──────────────────────────────────────────────

# (import 名, pip 包名) —— 打包前必须存在于当前解释器的关键依赖
_REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("PyInstaller", "pyinstaller"),
    ("PySide6", "PySide6"),
    ("requests", "requests"),
    ("yaml", "PyYAML"),
    ("numpy", "numpy"),
    ("PIL", "Pillow"),
    ("cv2", "opencv-python"),
    ("rapidocr_onnxruntime", "rapidocr-onnxruntime"),
]


def preflight_check() -> None:
    """打包前依赖预检:当前解释器缺关键包时立即失败,给出明确安装命令。

    背景:PyInstaller 只收集「执行 build.py 的那个解释器」里的包。
    系统存在多个 Python 时极易用错解释器,缺包要等到几分钟构建后的
    冒烟测试才暴露 —— 这里在构建前一秒拦下。
    """
    missing: list[str] = []
    for import_name, pip_name in _REQUIRED_PACKAGES:
        if importlib.util.find_spec(import_name) is None:
            missing.append(pip_name)
    if not missing:
        _ok(f"依赖预检通过({len(_REQUIRED_PACKAGES)} 个关键包齐全)")
        return

    _fail("依赖预检失败:当前解释器缺少以下包")
    print(f"    当前解释器: {sys.executable}", flush=True)
    print(f"    缺失: {', '.join(missing)}", flush=True)
    print("    安装命令:", flush=True)
    print(f'    "{sys.executable}" -m pip install ' + " ".join(missing), flush=True)
    print("    (注意:必须用上面这个解释器安装,装到别的 Python 无效)", flush=True)
    sys.exit(1)


def run_build(clean: bool) -> None:
    mods = collect_local_modules()
    datas = collect_datas()
    _log(f"hiddenimports: {len(mods)} 个本地模块(自动扫描)")
    _log(f"datas: {len(datas)} 个文件(显式清单)")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--distpath", str(DIST),
        "--workpath", str(BUILD_DIR),
        "--specpath", str(BUILD_DIR),   # spec 生成到 build/,不污染根目录
        "--name", APP_NAME,
        "--onedir",
        "--windowed",                    # 用户决策:不显示 CMD 窗口
        "--noupx",                       # 降低杀软误报
        "--collect-all", "rapidocr_onnxruntime",  # OCR 模型随包
        "--exclude-module", "PyQt5",     # 铁律:新旧 Qt 绝不混用
        "--exclude-module", "PyQt6",
        "--exclude-module", "tkinter",
        # 零引用连带库(省 ~466MB):grep 全项目无 import,
        # PyInstaller 扫描 rapidocr/matplotlib 依赖声明时误连带
        "--exclude-module", "torch",         # 360MB,最大浪费源
        "--exclude-module", "torchvision",   # 11MB
        "--exclude-module", "scipy",         # 72MB(含 scipy.libs)
        "--exclude-module", "pandas",        # 13MB
        "--exclude-module", "matplotlib",    # 12MB
        "--paths", str(PROJECT),
    ]
    if clean:
        cmd.append("--clean")
    for m in mods:
        cmd += ["--hiddenimport", m]
    for src, dst in datas:
        cmd += ["--add-data", f"{src};{dst}"]
    cmd.append(str(ENTRY))

    _log("PyInstaller 运行中(完整输出见 build/pyinstaller.log)...")
    t0 = time.time()
    BUILD_DIR.mkdir(exist_ok=True)
    log_file = BUILD_DIR / "pyinstaller.log"
    with open(log_file, "w", encoding="utf-8") as f:
        proc = subprocess.run(
            cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(PROJECT),
        )
    if proc.returncode != 0:
        _fail(f"PyInstaller 失败(exit={proc.returncode}),日志尾部:")
        tail = log_file.read_text(encoding="utf-8", errors="replace")
        for line in tail.splitlines()[-30:]:
            print("    " + line, flush=True)
        sys.exit(1)
    _ok(f"PyInstaller 完成,耗时 {time.time() - t0:.0f}s")


# ── 4. 构建后自检 ────────────────────────────────────────────────────

def self_check() -> tuple[list[str], int]:
    """检查关键资源是否齐全。返回 (缺失项, 检查总数)。"""
    checks = [
        APP_DIR / f"{APP_NAME}.exe",
        INTERNAL / "data" / "warframe.db",
        INTERNAL / "data" / "pixel_font.json",
        INTERNAL / "data" / "presets" / "cyberpunk.yaml",
        INTERNAL / "data" / "worldstate" / "solNodes.json",
        INTERNAL / "assets" / "fonts" / "Iceberg-Regular.ttf",
        INTERNAL / "assets" / "icons" / "nav_toggles.svg",
        INTERNAL / "PySide6",
        INTERNAL / "rapidocr_onnxruntime",  # collect-all 产物(OCR 模型)
    ]
    missing = [str(c.relative_to(APP_DIR)) for c in checks if not c.exists()]
    return missing, len(checks)


def _dir_size_mb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1024 / 1024


# ── 5. 冒烟测试 ──────────────────────────────────────────────────────

def smoke() -> bool:
    """启动 exe 观察 6 秒:存活且 stderr 无 traceback 才算通过。

    注意: windowed 应用崩溃时 PyInstaller 会弹错误对话框,进程不会退出,
    仅凭"进程存活"判断会假阳性 —— 必须同时检查 stderr 中的 traceback。
    (父进程提供 PIPE 时 windowed 进程的 stderr 句柄有效,
    PyInstaller 崩溃时会先把 traceback 写入 stderr 再弹框。)
    """
    exe = APP_DIR / f"{APP_NAME}.exe"
    _log("冒烟测试: 启动 exe,观察 6 秒 ...")
    proc = subprocess.Popen(
        [str(exe)], cwd=str(APP_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        time.sleep(6)
        alive = proc.poll() is None
    finally:
        # onedir 的 exe 是 bootloader,真实应用跑在其派生的子进程里;
        # terminate 只杀父进程,子进程会残留并锁住 dist 文件,
        # 下次打包 rmtree 时 PermissionError → 必须杀整棵进程树。
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
        )
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        # 兜底:父进程已先退但子进程成孤儿的情况,按映像名清理
        # (也会顺带清掉用户上次手动测试后忘关的 exe,防打包被锁)
        subprocess.run(
            ["taskkill", "/IM", f"{APP_NAME}.exe", "/F"],
            capture_output=True,
        )
        # 子进程已终止,管道关闭,一次性读出缓冲内容
        err = b""
        if proc.stderr:
            err = proc.stderr.read() or b""
            proc.stderr.close()
        if proc.stdout:
            proc.stdout.close()

    # 路径治理证据:首启应在 exe 旁生成用户 data/(数据库等模板复制)
    if (APP_DIR / "data").exists():
        _ok("路径治理生效: 首启已在 exe 旁生成 data/ 用户目录")
    # 发行前清掉冒烟产生的用户数据,保持出厂干净
    shutil.rmtree(APP_DIR / "data", ignore_errors=True)

    if b"Traceback" in err:
        _fail("冒烟测试发现崩溃 traceback(stderr 尾部):")
        for line in err.decode("utf-8", errors="replace").splitlines()[-12:]:
            print("    " + line, flush=True)
        return False
    return alive


# ── 6. 发行 ZIP ──────────────────────────────────────────────────────

def make_zip() -> Path:
    stamp = time.strftime("%Y%m%d")
    base = DIST / f"{APP_NAME}_win64_{stamp}"
    _log(f"生成 ZIP: {base.name}.zip ...")
    shutil.make_archive(str(base), "zip", root_dir=DIST, base_dir=APP_NAME)
    return base.with_suffix(".zip")


# ── main ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="WARFRAME-RELIC 一键打包")
    ap.add_argument("--zip", action="store_true", help="构建后生成发行 ZIP")
    ap.add_argument("--no-smoke", action="store_true", help="跳过冒烟测试")
    ap.add_argument("--no-clean", action="store_true", help="复用 PyInstaller 缓存")
    args = ap.parse_args()

    if not ENTRY.exists():
        _fail(f"入口不存在: {ENTRY}")
        sys.exit(1)

    _log("=" * 50)
    _log("WARFRAME-RELIC 打包开始(onedir + windowed)")
    _log("=" * 50)

    preflight_check()
    run_build(clean=not args.no_clean)

    missing, total = self_check()
    if missing:
        _fail(f"自检缺项 {len(missing)}/{total}:")
        for m in missing:
            print("    - " + m, flush=True)
        sys.exit(1)
    _ok(f"自检通过({total} 项关键资源齐全)")

    _ok(f"产物: {APP_DIR}  ({_dir_size_mb(APP_DIR):.0f} MB)")

    if not args.no_smoke:
        if smoke():
            _ok("冒烟测试通过(6 秒未闪退)")
        else:
            _fail("冒烟测试失败: 进程提前退出(疑似缺依赖闪退)")
            sys.exit(1)

    if args.zip:
        z = make_zip()
        _ok(f"ZIP 完成: {z.name}  ({z.stat().st_size / 1024 / 1024:.0f} MB)")

    _log("全部完成")


if __name__ == "__main__":
    main()
