"""T-02（待办 C2，含 W0-C3 切分修正）文件枚举器单元测试。

覆盖验收②：根级文件计入（W0 缺陷①回归夹具）、长路径（>260）、reparse point
跳过、权限跳过计数（monkeypatch 可控夹具）；另覆盖双口径合计、前沿并行路径、
CLI JSON 摘要与异常输入。
"""
from __future__ import annotations

import json
import os
import stat as stat_mod
import subprocess
import sys
import types

import pytest

from disk_audit import scanner
from disk_audit.__main__ import main as cli_main
from disk_audit.scanner import scan_path


def _write(path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


class _FakeIter:
    """模拟 os.scandir 返回的迭代器（支持 with 语法）。"""

    def __init__(self, items):
        self._iter = iter(items)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iter)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeEntry:
    def __init__(self, path: str, is_dir: bool, size: int = 0,
                 stat_error: OSError | None = None, attrs: int = 0):
        self.path = path
        self.name = path.replace("/", "\\").rsplit("\\", 1)[-1]  # 对齐 os.DirEntry.name
        self._is_dir = is_dir
        self._size = size
        self._stat_error = stat_error
        self._attrs = attrs

    def stat(self, follow_symlinks: bool = False):
        if self._stat_error is not None:
            raise self._stat_error
        mode = (stat_mod.S_IFDIR if self._is_dir else stat_mod.S_IFREG) | 0o644
        return types.SimpleNamespace(
            st_mode=mode, st_size=self._size, st_file_attributes=self._attrs, st_mtime=0.0
        )


# ---------- 验收②：根级文件计入（W0 缺陷①回归） ----------


def test_root_level_files_counted(tmp_path):
    """W0 缺陷①回归：并行切分曾漏算"前沿之上"的根级文件（全盘曾少算 14.76GB）。"""
    _write(tmp_path / "top.bin", 100)
    _write(tmp_path / "sub" / "inner.bin", 200)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.files == 2
    assert result.stats.logical_bytes == 300


def test_only_root_level_files(tmp_path):
    _write(tmp_path / "a.bin", 1)
    _write(tmp_path / "b.bin", 2)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.files == 2
    assert result.stats.dirs == 1  # 仅根目录自身


def test_dirs_counted_including_root(tmp_path):
    _write(tmp_path / "f.bin", 1)
    _write(tmp_path / "a" / "b" / "deep.bin", 2)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.dirs == 3  # 根 + a + b
    assert result.stats.files == 2


def test_parallel_frontier_path(tmp_path):
    """子目录数达到 min_parts(workers*3) 触发前沿切分，走线程池路径。"""
    for i in range(8):
        _write(tmp_path / f"d{i}" / "x.bin", 10)
    result = scan_path(str(tmp_path), workers=2)
    assert result.frontier_parts == 8
    assert result.stats.files == 8
    assert result.stats.logical_bytes == 80
    assert result.stats.dirs == 9  # 根 + 8 个子目录


# ---------- 验收②：长路径（>260） ----------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 长路径夹具")
def test_long_path_counted(tmp_path):
    deep = tmp_path
    for _ in range(6):
        deep = deep / ("L" * 40)  # 6 层 × 40 字符，叠加 tmp 前缀必超 260
    os.makedirs("\\\\?\\" + str(deep), exist_ok=True)
    with open("\\\\?\\" + str(deep / "deep.bin"), "wb") as handle:
        handle.write(b"x" * 64)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.files == 1
    assert result.stats.logical_bytes == 64
    assert result.stats.skips.too_long == 0


# ---------- 验收②：reparse point 跳过 ----------


@pytest.mark.skipif(sys.platform != "win32", reason="需要 NTFS junction")
def test_junction_skipped_and_counted(tmp_path):
    target = tmp_path / "real"
    _write(target / "inner.bin", 32)
    link = tmp_path / "link"
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True, errors="replace",  # cmd 输出为 ANSI 编码
    )
    assert proc.returncode == 0, proc.stderr
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.skips.reparse == 1
    assert result.stats.files == 1  # 仅 real/inner.bin；junction 子树不计


# ---------- 验收②：权限跳过计数（monkeypatch 可控夹具） ----------


def test_permission_skip_counted(tmp_path, monkeypatch):
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "blocked"), True),
            _FakeEntry(str(tmp_path / "ok.bin"), False, 7),
        ],
        str(tmp_path / "blocked"): None,  # 打开即 PermissionError
    }

    def fake_scandir(path):
        if entries.get(path) is None:
            raise PermissionError(13, "拒绝访问", path)
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    # 夹具文件并不真实存在，真实占用查询会失败——以替身返回逻辑大小
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: st.st_size)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.skips.permission == 1
    assert result.stats.files == 1  # 其余扫描不受影响（X-1：继续完成其余扫描）
    assert result.stats.logical_bytes == 7


def test_stat_failure_counted_as_other(tmp_path, monkeypatch):
    """条目 stat 失败（如扫描间隙被删除）计入 other，不中断。"""
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "gone.bin"), False, 5,
                       stat_error=OSError(2, "系统找不到指定的文件", str(tmp_path / "gone.bin"))),
        ],
    }

    def fake_scandir(path):
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.skips.other == 1
    assert result.stats.files == 0


