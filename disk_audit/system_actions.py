r"""系统交互白名单（待办 B3，任务卡 T4-05）——方案 U-4 的代码级落地。

依据：方案 U-4（"The system shall 仅通过白名单方式与系统交互：
explorer.exe /select,（定位文件）、ms-settings:appsfeatures（打开系统应用
列表）、写剪贴板；不调用任何安装/卸载可执行文件"）、方案 5.3（建议动作固定
5 种：A1 复制路径→剪贴板 / A2 打开所在文件夹→explorer /select, / A3 打开
系统应用列表→ms-settings:appsfeatures）、治理 §7 U-4 行（检查方式含 grep
门禁断言）、开发规范 §1（零第三方依赖、文案集中 texts.py）、任务卡 T4-05
（仅三能力、调用参数可注入、供 F4 消费）。

红线（模块级声明）：UninstallString 永不执行——本模块不构造、不拼接、不
调用任何安装/卸载可执行文件路径；"卸载相关"只经 A3（设置→应用）文字指引
用户自行操作。该红线由 tests/test_system_actions.py 固化：①产品代码任何
执行调用位置不得出现 UninstallString（grep + AST 双断言；数据采集/展示语境
出现为允许项）；②本模块字符串常量不含 UninstallString；③本模块不 import
subprocess/os（结构性排除子进程与 shell 出口）。

白名单语义（结构性越权防护）：
- 模块仅暴露三个能力函数（与 5.3 的 A1/A2/A3 一一对应），不存在通用
  "执行命令"入口；越权防护首先是结构性的；
- 全部 shell 交互收敛于唯一内部出口 _shell_execute：仅放行白名单常量表内的
  (file, params) 组合，其余一律 SystemActionRejected 拒绝并披露（中文文案
  取 texts.B3_TEXTS，含被拒目标与白名单边界）；
- 剪贴板仅写纯文本（CF_UNICODETEXT），不读剪贴板、不写其他格式。

实现方式（任务卡授权自决）：ShellExecuteW 经 ctypes 直调（与 launcher.py
GetDriveTypeW 同模式），不经 shell、不起 Python 子进程，无子进程治理面；
剪贴板经 ctypes user32/kernel32（零子进程零第三方）。

可注入点（任务卡"调用参数可注入便于测试"；供 F4/T4-07 消费）：
- executor：ShellExecuteW 替身，签名 (file, params) -> object；三个能力函数
  均经 ``executor=`` 注入，默认实现 _shell_execute_win 集中一处；
- writer：剪贴板写替身，签名 (text) -> None；copy_to_clipboard 经
  ``writer=`` 注入，默认实现 _write_clipboard_win32 集中一处。

本模块不接线 UI（F4/T4-07 消费）；launcher 现有 os.startfile 报告打开属 G3
范围（disk_audit.reports.open_report），不在本白名单收敛范围、不作改动。
"""
from __future__ import annotations

import ctypes
import time
from typing import Callable

from disk_audit.engine import texts

# 替身类型（供 F4/T4-07 的类型标注与测试注入）
ShellExecutor = Callable[[str, "str | None"], object]
ClipboardWriter = Callable[[str], None]

# 白名单常量（方案 U-4 / 5.3 定稿口径，禁止新增；修改须走方案变更流程）
_EXPLORER_FILE = "explorer.exe"
_SELECT_PARAM_PREFIX = "/select,"
_SETTINGS_FILE = "ms-settings:appsfeatures"

# Win32 常量
_SW_SHOWNORMAL = 1
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
# OpenClipboard 短暂被占用时的有限重试（剪贴板查看器/输入法等瞬时持有）
_OPEN_RETRY_TIMES = 5
_OPEN_RETRY_INTERVAL_SECONDS = 0.05


class SystemActionRejected(ValueError):
    """越权系统交互拒绝（U-4 白名单外目标）；中文披露文案取 texts.B3_TEXTS。"""


