"""T2-04（待办 D6）判定回归样例数据驱动测试。

依据：9.1 底线二（真实误判当天进回归集）、开发规范 §3（数据驱动、样例与测试
分离、回归样例 JSON 一律脱敏）。三层校验：
① 每个样例通过 docs/schemas/regression-case-v1.schema.json；
② 每个样例全文件脱敏（无真实用户名/计算机名/SID，用户目录一律 <user>）；
③ 按样例输入（path_pattern + unit + evidence_scenario）驱动判定引擎
   （生产知识库 knowledge/entries.json），断言期望档位/来源与 forbidden_terms。
新增回归样例只需落 JSON 文件，本测试无需改动（数据驱动）。
"""
from __future__ import annotations

import getpass
import json
import os
import re
import socket
from pathlib import Path

import pytest

from disk_audit.engine.judge import UnitInput, judge_unit
from disk_audit.engine.knowledge import load_knowledge
from disk_audit.evidence.appx import AppxPackage, AppxResult
from disk_audit.evidence.autostart import AutostartEntry, AutostartResult
from disk_audit.evidence.evidence import EvidenceBundle
from disk_audit.evidence.processes import ProcessResult
from disk_audit.evidence.registry_uninstall import UninstallEntry, UninstallResult
from disk_audit.evidence.services import ServiceResult
from tests._mini_schema import mini_validate

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "tests" / "data" / "regression"
REG_SCHEMA = json.loads(
    (REPO_ROOT / "docs" / "schemas" / "regression-case-v1.schema.json").read_text(encoding="utf-8")
)
NOW_TS = 1_800_000_000.0
AVAILABILITY_SOURCES = ("uninstall", "appx", "processes", "services", "autostart")


def _case_files() -> list[Path]:
    return sorted(CASES_DIR.glob("R[0-9][0-9][0-9]-*.json"))


def _case_ids() -> list[str]:
    return [p.stem for p in _case_files()]


def _resolve_availability(scenario: dict) -> dict[str, bool]:
    """解析样例可选 availability（T6-01）：缺省/未指源=True，显式值必须是 bool。

    驱动层只消费状态，不做 truthiness 归一：绕过 schema 直接喂 0/1、字符串、
    null、数组或对象时显式拒绝，避免"看起来是 False"被静默当默认值。
    """
    declared = scenario.get("availability", {})
    if not isinstance(declared, dict):
        raise ValueError("evidence_scenario.availability 必须是对象")
    unknown = sorted(set(declared) - set(AVAILABILITY_SOURCES))
    if unknown:
        raise ValueError(f"evidence_scenario.availability 含未知源：{unknown}")
    resolved: dict[str, bool] = {}
    for source in AVAILABILITY_SOURCES:
        value = declared.get(source, True)
        if not isinstance(value, bool):
            raise ValueError(f"evidence_scenario.availability.{source} 必须是 boolean")
        resolved[source] = value
    return resolved


def _build_bundle(scenario: dict) -> EvidenceBundle:
    availability = _resolve_availability(scenario)
    return EvidenceBundle(
        uninstall=UninstallResult(
            available=availability["uninstall"],
            entries=[UninstallEntry(**e) for e in scenario["uninstall"]],
        ),
        appx=AppxResult(
            available=availability["appx"],
            packages=[AppxPackage(**p) for p in scenario["appx"]],
        ),
        processes=ProcessResult(
            available=availability["processes"], paths=list(scenario["processes"])
        ),
        services=ServiceResult(
            available=availability["services"], paths=list(scenario["services"])
        ),
        autostart=AutostartResult(
            available=availability["autostart"],
            entries=[AutostartEntry(**a) for a in scenario["autostart"]],
        ),
    )


# ---------- ① schema 校验 ----------


@pytest.mark.parametrize("case_path", _case_ids())
def test_sample_matches_regression_schema(case_path: str):
    sample = json.loads((CASES_DIR / f"{case_path}.json").read_text(encoding="utf-8"))
    assert mini_validate(sample, REG_SCHEMA) == []


def test_first_case_registered():
    """首例（Roaming\\Code ≠ openaicodex）必须在场（验收②）。"""
    assert (CASES_DIR / "R001-code-not-openaicodex.json").exists()
    assert len(_case_files()) >= 4  # 首例 + ≥3 个边界反例（验收③）


# ---------- ② 脱敏断言（验收④） ----------


@pytest.mark.parametrize("case_path", _case_ids())
def test_samples_are_sanitized(case_path: str):
    text = (CASES_DIR / f"{case_path}.json").read_text(encoding="utf-8")
    lowered = text.lower()
    real_user = (getpass.getuser() or "").lower()
    if real_user:
        assert real_user not in lowered, f"{case_path}：样例含真实用户名"
    machine = (os.environ.get("COMPUTERNAME") or socket.gethostname() or "").lower()
    if machine:
        assert machine not in lowered, f"{case_path}：样例含真实计算机名"
    assert not re.search(r"S-1-5(?:-\d+){2,}", text), f"{case_path}：样例含 SID"
    sample = json.loads(text)
    assert "<user>" in sample["path_pattern"], f"{case_path}：用户目录未用 <user> 占位"


# ---------- ③ 引擎判定断言（数据驱动） ----------


@pytest.mark.parametrize("case_path", _case_ids())
def test_engine_verdict_matches_expectation(case_path: str):
    sample = json.loads((CASES_DIR / f"{case_path}.json").read_text(encoding="utf-8"))
    resolved_path = sample["path_pattern"].replace("<user>", "u")
    unit = UnitInput.from_scan_unit({**sample["unit"], "path": resolved_path})
    verdict = judge_unit(unit, _build_bundle(sample["evidence_scenario"]),
                         load_knowledge(), now_ts=NOW_TS)
    expect = sample["expect"]
    assert verdict.confidence == expect["confidence"], sample["case_id"]
    assert verdict.verdict_source == expect["verdict_source"], sample["case_id"]
    blob = json.dumps(verdict.to_json_dict(), ensure_ascii=False)
    for term in expect.get("forbidden_terms", []):
        assert term not in blob, f"{sample['case_id']}：输出出现禁词 {term}"