def test_occupied_error_counted(tmp_path, monkeypatch):
    """共享冲突（winerror 32）计入 occupied。"""
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "locked.bin"), False, 9,
                       stat_error=OSError(32, "另一个程序正在使用此文件", "locked.bin")),
        ],
    }

    def fake_scandir(path):
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.skips.occupied == 1


# ---------- 双口径计量 ----------


def test_dual_size_single_file(tmp_path):
    _write(tmp_path / "one.bin", 5000)  # >1KB 确保非 MFT 驻留，分配量必 ≥ 逻辑大小
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.logical_bytes == 5000
    if sys.platform == "win32":
        # 占用空间按簇对齐：不小于逻辑大小（与资源管理器同口径，P1）
        assert result.stats.allocated_bytes >= 5000


def test_empty_file_zero_allocated(tmp_path):
    _write(tmp_path / "empty.bin", 0)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.logical_bytes == 0
    assert result.stats.allocated_bytes == 0


# ---------- 纯函数与 CLI ----------


def test_long_path_prefix():
    assert scanner._long_path("C:\\a") == "C:\\a"
    assert scanner._long_path("C:\\" + "a" * 300).startswith("\\\\?\\")
    assert scanner._long_path("\\\\?\\C:\\a") == "\\\\?\\C:\\a"
    assert scanner._long_path("\\\\srv\\share\\x").startswith("\\\\?\\UNC\\")


def test_cli_scan_outputs_json(tmp_path, capsys):
    _write(tmp_path / "a.bin", 5)
    assert cli_main(["scan", str(tmp_path), "--workers", "2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == 1
    assert payload["entries"] == payload["files"] + payload["dirs"]
    assert payload["logical_bytes"] == 5
    assert payload["allocated_bytes"] >= 5
    assert set(payload["skipped"]) >= {
        "permission", "occupied", "too_long", "reparse", "other", "total",
    }


def test_cli_scan_bad_path(tmp_path, capsys):
    assert cli_main(["scan", str(tmp_path / "nope")]) == 2


def test_cli_scan_invalid_workers(tmp_path):
    assert cli_main(["scan", str(tmp_path), "--workers", "0"]) == 2


def test_selftest_still_green(capsys):
    """--selftest 门禁不受 scan 子命令接入影响。"""
    assert cli_main(["--selftest"]) == 0
    assert "passed" in capsys.readouterr().out


# ---------- DR-004 修订版三段分流（T2-01；验收④：属性位 monkeypatch） ----------

_COMPRESSED = 0x800  # FILE_ATTRIBUTE_COMPRESSED
_SPARSE = 0x200  # FILE_ATTRIBUTE_SPARSE_FILE


def test_compressed_sparse_files_use_handle_query(tmp_path, monkeypatch):
    """属性位含压缩/稀疏 → 句柄实查；常规文件走推算（验收④）。"""
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "c.bin"), False, 100, attrs=_COMPRESSED),
            _FakeEntry(str(tmp_path / "s.bin"), False, 100, attrs=_SPARSE),
            _FakeEntry(str(tmp_path / "n.bin"), False, 100),
        ],
    }
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    called: list[str] = []

    def spy_handle(path, st):
        called.append(path)
        return 4096

    monkeypatch.setattr(scanner, "_allocated_size", spy_handle)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert len(called) == 2  # 仅压缩/稀疏两个文件开句柄
    assert result.stats.allocated_bytes == 4096 * 2 + 104  # 常规文件 align8(100)


def test_normal_files_never_open_handle(tmp_path, monkeypatch):
    """逻辑 ≥ 簇的未压缩非稀疏文件零句柄（DR-004 裁决节④；601B~<簇 段按裁决③须开句柄）。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "a.bin"), False, 5000)]}
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))

    def boom(path, st):
        raise AssertionError("常规文件不得开句柄（DR-004 三段分流）")

    monkeypatch.setattr(scanner, "_allocated_size", boom)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.allocated_bytes == 8192  # 逻辑 ≥ 簇 → 簇对齐 ceil(5000/4096)


def test_align8_pure():
    """≤600B → align8（DR-004 裁决节②：600B 为本卷实测稳定驻留上限；探针 100→104）。"""
    assert scanner._align8(0) == 0
    assert scanner._align8(1) == 8
    assert scanner._align8(100) == 104
    assert scanner._align8(700) == 704
    assert scanner._align8(712) == 712
    assert scanner._align8(4096) == 4096


def test_handle_failure_counts_occupied(tmp_path, monkeypatch):
    """压缩/稀疏文件句柄实查失败 → X-1 计入 occupied（双口径一致，语义不变）。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "c.bin"), False, 9, attrs=_COMPRESSED)]}
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: None)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.skips.occupied == 1
    assert result.stats.files == 0


@pytest.mark.skipif(sys.platform != "win32", reason="句柄实查仅 Windows")
def test_resident_probe_align8_matches_handle(tmp_path):
    """DR-004 修订版探针条款：常驻小文件 align8 与句柄实查逐文件一致。

    样本 ≤600B，稳居本卷 MFT 驻留区间（探针实测驻留上限 ≈712B，
    完整梯度表见 tools/probe_resident_allocation.py 与 T2-01 执行记录）。
    """
    for size in (0, 1, 100, 600):
        probe = tmp_path / f"p{size}.bin"
        probe.write_bytes(b"x" * size)
        st = probe.stat()
        assert scanner._align8(st.st_size) == scanner._allocated_size(str(probe), st)


