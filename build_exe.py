"""
WARFRAME-RELIC 打包脚本
带进度条的 PyInstaller 打包流程，让用户能清楚看到每个步骤的进展。
"""
import subprocess
import sys
import os
import time
import shutil
import re
from pathlib import Path

# 确保 Python 输出使用 UTF-8（配合 chcp 65001）
os.environ["PYTHONIOENCODING"] = "utf-8"
# 禁用输出缓冲，确保实时显示进度
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).parent
SPEC_FILE = ROOT / "WARFRAME-RELIC.spec"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"


def progress_bar(current, total, label="", width=40):
    """绘制进度条 (纯 ASCII)"""
    pct = current / total if total > 0 else 0
    filled = int(width * pct)
    bar = "#" * filled + "-" * (width - filled)
    return f"  {label} [{bar}] {pct * 100:5.1f}%  ({current}/{total})"


def print_header(text):
    """打印标题"""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")
    print()


def print_step(num, total, text):
    """打印步骤标题"""
    print(f"\n>>> [{num}/{total}] {text}")
    print(f"{'-' * 60}")


def print_ok(text=""):
    print(f"  [OK] {text}")


def print_warn(text=""):
    print(f"  [WARN] {text}")


def print_err(text=""):
    print(f"  [ERR] {text}")


def print_info(text=""):
    print(f"  [*] {text}")


def get_python():
    """获取 venv 的 python"""
    py = ROOT / "venv" / "Scripts" / "python.exe"
    if py.exists():
        return str(py)
    return sys.executable


def step_check_env(python):
    """步骤1: 检查环境"""
    print_step(1, 5, "Check Python Environment")

    print(f"  Python path: {python}")
    try:
        result = subprocess.run(
            [python, "--version"], capture_output=True, text=True, check=True
        )
        ver = result.stdout.strip() or result.stderr.strip()
        print_ok(f"Python version: {ver}")
    except Exception as e:
        print_err(f"Cannot get Python version: {e}")
        return False

    # 检查关键包
    pkgs = ["PyQt6", "dxcam", "keyboard", "rapidocr_onnxruntime", "PIL", "numpy", "pypinyin"]
    print(f"\n  Checking dependencies...")
    all_ok = True
    for pkg in pkgs:
        try:
            subprocess.run(
                [python, "-c", f"import {pkg}"],
                capture_output=True, check=True
            )
            print(f"    [+] {pkg}")
        except subprocess.CalledProcessError:
            print(f"    [-] {pkg} MISSING!")
            all_ok = False

    if not all_ok:
        print_err("Missing dependencies! Run WARFRAME-RELIC.bat first.")
        return False

    print_ok("Environment check passed")
    return True


