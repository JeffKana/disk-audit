"""六层归属判定流水线 v1（待办 D1，任务卡 T2-02）。

依据：方案第四节架构③（硬保护 → 知识库 → 注册表 → 进程/服务 → Appx → 启发式，
顺序短路）、5.1（置信度四档）、5.3（A1~A5 固定枚举）、9.2（判定单元）、
S-1（硬保护最前短路返回，不参与打分、不可配置覆盖）、S-2（仅启发式兜底命中
置信度上限锁"低"）、验收报告 §3.3（服务证据统一"唯一路径"口径并在输出披露）。

判定为纯函数：输入单元聚合（UnitInput）+ EvidenceBundle + KnowledgeBase →
输出 Verdict；I/O 只在采集层；now_ts 可注入保证快照可测。

v1 打标口径（T2-03 将按 5.1/5.2 参数化锁定全部触发组合）：
- 受保护：硬保护命中，固定 A5；
- 高（已安装）：注册表卸载记录命中 → A3；
- 高（在用）：进程/服务/自启动路径命中 → A5；
- 中（在用·商店包）：Appx 注册包命中 → A3（对齐原型）；
- 高（残留）：知识库标注"已停止"且 5.1 五证据同时成立（无注册表 + 无进程/服务 +
  无自启动 + 陈旧 >180 天）→ A2；
- 中：知识库命中缺生命周期（"已停止"但不够陈旧视为 2 项证据成立）→ A2；
- 低：仅启发式（哈希/GUID、陈旧度、无 exe），措辞无倾向 → A5。
知识库命中但注册表/运行证据表明在用 → 以在用为准、知识库作归属上下文
（9.2"已安装"口径；M4 验收"高置信档对在用软件误判 = 0"）。
陈旧度阈值取方案 5.1 的 180 天（原型 STALE_DAYS=540 不采用：方案定稿优先）。
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from ..evidence.appx import AppxResult
from ..evidence.evidence import EvidenceBundle
from ..hardprotect import check_protection
from .knowledge import KnowledgeBase, KnowledgeEntry, match_entry
from .texts import CONFIDENCE_WORDING, REGENERABLE_WORDING

# 方案 5.1：目录陈旧（>180 天未改）；原型为 540 天，按"方案定稿优先"取 180
_STALE_DAYS = 180
_SECONDS_PER_DAY = 86400
# 容器命名规则（原型 classify：Local 下 programs/packages 为已下钻容器）
_CONTAINER_UNIT_NAMES = frozenset({"programs", "packages"})

_HASH_RE = re.compile(r"^[0-9a-f]{16,64}$")
_GUID_RE = re.compile(
    r"^\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?$"
)


@dataclass(frozen=True)
class UnitInput:
    """判定单元输入（来自 scan 输出 units 数组，9.2 判定单元聚合）。"""

    path: str
    files: int
    dirs: int
    logical_bytes: int
    allocated_bytes: int
    max_mtime: float
    exe_files: int

    @classmethod
    def from_scan_unit(cls, data: dict) -> "UnitInput":
        return cls(
            path=data["path"],
            files=int(data.get("files", 0)),
            dirs=int(data.get("dirs", 0)),
            logical_bytes=int(data.get("logical_bytes", 0)),
            allocated_bytes=int(data.get("allocated_bytes", 0)),
            max_mtime=float(data.get("max_mtime", 0.0)),
            exe_files=int(data.get("exe_files", 0)),
        )


@dataclass(frozen=True)
class EvidenceItem:
    """证据链条目（E-2；报告内 A4"查看证据链"的展示数据）。"""

    source: str
    content: str

    def to_json_dict(self) -> dict:
        return {"source": self.source, "content": self.content}


@dataclass(frozen=True)
class Verdict:
    """一个判定单元的判定结果。

    category 为内部归类（KB 分类/启发式归类），用于 5.2 可再生两档小计，
    不进报告候选字段（report-v1 草案 candidate 七字段固定）。
    """

    path: str
    confidence: str
    verdict_source: str
    evidence_chain: tuple[EvidenceItem, ...]
    suggested_action: str
    category: str

    def to_json_dict(self) -> dict:
        return {
            "path": self.path,
            "confidence": self.confidence,
            "verdict_source": self.verdict_source,
            "evidence_chain": [e.to_json_dict() for e in self.evidence_chain],
            "suggested_action": self.suggested_action,
        }


def _norm(text: str) -> str:
    """小写并去掉非字母数字/中文（对齐原型 norm）。"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (text or "").lower())


