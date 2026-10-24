"""import 白名单门禁：扫描 disk_audit/ 的运行时 import，仅允许标准库与包内模块。

依据：《开发规范》§2（零依赖白名单机制）、产品待办 A4、《CI-CD 规范》§3 阶段 B 门禁④。
退出码：0=通过；1=存在违规 import 或扫描失败。
扫描对象仅为 disk_audit/ 包（任务卡 T-01 约束）；tools/ 与 tests/ 属开发侧，不在门禁范围。
标准库判定以当前解释器 sys.stdlib_module_names 为准（含 winreg 等平台专属模块）。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PACKAGE_NAME = "disk_audit"


def default_scan_root() -> Path:
    """仓库内 disk_audit/ 目录（脚本位于 tools/ 下）。"""
    return Path(__file__).resolve().parents[1] / PACKAGE_NAME


def _root_module(module: str | None) -> str | None:
    """取 import 的顶层模块名；相对导入的 module 为 None，交由调用方按包内处理。"""
    if module is None:
        return None
    return module.split(".", 1)[0]


def find_violations(scan_root: Path, package_name: str = PACKAGE_NAME) -> list[str]:
    """返回违规 import 清单（"相对路径:行号: import 模块"）；文件解析失败按违规计。"""
    violations: list[str] = []
    for py in sorted(scan_root.rglob("*.py")):
        rel = py.relative_to(scan_root).as_posix()
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
            violations.append(f"{rel}: 解析失败 {exc!r}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = _root_module(alias.name)
                    if root not in sys.stdlib_module_names and root != package_name:
                        violations.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue  # 相对导入必然是包内模块
                root = _root_module(node.module)
                if root not in sys.stdlib_module_names and root != package_name:
                    names = ", ".join(a.name for a in node.names)
                    violations.append(
                        f"{rel}:{node.lineno}: from {node.module} import {names}"
                    )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="import 白名单门禁（运行时零第三方依赖）")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="扫描根目录（默认：仓库内 disk_audit/）",
    )
    args = parser.parse_args(argv)

    scan_root = args.root if args.root is not None else default_scan_root()
    if not scan_root.is_dir():
        print(f"[import 白名单] 扫描目录不存在：{scan_root}")
        return 1

    violations = find_violations(scan_root)
    if violations:
        print(
            f"[import 白名单] 发现 {len(violations)} 处违规"
            f"（仅允许标准库与 {PACKAGE_NAME}.*）："
        )
        for item in violations:
            print(f"  - {item}")
        return 1
    print(f"[import 白名单] 通过：{scan_root} 下所有 import 均为标准库或包内模块")
    return 0


if __name__ == "__main__":
    sys.exit(main())
