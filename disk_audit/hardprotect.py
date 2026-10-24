"""硬保护规则（S-1）：先于一切判定，不可被任何配置覆盖。

依据：《磁盘体检 · v0.1 方案（定稿）》第 3 节 S-1、第 9.1 节底线一、文末安全边界。
- Roaming\\Microsoft\\Protect 与 Crypto（DPAPI 密钥）：删除将导致浏览器密码、证书、
  Wi-Fi 凭据永久无法解密；
- XP 兼容 Junction（Application Data / History / Temporary Internet Files 等）；
- Microsoft 系系统组件目录。

本模块保持纯函数、无 I/O、无配置入口；pytest 覆盖率要求 100%（M1 验收③）。
"""
from __future__ import annotations

from dataclasses import dataclass
import ntpath

__all__ = ["PROTECTED_LABEL", "Protection", "check_protection"]

PROTECTED_LABEL = "受保护·不可处理"


@dataclass(frozen=True)
class Protection:
    rule_id: str   # 规则标识，进报告证据链
    reason: str    # 人读证据，进报告展示

    @property
    def label(self) -> str:
        return PROTECTED_LABEL


# 规则一：DPAPI 密钥目录（位于 Microsoft 目录之下）
_DPAPI_PARENT = "microsoft"
_DPAPI_NAMES = frozenset({"protect", "crypto"})

# 规则二：XP 兼容 Junction（目录名出现在路径任意层级即命中）
_JUNCTION_NAMES = frozenset(
    {"application data", "history", "temporary internet files", "local settings"}
)

# 规则三：Microsoft 系系统组件目录（用户配置根下以 Microsoft 起头的目录树）
_SYSTEM_ROOT = "microsoft"


def _parts(path: str) -> list[str]:
    """规范化为小写路径组件列表；接受 / 与 \\ 两种分隔符，过滤盘符。"""
    norm = ntpath.normpath(path.replace("/", "\\"))
    return [
        p.lower()
        for p in norm.split("\\")
        if p and p != "." and not p.endswith(":") and not p.startswith("\\")
    ]


def check_protection(path: str) -> Protection | None:
    """返回硬保护判定；None 表示未命中（继续进入正常判定流水线）。

    调用方必须将本函数置于判定流水线最前，命中即短路返回，不参与打分。
    """
    parts = _parts(path)

    for name in _JUNCTION_NAMES:
        if name in parts:
            return Protection(
                "HARDPROTECT-JUNCTION",
                f"路径包含 XP 兼容 Junction 链接目录“{name}”，删除将导致旧程序路径解析故障",
            )

    for i, part in enumerate(parts):
        if part != _DPAPI_PARENT:
            continue
        if i + 1 < len(parts) and parts[i + 1] in _DPAPI_NAMES:
            return Protection(
                "HARDPROTECT-DPAPI",
                "DPAPI 密钥目录（Microsoft\\Protect / Crypto）：删除将导致已保存的密码、"
                "证书、Wi-Fi 凭据永久无法解密",
            )
        return Protection(
            "HARDPROTECT-SYSTEM",
            "Microsoft 系统组件目录，属于系统数据",
        )

    return None
