# -*- coding: utf-8 -*-
r"""
AppData 残留候选识别原型 v0.1
================================
输入:
  1. TreeSize 导出的 AppData\Roaming / AppData\Local 顶层目录 CSV
  2. 本机证据 JSON (uninstall / appx / processes / services / runkeys, 由 01-03 号 PowerShell 采集)
输出:
  1. output/AppData残留候选分析.csv  —— 逐目录分类清单(归属/分类/建议/置信度/证据)
  2. prototype/summary.json          —— 汇总统计(供调研报告引用)
判定优先级:
  硬保护规则(系统/兼容链接) > 知识库(KB) > 注册表卸载项 > 运行进程/服务 > 商店包 > 启发式(哈希名/陈旧度)
"""
import csv, json, os, re, sys
from datetime import datetime

BASE = r'C:\Users\querkecor\WorkBuddy\电脑磁盘清理大师'
PROTO = os.path.join(BASE, 'prototype')
OUT = os.path.join(BASE, 'output')
os.makedirs(OUT, exist_ok=True)

ROAMING_CSV = r'C:\Users\querkecor\Desktop\乔夫卡那_C_Roaming_详细信息.csv'
LOCAL_CSV = r'C:\Users\querkecor\Desktop\乔夫卡那_C_Local_详细信息.csv'
APPDATA = os.environ.get('APPDATA') or r'C:\Users\querkecor\AppData\Roaming'
LOCALAPPDATA = os.environ.get('LOCALAPPDATA') or r'C:\Users\querkecor\AppData\Local'

NOW = datetime(2026, 10, 23)
STALE_DAYS = 540  # 约 18 个月未修改 → 视为"陈旧"

# ---------------- 分类常量 ----------------
CAT_SYS   = '系统组件'
CAT_LINK  = '兼容链接·严禁删除'
CAT_INST  = '已安装应用'
CAT_ACTIVE= '使用中(无安装记录)'
CAT_UPD   = '更新缓存'
CAT_DEV   = '开发缓存'
CAT_CACHE = '缓存/转储'
CAT_GAME  = '游戏数据'
CAT_ORPH_H= '残留候选·高置信'
CAT_ORPH_M= '残留候选·中置信'
CAT_ORPH_L= '残留候选·低置信'
CAT_CONT  = '容器(已下钻)'

ADVICE = {
    CAT_SYS: '保留(勿动)', CAT_LINK: '严禁删除',
    CAT_INST: '保留', CAT_ACTIVE: '保留',
    CAT_UPD: '可清理(会自动重建)', CAT_DEV: '可清理(按需重建)',
    CAT_CACHE: '可清理', CAT_GAME: '视游戏去留人工确认',
    CAT_ORPH_H: '人工确认后删除', CAT_ORPH_M: '人工确认后删除', CAT_ORPH_L: '先查明归属再决定',
    CAT_CONT: '见下钻明细',
}

# ---------------- 工具函数 ----------------
def parse_size_mb(s):
    s = (s or '').strip()
    if not s: return 0.0
    if s.endswith('字节'):
        num = s[:-2].strip().replace(',', '')
        try: return float(num or 0) / (1024 * 1024)
        except ValueError: return 0.0
    for unit, mult in (('TB', 1024*1024), ('GB', 1024), ('MB', 1), ('KB', 1/1024)):
        if s.endswith(' ' + unit):
            num = s[:-(len(unit)+1)].replace(',', '')
            try: return float(num) * mult
            except ValueError: return 0.0
    return 0.0

def parse_date(s):
    s = (s or '').strip()
    for fmt in ('%Y/%m/%d', '%Y/%m/%d %H:%M'):
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    return None

def load_treesize_csv(path, root_label, root_path):
    rows = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        lines = f.read().splitlines()
    hdr_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith('名称,'):
            hdr_idx = i; break
    if hdr_idx is None:
        raise RuntimeError('未找到表头: ' + path)
    reader = csv.reader(lines[hdr_idx:])
    next(reader)  # header
    for rec in reader:
        if len(rec) < 8 or not rec[0].strip(): continue
        rows.append({
            'root': root_label, 'root_path': root_path,
            'name': rec[0].strip(),
            'size_mb': parse_size_mb(rec[1]),
            'files': int(rec[3] or 0),
            'dirs': int(rec[4] or 0),
            'mtime': parse_date(rec[6]),
            'owner': rec[8].strip() if len(rec) > 8 else '',
        })
    return rows

def load_json(name):
    p = os.path.join(PROTO, name)
    if not os.path.exists(p): return None
    with open(p, 'r', encoding='utf-8-sig') as f:
        return json.load(f)

def norm(s):
    """小写并去掉非字母数字/中文"""
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '', (s or '').lower())

def extract_path(s):
    """从命令行/服务路径串中提取第一个 Windows 绝对路径"""
    m = re.search(r'[A-Za-z]:\\[^\s"]+', (s or ''))
    return m.group(0).lower() if m else ''

# ---------------- 证据加载 ----------------
ev_uninst = load_json('uninstall.json') or []
ev_appx   = load_json('appx.json') or []
ev_procs  = load_json('processes.json') or []
ev_svcs   = load_json('services.json') or []
ev_runs   = load_json('runkeys.json') or []
if isinstance(ev_uninst, dict): ev_uninst = [ev_uninst]
if isinstance(ev_appx, str):    ev_appx = [ev_appx]
if isinstance(ev_procs, str):   ev_procs = [ev_procs]
if isinstance(ev_svcs, str):    ev_svcs = [ev_svcs]
if isinstance(ev_runs, dict):   ev_runs = [ev_runs]

# 注册表应用语料库
apps = []
for u in ev_uninst:
    d = (u.get('display') or '').strip()
    if not d: continue
    apps.append({
        'display': d, 'pub': (u.get('pub') or '').strip(),
        'loc': (u.get('loc') or '').strip(),
        'icon': (u.get('icon') or '').strip(),
        'nd': norm(d), 'np': norm(u.get('pub')),
    })

# 活动路径集合 (进程 / 服务 / 自启动)
active_paths = set()
for p in ev_procs:
    if p: active_paths.add(p.lower())
