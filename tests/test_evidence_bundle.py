"""T-06（待办 C5）进程/服务/自启动采集与 evidence 聚合单元测试。

覆盖：路径行解析（去空行/去重/排序）、自启动 Run 键与启动文件夹采集、
单文件夹失败跳过计数、聚合接口结构（验收③的 JSON 结构示例见 evidence.py
docstring）、单源故障不中断聚合（X-1）。
"""
from __future__ import annotations

import types
from pathlib import Path

import pytest

from disk_audit.evidence import evidence as evidence_module
from disk_audit.evidence.autostart import collect_autostart
from disk_audit.evidence.evidence import EvidenceBundle, collect_all
from disk_audit.evidence.processes import collect_processes, parse_path_lines
from disk_audit.evidence.registry_uninstall import UninstallEntry, UninstallResult
from disk_audit.evidence.services import collect_services


def _ok_runner(stdout: str):
    def runner(argv, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return runner


class _RunKeyNode:
    """模拟 Run 键：只有值表，支持 EnumValue 与 with 协议。"""

    def __init__(self, values: dict[str, object] | None = None):
        self.values: list[tuple[str, object, int]] = [
            (name, value, 1) for name, value in (values or {}).items()
        ]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeRunWinreg:
    KEY_READ = 0x20019
    HKEY_LOCAL_MACHINE = "hive-hklm"
    HKEY_CURRENT_USER = "hive-hkcu"

    def __init__(self):
        self.runs: dict[str, dict[str, object]] = {}

    def set_run(self, hive: str, sub_key: str, values: dict[str, object]) -> None:
        self.runs[(hive, sub_key)] = values

    def OpenKey(self, key, sub_key, reserved=0, access=0):
        values = self.runs.get((key, sub_key))
        if values is None:
            raise FileNotFoundError(2, "系统找不到指定的注册表项或值", sub_key)
        return _RunKeyNode(values)

    def EnumValue(self, key, index):
        if index >= len(key.values):
            raise OSError(22, "没有更多的元素")
        return key.values[index]


def test_parse_path_lines_dedup_and_sort():
    stdout = "C:\\B.exe\r\nC:\\a.exe\r\n\r\nC:\\B.exe\n  C:\\c.exe  \n"
    assert parse_path_lines(stdout) == ["C:\\B.exe", "C:\\a.exe", "C:\\c.exe"]


def test_collect_processes_success():
    result = collect_processes(runner=_ok_runner("C:\\a.exe\nC:\\b.exe\n"))
    assert result.available is True
    assert result.paths == ["C:\\a.exe", "C:\\b.exe"]


def test_collect_services_success():
    result = collect_services(runner=_ok_runner("C:\\svchost.exe -k net\n"))
    assert result.available is True
    assert result.paths == ["C:\\svchost.exe -k net"]


def test_collect_processes_degraded():
    def runner(argv, **kwargs):
        raise FileNotFoundError(2, "找不到文件", argv[0])

    result = collect_processes(runner=runner)
    assert result.available is False
    assert result.paths == []
    assert "不可用" in result.reason


def test_collect_processes_empty_stdout_disclosed():
    """C5 新问题披露口径：rc=0 但空输出按不可用披露，不再静默 available=True + 0 条。"""
    result = collect_processes(runner=_ok_runner(""))
    assert result.available is False
    assert result.paths == []
    assert "空输出" in result.reason


def test_collect_processes_gbk_bytes_no_crash():
    """C5 新问题回归：中文路径 GBK 字节（前导句失效场景）不再崩读取线程、不静默为空。"""
    stdout = "C:\\工具\\微信.exe\nC:\\a.exe\n".encode("gbk")

    def runner(argv, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")

    result = collect_processes(runner=runner)
    assert result.available is True
    assert len(result.paths) == 2  # 静默为空即回归


def test_collect_autostart_registry_and_folders(tmp_path):
    fake = FakeRunWinreg()
    run_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    fake.set_run(FakeRunWinreg.HKEY_CURRENT_USER, run_key, {"Fences": r'"c:\fences.exe" /startup'})
    fake.set_run(
        FakeRunWinreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
        {"Legacy": r"C:\legacy\app.exe"},
    )
    user_startup = tmp_path / "user_startup"
    user_startup.mkdir()
    (user_startup / "OneDrive.lnk").write_bytes(b"\x00")
    missing_folder = tmp_path / "missing"  # 不存在 → 跳过计数
    result = collect_autostart(
        winreg_module=fake, folders=[str(user_startup), str(missing_folder)]
    )
    registry_entries = [e for e in result.entries if e.kind == "registry"]
    assert [(e.source.split("\\")[0], e.name) for e in registry_entries] == [
        ("HKCU", "Fences"),
        ("HKLM", "Legacy"),
    ]
    folder_entries = [e for e in result.entries if e.kind == "startup_folder"]
    assert len(folder_entries) == 1
    assert folder_entries[0].name == "OneDrive.lnk"
    assert folder_entries[0].command == str(user_startup / "OneDrive.lnk")
    assert result.skipped == 1
    assert result.available is True


def test_collect_autostart_all_missing():
    fake = FakeRunWinreg()
    result = collect_autostart(winreg_module=fake, folders=[])
    assert result.entries == []
    assert result.available is True


# ---------- 聚合接口 ----------


def _mini_uninstall() -> UninstallResult:
    return UninstallResult(
        entries=[
            UninstallEntry(
                display_name="Demo App",
                publisher="Vendor",
                install_location=r"C:\Program Files\Demo",
                install_date="20260101",
                uninstall_string=r'"C:\Program Files\Demo\unins000.exe"',
                reg_path=r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\demo",
            )
        ],
        skipped=0,
        sources_scanned=["HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"],
    )


def test_collect_all_aggregates(monkeypatch, tmp_path):
    from disk_audit.evidence.appx import AppxPackage, AppxResult
    from disk_audit.evidence.autostart import AutostartEntry, AutostartResult
    from disk_audit.evidence.processes import ProcessResult
    from disk_audit.evidence.services import ServiceResult

    monkeypatch.setattr(evidence_module, "collect_uninstall", lambda *a, **kw: _mini_uninstall())
    monkeypatch.setattr(
        evidence_module,
        "collect_appx",
        lambda *a, **kw: AppxResult(
            available=True, packages=[AppxPackage(name="P", package_full_name="P_full", install_location="")]
        ),
    )
    monkeypatch.setattr(
        evidence_module, "collect_processes",
        lambda *a, **kw: ProcessResult(available=True, paths=["C:\\a.exe"]),
    )
    monkeypatch.setattr(
        evidence_module, "collect_services",
        lambda *a, **kw: ServiceResult(available=False, reason="该证据源不可用"),
    )
    monkeypatch.setattr(
        evidence_module,
        "collect_autostart",
        lambda *a, **kw: AutostartResult(
            entries=[AutostartEntry(source="HKCU\\...\\Run", name="n", command="c", kind="registry")]
        ),
    )
    bundle = collect_all()
    payload = bundle.to_json_dict()
    assert payload["schema_version"] == "evidence.v1"
    assert payload["uninstall"]["count"] == 1
    assert payload["uninstall"]["entries"][0]["display_name"] == "Demo App"
    assert payload["appx"]["count"] == 1
    assert payload["processes"]["paths"] == ["C:\\a.exe"]
    assert payload["services"]["available"] is False
    assert payload["services"]["reason"] == "该证据源不可用"
    assert payload["autostart"]["entries"][0]["kind"] == "registry"
    assert payload["errors"] == []
    assert payload["collected_at"]  # ISO 时间串


def test_collect_all_isolates_single_source_failure(monkeypatch):
    """单源抛未预期异常 → errors 披露，其余源继续（X-1/降级披露）。"""
    from disk_audit.evidence.processes import ProcessResult

    def boom(*a, **kw):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(evidence_module, "collect_uninstall", boom)
    monkeypatch.setattr(
        evidence_module, "collect_processes",
        lambda *a, **kw: ProcessResult(available=True, paths=["C:\\a.exe"]),
    )
    bundle = collect_all()
    assert len(bundle.errors) == 1
    assert "注册表卸载项" in bundle.errors[0]
    assert bundle.processes.available is True
    assert bundle.uninstall.available is True  # 默认值兜底，未采到即空
    assert bundle.uninstall.entries == []


def test_to_json_dict_defaults_no_crash():
    """全默认（未采集）的 bundle 也能输出完整结构。"""
    payload = EvidenceBundle().to_json_dict()
    assert set(payload) >= {
        "schema_version", "collected_at", "uninstall", "appx",
        "processes", "services", "autostart", "errors",
    }
    assert payload["appx"]["reason"] == "未采集"
    assert payload["errors"] == []
