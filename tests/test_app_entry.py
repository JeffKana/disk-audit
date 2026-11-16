"""冻结程序统一入口路由测试（T7-01-A / DR-019，行为矩阵见 docs/evidence/T7-01-A）。

路由冻结：空参数→launcher.main(副本)；首 token 精确 --elevated-rescan 或
--elevated-rescan= 前缀→launcher.main(原样副本)；其它非空→disk_audit.__main__.main(副本)。
GUI/admin 后端一律替身（不真实 Tk/UAC/盘型探测/扫描/用户数据）；CLI 分支另以新鲜
子进程 + 导入禁令实证无 launcher/tkinter。透传用自定义 BaseException 子类，禁真
KeyboardInterrupt 外泄（开发规范与卡面标准 2）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import disk_audit_app
import launcher
from disk_audit import __main__ as cli_backend

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_PATH = REPO_ROOT / "disk_audit_app.py"


class _RecordingBackend:
    """记录调用实参的后端替身；可配置返回码或注入异常。"""

    def __init__(self, result: int = 0, exc: BaseException | None = None) -> None:
        self.calls: list[list[str]] = []
        self._result = result
        self._exc = exc

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(argv)
        if self._exc is not None:
            raise self._exc
        return self._result


class _CustomBaseExit(BaseException):
    """自定义 BaseException 子类：证明 BaseException 透传，不用真 KeyboardInterrupt。"""


def _utf8_env() -> dict[str, str]:
    """子进程环境：PYTHONUTF8=1 对齐 CI，避免中文输出 cp1252 假红。"""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return env


def _run_py(args: list[str], cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        env=_utf8_env(), timeout=120,
    )


# ---------- 一、路由矩阵（后端替身） ----------


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--elevated-rescan"],
        ["--elevated-rescan=x"],
        ["--elevated-rescan="],
        ["--elevated-rescan", "--selftest"],
    ],
)
def test_gui_admin_routes_to_launcher(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    stub = _RecordingBackend(result=7)
    monkeypatch.setattr(launcher, "main", stub)
    monkeypatch.setattr(
        cli_backend, "main", lambda a: pytest.fail("GUI/admin 分支不得进入 CLI 后端")
    )
    original = list(argv)
    assert disk_audit_app.main(argv) == 7
    assert stub.calls == [original]
    assert stub.calls[0] is not argv  # 副本语义：不改调用者列表
    assert argv == original


@pytest.mark.parametrize(
    "argv",
    [
        ["--selftest"],
        ["--version"],
        ["--help"],
        ["-h"],
        ["scan", r"C:\sample\dir", "--workers", "4"],
        ["judge", "scan.json"],
        ["render", "report.json"],
        ["export-csv", "report.json", "--raw"],
        ["--unknown-option"],
        ["--selftest", "--elevated-rescan"],
        ["--elevated-rescans"],
        ["--elevated-rescanx"],
    ],
)
def test_cli_routes_to_engine(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    stub = _RecordingBackend(result=5)
    monkeypatch.setattr(cli_backend, "main", stub)
    monkeypatch.setattr(
        launcher, "main", lambda a: pytest.fail("CLI 分支不得进入 launcher 后端")
    )
    original = list(argv)
    assert disk_audit_app.main(argv) == 5
    assert stub.calls == [original]
    assert stub.calls[0] is not argv
    assert argv == original


def test_argv_none_empty_routes_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["disk_audit_app.py"])
    stub = _RecordingBackend(result=7)
    monkeypatch.setattr(launcher, "main", stub)
    monkeypatch.setattr(cli_backend, "main", lambda a: pytest.fail("空参数不得进入 CLI"))
    assert disk_audit_app.main() == 7  # 默认 argv=None
    assert stub.calls == [[]]


def test_argv_none_nonempty_routes_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["disk_audit_app.py", "--selftest"])
    stub = _RecordingBackend(result=5)
    monkeypatch.setattr(cli_backend, "main", stub)
    monkeypatch.setattr(launcher, "main", lambda a: pytest.fail("非空参数不得进入 launcher"))
    assert disk_audit_app.main(None) == 5
    assert stub.calls == [["--selftest"]]


def test_argv_none_does_not_mutate_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ["disk_audit_app.py", "--selftest"]
    monkeypatch.setattr(sys, "argv", fake)
    monkeypatch.setattr(cli_backend, "main", _RecordingBackend(result=0))
    disk_audit_app.main(None)
    assert sys.argv is fake
    assert fake == ["disk_audit_app.py", "--selftest"]


# ---------- 二、真实旧解析器拒绝（不落回 GUI、不进提权分支） ----------


@pytest.mark.parametrize(
    "argv",
    [["--elevated-rescan=x"], ["--elevated-rescan="], ["--elevated-rescan", "--selftest"]],
)
def test_admin_malformed_rejected_by_legacy_parser(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    monkeypatch.setattr(
        launcher, "run", lambda **kw: pytest.fail("畸形 admin 参数不得落回 GUI")
    )
    monkeypatch.setattr(
        launcher, "_cmd_elevated_rescan", lambda: pytest.fail("畸形 admin 参数不得进提权分支")
    )
    with pytest.raises(SystemExit) as ei:
        disk_audit_app.main(argv)
    assert ei.value.code == 2


def test_exact_admin_flag_reaches_admin_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_cmd_elevated_rescan", lambda: 4)
    monkeypatch.setattr(
        launcher, "run", lambda **kw: pytest.fail("精确 admin 标记不得进 GUI")
    )
    assert disk_audit_app.main(["--elevated-rescan"]) == 4


def test_empty_args_reaches_gui_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "run", lambda **kw: 0)
    monkeypatch.setattr(
        launcher, "_cmd_elevated_rescan", lambda: pytest.fail("空参数不得进提权分支")
    )
    assert disk_audit_app.main([]) == 0


def test_mixed_cli_order_rejected_without_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        launcher, "run", lambda **kw: pytest.fail("CLI 拒绝不得落回 GUI")
    )
    with pytest.raises(SystemExit) as ei:
        disk_audit_app.main(["--selftest", "--elevated-rescan"])
    assert ei.value.code == 2


# ---------- 三、透传矩阵 ----------


@pytest.mark.parametrize("code", [0, 3, 4, 5, 33])
def test_cli_return_code_passthrough(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    monkeypatch.setattr(cli_backend, "main", lambda a: code)
    assert disk_audit_app.main(["--selftest"]) == code


@pytest.mark.parametrize("code", [0, 3])
def test_launcher_return_code_passthrough(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    monkeypatch.setattr(launcher, "main", lambda a: code)
    assert disk_audit_app.main([]) == code


def test_cli_exception_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_backend, "main", _RecordingBackend(exc=ValueError("后端异常")))
    with pytest.raises(ValueError, match="后端异常"):
        disk_audit_app.main(["--selftest"])


def test_launcher_exception_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "main", _RecordingBackend(exc=RuntimeError("启动器异常")))
    with pytest.raises(RuntimeError, match="启动器异常"):
        disk_audit_app.main([])


def test_systemexit_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_backend, "main", _RecordingBackend(exc=SystemExit(2)))
    with pytest.raises(SystemExit) as ei:
        disk_audit_app.main(["--unknown-option"])
    assert ei.value.code == 2


def test_custom_baseexception_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_backend, "main", _RecordingBackend(exc=_CustomBaseExit("自定义")))
    with pytest.raises(_CustomBaseExit, match="自定义"):
        disk_audit_app.main(["--selftest"])


# ---------- 四、导入隔离与新鲜子进程实跑 ----------


def test_module_import_pulls_no_backends() -> None:
    code = (
        "import sys, disk_audit_app; "
        "bad = [m for m in ('launcher', 'tkinter', '_tkinter', 'disk_audit', "
        "'disk_audit.__main__') if m in sys.modules]; "
        "assert bad == [], bad; print('import-purity-ok')"
    )
    proc = _run_py([sys.executable, "-c", code])
    assert proc.returncode == 0, proc.stderr
    assert "import-purity-ok" in proc.stdout


_DRIVER_SOURCE = """\
import json
import runpy
import sys
from pathlib import Path

