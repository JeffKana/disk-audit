"""文件枚举器：os.scandir + 8 线程前沿切分，双口径计量（逻辑大小 / 占用空间）。

依据：方案第四节"文件枚举"行与 P1（逻辑大小与占用空间双列，汇总一律用占用空间）；
DR-004（含 2026-10-25 修订节，三段分流：压缩/稀疏句柄实查、逻辑<簇 align8、
逻辑≥簇簇对齐，簇大小经 GetDiskFreeSpaceW 查询缓存）；
9.2（判定单元 = 扫描范围顶层目录及下钻子项，随遍历顺带聚合，D1 判定流水线消费）；
W0 实测报告缺陷①修复——前沿切分必须补算"前沿之上"层级的文件，否则漏算根级大文件
（docs/upstream/poc/W0_POC实测报告_2026-10-23.html，全盘曾少算 14.76GB）；
X-1：权限不足/超长/占用/reparse point 一律跳过+计数+继续，不中断扫描。
约束：浅层切分 + 叶级单线程递归，禁止线程池内嵌套 submit（W0 实测死锁）；
流式聚合，不缓存全量条目；纯引擎、零 UI 依赖（待办 C2，任务卡 T-02/T2-01）。
"""
from __future__ import annotations

import ctypes
import os
import stat as _stat
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial

# Win32 FILE_ATTRIBUTE_REPARSE_POINT（Junction/符号链接等，跳过防循环）
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
# Win32 FILE_ATTRIBUTE_COMPRESSED / FILE_ATTRIBUTE_SPARSE_FILE
# （DR-004 修订版三段分流①：含任一属性位 → 句柄实查占用空间）
_FILE_ATTRIBUTE_COMPRESSED = 0x800
_FILE_ATTRIBUTE_SPARSE_FILE = 0x200
_LONG_PREFIX = "\\\\?\\"
_LONG_UNC_PREFIX = "\\\\?\\UNC\\"
# 路径达到该长度即加 \\?\ 前缀（POC v2 同款阈值，为 MAX_PATH 预留余量）
_LONG_PATH_THRESHOLD = 240
_DEFAULT_WORKERS = 8
_FRONTIER_MAX_DEPTH = 4
# 判定单元下钻容器（9.2 + 原型 drill_programs/drill_packages 口径，大小写不敏感）
_CONTAINER_NAMES = frozenset({"programs", "packages"})

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
    # DR-004：簇大小经 GetDiskFreeSpaceW 查询一次并缓存（三段分流②③推算依据）
    _get_disk_free_space_w = _kernel32.GetDiskFreeSpaceW
    _get_disk_free_space_w.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    _get_disk_free_space_w.restype = ctypes.c_int
else:
    # 非 Windows 开发环境降级：占用空间以逻辑大小代替（仅便于本地开发，验收在 Windows）
    _create_file_w = None
    _get_disk_free_space_w = None

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


# 簇大小缓存：{盘符根小写: 字节数}（DR-004：GetDiskFreeSpaceW 查询一次并缓存）
_CLUSTER_DEFAULT = 4096
_CLUSTER_CACHE: dict[str, int] = {}


def _align8(size: int) -> int:
    """8 字节向上对齐（NTFS MFT 驻留小文件的实占口径，DR-004 修订版三段分流②）。"""
    return (size + 7) & ~7


