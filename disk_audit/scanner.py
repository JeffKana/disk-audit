"""文件枚举器：os.scandir + 8 线程前沿切分，双口径计量（逻辑大小 / 占用空间）。

依据：方案第四节"文件枚举"行与 P1（逻辑大小与占用空间双列，汇总一律用占用空间）；
W0 实测报告缺陷①修复——前沿切分必须补算"前沿之上"层级的文件，否则漏算根级大文件
（docs/upstream/poc/W0_POC实测报告_2026-10-23.html，全盘曾少算 14.76GB）；
X-1：权限不足/超长/占用/reparse point 一律跳过+计数+继续，不中断扫描。
约束：浅层切分 + 叶级单线程递归，禁止线程池内嵌套 submit（W0 实测死锁）；
流式聚合，不缓存全量条目；纯引擎、零 UI 依赖（待办 C2，任务卡 T-02）。
"""
from __future__ import annotations

import ctypes
import os
import stat as _stat
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

# Win32 FILE_ATTRIBUTE_REPARSE_POINT（Junction/符号链接等，跳过防循环）
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_LONG_PREFIX = "\\\\?\\"
_LONG_UNC_PREFIX = "\\\\?\\UNC\\"
# 路径达到该长度即加 \\?\ 前缀（POC v2 同款阈值，为 MAX_PATH 预留余量）
_LONG_PATH_THRESHOLD = 240
_DEFAULT_WORKERS = 8
_FRONTIER_MAX_DEPTH = 4

# 模块级间接层：供测试 monkeypatch 替换，不污染全局 os
_scandir = os.scandir

if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _create_file_w = _kernel32.CreateFileW
    _create_file_w.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    _create_file_w.restype = ctypes.c_void_p
    _get_file_information_by_handle_ex = _kernel32.GetFileInformationByHandleEx
    _get_file_information_by_handle_ex.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    _get_file_information_by_handle_ex.restype = ctypes.c_int
    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = [ctypes.c_void_p]
    _close_handle.restype = ctypes.c_int
else:
    # 非 Windows 开发环境降级：占用空间以逻辑大小代替（仅便于本地开发，验收在 Windows）
    _create_file_w = None

_FILE_READ_ATTRIBUTES = 0x0080
_FILE_SHARE_ALL = 0x00000007  # READ | WRITE | DELETE
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_STANDARD_INFO_CLASS = 1  # GetFileInformationByHandleEx → FileStandardInfo
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value if os.name == "nt" else 0


class _FILE_STANDARD_INFO(ctypes.Structure):
    """Win32 FILE_STANDARD_INFO（FileStandardInfo 类；字段对齐与 C 定义一致）。"""

    _fields_ = [
        ("AllocationSize", ctypes.c_int64),
        ("EndOfFile", ctypes.c_int64),
        ("NumberOfLinks", ctypes.c_uint32),
        ("DeletePending", ctypes.c_int8),
        ("Directory", ctypes.c_int8),
    ]


def _long_path(path: str) -> str:
    """超长路径加 \\\\?\\ 前缀（入参须为绝对路径）；UNC 路径改写为 \\\\?\\UNC\\ 形式。"""
    if path.startswith(_LONG_PREFIX):
        return path
    if path.startswith("\\\\"):
        return _LONG_UNC_PREFIX + path[2:]
    if len(path) >= _LONG_PATH_THRESHOLD:
        return _LONG_PREFIX + path
    return path


