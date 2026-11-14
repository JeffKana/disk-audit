# record-comparison 接口说明（T5-03 · I2a 两份体检记录的纯比较）

本文冻结 `disk_audit/comparison.py` 的公共 API、字段语义、异常与边界，供后续 UI 卡
（T5-05）和独立测试交接使用。**本文不引入新的持久化格式或记录 envelope**：比较输入
仍是 report-v1 形状的体检报告/记录，落盘格式与版本语义见
[report-v1.schema.json](report-v1.schema.json) 与
[record-v1-字段对照表.md](record-v1-字段对照表.md)。

依据：F1 定稿 E-3（新增/减少/不变与净变化）、Q7（记录内容与版本提示）、§7-M3
（对比结果须与两次报告交叉核对）、§9.2（判定单元 = 顶层目录及下钻子项）。

## 1. 公共 API

```python
def compare_records(before: object, after: object) -> RecordComparison: ...
```

- `before` = 前一份报告/记录，`after` = 后一份；**顺序由调用方显式给出**。
- 不读磁盘、不读记录目录、不取系统时间、不自动挑"最近一条"、不排序时间。
- 两份输入先经 `disk_audit.records.validate_record` 校验；本模块不放宽/不复制校验器。
- 返回不可变结果；不修改任一输入（含嵌套 `totals`/`candidates`/`evidence_chain`）。
- 运行时仅标准库 + 包内模块；无文件/目录/注册表/子进程/网络调用。

### 1.1 数据类型

```python
@dataclass(frozen=True)
class ComparisonItem:
    path: str
    before: dict | None   # 不存在侧为 None；存在侧为该记录中已校验的候选对象
    after: dict | None
    allocated_delta: int  # 带符号，见 §2.3

@dataclass(frozen=True)
class RecordComparison:
    added: tuple[ComparisonItem, ...]
    removed: tuple[ComparisonItem, ...]
    unchanged: tuple[ComparisonItem, ...]
    net_allocated_delta: int
    scan_root: str
    admin_mode: bool
    before_schema_version: str
    after_schema_version: str
```

- 三组成员互斥且覆盖两份报告出现过的全部路径（每个 path 恰好出现一次）。
- 组内按**字面 `path` 升序**（Python 码点序）；输入候选顺序不影响结果。
- `scan_root` 为两份逐字相同的扫描根；`admin_mode` 为共同模式；版本字段保留各自
  `schema_version`（1.0 与 1.1 可同模式比较，见 §3）。
- 结果中的候选对象来自已校验记录的浅拷贝顶层对象（嵌套证据链共享），调用方**不得修改**。

## 2. 分类与数值语义

### 2.1 三态（按字面路径是否存在）

| 情况 | 分类 | `before` | `after` |
| --- | --- | --- | --- |
| after 有、before 无 | 新增 `added` | `None` | 候选 |
| before 有、after 无 | 减少 `removed` | 候选 | `None` |
| 两份均有 | 不变 `unchanged` | 候选 | 候选 |

"不变"只表示该判定单元**仍然存在**；占用、置信度、判定来源、建议动作、证据链
变化都**不**改变分类，前后候选原样保留供展示。

### 2.2 净变化

`net_allocated_delta = after.totals.allocated_bytes - before.totals.allocated_bytes`。

**只取 totals 差**：不得用候选 `allocated_delta` 求和替代（父子判定单元会重叠，
例如候选差值和 50 B、totals 实际只差 20 B 时，净变化必须是 20 B）。负值表示总量
下降；零表示总量不变。

### 2.3 每项带符号差值

| 分类 | `allocated_delta` |
| --- | --- |
| 新增 | `after.allocated_bytes - 0`（正） |
| 减少 | `0 - before.allocated_bytes`（负） |
| 不变 | `after.allocated_bytes - before.allocated_bytes`（可正/零/负） |