def step_install_pyinstaller(python):
    """步骤2: 检查/安装 PyInstaller"""
    print_step(2, 5, "Check PyInstaller")

    try:
        result = subprocess.run(
            [python, "-m", "pip", "show", "pyinstaller"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    ver = line.split(":")[1].strip()
                    print_ok(f"PyInstaller already installed (v{ver})")
                    return True

        # 未安装，开始安装
        print(f"  Installing PyInstaller...")
        print(f"  (Using Tencent Cloud mirror)")
        print()

        # 实时显示 pip 安装进度
        process = subprocess.Popen(
            [python, "-m", "pip", "install", "pyinstaller",
             "-i", "https://mirrors.cloud.tencent.com/pypi/simple"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        for line in process.stdout:
            line = line.strip()
            if line:
                if "Downloading" in line:
                    print(f"  [D] {line[:80]}")
                elif "Installing" in line:
                    print(f"  [I] {line[:80]}")
                elif "Successfully" in line:
                    print(f"  [OK] {line}")
                elif "already satisfied" in line:
                    print(f"  [OK] {line}")
                elif "ERROR" in line or "error" in line.lower():
                    print(f"  [ERR] {line}")

        process.wait()
        if process.returncode != 0:
            print_err("PyInstaller installation failed!")
            return False

        print_ok("PyInstaller installed successfully")
        return True

    except Exception as e:
        print_err(f"Error installing PyInstaller: {e}")
        return False


def _kill_stale_processes():
    """杀掉可能占用 dist/ 目录的残留进程（仅杀 EXE，不动 python）"""
    try:
        subprocess.run(
            ["taskkill", "/f", "/im", "WARFRAME-RELIC.exe"],
            capture_output=True, timeout=5, check=False
        )
    except Exception:
        pass

def step_clean():
    """步骤3: 清理旧构建"""
    print_step(3, 5, "Clean Old Build Files")

    # 先杀残留进程，避免文件被占用
    _kill_stale_processes()

    dirs_to_clean = {
        BUILD_DIR: "build/",
        DIST_DIR: "dist/",
    }

    for path, name in dirs_to_clean.items():
        if path.exists():
            print(f"  Deleting {name}...", end=" ")
            try:
                shutil.rmtree(path)
                print("Done")
            except Exception as e:
                print(f"Failed: {e}")
                print("  请手动关闭 WARFRAME-RELIC.exe 后重试")
                return False
        else:
            print(f"  [SKIP] {name} not found")

    # 清理 spec 文件
    if SPEC_FILE.exists():
        print(f"  Deleting old .spec...", end=" ")
        SPEC_FILE.unlink()
        print("Done")

    print_ok("Cleanup completed")
    return True


def _find_upx():
    """查找 UPX 可执行文件"""
    # 1) PyInstaller 自带的 upx
    import importlib.util
    try:
        spec = importlib.util.find_spec("PyInstaller")
        if spec and spec.submodule_search_locations:
            pyi_dir = Path(spec.submodule_search_locations[0]).parent.parent
            for upx_exe in [pyi_dir / "upx.exe", pyi_dir / "bin" / "upx.exe"]:
                if upx_exe.exists():
                    return str(upx_exe)
    except Exception:
        pass

    # 2) PATH 中的 upx
    for p in os.environ.get("PATH", "").split(os.pathsep):
        upx = Path(p) / "upx.exe"
        if upx.exists():
            return str(upx)

    return None


def step_build(python):
    """步骤4: PyInstaller 打包（带实时进度显示）"""
    print_step(4, 5, "PyInstaller Build")
    print()

    # 检测 UPX
    upx_path = _find_upx()
    if upx_path:
        print_info(f"UPX found: {upx_path}")
    else:
        print_warn("UPX not found, skip compression (download from https://upx.github.io/)")

    # PyInstaller 参数
    cmd = [
        python, "-m", "PyInstaller",
        "--onedir",
        "--noconsole",
        "--name", "WARFRAME-RELIC",
        "--add-data", f"data{os.pathsep}data",
        "--add-data", f"core{os.pathsep}core",
        "--add-data", f"recognizers{os.pathsep}recognizers",
        "--add-data", f"qt.conf{os.pathsep}.",
        # 排除 rapidocr-onnxruntime 拉进来的无关大包（torch/scipy/pandas 等）
        # 注意：shapely 是 rapidocr_onnxruntime 的依赖，不能排除！
        "--exclude-module", "torch",
        "--exclude-module", "torchvision",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "google.protobuf",
        "--exclude-module", "dateutil",
        "--exclude-module", "setuptools",
        "--exclude-module", "charset_normalizer",
        "--exclude-module", "chardet",
        "--exclude-module", "certifi",
        "--exclude-module", "markupsafe",
        "--exclude-module", "tzdata",
        "--exclude-module", "safetensors",
        "--exclude-module", "psutil",
        # 排除用不到的 PyQt6 子模块（减小体积）
        "--exclude-module", "PyQt6.QtWebEngine",
        "--exclude-module", "PyQt6.QtWebEngineCore",
        "--exclude-module", "PyQt6.QtWebEngineWidgets",
        "--exclude-module", "PyQt6.QtWebChannel",
        "--exclude-module", "PyQt6.QtMultimedia",
        "--exclude-module", "PyQt6.QtMultimediaWidgets",
        "--exclude-module", "PyQt6.QtBluetooth",
        "--exclude-module", "PyQt6.QtSensors",
        "--exclude-module", "PyQt6.QtSerialPort",
        "--exclude-module", "PyQt6.QtSql",
        "--exclude-module", "PyQt6.QtSvg",
        "--exclude-module", "PyQt6.QtSvgWidgets",
        "--exclude-module", "PyQt6.QtTest",
        "--exclude-module", "PyQt6.QtPrintSupport",
        "--exclude-module", "PyQt6.QtHelp",
        "--exclude-module", "PyQt6.QtXml",
        "--exclude-module", "PyQt6.QtQml",
        "--exclude-module", "PyQt6.QtQuick",
        "--exclude-module", "PyQt6.QtQuickWidgets",
        "--exclude-module", "PyQt6.QtDesigner",
        "--exclude-module", "PyQt6.QtOpenGL",
        "--exclude-module", "PyQt6.QtOpenGLWidgets",
        "--exclude-module", "PyQt6.QtTextToSpeech",
        "--exclude-module", "PyQt6.QtPositioning",
        "--exclude-module", "PyQt6.QtNfc",
        "--exclude-module", "PyQt6.QtNetwork",
        "--exclude-module", "PyQt6.QtDBus",
        "--exclude-module", "PyQt6.QtPdf",
        "--exclude-module", "PyQt6.QtPdfWidgets",
        "--exclude-module", "PyQt6.Qt3DCore",
        "--exclude-module", "PyQt6.Qt3DRender",
        "--exclude-module", "PyQt6.Qt3DInput",
        "--exclude-module", "PyQt6.Qt3DAnimation",
        "--exclude-module", "PyQt6.Qt3DLogic",
        "--exclude-module", "PyQt6.Qt3DExtras",
        "--exclude-module", "PyQt6.QtDataVisualization",
        "--exclude-module", "PyQt6.QtCharts",
        "--exclude-module", "PyQt6.QtRemoteObjects",
        "--exclude-module", "PyQt6.QtSpatialAudio",
        "--exclude-module", "PyQt6.QtStateMachine",
        "--exclude-module", "PyQt6.QtWebSockets",
        "--exclude-module", "PyQt6.QtHttpServer",
        "--collect-all", "rapidocr_onnxruntime",
        "--collect-all", "onnxruntime",
        "--collect-all", "dxcam",
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "dxcam",
        "--hidden-import", "keyboard",
        "--hidden-import", "rapidocr_onnxruntime",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "numpy",
        "--hidden-import", "onnxruntime",
        "--hidden-import", "json",
        "--hidden-import", "sqlite3",
        "--hidden-import", "pypinyin",
        "--hidden-import", "pypinyin.pinyin",
        "--hidden-import", "pypinyin.style",
        "--hidden-import", "core.bootstrap",
        "--hidden-import", "core.hotkey_manager",
        "--hidden-import", "core.mode_handlers",
        "--hidden-import", "core.bg_layer",
        "--hidden-import", "core.panel_styles",
        "--hidden-import", "core.panel_builder",
    ]
    # 如果找到 UPX，添加压缩参数
    if upx_path:
        cmd.extend(["--upx-dir", str(Path(upx_path).parent)])
    cmd.append(str(ROOT / "main.py"))

    # 打包阶段定义
    stage_names = [
        "1/4  Analyzing dependencies...",
        "2/4  Collecting modules...",
        "3/4  Building PKG...",
        "4/4  Building EXE...",
    ]

    current_stage = stage_names[0]
    stage_idx = 0

    print(f"  Stage: {current_stage}")
    print(f"  (First build may take 3-8 minutes, please wait...)")
    print()

    # 启动 PyInstaller
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, cwd=str(ROOT)
    )

    collected_count = 0
    start_time = time.time()

    # 进度条状态
    analysis_total = 0
    collect_total = 0

    for line in process.stdout:
        line_stripped = line.strip()

        # 检测阶段变化
        if "Building PKG" in line_stripped:
            if stage_idx < 2:
                stage_idx = 2
                current_stage = stage_names[stage_idx]
                print()
                print(f"  >>> Stage: {current_stage}")
        elif "Building EXE" in line_stripped:
            if stage_idx < 3:
                stage_idx = 3
                current_stage = stage_names[stage_idx]
                print()
                print(f"  >>> Stage: {current_stage}")

        # 解析进度信息
        if "Processing pre-safe-import" in line_stripped:
            analysis_total += 1
            if analysis_total % 10 == 0:
                sys.stdout.write(f"\r  Analyzed {analysis_total} modules...")
                sys.stdout.flush()

        elif "Processing module" in line_stripped:
            collect_total += 1
            if collect_total % 5 == 0:
                sys.stdout.write(f"\r  Collected {collect_total} modules...")
                sys.stdout.flush()

        # 显示关键信息
        if any(kw in line_stripped for kw in [
            "INFO: Analyzing", "INFO: Processing", "INFO: Building",
            "INFO: copying", "INFO: Appending", "INFO: Updating",
        ]):
            collected_count += 1
            # 截断过长的路径
            if len(line_stripped) > 100:
                line_stripped = line_stripped[:97] + "..."
            print(f"  {collected_count:>4}  {line_stripped}")

        # 警告和错误（过滤掉 _mypyc 等无害警告）
        elif "WARNING" in line_stripped:
            if "_mypyc" not in line_stripped:
                print(f"  [WARN] {line_stripped}")
        elif "ERROR" in line_stripped:
            print(f"  [ERR] {line_stripped}")

    # 清除进度行
    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()

    process.wait()
    elapsed = time.time() - start_time

    print()
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    print(f"  Elapsed: {mins}m {secs}s | Processed {collected_count} items | "
          f"Analyzed {analysis_total} modules | Collected {collect_total} modules")

    if process.returncode != 0:
        print_err(f"Build failed! (exit code: {process.returncode})")
        return False

    print_ok("PyInstaller build completed")
    return True


def step_verify():
    """步骤5: 验证输出"""
    print_step(5, 5, "Verify Output")

    exe_dir = DIST_DIR / "WARFRAME-RELIC"
    exe_path = exe_dir / "WARFRAME-RELIC.exe"

    if exe_path.exists():
        # 计算整个文件夹大小
        total_size = sum(
            f.stat().st_size for f in exe_dir.rglob("*") if f.is_file()
        )
        exe_size = exe_path.stat().st_size
        total_mb = total_size / (1024 * 1024)
        exe_mb = exe_size / (1024 * 1024)
        print_ok(f"Output: {exe_dir}")
        print(f"  EXE size: {exe_mb:.1f} MB ({exe_size:,} bytes)")
        print(f"  Total folder size: {total_mb:.1f} MB ({total_size:,} bytes)")

        # 列出文件夹中主要文件
        files = sorted(exe_dir.glob("*.dll")) + sorted(exe_dir.glob("*.exe"))
        if files:
            print(f"\n  Key files in dist/WARFRAME-RELIC/:")
            for f in files[:10]:
                size_kb = f.stat().st_size / 1024
                print(f"    {f.name:<40} {size_kb:>8.0f} KB")
            if len(files) > 10:
                print(f"    ... and {len(files) - 10} more")

        return True
    else:
        print_err("Output file not found!")
        print(f"  Expected: {exe_path}")

        # 列出 dist 目录内容
        if DIST_DIR.exists():
            files = list(DIST_DIR.iterdir())
            if files:
                print(f"\n  Contents of dist/:")
                for f in files:
                    print(f"    {f.name}")

        return False


def print_tips():
    """打印使用提示"""
    print()
    print(f"{'=' * 60}")
    print(f"  BUILD SUCCESS!")
    print(f"{'=' * 60}")
    print(f"  Output: dist\\WARFRAME-RELIC\\")
    print()
    print(f"  Notes:")
    print(f"    1. Distribute the entire 'WARFRAME-RELIC' folder")
    print(f"    2. Run: dist\\WARFRAME-RELIC\\WARFRAME-RELIC.exe")
    print(f"    3. First launch loads ~5-10s (no temp extraction needed)")
    print(f"    4. You can delete build/ folder to save space")
    print()


def main():
    print()
    print(f"{'=' * 60}")
    print(f"    WARFRAME-RELIC - Build to EXE")
    print(f"{'=' * 60}")
    print()
    print(f"  Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    python = get_python()

    # 执行各步骤
    steps = [
        ("Check Environment", lambda: step_check_env(python)),
        ("Check PyInstaller", lambda: step_install_pyinstaller(python)),
        ("Clean Old Builds", step_clean),
        ("PyInstaller Build", lambda: step_build(python)),
        ("Verify Output", step_verify),
    ]

    for i, (name, fn) in enumerate(steps, 1):
        try:
            if not fn():
                print(f"\n*** Build FAILED at step [{i}/{len(steps)}] {name} ***")
                print(f"Check the error messages above and retry.")
                input(f"\nPress Enter to exit...")
                sys.exit(1)
        except KeyboardInterrupt:
            print(f"\n\nBuild cancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n*** Unexpected error during build! ***")
            print(f"  {e}")
            import traceback
            traceback.print_exc()
            input(f"\nPress Enter to exit...")
            sys.exit(1)

    print_tips()
    print(f"  End: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    input(f"Press Enter to exit...")


if __name__ == "__main__":
    main()
