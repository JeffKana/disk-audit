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

# 高档两短句（与方案表格逐字对照用）
CONFIDENCE_HIGH_PARTS: tuple[str, str] = ("高度可能为残留", "删除前请确认")

# 5.2 两档表述（方案定稿原文）
REGENERABLE_WORDING = "可再生：应用会自行重建"
REGENERABLE_CONFIRM_WORDING = "可再生但需确认：清理后需重新下载，可能影响离线构建"

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
