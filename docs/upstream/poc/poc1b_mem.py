# -*- coding: utf-8 -*-
"""POC-1 补充：扫描过程峰值内存实测（流式聚合是否真的省内存）"""
import os, sys, ctypes, ctypes.wintypes as wt, time, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc1_scan_bench_v2 import scan_tree, run_parallel


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def peak_mb():
    p = PMC()
    p.cb = ctypes.sizeof(PMC)
    h = ctypes.windll.kernel32.GetCurrentProcess()
    fn = ctypes.windll.psapi.GetProcessMemoryInfo
    fn.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    fn.restype = wt.BOOL
    ok = fn(h, ctypes.byref(p), p.cb)
    if not ok:
        err = ctypes.get_last_error() or ctypes.windll.kernel32.GetLastError()
        return (-1.0, -1.0) if err else (-2.0, -2.0)
    return round(p.PeakWorkingSetSize / 1024 ** 2, 1), round(p.WorkingSetSize / 1024 ** 2, 1)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~\\AppData")
    base = peak_mb()
    t0 = time.perf_counter()
    c, dt, parts, depth = run_parallel(root, 8)
    after = peak_mb()
    print(json.dumps({
        "root": root, "workers": 8,
        "items": c.files + c.dirs, "seconds": round(dt, 2),
        "peak_ws_before_mb": base[0], "peak_ws_after_mb": after[0],
        "peak_ws_final_mb": after[1],
    }, ensure_ascii=False, indent=2))
