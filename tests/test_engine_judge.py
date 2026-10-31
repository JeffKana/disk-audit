"""T2-02（待办 D1）归属判定流水线 v1 测试。

依据：方案第四节架构③（六层顺序：硬保护 → 知识库 → 注册表 → 进程/服务 → Appx →
启发式）、5.1（置信度四档）、5.3（A1~A5）、9.2（判定单元）、S-1/S-2（硬保护最前
短路不可覆盖；仅启发式置信度上限锁"低"）、验收报告 §3.3（服务证据统一"唯一路径"
口径并在输出披露）、开发规范 §3（快照测试：固定输入 → 固定输出，≥6 代表单元）。

测试知识库/证据全部为罐装固定输入（判定为纯函数，I/O 只在采集层）。
"""
from __future__ import annotations

import inspect
import json
import os

import pytest

from disk_audit.engine.judge import UnitInput, judge_unit
from disk_audit.engine.knowledge import build_knowledge
from disk_audit.engine.report import judge_scan_result
from disk_audit.evidence.appx import AppxPackage, AppxResult
from disk_audit.evidence.autostart import AutostartEntry, AutostartResult
from disk_audit.evidence.evidence import EvidenceBundle
from disk_audit.evidence.processes import ProcessResult
from disk_audit.evidence.registry_uninstall import UninstallEntry, UninstallResult
from disk_audit.evidence.services import ServiceResult
from tests._mini_schema import mini_validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = json.loads(
    open(
        os.path.join(REPO_ROOT, "docs", "schemas", "report-v1.schema.json"),
        encoding="utf-8",
    ).read()
)

NOW_TS = 1_800_000_000.0  # 固定"当前时间"，保证快照确定
RECENT = NOW_TS - 10 * 86400
STALE = NOW_TS - 400 * 86400

KB_ENTRIES = [
    {"name": "sun", "product": "旧版 Sun Java(JRE/JDK)", "vendor": "", "aliases": [],
     "category": "残留候选·高置信", "lifecycle": "未知", "regex_family": None,
     "source": "本机实测", "notes": "测试条目"},
    {"name": "oldapp", "product": "OldApp 停运产品", "vendor": "OldCorp",
     "aliases": ["oldapp-old"], "category": "残留候选·高置信", "lifecycle": "已停止",
     "regex_family": None, "source": "公开软件名", "notes": "公开下线依据（测试）"},
    {"name": "devcachetool", "product": "DevCacheTool 构建缓存", "vendor": "", "aliases": [],
     "category": "开发缓存", "lifecycle": "未知", "regex_family": None,
     "source": "本机实测", "notes": ""},
    {"name": "programs", "product": "每用户安装应用容器", "vendor": "", "aliases": [],
     "category": "容器(已下钻)", "lifecycle": "未知", "regex_family": None,
     "source": "本机实测", "notes": ""},
]
KB = build_knowledge(KB_ENTRIES)


def _unit(name: str, *, max_mtime: float = RECENT, exe_files: int = 1,
          files: int = 3, dirs: int = 1, logical: int = 4096, allocated: int = 4096) -> UnitInput:
    return UnitInput(
        path=rf"C:\Users\u\AppData\Roaming\{name}", files=files, dirs=dirs,
        logical_bytes=logical, allocated_bytes=allocated, max_mtime=max_mtime,
        exe_files=exe_files,
    )


def _bundle(*, uninstall=(), processes=(), services=(), appx=(), autostart=()) -> EvidenceBundle:
    bundle = EvidenceBundle()
    bundle.uninstall = UninstallResult(available=True, entries=list(uninstall))
    bundle.processes = ProcessResult(available=True, paths=list(processes))
    bundle.services = ServiceResult(available=True, paths=list(services))
    bundle.appx = AppxResult(available=True, packages=list(appx))
    bundle.autostart = AutostartResult(available=True, entries=list(autostart))
    return bundle


def _reg(display_name: str, publisher: str = "") -> UninstallEntry:
    return UninstallEntry(
        display_name=display_name, publisher=publisher, install_location="",
        install_date="", uninstall_string="", reg_path=r"HKCU\SOFTWARE\…\Uninstall",
    )


