r"""体检记录 JSON 存储基础（I1a，任务卡 T5-01 / T501-v1；第1次退回整改 T501-RETURN-1）。

依据：F1 定稿一节本地数据目录、三节 U-2/X-2/S-3、六节数据预算、七节 M3 与 Q7；
`docs/schemas/report-v1.schema.json`（含 1.0→1.1 兼容声明）；`disk_audit/__init__.py`
的 RECORDS_DIR；`disk_audit/reports.py` 的命名/路径守卫先例；《开发规范》§1/§2/§7。

边界（本卡明确不做，保留为后续卡）：
- 不接线 launcher/UI、不启动真实扫描、不实现两次比较（T5-03/05）、不做联合 50MB
  额度与 12 次淘汰（T5-04）、不新增外部系统能力。
- 存储内容严格复用 report-v1 的字段语义，**不引入新记录 envelope**：落盘 JSON 就是
  一份报告形状的对象（schema_version/generated_at/scan_root/totals/candidates +
  已定义的 admin_mode/incomplete）。不收原始采集 bundle、全量扫描文件清单或 HTML 全文；
  任何未定义字段一律明确拒绝，不悄悄持久化额外隐私数据。
- 版本边界：已知 1.0/1.1 可读；1.0 缺 admin_mode 按普通模式消费；未知/不兼容版本
  以可区分的 ``RecordVersionError`` 拒绝，中文文案含"旧记录不可比"供后续 UI 卡消费；
  不改 REPORT_SCHEMA_VERSION、不把版本默默归一化成另一版本。
- 默认只写 RECORDS_DIR（%LOCALAPPDATA%\DiskAudit\records）；测试根可注入。文件名由
  本模块生成并严格校验（普通 ``record-<时间戳>[-序号].json``、管理员
  ``admin-record-<时间戳>[-序号].json``），同秒冲突追加序号不覆盖；ID（文件名主干）
  与路径分离，不接收任意路径注入。
- 临时文件只落同一授权目录，写完后经原子改名完整发布，失败不残留可见的半条正式记录；
  列举/读取只操作授权目录下本模块严格命名的普通文件，不跟随目录/重解析点，不遍历
  被扫描目标；单点损坏/不兼容可披露且不阻断其他合法记录列举。
- T501-RETURN-1 整改：根与祖先重解析点（root/ancestor junction）同样不跟随——三个
  公共操作在任何 makedirs/listdir/读取/临时写入前逐段核验从路径根到记录目录的现有
  组成部分；四枚举位置的 list/dict 坏容器文档化拒绝而非未包装 TypeError；固定中文
  校验细节集中 texts.py 本卡资源区、动态值走模板参数（OBS-1）。
- 运行时零第三方依赖（仅标准库 + 包内模块），无 UI import/网络/提权/子进程/自动重扫。
  对外中文文案集中在 texts.py 文末本卡独立资源区。
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime

from disk_audit import RECORDS_DIR
from .engine import texts

# 版本契约（Q7 / report-v1.schema.json）：1.0 为定稿基线，1.1 = 1.0 + 可选 admin_mode。
# 1.0 旧记录无 admin_mode 仍合法（旧记录可比）；其余主/次版本一律视为不可比。
KNOWN_VERSIONS: tuple[str, ...] = ("1.0", "1.1")

# 文件名/ID 模式：时间戳定长（字典序即时间序）；管理员以 admin- 前缀区分；
# 同秒冲突在扩展名前追加 -N 序号。ID 为主干（不含 .json），与路径分离。
RECORD_ID_RE = re.compile(r"^(?:admin-)?record-\d{8}-\d{6}(?:-\d+)?$")
RECORD_NAME_RE = re.compile(r"^(?:admin-)?record-\d{8}-\d{6}(?:-\d+)?\.json$")
RECORD_NORMAL_PREFIX = "record"
RECORD_ADMIN_PREFIX = "admin-record"
_JSON_EXT = ".json"
_TMP_PREFIX = ".tmp-record-"

_REQUIRED_TOP: tuple[str, ...] = (
    "schema_version",
    "generated_at",
    "scan_root",
    "totals",
    "candidates",
)
_ALLOWED_TOP: frozenset[str] = frozenset(_REQUIRED_TOP + ("incomplete", "admin_mode"))
_TOTALS_KEYS: tuple[str, ...] = (
    "allocated_bytes",
    "logical_bytes",
    "regenerable_subtotal",
    "regenerable_confirm_subtotal",
    "skipped_entries",
)
_CANDIDATE_KEYS: tuple[str, ...] = (
    "path",
    "logical_bytes",
    "allocated_bytes",
    "confidence",
    "verdict_source",
    "evidence_chain",
    "suggested_action",
)
# 枚举与 report-v1.schema.json 定稿一致；置信度/证据来源复用 texts.py 既有单一措辞源。
_VERDICT_SOURCES: frozenset[str] = frozenset(
    ("硬保护", "知识库", "注册表", "进程服务", "Appx", "启发式")
)
_ACTIONS: frozenset[str] = frozenset(("A1", "A2", "A3", "A4", "A5"))
_CONFIDENCES: frozenset[str] = frozenset(texts.CONFIDENCE_WORDING)
_EVIDENCE_SOURCES: frozenset[str] = frozenset(texts.EVIDENCE_SOURCE_ENUM)


# ---------------------------------------------------------------------------
# 异常（接口形状/异常类型属 D-执行自决，文档化于 docs/schemas/record-v1-字段对照表.md）
# ---------------------------------------------------------------------------


class RecordError(ValueError):
    """记录存储基础异常（中文文案）；所有本模块拒绝/读取失败的公共父类。"""


class RecordValidationError(RecordError):
    """输入形状/字段/候选非法、多余字段、incomplete 等校验失败：拒绝持久化。"""


class RecordVersionError(RecordError):
    """未知/不兼容 schema_version：与形状错误可区分，文案含"旧记录不可比"。"""


class RecordWriteError(RecordError):
    """写盘/发布失败（含目标冲突拒绝覆盖）。"""


@dataclass(frozen=True)
class RecordEntry:
    """列举结果项：合法记录 comparable=True 并带 record；损坏/不兼容/非普通文件
    comparable=False 并带 problem（可披露），不得静默说可比。"""

    record_id: str
    filename: str
    comparable: bool
    record: dict | None
    problem: str | None
    admin_mode: bool
    schema_version: str | None


# ---------------------------------------------------------------------------
# 输入校验（纯函数，无 I/O）
# ---------------------------------------------------------------------------


def _is_nonneg_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _detail(template_key: str, **params: object) -> str:
    """固定中文校验细节一律取自 texts 本卡资源区，动态值走模板参数（OBS-1）。"""
    return texts.RECORDS_TEXTS[template_key].format(**params)


def _validate_totals(totals: object) -> None:
    def bad(key: str, **params: object) -> RecordValidationError:
        return RecordValidationError(
            texts.RECORDS_TEXTS["records_err_bad_totals"].format(detail=_detail(key, **params))
        )

    if not isinstance(totals, dict):
        raise bad("records_detail_not_object")
    missing = [key for key in _TOTALS_KEYS if key not in totals]
    if missing:
        raise bad("records_detail_missing_fields", fields="、".join(missing))
    extra = sorted(set(totals) - set(_TOTALS_KEYS))
    if extra:
        raise bad("records_detail_extra_fields", fields="、".join(extra))
    for key in _TOTALS_KEYS:
        if not _is_nonneg_int(totals[key]):
            raise bad("records_detail_nonneg_int", field=key)


def _validate_candidates(candidates: object) -> None:
    def bad(key: str, **params: object) -> RecordValidationError:
        return RecordValidationError(
            texts.RECORDS_TEXTS["records_err_bad_candidates"].format(detail=_detail(key, **params))
        )

    if not isinstance(candidates, list):
        raise bad("records_detail_not_array")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise bad("records_detail_candidate_not_object", index=index)
        missing = [key for key in _CANDIDATE_KEYS if key not in candidate]
        if missing:
            raise bad("records_detail_candidate_missing", index=index, fields="、".join(missing))
        extra = sorted(set(candidate) - set(_CANDIDATE_KEYS))
        if extra:
            raise bad("records_detail_candidate_extra", index=index, fields="、".join(extra))
        if not isinstance(candidate["path"], str) or not candidate["path"]:
            raise bad("records_detail_candidate_nonempty_str", index=index, field="path")
        for key in ("logical_bytes", "allocated_bytes"):
            if not _is_nonneg_int(candidate[key]):
                raise bad("records_detail_candidate_nonneg_int", index=index, field=key)
        # DEF-1：枚举值先做类型守卫，再查 frozenset；坏容器（list/dict）或非字符串
        # 一律文档化 RecordValidationError，绝不抛出未包装的 TypeError。
        for key, allowed in (
            ("confidence", _CONFIDENCES),
            ("verdict_source", _VERDICT_SOURCES),
            ("suggested_action", _ACTIONS),
        ):
            value = candidate[key]
            if not isinstance(value, str) or value not in allowed:
                raise bad("records_detail_enum_invalid", index=index, field=key)
        chain = candidate["evidence_chain"]
        if not isinstance(chain, list) or len(chain) == 0:
            raise bad(
                "records_detail_chain_not_array",
                index=index,
                field="evidence_chain",
                minimum=1,
            )
        for position, item in enumerate(chain):
            if not isinstance(item, dict) or set(item) != {"source", "content"}:
                raise bad(
                    "records_detail_chain_item_shape",
                    index=index,
                    field="evidence_chain",
                    position=position,
                    keys="source/content",
                )
            source = item["source"]
            if not isinstance(source, str) or source not in _EVIDENCE_SOURCES:
                raise bad(
                    "records_detail_chain_source_invalid",
                    index=index,
                    field="evidence_chain",
                    position=position,
                )
            if not isinstance(item["content"], str):
                raise bad(
                    "records_detail_chain_content_not_str",
                    index=index,
                    field="evidence_chain",
                    position=position,
                    sub="content",
                )


def validate_record(report: object) -> dict:
    """校验一份报告形状对象，返回顶层浅拷贝（不改动入参）；非法则抛中文异常。

    复用 report-v1 字段语义：只接受定稿顶层字段集（含可选 incomplete/admin_mode），
    多余字段一律拒绝；totals 五字段、候选七字段与证据链逐项校验。版本不在
    KNOWN_VERSIONS 时抛 RecordVersionError（含"旧记录不可比"），不归一化。
    incomplete=True 抛 RecordValidationError（不得存成完整体检记录）。
    """
    if not isinstance(report, dict):
        raise RecordValidationError(texts.RECORDS_TEXTS["records_err_not_object"])
    missing = [key for key in _REQUIRED_TOP if key not in report]
    if missing:
        raise RecordValidationError(
            texts.RECORDS_TEXTS["records_err_missing_fields"].format(fields="、".join(missing))
        )
    version = report["schema_version"]
    if not isinstance(version, str) or version not in KNOWN_VERSIONS:
        raise RecordVersionError(
            texts.RECORDS_TEXTS["records_err_bad_version"].format(version=version)
        )
    extra = sorted(set(report) - _ALLOWED_TOP)
    if extra:
        raise RecordValidationError(
            texts.RECORDS_TEXTS["records_err_extra_fields"].format(fields="、".join(extra))
        )
    for key in ("generated_at", "scan_root"):
        if not isinstance(report[key], str) or not report[key]:
            raise RecordValidationError(
                texts.RECORDS_TEXTS["records_err_bad_field"].format(
                    detail=_detail("records_detail_nonempty_str", field=key)
                )
            )
    if "admin_mode" in report:
        if version == "1.0":
            raise RecordValidationError(texts.RECORDS_TEXTS["records_err_bad_admin_mode"])
        if not isinstance(report["admin_mode"], bool):
            raise RecordValidationError(
                texts.RECORDS_TEXTS["records_err_bad_field"].format(
                    detail=_detail("records_detail_bool", field="admin_mode")
                )
            )
    if "incomplete" in report:
        incomplete = report["incomplete"]
        if not isinstance(incomplete, bool):
            raise RecordValidationError(texts.RECORDS_TEXTS["records_err_incomplete_type"])
        if incomplete is True:
            raise RecordValidationError(texts.RECORDS_TEXTS["records_err_incomplete"])
    _validate_totals(report["totals"])
    _validate_candidates(report["candidates"])
    return dict(report)


# ---------------------------------------------------------------------------
# 路径守卫 / 命名
# ---------------------------------------------------------------------------


def resolve_record_path(directory: str, record_id: str) -> str:
    """记录路径守卫：ID 必须为本模块命名模式，解析后必须落在 directory 之下。

    只接受逻辑 ID（文件名主干），不接受任意路径/文件名注入；绝对路径、``..`` 上跳、
    子目录、双扩展名等一律 RecordValidationError（中文文案），调用前不产生任何写入。
    """
    if RECORD_ID_RE.fullmatch(record_id) is None:
        raise RecordValidationError(
            texts.RECORDS_TEXTS["records_err_bad_id"].format(record_id=record_id)
        )
    root = os.path.abspath(directory)
    target = os.path.abspath(os.path.join(root, record_id + _JSON_EXT))
    if os.path.dirname(target) != root:
        raise RecordValidationError(
            texts.RECORDS_TEXTS["records_err_outside_dir"].format(target=target)
        )
    return target


def _reserve_target(directory: str, stem: str) -> tuple[str, str]:
    """选定同秒不冲突的 ID 与其绝对路径（只查 lexists，不覆盖既有项）。"""
    root = os.path.abspath(directory)
    sequence = 0
    while True:
        record_id = stem if sequence == 0 else f"{stem}-{sequence}"
        target = resolve_record_path(root, record_id)
        if not os.path.lexists(target):
            return record_id, target
        sequence += 1


def _path_chain(root: str) -> list[str]:
    """从文件系统根到 root 的逐级路径（含 root 自身），由浅到深。root 应为 abspath。"""
    chain: list[str] = []
    current = root
    while True:
        chain.append(current)
        parent = os.path.dirname(current)
        if parent == current:  # 已到盘符根 / 文件系
            break
        current = parent
    chain.reverse()
    return chain


def _is_reparse_point(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attrs & flag)


def _require_safe_root(directory: str) -> str:
    """DEF-2：在 makedirs/listdir/文件读取/临时写入前核验从文件系统根到记录目录的
    **现有组成部分**，任一现有组成部分是重解析点（junction/symlink/挂载点）或非目录
    即以中文 RecordError 停止并披露，绝不继续访问其子路径/target。

    由浅到深逐段 os.lstat（不跟随）；遇到第一个不存在的组成部分即停止（其下不可能
    已存在，正常创建合法）。保持合法普通目录、正常新建目录与已存在叶文件守卫语义。
    返回规范化后的绝对路径，供调用方后续所有文件系统动作复用。
    """
    root = os.path.abspath(directory)
    for component in _path_chain(root):
        try:
            st = os.lstat(component)
        except (FileNotFoundError, NotADirectoryError):
            break  # 首个缺失组成部分：其下尚不存在，允许正常创建
        except OSError as exc:
            raise RecordError(
                texts.RECORDS_TEXTS["records_err_root_stat"].format(exc=exc)
            ) from exc
        if _is_reparse_point(st):
            raise RecordError(
                texts.RECORDS_TEXTS["records_err_root_reparse"].format(target=component)
            )
        if not stat.S_ISDIR(st.st_mode):
            raise RecordError(
                texts.RECORDS_TEXTS["records_err_root_not_dir"].format(target=component)
            )
    return root


# ---------------------------------------------------------------------------
# 写盘（原子发布 / 失败清理）—— 可注入的私有 seam 供测试替身
# ---------------------------------------------------------------------------


def _serialize(report: dict) -> str:
    """report-v1 形状对象 → UTF-8 JSON 文本（中文不转义）。"""
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _stage(directory: str, payload: str) -> str:
    """临时文件只落同一授权目录；完整写入并 fsync 后返回临时路径，失败自清理。"""
    fd, temp_path = tempfile.mkstemp(prefix=_TMP_PREFIX, suffix=_JSON_EXT, dir=directory)
    os.close(fd)
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        _safe_unlink(temp_path)
        raise
    return temp_path


def _publish(temp_path: str, target: str) -> None:
    """完整发布：os.rename 原子改名；Windows 下目标已存在即失败，绝不覆盖既有记录。"""
    if os.path.lexists(target):
        raise RecordWriteError(
            texts.RECORDS_TEXTS["records_err_conflict"].format(target=target)
        )
    os.rename(temp_path, target)


def save_record(
    report: object,
    *,
    records_dir: str | None = None,
    now: datetime | None = None,
) -> str:
    """校验并落盘一份完整体检记录，返回逻辑 ID（文件名主干，不含路径/扩展名）。

    默认写入位 = 包内 RECORDS_DIR；测试根可注入。文件名由本模块生成：管理员报告
    （1.1 admin_mode=True）用 admin-record- 前缀，其余用 record- 前缀；同秒追加 -N。
    校验/序列化/写盘/发布任一失败均不改动既有记录、不残留可见半条正式记录；
    临时文件与正式文件共用同一授权目录。不接收任意路径注入，不对 scan_root 做任何
    文件系统操作。
    """
    validated = validate_record(report)  # 校验先于任何目录创建/写盘
    directory = _require_safe_root(records_dir if records_dir is not None else RECORDS_DIR)
    os.makedirs(directory, exist_ok=True)
    admin = validated.get("admin_mode") is True
    prefix = RECORD_ADMIN_PREFIX if admin else RECORD_NORMAL_PREFIX
    stamp = (now if now is not None else datetime.now()).strftime("%Y%m%d-%H%M%S")
    record_id, target = _reserve_target(directory, f"{prefix}-{stamp}")
    payload = _serialize(validated)
    temp_path: str | None = None
    try:
        temp_path = _stage(directory, payload)
        _publish(temp_path, target)
        temp_path = None  # 已被 rename 消费
        return record_id
    finally:
        if temp_path is not None:
            _safe_unlink(temp_path)


# ---------------------------------------------------------------------------
# 读取 / 列举
# ---------------------------------------------------------------------------


def _require_regular_file(target: str) -> None:
    """os.lstat 不跟随符号链接/重解析点；目录、重解析点、非普通文件一律拒绝。"""
    try:
        st = os.lstat(target)
    except OSError as exc:
        raise RecordError(
            texts.RECORDS_TEXTS["records_err_read"].format(exc=exc)
        ) from exc
    if _is_reparse_point(st) or not stat.S_ISREG(st.st_mode):
        raise RecordError(
            texts.RECORDS_TEXTS["records_err_not_regular"].format(
                filename=os.path.basename(target)
            )
        )


def _read_raw(target: str) -> str:
    """读取 UTF-8 文本；读取/解码失败包装为中文 RecordError。"""
    try:
        with open(target, "r", encoding="utf-8") as handle:
            return handle.read()
    except UnicodeDecodeError as exc:
        raise RecordError(
            texts.RECORDS_TEXTS["records_err_encode"].format(exc=exc)
        ) from exc
    except OSError as exc:
        raise RecordError(
            texts.RECORDS_TEXTS["records_err_read"].format(exc=exc)
        ) from exc


def _load_record(target: str) -> dict:
    """普通文件守卫 → 读取 → JSON 解析 → 形状/版本校验；任一失败抛 RecordError。"""
    _require_regular_file(target)
    raw = _read_raw(target)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RecordError(
            texts.RECORDS_TEXTS["records_err_json"].format(exc=exc)
        ) from exc
    return validate_record(data)


def read_record(record_id: str, *, records_dir: str | None = None) -> dict:
    """按逻辑 ID 读取并校验一条记录，返回报告形状对象；ID 非法/越界、损坏、不兼容
    版本均抛可区分的 RecordError 子类。默认根 = RECORDS_DIR，测试根可注入。
    """
    directory = _require_safe_root(records_dir if records_dir is not None else RECORDS_DIR)
    target = resolve_record_path(directory, record_id)
    return _load_record(target)


def list_records(*, records_dir: str | None = None) -> list[RecordEntry]:
    """列举授权目录下本模块严格命名的普通文件，按文件名排序返回 RecordEntry 列表。

    仅识别 RECORD_NAME_RE 且为普通文件（非目录、非重解析点）的条目；损坏 JSON、
    坏字段、不兼容版本逐项披露为 comparable=False + problem，不崩溃、不阻断同目录
    其他合法记录、不静默说可比。外来文件/临时文件/目录/重解析点不进入或不被跟随。
    默认根 = RECORDS_DIR，测试根可注入；不遍历被扫描目标。
    """
    directory = _require_safe_root(records_dir if records_dir is not None else RECORDS_DIR)
    if not os.path.isdir(directory):
        return []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    entries: list[RecordEntry] = []
    for name in names:
        if RECORD_NAME_RE.fullmatch(name) is None:
            continue
        record_id = name[: -len(_JSON_EXT)]
        try:
            target = resolve_record_path(directory, record_id)
            data = _load_record(target)
        except RecordError as exc:
            entries.append(
                RecordEntry(
                    record_id=record_id,
                    filename=name,
                    comparable=False,
                    record=None,
                    problem=str(exc),
                    admin_mode=False,
                    schema_version=None,
                )
            )
            continue
        entries.append(
            RecordEntry(
                record_id=record_id,
                filename=name,
                comparable=True,
                record=data,
                problem=None,
                admin_mode=data.get("admin_mode") is True,
                schema_version=data["schema_version"],
            )
        )
    return entries
