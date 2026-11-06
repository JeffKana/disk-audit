"""对外文案资源（开发规范 §1：对外文案中文、集中在文案资源处，不散落硬编码）。

依据：方案 5.1（置信度四档输出措辞，逐字）、5.2（可再生两档表述，逐字）、
Q3（禁"可回收"字样与合并"可释放"总量）。供判定输出（judge）与报告渲染
（F2，S3）消费；措辞变更须与方案定稿同步（tests/test_engine_wording.py 对照表断言）。
"""
from __future__ import annotations

# 5.1 四档输出措辞（方案定稿表格原文；高档原为两短句"高度可能为残留"＋
# "删除前请确认"，输出串以"；"连接——连接符为呈现决定，短句逐字保留）
CONFIDENCE_WORDING: dict[str, str] = {
    "高": "高度可能为残留；删除前请确认",
    "中": "疑似残留，建议核对证据",
    "低": "归属未知，需人工判断",
    "受保护": "受保护，不可处理",
}

# 置信度档位（report-v1 schema 枚举键，非展示文案）→ POC-4 配色类
# （poc4_gen_bigreport.py 的 CLS 映射；键为 schema 数据值，放文案资源处统一维护）
CONFIDENCE_CSS_CLASSES: dict[str, str] = {
    "高": "hi",
    "中": "mid",
    "低": "low",
    "受保护": "prot",
}

# 高档两短句（与方案表格逐字对照用）
CONFIDENCE_HIGH_PARTS: tuple[str, str] = ("高度可能为残留", "删除前请确认")

# 5.2 两档表述（方案定稿原文）
REGENERABLE_WORDING = "可再生：应用会自行重建"
REGENERABLE_CONFIRM_WORDING = "可再生但需确认：清理后需重新下载，可能影响离线构建"

# =====================================================# F2 报告渲染文案（待办 F2，任务卡 T3-02；S3 追加区块——独立追加，勿改动上方既有内容）
# 依据：方案 E-2、5.1~5.3、Q3、X-2/C7、U-2/U-4、R10（零假设原则：措辞保守宁少说）、
# 产品待办 F2（概览/明细/证据链/建议动作四区）、POC-4 呈现基线。
# ============================================================

# 页眉（"只诊断，不动手"定位 + 脱敏提示）
REPORT_TITLE = "磁盘体检报告"
REPORT_MOTTO = "只诊断，不动手"
REPORT_PRIVACY_NOTICE = (
    "本报告包含本机目录路径与容量信息，属个人设备数据，仅供本机查看；"
    "如需分享请先自行处理其中的敏感内容。"
)
REPORT_OFFLINE_NOTICE = "本报告为离线静态页面，不加载任何网络资源，不提供任何操作按钮，不做任何修改或删除。"

# 四区标题（产品待办 F2）
REPORT_ZONE_OVERVIEW = "概览"
REPORT_ZONE_DETAILS = "明细"
REPORT_ZONE_EVIDENCE = "证据链"
REPORT_ZONE_ACTIONS = "建议动作"

# 元信息与概览字段（report-v1 totals 五字段；E-4/X-1：跳过统计必须披露，不得静默）
REPORT_LABEL_SCAN_ROOT = "扫描范围"
REPORT_LABEL_GENERATED_AT = "生成时间"
REPORT_LABEL_CANDIDATE_COUNT = "候选条目"
REPORT_UNIT_ITEMS = "条"
TOTALS_LABELS: dict[str, str] = {
    "allocated_bytes": "磁盘占用总量（占用空间口径）",
    "logical_bytes": "逻辑大小总量",
    "regenerable_subtotal": REGENERABLE_WORDING + "（小计）",
    "regenerable_confirm_subtotal": REGENERABLE_CONFIRM_WORDING + "（小计）",
    "skipped_entries": "未扫描/跳过条目数",
}

# 明细表列（E-2 候选七字段：六个进明细表列，"证据链"在证据链区展开呈现）
DETAIL_COLUMNS: dict[str, str] = {
    "path": "路径",
    "logical_bytes": "逻辑大小",
    "allocated_bytes": "占用空间",
    "confidence": "置信度",
    "verdict_source": "判定来源",
    "suggested_action": "建议动作",
}

# 证据链（5.3 A4：报告内展开，无外部调用）
EVIDENCE_SUMMARY_FMT = "查看证据链（{count} 条）"

