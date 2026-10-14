"""
[L-Service] LicenseService — 离线机器绑定授权（激活码校验）

依赖: Python 标准库 + cryptography(Ed25519) + core.paths
禁止: PySide6 / QtWidgets / QtGui / QtCore（纯逻辑层）
返回: bool / str / dict（绝不返回 Qt 对象）

工作模型（全程离线）:
  用户电脑硬件指纹(2 因子) → 机器码 → 发给作者；
  作者用 tools/license_tool.py 私钥签发激活码 → 用户输入；
  本服务用内置公钥验签 + 比对本机指纹，通过后写 data/license.dat。
  安装包转发到其他电脑：指纹不同且无私钥，无法通过验证。

安全边界: 防"随手转发"，不防专业逆向（PyInstaller 产物可被反编译）。
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import winreg
from ctypes import wintypes
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from core.paths import user_data_dir

# ============================================================
# 内置公钥（私钥只在作者本机 tools/license_keys/，永不进包）
# ============================================================
# 由 `python tools/license_tool.py init` 生成；重新生成密钥对后，
# 需把新公钥 PEM 同步到此处并重新打包（旧激活码会全部失效）。
PUBLIC_KEY_PEM = b"""
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAI4y5gZ2csHvP35Ulr08mjhVY2B5PJ7Ztkx+IVTSQRjc=
-----END PUBLIC KEY-----
"""

# 签名域分隔前缀：防止同一签名被挪作其他用途
LICENSE_SIGN_PREFIX = b"WFRELIC-LIC-V1\n"

# 指纹取 SHA256 前 15 字节 → Base32 恰好 24 个字符
FP_BYTES = 15
MACHINE_CODE_LEN = 24
# Ed25519 签名 64 字节 → Base32 无填充恰好 103 个字符
ACTIVATION_CODE_LEN = 103

LICENSE_FILE_NAME = "license.dat"

# activate() 返回的原因码（UI 层据此映射文案）
REASON_OK = "ok"
REASON_FP_UNAVAILABLE = "fp_unavailable"
REASON_BAD_FORMAT = "bad_format"
REASON_INVALID = "invalid"

# Base32 字母表（RFC 4648），激活码只允许这些字符
_BASE32_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")

# 公钥惰性缓存：PEM 解析只需一次，避免每次验签重复解析
_public_key_cache = None


def _get_public_key():
    """解析内置公钥（进程内只解析一次）。"""
    global _public_key_cache
    if _public_key_cache is None:
        _public_key_cache = load_pem_public_key(PUBLIC_KEY_PEM)
    return _public_key_cache


# ============================================================
# 编码工具（service 与 tools/license_tool.py 共用）
# ============================================================

def base32_encode(raw: bytes) -> str:
    """字节 → 无填充大写 Base32。"""
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def base32_decode(text: str) -> bytes | None:
    """无填充 Base32 → 字节；非法输入返回 None。"""
    try:
        padded = text + "=" * ((8 - len(text) % 8) % 8)
        return base64.b32decode(padded, casefold=True)
    except Exception:
        return None


def normalize_code(text: str) -> str:
    """用户输入标准化：去横杠/空格/换行、转大写、只留 Base32 合法字符。"""
    return "".join(ch for ch in text.strip().upper() if ch in _BASE32_ALPHABET)


def group_code(code: str, group_size: int = 4) -> str:
    """把连续码按固定长度用横杠分组（仅用于显示）。"""
    return "-".join(
        code[i:i + group_size] for i in range(0, len(code), group_size)
    )


def decode_machine_code(text: str) -> bytes | None:
    """机器码（可含横杠/空格）→ 指纹字节；格式错返回 None。"""
    norm = normalize_code(text)
    if len(norm) != MACHINE_CODE_LEN:
        return None
    fp = base32_decode(norm)
    if fp is None or len(fp) != FP_BYTES:
        return None
    return fp


# ============================================================
# 硬件指纹（严格 2 因子：Windows 安装 ID + 系统盘卷序列号）
# ============================================================

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.GetVolumeInformationW.argtypes = [
    wintypes.LPCWSTR,           # lpRootPathName
    wintypes.LPWSTR,            # lpVolumeNameBuffer
    wintypes.DWORD,             # nVolumeNameSize
    ctypes.POINTER(wintypes.DWORD),  # lpVolumeSerialNumber
    ctypes.POINTER(wintypes.DWORD),  # lpMaximumComponentLength
    ctypes.POINTER(wintypes.DWORD),  # lpFileSystemFlags
    wintypes.LPWSTR,            # lpFileSystemNameBuffer
    wintypes.DWORD,             # nFileSystemNameSize
]
_kernel32.GetVolumeInformationW.restype = wintypes.BOOL


def _read_machine_guid() -> str:
    """读取 Windows 安装 ID（MachineGuid）。

    显式访问 64 位注册表视图，避免 32 位进程被重定向到 WOW6432Node。
    """
    # 显式访问 64 位注册表视图（老版本 Windows 无此标志时退回默认视图）
    access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Cryptography",
        0,
        access,
    ) as key:
        value, _vtype = winreg.QueryValueEx(key, "MachineGuid")
    guid = str(value).strip()
    if not guid:
        raise RuntimeError("MachineGuid 为空")
    return guid


def _read_system_drive_serial() -> int:
    """读取系统盘卷序列号（重装/格式化系统盘才会变）。"""
    root = os.environ.get("SystemDrive", "C:") + "\\"
    serial = wintypes.DWORD(0)
    ok = _kernel32.GetVolumeInformationW(
        root, None, 0, ctypes.byref(serial), None, None, None, 0
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(serial.value)


def collect_fingerprint() -> bytes:
    """采集严格 2 因子指纹。

    任一因子采集失败即抛异常，由上层按"无法验证"安全降级。
    """
    guid = _read_machine_guid().lower()
    serial = _read_system_drive_serial()
    digest = hashlib.sha256(f"{guid}|{serial:08X}".encode("utf-8")).digest()
    return digest[:FP_BYTES]


# ============================================================
# 授权服务（单例）
# ============================================================

class LicenseService:
    """离线机器绑定授权服务。

    用法::

        svc = LicenseService.instance()
        if not svc.licensed:
            code = ...  # 用户输入
            ok, reason = svc.activate(code)
    """

    _instance: "LicenseService | None" = None

    @classmethod
    def instance(cls) -> "LicenseService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._fp: bytes | None = None
        self._fp_error: str = ""
        self._machine_code: str = ""
        self._licensed: bool = False
        self._collect()
        self.reload()

    # ── 只读状态 ──

    @property
    def licensed(self) -> bool:
        """当前是否已通过本机授权（内存缓存，activate/reload 后更新）。"""
        return self._licensed

    @property
    def machine_code(self) -> str:
        """本机机器码（分组显示形态）；指纹采集失败时为空串。"""
        return self._machine_code

    @property
    def machine_code_plain(self) -> str:
        """本机机器码（无分隔符）；指纹采集失败时为空串。"""
        if self._fp is None:
            return ""
        return base32_encode(self._fp)

    @property
    def fingerprint_error(self) -> str:
        """指纹采集失败原因（空串表示成功）。"""
        return self._fp_error

    # ── 核心操作 ──

    def reload(self) -> bool:
        """重新读取 license.dat 并校验，返回是否授权通过。"""
        self._licensed = False
        if self._fp is None:
            return False

        code = self._read_stored_code()
        if code:
            self._licensed = self._verify(code, self._fp)
        return self._licensed

    def activate(self, code_text: str) -> tuple[bool, str]:
        """校验用户输入的激活码，成功则持久化。

        Returns:
            (是否成功, 原因码)；原因码见模块顶部 REASON_* 常量。
        """
        if self._fp is None:
            return False, REASON_FP_UNAVAILABLE

        norm = normalize_code(code_text)
        if len(norm) != ACTIVATION_CODE_LEN:
            return False, REASON_BAD_FORMAT

        if not self._verify(norm, self._fp):
            return False, REASON_INVALID

        # 落盘失败也放行本次会话（仅下次启动需重新输入）；
        # _write_stored_code 内部已吞掉 IO 异常并返回 False
        self._write_stored_code(norm)
        self._licensed = True
        return True, REASON_OK

    # ── 内部实现 ──

    def _collect(self) -> None:
        try:
            self._fp = collect_fingerprint()
            self._machine_code = group_code(base32_encode(self._fp))
            self._fp_error = ""
        except Exception as e:
            self._fp = None
            self._machine_code = ""
            self._fp_error = f"{type(e).__name__}: {e}"

    def _verify(self, code_norm: str, fp: bytes) -> bool:
        """公钥验签 + 本机指纹比对（双重检查，缺一不可）。"""
        if len(code_norm) != ACTIVATION_CODE_LEN or len(fp) != FP_BYTES:
            return False
        signature = base32_decode(code_norm)
        if signature is None:
            return False
        try:
            _get_public_key().verify(signature, LICENSE_SIGN_PREFIX + fp)
            return True
        except InvalidSignature:
            return False
        except Exception:
            # 公钥/数据形态异常等一律按"验签未通过"安全处理，绝不放行
            return False

    def _license_path(self) -> Path:
        return user_data_dir() / LICENSE_FILE_NAME

    def _read_stored_code(self) -> str:
        try:
            # utf-8-sig 同时兼容无 BOM（本软件写入）与带 BOM（外部编辑器另存）两种文件
            with open(self._license_path(), "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            code = normalize_code(str(data.get("code", "")))
            return code if len(code) == ACTIVATION_CODE_LEN else ""
        except Exception:
            return ""

    def _write_stored_code(self, code_norm: str) -> bool:
        """原子写入 license.dat，防止写一半导致文件损坏。"""
        path = self._license_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".dat.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"code": code_norm}, f, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False
