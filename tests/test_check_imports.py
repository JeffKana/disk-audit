"""T-01（待办 A4）import 白名单门禁的单元测试。

覆盖：干净树通过、第三方 import 拒绝（正/反例）、语法错误按违规计、
main() 退出码、真实仓库包通过（验收①的可执行形态）。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
_SPEC = importlib.util.spec_from_file_location("check_imports", _TOOLS / "check_imports.py")
check_imports = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_imports)


def _make_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def test_clean_tree_passes(tmp_path):
    root = _make_tree(tmp_path, {
        "pkg/a.py": (
            "from __future__ import annotations\n"
            "import os\n"
            "import ctypes\n"
            "from pathlib import Path\n"
            "from . import b\n"
            "from .b import thing\n"
        ),
        "pkg/b.py": (
            "import disk_audit.scanner\n"
            "from disk_audit import __version__\n"
        ),
    })
    assert check_imports.find_violations(root) == []


def test_third_party_import_rejected(tmp_path):
    root = _make_tree(tmp_path, {"pkg/a.py": "import requests\n"})
    violations = check_imports.find_violations(root)
    assert len(violations) == 1
    assert "requests" in violations[0]
    assert "a.py:1" in violations[0]


def test_third_party_from_import_rejected(tmp_path):
    root = _make_tree(tmp_path, {"pkg/a.py": "from yaml import safe_load\n"})
    violations = check_imports.find_violations(root)
    assert len(violations) == 1
    assert "yaml" in violations[0]


def test_submodule_of_allowed_package_rejected_by_root_name(tmp_path):
    """第三方包的子模块同样拒绝（按顶层模块名判定）。"""
    root = _make_tree(tmp_path, {"pkg/a.py": "import numpy.linalg\n"})
    assert check_imports.find_violations(root) != []


def test_syntax_error_counted_as_violation(tmp_path):
    root = _make_tree(tmp_path, {"pkg/a.py": "def broken(:\n"})
    violations = check_imports.find_violations(root)
    assert len(violations) == 1
    assert "解析失败" in violations[0]


@pytest.mark.skipif("winreg" not in sys.stdlib_module_names, reason="非 Windows 无 winreg")
def test_winreg_is_stdlib(tmp_path):
    root = _make_tree(tmp_path, {"pkg/a.py": "import winreg\n"})
    assert check_imports.find_violations(root) == []


def test_main_exit_codes(tmp_path, capsys):
    clean = _make_tree(tmp_path / "clean", {"pkg/a.py": "import os\n"})
    assert check_imports.main(["--root", str(clean)]) == 0
    dirty = _make_tree(tmp_path / "dirty", {"pkg/a.py": "import requests\n"})
    assert check_imports.main(["--root", str(dirty)]) == 1
    out = capsys.readouterr().out
    assert "requests" in out


def test_main_missing_root_fails(tmp_path):
    assert check_imports.main(["--root", str(tmp_path / "nope")]) == 1


def test_real_package_passes():
    """真实仓库 disk_audit/ 必须通过门禁（验收①）。"""
    assert check_imports.main() == 0


def test_gate_survives_non_utf8_stdout(tmp_path):
    """回归（PM 退回单 T-01）：runner stdout 默认 cp1252 时中文输出不得使门禁假红。

    用 PYTHONIOENCODING=cp1252 子进程复现（其优先级高于 PYTHONUTF8）：干净树必须
    退出码 0（未修复时会因 UnicodeEncodeError 崩成非 0）；违规树仍为退出码 1。
    """
    clean = _make_tree(tmp_path / "clean", {"pkg/a.py": "import os\n"})
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run(
        [sys.executable, str(_TOOLS / "check_imports.py"), "--root", str(clean)],
        capture_output=True, env=env, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout[-200:]

    dirty = _make_tree(tmp_path / "dirty", {"pkg/a.py": "import requests\n"})
    proc = subprocess.run(
        [sys.executable, str(_TOOLS / "check_imports.py"), "--root", str(dirty)],
        capture_output=True, env=env, timeout=60,
    )
    assert proc.returncode == 1