# 建议动作（5.3 固定 5 种，不新增；报告只展示含义与分布，不提供任何操作入口）
ACTION_LEGEND_COLUMNS: tuple[str, ...] = ("编号", "动作", "含义")
ACTION_DISTRIBUTION_FMT = "{label}：{count} 条"
ACTION_LABELS: dict[str, str] = {
    "A1": "复制路径",
    "A2": "打开所在文件夹",
    "A3": "打开系统应用列表",
    "A4": "查看证据链",
    "A5": "无建议",
}
ACTION_DESCRIPTIONS: dict[str, str] = {
    "A1": "将该候选路径复制到剪贴板。",
    "A2": "在资源管理器中定位该目录。",
    "A3": "打开 Windows 的“应用和功能”设置页。",
    "A4": "在本报告内展开判定依据，无外部调用。",
    "A5": "受保护项与低置信项固定为无建议；本报告不提供任何处理入口。",
}
REPORT_ACTIONS_NOTE = "本报告只展示建议与依据，不执行任何操作；请人工核对证据后自行决定。"

# 不完整报告（X-2/C7：徽标 + 无汇总结论区）
INCOMPLETE_BADGE = "不完整报告"
INCOMPLETE_NOTE = (
    "本次扫描被中止或异常退出，以下仅为已采集的部分结果；"
    "汇总结论不可用，本报告不作为完整体检结论使用。"
)
INCOMPLETE_TOTALS_UNAVAILABLE = "汇总结论不可用（不完整报告不输出汇总数据）"

# 空态与大小单位（二进制口径 KB=1024 B，与资源管理器"占用空间"一致）
REPORT_NO_CANDIDATES = "（无候选条目）"
SIZE_UNITS: tuple[str, ...] = ("B", "KB", "MB", "GB", "TB")
SIZE_EXACT_FMT = "{total} 字节"

# 渲染输入校验异常（中文提示）
RENDER_ERR_NOT_OBJECT = "报告 JSON 顶层应为对象"
RENDER_ERR_MISSING_FIELDS = "报告 JSON 缺少必需字段：{fields}"
RENDER_ERR_BAD_VERSION = "不支持的报告 schema 版本：{version}（旧记录不可比，请使用对应版本的工具查看）"
RENDER_ERR_TOTALS_NOT_OBJECT = "报告 JSON totals 应为对象"
RENDER_ERR_CANDIDATES_NOT_LIST = "报告 JSON candidates 应为数组"
RENDER_ERR_CANDIDATE_NOT_OBJECT = "候选条目 #{index} 应为对象"
RENDER_ERR_CANDIDATE_MISSING = "候选条目 #{index} 缺少必需字段：{fields}"
RENDER_ERR_BAD_NUMBER = "报告数值字段不是合法整数"
# ======================================================================
# G1 启动器文案（T3-04；方案 P4 预设四目录 / P5 build 22621 门槛 / P6 置灰原因）。
# 本区块 append-only：Sprint 3 多分支并行修改本文件，新增文案一律向文末追加，
# 严禁改动上方既有键值（tests/test_engine_wording.py 对其逐字断言）。
# ======================================================================
LAUNCHER_TEXTS: dict[str, str] = {
    "window_title": "磁盘体检 · 选择扫描范围",
    "build_status_ok": "系统版本：Windows build {build}（满足最低要求 {min_build}）",
    "build_unsupported_title": "系统版本不支持",
    "build_unsupported": (
        "本程序仅支持 Windows 11 22H2（build 22621）及以上。\n"
        "当前系统 build 为 {build}，低于最低要求 {min_build}，程序即将退出。"
    ),
    "scope_group": "扫描范围",
    "preset_label_appdata": "当前用户漫游数据（%APPDATA%）",
    "preset_label_localappdata": "当前用户本地数据（%LOCALAPPDATA%）",
    "preset_label_programdata": "全机共享数据（%PROGRAMDATA%）",
    "preset_label_programfiles": "程序安装目录（C:\\Program Files）",
    "custom_option": "自定义文件夹",
    "custom_browse": "浏览…",
    "drives_group": "磁盘驱动器（仅固定本地盘支持扫描）",
    "drive_fixed": "固定本地盘",
    "drive_reason_removable": "可移动盘：仅支持固定本地盘",
    "drive_reason_remote": "网络盘：仅支持固定本地盘",
    "drive_reason_cdrom": "光驱：仅支持固定本地盘",
    "drive_reason_ramdisk": "RAM 盘：仅支持固定本地盘",
    "drive_reason_unknown": "无法识别的盘型：仅支持固定本地盘",
    "start_button": "开始体检",
    "status_no_selection": "尚未选择扫描范围，请先在上方选择",
    "status_selected": "已选择扫描范围：{path}；扫描功能将在后续版本接入",
    "status_missing_folder": "所选文件夹不存在，请重新选择",
}

