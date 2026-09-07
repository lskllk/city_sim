/**
 * EntityRenderer.ts —— NPC / 建筑内实体渲染与命中(全在 Pixi 侧)。
 *
 * 实体: 在所属建筑(room)内按顺序摆放, 显示 emoji ICON(snapshot.icon 由后端 tag 推导);
 * 鼠标悬浮文字说明交给上层(DOM hover)。NPC: 位置来自 snapshot 并做纯视觉平滑。
 */
import { Container, Graphics, Text, TextStyle } from 'pixi.js';
import type { NPCSnapshot, EntitySnapshot, LocationInfo } from '../../protocol/schemas';
import { dist, frameAlpha, lerp, type Vec2 } from '../../simulation/interpolation';

const NPC_RADIUS = 7;
const ENT_ICON_SIZE = 17;
const ENT_FALLBACK = '▪';

const ICON_STYLE = new TextStyle({
  fontFamily: 'system-ui, "Segoe UI Emoji", "Apple Color Emoji", sans-serif',
  fontSize: ENT_ICON_SIZE,
  fill: 0xffffff,
  stroke: 0x000000,
  strokeThickness: 1.5,
});

const NPCS_COLORS = [
  0x5bb0ff, 0xffb35c, 0x5bd6a0, 0xee7d9a, 0xc08bff,
  0x79e0e0, 0xf0e05e, 0xff8a5c, 0xa0d96b, 0xffd1dc,
];

interface NpcVisual {
  c: Container;
  body: Graphics;
  ring: Graphics | null;
  target: Vec2;
  cur: Vec2;
  color: number;
}

interface EntVisual {
  c: Container;
  base: Graphics;
  icon: Text | null;
  target: Vec2;
  id: string;
}

function tagColor(e: { tags?: string[] }): number {
  const t = e.tags ?? [];
  if (t.includes('edible') || t.includes('food')) return 0x7ed58a;
  if (t.includes('sleepable')) return 0x8f9fd8;
  if (t.includes('toilet')) return 0x5bc9c9;
  if (t.includes('drink')) return 0x69a8f0;
  if (t.includes('entertain') || t.includes('fun')) return 0xb78beb;
  if (t.includes('work')) return 0xd0b26a;
  return 0x55637c;
}

export class EntityRenderer {
  private readonly npcLayer = new Container();
  private readonly entLayer = new Container();
  private npcVis = new Map<string, NpcVisual>();
  private entVis = new Map<string, EntVisual>();

  constructor(readonly parent: Container) {
    parent.addChild(this.entLayer);
    parent.addChild(this.npcLayer);
  }

  private npcColor(id: string): number {
    let h = 0;
    for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
    return NPCS_COLORS[h % NPCS_COLORS.length];
  }

  /** 结构 reconcile; rooms 用于给实体在其建筑内按顺序排位。 */
  reconcile(npcs: Record<string, NPCSnapshot>,
            entities: Record<string, EntitySnapshot>,
            rooms: Record<string, LocationInfo>): void {
    for (const id of [...this.npcVis.keys()]) {
      if (!npcs[id]) {
        const v = this.npcVis.get(id);
        if (v) {
          this.npcLayer.removeChild(v.c);
          v.c.destroy({ children: true });
        }
        this.npcVis.delete(id);
      }
    }
    for (const id of Object.keys(npcs)) {
      const n = npcs[id];
      if (!this.npcVis.has(id)) {
        const color = this.npcColor(id);
        const body = new Graphics();
        body.beginFill(color, 0.92);
        body.lineStyle(1, 0xffffff, 0.75);
        body.drawCircle(0, 0, NPC_RADIUS);
        body.endFill();
        const c = new Container();
        c.addChild(body);
        this.npcLayer.addChild(c);
        const start = toVec(n.position);
        this.npcVis.set(id, {
          c, body, ring: null, target: start, cur: start, color,
        });
      }
    }

    // 建筑内实体: 增删 + 在所属 room 内按顺序摆放(icon)
    for (const id of [...this.entVis.keys()]) {
      if (!entities[id]) {
        const v = this.entVis.get(id);
        if (v) {
          this.entLayer.removeChild(v.c);
          v.c.destroy({ children: true });
        }
        this.entVis.delete(id);
      }
    }
    for (const id of Object.keys(entities)) {
      const e = entities[id];
      if (this.entVis.has(id)) continue;
      const c = new Container();
      const base = new Graphics();
      base.beginFill(tagColor(e), 0.92);
      base.lineStyle(1, 0xffffff, 0.35);
      base.drawRoundedRect(-10, -10, 20, 20, 5);
      base.endFill();
      c.addChild(base);
      let icon: Text | null = null;
      try {
        icon = new Text(e.icon || ENT_FALLBACK, ICON_STYLE);
        icon.anchor.set(0.5, 0.5);
        c.addChild(icon);
      } catch {
        icon = null;                      // glyph 失败也不中断整批
      }
      this.entLayer.addChild(c);
      const target = { x: 0, y: 0 };
      this.entVis.set(id, { c, base, icon, target, id });
    }
    this.layoutEntities(entities, rooms);
  }

