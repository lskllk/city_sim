/** panel.js —— 点一个人，看穿他。
 *
 * 这一页是整个 demo 的核心：**不是看数字，是看"他知道的东西有多旧"**。
 * 记忆卡上三个东西最重要：
 *   source   来源（亲眼 / 听说 / 传闻）—— 他凭什么知道
 *   believe  置信度 —— 他有多信
 *   last_seen + price —— 【他记得的价格】可能已经过时了
 */
const SIGNALS = [
  ["energy", "精力"], ["hunger", "饿"], ["bladder", "憋"],
  ["hp", "健康"], ["fun", "想玩"],
];
const TICKS_PER_DAY = 1440;        // config/sim.toml 的常量；1 游戏天 = 1440 tick

const SOURCE_CLASS = { 亲眼: "src-亲眼", 听说: "src-听说", 传闻: "src-传闻" };

const esc = (s) => String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

/** tick 差 → 人话（"3 小时前""2 天前"）。 */
function ago(ticks) {
  if (ticks == null || ticks < 0) return "不记得了";
  const h = ticks / (TICKS_PER_DAY / 24);
  if (h < 1) return "刚刚";
  if (h < 24) return `${Math.round(h)} 小时前`;
  return `${Math.round(h / 24)} 天前`;
}

export function renderPanel(host, npc, store, onClose) {
  if (!npc) { host.classList.add("hide"); host.innerHTML = ""; return; }
  host.classList.remove("hide");

  const sig = SIGNALS.map(([k, label]) => {
    const v = Math.max(0, Math.min(1, Number(npc.signals?.[k] ?? 0)));
    return `<div class="sig${v < 0.3 ? " down" : ""}">
      <span>${label}</span>
      <span class="track"><span class="fill" style="width:${(v * 100).toFixed(0)}%"></span></span>
      <span class="num">${(v * 100).toFixed(0)}</span></div>`;
  }).join("");

  const act = npc.active
    ? `${npc.active.verb || "?"} <span class="dim">${esc(npc.active.item || "")}</span>`
    : (npc.activity || "站着");
  const travel = npc.travel
    ? `<div class="memo">正在走去 <b>${esc(store.locations[npc.travel.to]?.name || npc.travel.to)}</b>
       <span class="who">${ago(npc.travel.depart != null ? store.tick - npc.travel.depart : null)}出发</span></div>`
    : "";

  host.innerHTML = `
    <button class="close" title="关掉">✕</button>
    <h2>${esc(npc.name)}</h2>
    <div class="role">${esc(npc.role || "—")} · ${npc.age ?? "?"} 岁
      · 家：${esc(store.locations[npc.home]?.name || "无")}</div>

    <h3>现在</h3>
    <dl class="kv">
      <dt>在做</dt><dd style="text-align:left">${act}</dd>
      <dt>在哪</dt><dd>${esc(store.locations[npc.loc]?.name || npc.loc || "路上")}</dd>
      <dt>钱</dt><dd>${npc.money ?? "—"}</dd>
    </dl>
    ${travel}

    <h3>状态</h3>
    ${sig}

    <h3>他记得什么 <span class="dim">${npc.memory ? "共 " + npc.memory.length + " 条" : "(加载中…)"}</span></h3>
    ${npc.memory ? renderMemory(npc, store) : '<div class="empty">后端每 6 帧才带一次记忆</div>'}
  `;
  host.querySelector(".close").onclick = onClose;
}

function renderMemory(npc, store) {
  if (!npc.memory.length) return '<div class="empty">他什么都还不知道 —— 没去过、也没听人说过。</div>';
  // 越旧的排前面：这条列表是用来"看见旧"的，不是用来查货的
  const rows = [...npc.memory].sort((a, b) => (a.last_seen ?? 0) - (b.last_seen ?? 0)).slice(0, 14);
  return rows.map(m => {
    const where = store.locations[m.located]?.name || m.located || "?";
    const stale = m.last_seen != null ? store.tick - m.last_seen : null;
    const old = stale != null && stale > TICKS_PER_DAY;      // 超过一天 = 该打个标记
    return `<div class="memo ${SOURCE_CLASS[m.source] || ""}">
      <b>${esc(itemLabel(m))}</b>
      <span class="who">@ ${esc(where)}</span>
      <div class="who" style="margin-top:2px">
        记得 <b>${m.price ?? "?"}</b>${old ? " ⚠可能过时" : ""}
        · 信 ${(m.believe * 100).toFixed(0)}%
        · ${esc(m.source || "?")}
        · ${ago(stale)}
      </div></div>`;
  }).join("");
}

function itemLabel(m) {
  return (m.item_type || m.item_id || "?").replace(/^[a-z]+_/, (s) => s);
}
