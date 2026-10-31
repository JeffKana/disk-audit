"""命令行入口。引擎层必须可独立 CLI 调用、零 UI 依赖（M1 验收④）。

--selftest 为 CI 门禁；scan 子命令输出扫描 JSON（待办 C2）；
judge 子命令消费 scan 结果执行归属判定并输出报告 JSON（待办 D1，任务卡 T2-02）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine.report import judge_scan_result
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
    """scan 子命令：输出 JSON 摘要（条目数、双口径总量、跳过统计、判定单元）。"""
    try:
        result = scan_path(args.path, workers=args.workers)
    except ValueError as exc:
        print(f"扫描失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2))
    return 0


def _cmd_judge(args: argparse.Namespace) -> int:
    """judge 子命令：读 scan 结果 JSON → 六层判定 → 输出 report-v1 草案 JSON。"""
    try:
        scan = json.loads(Path(args.scan_result).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"判定失败：无法读取扫描结果文件：{exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"判定失败：扫描结果文件不是合法 JSON：{exc}", file=sys.stderr)
        return 2
    try:
        report = judge_scan_result(scan)
    except ValueError as exc:
        print(f"判定失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
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
    judge_parser = sub.add_parser(
        "judge", help="对 scan 结果执行归属判定并输出报告 JSON（待办 D1）"
    )
    judge_parser.add_argument("scan_result", help="scan 子命令输出的 JSON 文件路径")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if args.command == "scan":
        return _cmd_scan(args)
    if args.command == "judge":
        return _cmd_judge(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