def _appx(name: str, full: str) -> AppxPackage:
    return AppxPackage(name=name, package_full_name=full, install_location=r"C:\…\WindowsApps")


# ---------- 六个代表单元：纯函数快照（固定输入 → 固定输出） ----------


def _snapshot(verdict) -> dict:
    return verdict.to_json_dict()


def test_snapshot_protected():
    v = judge_unit(_unit(r"Microsoft\Protect"), _bundle(), KB, now_ts=NOW_TS)
    assert _snapshot(v) == {
        "path": r"C:\Users\u\AppData\Roaming\Microsoft\Protect",
        "confidence": "受保护",
        "verdict_source": "硬保护",
        "evidence_chain": [
            {"source": "硬保护规则", "content": "受保护，不可处理"},
            {"source": "硬保护规则",
             "content": "HARDPROTECT-DPAPI：DPAPI 密钥目录（Microsoft\\Protect / Crypto）："
                        "删除将导致已保存的密码、证书、Wi-Fi 凭据永久无法解密"},
        ],
        "suggested_action": "A5",
    }


def test_snapshot_installed_via_registry():
    v = judge_unit(_unit("vscode"), _bundle(uninstall=[_reg("VS Code")]), KB, now_ts=NOW_TS)
    assert _snapshot(v) == {
        "path": r"C:\Users\u\AppData\Roaming\vscode",
        "confidence": "高",
        "verdict_source": "注册表",
        "evidence_chain": [{"source": "注册表卸载项", "content": "注册表卸载记录：VS Code"}],
        "suggested_action": "A3",
    }


def test_snapshot_knowledge_hit_missing_lifecycle():
    v = judge_unit(_unit("sun"), _bundle(), KB, now_ts=NOW_TS)
    assert _snapshot(v) == {
        "path": r"C:\Users\u\AppData\Roaming\sun",
        "confidence": "中",
        "verdict_source": "知识库",
        "evidence_chain": [
            {"source": "知识库", "content": "疑似残留，建议核对证据"},
            {"source": "知识库",
             "content": "知识库命中：旧版 Sun Java(JRE/JDK)（残留候选·高置信；"
                        "生命周期未知，缺公开下线依据）"},
        ],
        "suggested_action": "A2",
    }


def test_snapshot_updater_naming_family():
    v = judge_unit(_unit("xmind-vana-updater"), _bundle(), KB, now_ts=NOW_TS)
    assert _snapshot(v) == {
        "path": r"C:\Users\u\AppData\Roaming\xmind-vana-updater",
        "confidence": "高",
        "verdict_source": "知识库",
        "evidence_chain": [
            {"source": "知识库·正则族", "content": "可再生：应用会自行重建"},
            {"source": "知识库·正则族",
             "content": "updater-suffix（*-updater）：Electron electron-updater 下载的"
                        "安装包缓存"},
        ],
        "suggested_action": "A2",
    }


def test_snapshot_heuristic_hash_name():
    v = judge_unit(_unit("0123456789abcdef0123456789abcdef", exe_files=0),
                   _bundle(), KB, now_ts=NOW_TS)
    assert _snapshot(v) == {
        "path": r"C:\Users\u\AppData\Roaming\0123456789abcdef0123456789abcdef",
        "confidence": "低",  # S-2：仅启发式兜底，置信度上限锁"低"
        "verdict_source": "启发式",
        "evidence_chain": [
            {"source": "启发式", "content": "归属未知，需人工判断"},
            {"source": "启发式",
             "content": "哈希/GUID 命名目录，常见于推广 SDK/DRM 组件，无法从名称推断归属"},
            {"source": "启发式", "content": "单元内无可执行文件（.exe）"},
        ],
        "suggested_action": "A5",
    }


def test_snapshot_unknown_tail():
    v = judge_unit(_unit("zzz-unknown-tail"), _bundle(), KB, now_ts=NOW_TS)
    assert _snapshot(v) == {
        "path": r"C:\Users\u\AppData\Roaming\zzz-unknown-tail",
        "confidence": "低",
        "verdict_source": "启发式",
        "evidence_chain": [
            {"source": "启发式", "content": "归属未知，需人工判断"},
            {"source": "启发式",
             "content": "无安装记录、无运行证据、无命名特征命中（未知长尾）"},
        ],
        "suggested_action": "A5",
    }


