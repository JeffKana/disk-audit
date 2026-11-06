r"""T4-06（待办 F3）报告候选 CSV 导出与默认脱敏测试。

依据：任务卡 T4-06 验收标准（①四类脱敏各正反单测；②默认导出不含原文断言；
③显式 --raw 才出原文；④CSV 可被 Excel 打开——BOM/编码 utf-8-sig 留档；
⑤远端 CI 绿）、方案 P7 与第八节"脱敏"（四类：当前用户名/计算机名/用户 SID/
其他用户目录名）、U-2（导出仅写 DATA_DIR\\reports\\，路径根可注入替身）。

脱敏身份一律显式注入或 monkeypatch 环境变量，断言不依赖执行机的真实
用户名/机器名（CI 与本地均确定）；真实报告端到端见执行记录留档（非单测）。
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from disk_audit import csv_export  # noqa: E402
from disk_audit.engine import texts  # noqa: E402

FIXED_NOW = datetime(2026, 11, 3, 10, 0, 0)
USER = "querkecor"
COMPUTER = "DESK-01"
OTHER_USER = "someone"
SID = "S-1-5-21-1004336348-117809857-682003330-1001"

PH_USER = "<用户名>"
PH_COMPUTER = "<计算机名>"
PH_SID = "<SID>"
PH_OTHER = "<其他用户>"


def _sanitize(text: str) -> str:
    return csv_export.sanitize_text(text, username=USER, computer=COMPUTER)


# ---------- 验收①：四类脱敏正反单测 ----------


def test_sanitize_username_mid_path():
    """用户名在路径中段（Users 下）→ 占位符，其余部分保留。"""
    assert _sanitize(rf"C:\Users\{USER}\AppData\Roaming\LeftApp") == (
        rf"C:\Users\{PH_USER}\AppData\Roaming\LeftApp"
    )


def test_sanitize_username_tail_path():
    """用户名在路径尾部 → 占位符。"""
    assert _sanitize(rf"C:\Users\{USER}") == rf"C:\Users\{PH_USER}"
    assert _sanitize(rf"D:\backup\{USER}") == rf"D:\backup\{PH_USER}"


def test_sanitize_username_outside_users_dir():
    """用户名出现在非 Users 目录中段同样命中（当前用户名四类口径不限位置）。"""
    assert _sanitize(rf"D:\data\{USER}\dump") == rf"D:\data\{PH_USER}\dump"


def test_sanitize_username_case_insensitive():
    """Windows 路径大小写不敏感 → 大写形态的用户名同样脱敏。"""
    assert _sanitize(rf"C:\Users\{USER.upper()}\X") == rf"C:\Users\{PH_USER}\X"


def test_sanitize_username_not_replaced_inside_longer_segment():
    """反例：用户名只是更长目录名的子串（querkecor2-backup）→ 原样保留。"""
    raw = rf"C:\tools\{USER}2-backup\X"
    assert _sanitize(raw) == raw


def test_sanitize_unrelated_path_untouched():
    """反例：不含任何敏感项的路径逐字保留。"""
    raw = r"C:\Program Files\App\bin\file.dll"
    assert _sanitize(raw) == raw


def test_sanitize_computer_name_unc_and_mid_path():
    """计算机名：UNC 前缀与非 UNC 中段都命中。"""
    assert _sanitize(rf"\\{COMPUTER}\share\X") == rf"\\{PH_COMPUTER}\share\X"
    assert _sanitize(rf"D:\{COMPUTER}\logs") == rf"D:\{PH_COMPUTER}\logs"


def test_sanitize_computer_name_not_replaced_inside_longer_segment():
    """反例：计算机名是更长段名的子串（DESK-0101）→ 原样保留。"""
    raw = rf"D:\{COMPUTER}01\logs"
    assert _sanitize(raw) == raw


def test_sanitize_sid_domain_form():
    """SID 形如 S-1-5-21-*（域/账户 SID）→ 占位符。"""
    assert _sanitize(rf"D:\Profiles\{SID}\NTUSER.DAT") == rf"D:\Profiles\{PH_SID}\NTUSER.DAT"


def test_s_sid_short_wellknown_not_replaced():
    """反例：短型 well-known SID（S-1-5-18，全机通用无个人可识别信息）按
    正则下限（≥3 组后缀）设计为不脱敏——留档为有意行为。"""
    raw = r"C:\Windows\System32\config\profile-S-1-5-18"
    assert _sanitize(raw) == raw


def test_sanitize_other_user_directory():
    """其他用户目录 C:\\Users\\<other>\\ → 占位符（当前用户名除外）。"""
    assert _sanitize(rf"C:\Users\{OTHER_USER}\Downloads\old") == (
        rf"C:\Users\{PH_OTHER}\Downloads\old"
    )


def test_sanitize_current_user_dir_not_marked_other_user():
    """反例：当前用户自己的 Users 目录不被标为"其他用户"，只脱为 <用户名>。"""
    got = _sanitize(rf"C:\Users\{USER}\AppData\Local\X")
    assert PH_OTHER not in got
    assert got == rf"C:\Users\{PH_USER}\AppData\Local\X"


def test_sanitize_other_user_when_identity_unknown_over_sanitizes(monkeypatch):
    """身份未知（无环境变量）时兜底：Users 下所有目录一律按其他用户脱敏
    （宁过度不遗漏）；回退覆盖面决策留档。"""
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("COMPUTERNAME", raising=False)
    got = csv_export.sanitize_text(rf"C:\Users\{OTHER_USER}\X")
    assert got == rf"C:\Users\{PH_OTHER}\X"


def test_sanitize_all_four_categories_in_one_text():
    """四类同串复合：全部命中且互不干扰（每类均为完整路径段）。"""
    raw = rf"\\{COMPUTER}\scan\{SID}\Users\{OTHER_USER}\{USER}\tail"
    got = _sanitize(raw)
    assert got == rf"\\{PH_COMPUTER}\scan\{PH_SID}\Users\{PH_OTHER}\{PH_USER}\tail"
    for secret in (COMPUTER, SID, OTHER_USER, USER):
        assert secret not in got


def test_sanitize_sid_segment_under_users_keeps_sid_placeholder():
    """顺序决策留档：SID 先于其他用户目录替换（最具体优先），
    Users 下的 SID 段脱为 <SID> 而非 <其他用户>。"""
    got = _sanitize(rf"C:\Users\{SID}")
    assert got == rf"C:\Users\{PH_SID}"


def test_sanitize_default_identity_from_environment(monkeypatch):
    """默认身份锚定 = 环境变量 USERNAME/COMPUTERNAME（双锚定之值锚）。"""
    monkeypatch.setenv("USERNAME", USER)
    monkeypatch.setenv("COMPUTERNAME", COMPUTER)
    assert csv_export.sanitize_text(rf"C:\Users\{USER}\X") == rf"C:\Users\{PH_USER}\X"
    assert csv_export.sanitize_text(rf"\\{COMPUTER}\s") == rf"\\{PH_COMPUTER}\s"


# ---------- 验收②/③：默认导出不含原文；--raw 才出原文 ----------


def _sample_report() -> dict:
    """含真实形态敏感项的样例报告（report-v1 候选字段全集）。"""
    return {
        "schema_version": "1.0",
        "generated_at": "2026-11-03T10:00:00+08:00",
        "scan_root": rf"C:\Users\{USER}\AppData\Roaming",
        "totals": {
            "allocated_bytes": 1000,
            "logical_bytes": 900,
            "regenerable_subtotal": 0,
            "regenerable_confirm_subtotal": 0,
            "skipped_entries": 0,
        },
        "candidates": [
            {
                "path": rf"C:\Users\{USER}\AppData\Roaming\LeftApp",
                "logical_bytes": 100,
                "allocated_bytes": 200,
                "confidence": "高",
                "verdict_source": "知识库",
                "evidence_chain": [{"source": "知识库", "content": "证据全文-mark-EVID1"}],
                "suggested_action": "A4",
            },
            {
                "path": rf"C:\Users\{USER}",  # 尾部用户名
                "logical_bytes": 10,
                "allocated_bytes": 20,
                "confidence": "中",
                "verdict_source": "注册表",
                "evidence_chain": [{"source": "注册表卸载项", "content": "x"}],
                "suggested_action": "A3",
            },
            {
                "path": rf"C:\Users\{OTHER_USER}\Downloads\old",  # 其他用户目录
                "logical_bytes": 30,
                "allocated_bytes": 40,
                "confidence": "低",
                "verdict_source": "启发式",
                "evidence_chain": [{"source": "启发式", "content": "y"}],
                "suggested_action": "A5",
            },
            {
                "path": rf"\\{COMPUTER}\public\stuff",  # 计算机名
                "logical_bytes": 50,
                "allocated_bytes": 60,
                "confidence": "受保护",
                "verdict_source": "硬保护",
                "evidence_chain": [{"source": "硬保护", "content": "z"}],
                "suggested_action": "A5",
            },
            {
                "path": rf"D:\Profiles\{SID}\AppData",  # SID
                "logical_bytes": 70,
                "allocated_bytes": 80,
                "confidence": "高",
                "verdict_source": "知识库",
                "evidence_chain": [{"source": "知识库", "content": "w"}],
                "suggested_action": "A2",
            },
        ],
    }


@pytest.fixture()
def identity_env(monkeypatch):
    monkeypatch.setenv("USERNAME", USER)
    monkeypatch.setenv("COMPUTERNAME", COMPUTER)


def test_export_csv_default_contains_no_originals(tmp_path: Path, identity_env):
    """验收②：默认导出全文检索四类原文零出现（含真实样例形态）；占位符在场；
    证据链全文不进 CSV（仅数据列）。"""
    out = Path(csv_export.export_csv(_sample_report(), out_dir=str(tmp_path), now=FIXED_NOW))
    text = out.read_text(encoding="utf-8-sig")
    for secret in (USER, COMPUTER, OTHER_USER, SID):
        assert secret not in text, f"原文泄露：{secret}"
    for placeholder in (PH_USER, PH_OTHER, PH_SID, PH_COMPUTER):
        assert placeholder in text
    assert "EVID1" not in text  # 证据链全文不导出（控体量）


def test_export_csv_raw_flag_outputs_originals(tmp_path: Path, identity_env):
    """验收③：显式 raw=True 才出原文（默认脱敏不反转）。"""
    out = Path(
        csv_export.export_csv(_sample_report(), out_dir=str(tmp_path), raw=True, now=FIXED_NOW)
    )
    text = out.read_text(encoding="utf-8-sig")
    for secret in (USER, COMPUTER, OTHER_USER, SID):
        assert secret in text
    for placeholder in (PH_USER, PH_OTHER, PH_SID, PH_COMPUTER):
        assert placeholder not in text


def test_export_csv_writes_utf8_sig_bom(tmp_path: Path, identity_env):
    """验收④：文件以 utf-8-sig 落盘，前 3 字节为 BOM（Excel 直开不乱码留档）。"""
    out = Path(csv_export.export_csv(_sample_report(), out_dir=str(tmp_path), now=FIXED_NOW))
    raw_bytes = out.read_bytes()
    assert raw_bytes[:3] == b"\xef\xbb\xbf"
    raw_bytes.decode("utf-8-sig")  # 可解码


def test_export_csv_header_and_rows_roundtrip(tmp_path: Path, identity_env):
    """CSV 结构：表头六数据列（无证据链列），行数与字段数正确，csv 模块可回读。"""
    out = Path(csv_export.export_csv(_sample_report(), out_dir=str(tmp_path), now=FIXED_NOW))
    with open(out, "r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == [
        "路径", "逻辑大小（字节）", "占用空间（字节）", "置信度", "判定来源", "建议动作",
    ]
    assert len(rows) == 1 + len(_sample_report()["candidates"])
    assert all(len(row) == 6 for row in rows)
    assert rows[1][0] == rf"C:\Users\{PH_USER}\AppData\Roaming\LeftApp"
    assert rows[1][1] == "100" and rows[1][2] == "200"
    assert rows[1][3] == "高" and rows[1][5] == "A4"


def test_export_csv_quotes_paths_with_comma_and_quote(tmp_path: Path):
    """验收④留档：含逗号/引号路径按 QUOTE_MINIMAL 规则转义，回读逐字一致
    （Excel 兼容性 = BOM + 标准引号转义）。"""
    report = {
        "schema_version": "1.0",
        "generated_at": "2026-11-03T10:00:00+08:00",
        "scan_root": "C:\\x",
        "totals": {
            "allocated_bytes": 0, "logical_bytes": 0,
            "regenerable_subtotal": 0, "regenerable_confirm_subtotal": 0,
            "skipped_entries": 0,
        },
        "candidates": [
            {
                "path": r'C:\proj\a,b"c\dir',
                "logical_bytes": 1, "allocated_bytes": 2,
                "confidence": "低", "verdict_source": "启发式",
                "evidence_chain": [{"source": "启发式", "content": "e"}],
                "suggested_action": "A5",
            }
        ],
    }
    out = Path(csv_export.export_csv(report, out_dir=str(tmp_path), now=FIXED_NOW))
    with open(out, "r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[1][0] == r'C:\proj\a,b"c\dir'


# ---------- 落盘路径：时间戳命名 / 同秒序号 / 越界守卫（U-2，复用 reports.py 模式） ----------


def test_export_csv_timestamped_name_and_absolute_path(tmp_path: Path):
    out = Path(csv_export.export_csv(_sample_report(), out_dir=str(tmp_path), now=FIXED_NOW))
    assert out.is_absolute()
    assert out.parent == tmp_path
    assert out.name == "candidates-20261103-100000.csv"


def test_export_csv_same_second_conflict_gets_sequence_suffix(tmp_path: Path):
    first = csv_export.export_csv(_sample_report(), out_dir=str(tmp_path), now=FIXED_NOW)
    second = csv_export.export_csv(_sample_report(), out_dir=str(tmp_path), now=FIXED_NOW)
    assert Path(first).name == "candidates-20261103-100000.csv"
    assert Path(second).name == "candidates-20261103-100000-1.csv"


def test_export_csv_default_dir_is_reports_constant(tmp_path: Path, monkeypatch):
    """默认写入位 = 包内 REPORTS_DIR（DATA_DIR\\reports\\，U-2），根可替换。"""
    monkeypatch.setattr(csv_export, "REPORTS_DIR", str(tmp_path / "replaced"))
    out = Path(csv_export.export_csv(_sample_report(), now=FIXED_NOW))
    assert out.parent == tmp_path / "replaced"
    assert out.name == "candidates-20261103-100000.csv"


@pytest.mark.parametrize(
    "bad_name",
    [
        r"..\evil.csv",  # 相对上跳
        r"sub\dir.csv",  # 子目录
        "evil.csv",  # 不符合本程序命名模式
        "candidates-20261103-100000.csv.exe",  # 双扩展名
        r"C:\Windows\evil.csv",  # 绝对路径注入
    ],
)
def test_resolve_csv_path_rejects_out_of_bounds_names(tmp_path: Path, bad_name: str):
    """越界路径构造 → ValueError（中文文案），且不产生任何写入（U-2）。"""
    with pytest.raises(ValueError) as excinfo:
        csv_export.resolve_csv_path(str(tmp_path), bad_name)
    assert str(excinfo.value)
    assert list(tmp_path.rglob("*")) == []


def test_resolve_csv_path_accepts_valid_name(tmp_path: Path):
    got = csv_export.resolve_csv_path(str(tmp_path), "candidates-20261103-100000.csv")
    assert Path(got) == tmp_path / "candidates-20261103-100000.csv"


# ---------- 输入校验：拒绝并披露，不产生半成品文件 ----------


def _drop_field(report: dict, index: int, field: str) -> dict:
    import copy

    cloned = copy.deepcopy(report)
    del cloned["candidates"][index][field]
    return cloned


@pytest.mark.parametrize(
    "bad_report",
    [
        "not-a-dict",
        {"schema_version": "1.0"},  # 缺 candidates
        {"schema_version": "1.0", "candidates": "no-list"},  # candidates 非数组
    ],
)
def test_export_csv_rejects_invalid_top_level(tmp_path: Path, bad_report):
    with pytest.raises(ValueError):
        csv_export.export_csv(bad_report, out_dir=str(tmp_path), now=FIXED_NOW)
    assert list(tmp_path.rglob("*")) == []  # 校验失败不产生半成品文件


def test_export_csv_rejects_candidate_missing_field(tmp_path: Path):
    bad = _drop_field(_sample_report(), 2, "confidence")
    with pytest.raises(ValueError) as excinfo:
        csv_export.export_csv(bad, out_dir=str(tmp_path), now=FIXED_NOW)
    assert "#2" in str(excinfo.value) and "置信度" in str(excinfo.value)
    assert list(tmp_path.rglob("*")) == []


def test_export_csv_rejects_non_integer_size(tmp_path: Path):
    bad = _drop_field(_sample_report(), 0, "logical_bytes")
    bad["candidates"][0]["logical_bytes"] = "many"
    with pytest.raises(ValueError):
        csv_export.export_csv(bad, out_dir=str(tmp_path), now=FIXED_NOW)
    assert list(tmp_path.rglob("*")) == []


def test_export_csv_empty_candidates_writes_header_only(tmp_path: Path, identity_env):
    report = _sample_report()
    report["candidates"] = []
    out = Path(csv_export.export_csv(report, out_dir=str(tmp_path), now=FIXED_NOW))
    with open(out, "r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 1


# ---------- CLI 子命令（argv 隔离：main 显式传参，M-01 教训） ----------


def _write_report(tmp_path: Path) -> Path:
    report_json = tmp_path / "report.json"
    report_json.write_text(
        json.dumps(_sample_report(), ensure_ascii=False), encoding="utf-8"
    )
    return report_json


def test_cli_export_csv_default_sanitized_message(tmp_path: Path, monkeypatch, capsys, identity_env):
    """CLI 默认导出：完成态含分享提示文案（"报告含本机路径"），文件落替身目录。

    identity_env 夹具显式锚定脱敏身份——不得依赖执行机环境碰巧一致
    （CI runner 用户名与样例用户名不同， Ambient env 会导致假红）。"""
    from disk_audit.__main__ import main

    monkeypatch.setattr(csv_export, "REPORTS_DIR", str(tmp_path / "out"))
    monkeypatch.chdir(tmp_path)
    report_json = _write_report(tmp_path)
    exit_code = main(["export-csv", str(report_json)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "导出完成（已脱敏）" in captured.out
    assert "报告含本机路径" in captured.out
    produced = list((tmp_path / "out").glob("candidates-*.csv"))
    assert len(produced) == 1
    text = produced[0].read_text(encoding="utf-8-sig")
    assert USER not in text and PH_USER in text


def test_cli_export_csv_raw_flag_warns_unsanitized(tmp_path: Path, monkeypatch, capsys, identity_env):
    """--raw：完成态提示升级为"未脱敏"警示（R10 零假设原则），文件含原文。"""
    from disk_audit.__main__ import main

    monkeypatch.setattr(csv_export, "REPORTS_DIR", str(tmp_path / "out"))
    monkeypatch.chdir(tmp_path)
    report_json = _write_report(tmp_path)
    exit_code = main(["export-csv", str(report_json), "--raw"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "未脱敏" in captured.out
    assert "警示" in captured.out
    produced = list((tmp_path / "out").glob("candidates-*.csv"))
    text = produced[0].read_text(encoding="utf-8-sig")
    assert USER in text


def test_cli_export_csv_missing_file_exit_two(tmp_path: Path, monkeypatch, capsys):
    from disk_audit.__main__ import main

    monkeypatch.setattr(csv_export, "REPORTS_DIR", str(tmp_path / "out"))
    monkeypatch.chdir(tmp_path)
    exit_code = main(["export-csv", str(tmp_path / "missing.json")])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "导出失败" in captured.err


def test_cli_export_csv_invalid_json_exit_two(tmp_path: Path, monkeypatch, capsys):
    from disk_audit.__main__ import main

    monkeypatch.setattr(csv_export, "REPORTS_DIR", str(tmp_path / "out"))
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    exit_code = main(["export-csv", str(bad)])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "导出失败" in captured.err


# ---------- 文案集中资源处（开发规范 §1） ----------


def test_f3_texts_required_keys_exist():
    required = [
        "csv_done_default",
        "csv_share_notice",
        "csv_done_raw",
        "csv_share_notice_raw",
        "csv_err_read",
        "csv_err_json",
        "csv_err_encode",
    ]
    missing = [key for key in required if key not in texts.F3_TEXTS]
    assert missing == []


def test_f3_share_notice_carries_required_wording():
    """任务卡实现约束：分享提示文案（"报告含本机路径"）在导出完成态展示。"""
    assert "报告含本机路径" in texts.F3_TEXTS["csv_share_notice"]
    assert "未脱敏" in texts.F3_TEXTS["csv_share_notice_raw"]


def test_f3_placeholders_distinct_and_fixed():
    """四类占位符固定且互不相同（脱敏输出可检索、不互相覆盖）。"""
    values = set(texts.SANITIZE_PLACEHOLDERS.values())
    assert len(values) == 4
    assert values == {PH_USER, PH_COMPUTER, PH_SID, PH_OTHER}


def test_f3_texts_no_forbidden_terms():
    """Q3 禁"可回收"对新增文案同样生效。"""
    blob = "".join(texts.F3_TEXTS.values())
    assert "可回收" not in blob