def _extract_path(text: str) -> str:
    """从命令行/服务路径串中提取第一个 Windows 绝对路径（对齐原型 extract_path）。"""
    found = re.search(r"[A-Za-z]:\\[^\s\"]+", (text or ""))
    return found.group(0).lower() if found else ""


def _match_registry(nname: str, bundle: EvidenceBundle) -> list[str]:
    """注册表卸载项匹配（原型 match_installed 口径）：norm 后精确相等优先；
    未命中且目录名 norm 长度 ≥5 才做包含匹配（防短名子串误判，D6）。"""
    hits: list[str] = []
    if len(nname) < 2:
        return hits
    for entry in bundle.uninstall.entries:
        if _norm(entry.display_name) == nname:
            hits.append(entry.display_name)
    if not hits:
        for entry in bundle.uninstall.entries:
            if len(nname) >= 5 and (
                nname in _norm(entry.display_name) or nname in _norm(entry.publisher)
            ):
                hits.append(entry.display_name)
    return hits


def _active_under(unit_path: str, bundle: EvidenceBundle) -> tuple[str, str] | None:
    """进程/服务/自启动路径是否位于该单元下（原型 active_under 口径）。

    返回（原文, 证据类型）；服务经 extract_path 提取（PathName 可能带参数）。
    """
    prefix = unit_path.lower()
    for path in bundle.processes.paths:
        lowered = path.lower()
        if lowered == prefix or lowered.startswith(prefix + "\\") or lowered.startswith(prefix + "."):
            return path, "进程"
    for raw in bundle.services.paths:
        extracted = _extract_path(raw)
        if extracted and (
            extracted == prefix
            or extracted.startswith(prefix + "\\")
            or extracted.startswith(prefix + ".")
        ):
            return raw, "服务"
    for entry in bundle.autostart.entries:
        extracted = _extract_path(entry.command)
        if extracted and (
            extracted == prefix
            or extracted.startswith(prefix + "\\")
            or extracted.startswith(prefix + ".")
        ):
            return entry.command, "自启动"
    return None


def _match_appx(name_l: str, nname: str, appx: AppxResult) -> str | None:
    """Appx 注册包匹配（原型 match_appx + drill_packages 口径）：
    包名/全名精确命中 → 含点号的包名式命名双向包含（code ≠ openaicodex 防护）→
    Packages 数据目录 FamilyName_hash 按包全名前缀比对。"""
    raw = {p.package_full_name.lower() for p in appx.packages}
    raw |= {p.name.lower() for p in appx.packages}
    if name_l in raw:
        return name_l
    if "." in name_l and len(nname) >= 4:
        for package in appx.packages:
            family_norm = _norm(package.name)
            if family_norm and (nname in family_norm or family_norm in nname):
                return package.package_full_name
    if "_" in name_l:
        family = name_l.rsplit("_", 1)[0]
        if len(family) >= 4:
            for package in appx.packages:
                if package.package_full_name.lower().startswith(family + "_"):
                    return package.package_full_name
    return None


