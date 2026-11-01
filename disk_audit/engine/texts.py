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

# ======================================================================
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
