"""T-04（待办 C3）注册表卸载项采集单元测试。

用假 winreg 模块（只实现 OpenKey/EnumKey/QueryValueEx/CloseKey 与常量）注入采集
函数：解析正确性 + 验收③"全程无任何注册表写操作"（假模块不存在写方法，调用
序列断言只出现只读 API）。
"""
from __future__ import annotations

from disk_audit.evidence.registry_uninstall import collect_uninstall


class _Node:
    """模拟注册表键：子键表 + 值表；支持 with 协议。"""

    def __init__(self):
        self.children: dict[str, "_Node"] = {}
        self.values: dict[str, object] = {}
        self.fail_open = False  # 模拟打开该键权限不足

    def __enter__(self) -> "_Node":
        return self

    def __exit__(self, *exc_info):
        return False


class FakeWinreg:
    """假 winreg：不存在任何写方法（Create/Set/Delete 等一概没有）。"""

    KEY_READ = 0x20019
    HKEY_LOCAL_MACHINE = "hive-hklm"
    HKEY_CURRENT_USER = "hive-hkcu"

    def __init__(self):
        self.roots: dict[str, _Node] = {
            self.HKEY_LOCAL_MACHINE: _Node(),
            self.HKEY_CURRENT_USER: _Node(),
        }
        self.calls: list[str] = []

    def build(self, hive: str, sub_path: str) -> _Node:
        node = self.roots[hive]
        for part in sub_path.split("\\"):
            node = node.children.setdefault(part, _Node())
        return node

    def _walk(self, base: _Node, sub_key: str) -> _Node:
        node = base
        for part in sub_key.split("\\"):
            if part not in node.children:
                raise FileNotFoundError(2, "系统找不到指定的注册表项或值", sub_key)
            node = node.children[part]
        return node

    def OpenKey(self, key, sub_key, reserved=0, access=0):
        self.calls.append("OpenKey")
        base = key if isinstance(key, _Node) else self.roots[key]
        node = self._walk(base, sub_key)
        if node.fail_open:
            raise PermissionError(5, "拒绝访问", sub_key)
        return node

    def EnumKey(self, key, index):
        self.calls.append("EnumKey")
        names = list(key.children)
        if index >= len(names):
            raise OSError(22, "没有更多的元素")
        return names[index]

    def QueryValueEx(self, key, value_name):
        self.calls.append("QueryValueEx")
        if value_name not in key.values:
            raise FileNotFoundError(2, "系统找不到指定的注册表项或值", value_name)
        return key.values[value_name], 1

    def CloseKey(self, key):
        self.calls.append("CloseKey")


UNINSTALL = r"Microsoft\Windows\CurrentVersion\Uninstall"


def _make_fake() -> FakeWinreg:
    fake = FakeWinreg()
    hklm = fake.build(FakeWinreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\{UNINSTALL}")
    hklm.children["app64"] = _make_entry({
        "DisplayName": "App 64",
        "Publisher": "Vendor A",
        "InstallLocation": "C:\\Program Files\\App64\\",
        "InstallDate": "20260101",
        "UninstallString": r'"C:\Program Files\App64\unins000.exe"',
    })
    hklm.children["partial"] = _make_entry({"DisplayName": "Partial App"})
    hklm.children["badopen"] = _make_entry({"DisplayName": "Locked"})
    hklm.children["badopen"].fail_open = True

    wow = fake.build(FakeWinreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Wow6432Node\{UNINSTALL}")
    wow.children["app32"] = _make_entry({
        "DisplayName": "App 32 (Wow6432Node)",
        "InstallDate": 20260101,  # REG_DWORD → 转字符串
    })

    hkcu = fake.build(FakeWinreg.HKEY_CURRENT_USER, rf"SOFTWARE\{UNINSTALL}")
    hkcu.children["userapp"] = _make_entry({"DisplayName": "User App"})
    # HKCU 的 Wow6432Node 缺失 → 该源静默跳过，不算异常
    return fake


def _make_entry(values: dict[str, object]) -> _Node:
    node = _Node()
    node.values = values
    return node


def test_parse_entries_correctly():
    fake = _make_fake()
    result = collect_uninstall(fake)
    names = [e.display_name for e in result.entries]
    assert names == ["App 64", "Partial App", "App 32 (Wow6432Node)", "User App"]
    assert result.skipped == 1  # badopen 打不开 → X-1 计数
    # 打开成功的根键：HKLM 64 位、HKLM Wow6432Node、HKCU（HKCU Wow6432Node 缺失不计）
    assert len(result.sources_scanned) == 3
    assert any("Wow6432Node" in s for s in result.sources_scanned)


def test_fields_mapped_and_uninstall_string_verbatim():
    fake = _make_fake()
    result = collect_uninstall(fake)
    app64 = result.entries[0]
    assert app64.publisher == "Vendor A"
    assert app64.install_location == "C:\\Program Files\\App64\\"
    assert app64.install_date == "20260101"
    assert app64.uninstall_string == r'"C:\Program Files\App64\unins000.exe"'  # 原文不变
    assert app64.reg_path == (
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\app64"
    )


def test_missing_values_default_empty():
    fake = _make_fake()
    result = collect_uninstall(fake)
    partial = result.entries[1]
    assert partial.display_name == "Partial App"
    assert partial.publisher == ""
    assert partial.install_location == ""
    assert partial.uninstall_string == ""


def test_dword_value_stringified():
    fake = _make_fake()
    result = collect_uninstall(fake)
    assert result.entries[2].install_date == "20260101"


def test_reg_path_full_and_distinguishable():
    fake = _make_fake()
    result = collect_uninstall(fake)
    paths = [e.reg_path for e in result.entries]
    assert any(p.startswith("HKLM\\SOFTWARE\\Microsoft") for p in paths)
    assert any(p.startswith("HKLM\\SOFTWARE\\Wow6432Node") for p in paths)
    assert any(p.startswith("HKCU\\SOFTWARE\\Microsoft") for p in paths)


def test_only_readonly_registry_api_used():
    """验收③：调用序列只出现只读 API；假模块本身不存在任何写方法。"""
    fake = _make_fake()
    collect_uninstall(fake)
    assert set(fake.calls) <= {"OpenKey", "EnumKey", "QueryValueEx", "CloseKey"}
    assert not any(
        name.lower().startswith(("create", "set", "delete", "save", "restore", "load"))
        for name in dir(FakeWinreg)
    )


def test_all_sources_missing_returns_empty():
    fake = FakeWinreg()  # 无任何键
    result = collect_uninstall(fake)
    assert result.entries == []
    assert result.skipped == 0
    assert result.sources_scanned == []
