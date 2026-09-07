/**
 * MapRenderer.ts —— 用 hello 的 locations/canvas 画街区(第一版 rectangle/line/text)。
 */
import { Container, Graphics, Text, TextStyle } from 'pixi.js';
import type { CanvasInfo, LocationInfo } from '../../protocol/schemas';

const BG_FILL = 0x0d1016;
const ROOM_FILL = 0x1d2531;
const ROOM_STROKE = 0x3d4a60;
const TEXT_STYLE = new TextStyle({
  fontFamily: 'system-ui, "Microsoft YaHei", sans-serif',
  fontSize: 13,
  fill: 0xcfd6e3,
});

const KIND_ZH: Record<string, string> = {
  home: '住宅', apartment: '公寓', shop: '商店', market: '集市',
  work: '工作', public: '公共', site: '工地',
};

export function kindZh(kind: string): string {
  return KIND_ZH[kind] ?? kind;
}

export class MapRenderer {
  private readonly bg = new Container();
  private readonly rooms = new Container();
  private worldW = 1280;
  private worldH = 800;
  private lastRoomsKey = '';
  private lastCanvasKey = '';

  constructor(readonly parent: Container) {
    parent.addChild(this.bg);
    parent.addChild(this.rooms);
  }

  get worldSize(): { w: number; h: number } {
    return { w: this.worldW, h: this.worldH };
  }

  rebuild(rooms: Record<string, LocationInfo>, canvas: CanvasInfo): void {
    const canvasKey = `${canvas.w}x${canvas.h}`;
    const roomsKey = Object.keys(rooms).sort().join(',');
    if (canvasKey === this.lastCanvasKey && roomsKey === this.lastRoomsKey) {
      return;
    }
    this.lastCanvasKey = canvasKey;
    this.lastRoomsKey = roomsKey;
    this.worldW = canvas.w || 1280;
    this.worldH = canvas.h || 800;
    this.bg.removeChildren().forEach((c) => c.destroy({ children: true }));
    this.rooms.removeChildren().forEach((c) => c.destroy({ children: true }));

    const bg = new Graphics();
    bg.beginFill(BG_FILL);
    bg.drawRect(-2000, -2000, this.worldW + 4000, this.worldH + 4000);
    bg.endFill();
    this.bg.addChild(bg);

    for (const [id, loc] of Object.entries(rooms)) {
      const g = new Graphics();
      g.beginFill(ROOM_FILL, 0.35);
      g.lineStyle(1.5, ROOM_STROKE, 1);
      g.drawRoundedRect(loc.x, loc.y, loc.w, loc.h, 6);
      g.endFill();
      this.rooms.addChild(g);

      // 建筑: 只保留一个克制的小标签
      const label = new Text(loc.name || id, TEXT_STYLE);
      label.style.fontSize = 11;
      label.style.fill = 0x9fb0c4;
      label.anchor.set(0.5, 0.5);
      label.position.set(loc.x + loc.w / 2, loc.y + 12);
      this.rooms.addChild(label);
    }
  }

  /** 命中测试: 返回包含该世界点的 location id, 否则 null。 */
  hitTest(wx: number, wy: number, rooms: Record<string, LocationInfo>): string | null {
    for (const [id, r] of Object.entries(rooms)) {
      if (wx >= r.x && wx <= r.x + r.w && wy >= r.y && wy <= r.y + r.h) {
        return id;
      }
    }
    return null;
  }
}