# =====================================================#
# F5 报告筛选文案（待办 F5，任务卡 T3-03；S3 追加区块——独立追加，勿改动上方既有内容）
# 依据：方案第六节性能预算（5000 行 ≤5MB / 首屏 ≤1s / 筛选 ≤150ms）、POC-4
# 筛选基线（原生 JS display 切换，poc4_gen_bigreport.py）、U-2/U-4（纯展示
# 页面：input 为文本筛选框非按钮，不提供任何处理动作）、R10（零假设原则）。
# ============================================================
REPORT_FILTER_LABEL = "筛选"
REPORT_FILTER_PLACEHOLDER = "输入路径关键词，如 tencent"
REPORT_FILTER_COUNT_FMT = "共 {count} 行"
REPORT_FILTER_MATCHED_FMT = "筛选后 {count} 行"
# ======================================================================
# T3-07 证据来源枚举与渲染拒绝文案（08 报告 §3 裁决 1；P1 热修）。
# 本区块 append-only：Sprint 3 多分支并行修改本文件，新增文案一律向文末追加，
# 严禁改动上方既有内容。
# ======================================================================
# 证据来源九值枚举：逐字取自 docs/schemas/report-v1.schema.json 定稿
# $defs.candidate.properties.evidence_chain.items.properties.source.enum
# （六源 + 判定层三源，见 report-v1-字段对照表）；与 schema 的一致性由
# tests/test_engine_render.py::test_evidence_source_enum_matches_schema 守卫。
EVIDENCE_SOURCE_ENUM: tuple[str, ...] = (
    "硬保护", "知识库", "注册表卸载项", "进程", "服务", "自启动",
    "Appx", "启发式", "文件枚举",
)
# 渲染输入校验：证据链 source 不在九值枚举 → 拒绝渲染并披露
# （拒绝并披露优于静默渲染；含非法值与期望枚举提示）
RENDER_ERR_BAD_EVIDENCE_SOURCE = (
    "候选条目 #{index} 证据链第 {position} 条证据来源非法：{source}"
    "（合法来源为：{expected}）"
)
# G3 结果入口文案（T3-06；方案四节架构⑤"静态 HTML · 默认浏览器打开"、M2 闸①
# "双击到看到报告 ≤3 步"）。本区块 append-only：新增文案一律向文末追加，
# 严禁改动上方既有键值。
# ======================================================================
G3_TEXTS: dict[str, str] = {
    "status_scanning": "正在体检：{path}；完成后报告将自动在默认浏览器打开",
    "status_report_opened": "体检完成，报告已保存并在默认浏览器打开：{path}",
    "status_audit_failed": "体检未完成：{reason}",
    "reports_err_bad_filename": "报告文件名不合法：{filename}",
    "reports_err_outside_dir": "报告写入路径越界，已拒绝写入：{target}",
    "reports_err_bad_keep": "报告保留份数必须为正整数：{keep}",
}

# ======================================================================
# G2 进度与中止文案（T3-05；方案 E-1 实时进度 / X-2·C7 不完整出口 / R10 零假设）。
# 本区块 append-only：新增文案一律向文末追加，严禁改动上方既有键值。
# 进度三字段取 E-1 口径（已扫描条目数 / 当前路径 / 已用时）；
# 中止路径不生成报告文件，横幅如实披露（"未生成报告"）。
# ======================================================================
G2_TEXTS: dict[str, str] = {
    "progress_group": "体检进度",
    "progress_status": "已扫描 {entries} 项 · 已用时 {seconds} 秒",
    "progress_current_path": "当前路径：{path}",
    "abort_button": "中止体检",
    "status_aborting": "正在中止，请稍候…",
    "status_incomplete": "体检未完成：结果不完整，未生成报告。",
    "incomplete_banner": (
        "不完整报告：本次体检已中止或未完成，已扫描的部分结果不作为体检结论，"
        "未生成报告文件；可选择扫描范围后重新发起体检。"
    ),
}

