r"""报告落盘、淘汰与打开（待办 G3，任务卡 T3-06）。

依据：方案四节架构⑤（报告渲染：静态 HTML · 默认浏览器打开）、M2 闸①
（双击到看到报告 ≤3 步）、U-2（程序自身仅在 %LOCALAPPDATA%\DiskAudit\ 内写
入——本模块为报告唯一写入位）、U-4（os.startfile 只读打开，不引入其他系统
交互）、任务卡实现约束（文件名含时间戳；旧报告按时间淘汰保留 12 份）。

设计：
- 落盘与淘汰为独立纯逻辑模块，路径根可注入（``reports_dir`` 参数，默认包内
  REPORTS_DIR 常量）供单测与测试替身替换，不新造路径逻辑；
- 文件名含时间戳：``report-YYYYmmdd-HHMMSS.html``，同秒冲突在扩展名前追加
  ``-N`` 序号，不覆盖既有报告；
- 淘汰按文件名时间序（基名字典序 + 序号）保留最新 keep=12 份，仅识别本模块
  命名模式的文件参与淘汰，其余文件一律不动（不扩大删除范围）；
- 写入前经 ``resolve_report_path`` 守卫：任何越界路径构造（相对上跳、子目录、
  绝对路径、双扩展名等）一律 ValueError 拒绝，不产生任何写入——U-2 验收②
  等效证据的代码层守卫（另有单测逐项断言）。
对外文案与异常提示集中在 texts.py G3_TEXTS 区块（开发规范 §1）。
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Callable

from disk_audit import REPORTS_DIR
from .engine import texts

# 报告文件名模式：report-YYYYmmdd-HHMMSS.html；同秒冲突为 report-...-N.html。
# 时间戳定长 + 字典序 = 时间序，是淘汰排序确定性的基础。
REPORT_NAME_RE = re.compile(r"^report-(\d{8}-\d{6})(?:-(\d+))?\.html$")

# 任务卡实现约束：旧报告按时间淘汰保留 12 份
DEFAULT_KEEP = 12

_HTML_EXT = ".html"


def report_filename(now: datetime | None = None) -> str:
    """生成含时间戳的报告文件名（时间来源可注入，保证测试确定性）。"""
    stamp = (now if now is not None else datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"report-{stamp}{_HTML_EXT}"


def resolve_report_path(directory: str, filename: str) -> str:
    """报告写路径守卫：文件名必须为本模块命名模式，且解析后必须落在 directory 之下。

    越界路径构造（``..\\`` 上跳、含子目录、绝对路径注入、双扩展名等）一律
    抛 ValueError（中文文案），调用前不产生任何文件系统写入（U-2）。
    """
    if REPORT_NAME_RE.fullmatch(filename) is None:
        raise ValueError(texts.G3_TEXTS["reports_err_bad_filename"].format(filename=filename))
    root = os.path.abspath(directory)
    target = os.path.abspath(os.path.join(root, filename))
    if os.path.dirname(target) != root:
        raise ValueError(texts.G3_TEXTS["reports_err_outside_dir"].format(target=target))
    return target


def _next_available(directory: str, filename: str) -> str:
    """同秒冲突时在扩展名前追加 -N 序号（N 从 1 起），不覆盖既有报告。"""
    if not os.path.exists(os.path.join(directory, filename)):
        return filename
    stem = filename[: -len(_HTML_EXT)]
    sequence = 1
    while os.path.exists(os.path.join(directory, f"{stem}-{sequence}{_HTML_EXT}")):
        sequence += 1
    return f"{stem}-{sequence}{_HTML_EXT}"


def save_report(
    html_text: str,
    *,
    reports_dir: str | None = None,
    now: datetime | None = None,
) -> str:
    """渲染后的 HTML → 落盘为带时间戳的报告文件，返回绝对路径。

    目录不存在则创建；本函数是报告的唯一写入点，写路径经
    ``resolve_report_path`` 守卫（U-2：仅 DATA_DIR\\reports\\ 或注入替身之下）。
    """
    directory = reports_dir if reports_dir is not None else REPORTS_DIR
    os.makedirs(directory, exist_ok=True)
    filename = _next_available(directory, report_filename(now))
    target = resolve_report_path(directory, filename)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(html_text)
    return target


def _sort_key(filename: str) -> tuple[str, int]:
    """文件名 → 排序键：(时间戳基名, 序号)。调用方已按 REPORT_NAME_RE 过滤。"""
    match = REPORT_NAME_RE.fullmatch(filename)
    stamp = match.group(1) if match else ""
    sequence = match.group(2) if match else None
    return (stamp, int(sequence) if sequence else 0)


def prune_reports(
    *,
    reports_dir: str | None = None,
    keep: int = DEFAULT_KEEP,
) -> list[str]:
    """按时间淘汰旧报告：保留最新 keep 份，返回被删除的文件名列表。

    仅本模块命名模式（report-*.html）的文件参与淘汰，其余文件不动；
    目录不存在或不足 keep 份时不做任何删除；keep 非正整数抛 ValueError。
    """
    if keep < 1:
        raise ValueError(texts.G3_TEXTS["reports_err_bad_keep"].format(keep=keep))
    directory = reports_dir if reports_dir is not None else REPORTS_DIR
    if not os.path.isdir(directory):
        return []
    names = [name for name in os.listdir(directory) if REPORT_NAME_RE.fullmatch(name)]
    names.sort(key=_sort_key)
    excess = names[:-keep] if len(names) > keep else []
    for name in excess:
        os.remove(os.path.join(directory, name))
    return excess


def open_report(path: str, *, opener: Callable[[str], object] | None = None) -> None:
    """默认浏览器打开报告（方案架构⑤）：默认 os.startfile 只读打开，opener 可注入。

    os.startfile 以系统默认关联程序打开 .html 文件；本程序不向其传参数、
    不注入脚本（U-4：白名单外不引入其他系统交互）。
    """
    if opener is None:
        opener = os.startfile  # type: ignore[assignment]  # Windows 专属标准库出口
    opener(path)
