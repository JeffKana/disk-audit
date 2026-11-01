"""命令行入口。引擎层必须可独立 CLI 调用、零 UI 依赖（M1 验收④）。

--selftest 为 CI 门禁；scan 子命令输出扫描 JSON（待办 C2）；
judge 子命令消费 scan 结果执行归属判定并输出报告 JSON（待办 D1，任务卡 T2-02）；
render 子命令消费报告 JSON 输出离线单文件 HTML（待办 F2，任务卡 T3-02）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine.render import render_report
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


def _force_utf8_stdio() -> None:
    """强制 stdout/stderr 为 UTF-8（T-01 教训：runner/重定向默认编码非 UTF-8，
    中文输出假红/乱码；hasattr 守卫兼容 pytest 等替换过的流对象）。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _cmd_render(args: argparse.Namespace) -> int:
    """render 子命令：报告 JSON → 离线单文件 HTML 文本，输出到 stdout（待办 F2）。

    不落盘（U-2：本程序仅在 %LOCALAPPDATA%\\DiskAudit\\ 内写文件；报告落盘与
    默认浏览器打开由结果入口负责，T3-06）；重定向即得报告文件。
    """
    _force_utf8_stdio()
    try:
        raw = Path(args.report_json).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"渲染失败：无法读取报告文件：{exc}", file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        print(f"渲染失败：报告文件不是 UTF-8 编码：{exc}", file=sys.stderr)
        return 2
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"渲染失败：报告文件不是合法 JSON：{exc}", file=sys.stderr)
        return 2
    try:
        html_text = render_report(report)
    except ValueError as exc:
        print(f"渲染失败：{exc}", file=sys.stderr)
        return 2
    print(html_text)
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
    render_parser = sub.add_parser(
        "render", help="将报告 JSON 渲染为离线单文件 HTML 并输出到 stdout（待办 F2）"
    )
    render_parser.add_argument("report_json", help="judge 子命令输出的报告 JSON 文件路径")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if args.command == "scan":
        return _cmd_scan(args)
    if args.command == "judge":
        return _cmd_judge(args)
    if args.command == "render":
        return _cmd_render(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
