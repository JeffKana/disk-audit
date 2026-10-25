"""统一证据聚合接口（待办 C5，任务卡 T-06）：四源证据汇成 evidence 集合供引擎消费。

聚合永不抛异常：单源内部失败已在各自采集器降级（available=False + reason），
聚合层再兜底一层——任何未预期异常记入 errors 披露并继续其余源（X-1）。

JSON 结构示例（验收③，结构与 to_json_dict() 输出一一对应）：

    {
      "schema_version": "evidence.v1",
      "collected_at": "2026-10-24T12:00:00+08:00",
      "uninstall": {
        "available": true, "count": 206, "skipped": 3,
        "sources_scanned": ["HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"],
        "entries": [
          {"display_name": "NVM for Windows 1.2.2",
           "publisher": "Author Software Inc.",
           "install_location": "D:\\develop\\environment\\nvm\\",
           "install_date": "",
           "uninstall_string": "\\"D:\\\\develop\\\\environment\\\\nvm\\\\unins000.exe\\"",
           "reg_path": "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\nvm_is1"}
        ]
      },
      "appx": {
        "available": true, "count": 164, "reason": "",
        "packages": [
          {"name": "Microsoft.UI.Xaml.2.0",
           "package_full_name": "Microsoft.UI.Xaml.2.0_8wekyb3d8bbwe",
           "install_location": "C:\\Program Files\\WindowsApps\\..."}
        ]
      },
      "processes": {"available": true, "count": 54, "reason": "",
                    "paths": ["C:\\WINDOWS\\system32\\ApplicationFrameHost.exe"]},
      "services": {"available": true, "count": 303, "reason": "",
                   "paths": ["C:\\WINDOWS\\system32\\svchost.exe -k LocalServiceAndNoImpersonation -p"]},
      "autostart": {
        "available": true, "skipped": 0, "reason": "",
        "entries": [
          {"source": "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
           "name": "Fences",
           "command": "\\"c:\\\\program files (x86)\\\\stardock\\\\fences\\\\Fences.exe\\" /startup",
           "kind": "registry"}
        ]
      },
      "errors": []
    }
"""
from __future__ import annotations

import subprocess
import winreg
from dataclasses import dataclass, field
from datetime import datetime

from .appx import AppxResult, collect_appx
from .autostart import AutostartResult, collect_autostart
from .processes import ProcessResult, collect_processes
from .registry_uninstall import UninstallResult, collect_uninstall
from .services import ServiceResult, collect_services

SCHEMA_VERSION = "evidence.v1"


@dataclass
class EvidenceBundle:
    uninstall: UninstallResult = field(default_factory=UninstallResult)
    appx: AppxResult = field(default_factory=lambda: AppxResult(available=False, reason="未采集"))
    processes: ProcessResult = field(
        default_factory=lambda: ProcessResult(available=False, reason="未采集")
    )
    services: ServiceResult = field(
        default_factory=lambda: ServiceResult(available=False, reason="未采集")
    )
    autostart: AutostartResult = field(
        default_factory=lambda: AutostartResult(available=False, reason="未采集")
    )
    errors: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "uninstall": {
                "available": self.uninstall.available,
                "count": len(self.uninstall.entries),
                "skipped": self.uninstall.skipped,
                "sources_scanned": list(self.uninstall.sources_scanned),
                "entries": [
                    {
                        "display_name": e.display_name,
                        "publisher": e.publisher,
                        "install_location": e.install_location,
                        "install_date": e.install_date,
                        "uninstall_string": e.uninstall_string,
                        "reg_path": e.reg_path,
                    }
                    for e in self.uninstall.entries
                ],
            },
            "appx": {
                "available": self.appx.available,
                "count": len(self.appx.packages),
                "reason": self.appx.reason,
                "packages": [
                    {
                        "name": p.name,
                        "package_full_name": p.package_full_name,
                        "install_location": p.install_location,
                    }
                    for p in self.appx.packages
                ],
            },
            "processes": {
                "available": self.processes.available,
                "count": len(self.processes.paths),
                "reason": self.processes.reason,
                "paths": list(self.processes.paths),
            },
            "services": {
                "available": self.services.available,
                "count": len(self.services.paths),
                "reason": self.services.reason,
                "paths": list(self.services.paths),
            },
            "autostart": {
                "available": self.autostart.available,
                "skipped": self.autostart.skipped,
                "reason": self.autostart.reason,
                "entries": [
                    {
                        "source": e.source,
                        "name": e.name,
                        "command": e.command,
                        "kind": e.kind,
                    }
                    for e in self.autostart.entries
                ],
            },
            "errors": list(self.errors),
        }


def collect_all(winreg_module=winreg, runner=subprocess.run) -> EvidenceBundle:
    """聚合四源证据；单源未预期异常记入 errors 披露，不中断其余源（X-1）。"""
    bundle = EvidenceBundle()
    for label, collector, target in (
        ("注册表卸载项", lambda: collect_uninstall(winreg_module), "uninstall"),
        ("Appx 商店包", lambda: collect_appx(runner), "appx"),
        ("进程", lambda: collect_processes(runner), "processes"),
        ("服务", lambda: collect_services(runner), "services"),
        ("自启动", lambda: collect_autostart(winreg_module), "autostart"),
    ):
        try:
            setattr(bundle, target, collector())
        except Exception as exc:  # 聚合层兜底：单源失败不中断（X-1/降级披露）
            bundle.errors.append(f"证据源 {label} 采集失败：{exc.__class__.__name__}: {exc}")
    return bundle
