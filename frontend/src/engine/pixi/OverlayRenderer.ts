/**
 * OverlayRenderer.ts —— 空间语义反馈(纯展示):
 *   - NPC: 当前 location 高亮 + intent target 高亮(无箭头)
 *   - Location / Entity: 高亮所选地点 / 实体所在地点 + 实体标记
 */
import { Container, Graphics } from 'pixi.js';
import type { LocationInfo } from '../../protocol/schemas';

const CUR_COLOR = 0x3ddc84;
const TGT_COLOR = 0xffc24d;
const FOCUS_COLOR = 0x6fb7ff;

export interface VecPt { x: number; y: number }

export interface OverlayInput {
  rooms: Record<string, LocationInfo>;
  // NPC 视角
  curLoc?: string;
  target?: { kind: 'loc' | 'entity'; locId: string; at?: VecPt } | null;
  // 非 NPC 选中视角
  focus?: { kind: 'loc' | 'entity'; locId: string; at?: VecPt } | null;
}

export class OverlayRenderer {
  private readonly g = new Graphics();
  private lastKey = '';

  constructor(parent: Container) {
    this.g.alpha = 0.95;
    parent.addChild(this.g);
  }

  update(input: OverlayInput | null): void {
    const key = overlayKey(input);
    if (key === this.lastKey) return;
    this.lastKey = key;
    this.g.clear();
    if (!input) return;

    // 非 NPC 选中: focus
    if (input.focus) {
      const loc = input.rooms[input.focus.locId];
      if (loc) this.frameRect(loc, FOCUS_COLOR);
      if (input.focus.at) this.marker(input.focus.at, FOCUS_COLOR);
      return;
    }

    // NPC 视角: 高亮当前地点 + 目标(地点框 / 实体标记), 不画箭头
    if (input.curLoc) {
      const cur = input.rooms[input.curLoc];
      if (cur) this.frameRect(cur, CUR_COLOR);
    }
    if (input.target) {
      const loc = input.rooms[input.target.locId];
      if (loc) this.frameRect(loc, TGT_COLOR);
      if (input.target.at) this.marker(input.target.at, TGT_COLOR);
    }
  }

  private frameRect(rect: LocationInfo, color: number): void {
    this.g.lineStyle(2.5, color, 0.9);
    this.g.drawRoundedRect(rect.x, rect.y, rect.w, rect.h, 6);
  }

  private marker(p: VecPt, color: number): void {
    this.g.lineStyle(1, color, 0.95);
    this.g.beginFill(0x000000, 0);
    this.g.drawCircle(p.x, p.y, 7);
    this.g.endFill();
  }

  destroy(): void {
    this.g.destroy({ children: true });
  }
}

function overlayKey(input: OverlayInput | null): string {
  if (!input) return '';
  if (input.focus) {
    const at = input.focus.at;
    return `f${input.focus.locId}${at ? `:${at.x.toFixed(1)},${at.y.toFixed(1)}` : ''}`;
  }
  const t = input.target;
  return `${input.curLoc ?? ''}|`
    + (t ? `${t.kind}:${t.locId}:${t.at ? `${t.at.x.toFixed(1)},${t.at.y.toFixed(1)}` : ''}` : '');
}
