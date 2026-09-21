/** view.js —— 相机 + 输入 + 屏幕纸片。游戏和编辑器共用。
 *
 * ══ 输入模型（踩过坑，别改回去）══
 *
 * 按下的那一刻就问上层："这个点你要不要接？"
 *
 *     onDown(世界点) → true   上层接了（拖房子 / 画路）→ 之后所有 move 都给它
 *                    → false  没接 → **默认就是平移相机**
 *
 * 之前的写法是"移动超过 4px 就转交上层"，结果是：相机一旦动了 4px
 * 就再也不动了（拖动 = 一卡一卡），而画路又永远等不到 pointerdown。
 * 两个 bug 同一个根因：**把"拖"和"点"当成了互斥的两种模式**。
 * 它们不是 —— 拖是默认，上层可以抢。
 *
 * ══ 相机 ══
 *   cam = {x, y, k}：x,y 是【视口左上角对应的世界坐标】。
 *   #world 的 transform = translate(-x·k, -y·k) scale(k)
 *   默认铺满视口（cover），四周不露底 —— 原型就是这个行为。
 *
 * ══ 纸片 ══
 * 名字/气泡是 **DOM**，不进 canvas。它们在表达"这条信息有多旧"，那是规则不是
 * 美术（art-direction §三 L6/L7）。位置每帧用世界→屏幕投影算，所以缩放仍跟着目标。
 */
import { Application, Container } from '../vendor/pixi.min.mjs';

export const U = 12;                       // 1 世界单位 = 12 px

export class View {
  constructor(canvasEl, hudEl) {
    this.el = canvasEl;
    this.hud = hudEl;
    this.cam = { x: 0, y: 0, k: 1 };
    this.minK = 0.1; this.maxK = 6;
    this.world = { w: 1280 * U, h: 800 * U };   // 像素
    this.onDown = null;    // (wx, wy) => bool   上层要不要接这次按下
    this.onDrag = null;    // (wx, wy) => void
    this.onUp = null;      // (wx, wy) => void
    this.onPick = null;    // (wx, wy) => void   纯点击（没被 onDown 接走、也没平移）
    this.onHover = null;   // (wx, wy) => void
    this.onContext = null; // (wx, wy) => void  右键（右键不当拖动的起点）
    this.onView = null;    // () => void          相机变了（重画屏幕纸片）
    this.app = new Application();
  }

  async init(bg = 0x6d8a52) {
    await this.app.init({
      canvas: this.el, background: bg, antialias: true,
      resolution: Math.min(devicePixelRatio || 1, 2), autoDensity: true,
    });
    this.root = new Container();
    this.worldLayer = new Container();
    this.overlay = new Container();
    this.root.addChild(this.worldLayer, this.overlay);
    this.app.stage.addChild(this.root);
    this.resize();
    // ★ 用 ResizeObserver 而不是 window.resize：
    //   编辑器那块 canvas 在 Pixi init 时还是 display:none（初始 hidden），
    //   clientWidth = 0 → Pixi 退回默认 800×600 → 相机算出来的 k 一路被夹到最小，
    //   整个画面尺寸全错。ResizeObserver 在元素"变成可见且有尺寸"时会再响一次。
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(this.el.parentElement || document.body);
    this._input();
    return this;
  }

  /** 显式量父元素并设 canvas 尺寸。父元素没有尺寸时什么都不做（等 ResizeObserver）。 */
  resize() {
    const p = this.el.parentElement || document.body;
    const w = Math.max(1, Math.round(p.clientWidth));
    const h = Math.max(1, Math.round(p.clientHeight));
    if (p.clientWidth === 0 || p.clientHeight === 0) return;   // 还藏着的，别把尺寸写成 1×1
    if (this.app.renderer.width !== w * this.app.renderer.resolution
        || this.app.renderer.height !== h * this.app.renderer.resolution) {
      this.app.renderer.resize(w, h);
    }
    this.el.style.width = w + "px";
    this.el.style.height = h + "px";
    this.apply();
  }
  viewport() { return [this.app.renderer.width / this.app.renderer.resolution,
                       this.app.renderer.height / this.app.renderer.resolution]; }
  setWorld(canvas) { this.world = { w: canvas.w * U, h: canvas.h * U }; }

