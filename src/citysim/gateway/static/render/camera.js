/* camera.js —— 一次性 fit + 世界↔屏幕换算。canvasrecode.md 第 2 节。
   铁律：Camera.fit 只在 hello/reset/resize 调用；update()/draw() 一律不许写 camera。 */
"use strict";

const Camera = (() => {
  let s = 1, ox = 0, oy = 0, dpr = 1;
  let fitted = false;

  // cssRect: canvas 的 CSS 像素矩形
  function fit(rooms, cssRect) {
    const box = Layout.bbox(rooms), pad = 40;
    const W = box.w + 2 * pad, H = box.h + 2 * pad;
    s = Math.min(cssRect.width / W, cssRect.height / H);
    s = Math.max(0.25, Math.min(2.0, s));
    ox = (cssRect.width - W * s) / 2 - (box.x0 - pad) * s;
    oy = (cssRect.height - H * s) / 2 - (box.y0 - pad) * s;
    fitted = true;
  }

  // draw 开头调一次：设备像素基座 + 世界→屏幕
  function applyTo(ctx) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.translate(ox, oy);
    ctx.scale(s, s);
  }

  // 输入 CSS 像素（相对画布左上）→ 世界坐标
  function toWorld(px, py) { return { x: (px - ox) / s, y: (py - oy) / s }; }

  function setDpr(v) { dpr = v; }
  return { fit, applyTo, toWorld, setDpr,
           get: () => ({ s, ox, oy, dpr }), isFitted: () => fitted };
})();
