r"""T4-07（待办 F4）建议动作接线测试——A1~A3 经 B3 的参数断言、A5 无入口回归、
完成态建议动作区的数据透传。

依据：任务卡 T4-07 验收①②③（A1~A3 经 B3 参数断言单测；受保护/低置信无入口
回归；端到端真实触发另在本机留档不入 CI）、方案 5.3（A1~A5 固定 5 种：A1 复制
路径→剪贴板 / A2 打开所在文件夹→explorer /select, / A3 打开系统应用列表→
ms-settings:appsfeatures / A4 查看证据链→报告内展开、无外部调用 / A5 无建议→
受保护项与低置信项固定使用）、U-4/X2（A1~A3 为白名单三能力，经
disk_audit.system_actions 唯一出口，UninstallString 永不执行）、E-5（失败仅
提示，不弹错误框——本卡沿 G2 状态栏先例以状态栏文案披露）。

测试纪律（与 tests/test_system_actions.py 同款）：三能力一律经 B3 注入替身
（writer/executor）断言调用参数，不真开 explorer / 设置面板 / 不写真实剪贴板；
越权路径用 B3 真实拒绝出口（空路径拒绝发生在任何系统 API 之前，CI 安全）；
断言禁依赖系统 locale、无真 KeyboardInterrupt、无 argv 依赖。
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import launcher  # noqa: E402
from disk_audit import system_actions  # noqa: E402
from disk_audit.engine import texts  # noqa: E402


class RecordingExecutor:
    """ShellExecuteW 替身：记录 (file, params) 调用对（test_system_actions 同款）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, file: str, params: str | None) -> object:
        self.calls.append((file, params))
        return 42  # ShellExecuteW 成功哨兵（>32）


class RecordingWriter:
    """剪贴板写替身：记录写入文本，不触碰真实剪贴板。"""

    def __init__(self) -> None:
        self.written: list[str] = []

    def __call__(self, text: str) -> None:
        self.written.append(text)


# ---------- 验收①：A1~A3 经 B3 的参数断言（接线层 → B3 注入点） ----------


def test_default_action_deps_bind_b3_entrypoints():
    """默认装配绑定 B3 三能力公开函数（F4 消费 B3，不得旁路自实现系统交互）。"""
    deps = launcher.default_action_deps()
    assert deps.copy_path is system_actions.copy_to_clipboard
    assert deps.locate is system_actions.locate_in_explorer
    assert deps.open_settings is system_actions.open_apps_settings


def test_a1_copies_candidate_path_through_b3():
    """A1 复制路径：copy_to_clipboard 收到候选路径原文（无加工），且不触达
    A2/A3 出口；状态栏如实披露复制了哪条路径。"""
    writer = RecordingWriter()
    deps = launcher.ActionDeps(
        copy_path=lambda p: system_actions.copy_to_clipboard(p, writer=writer),
        locate=lambda p: pytest.fail("A1 不得触达 A2 出口"),
        open_settings=lambda: pytest.fail("A1 不得触达 A3 出口"),
    )
    status = launcher.run_suggested_action("A1", r"C:\scope\atom", deps=deps)
    assert writer.written == [r"C:\scope\atom"]
    assert r"C:\scope\atom" in status


def test_a2_locates_candidate_through_b3_whitelisted_params():
    """A2 打开所在文件夹：候选路径经 locate_in_explorer → B3 白名单出口构造
    explorer.exe /select,<候选路径>（只定位，不打开文件），不触达 A1/A3 出口。"""
    executor = RecordingExecutor()
    deps = launcher.ActionDeps(
        copy_path=lambda p: pytest.fail("A2 不得触达 A1 出口"),
        locate=lambda p: system_actions.locate_in_explorer(p, executor=executor),
        open_settings=lambda: pytest.fail("A2 不得触达 A3 出口"),
    )
    status = launcher.run_suggested_action("A2", r"C:\scope\atom", deps=deps)
    assert executor.calls == [("explorer.exe", "/select," + r"C:\scope\atom")]
    assert r"C:\scope\atom" in status


