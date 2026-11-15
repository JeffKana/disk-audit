"""T5-02-B1 记录UI展示与I3只读列表 · 真实行为回归（契约 T502B1-v1 / DR-018）。

覆盖（逐条对应任务卡验收②③④）：
- 真实 GUI 接线：假 Tk 控件树 + 真实延期 after 队列，点击"开始体检"实际抵达
  `_on_start` → `run_audit_async(on_record=...)`；完成回调实际写独立记录状态行，
  报告完成文案不被覆盖；刷新按钮实际触发后台 `records.list_records`。
- 本会话 latch / generation：跨会话迟到回执只影响独立行且过期即丢弃；新扫描清空旧态。
- 如实呈现：成功 / 失败 / 无回执（record=None 或合法报告但缺回执）/ 不完整 / 环节异常，
  一律不伪造"已保存/未保存"；失败文案不透传原异常。
- I3 列表：后台线程 I/O + 主线程控件写入（线程 ID 显式取证）；乱序刷新只回填最新
  generation；[] 中性文案；可观察异常 → 读取失败文案；坏项 version/mode 未知，
  不把 fallback admin_mode=False 当普通；有效 1.0/1.1 不误判旧版不可比；
  problem（含"旧记录不可比"）可见；按记录ID排序、不截断、全部行可达。
- 真实 records 临时根 save/list 往返：1.0 / 1.1 / 坏 JSON / 未知版本 / 坏 admin 前缀 /
  外来项共存，展示与文件清单一致且零修改（字节/hash 前后相同）。

安全边界：全部根经 tmp_path 注入；不读写真实 LOCALAPPDATA/用户记录；不真实扫描、
不提权、不开浏览器、不淘汰真实报告；tkinter 全程为假模块，不创建真实 Tk 窗口。
BaseException 用自定义哨兵，禁真 KeyboardInterrupt（launcher 模块契约）。
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import threading
import time
import types
from pathlib import Path

import pytest

import launcher
from disk_audit import records
from disk_audit.engine import texts


# ---------------------------------------------------------------------------
# 假 Tk：控件树 + 真实延期队列（after 只排队，主线程 drain 逐条执行）
# ---------------------------------------------------------------------------


class FakeVar:
    """tk.StringVar 替身：记录每次写入的线程 ID 与值（后台/主线程取证）。"""

    def __init__(self, value: str = "", **_kw: object) -> None:
        self._value = value
        self._traces: list = []
        self.writes: list[tuple[int, str]] = []

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value
        self.writes.append((threading.get_ident(), value))
        for callback in list(self._traces):
            callback("var", "", "write")

    def trace_add(self, _mode: str, callback) -> None:
        self._traces.append(callback)


class FakeWidget:
    def __init__(self, master=None, **kw: object) -> None:
        self.master = master
        self.kw = dict(kw)
        self.children: list = []
        self.packed = False
        self.pack_kw: dict = {}
        self.config_history: list[dict] = []
        self.write_threads: list[int] = []
        if master is not None:
            master.children.append(self)

    def pack(self, **kw: object) -> "FakeWidget":
        self.packed = True
        self.pack_kw = dict(kw)
        return self

    def pack_forget(self) -> None:
        self.packed = False

    def config(self, **kw: object) -> None:
        self.kw.update(kw)
        self.config_history.append(dict(kw))
        self.write_threads.append(threading.get_ident())

    configure = config

    def cget(self, key: str) -> object:
        return self.kw.get(key)

    @property
    def display_text(self) -> str:
        var = self.kw.get("textvariable")
        if isinstance(var, FakeVar):
            return var.get()
        return str(self.kw.get("text", ""))


class FakeFrame(FakeWidget):
    pass


class FakeLabelFrame(FakeWidget):
    pass


class FakeLabel(FakeWidget):
    pass


class FakeEntry(FakeWidget):
    pass


class FakeButton(FakeWidget):
    def invoke(self) -> None:
        """真实点击语义：执行 command（产品回调由此抵达，非直接调私有函数）。"""
        self.write_threads.append(threading.get_ident())
        command = self.kw.get("command")
        if command is not None:
            command()


class FakeRadiobutton(FakeWidget):
    def invoke(self) -> None:
        var = self.kw.get("variable")
        if isinstance(var, FakeVar):
            var.set(self.kw.get("value", ""))
        command = self.kw.get("command")
        if command is not None:
            command()


class FakeProgressbar(FakeWidget):
    def __init__(self, master=None, **kw: object) -> None:
        super().__init__(master, **kw)
        self.started: list = []
        self.stopped = 0

    def start(self, interval: int = 0) -> None:
        self.started.append(interval)

    def stop(self) -> None:
        self.stopped += 1


class FakeCombobox(FakeWidget):
    def __init__(self, master=None, **kw: object) -> None:
        super().__init__(master, **kw)
        self._current = -1

    def current(self, index: int | None = None) -> int:
        if index is not None:
            self._current = index
            var = self.kw.get("textvariable")
            values = self.kw.get("values") or ()
            if isinstance(var, FakeVar) and 0 <= index < len(values):
                var.set(values[index])
        return self._current


class FakeListbox(FakeWidget):
    """记录列表控件：insert/delete 记录线程 ID，行全量保留（不截断）。"""

    def __init__(self, master=None, **kw: object) -> None:
        super().__init__(master, **kw)
        self.items: list[str] = []
        self.op_threads: list[tuple[str, int]] = []

    def insert(self, _index: str, *items: str) -> None:
        self.op_threads.append(("insert", threading.get_ident()))
        self.items.extend(items)

    def delete(self, _first: object, _last: object) -> None:
        self.op_threads.append(("delete", threading.get_ident()))
        self.items.clear()

    def size(self) -> int:
        return len(self.items)

    def get(self, first: int, last: int | None = None) -> tuple[str, ...]:
        if last is None:
            return (self.items[first],)
        return tuple(self.items[first:last + 1])

    def yview(self, *_args: object) -> None:
        pass


class FakeScrollbar(FakeWidget):
    def set(self, *_args: object) -> None:
        self.write_threads.append(threading.get_ident())


class FakeRoot:
    """根窗口替身：after 为真实延期队列（只排队），drain 在主线程 FIFO 执行。"""

    def __init__(self) -> None:
        self.pending: list = []
        self.children: list = []
        self.destroyed = False
        self.after_calls = 0
        self.title_text: str | None = None

    def title(self, text: str) -> None:
        self.title_text = text

    def geometry(self, _spec: str) -> None:
        pass

    def minsize(self, _w: int, _h: int) -> None:
        pass

    def after(self, _ms: int, callback) -> int:
        if self.destroyed:
            raise RuntimeError("窗口已销毁")
        self.after_calls += 1
        self.pending.append(callback)
        return self.after_calls

    def drain(self) -> int:
        """主线程逐条执行（含执行中新排队的回调），返回执行条数。"""
        executed = 0
        while self.pending:
            callback = self.pending.pop(0)
            callback()
            executed += 1
        return executed


def install_fake_tk(monkeypatch) -> types.ModuleType:
    """把假 tkinter 注入 sys.modules：build_scope_ui 内部 import 即得假模块。"""
    mod = types.ModuleType("tkinter")
    mod.StringVar = FakeVar
    mod.Frame = FakeFrame
    mod.LabelFrame = FakeLabelFrame
    mod.Label = FakeLabel
    mod.Entry = FakeEntry
    mod.Button = FakeButton
    mod.Radiobutton = FakeRadiobutton
    mod.Listbox = FakeListbox
    mod.Scrollbar = FakeScrollbar
    ttk = types.ModuleType("tkinter.ttk")
    ttk.Progressbar = FakeProgressbar
    ttk.Combobox = FakeCombobox
    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.askdirectory = lambda **_kw: ""
    mod.ttk = ttk
    mod.filedialog = filedialog
    monkeypatch.setitem(sys.modules, "tkinter", mod)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", filedialog)
    return mod


# ---------------------------------------------------------------------------
# 控件树查找（读 UI 实际呈现，不读私有闭包变量）
# ---------------------------------------------------------------------------


def walk(widget):
    yield widget
    for child in getattr(widget, "children", []):
        yield from walk(child)


def find_all(root, cls) -> list:
    return [w for w in walk(root) if isinstance(w, cls)]


def button_by_text(root, text: str) -> FakeButton:
    hits = [w for w in find_all(root, FakeButton) if w.kw.get("text") == text]
    assert len(hits) == 1, f"按钮 {text!r} 应恰有一个，实得 {len(hits)}"
    return hits[0]


def frame_by_text(root, text: str) -> FakeLabelFrame:
    hits = [w for w in find_all(root, FakeLabelFrame) if w.kw.get("text") == text]
    assert len(hits) == 1, f"区块 {text!r} 应恰有一个，实得 {len(hits)}"
    return hits[0]


def record_line(root) -> FakeLabel:
    frame = frame_by_text(root, texts.RECORD_UI_TEXTS["record_group"])
    labels = [w for w in frame.children if isinstance(w, FakeLabel)]
    assert len(labels) == 1, "普通体检记录状态行应恰有一条"
    return labels[0]


def records_box(root) -> FakeListbox:
    frame = frame_by_text(root, texts.RECORD_UI_TEXTS["records_group"])
    boxes = [w for w in walk(frame) if isinstance(w, FakeListbox)]
    assert len(boxes) == 1, "记录列表控件应恰有一个"
    return boxes[0]


def records_summary(root) -> FakeLabel:
    frame = frame_by_text(root, texts.RECORD_UI_TEXTS["records_group"])
    labels = [w for w in frame.children
              if isinstance(w, FakeLabel) and isinstance(w.kw.get("textvariable"), FakeVar)]
    assert len(labels) == 1, "记录列表汇总行应恰有一条"
    return labels[0]


def status_label(root) -> FakeLabel:
    """底部报告状态栏（G3/G2 文案落点）：bottom Frame 内唯一 textvariable Label。"""
    buttons = [w for w in find_all(root, FakeButton)
               if w.kw.get("text") == texts.LAUNCHER_TEXTS["start_button"]]
    bottom = buttons[0].master
    labels = [w for w in bottom.children
              if isinstance(w, FakeLabel) and isinstance(w.kw.get("textvariable"), FakeVar)]
    assert len(labels) == 1
    return labels[0]


def select_scope(root, path: str) -> None:
    hits = [w for w in find_all(root, FakeRadiobutton) if w.kw.get("value") == path]
    assert len(hits) == 1, f"范围单选 {path!r} 应恰有一个"
    hits[0].invoke()


def settle(root, timeout: float = 10.0) -> None:
    """等后台线程结束并 drain 主线程队列（真实线程 + 真实队列，非即时 after）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.drain()
        workers = [t for t in threading.enumerate()
                   if t.name in ("diskaudit-records", "diskaudit-audit") and t.is_alive()]
        if not workers:
            root.drain()
            return
        for worker in workers:
            worker.join(0.05)
    raise AssertionError("后台线程未在超时内结束")


