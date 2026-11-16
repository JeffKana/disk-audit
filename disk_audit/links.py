r"""体检记录与报告的显式关联元数据基础（任务卡 T5-04-A / T504A-v1，DR-016）。

依据：DR-016（2026-11-16，七字段严格 schema `checkup-link-v1`）、F1 §1 本地数据目录与
§3 U-2（程序自身仅写 `%LOCALAPPDATA%\DiskAudit\`）、F1 §6「报告 + 记录最近 12 次 /
50,000,000 B」、DR-012 §4（拒绝按同秒/近似时间戳配对）、`records.py` 的根/祖先重解析点
守卫与原子发布先例、《开发规范》§1/§2/§4。

边界（本卡明确不做）：
- 不接线 launcher/UI/提权/清理，不实现联合额度或 12 次淘汰（后续卡），不删除任何既有
  报告/记录/link/外来文件；不改 record-v1 / report-v1 字段，不迁移旧数据，不按时间猜配。
- 元数据只写 `RECORDS_DIR/links`（F1 一级目录仍为 reports/records/tmp），文件名
  `link-<32 位小写 hex>.json`；正文与文件名 ID 必须一致。
- 纯 `build_link` / `validate_link` 不生成 ID、不读当前时间、不触碰文件系统；
  `save_link` 先校验后触碰根/磁盘，只清本次自建临时文件，禁止 os.replace 覆盖最终文件。
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime

from disk_audit import RECORDS_DIR
from . import records
from .engine import texts

# 冻结契约：DR-016 七字段严格 schema。
LINK_SCHEMA_VERSION = "checkup-link-v1"
LINK_ID_RE = re.compile(r"^[0-9a-f]{32}$")
LINK_NAME_RE = re.compile(r"^link-([0-9a-f]{32})\.json$")
REPORT_NAME_RE = re.compile(r"^(admin-)?report-[0-9]{8}-[0-9]{6}(?:-[0-9]+)?\.html$")
RECORD_ID_RE = re.compile(r"^(admin-)?record-[0-9]{8}-[0-9]{6}(?:-[0-9]+)?$")
RECORD_ERROR_MACHINE_CODE = "record-save-failed"

_KEYS: tuple[str, ...] = (
    "schema_version",
    "checkup_id",
    "created_at",
    "mode",
    "report_filename",
    "record_id",
    "record_error",
)
_ALLOWED: frozenset[str] = frozenset(_KEYS)
_MODES: tuple[str, ...] = ("normal", "admin")
_ADMIN_PREFIX = "admin-"
_JSON_EXT = ".json"
_TMP_PREFIX = ".tmp-link-"
_LINKS_DIR_NAME = "links"

# ISO 8601：必须含日期 + 时间 + 明确时区（Z 或 ±HH:MM）；不接受仅日期的写法。
_ISO_ZONED_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class LinkError(ValueError):
    """关联元数据公共异常基类（中文文案）；所有拒绝/读取失败可消费。"""


class LinkValidationError(LinkError):
    """字段/形状/类型/命名/组合规则非法：拒绝构建、保存或读取。"""


class LinkVersionError(LinkError):
    """schema_version 非字符串或未知版本：与形状错误可区分。"""


class LinkIOError(LinkError):
    """根/祖先/叶守卫、读写、序列化或原子发布失败。"""


@dataclass(frozen=True)
class LinkEntry:
    """列举项：合法项 data 非空且 problem 为 None；坏项 data=None 并逐项披露 problem。"""

    checkup_id: str
    filename: str
    data: dict | None
    problem: str | None


def _text(key: str, **params: object) -> str:
    return texts.LINKS_TEXTS[key].format(**params)


def _show(value: object) -> str:
    """错误消息里的动态值：字符串原样，其余只给类型名，避免回显任意对象内容。"""
    return value if isinstance(value, str) else type(value).__name__


def _field_error(field: str, detail_key: str, **params: object) -> LinkValidationError:
    return LinkValidationError(
        _text("links_err_bad_field", detail=_text(detail_key, field=field, **params))
    )


def new_checkup_id() -> str:
    """独立熵入口：uuid4().hex（32 位小写 hex），不依赖秒/mtime/序列。"""
    return uuid.uuid4().hex


def _is_zoned_iso8601(value: str) -> bool:
    if _ISO_ZONED_RE.fullmatch(value) is None:
        return False
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_checkup_id(value: object) -> None:
    if not isinstance(value, str) or LINK_ID_RE.fullmatch(value) is None:
        raise _field_error("checkup_id", "links_detail_bad_id")


def _validate_created_at(value: object) -> None:
    if not isinstance(value, str) or not _is_zoned_iso8601(value):
        raise _field_error("created_at", "links_detail_bad_time")


def _validate_mode(value: object) -> None:
    if not isinstance(value, str) or value not in _MODES:
        raise _field_error("mode", "links_detail_bad_mode")


def _validate_report_filename(value: object, mode: str) -> None:
    if not isinstance(value, str) or REPORT_NAME_RE.fullmatch(value) is None:
        raise _field_error("report_filename", "links_detail_bad_report")
    admin_prefix = REPORT_NAME_RE.fullmatch(value).group(1) == _ADMIN_PREFIX
    if admin_prefix != (mode == "admin"):
        raise _field_error("report_filename", "links_detail_mode_mismatch")


def _validate_record_id(value: object, mode: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or RECORD_ID_RE.fullmatch(value) is None:
        raise _field_error("record_id", "links_detail_bad_record")
    admin_prefix = RECORD_ID_RE.fullmatch(value).group(1) == _ADMIN_PREFIX
    if admin_prefix != (mode == "admin"):
        raise _field_error("record_id", "links_detail_mode_mismatch")


def _validate_record_error(value: object) -> None:
    if value is not None and value != RECORD_ERROR_MACHINE_CODE:
        raise _field_error("record_error", "links_detail_bad_record_error")


def validate_link(link: object) -> dict:
    """校验一条关联元数据并返回新的顶层字典（不改动入参、不触碰磁盘/时钟）。

    顺序：非对象 → 缺字段 → 版本 → 未定义字段 → 逐字段语义 → record_error XOR。
    版本非字符串或未知抛 LinkVersionError；其余形状/命名/组合问题抛
    LinkValidationError（枚举/键坏容器不泄漏 TypeError）。
    """
    if not isinstance(link, dict):
        raise LinkValidationError(_text("links_err_not_object"))
    missing = [key for key in _KEYS if key not in link]
    if missing:
        raise LinkValidationError(_text("links_err_missing_fields", fields="、".join(missing)))
    version = link["schema_version"]
    if not isinstance(version, str) or version != LINK_SCHEMA_VERSION:
        raise LinkVersionError(_text("links_err_bad_version", version=_show(version)))
    extra = [key for key in link if key not in _ALLOWED]
    if extra:
        raise LinkValidationError(
            _text("links_err_extra_fields", fields="、".join(_show(key) for key in extra))
        )
    _validate_checkup_id(link["checkup_id"])
    _validate_created_at(link["created_at"])
    _validate_mode(link["mode"])
    mode = link["mode"]
    _validate_report_filename(link["report_filename"], mode)
    _validate_record_id(link["record_id"], mode)
    _validate_record_error(link["record_error"])
    if (link["record_id"] is None) == (link["record_error"] is None):
        raise LinkValidationError(_text("links_detail_xor"))
    return {key: link[key] for key in _KEYS}


def build_link(
    *,
    checkup_id: str,
    created_at: str,
    mode: str,
    report_filename: str,
    record_id: str | None,
    record_error: str | None,
) -> dict:
    """按七字段构造并校验一条关联元数据（纯内存；不生成 ID、不读当前时间）。"""
    return validate_link(
        {
            "schema_version": LINK_SCHEMA_VERSION,
            "checkup_id": checkup_id,
            "created_at": created_at,
            "mode": mode,
            "report_filename": report_filename,
            "record_id": record_id,
            "record_error": record_error,
        }
    )


# ---------------------------------------------------------------------------
# 路径守卫（复用 records 的根/祖先重解析点核验，异常映射为 LinkIOError）
# ---------------------------------------------------------------------------


def _default_links_dir() -> str:
    """默认根：包内 RECORDS_DIR/links（F1 一级目录仍是 reports/records/tmp）。"""
    return os.path.join(RECORDS_DIR, _LINKS_DIR_NAME)


def _safe_root(directory: str) -> str:
    try:
        return records._require_safe_root(directory)
    except records.RecordError as exc:
        raise LinkIOError(_text("links_err_root", detail=str(exc))) from exc


def _link_filename(checkup_id: str) -> str:
    return "link-%s%s" % (checkup_id, _JSON_EXT)


def _link_path(directory: str, checkup_id: object) -> str:
    if not isinstance(checkup_id, str) or LINK_ID_RE.fullmatch(checkup_id) is None:
        raise LinkValidationError(_text("links_err_bad_id", checkup_id=_show(checkup_id)))
    root = os.path.abspath(directory)
    target = os.path.abspath(os.path.join(root, _link_filename(checkup_id)))
    if os.path.dirname(target) != root:
        raise LinkValidationError(_text("links_err_outside_dir", target=target))
    return target


def _is_reparse_point(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attrs & flag)


def _require_regular_file(target: str) -> None:
    try:
        st = os.lstat(target)
    except OSError as exc:
        raise LinkIOError(_text("links_err_read", exc=exc)) from exc
    if _is_reparse_point(st) or not stat.S_ISREG(st.st_mode):
        raise LinkIOError(_text("links_err_not_regular", filename=os.path.basename(target)))


def _require_created_dir(directory: str) -> None:
    """创建后复核：尾部必须是我们刚建/已存在的普通目录，不是重解析点。"""
    try:
        st = os.lstat(directory)
    except OSError as exc:
        raise LinkIOError(_text("links_err_root", detail=exc)) from exc
    if _is_reparse_point(st) or not stat.S_ISDIR(st.st_mode):
        raise LinkIOError(_text("links_err_not_regular", filename=directory))


# ---------------------------------------------------------------------------
# 写盘：本根临时文件 + 完整写/flush/fsync + Windows 不覆盖原子发布
# ---------------------------------------------------------------------------


def _serialize(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _stage(directory: str, payload: str) -> str:
    try:
        fd, temp_path = tempfile.mkstemp(prefix=_TMP_PREFIX, suffix=_JSON_EXT, dir=directory)
    except OSError as exc:
        raise LinkIOError(_text("links_err_write", exc=exc)) from exc
    os.close(fd)
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        _safe_unlink(temp_path)
        raise LinkIOError(_text("links_err_write", exc=exc)) from exc
    return temp_path


def _publish(temp_path: str, target: str) -> None:
    """os.rename 原子改名；Windows 下目标已存在即失败，绝不覆盖、不重试。"""
    try:
        os.rename(temp_path, target)
    except FileExistsError as exc:
        raise LinkIOError(_text("links_err_conflict", target=target)) from exc
    except OSError as exc:
        raise LinkIOError(_text("links_err_write", exc=exc)) from exc


def save_link(link: object, *, links_dir: str | None = None) -> str:
    """校验并落盘一条关联元数据，返回 checkup_id（文件名主干）。

    校验先于任何目录创建/写盘；根与现有祖先逐段 lstat 防重解析；尾部缺失可创建。
    最终文件已存在即失败且旧字节不动；失败只清本次自建的 .tmp-link- 临时文件。
    """
    validated = validate_link(link)
    directory = _safe_root(links_dir if links_dir is not None else _default_links_dir())
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        raise LinkIOError(_text("links_err_write", exc=exc)) from exc
    _require_created_dir(directory)
    checkup_id = validated["checkup_id"]
    target = _link_path(directory, checkup_id)
    if os.path.lexists(target):
        raise LinkIOError(_text("links_err_conflict", target=target))
    temp_path = _stage(directory, _serialize(validated))
    try:
        _publish(temp_path, target)
        temp_path = ""  # 已被 rename 消费
        return checkup_id
    finally:
        if temp_path:
            _safe_unlink(temp_path)


# ---------------------------------------------------------------------------
# 读取 / 列举
# ---------------------------------------------------------------------------


def _read_json(target: str) -> object:
    try:
        with open(target, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except UnicodeDecodeError as exc:
        raise LinkIOError(_text("links_err_encode", exc=exc)) from exc
    except OSError as exc:
        raise LinkIOError(_text("links_err_read", exc=exc)) from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LinkIOError(_text("links_err_json", exc=exc)) from exc


def _load_link(target: str, checkup_id: str) -> dict:
    _require_regular_file(target)
    data = validate_link(_read_json(target))
    if data["checkup_id"] != checkup_id:
        raise LinkValidationError(
            _text("links_err_id_mismatch", filename=os.path.basename(target))
        )
    return data


def read_link(checkup_id: str, *, links_dir: str | None = None) -> dict:
    """按 ID 读取并校验一条关联元数据；ID 非法在触碰文件系统前拒绝。"""
    if not isinstance(checkup_id, str) or LINK_ID_RE.fullmatch(checkup_id) is None:
        raise LinkValidationError(_text("links_err_bad_id", checkup_id=_show(checkup_id)))
    directory = _safe_root(links_dir if links_dir is not None else _default_links_dir())
    target = _link_path(directory, checkup_id)
    return _load_link(target, checkup_id)


def list_links(*, links_dir: str | None = None) -> list[LinkEntry]:
    """列举严格命名的关联文件（不递归），按文件名字面升序；坏项逐项披露不阻断。

    根不存在返回空列表；根/祖先不安全整体拒绝；非匹配外来项不读取、不修改、不列出。
    """
    directory = _safe_root(links_dir if links_dir is not None else _default_links_dir())
    if not os.path.isdir(directory):
        return []
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        raise LinkIOError(_text("links_err_read", exc=exc)) from exc
    entries: list[LinkEntry] = []
    for name in names:
        match = LINK_NAME_RE.fullmatch(name)
        if match is None:
            continue
        checkup_id = match.group(1)
        try:
            target = _link_path(directory, checkup_id)
            data = _load_link(target, checkup_id)
        except LinkError as exc:
            entries.append(
                LinkEntry(
                    checkup_id=checkup_id,
                    filename=name,
                    data=None,
                    problem=str(exc),
                )
            )
            continue
        entries.append(LinkEntry(checkup_id=checkup_id, filename=name, data=data, problem=None))
    return entries