# -*- coding: utf-8 -*-
"""T2-09 归属率一次性计算脚本（9.2 口径）。

口径：分母 = 全部判定单元数（candidates 总数）；分子 = 判为
已安装/系统组件/可再生/高置信残留/中置信残留 的单元数，
对应 confidence ∈ {受保护, 高, 中}（低 = 归属未知，仅计分母）。
高置信残留 = confidence=高 且证据链含 5.1 高档措辞"高度可能为残留"。
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

EVID = Path(r"E:\develop\project\diskaudit-wt\t209\docs\evidence\T2-09")
MACHINES = ["L1-acc-22h2", "L1-acc-24h2"]
SCANS = [("report_local.json", "%LOCALAPPDATA%"), ("report_roam.json", "%APPDATA%")]
NUM_CONF = {"受保护", "高", "中"}
HIGH_RESIDUE_MARK = "高度可能为残留"

# GT 11 件 → 单元路径匹配关键词（小写；人工逐一核对用）
GT_KEYWORDS = {
    "Chrome": ["google"],
    "Firefox": ["mozilla"],
    "7-Zip": ["7-zip", "7zip"],
    "Notepad++": ["notepad"],
    "Git": ["git"],
    "VS Code": ["code"],
    "微信": ["wechat", "weixin", "tencent"],
    "QQ NT": ["qq", "tencent"],
    "WPS": ["kingsoft", "wps"],
    "网易云音乐": ["netease", "cloudmusic"],
    "Steam": ["steam"],
}


def load_report(vm: str, fname: str) -> dict:
    return json.loads((EVID / vm / fname).read_text(encoding="utf-8"))


def high_residue(report: dict) -> list[str]:
    hits = []
    for c in report["candidates"]:
        if c["confidence"] == "高" and any(
            HIGH_RESIDUE_MARK in e.get("content", "") for e in c["evidence_chain"]
        ):
            hits.append(c["path"])
    return hits


def stats(report: dict) -> dict:
    conf = {}
    src = {}
    for c in report["candidates"]:
        conf[c["confidence"]] = conf.get(c["confidence"], 0) + 1
        src[c["verdict_source"]] = src.get(c["verdict_source"], 0) + 1
    total = len(report["candidates"])
    num = sum(n for k, n in conf.items() if k in NUM_CONF)
    return {"total": total, "num": num, "conf": conf, "src": src}


gt_hits: dict[str, list] = {k: [] for k in GT_KEYWORDS}
gt_missed = list(GT_KEYWORDS)

for vm in MACHINES:
    t_total = t_num = 0
    print(f"===== {vm} =====")
    residues = []
    for fname, label in SCANS:
        rep = load_report(vm, fname)
        s = stats(rep)
        t_total += s["total"]
        t_num += s["num"]
        print(
            f"[{label}] 单元总数={s['total']} 分子(受保护/高/中)={s['num']} "
            f"分母={s['total']} 归属率={s['num'] / s['total'] * 100:.2f}% "
            f"scan_root={rep['scan_root']}"
        )
        print(f"  按置信度: {s['conf']}")
        print(f"  按判定来源: {s['src']}")
        residues += high_residue(rep)
        for c in rep["candidates"]:
            name = c["path"].rstrip("\\/").rsplit("\\", 1)[-1].lower()
            for gt, kws in GT_KEYWORDS.items():
                if any(kw in name for kw in kws):
                    marks = "; ".join(
                        e.get("content", "")[:90] for e in c["evidence_chain"][:2]
                    )
                    gt_hits[gt].append(
                        (vm, label, c["path"], c["confidence"], c["verdict_source"], marks)
                    )
    rate = t_num / t_total * 100 if t_total else 0.0
    print(f"[{vm} 双范围合计] 单元总数={t_total} 分子={t_num} 归属率={rate:.2f}%")
    print(f"[{vm} 高置信残留单元] {len(residues)} 个: {residues}")

print("\n===== GT 11 件逐一核对（关键词命中单元，判定不得为高置信残留） =====")
for gt, hits in gt_hits.items():
    print(f"\n--- {gt} ({len(hits)} 个命中单元) ---")
    for vm, label, path, conf, srcv, marks in hits:
        flag = "  <-- 高置信残留!" if conf == "高" and HIGH_RESIDUE_MARK in marks else ""
        print(f"  [{vm}/{label}] {path} | 置信={conf} 来源={srcv}{flag}")
        print(f"      证据: {marks}")
    if not hits:
        print("  (扫描范围内无关键词命中单元)")
