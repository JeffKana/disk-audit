"""5000 行性能样张构造器（待办 F5，任务卡 T3-03；tests 夹具，不入产品运行时）。

数据分布复用 POC-4 生成器 docs/upstream/poc/poc4_gen_bigreport.py（同名池、
random.seed(42)、N=5000），按 report-v1 定稿 schema（docs/schemas/report-v1.schema.json）
映射为合法报告 dict，喂 render_report 产出测量样张。与 W0 基线同口径：

- 路径/类别/置信度/大小/陈旧天数：POC-4 同分布同种子；
- POC 判定来源池（知识库/注册表/商店包/进程服务/启发式兜底/硬保护规则）→
  schema verdict_source 六值枚举映射；
- 证据链 source 取 schema 九值枚举；content 沿用 POC 证据句式；
- 建议动作按置信度映射（高→A2 / 中→A4 / 低→A5 / 受保护→A5，与判定引擎
  语义一致，覆盖受保护与低置信固定 A5 的口径）；
- 占用空间 = 逻辑大小按 4096B 簇上取整（DR-004 占用空间口径的简化态）；
- totals 两档小计按 POC 类别映射（缓存/转储、更新缓存 → 可再生；开发缓存 →
  可再生但需确认），skipped_entries 取固定值。

仅供性能测量与字节数单测使用；判定正确性不归本模块（judge 测试另有覆盖）。
"""
from __future__ import annotations

import random

_GENERATED_AT = "2026-11-01T12:00:00+08:00"
_SCAN_ROOT = r"C:\Users\testuser\AppData"

# POC-4 数据池（docs/upstream/poc/poc4_gen_bigreport.py 原样保留）
_CATS = [
    "已安装应用", "残留候选·高置信", "残留候选·中置信", "残留候选·低置信",
    "开发缓存", "更新缓存", "系统组件", "游戏数据", "容器", "缓存/转储",
]
_NAMES = [
    "Tencent", "kingsoft", "Sun", "Netease", "obsidian-updater", "xmind-updater",
    "apifox-updater", "notion-updater", "deepseek-updater", "b1", "tidalab",
    "Yii.Guxing", "chat_pp", "dzip_pp", "tabx_pp", "qq_guild", "alixby",
    "Electron", "CEF", "AgoraAudio", "VoipNNModel", "WNS", "Cache",
    "360safe", "Ludashi", "DrvMgr", "lds", "fastpdf_core", "Microsoft",
]
_CONF = ["高", "中", "低", "受保护"]

# POC 判定来源池 → report-v1 schema verdict_source 枚举
_SRC_MAP = {
    "知识库": "知识库",
    "注册表": "注册表",
    "商店包": "Appx",
    "进程/服务": "进程服务",
    "启发式兜底": "启发式",
    "硬保护规则": "硬保护",
}
# 证据链 source（schema 九值枚举）
_EVIDENCE_SOURCE_MAP = {
    "知识库": "知识库",
    "注册表": "注册表卸载项",
    "商店包": "Appx",
    "进程/服务": "进程",
    "启发式兜底": "启发式",
    "硬保护规则": "硬保护",
}
_POCSRC = list(_SRC_MAP)

# POC 类别 → 5.2 可再生两档小计（其余类别不计入两小计）
_REGENERABLE_CATS = {"更新缓存", "缓存/转储"}
_REGENERABLE_CONFIRM_CATS = {"开发缓存"}

_ACTION_BY_CONFIDENCE = {"高": "A2", "中": "A4", "低": "A5", "受保护": "A5"}

_CLUSTER = 4096


def _allocated(logical: int) -> int:
    """逻辑大小按簇上取整（DR-004 占用空间口径的简化态，样张专用）。"""
    if logical <= 0:
        return 0
    return ((logical + _CLUSTER - 1) // _CLUSTER) * _CLUSTER


def build_big_report(n: int = 5000, seed: int = 42) -> dict:
    """构造 n 条候选的 report-v1 报告 dict（POC-4 同分布；罐装脱敏路径）。"""
    rng = random.Random(seed)
    candidates: list[dict] = []
    regenerable = 0
    regenerable_confirm = 0
    allocated_total = 0
    logical_total = 0
    for _ in range(n):
        name = rng.choice(_NAMES) + ("" if rng.random() < 0.5 else "_%d" % rng.randint(1, 999))
        cat = rng.choice(_CATS)
        conf = rng.choice(_CONF)
        size = rng.choice(
            [rng.randint(1, 500), rng.randint(500, 90000), rng.randint(90000, 610000)]
        )
        alloc = _allocated(size)
        src_poc = rng.choice(_POCSRC)
        age = rng.randint(3, 1500)
        path = r"C:\Users\testuser\AppData\%s\%s" % (rng.choice(["Roaming", "Local"]), name)
        evidence = [
            {
                "source": _EVIDENCE_SOURCE_MAP[src_poc],
                "content": "%s 命中；注册表无卸载记录；无关联进程；最后修改 %d 天前"
                % (src_poc, age),
            }
        ]
        candidates.append(
            {
                "path": path,
                "logical_bytes": size,
                "allocated_bytes": alloc,
                "confidence": conf,
                "verdict_source": _SRC_MAP[src_poc],
                "evidence_chain": evidence,
                "suggested_action": _ACTION_BY_CONFIDENCE[conf],
            }
        )
        allocated_total += alloc
        logical_total += size
        if cat in _REGENERABLE_CATS:
            regenerable += alloc
        elif cat in _REGENERABLE_CONFIRM_CATS:
            regenerable_confirm += alloc
    return {
        "schema_version": "1.0",
        "generated_at": _GENERATED_AT,
        "scan_root": _SCAN_ROOT,
        "totals": {
            "allocated_bytes": allocated_total,
            "logical_bytes": logical_total,
            "regenerable_subtotal": regenerable,
            "regenerable_confirm_subtotal": regenerable_confirm,
            "skipped_entries": 3,
        },
        "candidates": candidates,
    }