def test_a3_opens_settings_through_b3_whitelisted_target():
    """A3 打开系统应用列表：open_apps_settings 无参调用 → B3 白名单出口
    ms-settings:appsfeatures（卸载指引唯一出口），不触达 A1/A2 出口。"""
    executor = RecordingExecutor()
    deps = launcher.ActionDeps(
        copy_path=lambda p: pytest.fail("A3 不得触达 A1 出口"),
        locate=lambda p: pytest.fail("A3 不得触达 A2 出口"),
        open_settings=lambda: system_actions.open_apps_settings(executor=executor),
    )
    status = launcher.run_suggested_action("A3", r"C:\scope\atom", deps=deps)
    assert executor.calls == [("ms-settings:appsfeatures", None)]
    assert status  # 状态栏有完成披露（打开到哪里、后续人工操作指向）


# ---------- 验收①补：异常路径 → 状态栏披露（E-5 风格，不弹错误对话框） ----------


def test_empty_path_rejection_disclosed_in_status_never_raised():
    """B3 真实拒绝出口（空路径，任何系统 API 之前即拒）→ 返回披露文案，
    不向 UI 抛异常；文案含 B3 披露措辞（白名单边界）。"""
    status = launcher.run_suggested_action("A2", "   ", deps=launcher.default_action_deps())
    assert "已拒绝系统交互" in status  # texts.B3_TEXTS["b3_err_empty_path"] 措辞


def test_system_action_rejected_converted_to_status_text():
    """接线层捕获 SystemActionRejected 并转状态栏文案：披露被拒目标，
    不抛出、不弹错误框（E-5）。"""

    def boom(path: str) -> None:
        raise system_actions.SystemActionRejected(
            texts.B3_TEXTS["b3_err_rejected"].format(target="某越权目标")
        )

    deps = launcher.ActionDeps(copy_path=lambda p: None, locate=boom, open_settings=lambda: None)
    status = launcher.run_suggested_action("A2", r"C:\scope\atom", deps=deps)
    assert "已拒绝系统交互" in status and "某越权目标" in status


def test_clipboard_failure_disclosed_in_status_never_raised():
    """剪贴板写入失败（B3 OSError 中文文案）→ 状态栏披露失败原因，不抛出。"""

    def boom(path: str) -> None:
        raise OSError(texts.B3_TEXTS["b3_err_clipboard_open"])

    deps = launcher.ActionDeps(copy_path=boom, locate=lambda p: None, open_settings=lambda: None)
    status = launcher.run_suggested_action("A1", r"C:\scope\atom", deps=deps)
    assert "剪贴板" in status and "失败" in status


@pytest.mark.parametrize("action", ["A4", "A5", ""])
def test_unknown_action_key_performs_no_system_interaction(action: str):
    """非 A1/A2/A3 动作键（A4/A5/空串）：零系统交互、零替身触达，仅状态栏披露。"""
    writer = RecordingWriter()
    executor = RecordingExecutor()
    deps = launcher.ActionDeps(
        copy_path=lambda p: system_actions.copy_to_clipboard(p, writer=writer),
        locate=lambda p: system_actions.locate_in_explorer(p, executor=executor),
        open_settings=lambda: system_actions.open_apps_settings(executor=executor),
    )
    status = launcher.run_suggested_action(action, r"C:\scope\atom", deps=deps)
    assert status
    assert writer.written == [] and executor.calls == []


# ---------- 验收②（UI 侧）：受保护/低置信（及建议 A5 的候选）不进入可操作列表 ----------


def _report_with_four_confidences() -> dict:
    """四档齐全样例（键与 report-v1 schema $defs.candidate 对齐）：
    高·A2 / 中·A2 / 受保护·A5 / 低·A5，另加一条高置信但在用（judge 打标 A5）。"""
    return {
        "candidates": [
            {
                "path": r"C:\scope\atom",
                "confidence": "高",
                "verdict_source": "知识库",
                "suggested_action": "A2",
            },
            {
                "path": r"C:\scope\sun",
                "confidence": "中",
                "verdict_source": "知识库",
                "suggested_action": "A2",
            },
            {
                "path": r"C:\scope\Microsoft\Protect",
                "confidence": "受保护",
                "verdict_source": "硬保护",
                "suggested_action": "A5",
            },
            {
                "path": r"C:\scope\unknown-longtail",
                "confidence": "低",
                "verdict_source": "启发式",
                "suggested_action": "A5",
            },
            {
                "path": r"C:\scope\inuse-app",
                "confidence": "高",
                "verdict_source": "进程服务",
                "suggested_action": "A5",
            },
        ]
    }


