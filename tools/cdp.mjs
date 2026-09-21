/** tools/cdp.mjs —— 在页面里求值 / 派事件。验收用（我看不到浏览器）。
 *
 * 用法:
 *   node tools/cdp.mjs <url> <等待秒> <js表达式>
 *   node tools/cdp.mjs <url> <等待秒> --eval-file <文件>
 *
 * 表达式在页面里执行，返回值 JSON 化后打到 stdout。
 * 需要先起一个带 --remote-debugging-port=9222 的 Chrome。
 */
const [url, waitS, ...rest] = process.argv.slice(2);
const base = "http://127.0.0.1:9222";

let expr = rest.join(" ");
let evalFile = null;
const fi = rest.indexOf("--eval-file");
if (fi >= 0) { evalFile = rest[fi + 1]; expr = null; }

const list = await (await fetch(base + "/json")).json();
const page = list.find(t => t.type === "page");
if (!page) { console.error("没有可用页面"); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0; const wait = new Map();
const call = (m, p) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } };
await new Promise(r => ws.onopen = r);

const logs = [];
await call("Runtime.enable", {});
await call("Log.enable", {});
ws.addEventListener("message", e => {
  const m = JSON.parse(e.data);
  if (m.method === "Runtime.consoleAPICalled")
    logs.push("console." + m.params.type + ": " +
      m.params.args.map(a => a.value ?? a.description ?? a.type).join(" "));
  if (m.method === "Runtime.exceptionThrown")
    logs.push("EXCEPTION: " + (m.params.exceptionDetails.exception?.description
      || m.params.exceptionDetails.text));
});

await call("Network.setCacheDisabled", { cacheDisabled: true });
await call("Page.navigate", { url });
await new Promise(r => setTimeout(r, 1200));
await call("Page.reload", { ignoreCache: true });   // ★ ES module 会被浏览器缓存，
                                                     //   setCacheDisabled 管不住模块表
await new Promise(r => setTimeout(r, +waitS * 1000));

if (evalFile) {
  const { readFileSync } = await import("node:fs");
  expr = readFileSync(evalFile, "utf8");
}
const r = await call("Runtime.evaluate",
  { expression: expr, returnByValue: true, awaitPromise: true, userGesture: true });
if (r.result?.exceptionDetails) {
  console.error("  页面里抛错:", JSON.stringify(r.result.exceptionDetails).slice(0, 500));
}
const v = r.result?.result?.value;
console.log(typeof v === "string" ? v : JSON.stringify(v, null, 1));
if (logs.length) console.log("\n  ── 控制台 ──\n  " + logs.join("\n  "));
process.exit(0);
