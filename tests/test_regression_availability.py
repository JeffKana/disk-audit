"""T6-01（T601-v1）回归夹具证据可用性（availability）兼容扩展测试。

依据：任务卡 T6-01《冻结的数据语义》——`evidence_scenario` 保留原五数组语义，
新增**可选** `availability` 对象，只允许 uninstall/appx/processes/services/autostart
五个严格 boolean 键；整个对象缺省、空对象或只列部分源时，未指源沿用旧夹具的
True 含义；显式 False 必须落到真实 `Result.available=False`，且不丢弃已给出的
entries/paths/packages/自启动记录等正证据。

本模块只做回归**夹具格式**验证，不改判定：合成样例明确标注“非真实误判”，
源不可用时的判定口径缺陷归 T5-06，不在此写固定期望。
"""
from __future__ import annotations

import copy
import json

import pytest

from tests._mini_schema import mini_validate
from tests.test_regression_cases import (
    CASES_DIR,
    REG_SCHEMA,
    _build_bundle,
    _case_files,
)

SOURCES = ("uninstall", "appx", "processes", "services", "autostart")
_OMIT = object()

# 非法 bool 替身：0/1 是 int、0.0/1.0 是 float，均不得被当作 boolean 接受。
BAD_BOOLEAN_VALUES = [
    pytest.param(0, id="int-0"),
    pytest.param(1, id="int-1"),
    pytest.param(0.0, id="float-0"),
    pytest.param(1.0, id="float-1"),
    pytest.param("true", id="str-true"),
    pytest.param("false", id="str-false"),
    pytest.param("", id="str-empty"),
    pytest.param(None, id="null"),
    pytest.param([], id="list-empty"),
    pytest.param(["uninstall"], id="list-nonempty"),
    pytest.param({}, id="dict-empty"),
    pytest.param({"available": True}, id="dict-nonempty"),
]


def _base_case() -> dict:
    """合成合法样例（非真实误判）：五源均带正证据，便于观察状态与内容保真。"""
    return {
        "case_id": "R901",
        "title": "合成夹具：availability 表达验证（非真实误判）",
        "registered_at": "2026-11-14",
        "registered_by": "CodeBuddy-Dev-T6-01（任务卡 T6-01）",
        "source_ref": "任务卡 T6-01 冻结的数据语义",
        "root_cause": "合成样例，仅验证回归夹具格式，不对应任何真实误判",
        "path_pattern": "C:\\Users\\<user>\\AppData\\Roaming\\sample-availability",
        "unit": {
            "files": 4,
            "dirs": 2,
            "logical_bytes": 8192,
            "allocated_bytes": 12288,
            "max_mtime": 0,
            "exe_files": 1,
        },
        "evidence_scenario": {
            "uninstall": [
                {
                    "display_name": "Sample Suite",
                    "publisher": "Sample Publisher",
                    "install_location": "C:\\Program Files\\Sample",
                    "install_date": "2026-01-01",
                    "uninstall_string": "\"C:\\Program Files\\Sample\\unins000.exe\"",
                    "reg_path": "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SampleSuite",
                }
            ],
            "appx": [
                {
                    "name": "Sample.Store.App",
                    "package_full_name": "Sample.Store.App_1.0.0.0_x64__abcdef01",
                    "install_location": "C:\\Program Files\\WindowsApps\\Sample.Store.App_1.0.0.0_x64__abcdef01",
                }
            ],
            "processes": ["C:\\Program Files\\Sample\\sample.exe"],
            "services": ["C:\\Program Files\\Sample\\samplesvc.exe -k Sample"],
            "autostart": [
                {
                    "source": "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
                    "name": "SampleTray",
                    "command": "\"C:\\Program Files\\Sample\\sample.exe\" /tray",
                    "kind": "registry",
                }
            ],
        },
        "expect": {"confidence": "低", "verdict_source": "启发式"},
    }


def _case_with(availability=_OMIT) -> dict:
    case = _base_case()
    if availability is not _OMIT:
        case["evidence_scenario"]["availability"] = copy.deepcopy(availability)
    return case


def _assert_schema_ok(case: dict) -> None:
    assert mini_validate(case, REG_SCHEMA) == []