def test_operable_candidates_exclude_protected_and_low_confidence():
    """卡面硬约束：受保护/低置信候选永不进入可操作列表（A5 固定，无任何入口）。"""
    operable = launcher.select_operable_candidates(_report_with_four_confidences())
    paths = [str(c["path"]) for c in operable]
    assert r"C:\scope\Microsoft\Protect" not in paths  # 受保护（硬保护）
    assert r"C:\scope\unknown-longtail" not in paths  # 低置信（启发式）
    assert r"C:\scope\inuse-app" not in paths  # 高置信但在用：报告展示"无建议"，UI 不自相矛盾


def test_operable_candidates_keep_only_high_mid_with_a1_a2_a3():
    """可操作集合 = 置信度 ∈ {高, 中} 且建议动作 ∈ {A1, A2, A3}
    （对卡面"仅高/中可操作"的收窄而非放宽：建议已是 A5 的候选同样排除）。"""
    operable = launcher.select_operable_candidates(_report_with_four_confidences())
    assert [str(c["path"]) for c in operable] == [r"C:\scope\atom", r"C:\scope\sun"]
    for candidate in operable:
        assert candidate["confidence"] in ("高", "中")
        assert candidate["suggested_action"] in ("A1", "A2", "A3")


@pytest.mark.parametrize(
    "report",
    [
        {},
        {"candidates": None},
        {"candidates": []},
        {"candidates": ["非对象元素", 42, None]},
        None,
    ],
)
def test_select_operable_candidates_defensive_shapes(report: object):
    """防御性输入（缺键/空/非对象元素/非 dict）→ 空列表，不抛异常。"""
    assert launcher.select_operable_candidates(report) == []  # type: ignore[arg-type]


# ---------- A4 入口语义与文案确认（F2 details 原生，本卡仅确认入口与文案） ----------


def test_a4_hint_points_to_report_internal_expansion():
    """A4 文案：指向报告"证据链"区报告内展开，与方案 5.3 A4"报告内展开，
    无外部调用"同口径；动作名复用 5.3 固定标签（单一措辞源）。"""
    hint = texts.F4_TEXTS["a4_hint"]
    assert texts.ACTION_LABELS["A4"] in hint  # "查看证据链"
    assert "证据链" in hint and "报告" in hint
    assert "无外部调用" in hint


def test_f4_texts_state_a5_has_no_entry():
    """A5 语义文案：明确"无建议/不提供处理入口"，且不出现"下一步"（F2 断言体系）。"""
    blob = texts.F4_TEXTS["no_operable"] + texts.F4_TEXTS["actions_note"]
    assert "无建议" in blob
    assert "不提供" in blob
    assert "下一步" not in blob


def test_f4_texts_required_keys_exist():
    required = [
        "actions_group",
        "candidate_none",
        "candidate_item_fmt",
        "no_operable",
        "no_candidate_selected",
        "a4_hint",
        "status_copied",
        "status_located",
        "status_settings_opened",
        "status_action_failed",
        "status_unknown_action",
        "actions_note",
    ]
    missing = [key for key in required if key not in texts.F4_TEXTS]
    assert missing == []


def test_f4_texts_no_forbidden_terms():
    """Q3 禁词约束对全部对外文案生效；R10 零假设：不出现行为建议措辞。"""
    blob = "".join(texts.F4_TEXTS.values())
    assert "可回收" not in blob
    assert "可释放" not in blob


