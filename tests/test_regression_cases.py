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


def _case_files() -> list[Path]:
    return sorted(CASES_DIR.glob("R[0-9][0-9][0-9]-*.json"))


def _case_ids() -> list[str]:
    return [p.stem for p in _case_files()]


def _build_bundle(scenario: dict) -> EvidenceBundle:
    return EvidenceBundle(
        uninstall=UninstallResult(
            available=True, entries=[UninstallEntry(**e) for e in scenario["uninstall"]]
        ),
        appx=AppxResult(
            available=True, packages=[AppxPackage(**p) for p in scenario["appx"]]
        ),
        processes=ProcessResult(available=True, paths=list(scenario["processes"])),
        services=ServiceResult(available=True, paths=list(scenario["services"])),
        autostart=AutostartResult(
            available=True, entries=[AutostartEntry(**a) for a in scenario["autostart"]]
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