# ======================================================================
# B3 系统交互白名单文案（待办 B3，任务卡 T4-05；方案 U-4 / 5.3 A1~A3）。
# 本区块 append-only：新增文案一律向文末追加，严禁改动上方既有键值。
# 越权拒绝披露文案：明确说出被拒目标与白名单边界（任务卡验收②"拒绝并披露"）。
# ======================================================================
B3_TEXTS: dict[str, str] = {
    "b3_err_rejected": "已拒绝系统交互：{target} 不在白名单内（仅允许：定位文件、打开应用列表、复制路径）。",
    "b3_err_empty_path": "已拒绝系统交互：定位文件需要非空路径。",
    "b3_err_clipboard_alloc": "剪贴板写入失败：内存分配失败。",
    "b3_err_clipboard_lock": "剪贴板写入失败：内存锁定失败。",
    "b3_err_clipboard_open": "剪贴板写入失败：剪贴板被其他程序占用，请稍后重试。",
    "b3_err_clipboard_set": "剪贴板写入失败：系统拒绝了写入请求。",
}

# ======================================================================
# F4 建议动作接线文案（待办 F4，任务卡 T4-07；方案 5.3 / U-4 / X2 / E-5）。
# 本区块 append-only：新增文案一律向文末追加，严禁改动上方既有键值。
# 依据：方案 5.3（A1~A5 固定 5 种，动作名复用 ACTION_LABELS 单一措辞源）、
# U-4/X2（A1~A3 为白名单可执行动作，经 disk_audit.system_actions 执行）、
# E-5 风格（拒绝/失败仅状态栏披露，不弹错误框；沿 G2 状态栏先例）、
# R10（零假设：A5 语义只陈述"无建议、不提供处理入口"，不出现"下一步"）。
# ======================================================================
F4_TEXTS: dict[str, str] = {
    "actions_group": "建议动作",
    "candidate_none": "（尚无可操作候选：完成一次体检后，此处列出本次结果中可执行建议动作的候选）",
    "candidate_item_fmt": "{path}（{confidence} · {source}）",
    "no_operable": "本次结果没有可执行建议动作的候选；受保护项与低置信项固定无建议，不提供任何处理入口。",
    "no_candidate_selected": "请先在列表中选择一个候选，再点击动作按钮。",
    "a4_hint": "查看证据链（A4）：请在已打开报告的“证据链”区点击对应候选展开——报告内展开，无外部调用。",
    "status_copied": "已复制路径到剪贴板：{path}",
    "status_located": "已在资源管理器中定位（所在文件夹已打开并高亮）：{path}",
    "status_settings_opened": "已打开系统应用列表（设置 → 应用），卸载等操作请在该页面人工进行。",
    "status_action_failed": "该动作未能完成：{reason}",
    "status_unknown_action": "动作 {action} 不通过本界面执行。",
    "actions_note": (
        "仅列出建议动作为 A1~A3 的高/中置信候选；受保护项与低置信项固定无建议，"
        "不提供任何处理入口。动作经系统交互白名单执行（仅：复制路径、定位文件、"
        "打开应用列表），本界面不做任何修改或删除。"
    ),
}





# ======================================================================
# F3 CSV 导出与脱敏文案（待办 F3，任务卡 T4-06；方案 P7、第八节"脱敏"：
# 四类 = 当前用户名 / 计算机名 / 用户 SID / 其他用户目录名；CSV 默认脱敏，
# 显式 --raw 才出原文；分享提示在导出完成态展示）。
# 本区块 append-only：新增文案一律向文末追加，严禁改动上方既有键值。
# ======================================================================

# 脱敏占位符（固定字面量：脱敏输出可全文检索，四类互不覆盖）
SANITIZE_PLACEHOLDERS: dict[str, str] = {
    "user": "<用户名>",
    "computer": "<计算机名>",
    "sid": "<SID>",
    "other_user": "<其他用户>",
}

# CSV 表头（仅数据列：路径/大小双口径/置信度/来源/建议动作；无证据链全文——
# 任务卡"控体量"约束。字节取整数便于 Excel 排序，列名标注单位）
CSV_HEADERS: dict[str, str] = {
    "path": "路径",
    "logical_bytes": "逻辑大小（字节）",
    "allocated_bytes": "占用空间（字节）",
    "confidence": "置信度",
    "verdict_source": "判定来源",
    "suggested_action": "建议动作",
}