@pytest.mark.skipif(sys.platform != "win32", reason="句柄实查仅 Windows")
def test_cluster_alignment_matches_handle_for_large_file(tmp_path):
    """逻辑 ≥ 簇 → 簇对齐与句柄实查一致（真实 NTFS 文件）。"""
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 5000)
    st = big.stat()
    cluster = scanner._cluster_bytes(str(big))
    expected = ((st.st_size + cluster - 1) // cluster) * cluster
    assert expected == scanner._allocated_size(str(big), st)


def test_cluster_bytes_cached_and_fallback(monkeypatch):
    """GetDiskFreeSpaceW 按盘符根查询并缓存；失败回退 4096。"""
    monkeypatch.setattr(scanner, "_CLUSTER_CACHE", {})
    calls: list[str] = []

    def fake_query(root, sectors, bytes_per_sector, free, total):
        calls.append(root)
        sectors.value = 8
        bytes_per_sector.value = 512
        free.value = 100
        total.value = 200
        return 1

    monkeypatch.setattr(scanner, "_get_disk_free_space_w", fake_query)
    assert scanner._cluster_bytes(r"C:\x\y") == 8 * 512
    assert scanner._cluster_bytes(r"C:\z") == 8 * 512
    assert len(calls) == 1  # 同盘符缓存生效

    monkeypatch.setattr(
        scanner, "_get_disk_free_space_w", lambda *a: 0  # 查询失败
    )
    monkeypatch.setattr(scanner, "_CLUSTER_CACHE", {})
    assert scanner._cluster_bytes(r"D:\x") == 4096  # 回退默认簇


# ---------- DR-004 裁决节四段分流（T2-08；验收④：600B/601B 边界 + 属性位） ----------


def test_boundary_600_align8_601_handle(tmp_path, monkeypatch):
    """裁决节②③边界：≤600B → align8 零句柄；601B~<簇 → 句柄实查。"""
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "a600.bin"), False, 600),
            _FakeEntry(str(tmp_path / "b601.bin"), False, 601),
        ],
    }
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    called: list[str] = []

    def spy_handle(path, st):
        called.append(path)
        return 1048  # 句柄实查替身回报值（非驻留实占由卷决定，单测不依赖具体值）

    monkeypatch.setattr(scanner, "_allocated_size", spy_handle)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert called == [str(tmp_path / "b601.bin")]  # 仅 601B 开句柄，600B 零句柄
    assert result.stats.allocated_bytes == 600 + 1048  # 600B → align8(600)=600


