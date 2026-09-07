/**
 * Camera.ts —— pan(drag) / zoom(wheel, 锚定鼠标) / reset(fit world)。
 * 只管 world↔screen 变换; 不含任何 simulation 语义。
 */
import type { Container } from 'pixi.js';

const MIN_ZOOM = 0.15;
const MAX_ZOOM = 8;
const PAD = 24;

export class Camera {
  private zoom = 1;
  private tx = 0;
  private ty = 0;
  private viewW = 0;
  private viewH = 0;

  constructor(private readonly root: Container) {}

  resize(w: number, h: number): void {
    this.viewW = Math.max(1, w);
    this.viewH = Math.max(1, h);
    this.apply();
  }

  fitWorld(worldW: number, worldH: number): void {
    if (worldW <= 0 || worldH <= 0) return;
    const z = Math.max(0.1, Math.min(
      (this.viewW - PAD * 2) / worldW,
      (this.viewH - PAD * 2) / worldH,
      MAX_ZOOM,
    ));
    this.zoom = Math.max(MIN_ZOOM, z);
    this.tx = (this.viewW - worldW * this.zoom) / 2;
    this.ty = (this.viewH - worldH * this.zoom) / 2;
    this.apply();
  }

  reset(): void {
    this.fitWorld(this.lastWorldW, this.lastWorldH);
  }

  private lastWorldW = 1280;
  private lastWorldH = 800;

  apply(): void {
    this.root.scale.set(this.zoom);
    this.root.position.set(this.tx, this.ty);
  }

  get scale(): number {
    return this.zoom;
  }

  screenToWorld(sx: number, sy: number): { x: number; y: number } {
    return {
      x: (sx - this.tx) / this.zoom,
      y: (sy - this.ty) / this.zoom,
    };
  }

  worldToScreen(wx: number, wy: number): { x: number; y: number } {
    return { x: wx * this.zoom + this.tx, y: wy * this.zoom + this.ty };
  }

  panBy(dx: number, dy: number): void {
    this.tx += dx;
    this.ty += dy;
    this.apply();
  }

  zoomAt(factor: number, sx: number, sy: number, worldW = 1280, worldH = 800): void {
    this.lastWorldW = worldW;
    this.lastWorldH = worldH;
    // 保持鼠标下的世界点不动
    const wx = (sx - this.tx) / this.zoom;
    const wy = (sy - this.ty) / this.zoom;
    const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, this.zoom * factor));
    this.zoom = next;
    this.tx = sx - wx * this.zoom;
    this.ty = sy - wy * this.zoom;
    this.apply();
  }
}