def _judge_kb_hit(
    entry: KnowledgeEntry,
    *,
    stale: bool,
    age_days: float | None,
    reg_hits: list[str],
    active: tuple[str, str] | None,
) -> Verdict | None:
    """知识库层判定；返回 None 表示本层不能定档，落到后续层（知识库转上下文）。

    残留类判定在证据链首位携带 5.1 输出措辞（文案资源 texts.CONFIDENCE_WORDING）；
    已安装/在用类判定不属残留档位，不带残留措辞。
    """
    category = entry.category
    if category in ("容器(已下钻)", "系统组件", "兼容链接·严禁删除"):
        return Verdict(
            path="", confidence="高", verdict_source="知识库",
            evidence_chain=(EvidenceItem("知识库", f"知识库命中：{entry.product}（{category}）"),),
            suggested_action="A5", category=category,
        )
    if entry.lifecycle == "已停止":
        if not reg_hits and active is None:
            chain = [EvidenceItem("知识库", CONFIDENCE_WORDING["中" if not stale else "高"])]
            chain += [
                EvidenceItem("知识库", f"知识库标注已停止：{entry.product}"),
                EvidenceItem("注册表卸载项", "注册表无卸载记录"),
                EvidenceItem("进程服务", "无匹配进程/服务/自启动"),
            ]
            if stale:
                chain.append(EvidenceItem(
                    "启发式", f"目录陈旧：{int(age_days)} 天未修改（> {_STALE_DAYS} 天）"
                ))
                # 5.1 高档：五证据同时成立
                return Verdict(
                    path="", confidence="高", verdict_source="知识库",
                    evidence_chain=tuple(chain), suggested_action="A2", category=category,
                )
            # "已停止"但不够陈旧：KB 标注 + 无运行证据 = 2 项证据成立 → 中（5.1 中档）
            return Verdict(
                path="", confidence="中", verdict_source="知识库",
                evidence_chain=tuple(chain), suggested_action="A2", category=category,
            )
        return None  # 有注册表/运行证据 → 以在用为准（9.2），知识库转上下文
    if entry.lifecycle == "在用":
        return Verdict(
            path="", confidence="高", verdict_source="知识库",
            evidence_chain=(EvidenceItem("知识库", f"知识库标注在用：{entry.product}（{category}）"),),
            suggested_action="A5", category=category,
        )
    # lifecycle 未知：
    if category == "已安装应用":
        return Verdict(
            path="", confidence="高", verdict_source="知识库",
            evidence_chain=(EvidenceItem("知识库", f"知识库命中：{entry.product}（{category}）"),),
            suggested_action="A3", category=category,
        )
    if category == "使用中(无安装记录)":
        return Verdict(
            path="", confidence="高", verdict_source="知识库",
            evidence_chain=(EvidenceItem("知识库", f"知识库命中：{entry.product}（{category}）"),),
            suggested_action="A5", category=category,
        )
    # 其余类别（残留候选/缓存/游戏数据等）：KB 命中缺生命周期 → 中（5.1）
    return Verdict(
        path="", confidence="中", verdict_source="知识库",
        evidence_chain=(
            EvidenceItem("知识库", CONFIDENCE_WORDING["中"]),
            EvidenceItem(
                "知识库",
                f"知识库命中：{entry.product}（{category}；生命周期未知，缺公开下线依据）",
            ),
        ),
        suggested_action="A2", category=category,
    )