def test_segment3_handle_failure_counts_occupied(tmp_path, monkeypatch):
    """裁决节③：601B~<簇 句柄实查失败 → X-1 计入 occupied（与压缩/稀疏同语义）。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "m.bin"), False, 601)]}
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: None)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.skips.occupied == 1
    assert result.stats.files == 0


@pytest.mark.skipif(sys.platform != "win32", reason="句柄实查仅 Windows")
def test_gradient_mixed_vs_pure_handle_below_0_1pct(tmp_path):
    """裁决节 ②'：混合夹具（0B/~100B/~600B/~1KB/~5KB 梯度）混合路径与纯句柄
    路径的占用空间汇总偏差 <0.1%（选项 c 落地，预期 ~0.000%）。"""
    sizes = [0, 100, 600, 1024, 5000]
    files = []
    for copy in range(3):
        for size in sizes:
            probe = tmp_path / f"g{copy}_{size}.bin"
            probe.write_bytes(b"x" * size)
            files.append(probe)
    result = scan_path(str(tmp_path), workers=2)
    pure = sum(scanner._allocated_size(str(f), f.stat()) for f in files)
    assert pure > 0
    deviation = abs(result.stats.allocated_bytes - pure) / pure
    assert deviation < 0.001


# ---------- C7 中止与部分结果（T2-05，X-2：统一"不完整"出口） ----------


def test_normal_scan_not_incomplete(tmp_path):
    """正常完成路径：incomplete=False，回归保障（验收②）。"""
    _write(tmp_path / "a.bin", 10)
    result = scan_path(str(tmp_path))
    assert result.incomplete is False
    assert result.to_json_dict()["incomplete"] is False


def test_abort_check_marks_incomplete_and_keeps_partial(tmp_path):
    """用户中止（停止信号）：部分结果保留 + incomplete 标记（验收①）。"""
    for i in range(6):
        _write(tmp_path / f"d{i}" / "f.bin", 10)
    calls = {"n": 0}

    def abort_check() -> bool:  # 首个目录展开后即中止
        calls["n"] += 1
        return calls["n"] > 1

    result = scan_path(str(tmp_path), workers=2, abort_check=abort_check)
    assert result.incomplete is True
    assert result.stats.files < 6  # 部分结果：未扫完即停
    payload = result.to_json_dict()
    assert payload["incomplete"] is True


class _SimulatedCtrlC(Exception):
    """模拟用户中止（Ctrl+C/停止信号）的测试替身。

    禁止在测试中抛真 KeyboardInterrupt（06 报告退回单 #21/#22：真 KI 属
    BaseException，在 pwsh runner 上会从 pytest 会话层逃逸，环境时序相关的
    间歇雷；本异常派生自 Exception，走 scan_path 的统一捕获区，行为确定）。
    """


def test_user_abort_exception_marks_incomplete(tmp_path):
    """用户中止（停止信号）异常同样走"不完整"出口（验收④触发一）。

    以非 KI 自定义异常模拟中止（退回单修复口径）；abort_check 抛出的任何
    异常都应被 scan_path 统一捕获并置 incomplete。
    """
    _write(tmp_path / "d0" / "f.bin", 10)

    def abort_check() -> bool:
        raise _SimulatedCtrlC

    result = scan_path(str(tmp_path), workers=1, abort_check=abort_check)
    assert result.incomplete is True
    assert result.stats.files == 0  # 首个检查点即中止


def test_unexpected_exception_marks_incomplete(tmp_path, monkeypatch):
    """扫描中未预期异常：统一"不完整"出口，部分结果保留（验收④触发二）。"""
    _write(tmp_path / "d0" / "f.bin", 10)
    _write(tmp_path / "d1" / "f.bin", 10)
    real_scandir = scanner._scandir
    state = {"n": 0}

    def fake_scandir(path):
        state["n"] += 1
        if state["n"] > 2:  # 前两次正常（root 展开与首个子目录），之后炸
            raise RuntimeError("注入的未预期异常")
        return real_scandir(path)

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=1)
    assert result.incomplete is True
    assert result.stats.files >= 1  # 异常前已采集的文件保留


def test_cli_scan_outputs_incomplete_marker(tmp_path, monkeypatch, capsys):
    """CLI：中止后的 scan 输出含"不完整"标记且退出码 0（标记在带内）。"""
    _write(tmp_path / "a.bin", 5)
    real_scan_path = scanner.scan_path

    def aborting_scan(path, workers=8):
        result = real_scan_path(path, workers=workers)
        result.incomplete = True
        return result

    monkeypatch.setattr("disk_audit.__main__.scan_path", aborting_scan)
    assert cli_main(["scan", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["incomplete"] is True


# ---------- C8 实时进度事件（T3-01，E-1：线程安全进度回调） ----------


def test_progress_events_fields_monotonic_throttled(tmp_path, monkeypatch):
    """验收①：节流后事件含 entries/path/elapsed，entries 与 elapsed 单调不减，
    事件次数远小于条目数（双阈值节流生效）；终态事件给出精确全量条目数。"""
    # 屏蔽时间阈值（1000s 内不触发），仅条目阈值参与，计数确定性
    monkeypatch.setattr(scanner, "_PROGRESS_MIN_INTERVAL", 1000.0)
    monkeypatch.setattr(scanner, "_PROGRESS_ENTRY_STEP", 5)
    monkeypatch.setattr(scanner, "_PROGRESS_CHECK_STEP", 4)
    for i in range(8):
        for j in range(10):
            _write(tmp_path / f"d{i}" / f"f{j}.bin", 10)
    events: list[scanner.ProgressEvent] = []
    result = scan_path(str(tmp_path), workers=2, progress_cb=events.append)
    total = result.stats.files + result.stats.dirs
    assert total == 89  # 80 文件 + 8 子目录 + 根
    assert len(events) > 1  # 扫描中途确有事件（非仅终态一次）
    assert len(events) < total // 3  # 节流生效：事件次数远小于条目数
    for event in events:
        assert isinstance(event.entries, int) and event.entries >= 1
        assert isinstance(event.path, str) and event.path
        assert event.path.startswith(str(tmp_path))
        assert isinstance(event.elapsed, float) and event.elapsed >= 0.0
    entries_seq = [e.entries for e in events]
    elapsed_seq = [e.elapsed for e in events]
    assert entries_seq == sorted(entries_seq)  # 单调不减
    assert elapsed_seq == sorted(elapsed_seq)  # 单调不减
    assert events[-1].entries == total  # 终态事件 = 精确全量


def test_progress_default_thresholds_small_scan(tmp_path):
    """默认双阈值（500ms/2 万条目）下小快扫描仅终态事件级少量事件。"""
    for i in range(3):
        _write(tmp_path / f"d{i}" / "f.bin", 10)
    events: list[scanner.ProgressEvent] = []
    result = scan_path(str(tmp_path), workers=1, progress_cb=events.append)
    total = result.stats.files + result.stats.dirs
    assert total == 7  # 3 文件 + 3 子目录 + 根
    assert 1 <= len(events) <= 3  # 默认阈值下不逐条目轰炸
    assert all(e.entries <= total for e in events)
    assert events[-1].entries == total


def test_progress_callback_exception_bfs_phase(tmp_path):
    """验收②：回调抛异常 → 扫描正常完成（incomplete=False）、计 other、结果完整。"""
    for i in range(4):
        _write(tmp_path / f"d{i}" / "f.bin", 10)

    def boom(event):
        raise RuntimeError("注入的回调异常")

    result = scan_path(str(tmp_path), workers=2, progress_cb=boom)
    assert result.incomplete is False
    assert result.stats.files == 4
    assert result.stats.dirs == 5
    assert result.stats.skips.other >= 1


def test_progress_callback_exception_parallel_phase(tmp_path, monkeypatch):
    """验收②（并行段）：工作线程内回调异常同样计 other 且不中断扫描。"""
    monkeypatch.setattr(scanner, "_PROGRESS_MIN_INTERVAL", 1000.0)
    monkeypatch.setattr(scanner, "_PROGRESS_ENTRY_STEP", 2)
    monkeypatch.setattr(scanner, "_PROGRESS_CHECK_STEP", 2)
    for i in range(8):
        _write(tmp_path / f"d{i}" / "f.bin", 10)

    def boom(event):
        raise RuntimeError("注入的回调异常")

    result = scan_path(str(tmp_path), workers=2, progress_cb=boom)
    assert result.incomplete is False
    assert result.stats.files == 8
    assert result.stats.skips.other >= 1


def test_progress_none_default_zero_overhead_equivalent(tmp_path):
    """progress_cb=None（默认）与不传回调行为一致（零开销路径回归）。"""
    for i in range(6):
        _write(tmp_path / f"d{i}" / "f.bin", 10)
    r1 = scan_path(str(tmp_path), workers=2)
    r2 = scan_path(str(tmp_path), workers=2, progress_cb=None)
    d1, d2 = r1.to_json_dict(), r2.to_json_dict()
    d1.pop("seconds"), d2.pop("seconds")  # 耗时天然不同，不比较
    assert d1 == d2


def test_progress_multithread_monotonic(tmp_path, monkeypatch):
    """多线程段（workers=4）进度仍单调：锁内串行触发保证观察序。"""
    monkeypatch.setattr(scanner, "_PROGRESS_MIN_INTERVAL", 1000.0)
    monkeypatch.setattr(scanner, "_PROGRESS_ENTRY_STEP", 7)
    monkeypatch.setattr(scanner, "_PROGRESS_CHECK_STEP", 3)
    for i in range(16):
        for j in range(3):
            _write(tmp_path / f"d{i}" / f"f{j}.bin", 10)
    events: list[scanner.ProgressEvent] = []
    result = scan_path(str(tmp_path), workers=4, progress_cb=events.append)
    total = result.stats.files + result.stats.dirs
    assert total == 65  # 48 文件 + 16 子目录 + 根
    assert len(events) >= 2
    for prev, curr in zip(events, events[1:]):
        assert curr.entries >= prev.entries  # 多线程下 entries 单调不减
        assert curr.elapsed >= prev.elapsed  # 多线程下 elapsed 单调不减
    assert events[-1].entries == total


# ---------- T4-08/T3-08：枚举段（迭代器 next() 段）OSError 折入 X-1 ----------
# 场景依据：T2-09 首轮 4/4 扫描 incomplete 实证——VM AppX 服务窗口实时增删
# 判定单元目录，scandir 迭代句柄失效在 for entry in iterator 段抛 OSError，
# 逃逸进 X-2"不完整"出口。修复口径（08 报告 §3 裁决 2）：枚举段 OSError 折入
# X-1（跳过+计数+继续），X-2 保留给真实中止/致命异常。
# 与既有 stat 段夹具（_FakeEntry.stat_error）区分：本区块夹具在迭代器
# next() 段抛错，不触及 stat/计量段。


class _ChurnIter:
    """枚举段抖动夹具：产出前 churn_after 个条目后在迭代器 next() 段抛 error。

    error=None 时等价普通迭代器（耗尽即停）；churn_after 缺省 = 全部产出后抛
    （枚举尾部失效），传更小值模拟"枚举到一半目录被外部删除"。
    """

    def __init__(self, items, error: Exception | None = None,
                 churn_after: int | None = None):
        self._items = list(items)
        self._error = error
        self._churn_after = len(self._items) if churn_after is None else churn_after
        self._n = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._error is not None and self._n >= self._churn_after:
            raise self._error
        if self._n >= len(self._items):
            raise StopIteration
        item = self._items[self._n]
        self._n += 1
        return item

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_expand_dir_iteration_oserror_folds_into_x1(tmp_path, monkeypatch):
    """验收①（BFS 段）：_expand_dir 迭代段 OSError → 跳过计数+继续、不进 X-2。"""
    gone = OSError(2, "模拟目录在枚举期间被外部删除")
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "d1"), True),
            _FakeEntry(str(tmp_path / "ok"), True),
        ],
        str(tmp_path / "d1"): [_FakeEntry(str(tmp_path / "d1" / "g0.bin"), False, 10)],
        str(tmp_path / "ok"): [_FakeEntry(str(tmp_path / "ok" / "f.bin"), False, 20)],
    }

    def fake_scandir(path):
        if path == str(tmp_path / "d1"):
            return _ChurnIter(entries[path], error=gone)  # 产出 g0 后抛（枚举尾部失效）
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=1)  # 2 顶层目录 < min_parts=3 → 全 BFS 段
    assert result.incomplete is False  # 不触发 X-2"不完整"出口
    assert result.stats.skips.other == 1  # X-1 计数恰一次
    assert result.stats.files == 2  # 已枚举的 g0.bin 保留 + ok 目录完整
    assert result.stats.dirs == 3  # 根 + d1 + ok（扫描继续完成）


def test_scan_tree_iteration_oserror_folds_into_x1(tmp_path, monkeypatch):
    """验收①（并行段）：_scan_tree 迭代段 OSError → 计数+继续、不进 X-2。"""
    gone = OSError(2, "模拟前沿子树枚举期间目录消失")
    root_entries = [
        _FakeEntry(str(tmp_path / f"d{i}"), True) for i in range(6)
    ]
    entries = {str(tmp_path): root_entries}
    for i in range(6):
        entries[str(tmp_path / f"d{i}")] = [
            _FakeEntry(str(tmp_path / f"d{i}" / "f.bin"), False, 10)
        ]

    def fake_scandir(path):
        if path == str(tmp_path / "d3"):
            return _ChurnIter(entries[path], error=gone)
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=2)  # 6 顶层目录 ≥ min_parts=6 → 并行段
    assert result.incomplete is False
    assert result.stats.skips.other == 1  # 工作线程折入计数经 merge 汇入全局
    assert result.stats.files == 6  # d3 抛错前已产出的 f.bin 也计入
    assert result.stats.dirs == 7  # 根 + 6 个前沿目录


def test_deep_nested_iteration_oserror_folds_into_x1(tmp_path, monkeypatch):
    """验收②边界：折入发生在 BFS 嵌套深处（第 4 层）同样计数+继续。"""
    gone = OSError(2, "模拟深层目录枚举失效")
    entries = {
        str(tmp_path): [_FakeEntry(str(tmp_path / "a"), True)],
        str(tmp_path / "a"): [_FakeEntry(str(tmp_path / "a" / "b"), True)],
        str(tmp_path / "a" / "b"): [_FakeEntry(str(tmp_path / "a" / "b" / "deep"), True)],
        str(tmp_path / "a" / "b" / "deep"): [
            _FakeEntry(str(tmp_path / "a" / "b" / "deep" / "g0.bin"), False, 10)
        ],
    }

    def fake_scandir(path):
        if path == str(tmp_path / "a" / "b" / "deep"):
            return _ChurnIter(entries[path], error=gone)
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=1)  # 单链 < min_parts → deep 在 BFS 段展开
    assert result.incomplete is False
    assert result.stats.skips.other == 1
    assert result.stats.files == 1  # deep 已枚举的 g0.bin 保留
    assert result.stats.dirs == 4  # 根 + a + b + deep


def test_enumerate_units_iteration_oserror_folds_into_x1(tmp_path, monkeypatch):
    """验收③注入式：单元枚举段（Packages 容器下钻）迭代 OSError → 计数+继续。

    T2-09 实证场景（Packages 下 wpsappext1~3 消失）的注入等效：容器迭代段
    抛 OSError 时单元清单保留已枚举部分、扫描整体完整完成、不进 X-2。
    """
    gone = OSError(2, "模拟 AppX 服务窗口删 Packages 下单元目录")
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "Programs"), True),
            _FakeEntry(str(tmp_path / "Packages"), True),
        ],
        str(tmp_path / "Programs"): [_FakeEntry(str(tmp_path / "Programs" / "p_app"), True)],
        str(tmp_path / "Programs" / "p_app"): [],
        str(tmp_path / "Packages"): [_FakeEntry(str(tmp_path / "Packages" / "wps1"), True)],
        str(tmp_path / "Packages" / "wps1"): [],
    }

    def fake_scandir(path):
        if path == str(tmp_path / "Packages"):
            # 单元枚举段与 BFS 展开段各折入一次（同一夹具目录被两处枚举）
            return _ChurnIter(entries[path], error=gone)
        return _FakeIter(entries[path])

    # 单元枚举走独立间接层 _units_scandir（与 _scandir 的夹具调用计数隔离，
    # 见 scanner.py 注释）；BFS/并行展开走 _scandir——两者指同一 fake
    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    monkeypatch.setattr(scanner, "_units_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=1)
    assert result.incomplete is False
    assert result.stats.skips.other == 2  # enumerate_units 折入 + _expand_dir 折入
    unit_names = {u.path.rsplit("\\", 1)[-1] for u in result.units}
    assert unit_names == {"Programs", "Packages", "p_app", "wps1"}  # 已枚举单元保留
    assert result.stats.dirs == 5  # 根 + Programs + Packages + p_app + wps1


def test_progress_terminal_event_coexists_with_enumeration_fold(tmp_path, monkeypatch):
    """C8 共存：折入后进度终态事件仍发且条目数与结果一致。"""
    gone = OSError(2, "模拟目录消失")
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "d1"), True),
            _FakeEntry(str(tmp_path / "ok"), True),
        ],
        str(tmp_path / "d1"): [_FakeEntry(str(tmp_path / "d1" / "g0.bin"), False, 10)],
        str(tmp_path / "ok"): [_FakeEntry(str(tmp_path / "ok" / "f.bin"), False, 20)],
    }

    def fake_scandir(path):
        if path == str(tmp_path / "d1"):
            return _ChurnIter(entries[path], error=gone)
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    events: list[scanner.ProgressEvent] = []
    result = scan_path(str(tmp_path), workers=1, progress_cb=events.append)
    assert result.incomplete is False
    assert result.stats.skips.other == 1
    assert len(events) >= 1  # 终态事件不受节流必发
    total = result.stats.files + result.stats.dirs
    assert events[-1].entries == total  # 终态条目数 = 实际结果口径


def test_non_oserror_iteration_exception_still_x2(tmp_path, monkeypatch):
    """验收②反例：迭代段非 OSError 致命异常仍走 X-2"不完整"出口（边界不放宽）。"""
    entries = {
        str(tmp_path): [_FakeEntry(str(tmp_path / "d0"), True)],
        str(tmp_path / "d0"): [_FakeEntry(str(tmp_path / "d0" / "f.bin"), False, 10)],
    }

    def fake_scandir(path):
        if path == str(tmp_path / "d0"):
            return _ChurnIter(entries[path], error=RuntimeError("非 OSError 致命异常"))
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    result = scan_path(str(tmp_path), workers=1)
    assert result.incomplete is True  # X-2 语义不变
    assert result.stats.files == 1  # 异常前已采集的部分保留（部分出口口径）


# ---------- T4-09/T3-09：段③（601B~<簇）目录级批查取数 ----------
# 依据：DR-004 实测规模更正节（2026-11-01）——段③ Roaming 67,035 / Local 163,238
# 个文件逐文件句柄 ≈30µs/次，AppData 合计 ~14.4s；本卡只改段③取数机制：目录级
# 批查（FileIdExtdDirectoryInfo 一次目录句柄带回整目录 AllocationSize/EndOfFile/
# FileAttributes/文件名），映射未命中/批查失败静默回退现行逐文件句柄（X-1 语义
# 不变）；四段分流规则与双口径语义不变（DR-004 裁决节勿重议——①压缩/稀疏、
# ②≤600B align8、④≥簇 簇对齐三段路径不动）。机制经本机实证（2026-11-05 探针，
# 留档执行记录）：FILE_ID_EXTD_DIR_INFO 由 class 19(0x13) 触发（MSDN 结构体页
# 明示；卡面提示"class 22"实证为 ERROR_INVALID_PARAMETER），批查 AllocationSize
# 与逐文件 FileStandardInfo 同源同值（含驻留边界样本 600B→600）。

def test_segment3_batch_hit_avoids_per_file_handle(tmp_path, monkeypatch):
    """段③批查生效：601B~<簇 经批查映射取 AllocationSize、零逐文件句柄（懒加载
    恰一次）；②④段无视映射值（999 罐头值不被采用，路径不动）。"""
    entries = {
        str(tmp_path): [
            _FakeEntry(str(tmp_path / "r600.bin"), False, 600),
            _FakeEntry(str(tmp_path / "m601.bin"), False, 601),
            _FakeEntry(str(tmp_path / "big.bin"), False, 5000),
        ],
    }
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    loader_calls: list[str] = []

    def fake_loader(directory):
        loader_calls.append(directory)
        # 罐头值 999：仅段③样本（m601）应被采用；②段/④段若误用即断言失败
        return {
            "r600.bin": (999, 0x20),
            "m601.bin": (1048, 0x20),
            "big.bin": (999, 0x20),
        }

    monkeypatch.setattr(scanner, "_batch_directory_allocation", fake_loader)

    def boom(path, st):
        raise AssertionError("段③批查命中时不得回退逐文件句柄")

    monkeypatch.setattr(scanner, "_allocated_size", boom)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert loader_calls == [str(tmp_path)]  # 懒加载：首个段③文件触发，整目录一次
    assert result.stats.allocated_bytes == 600 + 1048 + 8192
    # 600B→align8(600)=600（非 999）；601B→批查 1048；5000B→簇对齐 8192（非 999）
    assert result.stats.skips.total == 0
    assert result.incomplete is False


def test_batch_parallel_phase_hit(tmp_path, monkeypatch):
    """并行段（_scan_tree）同样走批查映射：每个前沿目录各自批查命中、零句柄。"""
    entries = {
        str(tmp_path): [_FakeEntry(str(tmp_path / f"d{i}"), True) for i in range(6)],
    }
    for i in range(6):
        entries[str(tmp_path / f"d{i}")] = [
            _FakeEntry(str(tmp_path / f"d{i}" / "f.bin"), False, 601)
        ]

    def fake_scandir(path):
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)

    def fake_loader(directory):
        return {"f.bin": (1048, 0x20)}

    monkeypatch.setattr(scanner, "_batch_directory_allocation", fake_loader)

    def boom(path, st):
        raise AssertionError("并行段批查命中时不得回退逐文件句柄")

    monkeypatch.setattr(scanner, "_allocated_size", boom)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)  # 6 顶层目录 ≥ min_parts=6 → 并行段
    assert result.stats.files == 6
    assert result.stats.allocated_bytes == 1048 * 6
    assert result.incomplete is False


def test_batch_none_falls_back_to_handle(tmp_path, monkeypatch):
    """验收④：批查失败（返回 None）→ 静默回退现行逐文件句柄，X-1 计数语义不变。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "m.bin"), False, 601)]}
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    monkeypatch.setattr(scanner, "_batch_directory_allocation", lambda directory: None)
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: 1048)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.files == 1
    assert result.stats.allocated_bytes == 1048
    assert result.stats.skips.total == 0  # 批查失败静默：不新创计数（卡面实现约束）
    assert result.incomplete is False


