"""T3-02（待办 F2）report-v1 → 离线单文件 HTML 渲染测试。

依据：任务卡 T3-02 验收①~⑤、方案 E-2（候选七字段）、5.1~5.3（四档/两档/
动作枚举措辞）、Q3（禁"可回收"与合并"可释放"总量）、X-2/C7（不完整报告：
徽标 + 无汇总结论）、R10（零假设：全文档无按钮、无操作入口）、M2 闸②
（断网完整 → 结构性零外链断言）。

测试输入全部为罐装脱敏夹具（schema example + 构造候选）；DOM 断言用标准库
html.parser（禁第三方）；渲染为纯函数（同输入同输出、不修改输入）。
"""
from __future__ import annotations

import ast
import copy
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from disk_audit.engine import render, texts
from disk_audit.engine.report import judge_scan_result
from tests.test_engine_judge import KB, STALE, _bundle

_REPO = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads(
    (_REPO / "docs" / "schemas" / "report-v1.example.json").read_text(encoding="utf-8")
)


def _fixture_report() -> dict:
    """schema example + 一条高置信 A2 候选（覆盖 A2 渲染路径，脱敏罐装数据）。"""
    data = copy.deepcopy(EXAMPLE)
    data["candidates"].insert(
        0,
        {
            "path": r"C:\Users\u\AppData\Roaming\oldapp",
            "logical_bytes": 2048,
            "allocated_bytes": 4096,
            "confidence": "高",
            "verdict_source": "知识库",
            "evidence_chain": [
                {"source": "知识库", "content": "高度可能为残留；删除前请确认"},
                {"source": "注册表卸载项", "content": "注册表无卸载记录"},
            ],
            "suggested_action": "A2",
        },
    )
    return data


# ---------- html.parser 极简 DOM 记录器（标准库，禁第三方） ----------

_ALLOWED_TAGS = frozenset(
    {
        "html", "head", "meta", "title", "style", "body",
        "header", "h1", "h2", "p", "span", "section",
        "table", "thead", "tbody", "tr", "th", "td",
        "details", "summary", "ul", "li", "footer",
    }
)
_ALLOWED_ATTRS = frozenset({"id", "class", "title", "charset", "lang"})
_FORBIDDEN_TAGS = frozenset(
    {"script", "link", "iframe", "embed", "object", "base", "form", "button", "input"}
)