def _assert_availability(case: dict, expected: dict) -> None:
    """按显式期望逐一核对五源 state，再核对正证据内容保真。"""
    bundle = _build_bundle(case["evidence_scenario"])
    actual = {
        "uninstall": bundle.uninstall.available,
        "appx": bundle.appx.available,
        "processes": bundle.processes.available,
        "services": bundle.services.available,
        "autostart": bundle.autostart.available,
    }
    assert actual == expected
    for source, flag in actual.items():
        assert flag is expected[source], f"{source}：状态必须是严格 boolean"
    scenario = case["evidence_scenario"]
    assert [e.display_name for e in bundle.uninstall.entries] == [
        e["display_name"] for e in scenario["uninstall"]
    ]
    assert [p.package_full_name for p in bundle.appx.packages] == [
        p["package_full_name"] for p in scenario["appx"]
    ]
    assert bundle.processes.paths == list(scenario["processes"])
    assert bundle.services.paths == list(scenario["services"])
    assert [(a.name, a.command, a.kind) for a in bundle.autostart.entries] == [
        (a["name"], a["command"], a["kind"]) for a in scenario["autostart"]
    ]


# ---------- ① 驱动消费：不经 schema 也必须消费显式 False ----------


def test_driver_consumes_declared_false_without_schema_gate():
    """驱动本身必须消费 False：不能靠 schema 通过而实现仍回退 True。"""
    case = _case_with({"appx": False, "services": False})
    bundle = _build_bundle(case["evidence_scenario"])
    assert bundle.appx.available is False
    assert bundle.services.available is False
    assert bundle.uninstall.available is True
    assert bundle.processes.available is True
    assert bundle.autostart.available is True
    assert bundle.appx.packages[0].package_full_name == case["evidence_scenario"]["appx"][0][
        "package_full_name"
    ]


# ---------- ② 兼容与缺省：旧形态 / 空对象 / 部分指定 ----------


def test_existing_shape_without_availability_stays_valid_and_true():
    """旧夹具形态（无 availability 键）仍合法，驱动按旧语义全 True。"""
    case = _case_with()
    _assert_schema_ok(case)
    _assert_availability(case, {source: True for source in SOURCES})


def test_empty_availability_object_defaults_all_true():
    case = _case_with({})
    _assert_schema_ok(case)
    _assert_availability(case, {source: True for source in SOURCES})


@pytest.mark.parametrize("source", SOURCES)
def test_single_source_false_does_not_touch_others(source):
    case = _case_with({source: False})
    _assert_schema_ok(case)
    expected = {name: name != source for name in SOURCES}
    _assert_availability(case, expected)


@pytest.mark.parametrize("source", SOURCES)
def test_single_source_true_keeps_others_default_true(source):
    case = _case_with({source: True})
    _assert_schema_ok(case)
    _assert_availability(case, {name: True for name in SOURCES})


def test_mixed_availability_flags_follow_declaration():
    case = _case_with({"uninstall": False, "appx": True, "services": False})
    _assert_schema_ok(case)
    _assert_availability(
        case,
        {
            "uninstall": False,
            "appx": True,
            "processes": True,
            "services": False,
            "autostart": True,
        },
    )


def test_all_false_keeps_positive_evidence():
    """全 False 时仍保留已观测的 entries/packages/paths，不推定成“无匹配”。"""
    case = _case_with({source: False for source in SOURCES})
    _assert_schema_ok(case)
    _assert_availability(case, {source: False for source in SOURCES})
    bundle = _build_bundle(case["evidence_scenario"])
    assert len(bundle.uninstall.entries) == 1
    assert len(bundle.appx.packages) == 1
    assert bundle.processes.paths
    assert bundle.services.paths
    assert len(bundle.autostart.entries) == 1


def test_bundle_json_keeps_declared_state_and_content():
    """真实 EvidenceBundle 的对外 JSON 也必须带 False 且不丢内容。"""
    case = _case_with({"appx": False, "services": False})
    _assert_schema_ok(case)
    data = _build_bundle(case["evidence_scenario"]).to_json_dict()
    assert data["uninstall"]["available"] is True
    assert data["appx"]["available"] is False
    assert data["processes"]["available"] is True
    assert data["services"]["available"] is False
    assert data["autostart"]["available"] is True
    assert data["uninstall"]["count"] == 1
    assert data["appx"]["count"] == 1
    assert data["appx"]["packages"][0]["name"] == "Sample.Store.App"
    assert data["processes"]["count"] == 1
    assert data["services"]["count"] == 1
    assert data["services"]["paths"] == case["evidence_scenario"]["services"]
    assert len(data["autostart"]["entries"]) == 1