def test_action_button_labels_reuse_53_fixed_labels():
    """按钮文案 = 5.3 编号 + 固定动作标签（texts.ACTION_LABELS 单一措辞源，不另造措辞）。"""
    assert launcher.action_button_label("A1") == "A1 复制路径"
    assert launcher.action_button_label("A2") == "A2 打开所在文件夹"
    assert launcher.action_button_label("A3") == "A3 打开系统应用列表"


# ---------- on_report 透传：judge 输出到达 UI（完成态建议动作区的数据源） ----------


def _deps_with_report(calls: list[tuple], report: dict) -> launcher.AuditDeps:
    """六环替身：judge 返回注入的 report dict，其余环照常记录。"""

    def scan(path: str, progress_cb=None, abort_check=None):
        calls.append(("scan", path))
        return {"root": path, "units": [], "skipped": {}}

    return launcher.AuditDeps(
        scan=scan,
        judge=lambda s: (calls.append(("judge", s["root"])), report)[1],
        render=lambda r: (calls.append(("render", None)), "<html></html>")[1],
        save=lambda html: (calls.append(("save", None)), r"C:\reports\report-t407.html")[1],
        prune=lambda: (calls.append(("prune", None)), [])[1],
        open=lambda path: calls.append(("open", path)),
    )


def test_execute_audit_surfaces_report_after_judge_before_render():
    """on_report 在 judge 完成后、render/save 前收到 report-v1 dict（原样透传）。"""
    calls: list[tuple] = []
    report = {"schema_version": "1.0", "candidates": [{"path": "p"}]}
    seen: list[dict] = []
    deps = _deps_with_report(calls, report)
    launcher.execute_audit(r"C:\scope", deps=deps, on_report=seen.append)
    assert seen == [report]
    order = [entry[0] for entry in calls]
    assert order.index("judge") < order.index("render") < order.index("save")


def test_execute_audit_without_on_report_keeps_old_contract():
    """不传 on_report 时六环语义与 T3-06 既有接线完全一致（新增可选项不破坏旧契约）。"""
    calls: list[tuple] = []
    deps = _deps_with_report(calls, {"schema_version": "1.0", "candidates": []})
    got = launcher.execute_audit(r"C:\scope", deps=deps)
    assert got == r"C:\reports\report-t407.html"
    assert [entry[0] for entry in calls] == ["scan", "judge", "render", "save", "prune", "open"]


def test_run_audit_async_forwards_report_via_after_on_main_thread():
    """on_report 经 after 派发主线程执行（工作线程内不直接执行 UI 更新，G2 同款纪律）；
    派发队列 FIFO 保证报告先于完成回调到达（完成态建议动作区先填充、后报完成）。"""
    calls: list[tuple] = []
    report = {"schema_version": "1.0", "candidates": []}
    deps = _deps_with_report(calls, report)
    after_cbs: list = []
    seen: list[dict] = []
    idents: list[int] = []
    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=deps,
        stop=threading.Event(),
        after=after_cbs.append,
        on_progress=lambda event: None,
        on_report=lambda r: (idents.append(threading.get_ident()), seen.append(r)),
        on_complete=lambda p: idents.append(threading.get_ident()),
        on_error=lambda e: pytest.fail("不应进入错误出口"),
    )
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert seen == []  # 工作线程内未直接执行（仅入队）
    assert len(after_cbs) == 2  # 1 报告派发 + 1 完成派发
    for cb in list(after_cbs):  # 主线程侧统一消化
        cb()
    assert seen == [report]
    assert set(idents) == {threading.get_ident()}  # 全部 UI 更新发生在主线程侧


def test_run_audit_async_without_on_report_no_report_dispatch():
    """不传 on_report：派发队列仅完成回调一条（旧契约零额外派发）。"""
    calls: list[tuple] = []
    deps = _deps_with_report(calls, {"schema_version": "1.0", "candidates": []})
    after_cbs: list = []
    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=deps,
        stop=threading.Event(),
        after=after_cbs.append,
        on_progress=lambda event: None,
        on_complete=lambda p: None,
        on_error=lambda e: pytest.fail("不应进入错误出口"),
    )
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(after_cbs) == 1
    for cb in list(after_cbs):
        cb()
