# -*- coding: utf-8 -*-
"""POC-1: 全盘/目录枚举性能实测
对比三种模式：单线程 scandir / 线程池 8 / 线程池 16
只做元数据统计（条目数、总字节、权限失败数、reparse 跳过数），不读文件内容、不落盘。
"""
import os, sys, time, json, stat, threading
from concurrent.futures import ThreadPoolExecutor

LONG = "\\\\?\\"


def safe_path(p: str) -> str:
    if p.startswith("\\\\?\\"):
        return p
    if len(p) >= 240:
        return LONG + p
    return p


class Counter:
    __slots__ = ("files", "dirs", "size", "denied", "reparse", "max_depth")

    def __init__(self):
        self.files = 0
        self.dirs = 0
        self.size = 0
        self.denied = 0
        self.reparse = 0
        self.max_depth = 0

    def add(self, other, depth=0):
        self.files += other.files
        self.dirs += other.dirs
        self.size += other.size
        self.denied += other.denied
        self.reparse += other.reparse
        if other.max_depth + depth > self.max_depth:
            self.max_depth = other.max_depth + depth


FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def scan_dir(path: str, depth: int = 0) -> Counter:
    """递归统计；跳过 reparse point（Junction/Symlink），避免循环与重复计数。"""
    c = Counter()
    try:
        with os.scandir(safe_path(path)) as it:
            subdirs = []
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    c.denied += 1
                    continue
                if st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    c.reparse += 1
                    continue
                if stat.S_ISDIR(st.st_mode):
                    c.dirs += 1
                    subdirs.append(e.path)
                else:
                    c.files += 1
                    c.size += st.st_size
            for sd in subdirs:
                child = scan_dir(sd, depth + 1)
                c.add(child, 1)
    except (PermissionError, OSError):
        c.denied += 1
    return c


def scan_dir_threaded(path: str, depth: int, pool: ThreadPoolExecutor) -> Counter:
    c = Counter()
    try:
        with os.scandir(safe_path(path)) as it:
            subdirs = []
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    c.denied += 1
                    continue
                if st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    c.reparse += 1
                    continue
                if stat.S_ISDIR(st.st_mode):
                    c.dirs += 1
                    subdirs.append(e.path)
                else:
                    c.files += 1
                    c.size += st.st_size
            if len(subdirs) > 8:
                futs = [pool.submit(scan_dir_threaded, sd, depth + 1, pool) for sd in subdirs]
                for f in futs:
                    c.add(f.result(), 1)
            else:
                for sd in subdirs:
                    c.add(scan_dir_threaded(sd, depth + 1, pool), 1)
    except (PermissionError, OSError):
        c.denied += 1
    return c


def run(root: str, mode: str, threads: int = 1):
    t0 = time.perf_counter()
    if mode == "single":
        c = scan_dir(root)
    else:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            c = scan_dir_threaded(root, 0, pool)
    dt = time.perf_counter() - t0
    total_items = c.files + c.dirs
    return {
        "root": root, "mode": mode, "threads": threads,
        "seconds": round(dt, 2),
        "files": c.files, "dirs": c.dirs, "items": total_items,
        "size_gb": round(c.size / 1024**3, 2),
        "denied": c.denied, "reparse_skipped": c.reparse,
        "items_per_sec": int(total_items / dt) if dt > 0 else 0,
    }


if __name__ == "__main__":
    roots = sys.argv[1:] or [os.path.expanduser("~\\AppData"), "C:\\"]
    out = []
    for root in roots:
        if not os.path.isdir(root):
            print("SKIP not found:", root, flush=True)
            continue
        print("==== ", root, flush=True)
        modes = [("single", 1)] if root == "C:\\" else [("single", 1), ("thread", 8), ("thread", 16)]
        for mode, th in modes:
            r = run(root, mode, th)
            out.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc1_result.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("DONE")
