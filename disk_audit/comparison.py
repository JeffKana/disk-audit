r"""两份体检记录的纯比较（I2a，任务卡 T5-03 / T503-v1）。

依据：F1 定稿 E-3（新增/减少/不变三态与净变化）、Q7（记录只存候选+聚合与
schema_version）、§7-M3（对比结果须与两次报告交叉核对）、§9.2（判定单元路径身份）；
`docs/schemas/record-v1-字段对照表.md`（记录形状/版本/异常边界）；`disk_audit/records.py`
的 `validate_record` 与 `RecordError` 层次；`docs/schemas/record-comparison-接口说明.md`。

冻结语义（本卡技术裁决 A~F）：
- 纯函数：输入两份 report/record 形状对象，由调用方给出前/后顺序；不读磁盘、
  不读记录目录、不取系统时间、不猜最近一条、不调用文件/注册表/子进程/网络。
- 身份按报告内**字面路径字符串**：scan_root 须逐字相同；候选 path 逐字作 key，
  不 casefold、不解析 symlink/junction、不合并大小写/分隔符/.. 的不同写法。
- 只比较同模式：普通与管理员记录不可比；已知 1.0/1.1 且同模式可比。
- 三态：after 有 before 无→新增；before 有 after 无→减少；两份均有→不变
  （仍存在，不要求占用/置信度/证据/动作相同）。
- 净变化只取两份 totals.allocated_bytes 之差，不以候选差值求和替代。

本模块**不**实现 UI/持久化/自动选记录/额度淘汰/CSV，也不引入新记录 envelope。
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine import texts
from .records import validate_record


class ComparisonError(ValueError):
    """比较层异常基类（中文文案）：跨记录不可比与重复路径等比较期错误的公共父类。"""


class ComparisonIncompatibleError(ComparisonError):
    """两份记录不可比：扫描范围不同或普通/管理员模式不同（不提供强制混比开关）。"""


class ComparisonDuplicatePathError(ComparisonError):
    """同一份报告内候选路径重复：拒绝 dict 后者静默覆盖。"""


@dataclass(frozen=True)
class ComparisonItem:
    """对比项：按字面 path 对齐；不存在侧为 None；allocated_delta 带符号。

    - 新增：`before=None`，`allocated_delta = after.allocated_bytes`。
    - 减少：`after=None`，`allocated_delta = -before.allocated_bytes`。
    - 不变：两侧候选均保留，`allocated_delta = after - before`（可正/零/负）。
    """

    path: str
    before: dict | None
    after: dict | None
    allocated_delta: int


@dataclass(frozen=True)
class RecordComparison:
    """两份记录的对比结果（不可变）：三组有序项 + 净变化与可比元数据。

    `added`/`removed`/`unchanged` 组内按字面 path 升序；`net_allocated_delta`
    只取 `after.totals.allocated_bytes - before.totals.allocated_bytes`，与候选
    差值之和无关（父子重叠候选不得双计）。
    """

    added: tuple[ComparisonItem, ...]
    removed: tuple[ComparisonItem, ...]
    unchanged: tuple[ComparisonItem, ...]
    net_allocated_delta: int
    scan_root: str
    admin_mode: bool
    before_schema_version: str
    after_schema_version: str


def _index_candidates(report: dict, side: str) -> dict[str, dict]:
    """按字面 path 建索引；同一份报告内重复 path 立即拒绝（不做后者覆盖）。"""
    index: dict[str, dict] = {}
    for candidate in report["candidates"]:
        path = candidate["path"]
        if path in index:
            raise ComparisonDuplicatePathError(
                texts.COMPARISON_TEXTS["comparison_err_duplicate_path"].format(
                    side=side, path=path
                )
            )
        index[path] = candidate
    return index


def compare_records(before: object, after: object) -> RecordComparison:
    """比较两份报告形状对象（before=前一份，after=后一份），返回不可变结果。

    两份输入先经 `records.validate_record` 校验（只接受 report-v1 形状与已知
    1.0/1.1 版本；多余字段、坏 totals/候选/枚举容器、`incomplete=True` 一律拒绝），
    再按字面 path 对齐分类；本函数不修改输入，也不访问任何文件系统/系统时间。

    检查顺序（决定同时存在多个问题时的异常）：前后两份校验 → 前/后报告内重复
    path（先前份后后份）→ `scan_root` 逐字相同 → 普通/管理员模式相同。

    Raises:
        records.RecordValidationError: 形状/字段/候选/多余字段/`incomplete=True` 非法。
        records.RecordVersionError: 未知或非字符串 `schema_version`（含"旧记录不可比"）。
        ComparisonDuplicatePathError: 同一份报告内候选路径重复。
        ComparisonIncompatibleError: 扫描范围不同，或普通/管理员模式不同。
    """
    before_record = validate_record(before)
    after_record = validate_record(after)

    before_index = _index_candidates(
        before_record, texts.COMPARISON_TEXTS["comparison_side_before"]
    )
    after_index = _index_candidates(
        after_record, texts.COMPARISON_TEXTS["comparison_side_after"]
    )

    if before_record["scan_root"] != after_record["scan_root"]:
        raise ComparisonIncompatibleError(
            texts.COMPARISON_TEXTS["comparison_err_root_mismatch"].format(
                before=before_record["scan_root"], after=after_record["scan_root"]
            )
        )

    before_admin = before_record.get("admin_mode") is True
    after_admin = after_record.get("admin_mode") is True
    if before_admin != after_admin:
        raise ComparisonIncompatibleError(
            texts.COMPARISON_TEXTS["comparison_err_mode_mismatch"].format(
                before=before_admin, after=after_admin
            )
        )

    added = tuple(
        ComparisonItem(
            path=path,
            before=None,
            after=after_index[path],
            allocated_delta=after_index[path]["allocated_bytes"],
        )
        for path in sorted(after_index)
        if path not in before_index
    )
    removed = tuple(
        ComparisonItem(
            path=path,
            before=before_index[path],
            after=None,
            allocated_delta=-before_index[path]["allocated_bytes"],
        )
        for path in sorted(before_index)
        if path not in after_index
    )
    unchanged = tuple(
        ComparisonItem(
            path=path,
            before=before_index[path],
            after=after_index[path],
            allocated_delta=(
                after_index[path]["allocated_bytes"]
                - before_index[path]["allocated_bytes"]
            ),
        )
        for path in sorted(before_index)
        if path in after_index
    )
    return RecordComparison(
        added=added,
        removed=removed,
        unchanged=unchanged,
        net_allocated_delta=(
            after_record["totals"]["allocated_bytes"]
            - before_record["totals"]["allocated_bytes"]
        ),
        scan_root=before_record["scan_root"],
        admin_mode=before_admin,
        before_schema_version=before_record["schema_version"],
        after_schema_version=after_record["schema_version"],
    )