# ---------- S-1：硬保护最前短路、不可配置覆盖 ----------


def test_hardprotect_wins_over_all_other_evidence():
    """同时命中知识库 + 注册表 + 进程 + Appx + 自启动，仍判受保护（S-1）。"""
    bundle = _bundle(
        uninstall=[_reg("Protect Backup Suite")],
        processes=[r"C:\Users\u\AppData\Roaming\Microsoft\Protect\run.exe"],
        services=[r"C:\Users\u\AppData\Roaming\Microsoft\Protect\svc.exe"],
        appx=[_appx("protect", "protect_1.0_x64__abc")],
        autostart=[AutostartEntry(source=r"HKCU\…\Run", name="p",
                                  command=r"C:\Users\u\AppData\Roaming\Microsoft\Protect\x.exe",
                                  kind="registry")],
    )
    v = judge_unit(_unit(r"Microsoft\Protect"), bundle, KB, now_ts=NOW_TS)
    assert v.confidence == "受保护"
    assert v.verdict_source == "硬保护"
    assert v.suggested_action == "A5"


def test_judge_unit_has_no_override_parameter():
    """S-1 不可配置覆盖：判定入口不存在任何覆盖/跳过配置参数。"""
    params = set(inspect.signature(judge_unit).parameters)
    assert params == {"unit", "bundle", "kb", "now_ts"}
    assert not any("override" in p or "config" in p or "skip" in p for p in params)


# ---------- 六层顺序短路（KB 已停止但缺陈旧/有在用证据 → 落到后续层） ----------


def test_registry_beats_process_and_appx():
    """注册表命中先于进程/Appx 层短路（架构③顺序）。"""
    bundle = _bundle(
        uninstall=[_reg("MyTool Suite")],
        processes=[r"C:\Users\u\AppData\Roaming\mytool\bin\mytool.exe"],
        appx=[_appx("mytool", "mytool_1.0_x64__abc")],
    )
    v = judge_unit(_unit("mytool"), bundle, KB, now_ts=NOW_TS)
    assert v.verdict_source == "注册表"
    assert v.confidence == "高"
    assert v.suggested_action == "A3"


def test_stopped_app_with_registry_falls_to_registry_with_kb_context():
    """KB 标注已停止但注册表有卸载记录 → 以已安装为准，KB 作归属上下文（9.2）。"""
    bundle = _bundle(uninstall=[_reg("OldApp Suite", publisher="OldCorp")])
    v = judge_unit(_unit("oldapp", max_mtime=STALE), bundle, KB, now_ts=NOW_TS)
    assert v.verdict_source == "注册表"
    assert v.confidence == "高"
    sources = [e.source for e in v.evidence_chain]
    assert sources == ["注册表卸载项", "知识库"]
    assert "OldApp 停运产品" in v.evidence_chain[1].content


def test_high_confidence_requires_all_five_evidences():
    """5.1 高档：KB 已停止 + 无注册表 + 无进程/服务/自启动 + 陈旧（400 天）→ 高残留。"""
    v = judge_unit(_unit("oldapp", max_mtime=STALE), _bundle(), KB, now_ts=NOW_TS)
    assert v.confidence == "高"
    assert v.verdict_source == "知识库"
    assert v.suggested_action == "A2"
    contents = [e.content for e in v.evidence_chain]
    assert contents == [
        "高度可能为残留；删除前请确认",
        "知识库标注已停止：OldApp 停运产品",
        "注册表无卸载记录",
        "无匹配进程/服务/自启动",
        "目录陈旧：400 天未修改（> 180 天）",
    ]


