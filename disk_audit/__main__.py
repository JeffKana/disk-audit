"""命令行入口。引擎层必须可独立 CLI 调用、零 UI 依赖（M1 验收④）。

当前为 Sprint 0 骨架：--selftest 作为 CI 门禁；扫描子命令随 Sprint 1~2 接入。
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .hardprotect import check_protection

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="disk-audit", description="磁盘体检 · 只诊断，不动手"
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--selftest", action="store_true", help="运行内置自检（CI 门禁）")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
