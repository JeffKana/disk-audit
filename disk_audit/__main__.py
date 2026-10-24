"""命令行入口。引擎层必须可独立 CLI 调用、零 UI 依赖（M1 验收④）。

--selftest 为 CI 门禁；scan 子命令输出扫描 JSON 摘要（待办 C2，任务卡 T-02）。
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .hardprotect import check_protection
from .scanner import scan_path

# 内置自检样例：与 tests/test_hardprotect.py 同步扩充（CI 门禁只认本命令退出码）
_SELFTEST_CASES: list[tuple[str, bool]] = [
    (r"C:\Users\u\AppData\Roaming\Microsoft\Protect", True),
    (r"C:\Users\u\AppData\Roaming\Microsoft\Crypto\RSA", True),
    (r"C:\Users\u\AppData\Local\Application Data", True),
    (r"C:\Users\u\AppData\Roaming\Microsoft\Windows", True),
    (r"C:\Users\u\AppData\Roaming\Code", False),
    (r"C:\Users\u\AppData\Local\Programs\SomeApp-updater", False),
]


def run_selftest() -> int:
    failed = 0
    for path, expect_protected in _SELFTEST_CASES:
        got = check_protection(path)
        if (got is not None) != expect_protected:
            print(f"[FAIL] {path}: 期望命中={expect_protected}, 实际={got}")
            failed += 1
    print(f"selftest: {len(_SELFTEST_CASES) - failed}/{len(_SELFTEST_CASES)} passed")
    return 1 if failed else 0


def _cmd_scan(args: argparse.Namespace) -> int:
    """scan 子命令：输出 JSON 摘要（条目数、双口径总量、跳过统计）。"""
    try:
        result = scan_path(args.path, workers=args.workers)
    except ValueError as exc:
        print(f"扫描失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="disk-audit", description="磁盘体检 · 只诊断，不动手"
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--selftest", action="store_true", help="运行内置自检（CI 门禁）")
    sub = parser.add_subparsers(dest="command")
    scan_parser = sub.add_parser("scan", help="扫描目录并输出 JSON 摘要（待办 C2）")
    scan_parser.add_argument("path", help="待扫描目录路径")
    scan_parser.add_argument(
        "--workers", type=int, default=8, help="并行线程数（默认 8，W0 实测最优）"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if args.command == "scan":
        return _cmd_scan(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