数值口径为占用空间（P1），与 totals 一致；布尔值不是数字，校验层已拒绝。

## 3. 版本与模式兼容

| 输入组合 | 结果 |
| --- | --- |
| 1.0 + 1.1，均为普通模式 | 可比（1.0 缺 `admin_mode` 按普通；1.1 缺省/`false` 也按普通） |
| 1.1 + 1.1，均 `admin_mode=true` | 可比，结果 `admin_mode=True` |
| `admin_mode` 一侧 true、另一侧 false/缺失 | `ComparisonIncompatibleError`（普通/管理员不自动比较；无 force 开关） |
| 未知主/次版本、非字符串版本 | `records.RecordVersionError`（含"旧记录不可比"） |
| 1.0 出现 `admin_mode` | `records.RecordValidationError`（沿用存储契约，不改义） |
| `incomplete=true` | `records.RecordValidationError`（不完整报告不参与比较） |

## 4. 路径身份（保守裁决）

- `scan_root` 必须**逐字相同**；不同即 `ComparisonIncompatibleError`。
- 候选 `path` **逐字**作为 key：不 casefold、不统一分隔符、不折叠 `.`/`..`、
  不解析 symlink/junction、不做任何文件系统探测。
- 因此 `C:\App\X`、`c:\app\x`、`C:\App\X\`、`C:\App\Sub\..\X` 是**四个不同**
  的判定单元；不把两种写法冒充为同一物理目录，也不冒充为物理不同。
- 同一份报告内出现重复 `path`（逐字相等）即 `ComparisonDuplicatePathError`，
  拒绝 dict 后者静默覆盖。

## 5. 异常

| 异常 | 父类 | 触发 |
| --- | --- | --- |
| `ComparisonDuplicatePathError` | `ComparisonError(ValueError)` | 同一份报告内路径重复 |
| `ComparisonIncompatibleError` | `ComparisonError(ValueError)` | 扫描范围不同 / 普通与管理员模式不同 |
| `records.RecordValidationError` | `records.RecordError(ValueError)` | 形状/字段/候选/多余字段/`incomplete=true` 非法 |
| `records.RecordVersionError` | `records.RecordError(ValueError)` | 未知/非字符串版本（"旧记录不可比"） |

检查顺序：前份校验 → 后份校验 → 前份重复路径 → 后份重复路径 → 扫描范围 →
模式。同时存在多个问题时按此顺序抛出第一个，便于调用方定位。

## 6. 使用示例

```python
from disk_audit.comparison import compare_records

result = compare_records(before_record, after_record)
for item in result.added:
    print("新增", item.path, item.after["allocated_bytes"])
for item in result.removed:
    print("减少", item.path, item.allocated_delta)
for item in result.unchanged:
    print("仍在", item.path, item.allocated_delta)
print("净变化", result.net_allocated_delta, "B")
```

## 7. 本卡未做（不宣称 I2/M3 完成）

- UI 两次对比入口、离线展示与旧记录提示：T5-05（本模块只提供纯函数）。
- 记录接线/自动选最近一条/普通与管理员隔离展示：T5-02。
- 联合 50 MB / 最近 12 次额度与淘汰：T5-04。
- 路径词法归一化（大小写/分隔符/`..`）、symlink/junction 解析、物理同一性判定：
  未实现；如后续需要另立裁决与测试，本卡不静默合并。
- CSV 导出、持久化对比结果、跨扫描根比较、混模式强制比较：均不支持。
- 真实 VM/CI/远端门禁与独立 DSH 验收：由 PM 在冻结候选 SHA 后另行派发。

## 8. 文案资源

固定中文文案集中在 `disk_audit/engine/texts.py` 文末 `COMPARISON_TEXTS`（append-only，
不改上方既有区）：侧别标签 2 键 + 范围/模式/重复路径错误模板 3 键。动态值
（根、模式布尔、路径、侧别）走模板参数；判定措辞与置信度文案不在本区。