@pytest.mark.parametrize("age_days,expected_confidence", [
    (180, "中"),    # 恰好 180 天：不满足"陈旧 >180 天" → 降中
    (181, "高"),    # 超过 180 天一天 → 五证据齐 → 高
])
def test_staleness_boundary_180_days(age_days, expected_confidence):
    mtime = NOW_TS - age_days * 86400
    v = judge_unit(_unit("oldapp", max_mtime=mtime), _bundle(), KB, now_ts=NOW_TS)
    assert v.confidence == expected_confidence


def test_active_process_marks_in_use():
    v = judge_unit(
        _unit("mytool"),
        _bundle(processes=[r"C:\Users\u\AppData\Roaming\mytool\bin\mytool.exe"]),
        KB, now_ts=NOW_TS,
    )
    assert v.verdict_source == "进程服务"
    assert v.confidence == "高"
    assert v.suggested_action == "A5"
    assert v.evidence_chain[0].source == "进程"


def test_service_hit_discloses_unique_path_scope():
    """服务证据统一"唯一路径"口径并在输出披露（验收报告 §3.3）。"""
    bundle = _bundle(services=[
        r"C:\Users\u\AppData\Roaming\mytool\svc.exe -k run",
        r"C:\WINDOWS\system32\svchost.exe -k netsvcs -p",
    ])
    v = judge_unit(_unit("mytool"), bundle, KB, now_ts=NOW_TS)
    assert v.verdict_source == "进程服务"
    assert "服务唯一路径口径，全库 2 条唯一路径" in v.evidence_chain[0].content


def test_autostart_hit_marks_in_use():
    bundle = _bundle(autostart=[AutostartEntry(
        source=r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run", name="mytool",
        command=r'"C:\Users\u\AppData\Roaming\mytool\bin\mytool.exe" /background',
        kind="registry")])
    v = judge_unit(_unit("mytool"), bundle, KB, now_ts=NOW_TS)
    assert v.verdict_source == "进程服务"
    assert v.evidence_chain[0].source == "自启动"


def test_appx_hit_medium_confidence():
    v = judge_unit(
        _unit("com.example.app"),
        _bundle(appx=[_appx("com.example.app", "com.example.app_1.0_x64__abc")]),
        KB, now_ts=NOW_TS,
    )
    assert v.verdict_source == "Appx"
    assert v.confidence == "中"
    assert v.suggested_action == "A3"


def test_appx_packages_data_dir_family_prefix():
    """Packages 数据目录（FamilyName_hash）按包全名前缀比对（原型 drill_packages 口径）。"""
    v = judge_unit(
        _unit("packagefamily_abc123"),
        _bundle(appx=[_appx("packagefamily", "packagefamily_1.0_x64__abc123")]),
        KB, now_ts=NOW_TS,
    )
    assert v.verdict_source == "Appx"


# ---------- D6 子串误判防护边界（原型修复口径） ----------


def test_substring_guard_code_not_openaicodex():
    """著名反例：code ≠ openaicodex（注册表包含匹配 len≥5；Appx 仅点号包名）。"""
    bundle = _bundle(
        uninstall=[_reg("OpenAI Codex CLI")],
        appx=[_appx("openaicodex", "openaicodex_1.0_x64__abc")],
    )
    v = judge_unit(_unit("code"), bundle, KB, now_ts=NOW_TS)
    assert v.verdict_source == "启发式"  # 两个包含匹配均不得命中


def test_dotted_package_name_containment_allowed():
    """正例：含点号的包名式命名允许包含匹配（com.example ⊂ com.example.app）。"""
    bundle = _bundle(appx=[_appx("com.example.app", "com.example.app_1.0_x64__abc")])
    v = judge_unit(_unit("com.example"), bundle, KB, now_ts=NOW_TS)
    assert v.verdict_source == "Appx"


def test_registry_containment_requires_five_chars():
    """注册表包含匹配仅限 len≥5（原型口径）：4 字符名不得包含命中。"""
    bundle = _bundle(uninstall=[_reg("Abcd Explorer Suite")])
    v = judge_unit(_unit("abcd"), bundle, KB, now_ts=NOW_TS)
    assert v.verdict_source != "注册表"


# ---------- 知识库其余分支 ----------