for s in ev_svcs:
    p = extract_path(s)
    if p: active_paths.add(p)
for r in ev_runs:
    p = extract_path(r.get('c', ''))
    if p: active_paths.add(p)

appx_norm = set(norm(a) for a in ev_appx if a)
appx_raw_l = set(a.lower() for a in ev_appx if a)

# ---------------- 知识库 (针对本机观测到的目录名) ----------------
# 条目: 名称(小写) -> (归属, 分类, 置信度, 说明)
KB_ROAM = {
    'sun': ('旧版 Sun Java(JRE/JDK)', CAT_ORPH_H, '高', 'Sun 品牌早已并入 Oracle,目录名 Sun 常为多年前 Java 残留'),
    'winrar': ('WinRAR', CAT_INST, '高', '压缩软件配置;若已卸载则为残留'),
    'tpdownloadproxy': ('下载组件(疑似迅雷系)', CAT_ORPH_M, '中', 'TP=ThunderPlatform 相关代理组件'),
    'chat_pp': ('捆绑推广组件', CAT_ORPH_H, '高', '与 360safe/鲁大师/Ludashi/lds/dzip_pp/tabx_pp/DrvMgr 同日(2023-04-08)植入,典型全家桶痕迹'),
    'dzip_pp': ('捆绑推广组件', CAT_ORPH_H, '高', '同上,2023-04-08 批量植入'),
    'tabx_pp': ('捆绑推广组件', CAT_ORPH_H, '高', '同上,2023-04-08 批量植入'),
    'drvmgr': ('捆绑推广组件(驱动管理类)', CAT_ORPH_H, '高', '同上,2023-04-08 批量植入'),
    '360safe': ('360安全卫士', CAT_ORPH_H, '高', '2023-04-08 植入,现已无安装记录'),
    'lds': ('捆绑推广组件', CAT_ORPH_H, '高', '同日植入的推广族'),
    'ludashi': ('鲁大师', CAT_ORPH_H, '高', '2023-04-08 植入'),
    'yxqxunyou': ('迅游系加速器推广组件', CAT_ORPH_M, '中', '2023-08 出现'),
    'firaxislive': ('《文明》系列(FiraxisLive)', CAT_GAME, '中', ' Firaxis 游戏在线组件'),
    'goldberg steamemu saves': ('Goldberg Steam 模拟器存档', CAT_ORPH_M, '中', '学习版游戏联机模拟器存档'),
    'electron': ('Electron 框架运行缓存', CAT_CACHE, '中', '由各 Electron 应用运行时生成'),
    'thunderx': ('迅雷X', CAT_ORPH_M, '中', '迅雷旧版本数据'),
    'thunder': ('迅雷', CAT_ORPH_M, '中', '迅雷下载器数据'),
    'xmp': ('迅雷影音(XMP)', CAT_ORPH_M, '中', '迅雷播放器'),
    'coreavc.ini': ('CoreAVC 解码器配置', CAT_ORPH_H, '高', '解码器配置文件残留'),
    'nuget': ('NuGet(Visual Studio)包缓存', CAT_DEV, '高', ''),
    'alixby': ('小白羊云盘(开源阿里云盘客户端)', CAT_ORPH_H, '高', '项目 2023 年已停止维护'),
    'rtsubscribe': ('Realtek 订阅组件', CAT_ORPH_M, '中', '驱动相关'),
    'visual studio setup': ('Visual Studio 安装器', CAT_INST, '高', 'VS 安装状态目录'),
    'ip_royal_paws': ('IPRoyal Pawns(闲置带宽共享)', CAT_ORPH_M, '中', '带宽变现应用'),
    'qq_guild': ('QQ频道', CAT_ORPH_H, '高', '腾讯 QQ频道服务已下线'),
    'cc': ('归属不明(疑似网易CC/Adobe CC)', CAT_ORPH_L, '低', '名称过于简短,需人工确认'),
    'third_wpsdc': ('WPS 第三方组件', CAT_ORPH_M, '中', 'wpsdc=WPS 数据组件'),
    'ecloudupgrade': ('天翼云盘升级组件', CAT_ORPH_M, '中', 'eCloud=天翼云'),
    'telegram a': ('Telegram(变体客户端)', CAT_INST, '中', 'Telegram A 为第三方改版'),
    'daum': ('Daum(PotPlayer/Kakao)', CAT_ORPH_M, '中', '韩国 Daum 系软件'),
    'sekiro': ('《只狼》游戏数据', CAT_GAME, '中', '存档/配置'),
    'openark': ('OpenArk(安全工具)', CAT_ORPH_M, '中', '若仍在使用请保留'),
    'intellijidea': ('IntelliJ IDEA 配置', CAT_DEV, '高', 'JetBrains IDE'),
    'btlog': ('BT 下载日志', CAT_ORPH_M, '中', '疑似比特彗星/迅雷 BT 日志'),
    'tdm': ('迅雷下载管理(TDM)', CAT_ORPH_M, '中', '归属不确切'),
    'd3d5d3c0-0f3d-40c1-9973-ceb7c072ae32.ini': ('GUID 配置残留', CAT_ORPH_H, '高', '组件 GUID 命名的 ini'),
    'paradox interactive': ('P社游戏(城市天际线等)', CAT_GAME, '中', ''),
    'paradox-launcher-v2': ('Paradox 启动器 v2', CAT_GAME, '中', 'P社游戏通用启动器'),
    'renpy': ('RenPy 引擎游戏存档', CAT_GAME, '中', '视觉小说类游戏'),
    'another-redis-desktop-manager': ('Another Redis Desktop Manager', CAT_INST, '中', 'Redis 可视化工具'),
    'updater': ('泛用更新器(归属不明)', CAT_ORPH_L, '低', '需人工确认'),
    'aclos': ('归属不明', CAT_ORPH_L, '低', '46MB,125 个文件,建议人工排查内容'),
    'systemkeys': ('归属不明', CAT_ORPH_L, '低', ''),
    'yylive': ('YY直播', CAT_ORPH_M, '中', '欢聚时代'),
    'voipnnmodel': ('通话降噪 AI 模型', CAT_SYS, '中', '钉钉/会议类应用共用组件,建议保留'),
    'dinglive': ('钉钉直播组件', CAT_INST, '中', '随钉钉重建'),
    'wns': ('腾讯 WNS 推送通道', CAT_INST, '中', '腾讯系应用共用'),
    'github cli': ('GitHub CLI(gh)', CAT_DEV, '高', '命令行工具'),
    'asus_framework': ('华硕主板/奥创组件', CAT_SYS, '中', '驱动框架'),
    'xlgame': ('迅雷游戏', CAT_ORPH_M, '中', ''),
    'jupyter': ('Jupyter 配置', CAT_DEV, '高', ''),
    'geek uninstaller': ('Geek Uninstaller(便携工具)', CAT_ACTIVE, '中', '绿色软件,注册表无卸载记录——体现"便携应用盲区"'),
    'kwallpaper_sogou': ('搜狗壁纸(推广组件)', CAT_ORPH_M, '中', '搜狗输入法系推广'),
    'kdesk': ('K桌面(归属不明)', CAT_ORPH_L, '低', ''),
    'luna_pc': ('归属不明', CAT_ORPH_L, '低', '疑似壁纸/直播类'),
    'tidalab': ('归属不明', CAT_ORPH_L, '低', '292MB!604 个文件,建议人工排查'),
    'lghub_bkp': ('罗技 G HUB 备份', CAT_ORPH_M, '中', 'LGHUB 配置备份'),
    'nextjs-nodejs': ('Next.js 编译缓存', CAT_DEV, '高', ''),
    'contextmanager': ('Windows 右键菜单管理工具', CAT_ACTIVE, '中', '便携工具'),
    'xmagic': ('剪映/字节特效引擎(xmagic)', CAT_INST, '中', '抖音系引擎组件'),
    'com.example': ('示例包名(调试残留)', CAT_ORPH_M, '中', 'com.example 为默认包名'),
    'cilizhai_pc': ('归属不明(次梨宅?)', CAT_ORPH_L, '低', ''),
    'tdcoresk': ('归属不明(疑似迅雷系)', CAT_ORPH_L, '低', ''),
    'plogs': ('日志', CAT_ORPH_L, '低', ''),
    'icreate-pc-lol': ('iCreate 英雄联盟辅助', CAT_ORPH_M, '中', 'LOL 教练/辅助类'),
    'lolaicoach': ('LOL AI 教练', CAT_ORPH_M, '中', ''),
    'systembeautify': ('系统美化工具', CAT_ORPH_M, '中', ''),
    'zcode': ('归属不明(疑似 AI 编程工具)', CAT_ORPH_L, '低', ''),
    'dsh desktop': ('WorkBuddy/DSH 桌面端', CAT_INST, '中', '腾讯系桌面应用(当前生态)'),
    'setting.json': ('游离配置文件', CAT_ORPH_L, '低', '根目录散落配置'),
    'wxdrive': ('微信文件/网盘组件', CAT_INST, '中', 'WXDrive=微信盘'),
    'awesun': ('AweSun 远程控制', CAT_ORPH_M, '中', 'AweRay 出品'),
    'jam software': ('TreeSize(JAM Software)', CAT_ACTIVE, '高', '用户正在使用的磁盘分析工具'),
    'com.qytapp.clients.apex': ('qyt 客户端', CAT_ORPH_L, '低', '包名式命名'),
    'utforpc': ('归属不明(疑似加速器)', CAT_ORPH_L, '低', ''),
    'isgpet': ('归属不明', CAT_ORPH_L, '低', ''),
    'mssdk': ('归属不明(疑似微软/MSDK)', CAT_ORPH_L, '低', ''),
    'baiduyunkernel': ('百度网盘内核', CAT_INST, '中', ''),
    'baiduyunguanjia': ('百度网盘管家', CAT_ORPH_M, '中', ''),
    'ichat': ('归属不明(疑似 IM 类)', CAT_ORPH_L, '低', ''),
    'hideandseek': ('归属不明', CAT_ORPH_L, '低', ''),
    'doubao': ('豆包(字节 AI 助手)', CAT_INST, '中', ''),
    'pixcake-qt_pro': ('PixCake 修图软件', CAT_INST, '中', ''),
    'unrealenginelauncher': ('虚幻引擎启动器', CAT_GAME, '中', ''),
    'code': ('Visual Studio Code 用户数据', CAT_INST, '高', 'VS Code 配置/工作区缓存;程序本体在 Local\\Programs'),
}

