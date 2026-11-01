"""report-v1 → 离线单文件 HTML 渲染（待办 F2，任务卡 T3-02）。

依据：方案 E-2（每条候选七字段）、5.1~5.3（置信度四档 / 可再生两档 / 建议动作
固定枚举的对外措辞）、Q3（禁"可回收"字样与合并"可释放"总量）、X-2/C7（不完整
报告：徽标 + 无汇总结论区）、U-2/U-4（报告为纯展示页面，不提供任何操作入口）、
R10（零假设原则：可能被非开发者误解的措辞一律保守，宁可少说）、产品待办 F2
（概览 / 明细 / 证据链 / 建议动作四区）。

渲染为纯函数：render_report(report: dict) -> str，无 I/O、无全局状态、不修改
输入；JSON 文本解析由调用方承担（CLI render 子命令 / T3-06 结果入口），与
开发规范 §1"I/O 与纯函数分离"同构。单文件内联 CSS，零 JS、零外链（无
http(s) 引用、无 src/href 属性——M2 闸②"断网完整"的结构性保障；明细筛选等
交互由 T3-03 叠加原生 JS 实现）。配色与表格基线沿用 POC-4
（docs/upstream/poc/poc4_gen_bigreport.py 的 CLS 四色与表格样式）。

四区结构：
- overview 概览：totals 五字段（两档小计分别列示；占用空间口径）+ 元信息；
  incomplete 时不输出任何汇总数据（X-2/C7）。
- details 明细：候选表（路径/逻辑大小/占用空间/置信度/判定来源/建议动作）。
- evidence 证据链：每候选一个 <details> 报告内展开（5.3 A4"查看证据链"原义，
  无外部调用）。
- actions 建议动作：A1~A5 固定枚举图例 + 各动作条数分布；全文档无按钮
  （受保护项与低置信项固定 A5，不提供任何"下一步"入口）。

对外文案一律取自 texts.py（tests/test_engine_render.py 以 AST 守卫本模块
不得散落中文字符串字面量）。
"""
from __future__ import annotations

import html

from . import texts

# Q7 版本语义：schema_version = major.minor；major 不为 1 → 拒绝渲染，
# 由调用方以 ValueError 呈现"旧记录不可比"，不静默错读。
_SUPPORTED_MAJOR = "1."

# report-v1 必需字段（docs/schemas/report-v1.schema.json 定稿；校验与 schema 对齐）
_REQUIRED_TOP = ("schema_version", "generated_at", "scan_root", "totals", "candidates")
_REQUIRED_TOTALS = (
    "allocated_bytes",
    "logical_bytes",
    "regenerable_subtotal",
    "regenerable_confirm_subtotal",
    "skipped_entries",
)
_REQUIRED_CANDIDATE = (
    "path",
    "logical_bytes",
    "allocated_bytes",
    "confidence",
    "verdict_source",
    "evidence_chain",
    "suggested_action",
)
_ACTION_KEYS = ("A1", "A2", "A3", "A4", "A5")  # 5.3 固定枚举，不新增

# 证据链 source 九值枚举（docs/schemas/report-v1.schema.json 定稿，逐字常量
# 维护在 texts.EVIDENCE_SOURCE_ENUM，tests 有防漂移对照断言）。T3-07（08 报告
# §3 裁决 1）：source 不在枚举的输入拒绝渲染——拒绝并披露优于静默渲染。
_ALLOWED_EVIDENCE_SOURCES = frozenset(texts.EVIDENCE_SOURCE_ENUM)

# 置信度档位 → POC-4 配色类（映射随档位枚举维护在 texts.py，本模块零中文常量）
_CONFIDENCE_CLASS = texts.CONFIDENCE_CSS_CLASSES

# 明细表列序（E-2 七字段中的六个；第七字段"证据链"在 evidence 区展开）
_DETAIL_COLUMNS = (
    "path",
    "logical_bytes",
    "allocated_bytes",
    "confidence",
    "verdict_source",
    "suggested_action",
)

