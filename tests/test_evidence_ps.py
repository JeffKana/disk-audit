"""_ps.py PowerShell 底座解码容错单元测试（C5 新问题修复）。

背景（T2-02/D1 卡未尽事项 1）：进程/服务命令行含中文路径时，PowerShell 按系统
代码页（zh-CN=GBK）输出字节，text=True 严格解码在子进程读取线程抛
UnicodeDecodeError，该源证据静默变空（available=True + 0 条，未降级未披露）。
修复机制：PS 侧统一 UTF-8 输出前导句 + 侧解码链 utf-8→mbcs→utf-8(replace)，
读取线程不再承担解码，任何字节输入都不崩。
"""
from __future__ import annotations

import os
import types

import pytest

from disk_audit.evidence._ps import decode_ps_output, powershell_exe, run_ps_script


def test_decode_utf8_bytes():
    """前导句生效（常态）：PowerShell 输出 UTF-8 字节，按 utf-8 精确解码。"""
    assert decode_ps_output("中文路径".encode("utf-8")) == "中文路径"


def test_decode_str_passthrough():
    """str 原样返回——既有测试桩以 str 提供 stdout 的兼容口径。"""
    assert decode_ps_output("C:\\a.exe") == "C:\\a.exe"
    assert decode_ps_output("") == ""


def test_decode_invalid_bytes_replaced_no_raise():
    """不可解码字节不抛异常，替换符兜底——读取线程永不因解码崩溃。"""
    out = decode_ps_output(b"\xff\xfe\xfaC:\\a.exe")
    assert "\ufffd" in out
    assert "C:\\a.exe" in out


@pytest.mark.skipif(os.name != "nt", reason="mbcs（系统 ANSI 代码页）仅 Windows")
def test_decode_gbk_fallback():
    """前导句失效场景：PowerShell 退回系统代码页（zh-CN=GBK），解码链第二级兜底。"""
    assert decode_ps_output("中文路径".encode("mbcs")) == "中文路径"


def test_run_ps_script_prologue_and_bytes_mode():
    """脚本携带 UTF-8 输出前导句；不向子进程传 text/encoding（解码只在侧发生）。"""
    captured: dict = {}

    def runner(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

    code, stdout, stderr = run_ps_script(runner, "Write-Output hi")
    assert (code, stdout, stderr) == (0, "ok", "")
    script_arg = captured["argv"][captured["argv"].index("-Command") + 1]
    assert "OutputEncoding" in script_arg
    assert "Write-Output hi" in script_arg
    for banned in ("text", "encoding", "universal_newlines"):
        assert banned not in captured["kwargs"]
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["timeout"] > 0
    assert captured["argv"][0] == powershell_exe()
