"""DR-004 探针测定脚本：各逻辑大小文件的占用空间（句柄实查 vs align8/簇对齐推算）。

依据：DR-004 2026-10-25 修订节探针条款（"探针（不同簇大小/NTFS 卷上 align8 vs
句柄实查）沉淀为测试或 tools/ 测定脚本，防止环境差异回归"）；2026-10-31 裁决节
按其证据落地四段分流（≤600B align8 / 601B~<簇 句柄实查 / ≥簇 簇对齐）。
用途：在目标卷上测定 MFT 驻留表现，供 DR-004 重开条件核对——**新卷部署前必跑**：
若 ≤600B 出现 align8 与句柄实查不一致，或 600B 以上多次运行稳定一致，即偏离裁决
前提（600B 稳定驻留上限），应停手上报重开 DR-004。
只读 + 临时目录（用后即删），零第三方依赖。

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
    for stream in (sys.stdout, sys.stderr):  # 中文输出守卫（rules-map 编码模式）
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="diskaudit_probe_"))
    created = not any(root.iterdir()) if root.exists() else False
    root.mkdir(parents=True, exist_ok=True)
    cluster = _cluster_bytes(str(root))
    print(f"样本目录：{root}")
    print(f"簇大小：{cluster} B")
    print(f"{'逻辑':>8} {'句柄实查':>10} {'推算':>10} {'差':>8}")
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
        print("注：推算列按 align8（<簇）/簇对齐（≥簇）计算，仅作驻留指示器——")
        print("与句柄实查一致即常驻。实现口径见 DR-004 裁决节四段分流")
        print("（601B~<簇 已改句柄实查，不依赖本列）；重开条件见本脚本 docstring。")
    finally:
        if created or "tempfile" in str(root):
            shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