# ---------- ② 旧 5 例兼容（字节/期望不动，状态全 True） ----------


def _case_ids() -> list[str]:
    return [path.stem for path in _case_files()]


@pytest.mark.parametrize("case_id", _case_ids())
def test_existing_regression_cases_remain_valid_and_available(case_id: str):
    sample = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
    _assert_schema_ok(sample)
    assert "availability" not in sample["evidence_scenario"]
    _assert_availability(sample, {source: True for source in SOURCES})


# ---------- ③ schema 拒绝坏类型（不得被 boolean 宽松吞掉） ----------


@pytest.mark.parametrize(
    "availability",
    [
        pytest.param(None, id="null"),
        pytest.param([], id="list-empty"),
        pytest.param([{"appx": False}], id="list-nonempty"),
        pytest.param("false", id="str"),
        pytest.param(0, id="int"),
        pytest.param(False, id="bool"),
    ],
)
def test_schema_rejects_non_object_availability(availability):
    case = _case_with(availability)
    errors = mini_validate(case, REG_SCHEMA)
    assert errors, "availability 非对象必须被拒绝"
    assert any("availability" in error for error in errors)


@pytest.mark.parametrize(
    "availability",
    [
        pytest.param({"reason": ""}, id="reason-key"),
        pytest.param({"incomplete": True}, id="incomplete-key"),
        pytest.param({"disk": False}, id="unknown-source"),
        pytest.param({"appx": False, "uninstall": True, "unit": True}, id="extra-key"),
    ],
)
def test_schema_rejects_unknown_availability_keys(availability):
    """reason/incomplete/其它源与多 unit 表达不属本卡，必须在 schema 层被拒。"""
    case = _case_with(availability)
    errors = mini_validate(case, REG_SCHEMA)
    assert errors
    assert any("availability" in error for error in errors)


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("bad_value", BAD_BOOLEAN_VALUES)
def test_schema_rejects_non_boolean_for_each_source(source, bad_value):
    case = _case_with({source: bad_value})
    errors = mini_validate(case, REG_SCHEMA)
    assert errors, f"{source}={bad_value!r} 必须被拒绝"
    assert any(f"availability.{source}" in error for error in errors)


def test_schema_rejects_bad_value_even_with_valid_siblings():
    case = _case_with({"uninstall": True, "appx": "false", "processes": True})
    errors = mini_validate(case, REG_SCHEMA)
    assert any("availability.appx" in error for error in errors)


def test_schema_keeps_existing_boundaries():
    """既有边界不因新增可选属性而放宽：缺字段/多余属性仍被拒绝。"""
    missing_required = _base_case()
    del missing_required["expect"]
    assert mini_validate(missing_required, REG_SCHEMA)

    missing_source = _base_case()
    del missing_source["evidence_scenario"]["services"]
    assert mini_validate(missing_source, REG_SCHEMA)

    extra_scenario_key = _base_case()
    extra_scenario_key["evidence_scenario"]["reason"] = ""
    assert mini_validate(extra_scenario_key, REG_SCHEMA)

    extra_case_key = _base_case()
    extra_case_key["availability"] = {"appx": False}
    assert mini_validate(extra_case_key, REG_SCHEMA)

    nested_in_entry = _base_case()
    nested_in_entry["evidence_scenario"]["uninstall"][0]["availability"] = False
    assert mini_validate(nested_in_entry, REG_SCHEMA)


# ---------- ④ 驱动层不得做 truthiness 归一化 ----------


@pytest.mark.parametrize(
    "availability",
    [
        pytest.param({"appx": 0}, id="int-0"),
        pytest.param({"appx": 1}, id="int-1"),
        pytest.param({"appx": "false"}, id="str-false"),
        pytest.param({"appx": None}, id="null"),
        pytest.param([], id="list"),
    ],
)
def test_driver_refuses_non_boolean_availability(availability):
    """绕过 schema 直接喂非法值时，驱动必须显式拒绝而不是按真假值归一。"""
    case = _case_with(availability)
    with pytest.raises(ValueError):
        _build_bundle(case["evidence_scenario"])


def test_driver_refuses_unknown_availability_key():
    """schema 外多出的源键不能被驱动静默忽略。"""
    case = _case_with({"disk": False, "appx": True})
    with pytest.raises(ValueError):
        _build_bundle(case["evidence_scenario"])
