/**
 * interpolation.ts —— 纯视觉插值。interpolation 只是表现处理, 不是 simulation。
 */
export interface Vec2 {
  x: number;
  y: number;
}

export function v2(x: number, y: number): Vec2 {
  return { x, y };
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function lerpVec(a: Vec2, b: Vec2, t: number): Vec2 {
  return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) };
}

export function dist(a: Vec2, b: Vec2): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * 帧率无关平滑系数: alpha=1-exp(-dt*k)。dt 秒。视觉跟随, 不改任何后端状态。
 */
export function frameAlpha(dtMs: number, k: number): number {
  return 1 - Math.exp(-(dtMs / 1000) * k);
}
