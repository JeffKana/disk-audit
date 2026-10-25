"""注册表卸载项只读采集（待办 C3，任务卡 T-04）。

依据：方案第四节"注册表"行（winreg，KEY_READ——标准库只读访问，无写风险）。
键位覆盖（待办 C3：HKLM/HKCU × 64/32 位视图，含 Wow6432Node）：
  HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall             （64 位视图）
  HKLM\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall （32 位视图）
  HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall
  HKCU\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall
采集参考：docs/upstream/poc/poc2_app.py（原型实测 284 键 / 206 有 DisplayName）；
字段按任务卡要求：DisplayName/Publisher/InstallLocation/InstallDate/
UninstallString（原文）/注册表完整路径。
安全底线：只读（KEY_READ），全流程无任何注册表写操作；UninstallString 原文只
采集、永不执行（U-4）。单键失败按 X-1 跳过+计数+继续。
"""
from __future__ import annotations

import winreg
from dataclasses import dataclass, field

_UNINSTALL_SUBKEY = r"Microsoft\Windows\CurrentVersion\Uninstall"
# (分支名, SOFTWARE 子路径)；Wow6432Node 即 32 位视图的物理位置，直取不依赖反射
_SOURCES: list[tuple[str, str]] = [
    ("HKLM", r"SOFTWARE"),
    ("HKLM", r"SOFTWARE\Wow6432Node"),
    ("HKCU", r"SOFTWARE"),
    ("HKCU", r"SOFTWARE\Wow6432Node"),
]
_VALUE_FIELDS = (
    "DisplayName",
    "Publisher",
    "InstallLocation",
    "InstallDate",
    "UninstallString",
)


@dataclass(frozen=True)
class UninstallEntry:
    display_name: str
    publisher: str
    install_location: str
    install_date: str
    uninstall_string: str  # UninstallString 原文；只采集不执行（U-4）
    reg_path: str  # 完整注册表路径，如 HKLM\SOFTWARE\...\Uninstall\<键名>


@dataclass
class UninstallResult:
    available: bool = True
    entries: list[UninstallEntry] = field(default_factory=list)
    skipped: int = 0  # X-1：打不开/读不了的子键计数
    sources_scanned: list[str] = field(default_factory=list)  # 实际打开成功的根键


def collect_uninstall(winreg_module=winreg) -> UninstallResult:
    """只读采集四个 Uninstall 键位的卸载条目。

    winreg_module 可注入以便测试（假模块只提供 OpenKey/EnumKey/QueryValueEx/
    CloseKey 与常量，天然断言不出现任何写操作）。
    """
    result = UninstallResult()
    hive_constants = {
        "HKLM": winreg_module.HKEY_LOCAL_MACHINE,
        "HKCU": winreg_module.HKEY_CURRENT_USER,
    }
    for hive_name, software_sub in _SOURCES:
        sub_path = f"{software_sub}\\{_UNINSTALL_SUBKEY}"
        try:
            root_key = winreg_module.OpenKey(
                hive_constants[hive_name], sub_path, 0, winreg_module.KEY_READ
            )
        except OSError:
            continue  # 键位不存在（如 HKCU 的 Wow6432Node）属正常，不算跳过
        result.sources_scanned.append(f"{hive_name}\\{sub_path}")
        with root_key:
            index = 0
            while True:
                try:
                    sub_name = winreg_module.EnumKey(root_key, index)
                except OSError:
                    break
                index += 1
                entry = _read_entry(
                    winreg_module, root_key, sub_name, f"{hive_name}\\{sub_path}"
                )
                if entry is None:
                    result.skipped += 1
                    continue
                result.entries.append(entry)
    return result


def _read_entry(
    winreg_module, root_key, sub_name: str, parent_path: str
) -> UninstallEntry | None:
    """读取单个卸载键；打不开按 X-1 返回 None 交由调用方计数。"""
    try:
        child = winreg_module.OpenKey(root_key, sub_name, 0, winreg_module.KEY_READ)
    except OSError:
        return None
    values: dict[str, str] = {}
    with child:
        for field_name in _VALUE_FIELDS:
            try:
                value, _value_type = winreg_module.QueryValueEx(child, field_name)
            except OSError:
                value = ""
            values[field_name] = value if isinstance(value, str) else str(value)
    return UninstallEntry(
        display_name=values["DisplayName"],
        publisher=values["Publisher"],
        install_location=values["InstallLocation"],
        install_date=values["InstallDate"],
        uninstall_string=values["UninstallString"],
        reg_path=f"{parent_path}\\{sub_name}",
    )
