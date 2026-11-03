r"""T4-05（待办 B3）系统交互白名单模块测试。

依据：方案 U-4（仅通过白名单方式与系统交互：explorer.exe /select,、
ms-settings:appsfeatures、写剪贴板；不调用任何安装/卸载可执行文件）、
方案 5.3（A1 复制路径 / A2 打开所在文件夹 / A3 打开系统应用列表）、
治理 §7 U-4 行（grep 门禁断言可入 CI）、任务卡 T4-05 验收①②③。

测试纪律：三能力一律经注入替身断言调用参数，不真开 explorer / 设置面板 /
真实剪贴板（真实剪贴板冒烟在验收现场单独留档，不入 CI）；越权拒绝测试断言
替身从未被触达 + 中文披露文案；UninstallString 红线用 grep + AST 双断言
（数据采集/展示语境出现为允许项，执行调用位置出现即失败）。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from disk_audit import system_actions  # noqa: E402
from disk_audit.engine import texts  # noqa: E402

WHITELIST_MODULE = _REPO_ROOT / "disk_audit" / "system_actions.py"


class RecordingExecutor:
    """ShellExecuteW 替身：记录 (file, params) 调用对，返回哨兵值。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, file: str, params: str | None) -> object:
        self.calls.append((file, params))
        return 42  # ShellExecuteW 成功时返回 >32 的哨兵


class RecordingWriter:
    """剪贴板写替身：记录写入文本，不触碰真实剪贴板。"""

    def __init__(self) -> None:
        self.written: list[str] = []

    def __call__(self, text: str) -> None:
        self.written.append(text)


# ---------- 验收①：三能力各一参数断言单测（注入替身） ----------


def test_locate_in_explorer_uses_whitelisted_select_invocation():
    """A2 定位文件：explorer.exe /select,<path>（只定位，不打开文件）。"""
    executor = RecordingExecutor()
    system_actions.locate_in_explorer(
        r"C:\Users\样例\AppData\Local\某软件", executor=executor
    )
    assert executor.calls == [
        ("explorer.exe", "/select,C:\\Users\\样例\\AppData\\Local\\某软件")
    ]


def test_open_apps_settings_uses_whitelisted_target():
    """A3 打开系统应用列表：ms-settings:appsfeatures，无额外参数。"""
    executor = RecordingExecutor()
    system_actions.open_apps_settings(executor=executor)
    assert executor.calls == [("ms-settings:appsfeatures", None)]


def test_copy_to_clipboard_passes_text_to_writer():
    """A1 复制路径：文本原样交给剪贴板写入口（含中文与空格路径）。"""
    writer = RecordingWriter()
    system_actions.copy_to_clipboard(r"C:\Program Files\某软件\子目录", writer=writer)
    assert writer.written == [r"C:\Program Files\某软件\子目录"]


# ---------- 验收②：越权调用拒绝（拒绝并披露，替身零触达） ----------


@pytest.mark.parametrize(
    ("file", "params"),
    [
        ("cmd.exe", "/c echo hi"),  # 任意命令
        ("explorer.exe", "/e,C:\\x"),  # explorer 但参数非 /select, 白名单形态
        ("explorer.exe", None),  # explorer 必须携带 /select, 参数
        ("ms-settings:appsfeatures", "/c something"),  # settings 目标不允许参数
        ("uninstall.exe", "/quiet"),  # 装/卸载类可执行文件（U-4 明文禁区）
    ],
)
def test_shell_choke_point_rejects_non_whitelist_targets(file: str, params: str | None):
    """白名单唯一 shell 出口：非白名单 (file, params) → 拒绝 + 披露 + 替身零触达。"""
    executor = RecordingExecutor()
    with pytest.raises(system_actions.SystemActionRejected) as excinfo:
        system_actions._shell_execute(executor, file, params)
    assert executor.calls == []
    message = str(excinfo.value)
    assert "白名单" in message  # 披露：明确说出白名单边界
    assert file in message  # 披露：明确说出被拒目标
    assert message == texts.B3_TEXTS["b3_err_rejected"].format(
        target=f"{file} {params or ''}".strip()
    )


def test_locate_in_explorer_rejects_empty_path():
    """空路径不是合法的 /select 目标（会退化为打开文档夹）→ 拒绝并披露。"""
    executor = RecordingExecutor()
    with pytest.raises(system_actions.SystemActionRejected):
        system_actions.locate_in_explorer("   ", executor=executor)
    assert executor.calls == []


# ---------- 验收③：UninstallString 永不执行（grep + AST 断言） ----------

