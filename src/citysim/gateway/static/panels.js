/* panels.js —— 右侧检查器 + 底部事件流的 DOM 渲染 (g5-life 02/06/07)。 */
const Panels = (() => {
  const $ = s => document.querySelector(s);
  const titleEl = $("#inspTitle"), panelEl = $("#panel");
  const tabBtns = [...document.querySelectorAll("#tabs [data-tab]")];
  const filterBtns = [...document.querySelectorAll("#evbar [data-filter]")];
  const listEl = $("#events");
  const clockEl = $("#clock"), connEl = $("#conn");
  let curTab = "status", curFilter = "all";
  let whoHandler = null;
  const ACT_TXT = { sleep: "睡眠", eat: "进食", toilet: "如厕", fun: "娱乐",
                    drink: "饮水", idle: "闲逛", move: "赶路" };
  const NAME = s => String(s);
  const bar = (label, v, color) => `
    <div class="needrow"><span class="needlab">${label}</span>
      <div class="sig"><div class="bar"><div class="fill" style="width:${Math.round(v*100)}%;background:${color||"#6fdc8c"}"></div></div></div>
      <span class="needval">${(v*100).toFixed(0)}</span></div>`;
  function bindHandlers(h) {
    tabBtns.forEach(b => b.addEventListener("click", () => {
      tabBtns.forEach(x => x.classList.remove("active"));
      b.classList.add("active"); curTab = b.dataset.tab;
      if (h.onTab) h.onTab(curTab);
    }));
    filterBtns.forEach(b => b.addEventListener("click", () => {
      filterBtns.forEach(x => x.classList.remove("active"));
      b.classList.add("active"); curFilter = b.dataset.filter;
      if (h.onFilter) h.onFilter(curFilter);
    }));
  }
  function showTab(tab) {
    curTab = tab;
    tabBtns.forEach(x => x.classList.toggle("active", x.dataset.tab === tab));
  }
  function title(html) { titleEl.innerHTML = html; }
  function conn(ok) {
    connEl.textContent = ok ? "● 已连接" : "● 已断开";
    connEl.style.color = ok ? "#6fdc8c" : "#ff7a7a";
  }
  function clock(txt) { if (clockEl.textContent !== txt) clockEl.textContent = txt; }
  function sigColor(v) { return v < 0.15 ? "#ff7a7a" : v < 0.3 ? "#e6c04a" : "#6fdc8c"; }

  function header(n, d) {
    const act = d.act_class || "idle";
    return `<div class="row"><b>${NAME(n)}</b>
      <span class="chip" data-act="${act}">${ACT_TXT[act] || act}</span></div>`;
  }
  function status(d) {
    if (!d) { panelEl.innerHTML = "<p class='dim'>（暂无状态）</p>"; return; }
    const s = d.signals || {};
    const ord = [["hunger", "饥饿"], ["thirst", "口渴"], ["energy", "精力"],
                 ["bladder", "膀胱"]];
    const rows = ord.filter(([k]) => s[k] !== undefined)
      .map(([k, l]) => bar(l, s[k], sigColor(s[k]))).join("");
    const it = d.intent;
    const tv = d.travel;
    panelEl.innerHTML = `
      <div class="head">${header(d.name || d.id, d)}</div>
      <div class="sec">${d.loc || ""}${it ? ` · 想${it.kind} ${it.target || ""}` : ""}${tv ? ` · 前往 ${tv.to}` : ""}</div>
      <div class="sec">${rows}</div>
      ${it ? `<div class="sec dim">理由：${NAME(it.reason)}</div>` : ""}`;
  }
  function why(d, nameFn) {
    if (!d) { panelEl.innerHTML = "<p class='dim'>（暂无）</p>"; return; }
    const N = nameFn || NAME;
    const it = d.intent;
    if (!it) { panelEl.innerHTML = header(d.name || d.id, d)
      + "<div class='sec dim'>当前无意图（闲逛/无需求）</div>"; return; }
    const picked = it.kind;
    const ranked = (it.ranked && it.ranked.length)
      ? it.ranked : [{ id: picked, score: 1 }];
    const maxScore = Math.max(...ranked.map(r => r.score), 0.0001);
    const rows = ranked.map(r => {
      const chosen = r.id === picked;
      const w = Math.max(2, Math.round(r.score / maxScore * 100));
      const label = ACT_TXT[r.id] || N(r.id) || r.id;
      return `<tr${chosen ? ' class="sel"' : ""}>
        <td>${label}${chosen ? " ✓" : ""}</td>
        <td style="min-width:84px"><div class="mini"><i style="width:${w}%"></i></div></td>
        <td class="rank">${r.score.toFixed(3)}</td>
        <td>${chosen ? "采纳" : "未采纳"}</td></tr>`;
    }).join("");
    const used = it.used_facts && it.used_facts.length
      ? `<div class="sec"><div class="sect">依据事实（本次决策）</div>` +
        it.used_facts.map(f => `<div class="row mono sm">${N(f.src)} ${f.relation} ${N(f.dst)} · ${f.source_kind || ""} ${f.confidence ? f.confidence.toFixed(2) : ""}</div>`).join("") + "</div>" : "";
    const plan = it.plan && it.plan.length
      ? `<div class="sec"><div class="sect">执行计划</div><div class="mono">${it.plan.join(" → ")}</div></div>` : "";
    panelEl.innerHTML = header(d.name || d.id, d)
      + `<div class="sec">当前决策：想 <b>${ACT_TXT[picked] || N(picked)}</b>${it.target ? " · " + N(it.target) : ""}</div>`
      + `<div class="sec dim">理由：${N(it.reason)}</div>`
      + `<div class="sec"><div class="sect">决策表（候选意图打分）</div>
         <table class="kbt"><tr><th>候选</th><th>得分</th><th>数值</th><th>结果</th></tr>${rows}</table></div>`
      + plan + used;
  }
  function kb(d, nameFn) {
    if (!d) { panelEl.innerHTML = "<p class='dim'>（该模式无知识）</p>"; return; }
    panelEl.innerHTML = header(d.name || d.id, d);
    const wrap = document.createElement("div");
    wrap.className = "kbwrap";
    panelEl.appendChild(wrap);
    kbGraph(wrap, d.kb, d.kb_counts, (subj, rel, obj) => {
      if (whoHandler) whoHandler(subj, rel, obj);
    });
    panelEl.appendChild(document.createElement("p")).className = "dim";
    panelEl.lastChild.textContent = "提示：点表格行高亮" + (nameFn ? "" : "");
  }
  function events(rows) {
    if (!rows || !rows.length) { panelEl.innerHTML = "<p class='dim'>（无事件）</p>"; return; }
    panelEl.innerHTML = rows.slice(0, 50)
      .map(x => `<div class="evrow">${x}</div>`).join("");
  }
  function feed(rows, filter) {
    const f = filter || curFilter;
    listEl.innerHTML = rows.filter(r => f === "all" || r.kind === f)
      .slice(0, 120).map(r => `<li class="${r.kind}">${r.html}</li>`).join("");
  }
  function setWhoHandler(fn) { whoHandler = fn; }

  return { bindHandlers, showTab, title, conn, clock, status, why, kb, events,
           feed, setWhoHandler, tab: () => curTab, filter: () => curFilter };
})();
