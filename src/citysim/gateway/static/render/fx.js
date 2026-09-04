/* fx.js —— 瞬态特效队列（canvasrecode.md 第 7 节）。
   push(kind, a, b?, data?)：a=主体 NPC id；arc 额外 b=对象；learn 带 data.short。
   update(dt) 每帧清过期；render 由 painter 的 Pass 6 读取 FX.list()。 */
"use strict";

const FX = (() => {
  let items = [];
  const TTL = { fail: 3.0, talk: 0.9, arc: 0.9, think: 0.35, learn: 1.6 };

  function push(kind, a, b, data) {
    items.push({ kind, a, b, born: performance.now(), data });
  }
  function has(kind, id) {
    return items.some(f => f.kind === kind && f.a === id);
  }
  function update() {
    const now = performance.now();
    items = items.filter(f => now - f.born < (TTL[f.kind] || 1));
  }
  function clear() { items = []; }
  return { push, has, update, clear, list: () => items, TTL };
})();
