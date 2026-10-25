"""证据采集的 PowerShell 调用底座（绝对路径 + 超时保护，任务卡 T-05/T-06 共用）。

依据：方案第四节"UWP/商店包"行与 W0 变更清单 C5——必须绝对路径调用
%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe，加
-NoProfile -NonInteractive；W0 教训：PATH 被裁剪时裸 "powershell" 会静默失败
（docs/upstream/poc/W0_POC实测报告_2026-10-23.html"顺带一个诚实说明"）。
"""
from __future__ import annotations

import os
import subprocess

CREATE_NO_WINDOW = 0x08000000  # 隐藏子进程窗口（POC-2 同款）
DEFAULT_TIMEOUT_SECONDS = 120


def powershell_exe() -> str:
    """Windows PowerShell 绝对路径；SystemRoot 缺失时回退 C:\\Windows。"""
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def run_ps_script(
    runner=subprocess.run,
    script: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, str, str]:
    """以绝对路径 + -NoProfile -NonInteractive 执行只读查询脚本。

    返回 (退出码, stdout, stderr)；exe 缺失/超时等异常向上抛出，由各采集器
    统一转为"该证据源不可用"降级标记（不抛出中断）。
    """
    argv = [powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", script]
    completed = runner(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""
