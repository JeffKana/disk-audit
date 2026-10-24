"""进程证据采集（待办 C5，任务卡 T-06）：当前运行进程的可执行文件路径清单。

机制自决：与 Appx 采集同款绝对路径 PowerShell 底座（_ps.py，W0-C5 教训），
Get-Process 只读查询；失败降级为 available=False，不抛异常。只读。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from ._ps import run_ps_script

_PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "Get-Process | Where-Object { $_.Path } | "
    "Select-Object -ExpandProperty Path -Unique"
)
_TIMEOUT_SECONDS = 60


@dataclass
class ProcessResult:
    available: bool
    paths: list[str] = field(default_factory=list)
    reason: str = ""


def parse_path_lines(stdout: str) -> list[str]:
    """逐行解析进程路径：去空行、去重、排序（稳定输出便于比对）。"""
    return sorted({line.strip() for line in (stdout or "").splitlines() if line.strip()})


def collect_processes(
    runner=subprocess.run, timeout_seconds: int = _TIMEOUT_SECONDS
) -> ProcessResult:
    """采集进程可执行路径清单；失败一律降级为 available=False。"""
    try:
        returncode, stdout, stderr = run_ps_script(
            runner, _PS_SCRIPT, timeout_seconds=timeout_seconds
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ProcessResult(available=False, reason=f"该证据源不可用：{exc.__class__.__name__}")
    if returncode != 0:
        detail = (stderr or "").strip()[:200]
        return ProcessResult(
            available=False, reason=f"该证据源不可用：PowerShell 退出码 {returncode}（{detail}）"
        )
    return ProcessResult(available=True, paths=parse_path_lines(stdout))
