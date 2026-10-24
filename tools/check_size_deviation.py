"""容量偏差对比脚本（待办 L2，任务卡 T-03；M1 验收①"与资源管理器偏差 <1%"的验收工具）。

口径依据：方案 9.2——容量偏差 = |报告汇总占用空间 − 资源管理器同范围占用空间| ÷ 资源管理器；
第六节"容量口径偏差"行：与资源管理器"占用空间"对比，W0 已发现并列切分漏算根级文件
（少 14.76GB），本脚本用于验证 T-02 修复后不再出现。

取数机制（卡面授权自决）：**已知基准夹具**——资源管理器"占用空间"由负责人在资源管理器
属性对话框读数后登记进基准 JSON（--baseline），脚本复算我们的口径并输出偏差百分比与明细。
不采用 Shell COM：零第三方依赖约束下无可靠的"占用空间"程序化取数途径（逻辑大小可取，
占用空间取数与资源管理器口径一致性无法保证）。

两种模式：
  --baseline <json>  对基准清单逐目录对比（默认只读，不写任何文件）；
  --fixture          构造 1000 个已知大小文件的临时夹具，预期=簇对齐公式，自检偏差为 0
                     或可解释（夹具仅写系统 TEMP，用后即删）。
退出码：0=全部 <1%；1=存在 ≥1% 的偏差；2=输入/环境错误。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from disk_audit.scanner import scan_path  # noqa: E402  仓库根已注入 sys.path

DEVIATION_LIMIT = 0.01
FIXTURE_FILE_COUNT = 1000


def cluster_bytes_of(path: str) -> int:
    """返回路径所在卷的簇大小（字节）；查询失败回退 4096。"""
    if os.name != "nt":
        return 4096
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive:
        return 4096
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    sectors_per_cluster = ctypes.c_ulong(0)
    bytes_per_sector = ctypes.c_ulong(0)
    free_clusters = ctypes.c_ulong(0)
    total_clusters = ctypes.c_ulong(0)
    ok = kernel32.GetDiskFreeSpaceW(
        ctypes.c_wchar_p(drive + "\\"),
        ctypes.byref(sectors_per_cluster),
        ctypes.byref(bytes_per_sector),
        ctypes.byref(free_clusters),
        ctypes.byref(total_clusters),
    )
    if not ok:
        return 4096
    return sectors_per_cluster.value * bytes_per_sector.value


def size_deviation(ours: int, baseline: int) -> float:
    """方案 9.2 口径：|报告汇总 − 资源管理器| ÷ 资源管理器。"""
    if baseline == 0:
        return 0.0 if ours == 0 else float("inf")
    return abs(ours - baseline) / baseline


def _fmt_bytes(n: int) -> str:
    return f"{n:,}"


def check_baseline(baseline_file: Path) -> int:
    """对基准 JSON 逐目录对比。JSON 形如：
    [{"path": "C:\\\\...\\\\某目录", "explorer_allocated_bytes": 123456789}, ...]
    """
    try:
        records = json.loads(baseline_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[容量偏差] 基准文件读取失败：{exc}")
        return 2
    if not isinstance(records, list) or not records:
        print("[容量偏差] 基准文件应为非空 JSON 数组")
        return 2

    print(
        "== L2 容量偏差对比（占用空间口径：|我们 − 资源管理器| ÷ 资源管理器，阈值 <1%）=="
    )
    failures = 0
    checked = 0
    for i, record in enumerate(records, start=1):
        if not isinstance(record, dict) or "path" not in record or "explorer_allocated_bytes" not in record:
            print(f"[{i}] 记录缺少 path / explorer_allocated_bytes 字段：{record!r}")
            failures += 1
            continue
        path = str(record["path"])
        baseline = int(record["explorer_allocated_bytes"])
        if not os.path.isdir(path):
            print(f"[{i}] 目录不存在，跳过：{path}")
            failures += 1
            continue
        result = scan_path(path)
        ours = result.stats.allocated_bytes
        dev = size_deviation(ours, baseline)
        verdict = "<1% 通过" if dev < DEVIATION_LIMIT else "≥1% 不通过"
        print(
            f"[{i}] {path}\n"
            f"    我们(占用空间)   ：{_fmt_bytes(ours)} B\n"
            f"    基准(资源管理器) ：{_fmt_bytes(baseline)} B\n"
            f"    偏差：{dev:.3%}  [{verdict}]"
        )
        checked += 1
        if dev >= DEVIATION_LIMIT:
            failures += 1
    print(f"== 结果：{checked} 个目录参与对比，{failures} 个不通过 ==")
    return 0 if failures == 0 else 1


def check_fixture() -> int:
    """构造 1000 个已知大小文件的夹具：预期=簇对齐公式，偏差应为 0。

    文件大小取 5000~5999 字节（大于常见簇、必为非常驻文件，避免 NTFS 驻留文件
    "占用 0 字节"的口径干扰）外加 10 个 0 字节文件（两侧口径均为 0）。
    """
    fixture_root = tempfile.mkdtemp(prefix="diskaudit_l2_")
    try:
        sizes: list[int] = [5000 + (i % 1000) for i in range(FIXTURE_FILE_COUNT - 10)]
        sizes += [0] * 10
        for i, size in enumerate(sizes):
            with open(os.path.join(fixture_root, f"f{i:04d}.bin"), "wb") as handle:
                handle.write(b"x" * size)
        cluster = cluster_bytes_of(fixture_root)
        expected = sum(0 if s == 0 else math.ceil(s / cluster) * cluster for s in sizes)
        result = scan_path(fixture_root)
        ours = result.stats.allocated_bytes
        dev = size_deviation(ours, expected)
        print(
            "== L2 夹具自检（1000 个已知大小文件）==\n"
            f"    夹具目录       ：{fixture_root}\n"
            f"    簇大小         ：{cluster} B\n"
            f"    预期(簇对齐公式)：{_fmt_bytes(expected)} B\n"
            f"    我们(占用空间)  ：{_fmt_bytes(ours)} B\n"
            f"    偏差：{dev:.3%}"
        )
        if dev == 0:
            print("    结论：偏差为 0，簇对齐公式与扫描口径一致")
        elif dev < DEVIATION_LIMIT:
            print("    结论：偏差 <1%，可解释（见方案 9.2 口径与文件系统差异）")
        else:
            print("    结论：偏差 ≥1%，需检查扫描口径（本夹具无压缩/稀疏文件，不应出现）")
        return 0 if dev < DEVIATION_LIMIT else 1
    finally:
        shutil.rmtree(fixture_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="容量偏差对比（占用空间口径，方案 9.2）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--baseline", type=Path, help="基准 JSON（资源管理器'占用空间'登记，格式见 docstring）"
    )
    group.add_argument(
        "--fixture", action="store_true", help="构造 1000 个已知大小文件的精确夹具自检"
    )
    args = parser.parse_args(argv)
    if args.baseline is not None:
        return check_baseline(args.baseline)
    return check_fixture()


if __name__ == "__main__":
    sys.exit(main())
