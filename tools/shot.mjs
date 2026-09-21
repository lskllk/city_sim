/** tools/shot.mjs —— 用 CDP 实拍一张（headless --screenshot 会缓存、也不等网络）。
 *  用法: node tools/shot.mjs <url> <out.png> [等几秒] [宽] [高]
 */
const [url, out, waitS = "9", W = "1400", H = "880"] = process.argv.slice(2);
const base = "http://127.0.0.1:9222";
const list = await (await fetch(base + "/json")).json();
let page = list.find(t => t.type === "page");
if (!page) { console.error("没有可用页面"); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0; const wait = new Map();
const call = (method, params) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } };
await new Promise(r => ws.onopen = r);
await call("Emulation.setDeviceMetricsOverride",
  { width: +W, height: +H, deviceScaleFactor: 1, mobile: false });
await call("Network.setCacheDisabled", { cacheDisabled: true });
await call("Page.navigate", { url });
await new Promise(r => setTimeout(r, 1200));
await call("Page.reload", { ignoreCache: true });   // ★ ES module 会被浏览器缓存，
                                                     //   setCacheDisabled 管不住模块表
await new Promise(r => setTimeout(r, +waitS * 1000));
const shot = await call("Page.captureScreenshot", { format: "png" });
const { writeFileSync } = await import("node:fs");
writeFileSync(out, Buffer.from(shot.result.data, "base64"));
console.log("  →", out);
process.exit(0);