# ---------------------------------------------------------------------------
# 合成报告 / 流水线替身（全部临时根，零真实扫描/浏览器/提权）
# ---------------------------------------------------------------------------


def valid_report(admin: bool = False, version: str = "1.1") -> dict:
    report: dict = {
        "schema_version": version,
        "generated_at": "2026-11-16T05:00:00+08:00",
        "scan_root": r"C:\synthetic-scope",
        "totals": {
            "allocated_bytes": 1024,
            "logical_bytes": 2048,
            "regenerable_subtotal": 0,
            "regenerable_confirm_subtotal": 0,
            "skipped_entries": 0,
        },
        "candidates": [
            {
                "path": r"C:\synthetic-scope\demo",
                "logical_bytes": 2048,
                "allocated_bytes": 1024,
                "confidence": "中",
                "verdict_source": "知识库",
                "evidence_chain": [{"source": "知识库", "content": "合成样例"}],
                "suggested_action": "A5",
            }
        ],
    }
    if admin:
        report["admin_mode"] = True
    return report


def make_deps(
    tmp_path: Path,
    *,
    report: dict | None = None,
    scan_result: dict | None = None,
    record_ring=True,
    record_error: Exception | None = None,
    stage_error: tuple[str, Exception] | None = None,
):
    """真实 save/prune/record（临时根）+ 合成 scan/judge/render + open 为 no-op。"""
    import dataclasses

    base = launcher.default_deps(
        reports_dir=str(tmp_path / "reports"), records_dir=str(tmp_path / "records")
    )
    payload = report if report is not None else valid_report()
    calls: list[str] = []

    def scan(path, progress_cb=None, abort_check=None):
        calls.append("scan")
        if scan_result is not None:
            return scan_result
        return {"root": path, "entries": 0, "skipped": {}, "units": []}

    def judge(scan_data):
        calls.append("judge")
        return payload

    def render(_report):
        calls.append("render")
        return "<html>T502B1-synthetic</html>"

    def open_noop(_path):
        calls.append("open")

    ring = None
    if record_ring:
        real_record = base.record

        def ring(report_dict):
            calls.append("record")
            if record_error is not None:
                raise record_error
            return real_record(report_dict)

    deps = dataclasses.replace(
        base, scan=scan, judge=judge, render=render, open=open_noop, record=ring
    )
    if stage_error is not None:
        stage, exc = stage_error

        def fail(*_a, **_k):
            raise exc

        object.__setattr__(deps, stage, fail)
    return deps, calls