  /** 按 room 顺序(优先 snapshot shelf_index, 否则 id 排序)把实体排成一行。 */
  private layoutEntities(entities: Record<string, EntitySnapshot>,
                         rooms: Record<string, LocationInfo>): void {
    const byRoom = new Map<string, EntitySnapshot[]>();
    for (const e of Object.values(entities)) {
      const list = byRoom.get(e.loc) ?? [];
      list.push(e);
      byRoom.set(e.loc, list);
    }
    for (const [locId, list] of byRoom) {
      const rect = rooms[locId];
      const ordered = [...list].sort((a, b) =>
        (a.shelf_index ?? 1e9) - (b.shelf_index ?? 1e9) || a.id.localeCompare(b.id));
      if (!rect) {
        // 建筑矩形缺失: 回退到后端真实坐标(防叠到原点/不显示)
        for (const e of ordered) {
          const v = this.entVis.get(e.id);
          if (!v) continue;
          const p = toVec(e.position);
          v.target = p;
          v.c.position.set(p.x, p.y);
        }
        continue;
      }
      const count = ordered.length;
      const step = Math.min(40, (rect.w - 20) / Math.max(1, count));
      const startX = rect.x + rect.w / 2 - ((count - 1) * step) / 2;
      const y = rect.y + rect.h - 16;                 // 建筑内靠下的一行
      ordered.forEach((e, i) => {
        const v = this.entVis.get(e.id);
        if (!v) return;
        const x = startX + i * step;
        v.target = { x, y };
        v.c.position.set(x, y);
      });
    }
  }

  /** 每帧: NPC 平滑跟随 + 选中环(纯表现)。 */
  update(dtMs: number, selectedId: string | null): void {
    const alpha = frameAlpha(dtMs, 10);
    for (const [id, v] of this.npcVis) {
      const n = (v as NpcVisual);
      const t = n.target;
      if (selectedId === id) {
        if (!n.ring) {
          const ring = new Graphics();
          ring.lineStyle(2, 0xffd24d, 1);
          ring.drawCircle(0, 0, NPC_RADIUS + 5);
          ring.endFill();
          n.c.addChild(ring);
          n.ring = ring;
        }
      } else if (n.ring) {
        n.c.removeChild(n.ring);
        n.ring.destroy();
        n.ring = null;
      }
      n.cur.x = lerp(n.cur.x, t.x, alpha);
      n.cur.y = lerp(n.cur.y, t.y, alpha);
      n.c.position.set(n.cur.x, n.cur.y);
    }
  }

  /** snapshot 到达: NPC 目标更新; 实体位置由 reconcile 的顺序摆放决定。 */
  applyTargets(npcs: Record<string, NPCSnapshot>,
               _entities: Record<string, EntitySnapshot>): void {
    for (const [id, n] of Object.entries(npcs)) {
      const v = this.npcVis.get(id);
      if (!v) continue;
      v.target = toVec(n.position);
    }
  }

  /** 命中: 世界坐标处的 npc id。 */
  pick(wx: number, wy: number): string | null {
    let best: string | null = null;
    let bestDist = Infinity;
    for (const [id, v] of this.npcVis) {
      const d = dist({ x: wx, y: wy }, v.cur);
      if (d < 14 && d < bestDist) {
        best = id;
        bestDist = d;
      }
    }
    return best;
  }

  /** 命中: 世界坐标处的实体 id(图标范围)。 */
  pickEntity(wx: number, wy: number): string | null {
    let best: string | null = null;
    let bestDist = Infinity;
    for (const [id, v] of this.entVis) {
      const d = dist({ x: wx, y: wy }, { x: v.c.x, y: v.c.y });
      if (d < 14 && d < bestDist) {
        best = id;
        bestDist = d;
      }
    }
    return best;
  }

  destroy(): void {
    this.npcLayer.destroy({ children: true });
    this.entLayer.destroy({ children: true });
  }
}

function toVec(p: [number, number] | null): Vec2 {
  return { x: p ? p[0] : 0, y: p ? p[1] : 0 };
}
