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
C8/E-1：可选线程安全进度回调 progress_cb（已扫描条目数/当前路径/已用时，
双阈值节流 ≥500ms 或 2 万条目；回调异常按 X-1 计 other 不中断扫描；
None 默认零开销路径；UI 侧自行调度主线程——待办 C8，任务卡 T3-01）。
T3-08（任务卡 T4-08）：枚举段（迭代器 next() 段，_expand_dir/_scan_tree/
_enumerate_units 的 for entry in iterator 期间）OSError 一并折入 X-1
（跳过+计数+继续，已枚举条目保留、该目录未枚举部分放弃、不触发 X-2）；
X-2 统一"不完整"出口保留给真实中止（abort_check 命中）与非 OSError 致命
异常——VM AppX 服务窗口实时增删单元目录致首轮整体不完整的实证修复
（T2-09 首轮 4/4 incomplete、08 报告 §3 裁决 2）。计数复用 skips.other
（不动报告 JSON 键集，见 SkipStats.other 注释）。
T4-09（任务卡 T4-09）：段③（601B~<簇）取数机制改目录级批查——首个段③文件
命中时懒加载一次目录句柄批查（GetFileInformationByHandleEx +
FileIdExtdDirectoryInfo，class=0x13，一次调用带回整目录条目的
AllocationSize/EndOfFile/FileAttributes/文件名），_account_file 按文件名查
映射取值；映射未命中/批查失败/批查异常静默回退现行逐文件句柄实查（X-1
语义不变，不新创计数）；①压缩/稀疏、②≤600B align8、④≥簇 簇对齐三段路径
与双口径汇总口径不变（DR-004 裁决节勿重议）。枚举仍走 os.scandir（T3-08
折入语义与 C8 进度不变），批查数据仅供计量。
"""
from __future__ import annotations

import ctypes
import os
import stat as _stat
import struct
import threading
import time
from collections.abc import Callable
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

# C8/E-1 进度节流双阈值：距上次触发 ≥ 时间阈值 或 全局新增 ≥ 条目阈值 才触发回调。
# 时间阈值取 E-1 上限 500ms；条目阈值自决 2 万（万级）：Roaming 实测 ~24.2 万项/4.8s
# ≈ 5 万项/s，满速下 ≈0.4s 一触发，与时间阈值同量级，事件总量 ≈ 条目数/2万 + 时长×2。
# CHECK_STEP 为目录内逐条目探测步长（仅控制阈值探测频率——探测含锁，避免逐条目加锁
# 竞争；1024 项 ≈ 20ms@满速，慢速盘下时间阈值活性 ≤ 1024 项/盘速）。
_PROGRESS_MIN_INTERVAL = 0.5
_PROGRESS_ENTRY_STEP = 20000
_PROGRESS_CHECK_STEP = 1024

# 模块级间接层：供测试 monkeypatch 替换，不污染全局 os
_scandir = os.scandir
# 判定单元枚举独立间接层：与 _scandir 分离——各自供测试注入互不干扰，
# _enumerate_units 的调用序不计入 _scandir 夹具的调用计数（T4-08）
_units_scandir = os.scandir

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
# T4-09 段③批查：FileIdExtdDirectoryInfo = 0x13。MSDN FILE_ID_EXTD_DIR_INFO 页
# 明示"returned when FileIdExtdDirectoryInfo (0x13) or FileIdExtdDirectoryRestartInfo
# (0x14)"；本机 NTFS 实证（2026-11-05 探针，T4-09 执行记录留档）：class 19 一次
# 调用带回整目录条目且 AllocationSize 与逐文件 FileStandardInfo 逐文件一致（含
# 驻留边界样本 600B→600）；卡面提示"class 22"实证为 ERROR_INVALID_PARAMETER。
_FILE_ID_EXTD_DIRECTORY_INFO_CLASS = 19
_ERROR_NO_MORE_FILES = 18  # GetFileInformationByHandleEx 枚举结束错误码
_FILE_LIST_DIRECTORY = 0x0001  # 目录枚举类必需访问权（与 FILE_READ_ATTRIBUTES 并用）
_BATCH_BUFFER_BYTES = 65536  # 64KB 批查缓冲（实证 256KB 无续位调用次数收益）
# 批查缓冲线程局部复用：并行段每 worker 一块（~8×64KB），免去每目录 64KB
# 分配+清零（6.4 万段③目录 × ~3µs ≈ 0.2s GIL 串行开销）；缓冲内容即用即覆写，
# 跨句柄复用无 API 侧状态（GetFileInformationByHandleEx 只写不读调用方缓冲）
_BATCH_BUFFER_TLS = threading.local()


class _FILE_STANDARD_INFO(ctypes.Structure):
    """Win32 FILE_STANDARD_INFO（FileStandardInfo 类；字段对齐与 C 定义一致）。"""

    _fields_ = [
        ("AllocationSize", ctypes.c_int64),
        ("EndOfFile", ctypes.c_int64),
        ("NumberOfLinks", ctypes.c_uint32),
        ("DeletePending", ctypes.c_int8),
        ("Directory", ctypes.c_int8),
    ]


class _FILE_ID_EXTD_DIR_INFO(ctypes.Structure):
    """Win32 FILE_ID_EXTD_DIR_INFO（FileIdExtdDirectoryInfo 类，仅目录句柄）。

    变长结构：固定区 88 字节后跟 FileNameLength 字节的 UTF-16 文件名（无终止
    符），下一条目由 NextEntryOffset 定位（0 为末条目）。字段偏移经实证探针
    核对（2026-11-05，T4-09 执行记录留档）。解析热路径用 struct.unpack_from
    按同一偏移解包（实测 ~0.7µs/条 vs ctypes 结构体 ~1.3µs/条，Local 段③
    规模下省 ~0.4s），本结构体保留作布局定义与 FileName.offset 常量来源。
    """

    _fields_ = [
        ("NextEntryOffset", ctypes.c_uint32),
        ("FileIndex", ctypes.c_uint32),
        ("CreationTime", ctypes.c_int64),
        ("LastAccessTime", ctypes.c_int64),
        ("LastWriteTime", ctypes.c_int64),
        ("ChangeTime", ctypes.c_int64),
        ("EndOfFile", ctypes.c_int64),
        ("AllocationSize", ctypes.c_int64),
        ("FileAttributes", ctypes.c_uint32),
        ("FileNameLength", ctypes.c_uint32),
        ("EaSize", ctypes.c_uint32),
        ("ReparsePointTag", ctypes.c_uint32),
        ("FileId", ctypes.c_uint8 * 16),
        ("FileName", ctypes.c_wchar * 1),
    ]


# 解析格式串（packed，与 _FILE_ID_EXTD_DIR_INFO 字段偏移一致）：
# NextEntryOffset/FileIndex(2×I)、CreationTime..AllocationSize(6×q)、
# FileAttributes/FileNameLength/EaSize/ReparsePointTag(4×I)、FileId(16s)。
_EXTD_DIR_PACK_FMT = "<II6qIIII16s"
# 布局自证：固定区长度必须与结构体 FileName 偏移、格式串尺寸三方一致
# （任一方漂移在 import 时即失败，不静默错位解析）
assert (
    _FILE_ID_EXTD_DIR_INFO.FileName.offset
    == struct.calcsize(_EXTD_DIR_PACK_FMT)
    == 88
)


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

# DR-004 裁决节（2026-10-31）：600B 为本卷实测稳定 MFT 驻留上限（≤600B 样本
# align8 与句柄实查逐字节一致；新卷部署前先跑 tools/probe_resident_allocation.py
# 核对，偏离即触发 DR-004 重开条件）
_RESIDENT_LIMIT = 600


def _align8(size: int) -> int:
    """8 字节向上对齐（NTFS MFT 驻留小文件的实占口径，DR-004 裁决节②，≤600B 段）。"""
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


def _batch_directory_allocation(directory: str) -> dict[str, tuple[int, int]] | None:
    """目录级批查（T4-09 段③）：一次目录句柄 + FileIdExtdDirectoryInfo 枚举取回
    整目录条目，返回 {文件名: (AllocationSize, FileAttributes)}；任何失败返回
    None（调用方静默回退现行逐文件句柄实查，X-1 语义不变）。仅 Windows。

    机制依据（2026-11-05 MSDN 核实 + 本机 NTFS 实证探针，T4-09 执行记录留档）：
    FILE_ID_EXTD_DIR_INFO 由 FileIdExtdDirectoryInfo(0x13) / RestartInfo(0x14)
    触发（MSDN 结构体页明示）；目录枚举类需目录句柄带 FILE_LIST_DIRECTORY
    访问权；同句柄多次调用按内部续位返回后续条目，ERROR_NO_MORE_FILES(18)
    表示枚举结束，其余错误一律按批查失败整体降级（部分结果不作可用映射，
    逐文件回退兜底精确性）；"."/".." 不入映射。批查 AllocationSize 与逐文件
    FileStandardInfo 同源同值（实证含驻留边界样本 600B→600/601B→608）。
    失败回退静默（卡面实现约束：不自创新计数，occupied/other 语义按现行规则）。
    """
    if _create_file_w is None:
        return None
    handle = _create_file_w(
        _long_path(directory),
        _FILE_READ_ATTRIBUTES | _FILE_LIST_DIRECTORY,
        _FILE_SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        return None
    try:
        buf = getattr(_BATCH_BUFFER_TLS, "buf", None)
        if buf is None:
            buf = _BATCH_BUFFER_TLS.buf = ctypes.create_string_buffer(
                _BATCH_BUFFER_BYTES
            )
        base = ctypes.addressof(buf)
        name_offset = _FILE_ID_EXTD_DIR_INFO.FileName.offset
        result: dict[str, tuple[int, int]] = {}
        unpack_from = struct.unpack_from
        wstring_at = ctypes.wstring_at
        while True:
            ok = _get_file_information_by_handle_ex(
                handle, _FILE_ID_EXTD_DIRECTORY_INFO_CLASS, buf, _BATCH_BUFFER_BYTES
            )
            if not ok:
                if ctypes.get_last_error() == _ERROR_NO_MORE_FILES:
                    break
                return None
            offset = 0
            while True:
                (
                    next_offset, _file_index, _creation, _access, _write, _change,
                    _end_of_file, allocation, attributes, name_len,
                    _ea_size, _reparse_tag, _file_id,
                ) = unpack_from(_EXTD_DIR_PACK_FMT, buf, offset)
                if name_len:
                    name = wstring_at(base + offset + name_offset, name_len >> 1)
                    if name != "." and name != "..":
                        result[name] = (max(allocation, 0), attributes)
                if next_offset == 0:
                    break
                offset += next_offset
        return result
    finally:
        _close_handle(handle)


class _DirBatch:
    """目录批查懒加载持有者（T4-09 段③）：首个 601B~<簇 文件命中时才发起批查。

    懒加载动机：无段③文件的目录（纯小文件/大文件目录）零批查开销；有段③文件
    的目录整目录仅一次"开句柄+枚举"（对比逐文件每条一次句柄，DR-004 实测规模
    更正节：段③ Roaming 67,035 / Local 163,238 个 × ~30µs/句柄）。
    线程安全：持有者随目录迭代循环创建、仅该循环所属线程使用（并行段每 worker
    处理各自前沿子树），批查句柄即用即关，无跨线程共享。批查失败/异常静默
    降级为"无映射"——lookup 返回 None，_account_file 回退逐文件句柄（X-1
    语义不变）；结果缓存一次，目录迭代期内不重复批查。
    """

    __slots__ = ("_directory", "_map", "_loaded")

    def __init__(self, directory: str) -> None:
        self._directory = directory
        self._map: dict[str, tuple[int, int]] | None = None
        self._loaded = False

    def lookup(self, name: str) -> tuple[int, int] | None:
        """返回文件名对应的 (AllocationSize, FileAttributes)；未命中/失败为 None。"""
        if not self._loaded:
            self._loaded = True
            try:
                self._map = _batch_directory_allocation(self._directory)
            except Exception:  # X-1 族：批查异常静默降级，不中断扫描
                self._map = None
        if self._map is not None:
            return self._map.get(name)
        return None


@dataclass
class SkipStats:
    """X-1 跳过统计（对外披露，不静默吞掉——W0 报告 C6）。"""

    permission: int = 0  # 权限不足
    occupied: int = 0  # 文件被占用 / 占用空间查询失败
    too_long: int = 0  # 路径超长（\\?\ 前缀后仍超限）
    reparse: int = 0  # reparse point（Junction/符号链接）
    # 其余 OSError：条目在扫描间隙消失（stat 段）、枚举段目录抖动（T3-08：
    # 目录在 for entry in iterator 期间被外部删除/系统抖动致迭代句柄失效，
    # VM AppX 服务窗口实证场景）与回调异常（C8）等。不复用既有四类语义、
    # 不新增对外子类（保持 scan 产物 JSON skipped 键集稳定，T4-08 决策）。
    other: int = 0

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


@dataclass(frozen=True)
class ProgressEvent:
    """E-1 实时进度事件快照（待办 C8）：已扫描条目数 / 当前路径 / 已用时。

    frozen 只读：回调在工作线程触发（T3-05 UI 侧自行经 after() 调度主线程），
    事件对象跨线程传递无共享可变状态。entries 与 ScanResult.to_json_dict()
    ["entries"] 同口径（files+dirs 累计，跳过项不计入）。
    """

    entries: int  # 已扫描条目数（文件+目录累计）
    path: str  # 当前路径（最近处理的文件/目录）
    elapsed: float  # 已用时（秒，time.monotonic 口径）


class _ProgressTracker:
    """线程安全进度聚合器（C8/E-1）：各工作线程聚合本地计数，触发点加锁合并。

    无锁热路径：tick 只由各计数源自己的线程调用（BFS 段=主线程一个源，并行段=
    每个工作线程一个源），本地增量在触发探测点才入锁合并；双阈值（时间或条目）
    满足其一才触发回调。回调在锁内串行触发——保证回调观察到的 entries/elapsed
    单调不减（T3-05 消费前提）。回调异常按 X-1 捕获计入调用方 stats.skips.other
    （不中断扫描、不进 X-2）；progress_cb=None 时不实例化本类（零节流聚合计算）。
    """

    def __init__(self, callback: Callable[[ProgressEvent], None]) -> None:
        self._cb = callback
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._entries = 0  # 已合并的全局条目数
        self._fired_entries = 0  # 上次触发时的全局条目数
        self._last_fire = self._start
        # {id(stats): (stats 本体强引用, 上次已合并的本地计数)}——强引用防 id
        # 复用误配（并行段 part_stats 合并后被回收，地址可能被新任务复用）
        self._sources: dict[int, tuple[ScanStats, int]] = {}

    def tick(self, stats: ScanStats, path: str) -> None:
        """合并调用方本地增量并按双阈值触发回调（仅计数源属主线程调用）。"""
        local_total = stats.files + stats.dirs
        with self._lock:
            now = time.monotonic()  # 锁内取时：触发序=锁序 → elapsed 单调不减
            record = self._sources.get(id(stats))
            last = record[1] if record is not None and record[0] is stats else 0
            if local_total > last:
                self._entries += local_total - last
                self._sources[id(stats)] = (stats, local_total)
            if (
                now - self._last_fire < _PROGRESS_MIN_INTERVAL
                and self._entries - self._fired_entries < _PROGRESS_ENTRY_STEP
            ):
                return
            self._fired_entries = self._entries
            self._last_fire = now
            event = ProgressEvent(self._entries, path, now - self._start)
            try:
                self._cb(event)
            except Exception:  # X-1：回调异常计 other，不中断扫描
                stats.skips.other += 1

    def settle(self, stats: ScanStats) -> None:
        """结清一个计数源的尾差（scan_path 串行汇合点调用，不触发回调）。

        工作线程 tick 只合并到其最后一次探测为止，分片末尾未探测的增量在此
        结清，保证终态事件条目数精确。BFS 源在前沿切分完成后结清一次——此后
        并行段汇合直接 stats.merge 进全局 stats，不再经本跟踪器对全局记账
        （否则 worker 增量被双计）。
        """
        local_total = stats.files + stats.dirs
        with self._lock:
            record = self._sources.get(id(stats))
            last = record[1] if record is not None and record[0] is stats else 0
            if local_total > last:
                self._entries += local_total - last
                self._sources[id(stats)] = (stats, local_total)

    def finish(self, path: str, stats: ScanStats) -> None:
        """终态事件（不受节流）：汇报已合并的全局条目数；回调异常计 other。"""
        with self._lock:
            now = time.monotonic()
            self._fired_entries = self._entries
            self._last_fire = now
            event = ProgressEvent(self._entries, path, now - self._start)
            try:
                self._cb(event)
            except Exception:  # X-1：回调异常计 other，不中断扫描
                stats.skips.other += 1


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
    path: str,
    name: str,
    st: os.stat_result,
    stats: ScanStats,
    unit: UnitStats | None,
    batch: _DirBatch | None = None,
) -> None:
    """文件计量（DR-004 裁决节四段分流，2026-10-31）：

    ① st_file_attributes 含压缩/稀疏 → 句柄实查（路径不动）；
    ② 逻辑 ≤ 600B（_RESIDENT_LIMIT，本卷实测稳定驻留上限）→ align8（路径不动）；
    ③ 601B ≤ 逻辑 < 簇 → 目录级批查映射（T4-09：FileIdExtdDirectoryInfo 一次
       系统调用带回整目录 AllocationSize，_DirBatch 懒加载）；映射未命中/批查
       失败/批查异常 → 静默回退现行逐文件句柄实查（X-1 语义不变）；
    ④ 逻辑 ≥ 簇 → 簇对齐（GetDiskFreeSpaceW 查询并缓存簇大小，路径不动）。
    ①③ 实查失败按 X-1 计入 occupied（语义一致）；非 Windows 降级不变
    （占用空间=逻辑大小，验收在 Windows）。
    """
    if _create_file_w is None:
        allocated = st.st_size
    else:
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & (_FILE_ATTRIBUTE_COMPRESSED | _FILE_ATTRIBUTE_SPARSE_FILE):
            allocated = _allocated_size(path, st)
        elif st.st_size <= _RESIDENT_LIMIT:
            allocated = _align8(st.st_size)
        else:
            cluster = _cluster_bytes(path)
            if st.st_size < cluster:
                record = batch.lookup(name) if batch is not None else None
                allocated = (
                    record[0] if record is not None else _allocated_size(path, st)
                )
            else:
                allocated = ((st.st_size + cluster - 1) // cluster) * cluster
        if allocated is None:
            stats.skips.occupied += 1
            return
    stats.files += 1
    stats.logical_bytes += st.st_size
    stats.allocated_bytes += allocated
    if unit is not None:
        unit.add_file(name, st.st_size, allocated, st.st_mtime)


def _enumerate_units(root_abs: str, stats: ScanStats) -> dict[str, UnitStats]:
    """判定单元划分（9.2）：扫描根的每个顶层子目录为一个单元；顶层存在
    Programs/Packages 容器（大小写不敏感）时，其每个子目录亦为单元（对齐原型
    drill_programs/drill_packages 下钻一层口径）。reparse point 不作单元（X-1）。
    枚举段（迭代器 next() 段）OSError 按 X-1 折入（T3-08）——此处正是 T2-09
    实证的 Packages 容器枚举路径，AppX 服务窗口删容器内单元目录时迭代句柄
    失效抛 OSError；折入后已发现单元保留、未枚举部分放弃，扫描继续不进 X-2。
    """
    units: dict[str, UnitStats] = {}
    containers: list[str] = []
    try:
        iterator = _units_scandir(root_abs)
    except OSError:
        return units
    with iterator:
        try:
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
        except OSError as exc:  # 枚举段（next() 段）抖动：X-1 折入（T3-08）
            _count_skip(stats, exc)
    for container in containers:
        try:
            sub_iterator = _units_scandir(container)
        except OSError:
            continue
        with sub_iterator:
            try:
                for entry in sub_iterator:
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if _reparse_or_symlink(st) or not _stat.S_ISDIR(st.st_mode):
                        continue
                    units[entry.path] = UnitStats(path=entry.path)
            except OSError as exc:  # 枚举段（next() 段）抖动：X-1 折入（T3-08）
                _count_skip(stats, exc)
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
    batch: _DirBatch | None = None,
) -> None:
    """单个目录项统一处理：异常/reparse 按 X-1 计数，目录收集，文件即层计量。

    单元归属：文件归其所在目录的单元；目录的 mtime 归目录自身解析出的单元。
    units 只读（成员判定）；聚合写入走 sink（BFS 段=共享，并行段=局部增量）。
    batch（T4-09）：所在目录的段③批查懒加载持有者（None=禁用批查，段③直走
    逐文件句柄）。
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
        _account_file(entry.path, entry.name, st, stats, unit, batch)


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
    progress: _ProgressTracker | None = None,
) -> None:
    """BFS 展开一个目录：目录计数、其中文件即层统计（W0 缺陷①修复）、子目录收集。"""
    _check_abort(abort_check)
    stats.dirs += 1
    unit_path = directory if directory in units else parent_unit_path
    unit = _sink_get(sink, unit_path)
    if unit is not None:
        unit.dirs += 1  # 目录计数归展开时解析出的单元（含单元目录自身）
    if progress is not None:
        progress.tick(stats, directory)  # 目录边界探测（空目录树也保活，C8）
    iterator = _open_dir(directory, stats)
    if iterator is None:
        return
    batch = _DirBatch(directory)  # 段③批查懒加载（T4-09）：无段③文件零开销
    with iterator:
        seen = 0  # 目录内探测步长计数（C8：仅控制探测频率，非计量口径）
        try:
            for entry in iterator:
                _handle_entry(entry, stats, subdirs, units, sink, unit_path, batch)
                if progress is not None:
                    seen += 1
                    if seen >= _PROGRESS_CHECK_STEP:
                        seen = 0
                        progress.tick(stats, entry.path)
        except OSError as exc:
            # 枚举段（next() 段）OSError 折入 X-1（T3-08）：目录在枚举期间被
            # 外部删除/系统抖动致迭代句柄失效（VM AppX 服务窗口实证场景）——
            # 已枚举条目保留，该目录未枚举部分放弃，计数后继续扫描，不进 X-2。
            # 循环体内 stat/计量段已各自捕获，此处实际捕获迭代器 next() 段。
            _count_skip(stats, exc)


