"""服务证据采集（待办 C5，任务卡 T-06）：服务二进制命令行清单（PathName 原文）。

机制自决：绝对路径 PowerShell 底座（_ps.py）+ Get-CimInstance Win32_Service 只读
查询；失败降级为 available=False，不抛异常。只读。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from ._ps import run_ps_script

_PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "Get-CimInstance Win32_Service | Where-Object { $_.PathName } | "
    "Select-Object -ExpandProperty PathName"
)
_TIMEOUT_SECONDS = 60


@dataclass
class ServiceResult:
    available: bool
    paths: list[str] = field(default_factory=list)
    reason: str = ""


def parse_path_lines(stdout: str) -> list[str]:
    """逐行解析服务命令行原文：去空行、去重、排序。"""
    return sorted({line.strip() for line in (stdout or "").splitlines() if line.strip()})


def collect_services(
    runner=subprocess.run, timeout_seconds: int = _TIMEOUT_SECONDS
) -> ServiceResult:
    """采集服务命令行清单；失败一律降级为 available=False。"""
    try:
        returncode, stdout, stderr = run_ps_script(
            runner, _PS_SCRIPT, timeout_seconds=timeout_seconds
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ServiceResult(available=False, reason=f"该证据源不可用：{exc.__class__.__name__}")
    if returncode != 0:
        detail = (stderr or "").strip()[:200]
        return ServiceResult(
            available=False, reason=f"该证据源不可用：PowerShell 退出码 {returncode}（{detail}）"
        )
    return ServiceResult(available=True, paths=parse_path_lines(stdout))
