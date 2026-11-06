r"""报告候选导出 CSV（默认脱敏）（待办 F3，任务卡 T4-06）。

依据：方案 P7（脱敏覆盖四类——当前用户名/计算机名/用户 SID/其他用户目录名；
CSV 默认脱敏）、第八节"脱敏"（CSV 导出默认脱敏，报告分享前提示"报告含本机
路径"）、E-2（候选字段）、U-2（程序自身仅在 %LOCALAPPDATA%\DiskAudit\ 内写
入——本模块为 CSV 导出唯一写入位）、任务卡实现约束（默认脱敏，显式 --raw
才出原文；仅数据列、无证据链全文以控体量；分享提示在导出完成态展示）。

设计：
- 落盘沿用 reports.py（G3）先例：路径根可注入（``out_dir`` 参数，默认包内
  REPORTS_DIR 常量即 DATA_DIR\\reports\\）；文件名含时间戳
  ``candidates-YYYYmmdd-HHMMSS.csv``，同秒冲突在扩展名前追加 ``-N`` 序号；
  写入前经 ``resolve_csv_path`` 守卫，越界路径构造一律 ValueError 拒绝；
- 脱敏引擎 ``sanitize_text``：纯函数，身份值可注入（默认读环境变量
  USERNAME/COMPUTERNAME——"正则 + 环境变量双锚定"之值锚；正则做段边界
  锚定——位置锚，中段/尾部完整段均命中）。替换顺序（自决，留档）：
  ① SID（最具体，正则形态匹配）→ ② 其他用户目录（\\Users\\<段>，当前用户名
  与 <SID> 占位符除外）→ ③ 当前用户名（段边界锚定）→ ④ 计算机名（段边界
  锚定）。先脱其他用户再锚当前用户，避免当前用户目录被误标"其他用户"；
  SID 最先，避免 Users 下的 SID 段被吞为"其他用户"；
- 用户名/计算机名仅按完整路径段匹配（段 = 两侧为盘符/分隔符/串边界）：
  用户名是更长目录名子串（如 querkecor2-backup）不误伤；短型 well-known SID
  （S-1-5-18 等，全机通用、无个人可识别信息）按正则下限（≥3 组数字后缀）
  不脱敏；身份未知时 Users 下所有目录一律按"其他用户"脱敏（宁过度不遗漏）；
- 编码 utf-8-sig（BOM）+ csv QUOTE_MINIMAL（含逗号/引号路径标准转义），
  Excel 可直接打开（验收④）；导出文件仅数据列，证据链全文不进 CSV。
对外文案集中在 texts.py F3 区块（开发规范 §1）。
"""
from __future__ import annotations

import csv
import os
import re
from datetime import datetime

from disk_audit import REPORTS_DIR
from .engine import texts

# CSV 文件名模式：candidates-YYYYmmdd-HHMMSS.csv；同秒冲突为 ...-N.csv
# （与 reports.py 报告命名同一纪律：时间戳定长 + 字典序确定）。
CSV_NAME_RE = re.compile(r"^candidates-(\d{8}-\d{6})(?:-(\d+))?\.csv$")

_CSV_EXT = ".csv"

# 用户 SID 形态（P7 第三类）：S-1 起头、≥3 组数字后缀，覆盖 S-1-5-21-* 域 SID
# 与内置账户 SID（S-1-5-32-*）；S-1-5-18 等短型 well-known SID 不在覆盖内
# （全机通用常量，不含个人可识别信息——有意下限，留档）。
SID_RE = re.compile(r"\bS-1(?:-\d+){3,}\b", re.IGNORECASE)

# 其他用户目录形态（P7 第四类）：\Users\<段>；替换时排除当前用户名与 <SID>
# 占位符（顺序决策见模块 docstring）。
_OTHER_USER_SEG_RE = re.compile(r"(?i)(\\Users\\)([^\\]+)")

# 段边界锚定（P7 第一/二类位置锚）：目标两侧为串边界或路径分隔符（正反斜杠
# 皆容），保证中段/尾部完整段命中、更长目录名内的子串不误伤。
# "(?<![^\\/])" = 前一字符不存在（串首）或为分隔符。
def _segment_pattern(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<![^\\/])" + re.escape(value) + r"(?=[\\/]|$)", re.IGNORECASE)


def _identity(username: str | None, computer: str | None) -> tuple[str, str]:
    """身份值锚：显式注入优先，缺省回读环境变量（空串 = 视为未知）。"""
    if username is None:
        username = os.environ.get("USERNAME", "")
    if computer is None:
        computer = os.environ.get("COMPUTERNAME", "")
    return username, computer


def sanitize_text(
    text: str,
    *,
    username: str | None = None,
    computer: str | None = None,
) -> str:
    """按 P7 四类脱敏一段文本（纯函数；身份可注入，缺省读环境变量）。

    替换顺序：SID → 其他用户目录 → 当前用户名 → 计算机名（理由见模块
    docstring）。raw 导出不经过本函数。
    """
    username, computer = _identity(username, computer)
    placeholders = texts.SANITIZE_PLACEHOLDERS
    result = SID_RE.sub(placeholders["sid"], text)

    def _replace_other(match: re.Match[str]) -> str:
        segment = match.group(2)
        if (username and segment.lower() == username.lower()) or segment == placeholders["sid"]:
            return match.group(0)
        return match.group(1) + placeholders["other_user"]

    result = _OTHER_USER_SEG_RE.sub(_replace_other, result)
    if username:
        result = _segment_pattern(username).sub(placeholders["user"], result)
    if computer:
        result = _segment_pattern(computer).sub(placeholders["computer"], result)
    return result