class _Recorder(HTMLParser):
    """记录标签/属性名/文本/section 标题的极简 DOM 记录器。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attr_names: set[str] = set()
        self.text: list[str] = []
        self.sections: list[tuple[str, str]] = []
        self._section: str | None = None
        self._in_h2 = False
        self._h2_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        for name, _value in attrs:
            self.attr_names.add(name)
        mapping = dict(attrs)
        if tag == "section" and "id" in mapping:
            self._section = mapping["id"]
        if tag == "h2":
            self._in_h2 = True
            self._h2_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._in_h2:
            self._in_h2 = False
            if self._section is not None:
                self.sections.append((self._section, "".join(self._h2_buf).strip()))

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._in_h2:
            self._h2_buf.append(data)


def _dom(html_text: str) -> _Recorder:
    recorder = _Recorder()
    recorder.feed(html_text)
    recorder.close()
    return recorder


# ---------- 验收⑤：渲染为纯函数（JSON → HTML 字符串） ----------


def test_render_is_pure_and_does_not_mutate_input():
    report = _fixture_report()
    snapshot = copy.deepcopy(report)
    html_first = render.render_report(report)
    html_second = render.render_report(report)
    assert html_first == html_second  # 同输入同输出，无全局状态
    assert report == snapshot  # 输入 dict 未被修改


def test_document_shape_and_header():
    out = render.render_report(_fixture_report())
    assert out.startswith("<!DOCTYPE html>")
    assert '<html lang="zh-CN">' in out
    assert '<meta charset="UTF-8">' in out
    assert "<style>" in out  # 内联 CSS
    assert out.rstrip().endswith("</html>")
    # 页眉：标题、"只诊断，不动手"、脱敏提示、扫描范围与生成时间
    assert texts.REPORT_TITLE in out
    assert texts.REPORT_MOTTO in out
    assert texts.REPORT_PRIVACY_NOTICE in out
    assert texts.REPORT_LABEL_SCAN_ROOT in out
    assert texts.REPORT_LABEL_GENERATED_AT in out


def test_render_from_parsed_json_text():
    """验收⑤：JSON 文本 → HTML 字符串的完整链路（解析在调用方，渲染为纯函数）。"""
    raw = (_REPO / "docs" / "schemas" / "report-v1.example.json").read_text(encoding="utf-8")
    out = render.render_report(json.loads(raw))
    assert out.startswith("<!DOCTYPE html>")
    assert "</html>" in out


# ---------- 验收①：四区齐备（DOM 断言） ----------


def test_four_zones_present_in_order():
    out = render.render_report(_fixture_report())
    dom = _dom(out)
    expected = [
        ("overview", texts.REPORT_ZONE_OVERVIEW),
        ("details", texts.REPORT_ZONE_DETAILS),
        ("evidence", texts.REPORT_ZONE_EVIDENCE),
        ("actions", texts.REPORT_ZONE_ACTIONS),
    ]
    assert dom.sections == expected


def test_details_table_covers_e2_fields():
    """E-2 候选七字段：六个进明细表列，"证据链"在证据链区呈现（A4 展开）。"""
    out = render.render_report(_fixture_report())
    for label in texts.DETAIL_COLUMNS.values():
        assert label in out
    dom = _dom(out)
    joined = "".join(dom.text)
    # 罐装候选的路径、判定来源、置信度档位均可见
    assert "oldapp" in joined
    assert "知识库" in joined
    assert "高" in joined
    assert '<span class="tag hi">高</span>' in out  # POC-4 配色类


def test_evidence_zone_expands_chain_per_candidate():
    out = render.render_report(_fixture_report())
    summary = texts.EVIDENCE_SUMMARY_FMT.format(count=2)
    assert summary in out  # oldapp 证据链 2 条
    dom = _dom(out)
    assert dom.tags.count("details") == 4  # 每候选一个 details（报告内展开，A4）
    assert "注册表无卸载记录" in "".join(dom.text)


def test_actions_zone_legend_and_distribution():
    out = render.render_report(_fixture_report())
    # 图例：A1~A5 五种固定枚举全部出现（5.3，不新增）
    for key, label in texts.ACTION_LABELS.items():
        assert key in out
        assert label in out
    for description in texts.ACTION_DESCRIPTIONS.values():
        assert description in out
    # 分布：A2/A4 各 1 条、A5 共 2 条（受保护 + 低置信）
    assert texts.ACTION_DISTRIBUTION_FMT.format(label="A2 打开所在文件夹", count=1) in out
    assert texts.ACTION_DISTRIBUTION_FMT.format(label="A4 查看证据链", count=1) in out
    assert texts.ACTION_DISTRIBUTION_FMT.format(label="A5 无建议", count=2) in out


def test_overview_totals_rendered_separately():
    """Q3：可再生两档小计分别列示；总量口径为占用空间（P1）。"""
    out = render.render_report(EXAMPLE)
    assert "50.2 GB（53,860,000,000 字节）" in out
    assert texts.TOTALS_LABELS["regenerable_subtotal"] in out
    assert texts.TOTALS_LABELS["regenerable_confirm_subtotal"] in out
    assert texts.TOTALS_LABELS["skipped_entries"] in out


# ---------- 验收③：受保护项与低置信项固定 A5，无任何"下一步"按钮 ----------


def test_protected_and_low_show_a5_without_any_button():
    out = render.render_report(_fixture_report())
    dom = _dom(out)
    # DOM 断言一：全文档不存在按钮类标签与事件属性（受保护项自然也无）
    assert not _FORBIDDEN_TAGS & set(dom.tags)
    assert dom.attr_names <= _ALLOWED_ATTRS
    # DOM 断言二："下一步"字样与 JS 入口全文档零出现
    joined = "".join(dom.text)
    assert "下一步" not in joined
    assert "onclick" not in out
    assert "javascript:" not in out
    # 受保护项与低置信项动作单元格均为"A5 无建议"
    assert out.count("A5 无建议</td>") >= 2


# ---------- 验收④：incomplete 输入 → 徽标 + 无汇总结论区 ----------


def test_incomplete_badge_and_no_summary_zone():
    data = copy.deepcopy(EXAMPLE)
    data["incomplete"] = True
    out = render.render_report(data)
    assert texts.INCOMPLETE_BADGE in out  # 徽标
    assert texts.INCOMPLETE_NOTE in out
    # 无汇总结论：totals 五字段标签与数值一律不出现（X-2/C7）
    for key in (
        "allocated_bytes",
        "logical_bytes",
        "regenerable_subtotal",
        "regenerable_confirm_subtotal",
        "skipped_entries",
    ):
        assert texts.TOTALS_LABELS[key] not in out
    assert "53,860,000,000" not in out
    assert "50.2 GB" not in out
    # 已采集的部分结果（候选）仍保留展示
    assert "Microsoft\\Protect" in out


def test_complete_report_has_totals_and_no_badge():
    out = render.render_report(EXAMPLE)
    assert texts.INCOMPLETE_BADGE not in out
    assert texts.TOTALS_LABELS["allocated_bytes"] in out


# ---------- 验收②等效口径：结构性零外链（无 http(s) 引用、无外部 src/href） ----------


@pytest.mark.parametrize("incomplete", [False, True])
def test_zero_external_references(incomplete: bool):
    data = copy.deepcopy(EXAMPLE)
    if incomplete:
        data["incomplete"] = True
    out = render.render_report(data)
    assert "http://" not in out
    assert "https://" not in out
    dom = _dom(out)
    assert not _FORBIDDEN_TAGS & set(dom.tags)  # 无 script/link/iframe 等
    assert dom.attr_names <= _ALLOWED_ATTRS  # 无 href/src/action/srcset
    assert "@import" not in out
    assert "url(" not in out


# ---------- R10 零假设与文案纪律 ----------


def test_q3_banned_words_absent():
    out = render.render_report(_fixture_report())
    assert "可回收" not in out
    assert "可释放" not in out


def test_no_chinese_literals_in_renderer_module():
    """对外文案一律取自 texts.py：渲染模块源码不得散落中文字符串字面量
    （docstring 除外；开发规范 §1"不散落硬编码"的可执行守卫）。"""
    source_path = _REPO / "disk_audit" / "engine" / "render.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    docstring_ids = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    cjk = re.compile(r"[\u4e00-\u9fff]")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_ids
        ):
            assert not cjk.search(node.value), f"渲染模块硬编码中文：{node.value!r}"


# ---------- 输入校验（中文异常文案，Q7 版本语义） ----------


def test_invalid_inputs_raise_valueerror():
    with pytest.raises(ValueError) as exc:
        render.render_report(["not", "a", "dict"])  # type: ignore[list-item]
    assert texts.RENDER_ERR_NOT_OBJECT in str(exc.value)

    with pytest.raises(ValueError) as exc:
        render.render_report({"schema_version": "1.0"})  # type: ignore[dict-item]
    assert "generated_at" in str(exc.value)

    bad_version = copy.deepcopy(EXAMPLE)
    bad_version["schema_version"] = "2.0"
    with pytest.raises(ValueError) as exc:
        render.render_report(bad_version)
    assert "2.0" in str(exc.value)

    bad_candidate = copy.deepcopy(EXAMPLE)
    del bad_candidate["candidates"][0]["evidence_chain"]
    with pytest.raises(ValueError) as exc:
        render.render_report(bad_candidate)
    assert "evidence_chain" in str(exc.value)


def test_hostile_strings_are_escaped():
    """路径/证据含 HTML 敏感字符时转义，不产生可执行标记（R10/安全底线）。"""
    data = copy.deepcopy(EXAMPLE)
    data["candidates"] = [
        {
            "path": r'C:\Users\u\AppData\Roaming\<script>alert("x")&</script>',
            "logical_bytes": 0,
            "allocated_bytes": 0,
            "confidence": "低",
            "verdict_source": "启发式",
            "evidence_chain": [{"source": "启发式", "content": 'a<b & "c"'}],
            "suggested_action": "A5",
        }
    ]
    out = render.render_report(data)
    assert "<script>" not in out
    assert "<script" not in out
    assert "&lt;script&gt;" in out
    assert "alert(&quot;x&quot;)" in out


def test_empty_candidates_renders_empty_note():
    data = copy.deepcopy(EXAMPLE)
    data["candidates"] = []
    out = render.render_report(data)
    assert texts.REPORT_NO_CANDIDATES in out


# ---------- 端到端：judge 罐装输出 → 渲染（验收①的 CI 可复现部分） ----------


def test_judge_real_pipeline_output_renders():
    """scan dict → judge（注入罐装证据/知识库）→ schema 校验 → 渲染成功。

    夹具取 updater（更新缓存）/受保护/未知长尾三条路径——均为判定输出过定稿
    schema 的干净分支；真实本机 scan→judge 的渲染验证在任务卡执行时单独留档
    （真实路径不进 git）。
    """
    from tests._mini_schema import mini_validate

    scan = {
        "root": r"C:\Users\u\AppData\Roaming",
        "units": [
            {
                "path": r"C:\Users\u\AppData\Roaming\Microsoft\Protect",
                "files": 2, "dirs": 1, "logical_bytes": 40960,
                "allocated_bytes": 40960, "max_mtime": STALE, "exe_files": 0,
            },
            {
                "path": r"C:\Users\u\AppData\Roaming\xmind-vana-updater",
                "files": 5, "dirs": 2, "logical_bytes": 2048000,
                "allocated_bytes": 2084864, "max_mtime": STALE, "exe_files": 0,
            },
            {
                "path": r"C:\Users\u\AppData\Roaming\zzz-unknown-tail",
                "files": 8, "dirs": 3, "logical_bytes": 40960,
                "allocated_bytes": 45056, "max_mtime": STALE, "exe_files": 1,
            },
        ],
        "allocated_bytes": 2170880,
        "logical_bytes": 2131712,
        "skipped": {"total": 3},
    }
    report = judge_scan_result(scan, bundle=_bundle(), kb=KB)
    schema = json.loads(
        (_REPO / "docs" / "schemas" / "report-v1.schema.json").read_text(encoding="utf-8")
    )
    assert mini_validate(report, schema) == []
    out = render.render_report(report)
    dom = _dom(out)
    assert len(dom.sections) == 4  # 四区齐备
    assert "A5 无建议</td>" in out  # 受保护项（硬保护短路）固定 A5
    assert not _FORBIDDEN_TAGS & set(dom.tags)


def test_evidence_source_out_of_enum_still_renders():
    """防御性渲染：证据链 source 不在 schema 枚举（如 judge.py 已停止分支现产出的
    "进程服务"，见执行记录未尽事项）时照常展示，不崩溃——渲染器不做枚举强校验。"""
    data = copy.deepcopy(EXAMPLE)
    data["candidates"][0]["evidence_chain"].append(
        {"source": "进程服务", "content": "无匹配进程/服务/自启动"}
    )
    out = render.render_report(data)
    assert "无匹配进程/服务/自启动" in "".join(_dom(out).text)
