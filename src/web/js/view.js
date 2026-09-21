/** view.js —— 相机 + 输入 + 屏幕空间的纸片。游戏和编辑器共用。
 *
 * 抽出这一个是因为两边要"看起来是同一个东西"：
 *   拖动平移 · 滚轮缩放（★ 锚在鼠标）· 点选 · 纸片贴在世界坐标上
 * 各写一份的话，迟早会一边能拖一边不能，一边锚鼠标一边锚中心。
 *
 * 分层：
 *   app.stage
 *     └ root（相机作用在这一层）
 *         ├ world   ← 地图画这里（MapLayer.root）
 *         └ overlay ← 编辑手柄画这里（游戏里空着）
 *   纸片（名字/气泡/提示）是 **DOM**，不进 canvas —— 它们在表达"信息有多旧"，
 *   那是规则，不是美术（见 art-direction §三 L6/L7）。
 */
import { Application, Container } from '../vendor/pixi.min.mjs';

export const U = 12;                        // 1 世界单位 = 12 px

export class View {
  constructor(canvasEl, hudEl) {
    this.el = canvasEl;
    this.hud = hudEl;
    this.app = new Application();
    this.cam = { x: 0, y: 0, zoom: 1 };
    this.onPick = null;                     // (worldX, worldY) => void（已排除拖动）
    this.onHover = null;                    // (worldX, worldY) => void
    this.onDrag = null;                     // (worldX, worldY) => void —— 拖动中
    this.onDrop = null;                     // () => void —— 松手（拖动结束）
    this.minZoom = 0.1; this.maxZoom = 8;
  }

  async init(bg = 0x6d8a52) {
    await this.app.init({
      canvas: this.el, background: bg, antialias: true,
      resolution: Math.min(devicePixelRatio || 1, 2), autoDensity: true,
      resizeTo: this.el.parentElement,
    });
    this.root = new Container();
    this.world = new Container();
    this.overlay = new Container();
    this.root.addChild(this.world, this.overlay);
    this.app.stage.addChild(this.root);
    this._input();
    return this;
  }

  // ── 相机 ────────────────────────────────────────────────────────────
  apply() {
    this.root.scale.set(this.cam.zoom);
    this.root.position.set(this.cam.x, this.cam.y);
  }
  viewport() {
    const r = this.app.renderer;
    return [r.width / r.resolution, r.height / r.resolution];
  }
  centerOn(wx, wy, zoom) {
    if (zoom) this.cam.zoom = zoom;
    const [vw, vh] = this.viewport();
    this.cam.x = vw / 2 - wx * U * this.cam.zoom;
    this.cam.y = vh / 2 - wy * U * this.cam.zoom;
    this.apply();
  }
  fit(canvas, pad = 70) {
    const [vw, vh] = this.viewport();
    const z = Math.min((vw - pad) / (canvas.w * U), (vh - pad) / (canvas.h * U));
    this.centerOn(canvas.w / 2, canvas.h / 2, Math.max(this.minZoom, z));
  }
  toWorld(sx, sy) {
    const s = this.root.scale.x, p = this.root.position;
    return [(sx - p.x) / s / U, (sy - p.y) / s / U];
  }
  /** 世界坐标 → 屏幕（CSS 像素）。纸片定位用。 */
  screenOf(wx, wy) {
    const s = this.root.scale.x, p = this.root.position;
    return [wx * U * s + p.x, wy * U * s + p.y];
  }

  _input() {
    const el = this.el;
    let drag = null, moved = 0;
    el.addEventListener("pointerdown", e => {
      drag = { x: e.clientX, y: e.clientY, cx: this.cam.x, cy: this.cam.y };
      moved = 0;
      try { el.setPointerCapture(e.pointerId); } catch { /* 已经丢了就算了 */ }
    });
    el.addEventListener("pointermove", e => {
      const r = el.getBoundingClientRect();
      const w = this.toWorld(e.clientX - r.left, e.clientY - r.top);
      if (!drag) { this.onHover?.(w, e); return; }
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      moved = Math.max(moved, Math.hypot(dx, dy));
      if (moved > 4) { this.onDrag?.(w); return; }   // ★ 拖动交给上层（编辑器要挪房子）
      this.cam.x = drag.cx + dx; this.cam.y = drag.cy + dy; this.apply();
    });
    el.addEventListener("pointerup", e => {
      try { el.releasePointerCapture(e.pointerId); } catch { /* 同上 */ }
      const dragged = moved > 4;
      drag = null;
      if (dragged) { this.onDrop?.(); return; }
      const r = el.getBoundingClientRect();
      this.onPick?.(...this.toWorld(e.clientX - r.left, e.clientY - r.top));
    });
    el.addEventListener("wheel", e => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const sx = e.clientX - r.left, sy = e.clientY - r.top;
      const before = this.toWorld(sx, sy);
      const k = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      this.cam.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, this.cam.zoom * k));
      this.apply();
      const after = this.toWorld(sx, sy);        // ★ 缩放锚在鼠标：把鼠标下的世界点钉住
      this.cam.x += (after[0] - before[0]) * U * this.cam.zoom;
      this.cam.y += (after[1] - before[1]) * U * this.cam.zoom;
      this.apply();
    }, { passive: false });
  }

  // ── 屏幕空间的纸片（DOM）────────────────────────────────────────────
  /** 一个贴在世界坐标上的小纸片。id 相同就复用，不会每帧新建节点。 */
  paper(id, text, wx, wy, cls = "bubble") {
    let el = this._paper?.get(id);
    if (!this._paper) this._paper = new Map();
    if (text == null) { el?.remove(); this._paper.delete(id); return null; }
    if (!el) {
      el = document.createElement("div");
      el.className = cls;
      this.hud.appendChild(el);
      this._paper.set(id, el);
    }
    if (el.textContent !== text) el.textContent = text;
    el.dataset.w = wx; el.dataset.h = wy;
    return el;
  }
  dropPaper(id) { this._paper?.get(id)?.remove(); this._paper?.delete(id); }
  syncPaper() {
    if (!this._paper) return;
    for (const el of this._paper.values()) {
      const [x, y] = this.screenOf(+el.dataset.w, +el.dataset.h);
      el.style.left = x + "px"; el.style.top = y + "px";
    }
  }
  clearPaper() { for (const id of [...(this._paper?.keys() || [])]) this.dropPaper(id); }
}
