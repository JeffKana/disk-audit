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