def _build_frontier(
    root: str,
    min_parts: int,
    max_depth: int,
    stats: ScanStats,
    units: dict[str, UnitStats],
    abort_check=None,
    progress: _ProgressTracker | None = None,
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
            _expand_dir(
                directory, next_level, stats, units, units, parent_unit_path,
                abort_check, progress,
            )
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
    progress: _ProgressTracker | None = None,
) -> tuple[ScanStats, dict[str, UnitStats]]:
    """叶级单线程递归统计（栈式迭代避免递归深度问题）；每个前沿子树独立聚合。

    并行段不写共享 UnitStats：单元增量先记入本子树局部字典，由 scan_path
    在汇合时串行合并（多前沿可属同一单元，避免线程竞争）。
    进度（C8）：本函数的 stats 为本工作线程私有计数源，tick 只合并自身增量。
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
        if progress is not None:
            progress.tick(stats, current)  # 目录边界探测（C8）
        iterator = _open_dir(current, stats)
        if iterator is None:
            continue
        subdirs: list[tuple[str, str | None]] = []
        batch = _DirBatch(current)  # 段③批查懒加载（T4-09）：无段③文件零开销
        seen = 0  # 目录内探测步长计数（C8：仅控制探测频率，非计量口径）
        with iterator:
            try:
                for entry in iterator:
                    _handle_entry(entry, stats, subdirs, units, local_units, unit_path, batch)
                    if progress is not None:
                        seen += 1
                        if seen >= _PROGRESS_CHECK_STEP:
                            seen = 0
                            progress.tick(stats, entry.path)
            except OSError as exc:
                # 枚举段（next() 段）OSError 折入 X-1（T3-08，同 _expand_dir）：
                # 已枚举条目与已收集子目录保留，该目录未枚举部分放弃，
                # 计数后继续扫描，不进 X-2。
                _count_skip(stats, exc)
        stack.extend(subdirs)
    return stats, local_units


def scan_path(
    root: str,
    workers: int = _DEFAULT_WORKERS,
    abort_check=None,
    progress_cb: Callable[[ProgressEvent], None] | None = None,
) -> ScanResult:
    """扫描一个目录树，返回双口径汇总、跳过统计、判定单元聚合与完整性标记。

    线程模型（W0 实测定稿）：浅层 BFS 切分 + 每个前沿目录单线程递归，
    ThreadPoolExecutor.map 汇聚，全程无嵌套 submit。
    中止安全（X-2/C7）：abort_check 周期性轮询（每个目录展开前调用一次），
    返回 True 或抛 KeyboardInterrupt/任意异常 → 统一"不完整"出口：返回已采集
    部分并置 incomplete=True（totals 由该标记判无效），不抛出、不产生半成品结论。
    进度回调（C8/E-1）：progress_cb 非 None 时，工作线程以 ProgressEvent
    （entries=已扫描条目数、path=当前路径、elapsed=已用时秒）通知进度，
    双阈值节流（距上次触发 ≥500ms 或全局新增 ≥2 万条目，刷新 ≤500ms）；
    回调在工作线程触发（零 UI 依赖，UI 侧自行调度主线程，T3-05），锁内串行
    触发保证 entries/elapsed 单调不减；回调异常按 X-1 计 skips.other 不中断
    扫描（abort_check 命中仍走 X-2 既有出口，优先级高于进度触发）；扫描结束
    （含中止）追加一次不受节流的终态事件。progress_cb=None（默认）为零开销
    路径：不做任何节流聚合计算。
    """
    if workers < 1:
        raise ValueError("workers 必须 ≥ 1")
    root_abs = os.path.abspath(os.path.expandvars(os.path.expanduser(root)))
    if not os.path.isdir(_long_path(root_abs)):
        raise ValueError(f"扫描根路径不存在或不是目录：{root_abs}")

    start = time.perf_counter()
    stats = ScanStats()  # 先于单元枚举创建：枚举段折入计数也汇入本 stats（T3-08）
    units = _enumerate_units(root_abs, stats)
    incomplete = False
    frontier: list[tuple[str, str | None]] = []
    depth = 0
    progress = None if progress_cb is None else _ProgressTracker(progress_cb)
    try:
        frontier, depth = _build_frontier(
            root_abs,
            min_parts=workers * 3,
            max_depth=_FRONTIER_MAX_DEPTH,
            stats=stats,
            units=units,
            abort_check=abort_check,
            progress=progress,
        )
        if progress is not None:
            progress.settle(stats)  # 结清 BFS 段尾差（并行段汇合不再对全局记账）
        if frontier:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for part_stats, part_units in pool.map(
                    partial(
                        _scan_tree, units=units, abort_check=abort_check, progress=progress
                    ),
                    frontier,
                ):
                    stats.merge(part_stats)
                    for unit_path, delta in part_units.items():
                        units[unit_path].merge(delta)
                    if progress is not None:
                        progress.settle(part_stats)  # 结清该分片未探测的尾差
    except Exception:  # X-2：用户中止/异常统一"不完整"出口（细粒度失败仍由 X-1 披露）
        incomplete = True
    if progress is not None:
        progress.finish(root_abs, stats)  # 终态事件（不受节流，C8）
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