KB_LOCAL = {
    'xweb_webview': ('微信内置浏览器(XWeb)内核', CAT_SYS, '中', '微信运行依赖'),
    'main.kts.compiled.cache': ('Kotlin 脚本编译缓存', CAT_DEV, '高', ''),
    'yodao': ('网易有道词典/云笔记', CAT_INST, '中', ''),
    'resmon.resmoncfg': ('资源监视器配置(系统)', CAT_SYS, '高', ''),
    'crashrpt': ('CrashRpt 崩溃报告库', CAT_CACHE, '中', '崩溃转储通用组件'),
    'flingtrainer': ('FLiNG 游戏修改器', CAT_ORPH_M, '中', '单机游戏修改器'),
    'firaxis games': ('《文明》系列(Firaxis)', CAT_GAME, '中', ''),
    'xbyyunpan-updater': ('小白羊云盘更新缓存', CAT_UPD, '高', '已停更项目的更新包'),
    'xmind-vana-updater': ('XMind 更新缓存', CAT_UPD, '高', 'Electron 更新下载包'),
    'dundiemu': ('蹲地模拟器(GBA 模拟器)', CAT_GAME, '中', ''),
    'microsoft sdks': ('Microsoft SDK 缓存', CAT_DEV, '高', ''),
    'azurefunctionstools': ('VS Azure Functions 工具缓存', CAT_DEV, '高', '603MB,VS 扩展缓存'),
    'identitynexusintegration': ('归属不明', CAT_ORPH_L, '低', ''),
    'isolatedstorage': ('.NET 隔离存储(系统)', CAT_SYS, '高', ''),
    'cisco packet tracer': ('Cisco Packet Tracer', CAT_INST, '中', '思科网络模拟器'),
    'mindjet': ('MindManager(Mindjet)', CAT_INST, '中', '思维导图'),
    'vmware': ('VMware', CAT_INST, '高', ''),
    'oobelibmkey.log': ('系统 OOBE 库日志', CAT_SYS, '高', ''),
    'fenv': ('归属不明', CAT_ORPH_L, '低', ''),
    'node-gyp': ('node-gyp 编译缓存', CAT_DEV, '高', ''),
    'diagnostics': ('系统诊断', CAT_SYS, '高', ''),
    '.identityservice': ('系统账户服务数据', CAT_SYS, '高', '微软账户令牌'),
    'qq-chat-updater': ('QQ 更新缓存', CAT_UPD, '高', ''),
    'unicompactview': ('Uni 系组件(疑似联想软件)', CAT_ORPH_M, '中', ''),
    'unisdk': ('Uni SDK(疑似联想软件)', CAT_ORPH_M, '中', ''),
    'pypa': ('Python 打包机构(pypa)缓存', CAT_DEV, '高', ''),
    'scikit-image': ('scikit-image 示例数据', CAT_DEV, '高', ''),
    'apps': ('系统应用数据容器', CAT_SYS, '中', ''),
    'sararesults': ('微软支持恢复助手(SARA)结果', CAT_SYS, '高', 'Support and Recovery Assistant'),
    'saralogs': ('微软支持恢复助手日志', CAT_SYS, '高', ''),
    'elevateddiagnostics': ('系统提权诊断', CAT_SYS, '高', ''),
    'apifox-updater': ('Apifox 更新缓存', CAT_UPD, '高', ''),
    'inethistory': ('系统 IE 历史(兼容)', CAT_SYS, '高', ''),
    'battleye': ('BattlEye 反作弊', CAT_GAME, '中', '游戏反作弊组件'),
    'wellbia': ('XIGNCODE3 反作弊(WELLBIA)', CAT_GAME, '中', '韩国反作弊'),
    'cgslb_transvod.json': ('腾讯 CDN 调度缓存', CAT_CACHE, '中', '直播/视频 SDK 拉流调度'),
    'cgslb_jodns.json': ('腾讯 CDN 调度缓存', CAT_CACHE, '中', ''),
    'draco_d79f909d.json': ('Draco 3D 解码缓存', CAT_CACHE, '中', 'web 3D 压缩库'),
    'virtualstore': ('UAC 文件虚拟化(系统)', CAT_SYS, '高', '重定向旧程序写入'),
    'b1': ('归属不明', CAT_ORPH_L, '低', '601MB!39 个文件,建议人工排查'),
    'sports interactive': ('足球经理(FM)', CAT_GAME, '中', ''),
    'quarkupdater': ('夸克网盘更新器', CAT_INST, '中', ''),
    'application data': ('XP 兼容 Junction', CAT_LINK, '高', '指向自身的目录链接,删除会破坏兼容性'),
    'history': ('XP 兼容 Junction', CAT_LINK, '高', '同上'),
    'temporary internet files': ('XP 兼容 Junction', CAT_LINK, '高', '同上'),
    'another-redis-desktop-manager-updater': ('Another Redis Desktop Manager 更新缓存', CAT_UPD, '高', ''),
    'epic games': ('Epic 平台数据', CAT_GAME, '高', ''),
    'epicgameslauncher': ('Epic 启动器缓存', CAT_GAME, '高', ''),
    'colossal order': ('城市:天际线(Colossal Order)', CAT_GAME, '中', ''),
    'yii.guxing': ('归属不明', CAT_ORPH_L, '低', '345 个文件,建议人工排查'),
    'package cache': ('安装器缓存(VS 等)', CAT_DEV, '高', ''),
    'rapogamedev': ('雷柏游戏外设驱动', CAT_SYS, '中', ''),
    'windows master store': ('Windows 优化大师商店组件', CAT_ORPH_H, '高', '推广软件族'),
    'v98pro': ('V98Pro 键盘驱动(VGN)', CAT_SYS, '中', ''),
    'xmind-updater': ('XMind 更新缓存', CAT_UPD, '高', ''),
    'speech': ('系统/输入法语音数据', CAT_SYS, '中', ''),
    'conda': ('Anaconda/Conda', CAT_DEV, '高', ''),
    'acsdkinslog': ('声网 Agora SDK 日志', CAT_CACHE, '中', '音视频 SDK'),
    'obsidian-updater': ('Obsidian 更新缓存', CAT_UPD, '高', ''),
    'adrive-desktop-updater': ('阿里云盘更新缓存', CAT_UPD, '高', ''),
    'rockstar games': ('Rockstar(R星)数据', CAT_GAME, '中', ''),
    '@guanjia-openclawelectron-updater': ('"管家"系应用更新缓存', CAT_UPD, '中', 'Electron 更新包'),
    'chromeextensioncache': ('Chrome 扩展缓存', CAT_CACHE, '高', ''),
    'baidu-translate-client-updater': ('百度翻译更新缓存', CAT_UPD, '高', ''),
    'kwallpaper_sogou': ('搜狗壁纸(推广组件)', CAT_ORPH_M, '中', ''),
    'intel corporation': ('Intel 驱动组件', CAT_SYS, '高', ''),
    'wsl': ('WSL 子系统数据', CAT_SYS, '高', ''),
    'wegame': ('腾讯 WeGame', CAT_INST, '中', ''),
    'fastpdf_duba': ('毒霸系 PDF 推广组件', CAT_ORPH_H, '高', 'fastpdf 推广族'),
    'fastpdf_sogou': ('搜狗系 PDF 推广组件', CAT_ORPH_H, '高', 'fastpdf 推广族'),
    'sogoupdf': ('搜狗 PDF 推广组件', CAT_ORPH_H, '高', 'fastpdf 推广族'),
    'acc_kernel': ('归属不明', CAT_ORPH_L, '低', ''),
    'dbg': ('调试转储', CAT_CACHE, '中', ''),
    'quarkclouddrivemini': ('夸克网盘迷你版', CAT_INST, '中', ''),
    '.lingma': ('通义灵码(阿里 AI 编程)', CAT_INST, '中', ''),
    'prisma-nodejs': ('Prisma 引擎缓存', CAT_DEV, '高', ''),
    'checkpoint-nodejs': ('Node 检查点缓存', CAT_DEV, '高', ''),
    'pix-worker': ('归属不明(疑似 Pix 下载)', CAT_ORPH_L, '低', ''),
    'agoraaudio': ('声网 Agora 音频 SDK', CAT_CACHE, '中', '直播/会议类共用'),
    'tslgame': ('《绝地求生》PUBG', CAT_GAME, '中', 'TslGame 配置/缓存'),
    'placeholdertilelogofolder': ('系统磁贴缓存', CAT_SYS, '高', ''),
    'android': ('Android SDK/模拟器', CAT_DEV, '高', ''),
    'cache': ('通用缓存(归属不明)', CAT_ORPH_L, '低', ''),
    'dsh-plugin-desktop-updater': ('DSH 桌面插件更新缓存', CAT_UPD, '高', 'WorkBuddy 生态'),
    'pixdownloader': ('Pix 下载器', CAT_ORPH_M, '中', ''),
    'docker-secrets-engine': ('Docker 密钥引擎', CAT_DEV, '高', ''),
    'com.github.wasilibs': ('wasilibs(wasm SDK)缓存', CAT_DEV, '高', ''),
    'kotlin': ('Kotlin 编译缓存', CAT_DEV, '高', ''),
    '.qoder-cn': ('通义 Qoder IDE(中文版)', CAT_INST, '中', '阿里 AI IDE'),
    'railcrashreport': ('腾讯 RailSDK 崩溃报告', CAT_GAME, '中', 'WeGame 账号体系'),
    'shanghai_yijing_network_l': ('上海弈鲸网络(未知厂商)', CAT_ORPH_L, '低', ''),
    'clash plus': ('Clash 代理客户端', CAT_ACTIVE, '中', ''),
    '@zcodedesktop-updater': ('ZCode 桌面更新缓存', CAT_UPD, '中', ''),
    'pixcake-qt_pro': ('PixCake 修图软件', CAT_INST, '中', ''),
    'aha_doctor': ('归属不明(疑似健康类应用)', CAT_ORPH_L, '低', ''),
    'doubalinkrouter': ('豆包组件', CAT_INST, '中', ''),
    'crashdumps': ('系统崩溃转储', CAT_CACHE, '高', '201MB,程序崩溃 dump,可清理'),
    'riot games': ('英雄联盟(Riot)', CAT_GAME, '中', ''),
    'icreate-sdk': ('iCreate SDK(LOL 辅助)', CAT_ORPH_M, '中', ''),
    'rail': ('腾讯 RailSDK', CAT_GAME, '中', ''),
    'claude-cli-nodejs': ('Claude Code CLI', CAT_ACTIVE, '中', '命令行 AI 工具'),
    'fastpdf_sogou': ('搜狗系 PDF 推广组件', CAT_ORPH_H, '高', 'fastpdf 推广族'),
    'node-addon-native-custom-loader': ('Node 原生加载器缓存', CAT_DEV, '高', ''),
    'pnpm-store-operation-locks': ('pnpm 存储锁', CAT_DEV, '高', ''),
    'pnpm-state': ('pnpm 状态', CAT_DEV, '高', ''),
    'pnpm-cache': ('pnpm 缓存', CAT_DEV, '高', ''),
    'pnpm': ('pnpm 包管理缓存', CAT_DEV, '高', ''),
    'frida': ('Frida 逆向框架', CAT_DEV, '高', ''),
    'wxworkweb': ('企业微信 Web 组件', CAT_INST, '中', ''),
    'fontconfig': ('字体配置缓存(跨平台库)', CAT_SYS, '中', ''),
    '@genieworkbuddy-desktop-updater': ('WorkBuddy 更新缓存', CAT_UPD, '高', '当前在用的 AI 工作台'),
    'iconcache.db': ('系统图标缓存', CAT_SYS, '高', ''),
    'bitcomet': ('比特彗星 BT 下载', CAT_INST, '中', ''),
    'bitcomet_x64': ('比特彗星 BT 下载', CAT_INST, '中', ''),
    'copilot': ('GitHub Copilot', CAT_DEV, '高', ''),
    'flutter_webview_windows': ('Flutter WebView 组件', CAT_SYS, '中', '某 Flutter 应用共用'),
    'notion-updater': ('Notion 更新缓存', CAT_UPD, '高', ''),
    'ua.net.qytclient.app.apex': ('qyt 客户端', CAT_ORPH_L, '低', ''),
    'cef': ('CEF/Chromium 嵌入式框架缓存', CAT_SYS, '中', '多应用共用'),
    'unrealengine': ('虚幻引擎数据', CAT_GAME, '中', ''),
    'hideandseek': ('归属不明', CAT_ORPH_L, '低', ''),
    'steam': ('Steam 平台', CAT_GAME, '高', ''),
    'comms': ('系统通信组件', CAT_SYS, '高', ''),
    'connecteddevicesplatform': ('系统设备平台', CAT_SYS, '高', ''),
    'toastnotificationmanagercompat': ('系统通知组件', CAT_SYS, '高', ''),
    'openai': ('OpenAI/ChatGPT 桌面端', CAT_INST, '中', ''),
    'stardock': ('Stardock 软件', CAT_INST, '中', ''),
    'qianwen': ('通义千问', CAT_INST, '中', ''),
    'qianwenupdater': ('通义千问更新器', CAT_INST, '中', ''),
    'codebuddyextension': ('CodeBuddy 扩展(腾讯)', CAT_INST, '中', 'AI 编程助手'),
    'backup': ('系统备份', CAT_SYS, '高', ''),
    'publishers': ('系统 COM 事件发布', CAT_SYS, '高', ''),
    'd3dscache': ('DirectX 着色器缓存', CAT_CACHE, '高', '可清理,会重建'),
    'nvidia': ('NVIDIA 着色器/驱动缓存', CAT_CACHE, '高', 'DXCache 类,可清理'),
    'nvidia corporation': ('NVIDIA 驱动组件', CAT_SYS, '高', '含 Ansel/帧率组件'),
    'turingshield': ('图灵盾(反诈组件)', CAT_SYS, '低', '归属存疑'),
    'com.bilingify.readest': ('Readest 阅读器', CAT_INST, '中', '跨平台电子书阅读器'),
    'temp': ('系统临时文件', CAT_CACHE, '高', '可清理(跳过占用中的)'),
    '@deepseek-ai': ('DeepSeek CLI/SDK', CAT_DEV, '高', ''),
    '@deepseek-aidsh-desktop-updater': ('DeepSeek DSH 桌面更新缓存', CAT_UPD, '高', ''),
    'claude-3p': ('Claude 第三方客户端', CAT_ACTIVE, '中', '541MB'),
    'dingtalk_133': ('钉钉', CAT_INST, '高', ''),
    'everything': ('Everything 搜索索引', CAT_INST, '高', '176MB 为文件索引数据库'),
    'netease': ('网易系(云音乐等)', CAT_INST, '中', ''),
}