def test_batch_exception_falls_back_to_handle(tmp_path, monkeypatch):
    """验收④：批查注入异常 → 静默回退逐文件句柄，不逃逸进 X-2"不完整"出口。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "m.bin"), False, 601)]}

    def boom_loader(directory):
        raise RuntimeError("注入的批查异常")

    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    monkeypatch.setattr(scanner, "_batch_directory_allocation", boom_loader)
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: 1048)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.files == 1
    assert result.stats.allocated_bytes == 1048
    assert result.stats.skips.total == 0
    assert result.incomplete is False


def test_batch_map_miss_falls_back_to_handle(tmp_path, monkeypatch):
    """映射未命中（文件名不在批查结果中，如扫描间隙新建/批查不完整）→ 回退。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "m.bin"), False, 601)]}
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    monkeypatch.setattr(
        scanner, "_batch_directory_allocation", lambda directory: {"other.bin": (1048, 0x20)}
    )
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: 1048)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.files == 1
    assert result.stats.allocated_bytes == 1048
    assert result.stats.skips.total == 0


def test_batch_parallel_phase_falls_back(tmp_path, monkeypatch):
    """并行段批查失败 → 逐文件回退同样生效（与 BFS 段对称）。"""
    entries = {
        str(tmp_path): [_FakeEntry(str(tmp_path / f"d{i}"), True) for i in range(6)],
    }
    for i in range(6):
        entries[str(tmp_path / f"d{i}")] = [
            _FakeEntry(str(tmp_path / f"d{i}" / "f.bin"), False, 601)
        ]

    def fake_scandir(path):
        return _FakeIter(entries[path])

    monkeypatch.setattr(scanner, "_scandir", fake_scandir)
    monkeypatch.setattr(scanner, "_batch_directory_allocation", lambda directory: None)
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: 1048)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)  # 6 顶层目录 → 并行段
    assert result.stats.files == 6
    assert result.stats.allocated_bytes == 1048 * 6
    assert result.incomplete is False


