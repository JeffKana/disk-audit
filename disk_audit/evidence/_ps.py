"""证据采集的 PowerShell 调用底座（绝对路径 + 超时保护，任务卡 T-05/T-06 共用）。

依据：方案第四节"UWP/商店包"行与 W0 变更清单 C5——必须绝对路径调用
%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe，加
-NoProfile -NonInteractive；W0 教训：PATH 被裁剪时裸 "powershell" 会静默失败
（docs/upstream/poc/W0_POC实测报告_2026-10-23.html"顺带一个诚实说明"）。

解码容错（C5 新问题修复，2026-10-31；去 locale 化见 06 退回单 #24）：进程/服务
命令行含中文路径时，PowerShell 按系统代码页（zh-CN=GBK）输出字节，text=True
严格解码在子进程读取线程抛 UnicodeDecodeError，该源证据静默变空（available=True
+ 0 条，未降级未披露）。修复三层：①脚本前导句统一 [Console]::OutputEncoding=UTF-8
（尽力而为，失败不阻断）；②bytes 模式捕获，侧按 utf-8→mbcs→utf-8(replace) 解码链
容错，读取线程不再承担解码；③空输出披露语义由各采集器自定（进程源按不可用披露）。
解码链编码表可注入（encodings 参数），测试注入不存在的编解码器直达目标分支，
断言不依赖系统 locale（en-US runner mbcs=cp1252 与开发机 GBK 行为分叉的教训）。
"""
from __future__ import annotations

import os
import subprocess

CREATE_NO_WINDOW = 0x08000000  # 隐藏子进程窗口（POC-2 同款）
DEFAULT_TIMEOUT_SECONDS = 120

# 侧解码链默认编码表：utf-8（前导句生效时）→ mbcs（系统 ANSI 代码页兜底，仅 Windows）
DEFAULT_DECODE_ENCODINGS = ("utf-8", "mbcs")

# PS 侧统一输出编码为 UTF-8；无控制台会话等异常下静默跳过（尽力而为）
_PS_UTF8_PROLOGUE = (
    "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }"
)


def powershell_exe() -> str:
    """Windows PowerShell 绝对路径；SystemRoot 缺失时回退 C:\\Windows。"""
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def decode_ps_output(
    data: bytes | str, encodings: tuple[str, ...] = DEFAULT_DECODE_ENCODINGS
) -> str:
    """子进程输出解码容错链：逐级尝试 encodings，全失败以 utf-8(replace) 兜底。

    str 原样返回（测试桩兼容口径）；编解码器缺失（LookupError，如非 Windows
    上的 mbcs）与 UnicodeDecodeError 一视同仁跳过；任何字节输入都不抛异常，
    杜绝读取线程崩溃。encodings 可注入供测试去 locale 化（06 退回单 #24）。
    """
    if isinstance(data, str):
        return data
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run_ps_script(
    runner=subprocess.run,
    script: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, str, str]:
    """以绝对路径 + -NoProfile -NonInteractive 执行只读查询脚本。

    返回 (退出码, stdout, stderr)；exe 缺失/超时等异常向上抛出，由各采集器
    统一转为"该证据源不可用"降级标记（不抛出中断）。
    """
    argv = [
        powershell_exe(),
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _PS_UTF8_PROLOGUE + "; " + script,
    ]
    completed = runner(
        argv,
        capture_output=True,
        timeout=timeout_seconds,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return (
        completed.returncode,
        decode_ps_output(completed.stdout or b""),
        decode_ps_output(completed.stderr or b""),
    )
