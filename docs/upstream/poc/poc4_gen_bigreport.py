# -*- coding: utf-8 -*-
"""POC-4: 大表格静态 HTML 报告性能
生成 5000 行明细 + 内联 CSS + 原生 JS 筛选，页面自报加载耗时（供 headless dump-dom 抓取）
"""
import os, time, json, random, html

N = 5000
random.seed(42)

CATS = ["已安装应用", "残留候选·高置信", "残留候选·中置信", "残留候选·低置信",
        "开发缓存", "更新缓存", "系统组件", "游戏数据", "容器", "缓存/转储"]
NAMES = ["Tencent", "kingsoft", "Sun", "Netease", "obsidian-updater", "xmind-updater",
         "apifox-updater", "notion-updater", "deepseek-updater", "b1", "tidalab",
         "Yii.Guxing", "chat_pp", "dzip_pp", "tabx_pp", "qq_guild", "alixby",
         "Electron", "CEF", "AgoraAudio", "VoipNNModel", "WNS", "Cache",
         "360safe", "Ludashi", "DrvMgr", "lds", "fastpdf_core", "Microsoft"]
CONF = ["高", "中", "低", "受保护"]
SRC = ["知识库", "注册表", "商店包", "进程/服务", "启发式兜底", "硬保护规则"]

rows = []
for i in range(N):
    name = random.choice(NAMES) + ("" if random.random() < 0.5 else "_%d" % random.randint(1, 999))
    cat = random.choice(CATS)
    conf = random.choice(CONF)
    size = random.choice([random.randint(1, 500), random.randint(500, 90000), random.randint(90000, 610000)])
    rows.append({
        "p": "C:\\Users\\querkecor\\AppData\\%s\\%s" % (random.choice(["Roaming", "Local"]), name),
        "s": size, "c": cat, "f": conf, "src": random.choice(SRC),
        "age": random.randint(3, 1500),
        "ev": "%s 命中；注册表无卸载记录；无关联进程；最后修改 %d 天前" % (random.choice(SRC), random.randint(3, 1500)),
    })

CLS = {"高": "hi", "中": "mid", "低": "low", "受保护": "prot"}

t0 = time.perf_counter()
parts = []
parts.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>POC-4 大表格性能测试</title><style>
body{margin:0;padding:24px;background:#f6f7f9;color:#1f2937;font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:20px;margin:0 0 6px}.bar{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;margin:12px 0}
#t{font-size:22px;font-weight:700;color:#1d4ed8}
table{width:100%;border-collapse:collapse;background:#fff;font-size:12.8px}
th{position:sticky;top:0;background:#f3f4f6;text-align:left;padding:6px 8px;border:1px solid #e5e7eb}
td{padding:5px 8px;border:1px solid #eef0f2}
tr:nth-child(even) td{background:#fafafa}
.hi{background:#fee2e2;color:#991b1b;font-weight:700}.mid{background:#fef3c7;color:#92400e}
.low{background:#e5e7eb;color:#374151}.prot{background:#ede9fe;color:#5b21b6;font-weight:700}
input{padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;width:280px}
.num{text-align:right}
</style></head><body>
<h1>POC-4：5000 行明细表渲染测试</h1>
<div class="bar">本页 <b>DOMContentLoaded → load 完成</b> 耗时：<span id="t">测量中…</span>
  <span style="color:#6b7280;font-size:13px">（由页面自身 performance API 计算，headless 与真实浏览器均可读）</span></div>
<div class="bar">筛选：<input id="q" placeholder="输入目录名，如 tencent"> <span id="cnt"></span></div>
<table><thead><tr><th>路径</th><th>大小(MB)</th><th>分类</th><th>置信度</th><th>判定来源</th><th>陈旧(天)</th><th>证据</th></tr></thead><tbody>
""")

for r in rows:
    parts.append(
        '<tr><td>%s</td><td class="num">%.1f</td><td>%s</td><td class="%s">%s</td><td>%s</td>'
        '<td class="num">%d</td><td>%s</td></tr>\n' % (
            html.escape(r["p"]), r["s"] / 1.0, html.escape(r["c"]), CLS[r["f"]], r["f"],
            r["src"], r["age"], html.escape(r["ev"])))

parts.append("""</tbody></table>
<script>
window.addEventListener('load',function(){
  var n=performance.getEntriesByType('navigation')[0];
  var v=n?(n.domContentLoadedEventEnd).toFixed(0):'n/a';
  var l=n?(n.loadEventEnd).toFixed(0):'n/a';
  /* 筛选响应实测：3 次关键词筛选的平均耗时 */
  var q=document.getElementById('q');
  var samples=['tencent','updater','zzz_not_exist'],sum=0;
  samples.forEach(function(s){
    var t0=performance.now();
    q.value=s;
    q.dispatchEvent(new Event('input'));
    document.body.offsetHeight; /* 强制布局，避免只测到 JS 不测重排 */
    sum+=performance.now()-t0;
  });
  var f=(sum/samples.length).toFixed(1);
  q.value='';
  q.dispatchEvent(new Event('input'));
  document.getElementById('t').textContent='DCL '+v+' ms / load '+l+' ms / 筛选均值 '+f+' ms';
  document.title='POC4_RESULT DCL='+v+' LOAD='+l+' FILTER='+f;
});
(function(){
  var q=document.getElementById('q'),b=document.querySelector('tbody'),cnt=document.getElementById('cnt');
  var trs=[].slice.call(b.rows);
  cnt.textContent='共 '+trs.length+' 行';
  q.addEventListener('input',function(){
    var s=q.value.toLowerCase();
    trs.forEach(function(r){r.style.display=(!s||r.cells[0].textContent.toLowerCase().indexOf(s)>-1)?'':'none'});
    var vis=trs.filter(function(r){return r.style.display!=='none'}).length;
    cnt.textContent='筛选后 '+vis+' 行';
  });
})();
</script></body></html>""")

doc = "".join(parts)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc4_bigreport.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(doc)
dt = time.perf_counter() - t0
size = os.path.getsize(out)
print(json.dumps({
    "rows": N, "file_kb": round(size / 1024, 1),
    "gen_seconds": round(dt, 2),
    "est_dom_nodes": N * 7 + 40,
    "path": out,
}, ensure_ascii=False, indent=2))