def test_batch_failure_and_handle_failure_still_occupied(tmp_path, monkeypatch):
    """负例：批查失败且逐文件实查也失败 → X-1 计 occupied（现行语义不变）。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "m.bin"), False, 601)]}
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    monkeypatch.setattr(scanner, "_batch_directory_allocation", lambda directory: None)
    monkeypatch.setattr(scanner, "_allocated_size", lambda path, st: None)
    monkeypatch.setattr(scanner, "_cluster_bytes", lambda path: 4096)
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.skips.occupied == 1
    assert result.stats.files == 0


def test_batch_non_windows_degradation_unchanged(tmp_path, monkeypatch):
    """非 Windows 降级路径不变：无句柄 API 时占用空间=逻辑大小，批查零发起。"""
    entries = {str(tmp_path): [_FakeEntry(str(tmp_path / "m.bin"), False, 601)]}
    monkeypatch.setattr(scanner, "_scandir", lambda path: _FakeIter(entries[path]))
    monkeypatch.setattr(scanner, "_create_file_w", None)  # 模拟非 Windows
    loader_calls: list[str] = []
    monkeypatch.setattr(
        scanner, "_batch_directory_allocation", lambda d: loader_calls.append(d)
    )
    result = scan_path(str(tmp_path), workers=2)
    assert result.stats.allocated_bytes == 601  # 逻辑大小降级（既有语义）
    assert loader_calls == []  # 降级路径零批查开销


@pytest.mark.skipif(sys.platform != "win32", reason="批查 API 仅 Windows")
def test_batch_matches_handle_per_file_segment3(tmp_path):
    """卡面一致性红线：批查结果与句柄实查逐文件一致（601B~<簇 样本集 + 驻留边界）。

    真实 NTFS 文件 + 真实 FileIdExtdDirectoryInfo 批查（无替身）：每个样本的
    批查 AllocationSize/FileAttributes 与逐文件 GetFileInformationByHandleEx
    (FileStandardInfo) 同源同值；600B 驻留边界样本 align8 与批查一致。
    """
    sizes = [600, 601, 700, 1024, 2000, 3000, 4095]  # 段③主样本 + 600B 边界对照
    for size in sizes:
        (tmp_path / f"p{size}.bin").write_bytes(b"x" * size)
    batch = scanner._batch_directory_allocation(str(tmp_path))
    assert batch is not None
    for size in sizes:
        probe = tmp_path / f"p{size}.bin"
        st = probe.stat()
        record = batch.get(probe.name)
        assert record is not None, f"批查未命中：{probe.name}"
        handle_alloc = scanner._allocated_size(str(probe), st)
        assert handle_alloc is not None
        assert record[0] == handle_alloc, f"{size}B：批查 {record[0]} ≠ 句柄 {handle_alloc}"
        assert record[1] == st.st_file_attributes
    assert scanner._align8(600) == batch["p600.bin"][0]  # 驻留边界：align8 与批查一致


@pytest.mark.skipif(sys.platform != "win32", reason="批查 API 仅 Windows")
def test_batch_multi_call_continuation(tmp_path):
    """超过单次调用缓冲的目录：句柄续位枚举直至 ERROR_NO_MORE_FILES，整目录取全。"""
    for i in range(700):  # 700 条 × ~112B ≈ 78KB > 64KB 缓冲 → 至少两次系统调用
        (tmp_path / f"f{i:04d}.bin").write_bytes(b"x" * 700)
    batch = scanner._batch_directory_allocation(str(tmp_path))
    assert batch is not None
    assert len(batch) == 700  # 整目录条目一个不少（含非段③样本）
    probe = tmp_path / "f0300.bin"
    st = probe.stat()
    assert batch[probe.name][0] == scanner._allocated_size(str(probe), st)  # 抽样同源