  // ── 相机 ────────────────────────────────────────────────────────────
  /** 把 cam 写进 transform。
   *
   *  ★ 以前这里先写 transform 再 clamp，而 clamp 会改 cam ——
   *    于是渲染用夹【前】的相机，toWorld / screenOf 用夹【后】的 cam，
   *    两边不是同一个数。症状是"名牌跑偏""缩放会漂"。
   *    现在不夹相机了（见下面），这个坑也就不存在了 ——
   *    但顺序仍然保持：**只有一处写 cam，写完立刻同步 transform**。
   */
  apply() {
    const { x, y, k } = this.cam;
    this.root.scale.set(k);
    this.root.position.set(-x * k, -y * k);
    this.onView?.();
  }
  /** ★ 故意【不夹】相机。
   *
   *  试过两种夹法，都会和"缩放锚在鼠标上"打架：
   *    · 夹在世界内        → 世界比视口小时可平移区间是负的，相机被钉死
   *    · 只在世界比视口大时夹 → k=0.1 时 sx/k = 3000px，照样夹到边界
   *  而夹到边界的那一刻，锚点必然漂 —— 用户要的是"锚点永远准"。
   *
   *  所以不夹，换来的是锚点在任何倍率都精确。代价是能平移出世界之外，
   *  用 `F`（铺满）或「我的店」一键回来就够。
   */
  /** ★ 铺满视口（cover），不留边距 —— 这就是"画面铺满整个窗口"。 */
  fill(zoomOut = 1) {
    const [vw, vh] = this.viewport();
    const { w, h } = this.world;
    const k = Math.max(vw / w, vh / h) * zoomOut;
    this.centerOn(w / U / 2, h / U / 2, k);
  }
  centerOn(wx, wy, k) {
    if (k) this.cam.k = Math.min(this.maxK, Math.max(this.minK, k));
    const [vw, vh] = this.viewport();
    this.cam.x = wx * U - vw / this.cam.k / 2;
    this.cam.y = wy * U - vh / this.cam.k / 2;
    this.apply();
  }
  /** 每帧调一次：把缩放平滑逼近目标。返回 true = 相机动了（调用方该重画屏幕纸片）。 */
  step() {
    const z = this._zT;
    if (!z) return false;
    // ★★ 锚点必须【在改 k 之前】算。
    //    先改 k 再 toWorld，等于用"新 k + 旧相机"去反推鼠标下的世界点 ——
    //    算出来的已经不是原来那个点了，于是每帧漂一点点，滚轮一多就漂飞。
    //    （测过：14 次滚轮累到 25 世界单位。）
    const [wx, wy] = this.toWorld(z.sx, z.sy);
    if (Math.abs(z.k - this.cam.k) < this.cam.k * 0.002) {
      this.cam.k = z.k; this._zT = null;
    } else {
      this.cam.k += (z.k - this.cam.k) * 0.22;        // 每帧逼近 22% —— 平滑而非突变
    }
    this.cam.x = wx * U - z.sx / this.cam.k;          // 把那个世界点重新钉回鼠标下
    this.cam.y = wy * U - z.sy / this.cam.k;
    this.apply();
    return true;
  }

  toWorld(sx, sy) {
    const { x, y, k } = this.cam;
    return [(x + sx / k) / U, (y + sy / k) / U];
  }
  screenOf(wx, wy) {
    const { x, y, k } = this.cam;
    return [(wx * U - x) * k, (wy * U - y) * k];
  }

