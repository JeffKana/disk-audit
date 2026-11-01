"""_ps.py PowerShell 底座解码容错单元测试（C5 新问题修复 + 06 退回单 #24 去 locale 化）。

背景（T2-02/D1 卡未尽事项 1）：进程/服务命令行含中文路径时，PowerShell 按系统
代码页输出字节，text=True 严格解码在子进程读取线程抛 UnicodeDecodeError，该源
证据静默变空（available=True + 0 条，未降级未披露）。
修复机制：PS 侧统一 UTF-8 输出前导句 + 侧解码链 utf-8→mbcs→utf-8(replace)，
读取线程不再承担解码，任何字节输入都不崩。

退回修复（CI run 41212836258，1/2 次退回）：原测试假设 mbcs=GBK（开发机 zh-CN），
en-US runner 上 mbcs=cp1252 行为分叉（GBK 样本无法编码 / 无效字节被 cp1252
成功解码）。修复口径（退回单指定）：编码链改为可注入，测试注入不存在的编解码器
直达目标分支——断言一律不依赖系统 locale。
"""
from __future__ import annotations

import inspect
import os
import types

import pytest

from disk_audit.evidence._ps import decode_ps_output, powershell_exe, run_ps_script

# 测试注入用：必然不存在的编解码器名（触发 LookupError，与 locale 无关）
_BAD_CODEC = "no-such-codec-xyz"


def test_decode_utf8_bytes():
    """前导句生效（常态）：PowerShell 输出 UTF-8 字节，按 utf-8 精确解码。"""
    assert decode_ps_output("中文路径".encode("utf-8")) == "中文路径"


def test_decode_str_passthrough():
    """str 原样返回——既有测试桩以 str 提供 stdout 的兼容口径。"""
    assert decode_ps_output("C:\\a.exe") == "C:\\a.exe"
    assert decode_ps_output("") == ""


def test_decode_invalid_bytes_replaced_no_raise():
    """不可解码字节不抛异常，替换符兜底——读取线程永不因解码崩溃。

    注入 ("utf-8", 不存在编码)：utf-8 失败（\\xff 恒非法）→ 二级 LookupError
    → 直达 replace 分支，任何 locale 下行为一致（退回单修复口径）。
    """
    out = decode_ps_output(b"\xff\xfe\xfaC:\\a.exe", encodings=("utf-8", _BAD_CODEC))
    assert "\ufffd" in out
    assert "C:\\a.exe" in out


def test_decode_second_tier_fallback_injected():
    """链式降级：第一级编解码器缺失（LookupError）→ 第二级接管（退回单：编码链可注入）。

    以 (不存在编码, utf-8) 验证"逐级尝试"，不依赖 mbcs 在具体 locale 下的行为。
    """
    out = decode_ps_output("中文路径".encode("utf-8"), encodings=(_BAD_CODEC, "utf-8"))
    assert out == "中文路径"


def test_decode_all_tiers_failed_falls_to_replace():
    """全链失败仍不抛异常：replace 兜底永远可达。"""
    out = decode_ps_output(b"\xff\xfe\xfa", encodings=(_BAD_CODEC, _BAD_CODEC))
    assert out == "\ufffd\ufffd\ufffd"


@pytest.mark.skipif(os.name != "nt", reason="mbcs（系统 ANSI 代码页）仅 Windows")
def test_default_chain_includes_mbcs():
    """生产默认链第二级为 mbcs（系统代码页兜底）——结构性断言，不依赖
    具体 locale 的解码行为（退回单 #24：禁止断言依赖系统 locale）。"""
    default = inspect.signature(decode_ps_output).parameters["encodings"].default
    assert "mbcs" in default


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
