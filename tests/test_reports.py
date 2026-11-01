r"""T3-06（待办 G3）报告落盘、淘汰与打开纯逻辑测试。

依据：任务卡 T3-06 实现约束（报告只写 DATA_DIR\reports、os.startfile 只读打开、
文件名含时间戳、旧报告按时间淘汰保留 12 份）、U-2（程序自身仅在
%LOCALAPPDATA%\DiskAudit\ 写入——验收②等效证据：越界路径构造 → 拒绝）、
方案四节架构⑤（静态 HTML · 默认浏览器打开）。

I/O 根全部可注入（tmp_path / monkeypatch），测试不触碰真实
%LOCALAPPDATA%\DiskAudit\、不启动真实浏览器（open_report 走替身）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from disk_audit import reports  # noqa: E402
from disk_audit.engine import texts  # noqa: E402

FIXED_NOW = datetime(2026, 11, 1, 15, 30, 45)


# ---------- save_report：落盘路径与时间戳命名 ----------


def test_save_report_writes_timestamped_file_creating_dir(tmp_path: Path):
    """注入目录不存在 → 自动创建；文件名含时间戳；内容逐字落盘；返回绝对路径。"""
    reports_dir = tmp_path / "reports"
    path = reports.save_report("<html>x</html>", reports_dir=str(reports_dir), now=FIXED_NOW)
    written = Path(path)
    assert written.is_absolute()
    assert written.parent == reports_dir
    assert written.name == "report-20261101-153045.html"
    assert written.read_text(encoding="utf-8") == "<html>x</html>"


def test_save_report_default_dir_is_package_reports_constant(tmp_path: Path, monkeypatch):
    """默认写入位 = 包内 REPORTS_DIR 常量（U-2 唯一写入位），根可替换便于测试。"""
    monkeypatch.setattr(reports, "REPORTS_DIR", str(tmp_path / "replaced"))
    path = reports.save_report("<html></html>", now=FIXED_NOW)
    assert Path(path).parent == tmp_path / "replaced"
    assert Path(path).name == "report-20261101-153045.html"


def test_save_report_same_second_conflict_gets_sequence_suffix(tmp_path: Path):
    """同秒保存第二份：扩展名前加 -1 序号，不覆盖既有报告。"""
    first = reports.save_report("<html>1</html>", reports_dir=str(tmp_path), now=FIXED_NOW)
    second = reports.save_report("<html>2</html>", reports_dir=str(tmp_path), now=FIXED_NOW)
    assert Path(first).name == "report-20261101-153045.html"
    assert Path(second).name == "report-20261101-153045-1.html"
    assert Path(first).read_text(encoding="utf-8") == "<html>1</html>"
    assert Path(second).read_text(encoding="utf-8") == "<html>2</html>"


def test_all_written_paths_stay_under_injected_dir(tmp_path: Path):
    """验收②等效证据：连续多秒多份落盘后，注入目录内只有本程序命名的报告文件，
    且注入目录外无任何新增文件（以 tmp_path 根为界清点）。"""
    for minute in (1, 2, 3):
        reports.save_report(
            "<html></html>",
            reports_dir=str(tmp_path / "reports"),
            now=datetime(2026, 11, 1, 15, 30, minute),
        )
    assert sorted(p.name for p in (tmp_path / "reports").iterdir()) == [
        "report-20261101-153001.html",
        "report-20261101-153002.html",
        "report-20261101-153003.html",
    ]
    assert [p.name for p in tmp_path.iterdir()] == ["reports"]


# ---------- resolve_report_path：越界构造拒绝（U-2 验收②等效证据） ----------


@pytest.mark.parametrize(
    "bad_name",
    [
        r"..\evil.html",  # 相对上跳
        r"sub\dir.html",  # 子目录
        "evil.html",  # 不符合本程序命名模式
        "report-20261101-153045.html.exe",  # 双扩展名
        r"C:\Windows\evil.html",  # 绝对路径注入
        "..\\..\\report-20261101-153045.html",  # 混合上跳
    ],
)
def test_resolve_report_path_rejects_out_of_bounds_names(tmp_path: Path, bad_name: str):
    """越界路径构造 → ValueError（中文文案），且目录外无任何文件产生。"""
    with pytest.raises(ValueError) as excinfo:
        reports.resolve_report_path(str(tmp_path), bad_name)
    assert str(excinfo.value)  # 中文文案非空（规范 §1：异常提示中文）
    assert list(tmp_path.rglob("*")) == []  # 拒绝路径未产生任何写入


def test_resolve_report_path_accepts_valid_report_name(tmp_path: Path):
    got = reports.resolve_report_path(str(tmp_path), "report-20261101-153045.html")
    assert Path(got) == tmp_path / "report-20261101-153045.html"


# ---------- prune_reports：按时间淘汰保留 12 份 ----------


def _make_reports(directory: Path, names: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text("<html></html>", encoding="utf-8")


def test_prune_reports_keeps_newest_twelve_and_removes_oldest(tmp_path: Path):
    names = [f"report-20261001-0000{index:02d}.html" for index in range(15)]
    _make_reports(tmp_path, names)
    removed = reports.prune_reports(reports_dir=str(tmp_path), keep=12)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert removed == names[:3]  # 删除最旧 3 份
    assert remaining == names[3:]  # 保留最新 12 份
    assert len(remaining) == 12


def test_prune_reports_default_keep_is_twelve(tmp_path: Path):
    names = [f"report-20261001-0000{index:02d}.html" for index in range(14)]
    _make_reports(tmp_path, names)
    removed = reports.prune_reports(reports_dir=str(tmp_path))
    assert len(removed) == 2
    assert len(list(tmp_path.iterdir())) == 12


def test_prune_reports_treats_sequence_suffix_as_same_moment_order(tmp_path: Path):
    """同秒 -1/-2 序号文件排序晚于无序号文件（时间序 = 基名字典序 + 序号）。"""
    names = [
        "report-20261101-153045.html",
        "report-20261101-153045-1.html",
        "report-20261101-153045-2.html",
        "report-20261101-153046.html",
        "report-20261101-153047.html",
    ]
    _make_reports(tmp_path, names)
    removed = reports.prune_reports(reports_dir=str(tmp_path), keep=3)
    assert removed == ["report-20261101-153045.html", "report-20261101-153045-1.html"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "report-20261101-153045-2.html",
        "report-20261101-153046.html",
        "report-20261101-153047.html",
    ]


def test_prune_reports_leaves_foreign_files_untouched(tmp_path: Path):
    """非本程序命名模式的文件不参与淘汰（不扩大删除范围）。"""
    names = [f"report-20261001-0000{index:02d}.html" for index in range(13)]
    _make_reports(tmp_path, names + ["notes.txt", "other.html", "report.txt"])
    removed = reports.prune_reports(reports_dir=str(tmp_path), keep=12)
    assert removed == names[:1]
    assert (tmp_path / "notes.txt").exists()
    assert (tmp_path / "other.html").exists()
    assert (tmp_path / "report.txt").exists()


def test_prune_reports_empty_or_missing_dir_returns_empty(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert reports.prune_reports(reports_dir=str(empty)) == []
    assert reports.prune_reports(reports_dir=str(tmp_path / "missing")) == []


def test_prune_reports_below_keep_threshold_removes_nothing(tmp_path: Path):
    names = [f"report-20261001-0000{index:02d}.html" for index in range(11)]
    _make_reports(tmp_path, names)
    assert reports.prune_reports(reports_dir=str(tmp_path), keep=12) == []
    assert len(list(tmp_path.iterdir())) == 11


def test_prune_reports_rejects_non_positive_keep(tmp_path: Path):
    with pytest.raises(ValueError):
        reports.prune_reports(reports_dir=str(tmp_path), keep=0)


# ---------- open_report：os.startfile 只读打开（U-4/架构⑤） ----------


def test_open_report_calls_injected_opener_with_path():
    opened: list[str] = []
    reports.open_report(r"C:\r\report.html", opener=opened.append)
    assert opened == [r"C:\r\report.html"]


def test_open_report_default_opener_is_os_startfile(monkeypatch):
    """默认出口 = os.startfile（只读打开）；monkeypatch 替身验证，不真开浏览器。"""
    opened: list[str] = []
    monkeypatch.setattr(os, "startfile", opened.append)
    reports.open_report(r"C:\r\report.html")
    assert opened == [r"C:\r\report.html"]


# ---------- 文案集中资源处（规范 §1） ----------


def test_reports_texts_required_keys_exist():
    required = [
        "status_scanning",
        "status_report_opened",
        "status_audit_failed",
        "reports_err_bad_filename",
        "reports_err_outside_dir",
        "reports_err_bad_keep",
    ]
    missing = [key for key in required if key not in texts.G3_TEXTS]
    assert missing == []


def test_reports_texts_no_forbidden_terms():
    """Q3 禁"可回收"（禁用词约束对全部对外文案生效）。"""
    blob = "".join(texts.G3_TEXTS.values())
    assert "可回收" not in blob