  // ── 输入 ────────────────────────────────────────────────────────────
  _input() {
    const el = this.el;
    let down = null;
    el.addEventListener("pointerdown", e => {
      if (e.button === 2) return;            // 右键交给 onContext
      const r = el.getBoundingClientRect();
      const w = this.toWorld(e.clientX - r.left, e.clientY - r.top);
      const grabbed = !!this.onDown?.(w[0], w[1]);
      down = { sx: e.clientX, sy: e.clientY, cx: this.cam.x, cy: this.cam.y,
               moved: 0, grabbed, w0: w };
      try { el.setPointerCapture(e.pointerId); } catch { /* 丢了就算了 */ }
      el.style.cursor = grabbed ? "grabbing" : "move";
    });
    el.addEventListener("pointermove", e => {
      const r = el.getBoundingClientRect();
      const w = this.toWorld(e.clientX - r.left, e.clientY - r.top);
      if (!down) { this.onHover?.(w[0], w[1]); return; }
      down.moved = Math.max(down.moved, Math.hypot(e.clientX - down.sx, e.clientY - down.sy));
      if (down.grabbed) { this.onDrag?.(w[0], w[1]); return; }   // 上层接了 → 一直给它
      if (down.moved > 3) {                                      // 没接 → 平移
        this.cam.x = down.cx - (e.clientX - down.sx) / this.cam.k;
        this.cam.y = down.cy - (e.clientY - down.sy) / this.cam.k;
        this.apply();
      }
    });
    const end = (e) => {
      if (!down) return;
      const r = el.getBoundingClientRect();
      const w = this.toWorld(e.clientX - r.left, e.clientY - r.top);
      const d = down; down = null;
      el.style.cursor = "crosshair";
      try { el.releasePointerCapture(e.pointerId); } catch { /* 同上 */ }
      if (d.grabbed) this.onUp?.(w[0], w[1]);          // 上层接了自己收尾
      else if (d.moved <= 3) this.onPick?.(w[0], w[1]); // 没动过 = 一次点击
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    el.addEventListener("contextmenu", e => {
      e.preventDefault();                    // 别弹系统菜单
      const r = el.getBoundingClientRect();
      this.onContext?.(...this.toWorld(e.clientX - r.left, e.clientY - r.top));
    });
    el.addEventListener("wheel", e => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const sx = e.clientX - r.left, sy = e.clientY - r.top;
      // ★ 不直接改 k，只记一个目标：真正的缩放在 step() 里逐帧逼近。
      //   滚轮一格 Δk 很大，直接跳过去是"突变"；而且一帧到位会把
      //   锚点算错（相机在夹边界上时尤其明显 —— 所以干脆不夹）。
      const want = (this._zT?.k ?? this.cam.k)
        * Math.exp(-e.deltaY * 0.0016);
      this._zT = { k: Math.min(this.maxK, Math.max(this.minK, want)), sx, sy };
    }, { passive: false });
  }

  // ── 屏幕纸片（DOM）────────────────────────────────────────────────
  /** dy 是【屏幕像素】的固定偏移 —— 千万别用世界单位。
   *  用世界单位的话偏移会跟着缩放放大：0.8 世界单位在 k=6 时是 57px，
   *  名牌看着就"脱离画布"了。 */
  paper(id, text, wx, wy, cls = "bubble", dy = 0) {
    this._paper ||= new Map();
    let el = this._paper.get(id);
    if (text == null) { el?.remove(); this._paper.delete(id); return null; }
    if (!el) {
      el = document.createElement("div");
      el.className = cls;
      this.hud.appendChild(el);
      this._paper.set(id, el);
    }
    if (el.textContent !== text) el.textContent = text;
    el.dataset.w = wx; el.dataset.h = wy; el.dataset.dy = dy;
    return el;
  }
  dropPaper(id) { this._paper?.get(id)?.remove(); this._paper?.delete(id); }
  clearPaper() { for (const id of [...(this._paper?.keys() || [])]) this.dropPaper(id); }
  syncPaper() {
    if (!this._paper) return;
    for (const el of this._paper.values()) {
      const [x, y] = this.screenOf(+el.dataset.w, +el.dataset.h);
      const dy = +el.dataset.dy || 0;
      el.style.transform = `translate(${x}px,${y + dy}px) translate(-50%,-100%)`;
    }
  }
}