def judge_unit(
    unit: UnitInput,
    bundle: EvidenceBundle,
    kb: KnowledgeBase,
    now_ts: float | None = None,
) -> Verdict:
    """对单个判定单元执行六层流水线（纯函数；now_ts 可注入）。"""
    now = time.time() if now_ts is None else now_ts

    # ---- 1. 硬保护（S-1：最前短路返回，不参与打分、不可配置覆盖） ----
    protection = check_protection(unit.path)
    if protection is not None:
        return Verdict(
            path=unit.path, confidence="受保护", verdict_source="硬保护",
            evidence_chain=(
                EvidenceItem("硬保护规则", CONFIDENCE_WORDING["受保护"]),
                EvidenceItem("硬保护规则", f"{protection.rule_id}：{protection.reason}"),
            ),
            suggested_action="A5", category="系统组件",
        )

    name = os.path.basename(unit.path.rstrip("\\/"))
    name_l = name.lower()
    nname = _norm(name_l)
    age_days: float | None = None
    if unit.max_mtime > 0:
        age_days = (now - unit.max_mtime) / _SECONDS_PER_DAY
    stale = age_days is not None and age_days > _STALE_DAYS

    # ---- 证据检索（纯查询，不产生判定） ----
    reg_hits = _match_registry(nname, bundle)
    active = _active_under(unit.path, bundle)

    # ---- 2. 知识库 ----
    kb_hit = match_entry(kb, name_l)
    if kb_hit is not None:
        verdict = _judge_kb_hit(kb_hit, stale=stale, age_days=age_days, reg_hits=reg_hits, active=active)
        if verdict is not None:
            return _finalize(verdict, unit)

    # 容器命名规则（原型口径）：programs/packages 已下钻，子项单独成单元
    if name_l in _CONTAINER_UNIT_NAMES:
        return _finalize(
            Verdict(
                path="", confidence="高", verdict_source="知识库",
                evidence_chain=(EvidenceItem("知识库", "容器目录（已下钻判定）：子项已单独成单元"),),
                suggested_action="A5", category="容器(已下钻)",
            ),
            unit,
        )

    # 更新缓存命名模式（原型：*-updater → 知识库正则族 updater-suffix，5.2 可再生）
    if "-updater" in name_l:
        return _finalize(
            Verdict(
                path="", confidence="高", verdict_source="知识库",
                evidence_chain=(
                    EvidenceItem("知识库·正则族", REGENERABLE_WORDING),
                    EvidenceItem(
                        "知识库·正则族",
                        "updater-suffix（*-updater）：Electron electron-updater 下载的"
                        "安装包缓存",
                    ),
                ),
                suggested_action="A2", category="更新缓存",
            ),
            unit,
        )

    # ---- 3. 注册表 ----
    if reg_hits:
        chain = [EvidenceItem("注册表卸载项", "注册表卸载记录：" + "；".join(reg_hits[:3]))]
        if kb_hit is not None:
            chain.append(EvidenceItem("知识库", f"知识库归属：{kb_hit.product}（{kb_hit.category}）"))
        return _finalize(
            Verdict(
                path="", confidence="高", verdict_source="注册表",
                evidence_chain=tuple(chain), suggested_action="A3",
                category=kb_hit.category if kb_hit is not None else "已安装应用",
            ),
            unit,
        )

    # ---- 4. 进程/服务/自启动 ----
    if active is not None:
        raw, kind = active
        content = f"运行证据（{kind}）：{raw}"
        if kind == "服务":
            content += f"（服务唯一路径口径，全库 {len(bundle.services.paths)} 条唯一路径）"
        return _finalize(
            Verdict(
                path="", confidence="高", verdict_source="进程服务",
                evidence_chain=(EvidenceItem(kind, content),),
                suggested_action="A5",
                category=kb_hit.category if kb_hit is not None else "使用中(无安装记录)",
            ),
            unit,
        )

    # ---- 5. Appx ----
    appx_family = _match_appx(name_l, nname, bundle.appx)
    if appx_family is not None:
        return _finalize(
            Verdict(
                path="", confidence="中", verdict_source="Appx",
                evidence_chain=(EvidenceItem("Appx", f"Appx 注册包匹配：{appx_family}"),),
                suggested_action="A3", category="已安装应用",
            ),
            unit,
        )

    # ---- 6. 启发式（S-2：仅启发式兜底命中，置信度上限锁"低"，措辞无倾向） ----
    signals: list[EvidenceItem] = [EvidenceItem("启发式", CONFIDENCE_WORDING["低"])]
    if _HASH_RE.match(name_l) or _GUID_RE.match(name_l):
        signals.append(EvidenceItem(
            "启发式", "哈希/GUID 命名目录，常见于推广 SDK/DRM 组件，无法从名称推断归属"
        ))
    if stale:
        signals.append(EvidenceItem(
            "启发式", f"目录陈旧：{int(age_days)} 天未修改（> {_STALE_DAYS} 天）"
        ))
    if unit.files > 0 and unit.exe_files == 0:
        signals.append(EvidenceItem("启发式", "单元内无可执行文件（.exe）"))
    if len(signals) == 1:  # 仅措辞，无任何启发式信号：未知长尾说明
        signals.append(EvidenceItem("启发式", "无安装记录、无运行证据、无命名特征命中（未知长尾）"))
    return _finalize(
        Verdict(
            path="", confidence="低", verdict_source="启发式",
            evidence_chain=tuple(signals), suggested_action="A5",
            category="残留候选·低置信",
        ),
        unit,
    )


def _finalize(verdict: Verdict, unit: UnitInput) -> Verdict:
    """补齐单元路径（各层构造时统一留空，出口处回填，避免重复传参）。"""
    return Verdict(
        path=unit.path,
        confidence=verdict.confidence,
        verdict_source=verdict.verdict_source,
        evidence_chain=verdict.evidence_chain,
        suggested_action=verdict.suggested_action,
        category=verdict.category,
    )
