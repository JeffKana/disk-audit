"""T2-03（待办 D2+D3）置信度四档打标与可再生两档测试。

依据：方案 5.1（四档触发条件与输出措辞，逐字）、5.2（两档归类与表述，逐字）、
Q3（禁"可回收"与合并"可释放"总量）、S-2（仅启发式上限锁"低"）、开发规范 §1
（对外文案集中在文案资源处）。文案资源 = disk_audit/engine/texts.py。

高档触发 = 5 项证据同时成立（KB 标注"已停止" + 注册表无卸载记录 + 无匹配
进程/服务 + 无自启动 + 陈旧 >180 天）；缺一降中（缺"在用"类证据时降中，
缺"无注册表/无运行"类证据则该单元本属已安装/在用，走正向判定层，见矩阵）。
"""
from __future__ import annotations

import os

import pytest

from disk_audit.engine import texts
from disk_audit.engine.judge import UnitInput, judge_unit
from disk_audit.engine.knowledge import build_knowledge
from disk_audit.engine.report import _REGENERABLE_CATEGORIES, _REGENERABLE_CONFIRM_CATEGORIES
from tests.test_engine_judge import KB, NOW_TS, RECENT, STALE, _bundle, _reg, _unit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------- 验收②：措辞枚举与方案 5.1/5.2 对照表断言（逐字） ----------


def test_confidence_wording_matches_plan_5_1():
    """方案 5.1 输出措辞四档，逐字摘自方案定稿 HTML 表格。"""
    assert texts.CONFIDENCE_WORDING["高"] == "高度可能为残留；删除前请确认"
    assert texts.CONFIDENCE_WORDING["中"] == "疑似残留，建议核对证据"
    assert texts.CONFIDENCE_WORDING["低"] == "归属未知，需人工判断"
    assert texts.CONFIDENCE_WORDING["受保护"] == "受保护，不可处理"


def test_high_wording_parts_verbatim():
    """高档在方案表格中为两短句（"高度可能为残留"＋"删除前请确认"），
    输出串以"；"连接（呈现决定），两短句必须逐字保留。"""
    assert texts.CONFIDENCE_HIGH_PARTS == ("高度可能为残留", "删除前请确认")
    for part in texts.CONFIDENCE_HIGH_PARTS:
        assert part in texts.CONFIDENCE_WORDING["高"]


def test_regenerable_wording_matches_plan_5_2():
    """方案 5.2 两档表述，逐字摘自方案定稿 HTML。"""
    assert texts.REGENERABLE_WORDING == "可再生：应用会自行重建"
    assert texts.REGENERABLE_CONFIRM_WORDING == (
        "可再生但需确认：清理后需重新下载，可能影响离线构建"
    )


def test_wording_resources_have_no_forbidden_terms():
    """Q3：文案资源全文不含"可回收"，不含"可释放"合并总量表述。"""
    blob = "".join(
        list(texts.CONFIDENCE_WORDING.values())
        + list(texts.CONFIDENCE_HIGH_PARTS)
        + [texts.REGENERABLE_WORDING, texts.REGENERABLE_CONFIRM_WORDING]
    )
    assert "可回收" not in blob
    assert "可释放" not in blob


# ---------- 验收①：参数化用例覆盖每档触发组合（含高档缺一降中边界） ----------


@pytest.mark.parametrize(
    "unit_name,max_mtime,expected_confidence,expected_source,reason",
    [
        ("oldapp", STALE, "高", "知识库", "5 证据同时成立：已停止+无注册表+无运行+无自启动+陈旧"),
        ("oldapp", RECENT, "中", "知识库", "高档缺「陈旧」→降中（已停止+无运行=2 项成立）"),
        ("sun", STALE, "中", "知识库", "KB 命中缺生命周期→中（含陈旧不升档）"),
        ("sun", RECENT, "中", "知识库", "KB 命中缺生命周期→中"),
        ("zzz-unknown-tail", STALE, "低", "启发式", "无 KB，仅启发式（陈旧）→S-2 上限锁低"),
        ("zzz-unknown-tail", RECENT, "低", "启发式", "无 KB 无信号→未知长尾低"),
    ],
)
def test_confidence_matrix(unit_name, max_mtime, expected_confidence, expected_source, reason):
    verdict = judge_unit(_unit(unit_name, max_mtime=max_mtime), _bundle(), KB, now_ts=NOW_TS)
    assert verdict.confidence == expected_confidence, reason
    assert verdict.verdict_source == expected_source, reason