# 通用(两根共享)
KB_ANY = {
    'google': ('Google(Chrome 等)', CAT_INST, '中', 'Chrome 相关数据'),
    'mozilla': ('Firefox(Mozilla)', CAT_INST, '中', '含浏览器配置/书签'),
    'adobe': ('Adobe 系', CAT_INST, '中', '含 Acrobat/AIGD 组件'),
    'com.adobe.dunamis': ('Adobe Dunamis 遥测', CAT_INST, '中', 'Adobe 遥测组件'),
    'apowersoft': ('Apowersoft', CAT_INST, '中', '录屏等工具'),
    'iobit': ('IObit 组件', CAT_ORPH_M, '中', '若 IObit 系已卸载则为残留'),
    'doubao': ('豆包(字节 AI)', CAT_INST, '中', ''),
    'tencent': ('腾讯系(QQ/微信聊天数据)', CAT_INST, '高', '含聊天记录,删除前务必确认'),
    'kingsoft': ('金山 WPS', CAT_INST, '高', 'WPS 配置与缓存'),
    'netease': ('网易系', CAT_INST, '中', ''),
    'jetbrains': ('JetBrains 全家桶', CAT_INST, '高', 'IDE 配置/索引'),
    'hbuilder x': ('HBuilderX(DCloud)', CAT_INST, '中', '前端 IDE'),
    '微信开发者工具': ('微信开发者工具', CAT_INST, '高', ''),
    'baidu': ('百度系组件', CAT_INST, '中', ''),
    'yarn': ('Yarn 包缓存', CAT_DEV, '高', '1.1GB'),
    'npm': ('npm 配置/全局包', CAT_DEV, '高', ''),
    'npm-cache': ('npm 下载缓存', CAT_DEV, '高', '可用 npm cache clean 清理'),
    'pip': ('pip 下载缓存', CAT_DEV, '高', '可用 pip cache purge 清理'),
    'uv': ('uv(Python 包管理)缓存', CAT_DEV, '高', 'Astral 出品'),
    'typora': ('Typora', CAT_INST, '高', 'Markdown 编辑器'),
    'notion': ('Notion', CAT_INST, '高', ''),
    'obsidian': ('Obsidian', CAT_INST, '高', ''),
    'apifox': ('Apifox', CAT_INST, '高', 'API 调试'),
    'xmind': ('XMind', CAT_INST, '高', '思维导图'),
    'clash plus': ('Clash Plus 代理客户端', CAT_ACTIVE, '中', ''),
    'docker': ('Docker Desktop', CAT_INST, '高', ''),
    'everything': ('Everything', CAT_INST, '高', ''),
    'nutstore': ('坚果云', CAT_INST, '高', ''),
    'nutstoreclient': ('坚果云客户端', CAT_INST, '高', ''),
    'nutstoreinstaller': ('坚果云安装器', CAT_ORPH_M, '中', '安装完成后即为残留'),
    'quarkclouddrive': ('夸克网盘', CAT_INST, '高', ''),
    'the quarkclouddrive authors': ('夸克网盘(签名目录)', CAT_ORPH_M, '中', '更新校验数据'),
    'quarkclouddriveupdater': ('夸克网盘更新器', CAT_INST, '中', ''),
    'baidunetdisk': ('百度网盘', CAT_INST, '高', ''),
    'bdtranslateclient': ('百度翻译客户端', CAT_INST, '高', ''),
    'dingtalk': ('钉钉', CAT_INST, '高', ''),
    'wemeetapp': ('腾讯会议', CAT_INST, '高', ''),
    'qq': ('QQ', CAT_INST, '高', ''),
    'forticlient': ('FortiClient VPN', CAT_INST, '中', '若已卸载则为残留'),
    'oray': ('贝锐(向日葵远程)', CAT_INST, '中', ''),
    'wondershare': ('万兴科技', CAT_INST, '中', ''),
    'sql yog': ('SQLyog', CAT_INST, '高', 'MySQL 客户端'),
    'sqlyog': ('SQLyog', CAT_INST, '高', ''),
    'rabbitmq': ('RabbitMQ', CAT_DEV, '高', ''),
    'leigod': ('雷神加速器', CAT_INST, '中', ''),
    'leigod-bac20ba4': ('雷神加速器(实例)', CAT_INST, '中', ''),
    'stardock': ('Stardock', CAT_INST, '中', ''),
    'openark': ('OpenArk', CAT_ORPH_M, '中', '若仍在用请保留'),
    'anaconda': ('Anaconda', CAT_DEV, '高', ''),
    'copilot': ('Copilot', CAT_DEV, '高', ''),
    'claude': ('Claude 桌面端', CAT_INST, '中', ''),
    'claude-3p': ('Claude 第三方客户端', CAT_ACTIVE, '中', ''),
    'workbuddy': ('WorkBuddy(AI 工作台)', CAT_ACTIVE, '高', '当前正在使用'),
    'nutstoreclient': ('坚果云', CAT_INST, '高', ''),
}

