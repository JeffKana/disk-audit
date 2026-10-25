"""自启动证据采集（待办 C5，任务卡 T-06）：Run 注册表键 + 启动文件夹列举。

覆盖（与原型 runkeys.json 同口径，docs/upstream/prototype/runkeys.json）：
  HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run
  HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run
  HKLM\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Run（32 位视图）
  用户启动文件夹 %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup
  公共启动文件夹 %ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup
只读（winreg KEY_READ + listdir）；单键/单文件夹失败按 X-1 跳过+计数+继续。
"""
from __future__ import annotations

import os
import winreg
from dataclasses import dataclass, field

_RUN_SUBKEY = r"Microsoft\Windows\CurrentVersion\Run"
_SOURCES: list[tuple[str, str]] = [
    ("HKCU", r"SOFTWARE"),
    ("HKLM", r"SOFTWARE"),
    ("HKLM", r"SOFTWARE\Wow6432Node"),
]


@dataclass(frozen=True)
class AutostartEntry:
    source: str  # 注册表完整路径或启动文件夹路径
    name: str  # 注册表值名 / 文件名
    command: str  # 命令原文（字符串化）/ 文件完整路径
    kind: str  # "registry" | "startup_folder"


@dataclass
class AutostartResult:
    available: bool = True
    entries: list[AutostartEntry] = field(default_factory=list)
    skipped: int = 0  # X-1：打不开的键/文件夹计数
    reason: str = ""


def default_startup_folders() -> list[str]:
    """用户与公共启动文件夹（环境变量缺失时跳过该项）。"""
    folders: list[str] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        folders.append(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
    program_data = os.environ.get("ProgramData")
    if program_data:
        folders.append(os.path.join(program_data, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
    return folders


def collect_autostart(
    winreg_module=winreg, folders: list[str] | None = None
) -> AutostartResult:
    """采集 Run 键值与启动文件夹条目；全程只读，单源失败跳过计数。"""
    result = AutostartResult()
    hive_constants = {
        "HKLM": winreg_module.HKEY_LOCAL_MACHINE,
        "HKCU": winreg_module.HKEY_CURRENT_USER,
    }
    for hive_name, software_sub in _SOURCES:
        sub_path = f"{software_sub}\\{_RUN_SUBKEY}"
        try:
            root_key = winreg_module.OpenKey(
                hive_constants[hive_name], sub_path, 0, winreg_module.KEY_READ
            )
        except OSError:
            continue
        with root_key:
            index = 0
            while True:
                try:
                    name, value, _value_type = winreg_module.EnumValue(root_key, index)
                except OSError:
                    break
                index += 1
                result.entries.append(
                    AutostartEntry(
                        source=f"{hive_name}\\{sub_path}",
                        name=str(name),
                        command=value if isinstance(value, str) else str(value),
                        kind="registry",
                    )
                )
    for folder in (folders if folders is not None else default_startup_folders()):
        try:
            names = os.listdir(folder)
        except OSError:
            result.skipped += 1
            continue
        for name in sorted(names):
            result.entries.append(
                AutostartEntry(
                    source=folder,
                    name=name,
                    command=os.path.join(folder, name),
                    kind="startup_folder",
                )
            )
    return result
