"""DR-004 修订版探针测定脚本：各逻辑大小文件的占用空间（句柄实查 vs 三段推算）。

依据：DR-004 2026-10-25 修订节探针条款（"探针（不同簇大小/NTFS 卷上 align8 vs
句柄实查）沉淀为测试或 tools/ 测定脚本，防止环境差异回归"）。
用途：在目标卷上测定 MFT 驻留上限与三段分流各段的表现，供容量偏差排查与
DR-004 再裁决引用。只读 + 临时目录（用后即删），零第三方依赖。

用法：python tools/probe_resident_allocation.py [样本目录]
退出码：0=完成。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from disk_audit.scanner import _align8, _allocated_size, _cluster_bytes  # noqa: E402

# 覆盖驻留边界两侧与簇边界两侧（探针实测驻留上限约 712B，簇 4096B 为常见默认）
SIZES = [0, 1, 100, 600, 700, 712, 800, 900, 1024, 2048, 4095, 4096, 5000]


class _Stat:
    """最小 stat 替身：句柄实查只读 st_size。"""

    def __init__(self, size: int) -> None:
        self.st_size = size


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="diskaudit_probe_"))
    created = not any(root.iterdir()) if root.exists() else False
    root.mkdir(parents=True, exist_ok=True)
    cluster = _cluster_bytes(str(root))
    print(f"样本目录：{root}")
    print(f"簇大小：{cluster} B")
    print(f"{'逻辑':>8} {'句柄实查':>10} {'三段推算':>10} {'差':>8}")
    try:
        for size in SIZES:
            probe = root / f"probe_{size}.bin"
            probe.write_bytes(b"x" * size)
            st = probe.stat()
            handle = _allocated_size(str(probe), st)
            estimated = (
                _align8(st.st_size) if st.st_size < cluster
                else ((st.st_size + cluster - 1) // cluster) * cluster
            )
            print(f"{size:>8} {handle:>10} {estimated:>10} {handle - estimated:>8}")
    finally:
        if created or "tempfile" in str(root):
            shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