@pytest.fixture
def gui(tmp_path, monkeypatch):
    """假 Tk + 真实 build_scope_ui + run_audit_async 间谍（捕获真实回调闭包）。"""
    install_fake_tk(monkeypatch)
    records_dir = tmp_path / "records"
    monkeypatch.setattr(records, "RECORDS_DIR", str(records_dir))

    captured: list[dict] = []
    real_async = launcher.run_audit_async

    def spy_async(path, **kwargs):
        captured.append({"path": path, **kwargs})
        return real_async(path, **kwargs)

    monkeypatch.setattr(launcher, "run_audit_async", spy_async)

    state: dict = {"deps": None, "calls": None}

    def build(deps=None, calls=None):
        if deps is not None:
            state["deps"] = deps
            state["calls"] = calls
            monkeypatch.setattr(launcher, "default_deps", lambda *a, **k: deps)
        root = FakeRoot()
        scope = tmp_path / "scope"
        scope.mkdir(exist_ok=True)
        presets = [launcher.PresetRow("synthetic", f"合成范围：{scope}", str(scope))]
        entries = launcher.build_drive_entries({"C:": launcher.DRIVE_FIXED})
        launcher.build_scope_ui(root, entries, presets, launcher.MIN_BUILD)
        return root

    return types.SimpleNamespace(
        root=None, build=build, captured=captured, tmp_path=tmp_path,
        records_dir=records_dir, state=state, monkeypatch=monkeypatch,
    )


def start_scan(gui, deps=None, calls=None):
    """实际点击"开始体检"（真实回调链，非直接调 _on_start）。"""
    root = gui.build(deps, calls)
    gui.root = root
    select_scope(root, str(gui.tmp_path / "scope"))
    button_by_text(root, texts.LAUNCHER_TEXTS["start_button"]).invoke()
    return root


# ---------------------------------------------------------------------------
# 验收③：真实 GUI 接线 —— _on_start 必须把 on_record 交给流水线
# ---------------------------------------------------------------------------