def test_high_breaks_absence_routes_to_installed_not_medium():
    """高档缺"无注册表"证据：单元本属已安装，走注册表正向判定，而非降中。"""
    verdict = judge_unit(
        _unit("oldapp", max_mtime=STALE), _bundle(uninstall=[_reg("OldApp Suite")]),
        KB, now_ts=NOW_TS,
    )
    assert verdict.verdict_source == "注册表"
    assert verdict.confidence == "高"


def test_high_breaks_no_active_routes_to_in_use():
    """高档缺"无匹配进程/服务"证据：单元在用，走运行证据正向判定。"""
    verdict = judge_unit(
        _unit("oldapp", max_mtime=STALE),
        _bundle(processes=[r"C:\Users\u\AppData\Roaming\oldapp\bin\oldapp.exe"]),
        KB, now_ts=NOW_TS,
    )
    assert verdict.verdict_source == "进程服务"
    assert verdict.confidence == "高"


# ---------- 5.1 输出措辞注入判定输出（首条证据链） ----------


def test_wording_injected_into_verdict_output():
    """四档措辞作为判定输出的首条证据链，档位→措辞可追溯。"""
    protected = judge_unit(_unit(r"Microsoft\Protect"), _bundle(), KB, now_ts=NOW_TS)
    assert protected.evidence_chain[0].content == texts.CONFIDENCE_WORDING["受保护"]

    high = judge_unit(_unit("oldapp", max_mtime=STALE), _bundle(), KB, now_ts=NOW_TS)
    assert high.evidence_chain[0].content == texts.CONFIDENCE_WORDING["高"]

    medium = judge_unit(_unit("sun"), _bundle(), KB, now_ts=NOW_TS)
    assert medium.evidence_chain[0].content == texts.CONFIDENCE_WORDING["中"]

    low = judge_unit(_unit("zzz-unknown-tail"), _bundle(), KB, now_ts=NOW_TS)
    assert low.evidence_chain[0].content == texts.CONFIDENCE_WORDING["低"]


def test_installed_verdicts_carry_no_residual_wording():
    """已安装/在用判定不属于残留档位，不得携带 5.1 残留措辞。"""
    installed = judge_unit(
        _unit("vscode"), _bundle(uninstall=[_reg("VS Code")]), KB, now_ts=NOW_TS
    )
    for item in installed.evidence_chain:
        assert item.content != texts.CONFIDENCE_WORDING["高"]


def test_updater_carries_regenerable_wording_verbatim():
    """更新缓存（*-updater）证据链携带 5.2 可再生表述逐字原文。"""
    verdict = judge_unit(_unit("xmind-vana-updater"), _bundle(), KB, now_ts=NOW_TS)
    assert any(
        item.content == texts.REGENERABLE_WORDING for item in verdict.evidence_chain
    )


# ---------- 验收④：低置信项固定 A5、无倾向表述 ----------


@pytest.mark.parametrize("unit_name,max_mtime", [
    ("zzz-unknown-tail", RECENT),
    ("zzz-unknown-tail", STALE),
    ("0123456789abcdef0123456789abcdef", RECENT),
])
def test_low_confidence_fixed_a5_and_neutral_wording(unit_name, max_mtime):
    verdict = judge_unit(_unit(unit_name, max_mtime=max_mtime, exe_files=0), _bundle(), KB, now_ts=NOW_TS)
    assert verdict.confidence == "低"
    assert verdict.suggested_action == "A5"
    assert verdict.evidence_chain[0].content == "归属未知，需人工判断"


# ---------- 5.2 两档归类范围 ----------


def test_regenerable_bucket_categories_match_plan_5_2():
    """可再生 = 更新缓存/缓存转储（含 %TEMP%、Windows 更新缓存、崩溃转储、
    应用更新缓存、浏览器与应用缓存）；需确认 = 开发缓存（npm/pip/uv/yarn/
    pnpm/gradle/maven/模型缓存等）。"""
    assert set(_REGENERABLE_CATEGORIES) == {"更新缓存", "缓存/转储"}
    assert set(_REGENERABLE_CONFIRM_CATEGORIES) == {"开发缓存"}
