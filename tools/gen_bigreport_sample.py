# -*- coding: utf-8 -*-
"""F5（任务卡 T3-03）测量样张生成：report-v1 JSON → render_report → 离线 HTML。

不入产品运行时、不入 CI、pytest 不依赖。数据分布复用 POC-4
（tests/_bigreport_sample.py，random.seed(42)），与 W0 基线同口径。
输出：HTML 文件路径 + 字节硬数字 + DOM 元素统计（JSON，stdout）。

用法：python tools/gen_bigreport_sample.py [--n 5000] [--out <path>]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from disk_audit.engine.render import render_report  # noqa: E402
from tests._bigreport_sample import build_big_report  # noqa: E402


class _DomCounter(HTMLParser):
    """统计元素总数与明细表行数的极简计数器（标准库）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements = 0
        self.rows = 0
        self.details_tags = 0
        self.tags: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements += 1
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if tag == "tr":
            self.rows += 1
        elif tag == "details":
            self.details_tags += 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="F5 性能样张生成（POC-4 同分布）")
    parser.add_argument("--n", type=int, default=5000)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    report = build_big_report(args.n)
    html_text = render_report(report)
    data = html_text.encode("utf-8")

    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "t303_bigreport.html"
    out.write_bytes(data)

    counter = _DomCounter()
    counter.feed(html_text)
    counter.close()

    script_start = html_text.find("<script>")
    script_end = html_text.find("</script>", script_start)
    js_bytes = script_end - script_start if script_start >= 0 else 0

    print(
        json.dumps(
            {
                "candidates": args.n,
                "file_path": str(out),
                "file_bytes": len(data),
                "dom_elements": counter.elements,
                "tr_rows": counter.rows,
                "details_tags": counter.details_tags,
                "inline_js_bytes": js_bytes,
                "css_bytes": len(
                    html_text[html_text.find("<style>") + 7 : html_text.find("</style>")].encode(
                        "utf-8"
                    )
                ),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