# 内联 CSS：POC-4 配色基线；零 url()/@import/外链字体
_CSS = (
    "body{margin:0;padding:24px;background:#f6f7f9;color:#1f2937;"
    'font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}'
    "h1{font-size:20px;margin:0 0 6px}"
    "h2{font-size:16px;margin:0 0 10px;border-left:4px solid #1d4ed8;padding-left:8px}"
    ".bar{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;margin:12px 0}"
    ".motto{font-size:13px;color:#166534;background:#dcfce7;border-radius:6px;"
    "padding:2px 8px;font-weight:600;vertical-align:middle}"
    ".badge{display:inline-block;background:#fef3c7;color:#92400e;border:1px solid #f59e0b;"
    "border-radius:6px;padding:2px 10px;font-weight:700}"
    ".note{color:#6b7280;font-size:12.8px}"
    "table{width:100%;border-collapse:collapse;background:#fff;font-size:12.8px}"
    "th{position:sticky;top:0;background:#f3f4f6;text-align:left;padding:6px 8px;"
    "border:1px solid #e5e7eb}"
    "td{padding:5px 8px;border:1px solid #eef0f2;vertical-align:top}"
    "tr:nth-child(even) td{background:#fafafa}"
    ".num{text-align:right}"
    ".path{word-break:break-all}"
    ".hi{background:#fee2e2;color:#991b1b;font-weight:700}"
    ".mid{background:#fef3c7;color:#92400e}"
    ".low{background:#e5e7eb;color:#374151}"
    ".prot{background:#ede9fe;color:#5b21b6;font-weight:700}"
    ".tag{display:inline-block;border-radius:4px;padding:0 6px}"
    "details{margin:6px 0}"
    "summary{cursor:pointer}"
    ".src{display:inline-block;background:#f3f4f6;border:1px solid #e5e7eb;border-radius:4px;"
    "padding:0 6px;margin-right:6px;font-size:12px}"
    "footer{color:#6b7280;font-size:12.8px;margin-top:16px}"
)


def _e(text: object) -> str:
    """HTML 转义（含引号，属性上下文安全）。"""
    return html.escape(str(text), quote=True)