# ---------------- 判定引擎 ----------------
HASH_RE = re.compile(r'^[0-9a-f]{16,64}$')
GUID_RE = re.compile(r'^\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?$')
FILE_EXT_RE = re.compile(r'\.(ini|json|log|db|cfg|cache|txt|resmoncfg)$', re.I)

def match_installed(name_l, nname):
    """注册表卸载项匹配: 返回 (matched_display_list)"""
    hits = []
    if len(nname) >= 2:
        for a in apps:
            if a['nd'] == nname:
                hits.append(a['display']); continue
        if not hits and len(nname) >= 5:
            for a in apps:
                if nname in a['nd'] or nname in a['np']:
                    hits.append(a['display'])
    return hits

def is_active(root_path, name):
    """进程/服务/自启动路径是否位于该目录下"""
    prefix = (root_path + '\\' + name).lower()
    for p in active_paths:
        if p.startswith(prefix + '\\') or p == prefix or p.startswith(prefix + '.'):
            return True
    return False

def active_under(path_l):
    for p in active_paths:
        if p.startswith(path_l + '\\'):
            return p
    return None

def match_appx(name_l, nname):
    if name_l in appx_raw_l: return name_l
    # 仅对"包名式命名"(含点号,如 com.example.app)做包含匹配,
    # 避免普通短名(如 code)误命中包名子串(如 openaicodex)
    if '.' in name_l:
        for f in appx_norm:
            if nname and (nname in f or f in nname) and len(nname) >= 4:
                return f
    return None