def _cluster_bytes(path: str) -> int:
    """返回路径所在卷的簇大小（字节）；GetDiskFreeSpaceW 按盘符根查询并缓存，
    查询失败回退 4096（与 tools/check_size_deviation.py cluster_bytes_of 同口径）。"""
    if _get_disk_free_space_w is None:
        return _CLUSTER_DEFAULT
    drive = os.path.splitdrive(os.path.abspath(path))[0].lower() or "?"
    cached = _CLUSTER_CACHE.get(drive)
    if cached is not None:
        return cached
    sectors_per_cluster = ctypes.c_ulong()
    bytes_per_sector = ctypes.c_ulong()
    free_clusters = ctypes.c_ulong()
    total_clusters = ctypes.c_ulong()
    ok = _get_disk_free_space_w(
        drive + "\\",  # 盘符根，如 "C:\\"
        sectors_per_cluster,  # ctypes 实例直接传参，自动按 POINTER 转换
        bytes_per_sector,
        free_clusters,
        total_clusters,
    )
    if ok and sectors_per_cluster.value and bytes_per_sector.value:
        cluster = sectors_per_cluster.value * bytes_per_sector.value
    else:
        cluster = _CLUSTER_DEFAULT
    _CLUSTER_CACHE[drive] = cluster
    return cluster


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
class UnitStats:
    """判定单元聚合（9.2：顶层目录及下钻子项；文件级不单独计入）。

    随遍历顺带聚合（st 在 _handle_entry 已取得，零额外系统调用）；
    dirs 含单元目录自身；max_mtime 为单元子树内最新修改时间（陈旧度启发式输入）；
    exe_files 为 .exe 文件数（"无 exe"启发式输入）。并行段各自本地聚合后合并。
    """

    path: str
    files: int = 0
    dirs: int = 0
    logical_bytes: int = 0
    allocated_bytes: int = 0
    max_mtime: float = 0.0
    exe_files: int = 0

    def add_file(self, name: str, size: int, allocated: int, mtime: float) -> None:
        self.files += 1
        self.logical_bytes += size
        self.allocated_bytes += allocated
        self.note_mtime(mtime)
        if name.lower().endswith(".exe"):
            self.exe_files += 1

    def note_mtime(self, mtime: float) -> None:
        """仅更新最新修改时间（目录在"发现时"记 mtime，"展开时"才计 dirs，防双计）。"""
        if mtime > self.max_mtime:
            self.max_mtime = mtime

    def merge(self, other: "UnitStats") -> None:
        self.files += other.files
        self.dirs += other.dirs
        self.logical_bytes += other.logical_bytes
        self.allocated_bytes += other.allocated_bytes
        if other.max_mtime > self.max_mtime:
            self.max_mtime = other.max_mtime
        self.exe_files += other.exe_files

    def to_json_dict(self) -> dict:
        return {
            "path": self.path,
            "files": self.files,
            "dirs": self.dirs,
            "logical_bytes": self.logical_bytes,
            "allocated_bytes": self.allocated_bytes,
            "max_mtime": self.max_mtime,
            "exe_files": self.exe_files,
        }


@dataclass
class ScanStats:
    """一次扫描的聚合结果（双口径总量与跳过统计；单元级聚合另见 UnitStats）。"""

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
    units: list[UnitStats] = field(default_factory=list)
    incomplete: bool = False  # X-2：中止/异常统一"不完整"出口，totals 由该标记判无效

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
            "units": [u.to_json_dict() for u in self.units],
            "incomplete": self.incomplete,
        }


class _ScanAborted(Exception):
    """内部中止信号：abort_check 触发（X-2 统一"不完整"出口，不对外抛出）。"""


def _check_abort(abort_check) -> None:
    if abort_check is not None and abort_check():
        raise _ScanAborted


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


