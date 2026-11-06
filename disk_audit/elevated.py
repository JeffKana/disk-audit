r"""以管理员身份重扫（待办 H1，任务卡 T4-01）。

依据：方案 Q6（用户点击触发 → ``ShellExecuteW(..., "runas", ...)`` 重启自身，扫描规格经
``tmp\\spec.json`` 传递）、E-4（"以管理员身份重扫"入口）、U-3（未获用户显式点击不发起
任何提权请求）、U-2（本程序仅写 %LOCALAPPDATA%\\DiskAudit\\，spec/done 均落
DATA_DIR\\tmp\\）、S-3（管理员模式独立产出，完整标注归 T4-04）、R9（提权后不联网、
不执行任何外部程序——本模块零子进程/零网络，AST 断言由 tests/test_elevated.py 固化）、
E-5/X-4（ERROR_CANCELLED 判定与失败呈现归 T4-02/T4-03，本卡仅返回码接口位）、
开发规范 §1（文案集中 texts；运行时零第三方依赖）。

【防重生设计（本卡第一设计约束；前次执行曾产生 python 进程自重生链，根因未确证）】
1. 自重启调用单点化：全仓库 ShellExecuteW 仅存在于 launcher._shell_execute_runas（UI
   点击回调链）；本模块与 launcher._cmd_elevated_rescan 及其调用链 AST 断言零自启动
   调用（ShellExecuteW/WinExec/os.system/os.popen/subprocess/os.startfile 一律禁止），
   提权实例在代码结构上不可能重启自身或任何外部程序；
2. spec 消费一次性语义：请求原子认领即焚（os.rename 认领，Windows 同目录目标存在即
   FileExistsError——并发双实例只有一个拿到请求），重复执行/陈旧请求/无请求一律
   EXIT_BAD_REQUEST 拒绝退出，绝不重试；
3. UI 侧仅单击触发：runas 发起只能由 launcher._on_admin_rescan 点击回调经
   request_admin_rescan 调用一次，无重试/轮询/自动再触发路径（调用点唯一性由 AST 断言）。

接口约定（T4-02/T4-03/T4-04 栈本分支，据此消费）：

1. spec.json（DATA_DIR\\tmp\\spec.json，U-2 合规位，Q1 定稿的规格传递位）::

     {"schema_version": "elevated-rescan-spec-v1",
      "request_id": "<uuid4 hex32>",
      "created_at": "<ISO8601 UTC，带时区>",
      "scope": "<扫描范围绝对路径>",
      "host_pid": <宿主进程 PID>}

   一次性消费：提权实例先原子认领（改名 spec.json → spec.json.claimed）再读取校验，
   读完即删除认领文件；时效窗 MAX_SPEC_AGE_SECONDS（600s），未来时间戳超容差
   FUTURE_TOLERANCE_SECONDS（60s）同样拒绝。写新请求时清掉旧认领与旧 done。

2. 完成标记 admin_rescan_done.json（DATA_DIR\\tmp\\，供 T4-04 消费）::

     {"schema_version": "elevated-rescan-done-v1",
      "request_id": "<与 spec 一致>",
      "mode": "admin",
      "status": "completed" | "failed",
      "report_path": "<报告绝对路径；failed 时为 null>",
      "finished_at": "<ISO8601 UTC>",
      "evidence_note": "<R9 证据降级披露（常量文案）>",
      "error": "<仅 failed 时存在>"}

   EXIT_BAD_REQUEST（4）路径不写 done——done 只由合法请求产出（H3 等待/消费前提）。

3. CLI：``python launcher.py --elevated-rescan``（提权实例入口 = 重启自身同一入口；
   规格取固定位 tmp\\spec.json，不接受路径参数——减小提权面）。退出码三态：
   0=成功（done=completed）、4=spec 缺失/损坏/过期/非法/已消费（不写 done）、
   5=流水线失败（done=failed）。

4. ShellExecuteW 返回码语义（Win32）：>32=已发起；ERROR_CANCELLED(1223)=UAC 取消
   （E-5，T4-02 接口位）；其余=发起失败（X-4 口径，T4-03 接口位）。宿主侧
   launcher.request_admin_rescan 原样返回该码，不弹框、不重试（本卡只留接口位）。

5. 管理员报告命名：``admin-report-YYYYmmdd-HHMMSS.html``（同秒冲突追加 -N）——先经
   reports.save_report 守卫落盘再同目录改名（写入位不变，U-2）；该命名不匹配淘汰
   正则，不参与普通报告 12 份淘汰（S-3 独立记录；清理归 T4-04/M3）。

6. R9 证据降级：提权实例只装配零子进程的注册表只读证据源（注册表卸载项/自启动）；
   需经 powershell 子进程采集的 Appx/进程/服务三源不采集，按方案口径"该证据源不可用"
   降级并以 reason/evidence_note 披露。

7. 管理员模式报告字段（T4-04 承接）：run_elevated_rescan 对注入 deps 的 judge 包装
   （_with_admin_judge → mark_admin_report），报告装配完成后置 ``admin_mode=true``
   （report-v1 1.1 可选顶层 boolean，S-3/H4；普通流水线不产该键）。报告页眉
   "管理员模式"徽标由 render 按该字段渲染（texts.ADMIN_MODE_BADGE，.adminbadge
   配色类）；独立记录三重区分 = 本字段 + admin- 文件名前缀 + done 标记 mode=admin。

模块边界：本模块零 UI、零网络、零子进程、零自启动；spec 写入与命令构造为宿主侧
可注入纯逻辑，编排（run_elevated_rescan）经 audit/deps 双注入复用 launcher.execute_audit
流水线（不 import launcher，依赖倒置防循环）。
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import uuid
import winreg
from datetime import datetime, timezone
from typing import Callable

from disk_audit import reports
from disk_audit.evidence.appx import AppxResult
from disk_audit.evidence.autostart import collect_autostart
from disk_audit.evidence.evidence import EvidenceBundle
from disk_audit.evidence.processes import ProcessResult
from disk_audit.evidence.registry_uninstall import collect_uninstall
from disk_audit.evidence.services import ServiceResult
from disk_audit.engine import texts

H1_TEXTS = texts.H1_TEXTS

# 文件名与 schema 版本（接口约定，见模块 docstring；tests/test_elevated.py 锁定）
SPEC_FILENAME = "spec.json"
CLAIM_SUFFIX = ".claimed"  # 原子认领文件后缀（消费即焚，写新请求时清除陈旧认领）
DONE_FILENAME = "admin_rescan_done.json"
SPEC_SCHEMA_VERSION = "elevated-rescan-spec-v1"
DONE_SCHEMA_VERSION = "elevated-rescan-done-v1"

# 管理员报告命名标记（S-3 文件级可区分；schema 字段/页眉徽标由 T4-04 承接）
ADMIN_REPORT_PREFIX = "admin-"

# 管理员模式报告字段名（report-v1 1.1 可选顶层 boolean，S-3/H4/T4-04；schema
# docs/schemas/report-v1.schema.json properties.admin_mode——仅提权实例产出报告
# 携带 true，普通报告不含本键，消费方缺省按非管理员处理）
ADMIN_MODE_FIELD = "admin_mode"

# 请求时效窗（防陈旧请求自决）：600s 覆盖 UAC 等待与慢环境；
# 未来时间戳容差 60s（时钟轻微偏差不作废请求）。
MAX_SPEC_AGE_SECONDS = 600
FUTURE_TOLERANCE_SECONDS = 60

# Win32：ShellExecuteW 返回 >32 视为已发起；ERROR_CANCELLED=UAC 取消（E-5/T4-02 接口位）
ERROR_CANCELLED = 1223
SW_SHOWNORMAL = 1

# 重启自身标记参数（提权实例入口，launcher.main 顶层 flag）
ELEVATED_FLAG = "--elevated-rescan"

# 提权实例退出码（接口约定；2=argparse 用法错误、3=launcher 版本闸，互不冲突）
EXIT_OK = 0
EXIT_BAD_REQUEST = 4  # spec 缺失/损坏/过期/字段非法/已消费（不写 done）
EXIT_PIPELINE_FAILED = 5  # scan/judge/render/save 环节失败（done=failed）

# ShellExecuteW 替身签名：(lp_file, lp_verb, lp_parameters) -> 返回码
ShellExecute = Callable[[str, str, str], int]

# 提权实例流水线替身签名：launcher.execute_audit 同款（path, *, deps=...) -> 报告路径 | None
AuditPipeline = Callable[..., "str | None"]


class RescanRequestError(ValueError):
    """spec.json 缺失/损坏/过期/字段非法/已消费（中文文案，texts.H1_TEXTS）。"""


def _default_tmp_dir() -> str:
    """运行时取包级 TMP_DIR（属性访问：测试 monkeypatch disk_audit.TMP_DIR 生效）。"""
    import disk_audit

    return disk_audit.TMP_DIR


def _utc_iso(now: datetime | None) -> str:
    moment = now if now is not None else datetime.now(timezone.utc)
    if moment.tzinfo is None:  # 防御：naive datetime 视为 UTC
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def _claim_path(directory: str) -> str:
    return os.path.join(directory, SPEC_FILENAME + CLAIM_SUFFIX)


def _discard(path: str) -> None:
    """消费/清理辅助：删除失败不阻断（文件属主即本程序，重放面由认领语义兜底）。"""
    try:
        os.remove(path)
    except OSError:
        pass


def write_rescan_request(
    scope: str,
    *,
    tmp_dir: str | None = None,
    now: datetime | None = None,
    request_id: str | None = None,
    host_pid: int | None = None,
) -> dict:
    """构造并写入 spec.json（宿主侧点击回调链调用；U-3 唯一写规格入口）。

    写入前清掉陈旧认领文件与上一次完成标记：陈旧认领不得阻塞新请求、旧 done
    不得被误挂到新请求（T4-04 消费前提）。返回请求 dict（含生成的 request_id）。
    """
    directory = tmp_dir if tmp_dir is not None else _default_tmp_dir()
    os.makedirs(directory, exist_ok=True)
    _discard(_claim_path(directory))
    _discard(os.path.join(directory, DONE_FILENAME))
    request = {
        "schema_version": SPEC_SCHEMA_VERSION,
        "request_id": request_id if request_id is not None else uuid.uuid4().hex,
        "created_at": _utc_iso(now),
        "scope": scope,
        "host_pid": host_pid if host_pid is not None else os.getpid(),
    }
    with open(os.path.join(directory, SPEC_FILENAME), "w", encoding="utf-8") as handle:
        json.dump(request, handle, ensure_ascii=False, indent=2)
    return request


def read_rescan_request(
    *,
    tmp_dir: str | None = None,
    now: datetime | None = None,
    max_age: int = MAX_SPEC_AGE_SECONDS,
    future_tolerance: int = FUTURE_TOLERANCE_SECONDS,
) -> dict:
    """读取并校验 spec.json；一次性消费语义（防重生防线 2）。

    流程：原子认领（os.rename spec → spec.claimed；Windows 同目录目标存在即
    FileExistsError，并发双实例必有一个认领失败）→ 读取校验 → 删除认领文件
    （消费即焚）。重复执行/陈旧请求/无请求一律抛 RescanRequestError，调用方
    （run_elevated_rescan）映射为 EXIT_BAD_REQUEST 拒绝退出，绝不重试。
    """
    directory = tmp_dir if tmp_dir is not None else _default_tmp_dir()
    path = os.path.join(directory, SPEC_FILENAME)
    claimed = _claim_path(directory)
    try:
        os.rename(path, claimed)  # 原子认领：第二个实例在此被拒（FileExistsError）
    except OSError as exc:
        raise RescanRequestError(
            H1_TEXTS["spec_err_missing"].format(path=path)
        ) from exc
    try:
        with open(claimed, encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        _discard(claimed)
        raise RescanRequestError(
            H1_TEXTS["spec_err_corrupt"].format(path=claimed)
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _discard(claimed)
        raise RescanRequestError(
            H1_TEXTS["spec_err_corrupt"].format(path=claimed)
        ) from exc
    reason = _validate_request(data, now=now, max_age=max_age, future_tolerance=future_tolerance)
    _discard(claimed)  # 校验通过与否均焚毁认领文件：一次性消费不留重放材料
    if reason is not None:
        raise RescanRequestError(H1_TEXTS["spec_err_invalid"].format(reason=reason))
    return data


def _validate_request(
    data: object, *, now: datetime | None, max_age: int, future_tolerance: int
) -> str | None:
    """返回 None 表示合法，否则返回中文原因（spec_err_invalid 的 reason）。"""
    if not isinstance(data, dict):
        return "请求必须是 JSON 对象"
    if data.get("schema_version") != SPEC_SCHEMA_VERSION:
        return f"schema_version 不符：{data.get('schema_version')!r}"
    request_id = data.get("request_id")
    if not isinstance(request_id, str) or len(request_id) != 32:
        return "request_id 必须为 32 位十六进制字符串"
    try:
        int(request_id, 16)
    except ValueError:
        return "request_id 必须为十六进制"
    created_raw = data.get("created_at")
    if not isinstance(created_raw, str):
        return "created_at 缺失"
    try:
        created = datetime.fromisoformat(created_raw)
    except ValueError:
        return "created_at 不是合法 ISO8601 时间"
    if created.tzinfo is None:
        return "created_at 缺少时区"
    moment = now if now is not None else datetime.now(timezone.utc)
    age = (moment - created).total_seconds()
    if age > max_age:
        return f"请求已超时效（{int(age)}s > {max_age}s）"
    if age < -future_tolerance:
        return "请求时间来自未来（超出容差）"
    scope = data.get("scope")
    if not isinstance(scope, str) or not scope or not os.path.isabs(scope):
        return "scope 必须为非空绝对路径"
    return None


def build_rescan_command(
    *,
    executable: str | None = None,
    script: str | None = None,
    frozen: bool | None = None,
) -> tuple[str, str]:
    """构造"重启自身"命令（纯函数）：返回 (lpFile, lpParameters)。

    脚本形态（python launcher.py）：lpFile=解释器，参数=带引号脚本路径 + 标记；
    冻结形态（PyInstaller 等 sys.frozen，M5 打包前置）：lpFile=自身 exe，参数=仅标记。
    frozen=None 时按运行环境自动判定（供真实路径；测试显式注入两分支）。
    """
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        return executable or sys.executable, ELEVATED_FLAG
    script_path = os.path.abspath(script if script is not None else sys.argv[0])
    return executable or sys.executable, f'"{script_path}" {ELEVATED_FLAG}'


def collect_evidence_readonly(*, winreg_module=winreg) -> EvidenceBundle:
    """提权实例只读证据装配（R9：提权进程不执行任何外部程序）。

    仅采集零子进程的注册表只读源（注册表卸载项/自启动）；需经 powershell 子进程
    采集的 Appx/进程/服务三源不采集，按方案口径"该证据源不可用"降级并以 reason
    披露（done 标记 evidence_note 承载同一披露，供 T4-04 报告标注承接）。
    聚合层 X-1 语义不变：单源失败记 errors 披露，不中断其余源。
    """
    bundle = EvidenceBundle()
    for label, collector, target in (
        ("注册表卸载项", lambda: collect_uninstall(winreg_module), "uninstall"),
        ("自启动", lambda: collect_autostart(winreg_module), "autostart"),
    ):
        try:
            setattr(bundle, target, collector())
        except Exception as exc:  # X-1：单源失败不中断其余源
            bundle.errors.append(f"证据源 {label} 采集失败：{exc.__class__.__name__}: {exc}")
    unavailable = H1_TEXTS["evidence_unavailable_reason"]
    bundle.appx = AppxResult(available=False, reason=unavailable)
    bundle.processes = ProcessResult(available=False, reason=unavailable)
    bundle.services = ServiceResult(available=False, reason=unavailable)
    return bundle


def save_admin_report(
    html_text: str,
    *,
    reports_dir: str | None = None,
    now: datetime | None = None,
) -> str:
    """管理员模式报告落盘：先经 reports.save_report 守卫写入，再同目录改名加
    ``admin-`` 前缀（S-3 文件级可区分；写入位不变——U-2）。

    admin- 前缀名不匹配淘汰正则，不被普通 12 份淘汰删除（S-3 独立记录；
    清理策略归 T4-04/M3）。同秒冲突沿用 -N 序号，不覆盖既有报告。
    """
    saved = reports.save_report(html_text, reports_dir=reports_dir, now=now)
    directory = os.path.dirname(saved)
    stem, ext = os.path.splitext(os.path.basename(saved))
    target = os.path.join(directory, f"{ADMIN_REPORT_PREFIX}{stem}{ext}")
    sequence = 1
    while os.path.exists(target):
        target = os.path.join(directory, f"{ADMIN_REPORT_PREFIX}{stem}-{sequence}{ext}")
        sequence += 1
    os.rename(saved, target)
    return target


def write_done_marker(
    *,
    request_id: str,
    status: str,
    report_path: str | None,
    error: str | None = None,
    tmp_dir: str | None = None,
    now: datetime | None = None,
) -> str:
    """写完成标记 admin_rescan_done.json（T4-04 消费接口），返回标记路径。

    evidence_note 恒携带 R9 证据降级披露（接口字段，文案集中 texts）。
    """
    directory = tmp_dir if tmp_dir is not None else _default_tmp_dir()
    os.makedirs(directory, exist_ok=True)
    marker: dict = {
        "schema_version": DONE_SCHEMA_VERSION,
        "request_id": request_id,
        "mode": "admin",
        "status": status,
        "report_path": report_path,
        "finished_at": _utc_iso(now),
        "evidence_note": H1_TEXTS["evidence_note_r9"],
    }
    if error is not None:
        marker["error"] = error
    path = os.path.join(directory, DONE_FILENAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(marker, handle, ensure_ascii=False, indent=2)
    return path


def read_done_marker(*, tmp_dir: str | None = None) -> dict | None:
    """读完成标记（T4-04 消费接口）：缺失/损坏返回 None，不抛异常。"""
    directory = tmp_dir if tmp_dir is not None else _default_tmp_dir()
    try:
        with open(os.path.join(directory, DONE_FILENAME), encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _elevated_print(message: str) -> None:
    """提权实例控制台日志（SW_SHOWNORMAL 可见窗口即观察点；print 非自启动调用）。"""
    print(message, flush=True)


def mark_admin_report(report: dict) -> dict:
    """装配完成的报告 dict → 原地置 ``admin_mode=True`` 并返回（S-3/H4，T4-04）。

    仅提权实例装配链（``run_elevated_rescan`` 对注入 deps 的 judge 包装）调用；
    普通流水线（launcher.default_deps → judge_scan_result）不经本函数，报告不含
    该键——"输出结构可区分 + 不写普通记录键"。消费方以
    ``report.get("admin_mode") is True`` 判定（1.0 旧记录无键按非管理员处理，
    I3 联动预留）。独立记录三重区分的 dict 侧：另两项为文件名 admin- 前缀与
    done 标记 mode=admin；记录存储/对比管理归 I1/M3。
    """
    report[ADMIN_MODE_FIELD] = True
    return report


def _with_admin_judge(deps: object) -> object:
    """把注入 deps 的 judge 包装为"装配完成后置 admin_mode 标志"的版本（H4 透传）。

    兼容两种装配形态：frozen dataclass（launcher.AuditDeps 真实装配——
    dataclasses.replace 重建，不 import launcher，依赖倒置延续）与 duck 型替身
    （属性可写时原对象换 judge）。包装只在原 judge 装配完成后追加标志，不改变
    判定行为；judge 抛出异常时报告未产出、无标志可置（X-4 失败路径不变）。
    """
    judge = getattr(deps, "judge", None)
    if not callable(judge):
        return deps

    def admin_judge(scan: dict) -> dict:
        return mark_admin_report(judge(scan))

    try:
        return dataclasses.replace(deps, judge=admin_judge)  # type: ignore[arg-type]
    except TypeError:
        pass
    try:
        deps.judge = admin_judge  # type: ignore[attr-defined]
    except AttributeError:
        pass
    return deps


def run_elevated_rescan(
    *,
    audit: AuditPipeline,
    deps: object,
    tmp_dir: str | None = None,
    now: datetime | None = None,
) -> int:
    """提权实例编排（--elevated-rescan 分支本体；R9/防重生：本链路零自启动、零网络）。

    流程：一次性消费 spec（失败 → EXIT_BAD_REQUEST，不写 done）→ audit 流水线
    （launcher.execute_audit 同款：scan→judge→render→save=admin- 前缀→prune/open
    no-op）→ done 标记 → 退出码三态。audit/deps 双注入：编排不 import launcher
    （依赖倒置防循环），测试以替身全链覆盖。注入 deps 的 judge 经
    _with_admin_judge 包装——提权实例装配的报告携带 admin_mode=true（S-3/H4，
    T4-04；普通流水线不经过此包装，报告不含该键）。
    """
    try:
        request = read_rescan_request(tmp_dir=tmp_dir, now=now)
    except RescanRequestError as exc:
        _elevated_print(H1_TEXTS["elevated_rejected"].format(code=EXIT_BAD_REQUEST, reason=exc))
        return EXIT_BAD_REQUEST
    scope = str(request["scope"])
    _elevated_print(H1_TEXTS["elevated_started"].format(scope=scope))
    deps = _with_admin_judge(deps)  # H4/S-3：管理员模式标志注入（装配后置位）
    try:
        report_path = audit(scope, deps=deps)
    except Exception as exc:  # X-4 接口位：失败细节进 done 标记（T4-03 消费），不重试
        write_done_marker(
            request_id=str(request["request_id"]), status="failed", report_path=None,
            error=str(exc), tmp_dir=tmp_dir, now=now,
        )
        _elevated_print(H1_TEXTS["elevated_failed"].format(reason=exc))
        return EXIT_PIPELINE_FAILED
    if report_path is None:  # X-2 不完整出口（防御性：提权实例无中止源）
        write_done_marker(
            request_id=str(request["request_id"]), status="failed", report_path=None,
            error=H1_TEXTS["elevated_err_incomplete"], tmp_dir=tmp_dir, now=now,
        )
        _elevated_print(H1_TEXTS["elevated_failed"].format(reason=H1_TEXTS["elevated_err_incomplete"]))
        return EXIT_PIPELINE_FAILED
    write_done_marker(
        request_id=str(request["request_id"]), status="completed",
        report_path=str(report_path), tmp_dir=tmp_dir, now=now,
    )
    _elevated_print(H1_TEXTS["elevated_report_done"].format(path=report_path))
    return EXIT_OK