def _allocated_size(path: str, st: os.stat_result) -> int | None:
    """返回文件占用空间（磁盘分配字节数）；查询失败返回 None，由调用方按 X-1 处理。

    机制依据（2026-10-24 文档核实 + 本机实测）：GetCompressedFileSizeW 对未压缩、
    非稀疏文件返回的是逻辑大小（MSDN Remarks："the value obtained is the actual
    file size, the same as GetFileSize"），并非"占用空间"；与资源管理器
    "占用空间"同口径的是 GetFileInformationByHandleEx(FileStandardInfo)
    .AllocationSize（簇对齐分配量，MFT 驻留小文件返回其在 MFT 中的实占字节）。
    以 FILE_READ_ATTRIBUTES 打开（不取数据读权限），被占用的文件通常也可查询。
    """
    if _create_file_w is None:
        return st.st_size
    handle = _create_file_w(
        _long_path(path),
        _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        return None
    try:
        info = _FILE_STANDARD_INFO()
        ok = _get_file_information_by_handle_ex(
            handle, _FILE_STANDARD_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            return None
        return max(info.AllocationSize, 0)
    finally:
        _close_handle(handle)


@dataclass
class SkipStats:
    """X-1 跳过统计（对外披露，不静默吞掉——W0 报告 C6）。"""

    permission: int = 0  # 权限不足
    occupied: int = 0  # 文件被占用 / 占用空间查询失败
    too_long: int = 0  # 路径超长（\\?\ 前缀后仍超限）
    reparse: int = 0  # reparse point（Junction/符号链接）
    other: int = 0  # 其余 OSError（如条目在扫描间隙消失）

    def merge(self, other_stats: "SkipStats") -> None:
        self.permission += other_stats.permission
        self.occupied += other_stats.occupied
        self.too_long += other_stats.too_long
        self.reparse += other_stats.reparse
        self.other += other_stats.other

    @property
    def total(self) -> int:
        return self.permission + self.occupied + self.too_long + self.reparse + self.other


@dataclass
class ScanStats:
    """一次扫描的聚合结果（只有汇总值，不含任何条目缓存）。"""

    files: int = 0
    dirs: int = 0
    logical_bytes: int = 0
    allocated_bytes: int = 0
    skips: SkipStats = field(default_factory=SkipStats)

    def merge(self, other: "ScanStats") -> None:
        self.files += other.files
        self.dirs += other.dirs
        self.logical_bytes += other.logical_bytes
        self.allocated_bytes += other.allocated_bytes
        self.skips.merge(other.skips)


@dataclass
class ScanResult:
    root: str
    workers: int
    frontier_parts: int
    frontier_depth: int
    seconds: float
    stats: ScanStats

    def to_json_dict(self) -> dict:
        return {
            "root": self.root,
            "workers": self.workers,
            "seconds": round(self.seconds, 2),
            "frontier_parts": self.frontier_parts,
            "frontier_depth": self.frontier_depth,
            "files": self.stats.files,
            "dirs": self.stats.dirs,
            "entries": self.stats.files + self.stats.dirs,
            "logical_bytes": self.stats.logical_bytes,
            "allocated_bytes": self.stats.allocated_bytes,
            "skipped": {
                "permission": self.stats.skips.permission,
                "occupied": self.stats.skips.occupied,
                "too_long": self.stats.skips.too_long,
                "reparse": self.stats.skips.reparse,
                "other": self.stats.skips.other,
                "total": self.stats.skips.total,
            },
        }


def _classify_oserror(exc: OSError) -> str:
    """OSError → X-1 跳过分类名（对应 SkipStats 字段）。

    注意：Windows 的共享冲突（WinError 32/33）在 Python 中以 PermissionError
    形态出现，故先按 winerror/errno 分流到 occupied，再按 PermissionError
    归入 permission。
    """
    winerror = getattr(exc, "winerror", None)
    if winerror in (32, 33) or exc.errno in (32, 33):
        return "occupied"  # ERROR_SHARING_VIOLATION / ERROR_LOCK_VIOLATION
    if isinstance(exc, PermissionError):
        return "permission"
    if winerror == 206 or exc.errno == 36:  # 文件名或扩展名太长 / ENAMETOOLONG
        return "too_long"
    return "other"


def _count_skip(stats: ScanStats, exc: OSError) -> None:
    """按 X-1 分类计数一次跳过。"""
    category = _classify_oserror(exc)
    setattr(stats.skips, category, getattr(stats.skips, category) + 1)


def _reparse_or_symlink(st: os.stat_result) -> bool:
    if getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    return _stat.S_ISLNK(st.st_mode)


def _account_file(path: str, st: os.stat_result, stats: ScanStats) -> None:
    """文件计量：占用空间查询失败时整个文件按 X-1 计入 occupied（保证双口径一致）。"""
    allocated = _allocated_size(path, st)
    if allocated is None:
        stats.skips.occupied += 1
        return
    stats.files += 1
    stats.logical_bytes += st.st_size
    stats.allocated_bytes += allocated


def _handle_entry(entry: os.DirEntry, stats: ScanStats, subdirs: list[str]) -> None:
    """单个目录项统一处理：异常/reparse 按 X-1 计数，目录收集，文件即层计量。"""
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError as exc:
        _count_skip(stats, exc)
        return
    if _reparse_or_symlink(st):
        stats.skips.reparse += 1
        return
    if _stat.S_ISDIR(st.st_mode):
        subdirs.append(entry.path)
    else:
        _account_file(entry.path, st, stats)


def _open_dir(directory: str, stats: ScanStats):
    """打开目录枚举器；失败按 X-1 计数并返回 None。"""
    try:
        return _scandir(_long_path(directory))
    except OSError as exc:
        _count_skip(stats, exc)
        return None


def _expand_dir(directory: str, subdirs: list[str], stats: ScanStats) -> None:
    """BFS 展开一个目录：目录计数、其中文件即层统计（W0 缺陷①修复）、子目录收集。"""
    stats.dirs += 1
    iterator = _open_dir(directory, stats)
    if iterator is None:
        return
    with iterator:
        for entry in iterator:
            _handle_entry(entry, stats, subdirs)


def _build_frontier(
    root: str, min_parts: int, max_depth: int, stats: ScanStats
) -> tuple[list[str], int]:
    """BFS 切出前沿目录集合；返回（前沿目录列表, 深度）。

    与 POC v2（docs/upstream/poc/poc1_scan_bench_v2.py build_frontier）的差异：
    POC 展开各层时只收集子目录、丢掉文件，导致前沿之上层级的文件全部漏算
    （W0 缺陷①，全盘少算 14.76GB）。此处展开每层时同步统计该层文件，前沿为空
    表示全部内容已在 BFS 阶段统计完，无需并行阶段。
    """
    level = [root]
    depth = 0
    frontier = level
    while depth < max_depth:
        next_level: list[str] = []
        for directory in level:
            _expand_dir(directory, next_level, stats)
        if not next_level:
            frontier = []  # 该层已全部展开且无子目录：无剩余工作
            break
        level = next_level
        depth += 1
        frontier = level
        if len(level) >= min_parts:
            break
    return frontier, depth


def _scan_tree(root: str) -> ScanStats:
    """叶级单线程递归统计（栈式迭代避免递归深度问题）；每个前沿子树独立聚合。"""
    stats = ScanStats()
    stack = [root]
    while stack:
        current = stack.pop()
        stats.dirs += 1
        iterator = _open_dir(current, stats)
        if iterator is None:
            continue
        subdirs: list[str] = []
        with iterator:
            for entry in iterator:
                _handle_entry(entry, stats, subdirs)
        stack.extend(subdirs)
    return stats


def scan_path(root: str, workers: int = _DEFAULT_WORKERS) -> ScanResult:
    """扫描一个目录树，返回双口径汇总与跳过统计。

    线程模型（W0 实测定稿）：浅层 BFS 切分 + 每个前沿目录单线程递归，
    ThreadPoolExecutor.map 汇聚，全程无嵌套 submit。
    """
    if workers < 1:
        raise ValueError("workers 必须 ≥ 1")
    root_abs = os.path.abspath(os.path.expandvars(os.path.expanduser(root)))
    if not os.path.isdir(_long_path(root_abs)):
        raise ValueError(f"扫描根路径不存在或不是目录：{root_abs}")

    start = time.perf_counter()
    stats = ScanStats()
    frontier, depth = _build_frontier(
        root_abs, min_parts=workers * 3, max_depth=_FRONTIER_MAX_DEPTH, stats=stats
    )
    if frontier:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for part_stats in pool.map(_scan_tree, frontier):
                stats.merge(part_stats)
    return ScanResult(
        root=root_abs,
        workers=workers,
        frontier_parts=len(frontier),
        frontier_depth=depth,
        seconds=time.perf_counter() - start,
        stats=stats,
    )