def csv_filename(now: datetime | None = None) -> str:
    """生成含时间戳的 CSV 文件名（时间来源可注入，保证测试确定性）。"""
    stamp = (now if now is not None else datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"candidates-{stamp}{_CSV_EXT}"


def resolve_csv_path(directory: str, filename: str) -> str:
    """CSV 写路径守卫（复用 reports.py G3 模式）：文件名必须为本模块命名模式，
    且解析后必须落在 directory 之下。

    越界路径构造（``..\\`` 上跳、含子目录、绝对路径注入、双扩展名等）一律
    抛 ValueError（中文文案），调用前不产生任何文件系统写入（U-2）。
    """
    if CSV_NAME_RE.fullmatch(filename) is None:
        raise ValueError(texts.F3_TEXTS["csv_err_bad_filename"].format(filename=filename))
    root = os.path.abspath(directory)
    target = os.path.abspath(os.path.join(root, filename))
    if os.path.dirname(target) != root:
        raise ValueError(texts.F3_TEXTS["csv_err_outside_dir"].format(target=target))
    return target


def _next_available(directory: str, filename: str) -> str:
    """同秒冲突时在扩展名前追加 -N 序号（N 从 1 起），不覆盖既有文件。"""
    if not os.path.exists(os.path.join(directory, filename)):
        return filename
    stem = filename[: -len(_CSV_EXT)]
    sequence = 1
    while os.path.exists(os.path.join(directory, f"{stem}-{sequence}{_CSV_EXT}")):
        sequence += 1
    return f"{stem}-{sequence}{_CSV_EXT}"


# CSV 仅数据列（任务卡"无证据链全文"）：六字段与 report-v1 候选七字段对齐，
# 唯 evidence_chain 不导出。
_REQUIRED_CANDIDATE_FIELDS = (
    "path",
    "logical_bytes",
    "allocated_bytes",
    "confidence",
    "verdict_source",
    "suggested_action",
)


def _as_int(value: object) -> int:
    """数值字段收整；非法输入抛 ValueError（中文文案），不让 TypeError 逸出。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(texts.F3_TEXTS["csv_err_bad_number"]) from exc


def _validate(report: object) -> list:
    """输入校验：顶层含 candidates 数组，候选含六个数据字段；不符抛
    ValueError（中文文案，texts.F3_TEXTS）。证据链不消费、不作要求。"""
    if not isinstance(report, dict):
        raise ValueError(texts.F3_TEXTS["csv_err_not_object"])
    if "candidates" not in report:
        raise ValueError(
            texts.F3_TEXTS["csv_err_missing_fields"].format(fields="candidates")
        )
    candidates = report["candidates"]
    if not isinstance(candidates, list):
        raise ValueError(texts.F3_TEXTS["csv_err_candidates_not_list"])
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(
                texts.F3_TEXTS["csv_err_candidate_not_object"].format(index=index)
            )
        missing = [key for key in _REQUIRED_CANDIDATE_FIELDS if key not in candidate]
        if missing:
            # 字段名以中文列名披露（开发规范 §1：异常提示中文），未知键回退原名
            shown = "、".join(texts.CSV_HEADERS.get(key, key) for key in missing)
            raise ValueError(
                texts.F3_TEXTS["csv_err_candidate_missing"].format(index=index, fields=shown)
            )
        _as_int(candidate["logical_bytes"])
        _as_int(candidate["allocated_bytes"])
    return candidates


def export_csv(
    report: dict,
    *,
    out_dir: str | None = None,
    raw: bool = False,
    now: datetime | None = None,
) -> str:
    """报告 dict 候选 → CSV 落盘，返回绝对路径。

    默认脱敏（raw=False）：全部文本列经 ``sanitize_text``（当前仅路径可能
    携带四类敏感项，统一过脱敏器以防未来列引入遗漏）；raw=True 显式出原文
    （任务卡：显式参数才出原文）。列集仅数据六列，无证据链全文（控体量）。
    目录不存在则创建；写入位经 ``resolve_csv_path`` 守卫（U-2：仅
    DATA_DIR\\reports\\ 或注入替身之下）。编码 utf-8-sig（Excel 直开）。
    """
    candidates = _validate(report)
    directory = out_dir if out_dir is not None else REPORTS_DIR
    headers = texts.CSV_HEADERS
    rows: list[list[str]] = [[headers[key] for key in _REQUIRED_CANDIDATE_FIELDS]]
    for candidate in candidates:
        path_cell = str(candidate["path"])
        confidence_cell = str(candidate["confidence"])
        source_cell = str(candidate["verdict_source"])
        action_cell = str(candidate["suggested_action"])
        if not raw:
            path_cell = sanitize_text(path_cell)
            confidence_cell = sanitize_text(confidence_cell)
            source_cell = sanitize_text(source_cell)
            action_cell = sanitize_text(action_cell)
        rows.append(
            [
                path_cell,
                str(_as_int(candidate["logical_bytes"])),
                str(_as_int(candidate["allocated_bytes"])),
                confidence_cell,
                source_cell,
                action_cell,
            ]
        )
    os.makedirs(directory, exist_ok=True)
    filename = _next_available(directory, csv_filename(now))
    target = resolve_csv_path(directory, filename)
    with open(target, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        writer.writerows(rows)
    return target