def tree_size_mb(path):
    total = 0.0; files = 0; dirs = 0
    for root, ds, fs in os.walk(path, onerror=lambda e: None):
        dirs += len(ds)
        for f in fs:
            files += 1
            try: total += os.path.getsize(os.path.join(root, f))
            except OSError: pass
    return total / (1024*1024), files, dirs

stats = {'kb': 0, 'registry': 0, 'process': 0, 'appx': 0, 'heuristic': 0, 'container': 0, 'hard': 0}

def classify(row):
    name = row['name']; name_l = name.lower(); nname = norm(name)
    root = row['root']; root_path = row['root_path']
    # ---- 1. 硬保护规则 ----
    if name_l == 'microsoft':
        note = 'Roaming\\Microsoft 含 DPAPI 密钥(Protect/Crypto)与证书,删除将导致加密数据不可恢复'
        if root == 'Local': note = '含 Edge/OneDrive/系统令牌缓存,只可细分清理,严禁整删'
        stats['hard'] += 1
        return dict(owner='微软系统组件', cat=CAT_SYS, conf='高', note=note, src='硬保护规则')
    if root == 'Local' and name_l in ('application data', 'history', 'temporary internet files'):
        stats['hard'] += 1
        return dict(owner='Windows XP 兼容性 Junction', cat=CAT_LINK, conf='高',
                    note='系统兼容链接,删除引发目录解析故障', src='硬保护规则')
    if root == 'Local' and name_l == 'programs':
        stats['container'] += 1
        return dict(owner='每用户安装应用容器', cat=CAT_CONT, conf='高', note='见下钻明细', src='容器下钻')
    if root == 'Local' and name_l == 'packages':
        stats['container'] += 1
        return dict(owner='UWP/商店应用数据容器', cat=CAT_CONT, conf='高', note='见下钻明细(按包名与已注册应用比对)', src='容器下钻')
    # ---- 2. 知识库 ----
    kb = KB_LOCAL.get(name_l) if root == 'Local' else KB_ROAM.get(name_l)
    if kb is None: kb = KB_ANY.get(name_l)
    if kb:
        owner, cat, conf, note = kb
        stats['kb'] += 1
        return dict(owner=owner, cat=cat, conf=conf, note=note, src='知识库')
    # 更新缓存模式: *-updater
    if '-updater' in name_l:
        stats['kb'] += 1
        return dict(owner=name.replace('-updater', '') + ' 更新缓存', cat=CAT_UPD, conf='高',
                    note='Electron electron-updater 下载的安装包缓存', src='命名模式')
    # ---- 3. 注册表卸载项 ----
    hits = match_installed(name_l, nname)
    if hits:
        stats['registry'] += 1
        return dict(owner=hits[0], cat=CAT_INST, conf='高',
                    note='注册表卸载项: ' + '; '.join(hits[:3]), src='注册表')
    # ---- 4. 进程/服务/自启动 ----
    p = active_under((root_path + '\\' + name).lower())
    if p:
        stats['process'] += 1
        return dict(owner=name + '(运行中)', cat=CAT_ACTIVE, conf='高',
                    note='活动进程/服务路径: ' + p, src='运行证据')
    # ---- 5. 商店应用 ----
    fam = match_appx(name_l, nname)
    if fam:
        stats['appx'] += 1
        return dict(owner='商店应用: ' + fam, cat=CAT_INST, conf='中', note='Get-AppxPackage 注册包匹配', src='商店包')
    # ---- 6. 启发式 ----
    stats['heuristic'] += 1
    mt = row['mtime']
    stale = (mt is not None and (NOW - mt).days > STALE_DAYS)
    if HASH_RE.match(name_l) or GUID_RE.match(name_l):
        return dict(owner='未知(哈希/GUID 命名)', cat=CAT_ORPH_L, conf='低',
                    note='哈希或 GUID 命名目录,常见于推广 SDK/DRM,无法从名称推断归属', src='启发式')
    if stale:
        return dict(owner='未知', cat=CAT_ORPH_M, conf='中',
                    note='无安装记录、无运行进程,且 %d 天未修改' % (NOW - mt).days, src='启发式')
    return dict(owner='未知', cat=CAT_ORPH_L, conf='低',
                note='无安装记录与运行证据,近期有改动,可能为便携/绿色软件数据' , src='启发式')

