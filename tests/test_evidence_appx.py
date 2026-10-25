"""T-05（待办 C4）Appx 商店包采集单元测试。

覆盖：样例 JSON 解析（数组与单包对象两种形态）、降级不抛异常（exe 缺失/超时/
非零退出/坏 JSON）、子进程调用参数断言（绝对路径 + -NoProfile -NonInteractive）。
"""
from __future__ import annotations

import json
import os
import subprocess
import types

from disk_audit.evidence._ps import powershell_exe
from disk_audit.evidence.appx import collect_appx, parse_appx_json

_SAMPLE_LIST = json.dumps(
    [
        {"Name": "Microsoft.UI.Xaml.2.0", "PackageFullName": "Microsoft.UI.Xaml.2.0_8wekyb3d8bbwe",
         "InstallLocation": r"C:\Program Files\WindowsApps\Microsoft.UI.Xaml.2.0_..."},
        {"Name": "Microsoft.NET.Native.Runtime.2.1",
         "PackageFullName": "Microsoft.NET.Native.Runtime.2.1_8wekyb3d8bbwe",
         "InstallLocation": r"C:\Program Files\WindowsApps\Microsoft.NET.Native.Runtime.2.1_..."},
    ],
    ensure_ascii=False,
)
_SAMPLE_SINGLE = json.dumps(
    {"Name": "Solo.Package", "PackageFullName": "Solo.Package_8wekyb3d8bbwe",
     "InstallLocation": r"C:\Program Files\WindowsApps\Solo.Package_..."},
    ensure_ascii=False,
)


def _ok_runner(stdout: str):
    def runner(argv, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return runner


def _failing_runner(exc: Exception):
    def runner(argv, **kwargs):
        raise exc

    return runner


def test_parse_list_json():
    packages = parse_appx_json(_SAMPLE_LIST)
    assert [p.name for p in packages] == [
        "Microsoft.UI.Xaml.2.0", "Microsoft.NET.Native.Runtime.2.1",
    ]
    assert packages[0].package_full_name == "Microsoft.UI.Xaml.2.0_8wekyb3d8bbwe"
    assert packages[0].install_location.startswith(r"C:\Program Files\WindowsApps")


def test_parse_single_object_json():
    packages = parse_appx_json(_SAMPLE_SINGLE)
    assert len(packages) == 1
    assert packages[0].name == "Solo.Package"


def test_parse_empty_output():
    assert parse_appx_json("") == []
    assert parse_appx_json("   \n") == []


def test_collect_success():
    result = collect_appx(runner=_ok_runner(_SAMPLE_LIST))
    assert result.available is True
    assert result.reason == ""
    assert len(result.packages) == 2


def test_collect_degraded_missing_exe():
    """验收②：命令不可用（W0 场景：PATH 被裁剪导致 FileNotFoundError）降级不抛异常。"""
    result = collect_appx(runner=_failing_runner(FileNotFoundError(2, "找不到文件", "powershell")))
    assert result.available is False
    assert result.packages == []
    assert "不可用" in result.reason


def test_collect_degraded_timeout():
    result = collect_appx(runner=_failing_runner(subprocess.TimeoutExpired(cmd="ps", timeout=120)))
    assert result.available is False
    assert "不可用" in result.reason


def test_collect_degraded_nonzero_exit():
    runner = lambda argv, **kw: types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
    result = collect_appx(runner=runner)
    assert result.available is False
    assert "退出码 1" in result.reason
    assert "boom" in result.reason


def test_collect_degraded_bad_json():
    result = collect_appx(runner=_ok_runner("not json"))
    assert result.available is False
    assert "解析失败" in result.reason


def test_argv_absolute_path_and_flags():
    """验收④：子进程调用参数可断言——绝对路径 + -NoProfile -NonInteractive。"""
    captured: dict = {}

    def runner(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    collect_appx(runner=runner)
    argv = captured["argv"]
    assert argv[0] == powershell_exe()
    assert os.path.isabs(argv[0])
    assert argv[0].lower().endswith("powershell.exe")
    assert "-NoProfile" in argv and "-NonInteractive" in argv
    assert "-Command" in argv
    assert "Get-AppxPackage" in argv[argv.index("-Command") + 1]
    assert captured["kwargs"]["timeout"] > 0
