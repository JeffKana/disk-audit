"""T2-02（待办 D1）判定单元划分与聚合测试。

依据：方案 9.2（判定单元 = 扫描范围顶层目录及其下钻子项，文件级不单独计入）；
容器下钻对齐原型 drill_programs/drill_packages（%LOCALAPPDATA%\Programs、Packages
各下钻一层）。验证 scan 输出新增 units 数组后：单元划分口径、每单元聚合值、
reparse 不作单元、JSON 字段齐备。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from disk_audit.scanner import scan_path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mkdir(path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write(path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_top_level_dirs_are_units(tmp_path):
    """扫描根的每个顶层子目录是一个判定单元；根级散文件不构成单元。"""
    _write(tmp_path / "alpha" / "data.bin", 100)
    _write(tmp_path / "beta" / "data.bin", 200)
    _write(tmp_path / "loose.txt", 10)  # 根级散文件：只进总量，不是单元
    result = scan_path(str(tmp_path))
    unit_paths = [u.path for u in result.units]
    assert unit_paths == sorted([str(tmp_path / "alpha"), str(tmp_path / "beta")])


def test_containers_drill_one_level(tmp_path):
    """Programs/Packages 容器下钻一层：子目录亦为单元，孙目录不再是单元。"""
    _write(tmp_path / "Programs" / "appA" / "app.exe", 50)
    _write(tmp_path / "Programs" / "appA" / "deep" / "x.bin", 5)
    _write(tmp_path / "Packages" / "pkg1" / "data.db", 30)
    _write(tmp_path / "Other" / "f.bin", 7)
    result = scan_path(str(tmp_path))
    unit_paths = {u.path for u in result.units}
    root_str = str(tmp_path)
    assert unit_paths == {
        os.path.join(root_str, "Programs"),
        os.path.join(root_str, "Programs", "appA"),
        os.path.join(root_str, "Packages"),
        os.path.join(root_str, "Packages", "pkg1"),
        os.path.join(root_str, "Other"),
    }


def test_unit_aggregates(tmp_path):
    """每单元 files/dirs（含单元自身）/双口径/max_mtime/exe_files 聚合正确。"""
    _write(tmp_path / "alpha" / "tool.exe", 100)
    _write(tmp_path / "alpha" / "sub" / "data.bin", 300)
    result = scan_path(str(tmp_path))
    unit = next(u for u in result.units if u.path == str(tmp_path / "alpha"))
    assert unit.files == 2
    assert unit.dirs == 2  # 单元自身 + sub
    assert unit.logical_bytes == 400
    assert unit.allocated_bytes >= unit.logical_bytes
    assert unit.exe_files == 1
    mtimes = [
        (tmp_path / "alpha" / "tool.exe").stat().st_mtime,
        (tmp_path / "alpha" / "sub" / "data.bin").stat().st_mtime,
    ]
    assert unit.max_mtime == max(mtimes)


def test_units_sorted_and_json_fields(tmp_path):
    """scan JSON 的 units 数组按路径排序，字段齐备（CLI 与库输出同构）。"""
    _write(tmp_path / "b" / "f.bin", 10)
    _write(tmp_path / "a" / "f.bin", 10)
    result = scan_path(str(tmp_path))
    paths = [u.path for u in result.units]
    assert paths == sorted(paths)
    data = json.loads(json.dumps(result.to_json_dict(), ensure_ascii=False))
    assert "units" in data
    expected_keys = {
        "path", "files", "dirs", "logical_bytes", "allocated_bytes",
        "max_mtime", "exe_files",
    }
    assert data["units"] and set(data["units"][0]) == expected_keys


def test_empty_root_has_no_units(tmp_path):
    result = scan_path(str(tmp_path))
    assert result.units == []
    assert result.to_json_dict()["units"] == []


@pytest.mark.skipif(sys.platform != "win32", reason="Junction 仅 Windows")
def test_reparse_top_dir_not_unit(tmp_path):
    """reparse point 顶层目录按 X-1 跳过，不作为判定单元（防循环）。"""
    target = tmp_path / "real"
    target.mkdir()
    (target / "f.bin").write_bytes(b"x" * 5)
    link = tmp_path / "jump"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True
    )
    result = scan_path(str(tmp_path))
    assert str(link) not in {u.path for u in result.units}
