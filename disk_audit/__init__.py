"""磁盘体检（disk-audit）—— 只诊断，不动手。

运行时零第三方依赖（仅 CPython 标准库）；CI 校验 import 白名单。
方案基线：《磁盘体检 · v0.1 方案（定稿 F1）》2026-10-23。
"""

__version__ = "0.1.0.dev0"

import os

# 本程序自身唯一允许写入的位置（U-2）
DATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\DiskAudit")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")   # 报告
RECORDS_DIR = os.path.join(DATA_DIR, "records")   # 体检记录
TMP_DIR = os.path.join(DATA_DIR, "tmp")           # 临时规格文件（如提权重扫 spec.json）
