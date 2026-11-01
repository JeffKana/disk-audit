#!/usr/bin/env node
// F5（任务卡 T3-03）报告性能测量：Edge/Chrome headless + DevTools Protocol。
// 口径与 W0 POC 实测一致（页面 performance API 自报 + headless 采样，W0 用
// --dump-dom 抓取，本脚本经 CDP Runtime.evaluate 直读，同源同义）：
//   ② 首屏 DOMContentLoaded：3 次加载采样取中位数（performance
//      getEntriesByType('navigation').domContentLoadedEventEnd）；
//   ③ 筛选响应：每次加载内跑 3 个关键词（tencent/updater/zzz_not_exist）
//      的 input 事件 + 强制布局（offsetHeight）取均值，3 次加载取中位数。
// 零 npm 依赖（Node 22+ 内置 WebSocket/fetch）；不入 CI、不入产品依赖。
// 用法：node tools/measure_report_perf.mjs <report.html> [rounds=3]
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const BROWSERS = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
];

const FILTER_EXPR = `(function(){
  var q=document.getElementById('q');
  var b=document.getElementById('dt');
  if(!q||!b){return JSON.stringify({error:'filter input missing'})}
  var samples=['tencent','updater','zzz_not_exist'],sum=0,each=[];
  samples.forEach(function(s){
    var t0=performance.now();
    q.value=s;q.dispatchEvent(new Event('input'));
    document.body.offsetHeight;
    var dt=performance.now()-t0;sum+=dt;each.push(Math.round(dt*10)/10);
  });
  q.value='';q.dispatchEvent(new Event('input'));
  document.body.offsetHeight;
  var vis=[].slice.call(b.rows).filter(function(r){return r.style.display!=='none'}).length;
  return JSON.stringify({avg:sum/samples.length,each:each,visible_after_reset:vis});
})()`;

const DCL_EXPR = `(function(){
  var n=performance.getEntriesByType('navigation')[0];
  return JSON.stringify({
    dcl:n?n.domContentLoadedEventEnd:-1,
    load:n?n.loadEventEnd:-1,
    dom_elements:document.getElementsByTagName('*').length
  });
})()`;

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = [];
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(typeof ev.data === "string" ? ev.data : ev.data.toString());
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(methodName(msg) + " " + JSON.stringify(msg.error))) : resolve(msg.result);
      } else if (msg.method) {
        for (const fn of this.listeners) fn(msg);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve: (r) => resolve({ ...r, __method: method }), reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  on(fn) {
    this.listeners.push(fn);
  }
  waitEvent(method, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("timeout waiting " + method)), timeoutMs);
      const fn = (msg) => {
        if (msg.method === method) {
          clearTimeout(timer);
          this.listeners = this.listeners.filter((f) => f !== fn);
          resolve(msg.params);
        }
      };
      this.listeners.push(fn);
    });
  }
}

function methodName(msg) {
  return msg.id ? "" : msg.method;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

async function findPageTarget(port) {
  for (let i = 0; i < 50; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/list`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch {
      /* browser not ready yet */
    }
    await sleep(200);
  }
  throw new Error("no page target on devtools port");
}

async function main() {
  const htmlPath = process.argv[2];
  const rounds = Number(process.argv[3] || 3);
  if (!htmlPath || !existsSync(htmlPath)) {
    console.error('usage: node tools/measure_report_perf.mjs <report.html> [rounds=3]');
    process.exit(2);
  }
  const url = pathToFileURL(htmlPath).href;
  const browser = BROWSERS.find((p) => existsSync(p));
  if (!browser) throw new Error("no Edge/Chrome found");
  const profile = mkdtempSync(join(tmpdir(), "t303-perf-"));
  const proc = spawn(browser, [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--disable-gpu",
    "--disable-extensions",
    "--no-default-browser-check",
    "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });

  let port = null;
  const stderrChunks = [];
  proc.stderr.on("data", (d) => {
    stderrChunks.push(d);
    const m = String(d).match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//);
    if (m) port = Number(m[1]);
  });
  for (let i = 0; i < 100 && port === null; i++) await sleep(100);
  if (port === null) {
    throw new Error("devtools port not announced: " + stderrChunks.join(""));
  }

  const dcls = [];
  const filters = [];
  const loads = [];
  let domElements = -1;
  try {
    for (let round = 1; round <= rounds; round++) {
      const target = await findPageTarget(port);
      const ws = new WebSocket(target.webSocketDebuggerUrl);
      await new Promise((resolve, reject) => {
        ws.addEventListener("open", resolve);
        ws.addEventListener("error", () => reject(new Error("ws error")));
      });
      const cdp = new CDP(ws);
      await cdp.send("Page.enable");
      await cdp.send("Runtime.enable");
      await cdp.send("Page.navigate", { url: "about:blank" });
      await sleep(150);
      const loaded = cdp.waitEvent("Page.loadEventFired", 60000);
      await cdp.send("Page.navigate", { url });
      await loaded;
      await sleep(250); // 等 navigation entry 的 loadEventEnd 落盘

      const dclRes = await cdp.send("Runtime.evaluate", {
        expression: DCL_EXPR,
        returnByValue: true,
      });
      const dcl = JSON.parse(dclRes.result.value);
      dcls.push(dcl.dcl);
      loads.push(dcl.load);
      domElements = dcl.dom_elements;

      const filterRes = await cdp.send("Runtime.evaluate", {
        expression: FILTER_EXPR,
        returnByValue: true,
      });
      const filter = JSON.parse(filterRes.result.value);
      if (filter.error) throw new Error(filter.error);
      filters.push(filter.avg);

      process.stderr.write(
        `round ${round}/${rounds}: DCL=${dcl.dcl.toFixed(0)}ms load=${dcl.load.toFixed(0)}ms ` +
        `filter_avg=${filter.avg.toFixed(1)}ms each=[${filter.each.join(",")}] visible=${filter.visible_after_reset}\n`
      );
      await cdp.send("Page.navigate", { url: "about:blank" }).catch(() => {});
      ws.close();
      await sleep(200);
    }
  } finally {
    spawnSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore" });
    try {
      rmSync(profile, { recursive: true, force: true });
    } catch {
      /* temp profile best-effort cleanup */
    }
  }

  const result = {
    browser,
    rounds,
    dom_elements: domElements,
    dcl_ms_samples: dcls.map((v) => Math.round(v)),
    dcl_ms_median: Math.round(median(dcls)),
    load_ms_samples: loads.map((v) => Math.round(v)),
    filter_ms_samples: filters.map((v) => Math.round(v * 10) / 10),
    filter_ms_median: Math.round(median(filters) * 10) / 10,
    budgets: { dcl_ms_le: 1000, filter_ms_le: 150 },
  };
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
}

main().catch((err) => {
  console.error(err && err.message ? err.message : err);
  process.exit(1);
});