def test_container_category_kb_hit():
    v = judge_unit(_unit("programs"), _bundle(), KB, now_ts=NOW_TS)
    assert v.verdict_source == "知识库"
    assert v.confidence == "高"
    assert v.suggested_action == "A5"


def test_kb_alias_match():
    v = judge_unit(_unit("oldapp-old", max_mtime=STALE), _bundle(), KB, now_ts=NOW_TS)
    assert v.verdict_source == "知识库"
    assert v.confidence == "高"


# ---------- 报告装配（report-v1 草案） ----------


def _scan_fixture(tmp_path):
    from disk_audit.scanner import scan_path

    (tmp_path / "xmind-vana-updater").mkdir()
    (tmp_path / "xmind-vana-updater" / "setup.pkg").write_bytes(b"x" * 1000)
    (tmp_path / "devcachetool").mkdir()
    (tmp_path / "devcachetool" / "c.bin").write_bytes(b"x" * 2000)
    (tmp_path / "Microsoft").mkdir()
    (tmp_path / "Microsoft" / "Protect").mkdir()
    (tmp_path / "zzz-unknown-tail").mkdir()
    (tmp_path / "zzz-unknown-tail" / "a.exe").write_bytes(b"x" * 10)
    result = scan_path(str(tmp_path))
    return result.to_json_dict()


def test_judge_scan_result_builds_draft_valid_report(tmp_path):
    scan = _scan_fixture(tmp_path)
    scan["skipped"]["total"] = 2
    report = judge_scan_result(scan, bundle=_bundle(), kb=KB)
    assert mini_validate(report, SCHEMA) == []
    assert report["schema_version"] == "1.0"
    assert report["scan_root"] == scan["root"]
    assert len(report["candidates"]) == len(scan["units"])
    assert report["totals"]["skipped_entries"] == 2
    confidences = {c["confidence"] for c in report["candidates"]}
    assert {"受保护", "高", "低"} <= confidences


def test_regenerable_two_buckets_separate(tmp_path):
    """5.2：更新缓存入可再生小计，开发缓存入需确认小计，两档分别列示。"""
    scan = _scan_fixture(tmp_path)
    report = judge_scan_result(scan, bundle=_bundle(), kb=KB)
    updater = next(u for u in scan["units"] if u["path"].endswith("xmind-vana-updater"))
    devcache = next(u for u in scan["units"] if u["path"].endswith("devcachetool"))
    assert report["totals"]["regenerable_subtotal"] == updater["allocated_bytes"]
    assert report["totals"]["regenerable_confirm_subtotal"] == devcache["allocated_bytes"]


def test_report_has_no_recyclable_wording(tmp_path):
    """Q3：输出全文不含"可回收"，totals 无合并"可释放"字段。"""
    scan = _scan_fixture(tmp_path)
    report = judge_scan_result(scan, bundle=_bundle(), kb=KB)
    assert "可回收" not in json.dumps(report, ensure_ascii=False)
    assert not any("releasable" in k or "可释放" in k for k in report["totals"])


def test_judge_scan_result_rejects_non_scan_input():
    with pytest.raises(ValueError):
        judge_scan_result({"foo": 1})
    with pytest.raises(ValueError):
        judge_scan_result({"root": "C:\\x"})  # 缺 units/汇总字段


# ---------- CLI：judge 子命令（零 UI 依赖，独立调用） ----------


def test_cli_judge_outputs_draft_valid_report(tmp_path, monkeypatch, capsys):
    import disk_audit.engine.report as report_module
    from disk_audit.__main__ import main

    scan = _scan_fixture(tmp_path)
    scan_file = tmp_path / "scan.json"
    scan_file.write_text(json.dumps(scan, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(report_module, "collect_all", lambda: _bundle())
    monkeypatch.setattr(report_module, "load_knowledge", lambda: KB)

    rc = main(["judge", str(scan_file)])
    out = capsys.readouterr().out
    assert rc == 0
    report = json.loads(out)
    assert mini_validate(report, SCHEMA) == []


def test_cli_judge_rejects_bad_input(tmp_path, capsys):
    from disk_audit.__main__ import main

    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    rc = main(["judge", str(bad)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "判定失败" in err
