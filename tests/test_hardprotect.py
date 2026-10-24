"""硬保护规则测试（S-1 / M1 验收③：pytest 覆盖 100%）。"""
from __future__ import annotations

import pytest

from disk_audit.hardprotect import PROTECTED_LABEL, Protection, check_protection

DPAPI_CASES = [
    r"C:\Users\u\AppData\Roaming\Microsoft\Protect",
    r"C:\Users\u\AppData\Roaming\Microsoft\Protect\CREDHIST",
    r"C:\Users\u\AppData\Roaming\Microsoft\Crypto",
    r"C:\Users\u\AppData\Roaming\Microsoft\Crypto\RSA\S-1-5-21",
    r"C:\Users\u\AppData\Local\Microsoft\Crypto",
]

JUNCTION_CASES = [
    r"C:\Users\u\AppData\Local\Application Data",
    r"C:\Users\u\AppData\Local\Application Data\Microsoft",
    r"C:\Users\u\AppData\Local\History",
    r"C:\Users\u\AppData\Local\Temporary Internet Files",
    r"C:\Users\u\AppData\Local\Low\History\some\deep\path",
    r"C:\Users\u\Local Settings",
]

SYSTEM_CASES = [
    r"C:\Users\u\AppData\Roaming\Microsoft",
    r"C:\Users\u\AppData\Roaming\Microsoft\Windows\Themes",
    r"C:\Users\u\AppData\Local\Microsoft\Edge",
    r"C:\ProgramData\Microsoft\Windows",
]

SAFE_CASES = [
    r"C:\Users\u\AppData\Roaming\Code",                       # VS Code：子串误判防护的著名反例
    r"C:\Users\u\AppData\Local\Programs\Obsidian",
    r"C:\Users\u\AppData\Local\Obsidian\app-1.0.0\updater",   # 普通更新目录不因含 updater 受保护
    r"C:\Users\u\AppData\Roaming\Tencent",
    r"C:\ProgramData\chocolatey",
    r"C:\Users\u\AppData\Roaming\protect-thing",              # 名为 protect* 但不在 Microsoft 之下
    r"Protect",                                               # 裸同名目录不命中 DPAPI 规则
]


@pytest.mark.parametrize("path", DPAPI_CASES)
def test_dpapi_protected(path: str) -> None:
    result = check_protection(path)
    assert isinstance(result, Protection)
    assert result.rule_id == "HARDPROTECT-DPAPI"


@pytest.mark.parametrize("path", JUNCTION_CASES)
def test_junction_protected(path: str) -> None:
    result = check_protection(path)
    assert isinstance(result, Protection)
    assert result.rule_id == "HARDPROTECT-JUNCTION"


@pytest.mark.parametrize("path", SYSTEM_CASES)
def test_microsoft_system_protected(path: str) -> None:
    result = check_protection(path)
    assert isinstance(result, Protection)
    assert result.rule_id == "HARDPROTECT-SYSTEM"


@pytest.mark.parametrize("path", SAFE_CASES)
def test_normal_paths_not_protected(path: str) -> None:
    assert check_protection(path) is None


def test_case_insensitive_and_forward_slashes() -> None:
    assert check_protection("c:/users/u/appdata/roaming/MICROSOFT/Protect") is not None
    assert check_protection(r"C:\Users\U\AppData\LOCAL\HISTORY") is not None
    assert check_protection("C:/Users/u/AppData/Roaming/vscode") is None


def test_label_and_reason_are_human_readable() -> None:
    result = check_protection(r"C:\Users\u\AppData\Roaming\Microsoft\Protect")
    assert result is not None
    assert result.label == PROTECTED_LABEL == "受保护·不可处理"
    assert "永久无法解密" in result.reason