# ---------------- 容器下钻 ----------------
def drill_programs(rows_out):
    base = os.path.join(LOCALAPPDATA, 'Programs')
    try: children = sorted(os.listdir(base))
    except OSError: children = []
    for ch in children:
        full = os.path.join(base, ch)
        if not os.path.isdir(full): continue
        sz, nf, nd = tree_size_mb(full)
        sub = {'root': 'Local\\Programs', 'root_path': base, 'name': ch, 'size_mb': sz,
               'files': nf, 'dirs': nd, 'mtime': None, 'owner': ''}
        try:
            mt = datetime.fromtimestamp(os.path.getmtime(full)); sub['mtime'] = mt
        except OSError: pass
        r = classify(sub)
        rows_out.append((sub, r))

def drill_packages(rows_out):
    base = os.path.join(LOCALAPPDATA, 'Packages')
    try: children = sorted(os.listdir(base))
    except OSError: children = []
    for ch in children:
        full = os.path.join(base, ch)
        if not os.path.isdir(full): continue
        sz, nf, nd = tree_size_mb(full)
        sub = {'root': 'Local\\Packages', 'root_path': base, 'name': ch, 'size_mb': sz,
               'files': nf, 'dirs': nd, 'mtime': None, 'owner': ''}
        try:
            mt = datetime.fromtimestamp(os.path.getmtime(full)); sub['mtime'] = mt
        except OSError: pass
        fam_l = ch.lower()
        if fam_l in appx_raw_l:
            r = dict(owner='已注册商店应用: ' + ch.split('_')[0], cat=CAT_INST, conf='高',
                     note='包名与 Get-AppxPackage 注册记录匹配', src='商店包')
            stats['appx'] += 1
        else:
            # 按包前缀模糊匹配(同应用不同版本/发布者ID)
            prefix = ch.split('_')[0].lower()
            hit = any(f.startswith(prefix + '_') for f in appx_raw_l)
            if hit:
                r = dict(owner='疑似已注册(前缀匹配)', cat=CAT_INST, conf='中',
                         note='包名前缀匹配已注册应用的其他版本', src='商店包')
                stats['appx'] += 1
            else:
                r = dict(owner='未注册 UWP 应用数据', cat=CAT_ORPH_M, conf='中',
                         note='商店应用已卸载或仅为其他账户暂存(staged)', src='商店包比对')
                stats['heuristic'] += 1
        rows_out.append((sub, r))