def test_on_start_passes_on_record_to_pipeline(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    assert len(gui.captured) == 1, "点击开始体检应恰发起一次后台流水线"
    assert gui.captured[0].get("on_record") is not None, (
        "旧 GUI 行为缺陷：_on_start 未把 on_record 交给 run_audit_async，记录回执永远到不了界面"
    )
    assert "record" in calls


def test_start_button_is_real_command_wiring(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    button = button_by_text(root, texts.LAUNCHER_TEXTS["start_button"])
    assert button.kw.get("command") is not None
    assert calls[0] == "scan"


# ---------------------------------------------------------------------------
# 验收②：独立记录状态行 —— 成功 / 失败 / 缺失 / 不完整 / 异常
# ---------------------------------------------------------------------------


def test_record_success_visible_once_and_report_text_preserved(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    line = record_line(root)
    saved = [v for _t, v in line.kw["textvariable"].writes
             if v.startswith(texts.RECORD_UI_TEXTS["record_saved"].split("{")[0])]
    assert len(saved) == 1, f"成功回执应恰呈现一次，实得 {saved}"
    ids = sorted(p.stem for p in gui.records_dir.glob("*.json"))
    assert len(ids) == 1
    assert ids[0] in line.display_text
    report_text = texts.G3_TEXTS["status_report_opened"].format(
        path=str(gui.tmp_path / "reports" / sorted(
            p.name for p in (gui.tmp_path / "reports").glob("*.html"))[0])
    )
    assert status_label(root).display_text == report_text, "报告完成文案不得被记录回执覆盖"


def test_record_failure_shows_generic_error_not_original_exception(gui):
    secret = "原始异常细节 C:\\Users\\真实用户名\\不该外泄"
    deps, calls = make_deps(gui.tmp_path, record_error=records.RecordWriteError(secret))
    root = start_scan(gui, deps, calls)
    settle(root)
    line = record_line(root)
    assert line.display_text == texts.RECORD_UI_TEXTS["record_failed"]
    assert secret not in line.display_text
    assert "真实用户名" not in line.display_text
    assert status_label(root).display_text.startswith(
        texts.G3_TEXTS["status_report_opened"].split("{")[0]
    ), "记录失败不得改变报告完成文案"
    assert list((gui.tmp_path / "reports").glob("*.html")), "报告仍应真实落盘"


def test_no_record_ring_only_says_not_provided(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    assert "record" not in calls
    assert record_line(root).display_text == texts.RECORD_UI_TEXTS["record_not_provided"]
    assert status_label(root).display_text.startswith(
        texts.G3_TEXTS["status_report_opened"].split("{")[0]
    )


def test_incomplete_scan_does_not_fabricate_record_result(gui):
    deps, calls = make_deps(
        gui.tmp_path, scan_result={"incomplete": True, "root": "x"}
    )
    root = start_scan(gui, deps, calls)
    settle(root)
    assert calls == ["scan"]
    line = record_line(root).display_text
    assert line == texts.RECORD_UI_TEXTS["record_incomplete"]
    assert texts.RECORD_UI_TEXTS["record_saved"].split("{")[0] not in line
    assert texts.RECORD_UI_TEXTS["record_failed"] not in line
    assert not gui.records_dir.exists() or list(gui.records_dir.glob("*.json")) == []


@pytest.mark.parametrize("stage", ["scan", "judge", "render", "save"])
def test_stage_failure_does_not_fabricate_record_result(gui, stage):
    deps, calls = make_deps(
        gui.tmp_path, stage_error=(stage, RuntimeError(stage + "-boom"))
    )
    root = start_scan(gui, deps, calls)
    settle(root)
    line = record_line(root).display_text
    assert line == texts.RECORD_UI_TEXTS["record_incomplete"]
    assert texts.RECORD_UI_TEXTS["record_saved"].split("{")[0] not in line
    assert status_label(root).display_text == texts.G3_TEXTS["status_audit_failed"].format(
        reason=stage + "-boom"
    )


def test_new_scan_clears_previous_record_state(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    first = record_line(root).display_text
    assert first != texts.RECORD_UI_TEXTS["record_idle"]
    select_scope(root, str(gui.tmp_path / "scope"))
    button_by_text(root, texts.LAUNCHER_TEXTS["start_button"]).invoke()
    assert record_line(root).display_text == texts.RECORD_UI_TEXTS["record_pending"], (
        "新扫描发起即应清空上一次记录状态"
    )
    settle(root)


def capture_notifications(gui) -> list:
    """捕获真实延期执行闭包（_record_notification 产物 = after 队列实际 drain 的对象）。"""
    captured: list = []
    real = launcher._record_notification

    def spy(on_record, payload):
        notify = real(on_record, payload)
        captured.append(notify)
        return notify

    gui.monkeypatch.setattr(launcher, "_record_notification", spy)
    return captured


def test_cross_session_late_receipt_is_discarded(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    stale_on_record = gui.captured[0].get("on_record")
    assert stale_on_record is not None
    select_scope(root, str(gui.tmp_path / "scope"))
    button_by_text(root, texts.LAUNCHER_TEXTS["start_button"]).invoke()
    settle(root)
    current = record_line(root).display_text
    assert len(gui.captured) == 2
    root.after(0, lambda: stale_on_record(
        {"saved": True, "record_id": "record-19990101-000000",
         "report_path": "x", "error": None}))
    root.drain()
    assert record_line(root).display_text == current, "跨会话迟到回执不得改写本次记录状态行"


def test_late_receipt_only_changes_independent_line(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    before_status = status_label(root).display_text
    on_record = gui.captured[0].get("on_record")
    assert on_record is not None
    root.after(0, lambda: on_record(
        {"saved": True, "record_id": "record-20261116-050000",
         "report_path": "x", "error": None}))
    root.drain()
    assert status_label(root).display_text == before_status
    assert "record-20261116-050000" in record_line(root).display_text


def test_record_callback_exception_isolated_but_base_exception_not_swallowed(gui):
    notifications = capture_notifications(gui)
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    assert notifications, "流水线应真实构造延期通知闭包（DR-013 执行点）"
    notify = notifications[0]
    var = record_line(root).kw["textvariable"]
    original_set = var.set
    seen: list = []

    def exploding_set(value):
        seen.append(value)
        raise RuntimeError("控件写入坏")

    var.set = exploding_set
    try:
        notify()  # 真实延期执行点：普通异常不得外泄给调度者
        root.drain()
    finally:
        var.set = original_set
    assert seen, "通知应真实抵达控件写入点"
    assert status_label(root).display_text.startswith(
        texts.G3_TEXTS["status_report_opened"].split("{")[0]
    )

    class _Sentinel(BaseException):
        """自定义 BaseException 哨兵：禁真 KeyboardInterrupt（launcher 模块契约）。"""

    def sentinel_set(_value):
        raise _Sentinel("sentinel-not-a-real-interrupt")

    var.set = sentinel_set
    try:
        with pytest.raises(_Sentinel):
            notify()
            root.drain()
    finally:
        var.set = original_set


def test_after_destroy_is_quiet(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    root.destroyed = True
    select_scope(root, str(gui.tmp_path / "scope"))
    button_by_text(root, texts.LAUNCHER_TEXTS["start_button"]).invoke()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not any(t.name == "diskaudit-audit" and t.is_alive()
                   for t in threading.enumerate()):
            break
        time.sleep(0.02)
    root.drain()
    assert not any(t.name == "diskaudit-audit" and t.is_alive()
                   for t in threading.enumerate())


# ---------------------------------------------------------------------------
# 验收④：后台 I/O + 主线程控件写入 + generation 乱序
# ---------------------------------------------------------------------------


def test_refresh_button_loads_records_in_background(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    io_threads: list[int] = []
    real_list = records.list_records

    def spy_list(*, records_dir=None):
        io_threads.append(threading.get_ident())
        return real_list(records_dir=records_dir)

    gui.monkeypatch.setattr(records, "list_records", spy_list)
    main_thread = threading.get_ident()
    box = records_box(root)
    ops_before = len(box.op_threads)
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    assert len(box.op_threads) == ops_before, "点击不得在主线程同步写列表控件"
    settle(root)
    assert io_threads, "刷新按钮应真实触发后台记录枚举"
    assert all(t != main_thread for t in io_threads), "枚举必须在后台线程"
    assert len(box.op_threads) > ops_before, "列表控件应有真实写入"
    assert all(t == main_thread for _op, t in box.op_threads), "控件写入必须在主线程"
    summary = records_summary(root)
    assert all(t == main_thread for t, _v in summary.kw["textvariable"].writes), (
        "汇总文案写入必须在主线程"
    )


def test_main_thread_does_no_listdir_during_refresh(gui):
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    main_thread = threading.get_ident()
    listdir_threads: list[int] = []
    real_listdir = os.listdir

    def spy_listdir(path="."):
        listdir_threads.append(threading.get_ident())
        return real_listdir(path)

    gui.monkeypatch.setattr(os, "listdir", spy_listdir)
    mark = len(listdir_threads)
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    assert len(listdir_threads) > mark, "刷新应真实发生目录枚举"
    assert main_thread not in listdir_threads[mark:], "主线程零 listdir"


def test_record_receipt_enqueued_by_worker_and_written_on_main_thread(gui):
    """真实延期队列取证：后台线程排队通知闭包，主线程 drain 才写记录状态行。"""
    notif = capture_notifications(gui)
    enqueued: list[tuple[int, object]] = []
    real_after = FakeRoot.after

    def spy_after(self, ms, callback):
        enqueued.append((threading.get_ident(), callback))
        return real_after(self, ms, callback)

    gui.monkeypatch.setattr(FakeRoot, "after", spy_after)
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    main_thread = threading.get_ident()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not any(t.name == "diskaudit-audit" and t.is_alive()
                   for t in threading.enumerate()):
            break
        time.sleep(0.02)
    assert len(notif) == 1, "记录环应恰构造一次延期通知闭包"
    record_enqueues = [(t, cb) for t, cb in enqueued if cb is notif[0]]
    assert len(record_enqueues) == 1, "真实通知闭包必须经 root.after 排队恰一次"
    assert record_enqueues[0][0] != main_thread, "排队发生在后台流水线线程"
    var = record_line(root).kw["textvariable"]
    before = len(var.writes)
    root.drain()
    assert len(var.writes) > before, "drain 之前不得抢先写记录状态行"
    assert all(t == main_thread for t, _v in var.writes), "记录状态行写入必须在主线程"
    assert var.get().startswith(texts.RECORD_UI_TEXTS["record_saved"].split("{")[0])


def test_out_of_order_refresh_only_latest_generation_backfills(gui):
    """乱序到达：较新 generation 先回、较旧 generation 后回且内容更多，仍须丢弃旧的。"""
    import datetime as dt

    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    records_dir = gui.records_dir
    records_dir.mkdir(parents=True, exist_ok=True)
    first = records.save_record(
        valid_report(version="1.0"), records_dir=str(records_dir),
        now=dt.datetime(2026, 11, 16, 5, 0, 0),
    )
    gates = [threading.Event(), threading.Event()]
    snapshots: list[list] = []
    real_list = records.list_records
    index = {"n": 0}

    def gated_list(*, records_dir=None):
        i = index["n"]
        index["n"] += 1
        assert gates[i].wait(10), "后台枚举应在闸门上等待"
        got = real_list(records_dir=records_dir)
        snapshots.append([e.record_id for e in got])
        return got

    gui.monkeypatch.setattr(records, "list_records", gated_list)
    refresh = button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"])
    refresh.invoke()
    refresh.invoke()
    deadline = time.monotonic() + 10
    while index["n"] < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert index["n"] == 2, "两次刷新应各起一次后台枚举"
    gates[1].set()  # 较新 generation 先完成（此时目录只有 1 条）
    deadline = time.monotonic() + 10
    while len(snapshots) < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert snapshots[0] == [first]
    second = records.save_record(
        valid_report(), records_dir=str(records_dir),
        now=dt.datetime(2026, 11, 16, 5, 0, 1),
    )
    gates[0].set()  # 较旧 generation 后完成（此时目录已有 2 条）
    settle(root)
    assert len(snapshots) == 2
    assert snapshots[1] == sorted([first, second])
    box = records_box(root)
    assert box.size() == 1, "过期 generation 的快照不得回填，即使它内容更新"
    assert first in box.items[0]
    assert second not in "\n".join(box.items)
    assert records_summary(root).display_text == texts.RECORD_UI_TEXTS[
        "records_summary_fmt"].format(count=1)


def test_empty_list_uses_neutral_wording(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    assert not gui.records_dir.exists()
    assert records_summary(root).display_text == texts.RECORD_UI_TEXTS["records_empty"]
    assert records_box(root).size() == 0


def test_observable_read_failure_is_disclosed_not_claimed_empty(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    blocker = gui.tmp_path / "records-blocker"
    blocker.write_text("occupied", encoding="utf-8")
    gui.monkeypatch.setattr(records, "RECORDS_DIR", str(blocker))
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    assert records_summary(root).display_text == texts.RECORD_UI_TEXTS["records_read_failed"]
    assert records_summary(root).display_text != texts.RECORD_UI_TEXTS["records_empty"]
    assert blocker.read_text(encoding="utf-8") == "occupied"


def test_refresh_never_scans_saves_prunes_or_elevates(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    mark = len(calls)
    saved_before = sorted(p.name for p in gui.records_dir.glob("*"))
    reports_before = sorted(p.name for p in (gui.tmp_path / "reports").glob("*"))
    elevated_calls: list = []
    gui.monkeypatch.setattr(
        launcher, "request_admin_rescan", lambda *a, **k: elevated_calls.append(a) or 0
    )
    for _ in range(3):
        button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
        settle(root)
    assert calls[mark:] == [], "刷新不得触发扫描/判定/渲染/保存/淘汰/打开"
    assert elevated_calls == []
    assert sorted(p.name for p in gui.records_dir.glob("*")) == saved_before
    assert sorted(p.name for p in (gui.tmp_path / "reports").glob("*")) == reports_before


# ---------------------------------------------------------------------------
# 验收③：真实 records 临时根往返 + 坏项共存 + 零修改
# ---------------------------------------------------------------------------


def build_mixed_records(records_dir: Path) -> dict:
    """1.0 / 1.1 / 1.1admin / 坏JSON / 未知版本 / 坏admin前缀 / 外来项 共存。"""
    records_dir.mkdir(parents=True, exist_ok=True)
    made: dict = {}
    made["v10"] = records.save_record(
        valid_report(version="1.0"), records_dir=str(records_dir),
        now=__import__("datetime").datetime(2026, 11, 16, 5, 0, 0),
    )
    made["v11"] = records.save_record(
        valid_report(), records_dir=str(records_dir),
        now=__import__("datetime").datetime(2026, 11, 16, 5, 0, 1),
    )
    made["admin"] = records.save_record(
        valid_report(admin=True), records_dir=str(records_dir),
        now=__import__("datetime").datetime(2026, 11, 16, 5, 0, 2),
    )
    (records_dir / "record-20261116-050003.json").write_text("{坏 JSON", encoding="utf-8")
    bad_version = valid_report()
    bad_version["schema_version"] = "9.9"
    (records_dir / "record-20261116-050004.json").write_text(
        json.dumps(bad_version, ensure_ascii=False), encoding="utf-8")
    (records_dir / "admin-record-20261116-050005.json").write_text(
        "{坏 admin", encoding="utf-8")
    (records_dir / "外来文件.txt").write_text("foreign", encoding="utf-8")
    (records_dir / ".tmp-record-9999.json").write_text("{}", encoding="utf-8")
    (records_dir / "record-20261116-050006.json").mkdir()
    return made


def test_pipeline_saved_record_roundtrips_into_list_without_manual_click(gui):
    """端到端：真实流水线保存 → on_complete 自动后台刷新 → 列表出现该记录。"""
    deps, calls = make_deps(gui.tmp_path)
    root = start_scan(gui, deps, calls)
    settle(root)
    assert "record" in calls
    prefix = texts.RECORD_UI_TEXTS["record_saved"].split("{")[0]
    line_text = record_line(root).display_text
    assert line_text.startswith(prefix), f"记录环应真实保存并回执，实得 {line_text!r}"
    saved_id = line_text[len(prefix):]
    assert saved_id in {p.stem for p in gui.records_dir.glob("*.json")}, (
        "状态行显示的 record_id 必须是磁盘上真实存在的记录"
    )
    box = records_box(root)
    first_items = list(box.items)
    assert any(r.split(" · ")[0] == saved_id for r in first_items), (
        "on_complete 必须真实触发一次后台刷新并经 after 队列回填，不靠手点按钮"
    )
    row = next(r for r in first_items if r.split(" · ")[0] == saved_id)
    assert "格式可比" in row and "版本 1.1" in row
    assert texts.RECORD_UI_TEXTS["record_mode_normal"] in row
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in gui.records_dir.rglob("*") if p.is_file()}
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    assert records_box(root).items == first_items, "手点刷新结果应与自动刷新一致"
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in gui.records_dir.rglob("*") if p.is_file()}
    assert after == before, "列表刷新不得修改任何记录字节"


def test_real_roundtrip_mixed_records_display_and_zero_modification(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    made = build_mixed_records(gui.records_dir)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in gui.records_dir.rglob("*") if p.is_file()}
    listing_before = sorted(p.name for p in gui.records_dir.iterdir())
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    box = records_box(root)
    entries = records.list_records(records_dir=str(gui.records_dir))
    assert box.size() == len(entries), "全部匹配项可达，不静默截断"
    assert box.size() == 7, "3 有效 + 4 坏项（坏JSON/未知版本/坏admin/同名目录）"
    joined = "\n".join(box.items)
    for key in ("v10", "v11", "admin"):
        assert made[key] in joined
    assert texts.RECORD_UI_TEXTS["record_mode_admin"] in joined
    assert texts.RECORD_UI_TEXTS["record_mode_normal"] in joined
    assert "旧记录不可比" in joined, "不兼容版本 problem 必须可见"
    assert "未知" in joined
    valid_rows = [r for r in box.items if "格式可比" in r]
    assert len(valid_rows) == 3
    for row in valid_rows:
        assert "1.0" in row or "1.1" in row
    assert records_summary(root).display_text == texts.RECORD_UI_TEXTS[
        "records_summary_fmt"].format(count=7)
    assert "按记录ID排序" in records_summary(root).display_text
    assert "最新" not in records_summary(root).display_text
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in gui.records_dir.rglob("*") if p.is_file()}
    assert after == before, "只读列表不得修改任何记录字节"
    assert sorted(p.name for p in gui.records_dir.iterdir()) == listing_before


def test_bad_items_never_claim_normal_mode_or_known_version(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    build_mixed_records(gui.records_dir)
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    box = records_box(root)
    invalid_rows = [r for r in box.items if "格式不可比" in r]
    assert len(invalid_rows) == 4
    for row in invalid_rows:
        assert "版本 未知" in row, "坏项版本必须未知，不从文件名/坏字段捏造"
        assert "模式 未知" in row, "坏项 admin_mode=False 是 fallback，不得当普通模式"
        assert texts.RECORD_UI_TEXTS["record_mode_normal"] not in row
        assert texts.RECORD_UI_TEXTS["record_mode_admin"] not in row
    admin_bad = [r for r in invalid_rows if r.startswith("admin-record-")]
    assert len(admin_bad) == 1
    assert texts.RECORD_UI_TEXTS["record_mode_normal"] not in admin_bad[0]


def test_valid_10_and_11_are_compatible_not_marked_incomparable(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    made = build_mixed_records(gui.records_dir)
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    rows = {r.split(" · ")[0]: r for r in records_box(root).items}
    assert "格式可比" in rows[made["v10"]]
    assert "版本 1.0" in rows[made["v10"]]
    assert "格式可比" in rows[made["v11"]]
    assert "版本 1.1" in rows[made["v11"]]
    assert "旧记录不可比" not in rows[made["v10"]]
    assert "旧记录不可比" not in rows[made["v11"]]


def test_list_order_is_record_id_order_not_time(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    build_mixed_records(gui.records_dir)
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    ids = [r.split(" · ")[0] for r in records_box(root).items]
    assert ids == sorted(ids)
    entries = records.list_records(records_dir=str(gui.records_dir))
    assert ids == [e.record_id for e in entries]


def test_more_than_twelve_records_are_all_reachable(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    gui.records_dir.mkdir(parents=True, exist_ok=True)
    import datetime as dt

    for i in range(15):
        records.save_record(
            valid_report(), records_dir=str(gui.records_dir),
            now=dt.datetime(2026, 11, 16, 5, 0, i),
        )
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    box = records_box(root)
    assert box.size() == 15, "不截前12条"
    assert box.size() == len(records.list_records(records_dir=str(gui.records_dir)))
    assert records_summary(root).display_text == texts.RECORD_UI_TEXTS[
        "records_summary_fmt"].format(count=15)
    scrolls = [w for w in walk(frame_by_text(root, texts.RECORD_UI_TEXTS["records_group"]))
               if isinstance(w, FakeScrollbar)]
    assert len(scrolls) == 1, "应有滚动条使全部行可达"


def test_foreign_names_skipped_and_matching_directory_disclosed_as_invalid(gui):
    deps, calls = make_deps(gui.tmp_path, record_ring=False)
    root = start_scan(gui, deps, calls)
    settle(root)
    build_mixed_records(gui.records_dir)
    button_by_text(root, texts.RECORD_UI_TEXTS["records_refresh"]).invoke()
    settle(root)
    joined = "\n".join(records_box(root).items)
    assert "外来文件" not in joined, "非记录命名不进入列表"
    assert ".tmp-record-" not in joined, "临时写入中间文件不进入列表"
    dir_rows = [r for r in records_box(root).items
                if r.startswith("record-20261116-050006")]
    assert len(dir_rows) == 1, "同名目录被 records 如实披露为坏项，UI 不得吞掉"
    assert "格式不可比" in dir_rows[0]
    assert "版本 未知" in dir_rows[0] and "模式 未知" in dir_rows[0]
    assert "不是普通文件" in dir_rows[0]
    assert texts.RECORD_UI_TEXTS["record_mode_normal"] not in dir_rows[0]


# ---------------------------------------------------------------------------
# 纯函数（必须被 GUI 真实消费——上方 GUI 用例即其见证）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [
    None, {}, [], "x", 3,
    {"saved": True, "record_id": "record-1", "report_path": "p"},
    {"saved": True, "record_id": "record-1", "report_path": "p", "error": None, "extra": 1},
    {"saved": "yes", "record_id": "record-1", "report_path": "p", "error": None},
    {"saved": True, "record_id": None, "report_path": "p", "error": None},
    {"saved": True, "record_id": "", "report_path": "p", "error": None},
    {"saved": True, "record_id": 7, "report_path": "p", "error": None},
])
def test_record_status_text_corrupt_or_missing_receipt_only_says_not_provided(payload):
    assert launcher.record_status_text(payload) == texts.RECORD_UI_TEXTS["record_not_provided"]


def test_record_status_text_success_and_failure():
    ok = {"saved": True, "record_id": "record-20261116-050000",
          "report_path": r"C:\r\report-1.html", "error": None}
    assert launcher.record_status_text(ok) == texts.RECORD_UI_TEXTS["record_saved"].format(
        record_id="record-20261116-050000")
    bad = {"saved": False, "record_id": None,
           "report_path": r"C:\r\report-1.html", "error": "原始异常 C:\\Users\\某人"}
    got = launcher.record_status_text(bad)
    assert got == texts.RECORD_UI_TEXTS["record_failed"]
    assert "某人" not in got and "原始异常" not in got


def test_records_view_model_empty_and_failure():
    assert launcher.records_view_model({"entries": [], "error": None}) == (
        texts.RECORD_UI_TEXTS["records_empty"], [])
    assert launcher.records_view_model({"entries": None, "error": True}) == (
        texts.RECORD_UI_TEXTS["records_read_failed"], [])
    assert launcher.records_view_model(None) == (
        texts.RECORD_UI_TEXTS["records_read_failed"], [])


def test_records_view_model_does_not_mutate_entries(tmp_path):
    entries = records.list_records(records_dir=str(tmp_path / "missing"))
    snapshot = {"entries": entries, "error": None}
    before = copy.deepcopy(snapshot)
    launcher.records_view_model(snapshot)
    assert snapshot == before


def test_load_records_snapshot_is_readonly_and_reports_observable_error(tmp_path, monkeypatch):
    monkeypatch.setattr(records, "RECORDS_DIR", str(tmp_path / "missing"))
    got = launcher.load_records_snapshot()
    assert got["error"] is None and got["entries"] == []
    blocker = tmp_path / "blocker"
    blocker.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(records, "RECORDS_DIR", str(blocker))
    got = launcher.load_records_snapshot()
    assert got["error"] is not None and got["entries"] is None
    assert blocker.read_text(encoding="utf-8") == "occupied"


# ---------------------------------------------------------------------------
# 文案资源（append-only 区块；禁词与 DR-018 逐字口径）
# ---------------------------------------------------------------------------


def test_record_ui_texts_required_keys_exist():
    required = {
        "record_group", "record_idle", "record_pending", "record_saved", "record_failed",
        "record_not_provided", "record_incomplete", "records_group", "records_refresh",
        "records_idle", "records_summary_fmt", "records_empty", "records_read_failed",
        "records_note", "record_row_valid_fmt", "record_row_invalid_fmt",
        "record_mode_normal", "record_mode_admin", "record_problem_unknown",
    }
    assert required <= set(texts.RECORD_UI_TEXTS)
    for key, value in texts.RECORD_UI_TEXTS.items():
        assert isinstance(value, str) and value, key


def test_record_ui_texts_empty_wording_matches_dr018_verbatim():
    assert texts.RECORD_UI_TEXTS["records_empty"] == (
        "未加载到记录（目录可能不存在、为空或暂不可读取）"
    )


def test_record_ui_texts_no_forbidden_terms():
    forbidden = ("可回收", "可释放", "下一步", "立即清理", "一键删除", "已删除", "最新记录")
    for key, value in texts.RECORD_UI_TEXTS.items():
        for term in forbidden:
            assert term not in value, f"{key} 含禁词 {term}"


def test_record_ui_texts_no_delete_or_compare_entry_claim():
    note = texts.RECORD_UI_TEXTS["records_note"]
    assert "只读" in note
    assert "按记录ID排序" in note
    assert "不提供比较、删除或打开历史报告的入口" in note


def test_existing_texts_zones_unchanged():
    assert texts.CONFIDENCE_WORDING["高"] == "高度可能为残留；删除前请确认"
    assert texts.G3_TEXTS["status_report_opened"] == (
        "体检完成，报告已保存并在默认浏览器打开：{path}"
    )
    assert texts.G2_TEXTS["status_incomplete"] == "体检未完成：结果不完整，未生成报告。"
    assert texts.RECORDS_TEXTS["records_err_bad_version"] == (
        "不支持的体检记录版本 {version}：旧记录不可比，请使用对应版本的工具查看"
    )
    assert texts.COMPARISON_TEXTS["comparison_side_before"] == "前一份"
    assert len(texts.EVIDENCE_SOURCE_ENUM) == 9