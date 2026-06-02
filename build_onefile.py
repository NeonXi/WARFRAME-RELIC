"""
WARFRAME-RELIC 单文件 EXE 打包脚本 (--onefile)

与 build_exe.py（--onedir 文件夹模式）不同，此脚本生成单个 .exe 文件。
优点: 分发方便，一个文件即可运行
缺点: 每次启动需解压到临时目录，首次启动较慢（10-15 秒）
"""
import subprocess
import sys
import os
import time
import shutil
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).parent
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
OUTPUT_NAME = "WARFRAME-RELIC"


def print_header(text):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")
    print()


def print_step(num, total, text):
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
    py = ROOT / "venv" / "Scripts" / "python.exe"
    if py.exists():
        return str(py)
    return sys.executable


def _kill_stale():
    try:
        subprocess.run(
            ["taskkill", "/f", "/im", f"{OUTPUT_NAME}.exe"],
            capture_output=True, timeout=5, check=False
        )
    except Exception:
        pass


def _find_upx():
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
    for p in os.environ.get("PATH", "").split(os.pathsep):
        upx = Path(p) / "upx.exe"
        if upx.exists():
            return str(upx)
    return None


def step_check_env(python):
    print_step(1, 4, "检查 Python 环境")
    try:
        result = subprocess.run(
            [python, "--version"], capture_output=True, text=True, check=True
        )
        ver = result.stdout.strip() or result.stderr.strip()
        print_ok(f"Python: {ver}")
    except Exception as e:
        print_err(f"无法获取 Python 版本: {e}")
        return False

    pkgs = ["PyQt6", "dxcam", "keyboard", "rapidocr_onnxruntime", "PIL", "numpy", "pypinyin"]
    all_ok = True
    for pkg in pkgs:
        try:
            subprocess.run([python, "-c", f"import {pkg}"], capture_output=True, check=True)
            print(f"    [+] {pkg}")
        except subprocess.CalledProcessError:
            print(f"    [-] {pkg} 缺失!")
            all_ok = False
    if not all_ok:
        print_err("缺少依赖! 请先运行 SETUP.bat")
        return False

    # 检查 PyInstaller
    try:
        subprocess.run([python, "-m", "pip", "show", "pyinstaller"], capture_output=True, check=True)
        print_ok("PyInstaller 已安装")
    except subprocess.CalledProcessError:
        print_warn("PyInstaller 未安装，正在安装...")
        subprocess.run(
            [python, "-m", "pip", "install", "pyinstaller",
             "-i", "https://mirrors.cloud.tencent.com/pypi/simple"],
            check=True
        )
        print_ok("PyInstaller 安装完成")

    return True


def step_clean():
    print_step(2, 4, "清理旧构建")
    _kill_stale()
    for path, name in [(BUILD_DIR, "build/"), (DIST_DIR, "dist/")]:
        if path.exists():
            print(f"  删除 {name}...", end=" ")
            try:
                shutil.rmtree(path)
                print("Done")
            except Exception as e:
                print(f"失败: {e}")
                return False
        else:
            print(f"  [SKIP] {name} 不存在")
    print_ok("清理完成")
    return True


def step_build(python):
    print_step(3, 4, "PyInstaller 单文件打包")
    print()

    upx_path = _find_upx()
    if upx_path:
        print_info(f"UPX 已找到: {upx_path}")
    else:
        print_warn("未找到 UPX，跳过压缩 (下载: https://upx.github.io/)")

    # --onefile 模式的关键参数
    cmd = [
        python, "-m", "PyInstaller",
        "--onefile",                          # <-- 单文件模式
        "--noconsole",
        "--name", OUTPUT_NAME,
        "--add-data", f"data{os.pathsep}data",
        "--add-data", f"core{os.pathsep}core",
        "--add-data", f"recognizers{os.pathsep}recognizers",
        "--add-data", f"qt.conf{os.pathsep}.",
        # 排除无关大包
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
        # 排除用不到的 PyQt6 子模块
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
    if upx_path:
        cmd.extend(["--upx-dir", str(Path(upx_path).parent)])
    cmd.append(str(ROOT / "main.py"))

    print(f"  模式: --onefile (单文件 EXE)")
    print(f"  (首次打包约 5-10 分钟，请耐心等待...)")
    print()

    start_time = time.time()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, cwd=str(ROOT)
    )

    collected = 0
    for line in process.stdout:
        line_s = line.strip()
        if "INFO: Building" in line_s and "EXE" in line_s:
            print(f"\n  >>> 正在生成单文件 EXE (此步骤较慢)...")
        if any(kw in line_s for kw in ["INFO: Analyzing", "INFO: Processing", "INFO: copying"]):
            collected += 1
            if len(line_s) > 100:
                line_s = line_s[:97] + "..."
            print(f"  {collected:>4}  {line_s}")
        elif "WARNING" in line_s and "_mypyc" not in line_s:
            print(f"  [WARN] {line_s}")
        elif "ERROR" in line_s:
            print(f"  [ERR] {line_s}")

    process.wait()
    elapsed = time.time() - start_time

    print()
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    print(f"  耗时: {mins}m {secs}s")

    if process.returncode != 0:
        print_err(f"打包失败! (exit code: {process.returncode})")
        return False

    print_ok("单文件 EXE 打包完成")
    return True


def step_verify():
    print_step(4, 4, "验证输出")

    exe_path = DIST_DIR / f"{OUTPUT_NAME}.exe"

    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print_ok(f"产物: {exe_path}")
        print(f"  大小: {size_mb:.1f} MB")
        print()
        print(f"  说明:")
        print(f"    - 这是单文件 EXE，直接双击运行即可")
        print(f"    - 首次启动约 10-15 秒 (解压到临时目录)")
        print(f"    - 后续启动约 3-5 秒")
        print(f"    - 临时目录: %TEMP%\\_MEI*\\ (退出后自动清理)")
        return True
    else:
        print_err(f"输出文件不存在: {exe_path}")
        if DIST_DIR.exists():
            for f in DIST_DIR.iterdir():
                print(f"    {f.name}")
        return False


def main():
    print()
    print_header("WARFRAME-RELIC - 单文件 EXE 打包")
    print(f"  开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  注意: 单文件模式启动较慢，适合分发")
    print(f"        日常使用建议用 打包.bat (文件夹模式)")

    python = get_python()

    steps = [
        ("检查环境", lambda: step_check_env(python)),
        ("清理旧构建", step_clean),
        ("单文件打包", lambda: step_build(python)),
        ("验证输出", step_verify),
    ]

    for i, (name, fn) in enumerate(steps, 1):
        try:
            if not fn():
                print(f"\n*** 打包失败于 [{i}/{len(steps)}] {name} ***")
                input("\n按 Enter 退出...")
                sys.exit(1)
        except KeyboardInterrupt:
            print("\n\n用户取消")
            sys.exit(1)
        except Exception as e:
            print(f"\n*** 异常: {e} ***")
            import traceback
            traceback.print_exc()
            input("\n按 Enter 退出...")
            sys.exit(1)

    print()
    print(f"{'=' * 60}")
    print(f"  打包成功!")
    print(f"{'=' * 60}")
    print(f"  单文件 EXE: dist\\{OUTPUT_NAME}.exe")
    print(f"  结束: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    input("按 Enter 退出...")


if __name__ == "__main__":
    main()
