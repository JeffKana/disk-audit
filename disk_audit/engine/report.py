"""report-v1 草案装配与 judge 编排（待办 D1/F1，任务卡 T2-02）。

依据：docs/schemas/report-v1.schema.json 草案（T2-07 定稿前按草案校验）、
5.2（可再生两档分别列示小计）、Q3（禁"可回收"字样与合并"可释放"总量）、
验收报告 §3.3（服务证据统一"唯一路径"口径——口径披露写入相关证据链 content，
因草案顶层 additionalProperties:false 不容新增字段，T2-07 定稿时再议独立字段）。

编排入口 judge_scan_result 消费 scan 子命令输出的 JSON；证据采集（collect_all）
与知识库装载（load_knowledge）是仅有的 I/O，判定本体为纯函数。
"""
from __future__ import annotations

from datetime import datetime

from ..evidence.evidence import EvidenceBundle, collect_all
from .judge import UnitInput, Verdict, judge_unit
from .knowledge import KnowledgeBase, load_knowledge

REPORT_SCHEMA_VERSION = "1.0"

# 5.2 可再生两档的类别归类（知识库 12 类 → 两档；其余类别不计入两档小计）
_REGENERABLE_CATEGORIES = ("更新缓存", "缓存/转储")
_REGENERABLE_CONFIRM_CATEGORIES = ("开发缓存",)


def _require_scan_result(scan: object) -> None:
    """校验输入为 scan 子命令的扫描结果 JSON；否则 ValueError（中文文案）。"""
    if not isinstance(scan, dict):
        raise ValueError("输入不是 scan 子命令的扫描结果 JSON：顶层应为对象")
    missing = [
        key
        for key in ("root", "units", "allocated_bytes", "logical_bytes", "skipped")
        if key not in scan
    ]
    if missing:
        raise ValueError(f"输入不是 scan 子命令的扫描结果 JSON：缺少字段 {'、'.join(missing)}")
    if not isinstance(scan["units"], list):
        raise ValueError("输入不是 scan 子命令的扫描结果 JSON：units 应为数组")


def build_report(scan: dict, verdicts: list[Verdict], *, incomplete: bool = False) -> dict:
    """判定结果 + scan 汇总 → report-v1 草案结构（Q3 双禁止天然满足：不产出该类字段）。

    incomplete（X-2/C7）：中止/异常产生的部分结果，totals 由该标记判无效；
    定稿前的草案 schema 不含该字段（T2-07 收录），故仅在不完整时输出。
    """
    units_by_path = {u["path"]: u for u in scan["units"]}
    candidates: list[dict] = []
    regenerable = 0
    regenerable_confirm = 0
    for verdict in verdicts:
        unit = units_by_path.get(verdict.path, {})
        allocated = int(unit.get("allocated_bytes", 0))
        if verdict.category in _REGENERABLE_CATEGORIES:
            regenerable += allocated
        elif verdict.category in _REGENERABLE_CONFIRM_CATEGORIES:
            regenerable_confirm += allocated
        candidates.append(
            {
                "path": verdict.path,
                "logical_bytes": int(unit.get("logical_bytes", 0)),
                "allocated_bytes": allocated,
                "confidence": verdict.confidence,
                "verdict_source": verdict.verdict_source,
                "evidence_chain": [e.to_json_dict() for e in verdict.evidence_chain],
                "suggested_action": verdict.suggested_action,
            }
        )
    skipped = scan["skipped"] if isinstance(scan["skipped"], dict) else {}
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scan_root": scan["root"],
        "totals": {
            "allocated_bytes": int(scan["allocated_bytes"]),
            "logical_bytes": int(scan["logical_bytes"]),
            "regenerable_subtotal": regenerable,
            "regenerable_confirm_subtotal": regenerable_confirm,
            "skipped_entries": int(skipped.get("total", 0)),
        },
        "candidates": candidates,
    }
    if incomplete:
        report["incomplete"] = True
    return report


def judge_scan_result(
    scan: dict,
    bundle: EvidenceBundle | None = None,
    kb: KnowledgeBase | None = None,
) -> dict:
    """对一份 scan 结果执行全量判定并装配报告（bundle/kb 可注入供测试）。"""
    _require_scan_result(scan)
    evidence = bundle if bundle is not None else collect_all()
    knowledge = kb if kb is not None else load_knowledge()
    verdicts = [judge_unit(UnitInput.from_scan_unit(u), evidence, knowledge) for u in scan["units"]]
    return build_report(scan, verdicts, incomplete=bool(scan.get("incomplete")))