FORBIDDEN_ROOTS = {"launcher", "tkinter", "_tkinter"}


class _ImportBan:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in FORBIDDEN_ROOTS:
            raise ImportError("导入禁令命中: " + fullname)
        return None


sys.meta_path.insert(0, _ImportBan())
entry = sys.argv[1]
product_args = sys.argv[2:]
sys.path.insert(0, str(Path(entry).resolve().parent))
sys.argv = [entry, *product_args]
exit_code = "no-exit"
try:
    runpy.run_path(entry, run_name="__main__")
except SystemExit as exc:
    exit_code = exc.code
forbidden = sorted(m for m in sys.modules if m.split(".", 1)[0] in FORBIDDEN_ROOTS)
ban_active = False
try:
    import launcher  # noqa: F401  阳性对照：禁令必须真能拦截
except ImportError:
    ban_active = True
print(json.dumps({
    "exit_code": exit_code,
    "forbidden_modules": forbidden,
    "ban_active": ban_active,
    "argv_tail_unchanged": sys.argv[1:] == product_args,
}))
"""


@pytest.mark.parametrize(
    "args,expected_code,expected_fragment",
    [
        (["--selftest"], 0, "selftest: 6/6 passed"),
        (["--version"], 0, "0.1.0.dev0"),
        (["--help"], 0, "export-csv"),
        (["-h"], 0, "export-csv"),
        (["--no-such-option"], 2, None),
        (["--selftest", "--elevated-rescan"], 2, None),
        (["scan"], 2, None),
    ],
)
def test_cli_subprocess_real_run_with_import_ban(
    tmp_path: Path, args: list[str], expected_code: int, expected_fragment: str | None
) -> None:
    driver = tmp_path / "import_ban_driver.py"
    driver.write_text(_DRIVER_SOURCE, encoding="utf-8")
    proc = _run_py([sys.executable, str(driver), str(ENTRY_PATH), *args])
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report["exit_code"] == expected_code
    assert report["forbidden_modules"] == []
    assert report["ban_active"] is True
    assert report["argv_tail_unchanged"] is True
    if expected_fragment is not None:
        assert expected_fragment in proc.stdout


@pytest.mark.parametrize("form", ["script", "module"])
def test_source_invocation_forms_selftest(form: str) -> None:
    if form == "script":
        cmd = [sys.executable, str(ENTRY_PATH), "--selftest"]
    else:
        cmd = [sys.executable, "-m", "disk_audit_app", "--selftest"]
    proc = _run_py(cmd)
    assert proc.returncode == 0, proc.stderr
    assert "selftest: 6/6 passed" in proc.stdout