# ---------------- 主流程 ----------------
def main():
    roam = load_treesize_csv(ROAMING_CSV, 'Roaming', APPDATA)
    local = load_treesize_csv(LOCAL_CSV, 'Local', LOCALAPPDATA)
    results = []
    for row in roam + local:
        results.append((row, classify(row)))
    drill_programs(results)
    drill_packages(results)

    # 输出 CSV
    csv_path = os.path.join(OUT, 'AppData残留候选分析_2026-10-23.csv')
    order = {CAT_LINK: 0, CAT_SYS: 1, CAT_CONT: 2, CAT_INST: 3, CAT_ACTIVE: 4, CAT_GAME: 5,
             CAT_UPD: 6, CAT_DEV: 7, CAT_CACHE: 8, CAT_ORPH_H: 9, CAT_ORPH_M: 10, CAT_ORPH_L: 11}
    rows_sorted = sorted(results, key=lambda x: (x[0]['root'] != 'Roaming', order.get(x[1]['cat'], 99), -x[0]['size_mb']))
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['位置', '名称', '大小MB', '文件数', '最后修改', '分类', '归属判定', '建议', '置信度', '证据/备注', '判定来源'])
        for row, r in rows_sorted:
            w.writerow([
                row['root'], row['name'], round(row['size_mb'], 1), row['files'],
                row['mtime'].strftime('%Y-%m-%d') if row['mtime'] else '',
                r['cat'], r['owner'], ADVICE.get(r['cat'], ''), r['conf'], r['note'], r['src'],
            ])

    # 汇总统计
    agg = {}
    for row, r in results:
        c = r['cat']
        a = agg.setdefault(c, {'count': 0, 'size_mb': 0.0})
        a['count'] += 1
        a['size_mb'] += row['size_mb']
    agg_top = {}
    for row, r in results:
        if row['root'] not in ('Roaming', 'Local'): continue  # 仅顶层,口径与 TreeSize CSV 一致
        c = r['cat']
        a = agg_top.setdefault(c, {'count': 0, 'size_mb': 0.0})
        a['count'] += 1
        a['size_mb'] += row['size_mb']
    roots_total = {}
    for row, r in results:
        if row['root'] in ('Roaming', 'Local'):
            t = roots_total.setdefault(row['root'], {'count': 0, 'size_mb': 0.0})
            t['count'] += 1; t['size_mb'] += row['size_mb']
    top_orphans = sorted(
        [(row['root'], row['name'], round(row['size_mb'], 1), row['mtime'].strftime('%Y-%m-%d') if row['mtime'] else '', r['owner'], r['note'])
         for row, r in results if r['cat'] in (CAT_ORPH_H, CAT_ORPH_M)],
        key=lambda x: -x[2])[:25]
    summary = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'evidence': {'uninstall_entries': len(apps), 'appx_packages': len(appx_raw_l),
                     'active_paths': len(active_paths), 'processes': len(ev_procs), 'services': len(ev_svcs)},
        'treesize_rows': {'Roaming': len(roam), 'Local': len(local)},
        'totals': roots_total,
        'category_agg': {k: {'count': v['count'], 'size_mb': round(v['size_mb'], 1)} for k, v in sorted(agg.items())},
        'category_agg_toplevel': {k: {'count': v['count'], 'size_mb': round(v['size_mb'], 1)} for k, v in sorted(agg_top.items())},
        'classify_sources': stats,
        'top_orphans': top_orphans,
    }
    with open(os.path.join(PROTO, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 运行日志
    log = []
    log.append('=== AppData 残留候选识别原型 运行日志 ===')
    log.append('输入行数: Roaming=%d, Local=%d' % (len(roam), len(local)))
    log.append('证据: 卸载项=%d, 商店包=%d, 活动路径=%d' % (len(apps), len(appx_raw_l), len(active_paths)))
    log.append('判定来源分布: ' + json.dumps(stats, ensure_ascii=False))
    log.append('分类汇总:')
    for k, v in summary['category_agg'].items():
        log.append('  %-14s %3d 项  %10.1f MB' % (k, v['count'], v['size_mb']))
    log.append('输出: ' + csv_path)
    log_text = '\n'.join(log)
    with open(os.path.join(PROTO, 'run_log.txt'), 'w', encoding='utf-8') as f:
        f.write(log_text)
    print(log_text)

if __name__ == '__main__':
    main()
