"""Appx 商店包只读采集（待办 C4，任务卡 T-05；含 W0-C5 绝对路径约束）。

依据：方案第四节"UWP/商店包"行——
%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe
-NoProfile -NonInteractive -Command Get-AppxPackage；
"失败降级为'该证据源不可用'并在报告披露"。本模块任何失败路径都不抛异常：
available=False + 中文 reason，供聚合层进报告披露字段。只读。
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from ._ps import DEFAULT_TIMEOUT_SECONDS, run_ps_script

_PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "Get-AppxPackage | Select-Object Name,PackageFullName,InstallLocation"
    " | ConvertTo-Json -Compress -Depth 2"
)


@dataclass(frozen=True)
class AppxPackage:
    name: str
    package_full_name: str
    install_location: str


@dataclass
class AppxResult:
    available: bool  # False = 证据源不可用（reason 为中文披露文案）
    packages: list[AppxPackage] = field(default_factory=list)
    reason: str = ""


def parse_appx_json(stdout: str) -> list[AppxPackage]:
    """解析 Get-AppxPackage 的 JSON 输出；单包时 ConvertTo-Json 输出对象而非数组。"""
    text = (stdout or "").strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict):
        data = [data]
    packages: list[AppxPackage] = []
    for item in data:
        packages.append(
            AppxPackage(
                name=str(item.get("Name") or ""),
                package_full_name=str(item.get("PackageFullName") or ""),
                install_location=str(item.get("InstallLocation") or ""),
            )
        )
    return packages


def collect_appx(
    runner=subprocess.run,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> AppxResult:
    """采集商店包清单；失败一律降级为 available=False，不抛异常。"""
    try:
        returncode, stdout, stderr = run_ps_script(
            runner, _PS_SCRIPT, timeout_seconds=timeout_seconds
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return AppxResult(
            available=False, reason=f"该证据源不可用：{exc.__class__.__name__}"
        )
    if returncode != 0:
        detail = (stderr or "").strip()[:200]
        return AppxResult(
            available=False,
            reason=f"该证据源不可用：PowerShell 退出码 {returncode}（{detail}）",
        )
    try:
        packages = parse_appx_json(stdout)
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        return AppxResult(
            available=False,
            reason=f"该证据源不可用：输出解析失败（{exc.__class__.__name__}）",
        )
    return AppxResult(available=True, packages=packages)