def _shell_execute(executor: ShellExecutor, file: str, params: str | None) -> object:
    """唯一 shell 出口：仅放行白名单常量表内的 (file, params) 组合（U-4）。

    越权目标在此拒绝并披露（SystemActionRejected），注入替身与真实实现都
    不会收到白名单外的任何调用——结构性防线，测试逐项断言。
    """
    allowed = (
        file == _EXPLORER_FILE
        and isinstance(params, str)
        and params.startswith(_SELECT_PARAM_PREFIX)
    ) or (file == _SETTINGS_FILE and params is None)
    if not allowed:
        target = f"{file} {params}".strip() if params else file
        raise SystemActionRejected(texts.B3_TEXTS["b3_err_rejected"].format(target=target))
    return executor(file, params)


def _shell_execute_win(file: str, params: str | None) -> object:
    """真实 ShellExecuteW（ctypes 直调，默认实现）：不经 shell、不起子进程。

    返回值语义（HINSTANCE > 32 为成功）由 Win32 约定给出，本模块不解释、
    不据此分支——三能力均为用户点击触发的火后不管交互（F4 接线语义）。
    """
    return ctypes.windll.shell32.ShellExecuteW(
        None, "open", file, params, None, _SW_SHOWNORMAL
    )


def _write_clipboard_win32(text: str) -> None:
    """真实剪贴板写入（ctypes user32/kernel32，默认实现）：零子进程零第三方。

    Win32 原型显式声明 argtypes/restype：句柄/指针为 64 位，ctypes 默认
    c_int 返回会截断（真实剪贴板冒烟实测抓到，2026-11-03）。
    CF_UNICODETEXT：UTF-16LE + 终结符写入可移动全局内存；SetClipboardData
    成功后内存所有权移交系统（此时不得 GlobalFree），失败路径回收句柄。
    任一失败抛 OSError（中文文案取 texts.B3_TEXTS），由调用方呈现。
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p  # HGLOBAL
    kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
    kernel32.GlobalLock.restype = ctypes.c_void_p  # LPVOID
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    user32.OpenClipboard.argtypes = (ctypes.c_void_p,)  # HWND
    user32.SetClipboardData.restype = ctypes.c_void_p  # HANDLE
    user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
    payload = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(payload))
    if not handle:
        raise OSError(texts.B3_TEXTS["b3_err_clipboard_alloc"])
    try:
        locked = kernel32.GlobalLock(handle)
        if not locked:
            raise OSError(texts.B3_TEXTS["b3_err_clipboard_lock"])
        try:
            ctypes.memmove(locked, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)
        for _ in range(_OPEN_RETRY_TIMES):
            if user32.OpenClipboard(None):
                break
            time.sleep(_OPEN_RETRY_INTERVAL_SECONDS)
        else:
            raise OSError(texts.B3_TEXTS["b3_err_clipboard_open"])
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
                raise OSError(texts.B3_TEXTS["b3_err_clipboard_set"])
            handle = None  # 所有权已移交剪贴板，禁止再 GlobalFree
        finally:
            user32.CloseClipboard()
    finally:
        if handle:
            kernel32.GlobalFree(handle)


def locate_in_explorer(path: str, *, executor: ShellExecutor | None = None) -> None:
    """A2 打开所在文件夹：explorer.exe /select,<path>（只定位，不打开文件）。

    空白路径拒绝（会退化为打开"文档"夹，属白名单外交互）并披露；
    executor 注入替身供测试与上层替换，默认 ctypes ShellExecuteW。
    """
    if not isinstance(path, str) or not path.strip():
        raise SystemActionRejected(texts.B3_TEXTS["b3_err_empty_path"])
    _shell_execute(
        executor if executor is not None else _shell_execute_win,
        _EXPLORER_FILE,
        _SELECT_PARAM_PREFIX + path,
    )


def open_apps_settings(*, executor: ShellExecutor | None = None) -> None:
    """A3 打开系统应用列表：ms-settings:appsfeatures（卸载指引的唯一出口）。"""
    _shell_execute(
        executor if executor is not None else _shell_execute_win,
        _SETTINGS_FILE,
        None,
    )


def copy_to_clipboard(text: str, *, writer: ClipboardWriter | None = None) -> None:
    """A1 复制路径：写剪贴板（CF_UNICODETEXT 纯文本）。

    writer 注入替身供测试与上层替换，默认 ctypes user32/kernel32 实现。
    """
    if writer is None:
        writer = _write_clipboard_win32
    writer(text)
