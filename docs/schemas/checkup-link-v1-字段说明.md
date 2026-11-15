# checkup-link-v1 字段说明（T5-04-A · 显式体检关联元数据基础）

本文件是 DR-016 冻结接口的交接说明，不是新记录/报告 schema，也不改变
[record-v1 字段对照表](record-v1-字段对照表.md) 与 [report-v1 字段对照表](report-v1-字段对照表.md)。
权威实现：disk_audit/links.py；默认根：RECORDS_DIR/links（F1 一级目录仍是 reports/records/tmp）。

## 1. 目的与边界

- 为「一次体检的 HTML 报告 + 至多一份 JSON 记录」提供**显式**关联标识，替代按同秒 /
  mtime / 目录顺序猜配（DR-012 §4 明确不采纳近似配对）。
- 本卡只做**基础库**：纯构建/校验、单文件保存/读取、只读列举。**不**接线 launcher/UI、
  **不**提权、**不**实现 12 次 / 50,000,000 B 联合额度或淘汰、**不**删除任何文件、
  **不**迁移旧数据、**不**改 record-v1 / report-v1 字段。
- 关联 schema 合法**不等于**报告或记录实际存在、内容完整或可安全删除；这些由后续
  纯 planner 与独立测试另行判定。

## 2. 七字段（全部且仅有）

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| schema_version | 字符串 | 固定 checkup-link-v1；非字符串或未知版本抛 LinkVersionError |
| checkup_id | 字符串 | 32 位**小写** ASCII hex（uuid4().hex）；与文件名 link-&lt;id&gt;.json 必须一致 |
| created_at | 字符串 | 含**明确时区**的 ISO 8601（Z 或 ±HH:MM）；必须有日期+时间；仅描述，不用作关联或“最近”排序 |
| mode | 字符串 | 严格 normal 或 admin |
| report_filename | 字符串 | 仅基名；ASCII 模式 (?:admin-)?report-[0-9]{8}-[0-9]{6}(?:-[0-9]+)?.html；admin 前缀必须与 mode 一致；不含路径/穿越/ADS/绝对根/双扩展名 |
| record_id | 字符串或 null | null 或 (?:admin-)?record-[0-9]{8}-[0-9]{6}(?:-[0-9]+)?（不含 .json）；前缀与 mode 一致；**不要求**与报告同秒 |
| record_error | 字符串或 null | 仅 record-save-failed（固定机器码）；拒绝空串/原始异常/自由文字/用户路径 |

顶层出现任何未定义字段（含非字符串键）或坏容器一律拒绝，不持久化额外数据。

## 3. 组合规则

1. **XOR**：record_id 与 record_error 必须且只能有一个非空。
   - 记录保存成功：record_id 非空、record_error=null。
   - 报告已存但记录保存失败：record_id=null、record_error="record-save-failed"。
2. **模式一致**：mode=admin 时报告/记录都必须带 admin- 前缀；mode=normal 时都不得带。
3. **同秒不要求**：报告与记录的时间戳可以不同（关联靠 checkup_id，不靠时间）。
4. 记录环未启用时**不自动创建** link（接线属后续卡，DR-016 未冻结）。

## 4. 文件与目录

- 目录：&lt;records&gt;/links/，直属普通目录；不递归。
- 文件名：link-&lt;32 位小写 hex&gt;.json；仅识别严格匹配项。
- 列举顺序：**文件名字面升序**（不是“最近体检顺序”，UUID 顺序无时间语义）。
- 非匹配外来文件 / 目录 / 临时文件：不读取、不修改、不列入。
- 坏项（坏 JSON、未知版本、正文 ID 不符、同名目录、重解析点叶）逐项返回 problem 且
  data=None，不阻断同目录其它合法项。

## 5. 对外接口与错误

```python
new_checkup_id() -> str
build_link(*, checkup_id, created_at, mode, report_filename, record_id, record_error) -> dict
validate_link(link: object) -> dict
save_link(link, *, links_dir=None) -> str          # 返回 checkup_id
read_link(checkup_id, *, links_dir=None) -> dict
list_links(*, links_dir=None) -> list[LinkEntry]   # frozen dataclass
```

| 异常 | 何时 |
| --- | --- |
| LinkError(ValueError) | 全部可消费错误的公共父类 |
| LinkValidationError | 形状/缺字段/多字段/类型/命名/模式前缀/XOR/正文 ID 不符/ID 非法 |
| LinkVersionError | schema_version 非字符串或未知版本 |
| LinkIOError | 根/祖先不安全、叶非普通文件/重解析点、缺失、编码/JSON/读写/发布失败、目标已存在 |

LinkEntry 字段：checkup_id: str、filename: str、data: dict | None、problem: str | None。
不提供“最近”或 admin 默认值推定。

build_link / validate_link 纯内存：不生成 ID、不读当前时间、不触碰文件系统；
validate_link 返回新的顶层字典，不改动入参。

## 6. 读写安全

- save_link：**先**纯校验，**再**触发根/磁盘动作；根及现有全部祖先逐段 lstat 核验
  （复用 records._require_safe_root，异常映射为 LinkIOError）；缺失的安全尾部可创建；
  创建后再核验一次尾部为普通目录。
- 写入：同目录 .tmp-link- 临时文件，完整写 + flush + fsync，再用 Windows 不覆盖语义的
  os.rename 原子发布；目标已存在即失败，旧字节不变，**禁止** os.replace 覆盖或重试循环；
  失败只清本次自建临时文件。
- read_link：ID 先校验（I/O 之前）；根/祖先/叶守卫；读取单一普通文件，JSON、schema、
  正文 ID 必须一致；read / list 不 mkdir。
- 以上是**调用时**守卫，不宣称对恶意并发路径替换的系统级形式证明（DR-016 原文边界）。

## 7. 示例

```json
{
  "schema_version": "checkup-link-v1",
  "checkup_id": "0123456789abcdef0123456789abcdef",
  "created_at": "2026-11-16T00:56:30+08:00",
  "mode": "normal",
  "report_filename": "report-20261116-005630.html",
  "record_id": "record-20261116-005630",
  "record_error": null
}
```

```json
{
  "schema_version": "checkup-link-v1",
  "checkup_id": "fedcba9876543210fedcba9876543210",
  "created_at": "2026-11-16T00:56:30Z",
  "mode": "admin",
  "report_filename": "admin-report-20261116-005630.html",
  "record_id": null,
  "record_error": "record-save-failed"
}
```