def _account_file(
    path: str, name: str, st: os.stat_result, stats: ScanStats, unit: UnitStats | None
) -> None:
    """文件计量（DR-004 修订版三段分流）：

    ① st_file_attributes 含压缩/稀疏 → 句柄实查（失败按 X-1 计入 occupied，
       双口径一致，语义与既有实现不变）；
    ② 逻辑 < 簇 → align8（MFT 驻留实占口径）；
    ③ 逻辑 ≥ 簇 → 簇对齐（GetDiskFreeSpaceW 查询并缓存簇大小）。
    非 Windows 开发降级不变（占用空间=逻辑大小，验收在 Windows）。
    """
    if _create_file_w is None:
        allocated = st.st_size
    else:
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & (_FILE_ATTRIBUTE_COMPRESSED | _FILE_ATTRIBUTE_SPARSE_FILE):
            allocated = _allocated_size(path, st)
            if allocated is None:
                stats.skips.occupied += 1
                return
        else:
            cluster = _cluster_bytes(path)
            if st.st_size < cluster:
                allocated = _align8(st.st_size)
            else:
                allocated = ((st.st_size + cluster - 1) // cluster) * cluster
    stats.files += 1
    stats.logical_bytes += st.st_size
    stats.allocated_bytes += allocated
    if unit is not None:
        unit.add_file(name, st.st_size, allocated, st.st_mtime)


def _enumerate_units(root_abs: str) -> dict[str, UnitStats]:
    """判定单元划分（9.2）：扫描根的每个顶层子目录为一个单元；顶层存在
    Programs/Packages 容器（大小写不敏感）时，其每个子目录亦为单元（对齐原型
    drill_programs/drill_packages 下钻一层口径）。reparse point 不作单元（X-1）。
    """
    units: dict[str, UnitStats] = {}
    containers: list[str] = []
    try:
        iterator = os.scandir(root_abs)
    except OSError:
        return units
    with iterator:
        for entry in iterator:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if _reparse_or_symlink(st) or not _stat.S_ISDIR(st.st_mode):
                continue
            units[entry.path] = UnitStats(path=entry.path)
            if entry.name.lower() in _CONTAINER_NAMES:
                containers.append(entry.path)
    for container in containers:
        try:
            sub_iterator = os.scandir(container)
        except OSError:
            continue
        with sub_iterator:
            for entry in sub_iterator:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if _reparse_or_symlink(st) or not _stat.S_ISDIR(st.st_mode):
                    continue
                units[entry.path] = UnitStats(path=entry.path)
    return units


def _sink_get(sink: dict[str, UnitStats], unit_path: str | None) -> UnitStats | None:
    """取单元聚合器：BFS 段 sink=共享 units（键必在）；并行段 sink=局部增量（按需建）。"""
    if unit_path is None:
        return None
    unit = sink.get(unit_path)
    if unit is None:
        unit = sink[unit_path] = UnitStats(path=unit_path)
    return unit


def _handle_entry(
    entry: os.DirEntry,
    stats: ScanStats,
    subdirs: list[tuple[str, str | None]],
    units: dict[str, UnitStats],
    sink: dict[str, UnitStats],
    parent_unit_path: str | None,
) -> None:
    """单个目录项统一处理：异常/reparse 按 X-1 计数，目录收集，文件即层计量。

    单元归属：文件归其所在目录的单元；目录的 mtime 归目录自身解析出的单元。
    units 只读（成员判定）；聚合写入走 sink（BFS 段=共享，并行段=局部增量）。
    """
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError as exc:
        _count_skip(stats, exc)
        return
    if _reparse_or_symlink(st):
        stats.skips.reparse += 1
        return
    if _stat.S_ISDIR(st.st_mode):
        unit_path = entry.path if entry.path in units else parent_unit_path
        subdirs.append((entry.path, unit_path))
        unit = _sink_get(sink, unit_path)
        if unit is not None:
            unit.note_mtime(st.st_mtime)  # 目录 mtime 在发现时记；dirs 在展开时计
    else:
        unit = _sink_get(sink, parent_unit_path)
        _account_file(entry.path, entry.name, st, stats, unit)


def _open_dir(directory: str, stats: ScanStats):
    """打开目录枚举器；失败按 X-1 计数并返回 None。"""
    try:
        return _scandir(_long_path(directory))
    except OSError as exc:
        _count_skip(stats, exc)
        return None


def _expand_dir(
    directory: str,
    subdirs: list[tuple[str, str | None]],
    stats: ScanStats,
    units: dict[str, UnitStats],
    sink: dict[str, UnitStats],
    parent_unit_path: str | None,
    abort_check=None,
) -> None:
    """BFS 展开一个目录：目录计数、其中文件即层统计（W0 缺陷①修复）、子目录收集。"""
    _check_abort(abort_check)
    stats.dirs += 1
    unit_path = directory if directory in units else parent_unit_path
    unit = _sink_get(sink, unit_path)
    if unit is not None:
        unit.dirs += 1  # 目录计数归展开时解析出的单元（含单元目录自身）
    iterator = _open_dir(directory, stats)
    if iterator is None:
        return
    with iterator:
        for entry in iterator:
            _handle_entry(entry, stats, subdirs, units, sink, unit_path)


def _build_frontier(
    root: str,
    min_parts: int,
    max_depth: int,
    stats: ScanStats,
    units: dict[str, UnitStats],
    abort_check=None,
) -> tuple[list[tuple[str, str | None]], int]:
    """BFS 切出前沿目录集合；返回（前沿目录与所属单元路径列表, 深度）。

    与 POC v2（docs/upstream/poc/poc1_scan_bench_v2.py build_frontier）的差异：
    POC 展开各层时只收集子目录、丢掉文件，导致前沿之上层级的文件全部漏算
    （W0 缺陷①，全盘少算 14.76GB）。此处展开每层时同步统计该层文件，前沿为空
    表示全部内容已在 BFS 阶段统计完，无需并行阶段。
    """
    level: list[tuple[str, str | None]] = [(root, None)]
    depth = 0
    frontier = level
    while depth < max_depth:
        next_level: list[tuple[str, str | None]] = []
        for directory, parent_unit_path in level:
            _expand_dir(directory, next_level, stats, units, units, parent_unit_path, abort_check)
        if not next_level:
            frontier = []  # 该层已全部展开且无子目录：无剩余工作
            break
        level = next_level
        depth += 1
        frontier = level
        if len(level) >= min_parts:
            break
    return frontier, depth


def _scan_tree(
    item: tuple[str, str | None],
    units: dict[str, UnitStats],
    abort_check=None,
) -> tuple[ScanStats, dict[str, UnitStats]]:
    """叶级单线程递归统计（栈式迭代避免递归深度问题）；每个前沿子树独立聚合。

    并行段不写共享 UnitStats：单元增量先记入本子树局部字典，由 scan_path
    在汇合时串行合并（多前沿可属同一单元，避免线程竞争）。
    """
    root, unit_hint = item
    stats = ScanStats()
    local_units: dict[str, UnitStats] = {}
    stack = [(root, unit_hint)]
    while stack:
        _check_abort(abort_check)
        current, parent_unit_path = stack.pop()
        stats.dirs += 1
        unit_path = current if current in units else parent_unit_path
        unit = _sink_get(local_units, unit_path)
        if unit is not None:
            unit.dirs += 1
        iterator = _open_dir(current, stats)
        if iterator is None:
            continue
        subdirs: list[tuple[str, str | None]] = []
        with iterator:
            for entry in iterator:
                _handle_entry(entry, stats, subdirs, units, local_units, unit_path)
        stack.extend(subdirs)
    return stats, local_units


def scan_path(
    root: str, workers: int = _DEFAULT_WORKERS, abort_check=None
) -> ScanResult:
    """扫描一个目录树，返回双口径汇总、跳过统计、判定单元聚合与完整性标记。

    线程模型（W0 实测定稿）：浅层 BFS 切分 + 每个前沿目录单线程递归，
    ThreadPoolExecutor.map 汇聚，全程无嵌套 submit。
    中止安全（X-2/C7）：abort_check 周期性轮询（每个目录展开前调用一次），
    返回 True 或抛 KeyboardInterrupt/任意异常 → 统一"不完整"出口：返回已采集
    部分并置 incomplete=True（totals 由该标记判无效），不抛出、不产生半成品结论。
    """
    if workers < 1:
        raise ValueError("workers 必须 ≥ 1")
    root_abs = os.path.abspath(os.path.expandvars(os.path.expanduser(root)))
    if not os.path.isdir(_long_path(root_abs)):
        raise ValueError(f"扫描根路径不存在或不是目录：{root_abs}")

    start = time.perf_counter()
    units = _enumerate_units(root_abs)
    stats = ScanStats()
    incomplete = False
    frontier: list[tuple[str, str | None]] = []
    depth = 0
    try:
        frontier, depth = _build_frontier(
            root_abs,
            min_parts=workers * 3,
            max_depth=_FRONTIER_MAX_DEPTH,
            stats=stats,
            units=units,
            abort_check=abort_check,
        )
        if frontier:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for part_stats, part_units in pool.map(
                    partial(_scan_tree, units=units, abort_check=abort_check), frontier
                ):
                    stats.merge(part_stats)
                    for unit_path, delta in part_units.items():
                        units[unit_path].merge(delta)
    except Exception:  # X-2：用户中止/异常统一"不完整"出口（细粒度失败仍由 X-1 披露）
        incomplete = True
    return ScanResult(
        root=root_abs,
        workers=workers,
        frontier_parts=len(frontier),
        frontier_depth=depth,
        seconds=time.perf_counter() - start,
        stats=stats,
        units=sorted(units.values(), key=lambda u: u.path),
        incomplete=incomplete,
    )
