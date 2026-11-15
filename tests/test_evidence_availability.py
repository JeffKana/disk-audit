r"""T5-06 证据源可用性纠偏回归（T506-v1）。

依据：F1 §5.1 高档五证据（注册表无卸载记录 + 无匹配进程/服务 + 无自启动 +
目录陈旧>180天 + KB 标注已停止）、§5.3 A1~A5、R9（提权零外部程序/联网）、
任务卡 T5-06 验收②~⑤、PM 只读探针 evidence-degrade-probe.json（合成复现，
非真实用户误判）。

核心反例：采集源 available=False（降级）不得当成已核验的"无匹配"，
不得给高档残留、不得虚写缺席；只有 available=True 且无命中才计入该"无"项。
测试全部使用合成输入与注入式只读替身，不碰真实注册表/用户目录/VM/UAC。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from disk_audit import elevated
from disk_audit.engine import texts
from disk_audit.engine.judge import UnitInput, judge_unit
from disk_audit.engine.knowledge import build_knowledge
from disk_audit.engine.render import render_report
from disk_audit.engine.report import build_report, judge_scan_result
from disk_audit.evidence import autostart as autostart_mod
from disk_audit.evidence.appx import AppxResult
from disk_audit.evidence.autostart import AutostartResult
from disk_audit.evidence.evidence import EvidenceBundle
from disk_audit.evidence.processes import ProcessResult
from disk_audit.evidence.registry_uninstall import UninstallResult
from disk_audit.evidence.services import ServiceResult
from tests._mini_schema import mini_validate

_REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (_REPO_ROOT / "docs" / "schemas" / "report-v1.schema.json").read_text(encoding="utf-8")
)

NOW_TS = 1_800_000_000.0
RECENT = NOW_TS - 10 * 86400          # 未陈旧
STALE = NOW_TS - 400 * 86400          # 陈旧 >180 天
BOUNDARY = NOW_TS - 180 * 86400       # 恰好 180 天
OVER = NOW_TS - 181 * 86400           # 181 天

KB = build_knowledge([
    {"name": "oldapp", "product": "OldApp 停运产品", "vendor": "OldCorp",
     "aliases": [], "category": "残留候选·高置信", "lifecycle": "已停止",
     "regex_family": None, "source": "公开软件名", "notes": "公开下线依据（测试）"},
])

UNIT_PATH = r"C:\Users\u\AppData\Local\OldApp"

# F1 五项分组所依赖的四个必要采集源 → 定稿 schema 九值枚举中的对应 source
SOURCE_ENUM = {
    "uninstall": "注册表卸载项",
    "processes": "进程",
    "services": "服务",
    "autostart": "自启动",
}

# 既有高档残留证据链（全部必要源可用且空 + KB 已停止 + 陈旧），逐字守护
FULL_HIGH_CHAIN = [
    "高度可能为残留；删除前请确认",
    "知识库标注已停止：OldApp 停运产品",
    "注册表无卸载记录",
    "无匹配进程/服务/自启动",
    "目录陈旧：400 天未修改（> 180 天）",
]


def _unit(max_mtime: float = STALE) -> UnitInput:
    return UnitInput(
        path=UNIT_PATH, files=3, dirs=1, logical_bytes=4096,
        allocated_bytes=8192, max_mtime=max_mtime, exe_files=1,
    )


def _bundle(
    *,
    uninstall: bool = True,
    processes: bool = True,
    services: bool = True,
    autostart: bool = True,
    appx: bool = True,
    reg_entries: tuple = (),
    proc_paths: tuple = (),
    svc_paths: tuple = (),
    autostart_entries: tuple = (),
) -> EvidenceBundle:
    """合成 EvidenceBundle：逐源 available 可控，默认全部完成且无命中。"""
    bundle = EvidenceBundle()
    bundle.uninstall = UninstallResult(available=uninstall, entries=list(reg_entries))
    bundle.processes = ProcessResult(available=processes, paths=list(proc_paths))
    bundle.services = ServiceResult(available=services, paths=list(svc_paths))
    bundle.autostart = AutostartResult(available=autostart, entries=list(autostart_entries))
    bundle.appx = AppxResult(available=appx, packages=[])
    return bundle


def _contents(verdict) -> list[str]:
    return [item.content for item in verdict.evidence_chain]


def _sources(verdict) -> list[str]:
    return [item.source for item in verdict.evidence_chain]


def _assert_legal_sources(verdict) -> None:
    legal = set(texts.EVIDENCE_SOURCE_ENUM)
    for item in verdict.evidence_chain:
        assert item.source in legal, f"非法证据来源：{item.source!r}"


def _scan(max_mtime: float = STALE) -> dict:
    return {
        "root": r"C:\Users\u\AppData\Local",
        "units": [{
            "path": UNIT_PATH, "files": 3, "dirs": 1,
            "logical_bytes": 4096, "allocated_bytes": 8192,
            "max_mtime": max_mtime, "exe_files": 1,
        }],
        "allocated_bytes": 8192,
        "logical_bytes": 4096,
        "skipped": {"total": 0},
    }


# ============================================================================
# 验收②：逐源不可用 / 组合不可用 —— 不达高档、不虚写缺席、明确披露
# ============================================================================


@pytest.mark.parametrize("bad_source", ["uninstall", "processes", "services", "autostart"])
def test_single_source_unavailable_never_high(bad_source):
    """单源不可用：五个必要源缺一，高档五证据不成立，绝不给高档残留。"""
    verdict = judge_unit(_unit(), _bundle(**{bad_source: False}), KB, now_ts=NOW_TS)
    assert verdict.confidence != "高"
    assert verdict.confidence == "中"          # 缺一：仍 ≥2 项成立 → 保守中档
    assert verdict.verdict_source == "知识库"


@pytest.mark.parametrize("bad_source", ["uninstall", "processes", "services", "autostart"])
def test_single_source_unavailable_discloses_in_chain(bad_source):
    """每个受影响候选证据链明确披露未完成的必要源（不可用 ≠ 无匹配）。"""
    verdict = judge_unit(_unit(), _bundle(**{bad_source: False}), KB, now_ts=NOW_TS)
    enum = SOURCE_ENUM[bad_source]
    disclosed = [
        item for item in verdict.evidence_chain
        if item.source == enum and "不可用" in item.content
    ]
    assert disclosed, f"未披露 {bad_source} 不可用：{_contents(verdict)}"


@pytest.mark.parametrize("bad_source", ["uninstall", "processes", "services", "autostart"])
def test_degraded_chain_has_no_unverified_absence_claim(bad_source):
    """不输出未经核验的"注册表无卸载记录"或合并"无匹配进程/服务/自启动"。"""
    verdict = judge_unit(_unit(), _bundle(**{bad_source: False}), KB, now_ts=NOW_TS)
    blob = "".join(_contents(verdict))
    assert "无匹配进程/服务/自启动" not in blob
    if bad_source == "uninstall":
        assert "注册表无卸载记录" not in blob
    _assert_legal_sources(verdict)
    assert _contents(verdict)[0] == texts.CONFIDENCE_WORDING[verdict.confidence]


@pytest.mark.parametrize(
    "flags,expected",
    [
        ({"uninstall": False, "processes": False, "services": False, "autostart": False}, "中"),
        ({"processes": False, "services": False}, "中"),
        ({"uninstall": False, "autostart": False}, "中"),
        ({"uninstall": False, "processes": False, "services": False,
          "autostart": False}, "中"),
    ],
)
def test_multi_source_unavailable_never_high(flags, expected):
    """多源/组合不可用：证据不足时不达高档。"""
    verdict = judge_unit(_unit(), _bundle(**flags), KB, now_ts=NOW_TS)
    assert verdict.confidence == expected
    _assert_legal_sources(verdict)
    assert "无匹配进程/服务/自启动" not in "".join(_contents(verdict))


def test_all_sources_unavailable_and_not_stale_is_conservative_low():
    """仅 KB 已停止一项成立（四源全不可用且未陈旧）→ 保守低档、固定 A5。"""
    flags = {"uninstall": False, "processes": False, "services": False, "autostart": False}
    verdict = judge_unit(_unit(max_mtime=RECENT), _bundle(**flags), KB, now_ts=NOW_TS)
    assert verdict.confidence == "低"
    assert verdict.suggested_action == "A5"
    assert _contents(verdict)[0] == texts.CONFIDENCE_WORDING["低"]


def test_scoring_uses_five_groups_not_string_count():
    """计分以五项分组而非证据链字段/字符串数量：多项披露不等于多项成立。"""
    flags = {"uninstall": False, "processes": False, "services": False, "autostart": False}
    verdict = judge_unit(_unit(max_mtime=RECENT), _bundle(**flags), KB, now_ts=NOW_TS)
    # 证据链条目很多（逐源披露），但成立的五项只有 KB 一项 → 低档
    assert len(verdict.evidence_chain) >= 5
    assert verdict.confidence == "低"


def test_unavailable_source_discloses_not_claims_absence_for_that_source():
    """不可用源只做披露，不产出该源的"无匹配"结论（不可用 ≠ 无匹配）。"""
    verdict = judge_unit(
        _unit(), _bundle(uninstall=False, processes=False, services=False, autostart=False),
        KB, now_ts=NOW_TS,
    )
    blob = "".join(_contents(verdict))
    assert blob.count("不可用") >= 4
    assert "无匹配进程/服务/自启动" not in blob
    assert "注册表无卸载记录" not in blob


# ============================================================================
# 验收②：新旧 / 180 天边界（降级与全可用两条路径都要守住）
# ============================================================================


@pytest.mark.parametrize("mtime,expected", [(BOUNDARY, "中"), (OVER, "高")])
def test_staleness_boundary_full_available(mtime, expected):
    """全可用：恰好 180 天不达高档（中），181 天五证据齐（高）。既有边界不变。"""
    verdict = judge_unit(_unit(max_mtime=mtime), _bundle(), KB, now_ts=NOW_TS)
    assert verdict.confidence == expected


@pytest.mark.parametrize("mtime", [BOUNDARY, OVER])
def test_staleness_boundary_degraded_never_high(mtime):
    """降级路径：无论是否陈旧，缺源都不达高档。"""
    verdict = judge_unit(
        _unit(max_mtime=mtime), _bundle(processes=False, services=False), KB, now_ts=NOW_TS
    )
    assert verdict.confidence != "高"


# ============================================================================
# 验收③：正向守护 —— 完整五证据 / 仅 Appx 不可用 / 正命中优先 / 硬保护
# ============================================================================


def test_full_five_evidence_keeps_existing_high_and_chain():
    """全部必要源可用且空 + KB 已停止 + 陈旧：既有高档与合法证据链逐字不变。"""
    verdict = judge_unit(_unit(), _bundle(), KB, now_ts=NOW_TS)
    assert verdict.confidence == "高"
    assert verdict.verdict_source == "知识库"
    assert verdict.suggested_action == "A2"
    assert _contents(verdict) == FULL_HIGH_CHAIN
    assert _sources(verdict) == ["知识库", "知识库", "注册表卸载项", "知识库", "启发式"]


def test_only_appx_unavailable_does_not_change_high():
    """Appx 不是额外高档必要条件：仅 Appx 不可用不改变既有高档与证据链。"""
    verdict = judge_unit(_unit(), _bundle(appx=False), KB, now_ts=NOW_TS)
    assert verdict.confidence == "高"
    assert _contents(verdict) == FULL_HIGH_CHAIN


def test_positive_registry_hit_wins_even_when_other_sources_unavailable():
    """即使 available=False 仍有正命中也保留在用正证据，不升级为高残留。"""
    verdict = judge_unit(
        _unit(),
        _bundle(processes=False, services=False, autostart=False,
                reg_entries=[_reg("OldApp Suite")]),
        KB, now_ts=NOW_TS,
    )
    assert verdict.verdict_source == "注册表"
    assert verdict.confidence == "高"


def test_positive_process_hit_wins_even_when_source_marked_unavailable():
    """进程源 available=False 但含正命中路径 → 在用正证据优先，不被丢掉。"""
    proc_path = UNIT_PATH + r"\bin\oldapp.exe"
    verdict = judge_unit(
        _unit(),
        _bundle(processes=False, services=False, autostart=False, proc_paths=[proc_path]),
        KB, now_ts=NOW_TS,
    )
    assert verdict.verdict_source == "进程服务"
    assert verdict.confidence == "高"


def test_hard_protection_still_first():
    """硬保护最前短路：降级 bundle 下受保护目录仍为"受保护"。"""
    protected = UnitInput(
        path=r"C:\Users\u\AppData\Roaming\Microsoft\Protect", files=1, dirs=0,
        logical_bytes=1024, allocated_bytes=1024, max_mtime=STALE, exe_files=1,
    )
    flags = {"uninstall": False, "processes": False, "services": False, "autostart": False}
    verdict = judge_unit(protected, _bundle(**flags), KB, now_ts=NOW_TS)
    assert verdict.confidence == "受保护"
    assert verdict.verdict_source == "硬保护"


def _reg(display_name: str):
    from disk_audit.evidence.registry_uninstall import UninstallEntry

    return UninstallEntry(
        display_name=display_name, publisher="", install_location="",
        install_date="", uninstall_string="", reg_path=r"HKCU\SOFTWARE\...\Uninstall",
    )


# ============================================================================
# 验收④：真实 collect_evidence_readonly + 注入只读采集替身 → judge→report→render
# ============================================================================


class _ReadOnlyWinreg:
    """只读 winreg 替身：仅提供读取所需常量/方法，任何写访问立即 AssertionError。

    OpenKey 一律抛 OSError（合成"键不存在"），使真实采集器走 X-1 空结果路径；
    不接触真实注册表。
    """

    HKEY_LOCAL_MACHINE = 1
    HKEY_CURRENT_USER = 2
    KEY_READ = 3

    def OpenKey(self, *args, **kwargs):
        raise OSError("synthetic read-only substitute: no registry key")

    def __getattr__(self, name):
        raise AssertionError(f"只读替身禁止访问 winreg.{name}（疑似注册表写入/外部访问）")


@pytest.fixture()
def r9_bundle(monkeypatch):
    """用真实 collect_evidence_readonly + 注入只读替身产生 R9 降级 bundle。"""
    monkeypatch.setattr(autostart_mod, "default_startup_folders", lambda: [])
    bundle = elevated.collect_evidence_readonly(winreg_module=_ReadOnlyWinreg())
    return bundle


def test_r9_bundle_shape_is_degraded(r9_bundle):
    """R9 降级 bundle：只读注册表源可用且空，外部程序三源不可用。"""
    assert r9_bundle.uninstall.available is True
    assert r9_bundle.autostart.available is True
    assert r9_bundle.appx.available is False
    assert r9_bundle.processes.available is False
    assert r9_bundle.services.available is False
    assert not r9_bundle.uninstall.entries
    assert not r9_bundle.autostart.entries
    assert not r9_bundle.processes.paths
    assert not r9_bundle.services.paths


def test_r9_readonly_chain_judge_report_render_has_no_false_absence_or_high(r9_bundle):
    """合成链路 judge→build_report→render：无虚假缺席说明、无高档、schema 通过。"""
    verdict = judge_unit(_unit(), r9_bundle, KB, now_ts=NOW_TS)
    assert verdict.confidence != "高"
    blob = "".join(_contents(verdict))
    assert "无匹配进程/服务/自启动" not in blob
    assert "不可用" in blob
    _assert_legal_sources(verdict)

    report = build_report(_scan(), [verdict])
    assert mini_validate(report, SCHEMA) == []
    candidate = report["candidates"][0]
    candidate_blob = "".join(item["content"] for item in candidate["evidence_chain"])
    assert "无匹配进程/服务/自启动" not in candidate_blob
    assert candidate["confidence"] != "高"
    assert "不可用" in candidate_blob
    html = render_report(report)
    assert "无匹配进程/服务/自启动" not in html
    assert html  # 渲染成功，未被九值枚举校验拒绝


def test_judge_scan_result_with_r9_bundle_produces_no_high(r9_bundle):
    """真实 judge_scan_result（judge→build_report）装配：降级 bundle 不产高档候选。"""
    scan = _scan(max_mtime=time.time() - 400 * 86400)
    report = judge_scan_result(scan, bundle=r9_bundle, kb=KB)
    assert mini_validate(report, SCHEMA) == []
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["confidence"] != "高"
    assert "无匹配进程/服务/自启动" not in "".join(
        item["content"] for item in report["candidates"][0]["evidence_chain"]
    )


# ============================================================================
# 验收⑤：探针新结果须区分"不可用"与"已核验无匹配"；纯函数/无外部能力
# ============================================================================


def test_probe_unavailable_differs_from_available_no_match():
    """PM 探针新结果：unavailable 与 available-no-match 不再同一高档/同一证据链。"""
    unavailable = judge_unit(
        _unit(), _bundle(processes=False, services=False, appx=False), KB, now_ts=NOW_TS
    )
    available = judge_unit(_unit(), _bundle(), KB, now_ts=NOW_TS)
    assert available.confidence == "高"
    assert unavailable.confidence != available.confidence
    assert _contents(unavailable) != _contents(available)
    assert "不可用" in "".join(_contents(unavailable))
    assert "无匹配进程/服务/自启动" not in "".join(_contents(unavailable))


def test_judge_unit_signature_unchanged_and_no_override():
    """judge 仍为纯函数入口，无覆盖/跳过/配置参数；新增逻辑不改变公共签名。"""
    import inspect

    params = set(inspect.signature(judge_unit).parameters)
    assert params == {"unit", "bundle", "kb", "now_ts"}
    assert not any("override" in p or "config" in p or "skip" in p for p in params)


def test_degraded_verdicts_pass_report_schema():
    """降级候选经 build_report 装配仍通过定稿 schema（枚举/字段合法）。"""
    for flags in (
        {"uninstall": False},
        {"processes": False},
        {"services": False},
        {"autostart": False},
        {"processes": False, "services": False},
        {"uninstall": False, "processes": False, "services": False, "autostart": False},
    ):
        verdict = judge_unit(_unit(), _bundle(**flags), KB, now_ts=NOW_TS)
        report = build_report(_scan(), [verdict])
        assert mini_validate(report, SCHEMA) == [], flags


def test_new_chinese_texts_in_t506_zone_only_and_no_q3_terms():
    """新增中文资源集中在 texts 本卡追加区；旧文案/四档措辞/枚举不变、无 Q3 禁词。"""
    assert texts.CONFIDENCE_WORDING["高"] == "高度可能为残留；删除前请确认"
    assert texts.CONFIDENCE_WORDING["中"] == "疑似残留，建议核对证据"
    assert texts.CONFIDENCE_WORDING["低"] == "归属未知，需人工判断"
    assert texts.CONFIDENCE_WORDING["受保护"] == "受保护，不可处理"
    assert texts.EVIDENCE_SOURCE_ENUM == (
        "硬保护", "知识库", "注册表卸载项", "进程", "服务", "自启动",
        "Appx", "启发式", "文件枚举",
    )
    zone = getattr(texts, "T506_TEXTS", None)
    assert isinstance(zone, dict) and zone
    blob = "".join(zone.values())
    assert "可回收" not in blob
    assert "可释放" not in blob
    assert "不可用" in blob