# 完成态与分享提示（R10 零假设原则：raw 模式提示升级为明确"未脱敏"警示）
F3_TEXTS: dict[str, str] = {
    "csv_done_default": "导出完成（已脱敏）：{path}",
    "csv_share_notice": "注意：报告含本机路径，对外分享前请确认脱敏符合预期。",
    "csv_done_raw": "导出完成（未脱敏）：{path}",
    "csv_share_notice_raw": (
        "警示：本次导出未脱敏，文件含用户名/计算机名/SID 等本机原文，"
        "对外分享前务必自行确认并处理敏感信息。"
    ),
    "csv_err_read": "无法读取报告文件：{exc}",
    "csv_err_json": "报告文件不是合法 JSON：{exc}",
    "csv_err_encode": "报告文件不是 UTF-8 编码：{exc}",
    "csv_err_not_object": "报告 JSON 顶层应为对象",
    "csv_err_missing_fields": "报告 JSON 缺少必需字段：{fields}",
    "csv_err_candidates_not_list": "报告 JSON candidates 应为数组",
    "csv_err_candidate_not_object": "候选条目 #{index} 应为对象",
    "csv_err_candidate_missing": "候选条目 #{index} 缺少导出必需字段：{fields}",
    "csv_err_bad_number": "报告数值字段不是合法整数",
    "csv_err_bad_filename": "CSV 文件名不合法：{filename}",
    "csv_err_outside_dir": "CSV 写入路径越界，已拒绝写入：{target}",
}

# ======================================================================
# H1 以管理员身份重扫文案（T4-01；方案 Q6/E-4/U-3/R9/S-3）。
# 本区块 append-only：新增文案一律向文末追加，严禁改动上方既有键值。
# 依据：E-4 入口文案取方案原文"以管理员身份重扫"；R9 披露口径"该证据源不可用"
# （方案四节 UWP 行降级披露先例）；E-5 取消/失败 UX 归 T4-02/T4-03，本卡文案
# 仅覆盖"已发起"事实与提权实例控制台日志、spec 校验错误。
# ======================================================================
H1_TEXTS: dict[str, str] = {
    "admin_rescan_button": "以管理员身份重扫",
    "status_admin_launched": (
        "管理员重扫已发起：请在 UAC 提示中选择“是”；提权实例将以管理员模式重新扫描，"
        "并在 reports\\ 目录生成以 admin- 开头的独立报告。"
    ),
    "cli_help_elevated": (
        "提权实例入口：消费 tmp\\spec.json 请求并以管理员模式重扫"
        "（仅由提权重启自身使用，不在界面中出现）"
    ),
    "elevated_started": "管理员模式重扫开始：{scope}",
    "elevated_report_done": "管理员模式报告已生成：{path}",
    "elevated_failed": "管理员重扫失败：{reason}",
    "elevated_rejected": "管理员重扫请求被拒绝（退出码 {code}）：{reason}",
    "elevated_err_incomplete": "扫描未完整（中止/异常出口），不生成体检结论",
    "spec_err_missing": "管理员重扫请求缺失或已被消费，拒绝执行：{path}",
    "spec_err_corrupt": "管理员重扫请求文件无法解析：{path}",
    "spec_err_invalid": "管理员重扫请求不合法：{reason}",
    "evidence_unavailable_reason": "提权模式不执行外部程序（R9），该证据源不可用",
    "evidence_note_r9": (
        "管理员模式：Appx/进程/服务三个证据源需调用外部程序（powershell）采集，"
        "按 R9 硬约束在提权实例中不采集，相应判定证据降级。"
    ),
}



# ======================================================================
# H2 UAC 取消处理文案（T4-02；方案 E-5）。
# 本区块 append-only：新增文案一律向文末追加，严禁改动上方既有键值。
# E-5 定稿口径：UAC 取消 → 保留原报告、不重试、不弹错误框，仅提示
# "已取消，结果未变更"——取消文案保留 E-5 原文短语，走非阻塞状态栏（G2 先例）。
# 发起失败（ShellExecuteW ≤32 且非 ERROR_CANCELLED）走独立文案并如实披露返回码，
# 不冒充取消；X-4"管理员重扫失败，已保留上次结果"完整失败语义归 T4-03（H3），
# 届时可细化该文案。
# ======================================================================
H2_TEXTS: dict[str, str] = {
    "status_admin_cancelled": "管理员重扫已取消，结果未变更。",
    "status_admin_launch_failed": "管理员重扫未能发起（返回码 {code}），结果未变更。",
}