def _as_int(value: object) -> int:
    """数值字段收整；非法输入抛 ValueError（中文文案），不让 TypeError 逸出。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(texts.RENDER_ERR_BAD_NUMBER) from exc


def _fmt_bytes(n: int) -> str:
    """字节数 → 人读大小（二进制口径 KB=1024，与资源管理器"占用空间"一致；确定性）。"""
    value = float(_as_int(n))
    units = texts.SIZE_UNITS
    for index, unit in enumerate(units):
        if value < 1024 or index == len(units) - 1:
            if index == 0:
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {units[-1]}"  # 不可达（循环必有返回），仅为类型完备


def _exact_bytes(n: int) -> str:
    """字节数的精确呈现（千分位分隔，locale 无关）。"""
    return texts.SIZE_EXACT_FMT.format(total=f"{_as_int(n):,}")


def _size_cell(n: int) -> str:
    """明细表尺寸单元格：人读大小 + title 悬浮精确字节。"""
    return f'<td class="num" title="{_e(_exact_bytes(n))}">{_e(_fmt_bytes(n))}</td>'


def _validate(report: object) -> None:
    """输入校验：与 report-v1 schema 必需字段对齐，不符抛 ValueError（中文）；
    证据链 source 不在九值枚举同样拒绝（T3-07，拒绝并披露优于静默渲染）。"""
    if not isinstance(report, dict):
        raise ValueError(texts.RENDER_ERR_NOT_OBJECT)
    missing = [key for key in _REQUIRED_TOP if key not in report]
    if missing:
        raise ValueError(texts.RENDER_ERR_MISSING_FIELDS.format(fields="、".join(missing)))
    version = report["schema_version"]
    if not isinstance(version, str) or not version.startswith(_SUPPORTED_MAJOR):
        raise ValueError(texts.RENDER_ERR_BAD_VERSION.format(version=version))
    totals = report["totals"]
    if not isinstance(totals, dict):
        raise ValueError(texts.RENDER_ERR_TOTALS_NOT_OBJECT)
    missing = [key for key in _REQUIRED_TOTALS if key not in totals]
    if missing:
        raise ValueError(texts.RENDER_ERR_MISSING_FIELDS.format(fields="、".join(missing)))
    candidates = report["candidates"]
    if not isinstance(candidates, list):
        raise ValueError(texts.RENDER_ERR_CANDIDATES_NOT_LIST)
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(texts.RENDER_ERR_CANDIDATE_NOT_OBJECT.format(index=index))
        missing = [key for key in _REQUIRED_CANDIDATE if key not in candidate]
        if missing:
            raise ValueError(
                texts.RENDER_ERR_CANDIDATE_MISSING.format(index=index, fields="、".join(missing))
            )
        chain = candidate["evidence_chain"]
        if isinstance(chain, list):
            for position, item in enumerate(chain, start=1):
                if (
                    isinstance(item, dict)
                    and "source" in item
                    and item["source"] not in _ALLOWED_EVIDENCE_SOURCES
                ):
                    raise ValueError(texts.RENDER_ERR_BAD_EVIDENCE_SOURCE.format(
                        index=index, position=position, source=item["source"],
                        expected="、".join(texts.EVIDENCE_SOURCE_ENUM),
                    ))


def _head(report: dict) -> str:
    title = f"{texts.REPORT_TITLE} · {report['scan_root']}"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        f"<title>{_e(title)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
    )


def _header(report: dict, incomplete: bool) -> str:
    parts = ['<header class="bar">']
    parts.append(
        f'<h1>{_e(texts.REPORT_TITLE)} <span class="motto">{_e(texts.REPORT_MOTTO)}</span></h1>'
    )
    if incomplete:
        parts.append(f'<p><span class="badge">{_e(texts.INCOMPLETE_BADGE)}</span></p>')
    parts.append(f'<p class="note">{_e(texts.REPORT_PRIVACY_NOTICE)}</p>')
    parts.append(
        f"<p>{_e(texts.REPORT_LABEL_SCAN_ROOT)}：{_e(report['scan_root'])}"
        f" · {_e(texts.REPORT_LABEL_GENERATED_AT)}：{_e(report['generated_at'])}</p>"
    )
    parts.append("</header>")
    return "".join(parts)


def _overview(report: dict, incomplete: bool) -> str:
    parts = ['<section id="overview" class="bar">']
    parts.append(f"<h2>{_e(texts.REPORT_ZONE_OVERVIEW)}</h2>")
    if incomplete:
        # X-2/C7：部分结果保留展示，但汇总结论一律不输出
        parts.append(f'<p class="note">{_e(texts.INCOMPLETE_NOTE)}</p>')
        parts.append(f"<p>{_e(texts.INCOMPLETE_TOTALS_UNAVAILABLE)}</p>")
    else:
        totals = report["totals"]
        parts.append("<table><tbody>")
        for key in _REQUIRED_TOTALS:
            label = texts.TOTALS_LABELS[key]
            value = _as_int(totals[key])
            if key == "skipped_entries":
                cell = f"<td>{value}</td>"
            else:
                cell = f"<td>{_e(_fmt_bytes(value))}（{_e(_exact_bytes(value))}）</td>"
            parts.append(f"<tr><th>{_e(label)}</th>{cell}</tr>")
        parts.append("</tbody></table>")
    count = len(report["candidates"])
    parts.append(
        f"<p>{_e(texts.REPORT_LABEL_CANDIDATE_COUNT)}：{count} {_e(texts.REPORT_UNIT_ITEMS)}</p>"
    )
    parts.append("</section>")
    return "".join(parts)


def _confidence_tag(confidence: object) -> str:
    label = _e(confidence)
    cls = _CONFIDENCE_CLASS.get(str(confidence))
    if cls is None:
        return label
    return f'<span class="tag {cls}">{label}</span>'


def _action_cell(suggested_action: object) -> str:
    key = str(suggested_action)
    label = texts.ACTION_LABELS.get(key, key)
    return f"<td>{_e(key)} {_e(label)}</td>"


def _detail_row(candidate: dict) -> str:
    cells = [
        f'<td class="path">{_e(candidate["path"])}</td>',
        _size_cell(_as_int(candidate["logical_bytes"])),
        _size_cell(_as_int(candidate["allocated_bytes"])),
        f"<td>{_confidence_tag(candidate['confidence'])}</td>",
        f"<td>{_e(candidate['verdict_source'])}</td>",
        _action_cell(candidate["suggested_action"]),
    ]
    return "<tr>" + "".join(cells) + "</tr>"


def _details(candidates: list) -> str:
    parts = ['<section id="details" class="bar">']
    parts.append(f"<h2>{_e(texts.REPORT_ZONE_DETAILS)}</h2>")
    if not candidates:
        parts.append(f'<p class="note">{_e(texts.REPORT_NO_CANDIDATES)}</p>')
        parts.append("</section>")
        return "".join(parts)
    parts.append("<table><thead><tr>")
    for key in _DETAIL_COLUMNS:
        parts.append(f"<th>{_e(texts.DETAIL_COLUMNS[key])}</th>")
    parts.append("</tr></thead><tbody>")
    for candidate in candidates:
        parts.append(_detail_row(candidate))
    parts.append("</tbody></table></section>")
    return "".join(parts)


def _evidence(candidates: list) -> str:
    parts = ['<section id="evidence" class="bar">']
    parts.append(f"<h2>{_e(texts.REPORT_ZONE_EVIDENCE)}</h2>")
    if not candidates:
        parts.append(f'<p class="note">{_e(texts.REPORT_NO_CANDIDATES)}</p>')
        parts.append("</section>")
        return "".join(parts)
    for candidate in candidates:
        chain = candidate["evidence_chain"] if isinstance(candidate["evidence_chain"], list) else []
        summary = texts.EVIDENCE_SUMMARY_FMT.format(count=len(chain))
        parts.append("<details>")
        parts.append(f"<summary>{_e(summary)} · {_e(candidate['path'])}</summary>")
        parts.append("<ul>")
        for item in chain:
            if isinstance(item, dict):
                source = item.get("source", "")
                content = item.get("content", "")
                parts.append(f'<li><span class="src">{_e(source)}</span>{_e(content)}</li>')
            else:
                parts.append(f"<li>{_e(item)}</li>")
        parts.append("</ul></details>")
    parts.append("</section>")
    return "".join(parts)


def _actions(candidates: list) -> str:
    parts = ['<section id="actions" class="bar">']
    parts.append(f"<h2>{_e(texts.REPORT_ZONE_ACTIONS)}</h2>")
    parts.append(f'<p class="note">{_e(texts.REPORT_ACTIONS_NOTE)}</p>')
    parts.append("<table><thead><tr>")
    for column in texts.ACTION_LEGEND_COLUMNS:
        parts.append(f"<th>{_e(column)}</th>")
    parts.append("</tr></thead><tbody>")
    for key in _ACTION_KEYS:
        label = texts.ACTION_LABELS[key]
        description = texts.ACTION_DESCRIPTIONS[key]
        parts.append(f"<tr><td>{_e(key)}</td><td>{_e(label)}</td><td>{_e(description)}</td></tr>")
    parts.append("</tbody></table>")
    if candidates:
        counts: dict[str, int] = {}
        for candidate in candidates:
            key = str(candidate["suggested_action"])
            counts[key] = counts.get(key, 0) + 1
        parts.append("<table><thead><tr>")
        parts.append(f"<th>{_e(texts.DETAIL_COLUMNS['suggested_action'])}</th>")
        parts.append("</tr></thead><tbody>")
        for key in _ACTION_KEYS + tuple(sorted(set(counts) - set(_ACTION_KEYS))):
            if key not in counts:
                continue
            label = f"{key} {texts.ACTION_LABELS.get(key, key)}"
            parts.append(
                "<tr><td>"
                + _e(texts.ACTION_DISTRIBUTION_FMT.format(label=label, count=counts[key]))
                + "</td></tr>"
            )
        parts.append("</tbody></table>")
    parts.append("</section>")
    return "".join(parts)


def _footer() -> str:
    return f"<footer>{_e(texts.REPORT_OFFLINE_NOTICE)}</footer>"


def render_report(report: dict) -> str:
    """report-v1 报告 dict → 离线单文件 HTML 文本（纯函数，无 I/O）。

    输入不合法时抛 ValueError（中文文案，texts.RENDER_ERR_*）；不修改输入。
    incomplete 输入（X-2/C7）：页眉徽标 + 概览区不输出任何汇总数据，
    已采集的部分候选仍保留展示。
    """
    _validate(report)
    incomplete = report.get("incomplete") is True
    candidates = report["candidates"]
    parts = [
        _head(report),
        _header(report, incomplete),
        _overview(report, incomplete),
        _details(candidates),
        _evidence(candidates),
        _actions(candidates),
        _footer(),
        "</body>\n</html>",
    ]
    return "".join(parts)
