# -*- coding: utf-8 -*-
"""POC-1: 全盘/目录枚举性能实测（v2，修正线程池递归死锁）

v1 教训：worker 内部向同一个有界线程池 submit 子任务并 .result() 等待，
        8 个 worker 全部阻塞在等待上 → 池内无空闲 worker 执行新任务 → 死锁。
v2 做法：先切出"浅层前沿目录集合"，再对每个前沿目录用单线程递归，
        由线程池并行 map。全程不发生嵌套 submit。
"""
import os, sys, time, json, stat
from concurrent.futures import ThreadPoolExecutor

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
LONG = "\\\\?\\"


def safe_path(p: str) -> str:
    if p.startswith(LONG):
        return p
    return LONG + p if len(p) >= 240 else p


class C:
    __slots__ = ("files", "dirs", "size", "denied", "reparse")

    def __init__(self):
        self.files = self.dirs = self.size = self.denied = self.reparse = 0

    def add(self, o):
        self.files += o.files
        self.dirs += o.dirs
        self.size += o.size
        self.denied += o.denied
        self.reparse += o.reparse


def scan_tree(path: str) -> C:
    """单线程递归统计（栈式，避免递归深度问题）。"""
    c = C()
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(safe_path(cur)) as it:
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
                        stack.append(e.path)
                    else:
                        c.files += 1
                        c.size += st.st_size
        except (PermissionError, OSError):
            c.denied += 1
    return c


def list_children(path):
    out = []
    try:
        with os.scandir(safe_path(path)) as it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    out.append(e.path)
    except (PermissionError, OSError):
        pass
    return out


def build_frontier(root: str, min_parts: int, max_depth: int = 4):
    """BFS 展开到"前沿目录"数量 >= min_parts，返回该层目录列表。"""
    level = [root]
    depth = 0
    while depth < max_depth:
        nxt = []
        for d in level:
            nxt.extend(list_children(d))
        if not nxt:
            break
        level = nxt
        depth += 1
        if len(level) >= min_parts:
            break
    return level, depth


def run_single(root):
    t0 = time.perf_counter()
    c = scan_tree(root)
    return c, time.perf_counter() - t0, 0, 0


def run_parallel(root, workers):
    t0 = time.perf_counter()
    parts, depth = build_frontier(root, min_parts=workers * 3)
    total = C()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for sub in pool.map(scan_tree, parts):
            total.add(sub)
    # 前沿之上的目录数与文件数（很浅，代价可忽略）
    return total, time.perf_counter() - t0, len(parts), depth


def pack(root, mode, workers, c, dt, parts=0, depth=0, extra_dirs=0):
    items = c.files + c.dirs + extra_dirs
    return {
        "root": root, "mode": mode, "workers": workers,
        "seconds": round(dt, 2), "items": items,
        "files": c.files, "dirs": c.dirs,
        "size_gb": round(c.size / 1024 ** 3, 2),
        "denied": c.denied, "reparse_skipped": c.reparse,
        "items_per_sec": int(items / dt) if dt > 0 else 0,
        "frontier_parts": parts, "frontier_depth": depth,
    }


if __name__ == "__main__":
    roots = sys.argv[1:] or [os.path.expanduser("~\\AppData"), "C:\\"]
    out = []
    for root in roots:
        if not os.path.isdir(root):
            print("SKIP:", root, flush=True)
            continue
        print("==== ", root, flush=True)
        # 单线程基准
        c, dt, _, _ = run_single(root)
        r = pack(root, "single", 1, c, dt)
        out.append(r); print(json.dumps(r, ensure_ascii=False), flush=True)
        # 并行
        for w in (8, 16):
            c, dt, parts, depth = run_parallel(root, w)
            r = pack(root, "frontier", w, c, dt, parts, depth)
            out.append(r); print(json.dumps(r, ensure_ascii=False), flush=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc1_result.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("DONE")
