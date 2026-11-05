"""T-03（待办 L2）容量偏差对比脚本单元测试。

覆盖：9.2 偏差公式、基准模式（贴数/超阈值/坏输入）、夹具模式（1000 个已知大小
文件的簇对齐公式自检）、脚本只读边界（基准模式不写文件）。
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
_SPEC = importlib.util.spec_from_file_location(
    "check_size_deviation", _TOOLS / "check_size_deviation.py"
)
check_size_deviation = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_size_deviation)


def test_deviation_formula():
    assert check_size_deviation.size_deviation(1000, 1000) == 0.0
    assert check_size_deviation.size_deviation(990, 1000) == 0.01
    assert check_size_deviation.size_deviation(1010, 1000) == 0.01
    assert check_size_deviation.size_deviation(0, 0) == 0.0
    assert check_size_deviation.size_deviation(5, 0) == float("inf")


def test_baseline_exact_match_passes(tmp_path, capsys):
    """夹具：一个已知大小的文件，基准=簇对齐公式的精确值 → 偏差 0，退出码 0。

    用 5000 字节（非 MFT 驻留）：驻留小文件的分配量是 MFT 内实占字节而非簇对齐，
    簇对齐公式只对非常驻文件成立。
    """
    target = tmp_path / "dir"
    target.mkdir()
    (target / "one.bin").write_bytes(b"x" * 5000)
    cluster = check_size_deviation.cluster_bytes_of(str(target))
    expected = math.ceil(5000 / cluster) * cluster
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps([{"path": str(target), "explorer_allocated_bytes": expected}]),
        encoding="utf-8",
    )
    before = sorted(p.name for p in tmp_path.iterdir())
    assert check_size_deviation.main(["--baseline", str(baseline)]) == 0
    out = capsys.readouterr().out
    assert "偏差：0.000%" in out
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after  # 基准模式只读，不产生任何文件


def test_baseline_over_limit_fails(tmp_path, capsys):
    """基准偏离一倍 → 偏差 100%，退出码 1。"""
    target = tmp_path / "dir"
    target.mkdir()
    (target / "one.bin").write_bytes(b"x" * 1000)
    cluster = check_size_deviation.cluster_bytes_of(str(target))
    expected = math.ceil(1000 / cluster) * cluster
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps([{"path": str(target), "explorer_allocated_bytes": expected * 2}]),
        encoding="utf-8",
    )
    assert check_size_deviation.main(["--baseline", str(baseline)]) == 1
    assert "不通过" in capsys.readouterr().out


def test_baseline_bad_input(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert check_size_deviation.main(["--baseline", str(bad)]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    assert check_size_deviation.main(["--baseline", str(broken)]) == 2


def test_baseline_missing_field(tmp_path):
    target = tmp_path / "dir"
    target.mkdir()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps([{"path": str(target)}]), encoding="utf-8")
    assert check_size_deviation.main(["--baseline", str(baseline)]) == 1


def test_fixture_mode_self_check(capsys):
    """验收②：1000 个已知大小文件，预期=簇对齐公式，偏差应为 0。"""
    assert check_size_deviation.main(["--fixture"]) == 0
    out = capsys.readouterr().out
    assert "偏差：0.000%" in out
    assert "簇对齐公式" in out


def test_main_entry_reconfigures_stdio_utf8(monkeypatch):
    """M-02：入口对 stdout/stderr 做 UTF-8 reconfigure 守卫（T-01 双保险先例）。

    注入记录型替身流，断言 main() 在参数解析前对两个流各执行一次
    reconfigure(encoding="utf-8")——缺参用法错误（SystemExit）不影响守卫先行。
    """
    reconfigured: list[dict] = []

    class _RecordingStream:
        def reconfigure(self, **kwargs):
            reconfigured.append(kwargs)

        def write(self, text):
            return len(text)

        def flush(self):
            return None

    stream = _RecordingStream()
    monkeypatch.setattr(check_size_deviation.sys, "stdout", stream, raising=False)
    monkeypatch.setattr(check_size_deviation.sys, "stderr", stream, raising=False)
    with pytest.raises(SystemExit):
        check_size_deviation.main([])
    assert reconfigured == [{"encoding": "utf-8"}, {"encoding": "utf-8"}]
