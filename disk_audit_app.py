"""冻结程序统一入口（T7-01-A / DR-019）。

依据：DR-019 冻结程序统一入口、开发规范 §1（引擎与 UI 严格分离——本模块为包外
独立入口，disk_audit 包内任何模块不得 import tkinter）。本模块是未来 PyInstaller
入口，不修改旧 launcher 或引擎 CLI，不新增协议/文案资源，复用现有中文文案。

路由（首 token 决定，副本传参，绝不改调用者列表/全局 argv）：
- 空参数 → 延迟导入 launcher.main 并传空列表副本（保持现有 GUI 启动）；
- 首 token 精确 --elevated-rescan 或以 --elevated-rescan= 开头 → 延迟导入
  launcher.main 原样传副本（= 值由旧 store_true 解析器拒绝，路由器不自创 bool 语义）；
- 其它所有非空 → 延迟导入 disk_audit.__main__.main 传副本（复用 --selftest/--version/
  help 与 scan/judge/render/export-csv；未知/混合/畸形由现有解析器拒绝，不回退 GUI、
  不自动提权/扫描/网络/更新）。

后端返回码与 SystemExit/普通异常/BaseException 全透传，不吞异常改成功；本模块不
额外读写文件/网络/查注册表/启动进程。引擎分支不导入 launcher/tkinter（延迟导入 +
子进程导入禁令实证，见 tests/test_app_entry.py）。支持 python disk_audit_app.py 与
python -m disk_audit_app 两种源代码调用形态；__main__ 用 sys.exit(main())。
"""
from __future__ import annotations

import sys

_ELEVATED_FLAG = "--elevated-rescan"


def main(argv: list[str] | None = None) -> int:
    """统一入口路由：按首 token 分派 GUI/admin/CLI，副本传参、返回与异常全透传。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] == _ELEVATED_FLAG or args[0].startswith(_ELEVATED_FLAG + "="):
        from launcher import main as launcher_main

        return launcher_main(args)
    from disk_audit.__main__ import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())