# 执行调用位置判定：以下函数名发起的调用视为"执行/派生外部程序"位置。
# 方案 U-4 允许 UninstallString 出现在数据采集（注册表 KEY_READ 值名）与
# 展示语境，故断言精确到执行调用位置而非全库禁词。
EXECUTION_FUNC_NAMES = frozenset(
    {
        "run", "runas", "Popen", "call", "check_call", "check_output", "system",
        "startfile", "ShellExecute", "ShellExecuteW", "ShellExecuteEx",
        "ShellExecuteExW", "WinExec", "CreateProcess", "CreateProcessW",
        "LoadLibrary", "LoadLibraryExW", "GetProcAddress", "exec", "execv",
        "execve", "spawn", "spawnv", "system",
    }
)

# grep 层：执行标记（大小写不敏感）——含 UninstallString 的行不得携带任何标记。
EXECUTION_LINE_MARKERS = (
    "subprocess", "os.system", "os.startfile", "Popen", "shellexecute",
    "winexec", "createprocess", "check_output", "check_call",
)


def _product_sources() -> list[tuple[Path, str]]:
    """产品代码 = disk_audit 包全部 .py + launcher.py（测试自身不在断言范围）。"""
    files = sorted((_REPO_ROOT / "disk_audit").rglob("*.py")) + [_REPO_ROOT / "launcher.py"]
    return [(path, path.read_text(encoding="utf-8")) for path in files]


def _normalized(token: str) -> str:
    """归一化比较：去下划线 + 小写，使 uninstall_string / UninstallString 等价。"""
    return token.replace("_", "").casefold()


def _call_func_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def _iter_call_tokens(node: ast.AST):
    """调用节点内的字符串常量与标识符（变量名也可携带可执行载荷的语义）。"""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child.value
        elif isinstance(child, ast.Name):
            yield child.id
        elif isinstance(child, ast.Attribute):
            yield child.attr


def test_no_uninstallstring_in_execution_call_positions():
    """AST 断言：产品代码任何执行调用位置不得出现 UninstallString（U-4 红线）。"""
    for path, source in _product_sources():
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_func_name(node) not in EXECUTION_FUNC_NAMES:
                continue
            for token in _iter_call_tokens(node):
                if "uninstallstring" in _normalized(token):
                    pytest.fail(
                        f"{path}: 执行调用位置出现 UninstallString（U-4：永不执行）"
                    )


def test_no_uninstallstring_on_execution_lines_grep():
    """grep 断言（治理 §7 U-4 行）：含 UninstallString 的产品代码行不得携带执行标记。"""
    for path, source in _product_sources():
        for lineno, line in enumerate(source.splitlines(), 1):
            if "uninstallstring" not in line.casefold():
                continue
            lowered = line.casefold()
            for marker in EXECUTION_LINE_MARKERS:
                assert marker not in lowered, (
                    f"{path}:{lineno}: UninstallString 与执行标记 '{marker}' 同行"
                )


def test_whitelist_module_string_constants_contain_no_uninstallstring():
    """白名单模块字符串常量不含 UninstallString 可执行路径。

    docstring 豁免（红线声明本身写在模块头，文档语境不构成可执行路径）；
    其余一切运行时字符串常量零容忍。
    """
    tree = ast.parse(WHITELIST_MODULE.read_text(encoding="utf-8"))
    docstring_constants: set[int] = set()
    for scope in ast.walk(tree):
        if isinstance(scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = scope.body[0] if scope.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstring_constants.add(id(first.value))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_constants
        ):
            assert "uninstallstring" not in _normalized(node.value), (
                f"{WHITELIST_MODULE}: 字符串常量出现 UninstallString（U-4：永不执行）"
            )


def test_whitelist_module_imports_no_process_spawn_modules():
    """结构性防线：白名单模块不 import subprocess / os（无子进程、无 shell 出口）。"""
    tree = ast.parse(WHITELIST_MODULE.read_text(encoding="utf-8"))
    forbidden_roots = {"subprocess", "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            roots = {(node.module or "").split(".")[0]}
        else:
            continue
        assert not (roots & forbidden_roots), (
            f"{WHITELIST_MODULE}: 出现禁用 import {sorted(roots & forbidden_roots)}"
        )


# ---------- 文案区块接线（B3_TEXTS append-only 区块） ----------


def test_b3_texts_block_exposes_disclosure_keys():
    """披露文案键齐备：越权拒绝 / 空路径 / 剪贴板三类失败出口。"""
    for key in (
        "b3_err_rejected",
        "b3_err_empty_path",
        "b3_err_clipboard_alloc",
        "b3_err_clipboard_open",
        "b3_err_clipboard_set",
    ):
        assert key in texts.B3_TEXTS, f"texts.B3_TEXTS 缺键：{key}"
        assert texts.B3_TEXTS[key].strip()
