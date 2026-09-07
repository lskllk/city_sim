/**
 * SimulationStage.ts —— 装配 Pixi: stage + camera + map + entities + overlay + 输入。
 * React 只负责挂载与销毁; 渲染/拾取/相机全在这里。
 */
import { Application, Container } from 'pixi.js';
import { Camera } from './Camera';
import { MapRenderer } from './MapRenderer';
import { EntityRenderer } from './EntityRenderer';
import { OverlayRenderer, type OverlayInput } from './OverlayRenderer';
import { useWorldStore } from '../../state/worldStore';
import { useSelectionStore } from '../../state/selectionStore';

export interface StageCallbacks {
  onPick?: (kind: 'npc' | 'location' | 'entity' | null, id: string | null) => void;
}

export class SimulationStage {
  private app: Application | null = null;
  private camera: Camera | null = null;
  private map: MapRenderer | null = null;
  private ents: EntityRenderer | null = null;
  private overlay: OverlayRenderer | null = null;
  private worldRoot = new Container();
  private lastRender = 0;
  private panning = false;
  private lastPX = 0;
  private lastPY = 0;
  private destroyed = false;

  constructor(private readonly mount: HTMLElement,
              private readonly cb: StageCallbacks) {
    if (this.destroyed) return;
    const app = new Application({
      background: 0x0a0d12,
      antialias: true,
      resizeTo: this.mount,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    });
    this.mount.appendChild(app.view as unknown as Node);
    this.app = app;
    app.stage.addChild(this.worldRoot);

    this.camera = new Camera(this.worldRoot);
    this.map = new MapRenderer(this.worldRoot);
    this.ents = new EntityRenderer(this.worldRoot);
    this.overlay = new OverlayRenderer(this.worldRoot);
    this.camera.resize(app.screen.width, app.screen.height);

    this.attachInput(app);
    this.lastRender = performance.now();
    app.ticker.add(this.frame);
    this.refreshWorld();
  }

  private frame = (): void => {
    if (!this.app) return;
    const now = performance.now();
    const dt = Math.min(64, now - this.lastRender);
    this.lastRender = now;
    this.refreshWorld();
    const st = useSelectionStore.getState();
    const npcId = st.kind === 'npc' ? st.selectedNpcId : null;
    this.ents?.update(dt, npcId);
    this.overlay?.update(overlayInputOf());
  };

  private refreshWorld(): void {
    const ws = useWorldStore.getState();
    if (ws.npcs === this.lastNpcs && ws.entities === this.lastEntities) return;
    this.lastNpcs = ws.npcs;
    this.lastEntities = ws.entities;
    this.map?.rebuild(ws.rooms, ws.canvas);
    this.ents?.reconcile(ws.npcs, ws.entities, ws.rooms);
    this.ents?.applyTargets(ws.npcs, ws.entities);
    if (this.camera && ws.canvas) {
      const key = `${ws.canvas.w}x${ws.canvas.h}`;
      if (key !== this.fittedKey) {
        this.fittedKey = key;
        this.camera.fitWorld(ws.canvas.w, ws.canvas.h);
      }
    }
  }

  private lastNpcs: Record<string, unknown> | null = null;
  private lastEntities: Record<string, unknown> | null = null;
  private fittedKey = '';

  resetView(): void {
    const ws = useWorldStore.getState();
    if (this.camera && ws.canvas) {
      this.camera.fitWorld(ws.canvas.w, ws.canvas.h);
    }
  }

  private attachInput(app: Application): void {
    const view = app.view as unknown as HTMLCanvasElement;
    view.style.cursor = 'grab';
    view.style.touchAction = 'none';

    const onDown = (ev: PointerEvent): void => {
      if (!this.camera) return;
      const rect = view.getBoundingClientRect();
      const sx = ev.clientX - rect.left;
      const sy = ev.clientY - rect.top;
      const wp = this.camera.screenToWorld(sx, sy);
      const ws = useWorldStore.getState();
      const npcId = this.ents?.pick(wp.x, wp.y) ?? null;
      if (npcId) {
        this.cb.onPick?.('npc', npcId);
        return;
      }
      const entId = this.ents?.pickEntity(wp.x, wp.y) ?? null;
      if (entId) {
        this.cb.onPick?.('entity', entId);
        return;
      }
      const locId = this.map?.hitTest(wp.x, wp.y, ws.rooms) ?? null;
      if (locId) {
        this.cb.onPick?.('location', locId);
        return;
      }
      this.cb.onPick?.(null, null);
      this.panning = true;
      this.lastPX = ev.clientX;
      this.lastPY = ev.clientY;
      view.style.cursor = 'grabbing';
    };

    const onMove = (ev: PointerEvent): void => {
      if (this.panning && this.camera) {
        this.camera.panBy(ev.clientX - this.lastPX, ev.clientY - this.lastPY);
        this.lastPX = ev.clientX;
        this.lastPY = ev.clientY;
      }
    };

    const onUp = (): void => {
      this.panning = false;
      if (view) view.style.cursor = 'grab';
    };

    const onWheel = (ev: WheelEvent): void => {
      if (!this.camera) return;
      ev.preventDefault();
      const rect = view.getBoundingClientRect();
      const sx = ev.clientX - rect.left;
      const sy = ev.clientY - rect.top;
      const ws = useWorldStore.getState();
      this.camera.zoomAt(ev.deltaY < 0 ? 1.15 : 1 / 1.15, sx, sy,
                         ws.canvas?.w, ws.canvas?.h);
    };

    const onDblClick = (): void => this.resetView();

    view.addEventListener('pointerdown', onDown);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    view.addEventListener('wheel', onWheel, { passive: false });
    view.addEventListener('dblclick', onDblClick);
    this.cleanupInput = () => {
      view.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      view.removeEventListener('wheel', onWheel);
      view.removeEventListener('dblclick', onDblClick);
    };
  }

  private cleanupInput: (() => void) | null = null;

  /** 相对 canvas 左上角: 命中的对象 kind+id(供悬浮说明)。 */
  hoverAt(sx: number, sy: number): { kind: 'npc' | 'entity' | 'location'; id: string } | null {
    if (!this.camera) return null;
    const wp = this.camera.screenToWorld(sx, sy);
    const npcId = this.ents?.pick(wp.x, wp.y) ?? null;
    if (npcId) return { kind: 'npc', id: npcId };
    const entId = this.ents?.pickEntity(wp.x, wp.y) ?? null;
    if (entId) return { kind: 'entity', id: entId };
    const ws = useWorldStore.getState();
    const locId = this.map?.hitTest(wp.x, wp.y, ws.rooms) ?? null;
    if (locId) return { kind: 'location', id: locId };
    return null;
  }

  destroy(): void {
    this.destroyed = true;
    this.cleanupInput?.();
    if (this.app) {
      this.app.ticker.remove(this.frame);
      const view = this.app.view as unknown as HTMLElement;
      if (view.parentNode) view.parentNode.removeChild(view);
      this.overlay?.destroy();
      this.ents?.destroy();
      this.map = null;
      this.ents = null;
      this.overlay = null;
      this.camera = null;
      this.worldRoot.destroy({ children: true });
      this.app.destroy(true, { children: true });
      this.app = null;
    }
  }
}

function overlayInputOf(): OverlayInput | null {
  const ws = useWorldStore.getState();
  const st = useSelectionStore.getState();
  if (st.kind === 'location' && st.selectedLocationId) {
    return { rooms: ws.rooms, focus: { kind: 'loc', locId: st.selectedLocationId } };
  }
  if (st.kind === 'entity' && st.selectedEntityId) {
    const e = ws.entities[st.selectedEntityId];
    if (!e) return null;
    return {
      rooms: ws.rooms,
      focus: { kind: 'entity', locId: e.loc,
               at: e.position ? { x: e.position[0], y: e.position[1] } : undefined },
    };
  }
  if (st.kind !== 'npc' || !st.selectedNpcId) return null;
  const npc = ws.npcs[st.selectedNpcId];
  if (!npc) return null;
  let target: OverlayInput['target'] = null;
  const tid = npc.intent?.target ?? null;
  if (tid) {
    if (ws.rooms[tid]) {
      target = { kind: 'loc', locId: tid };
    } else {
      const e = ws.entities[tid];
      if (e) {
        target = {
          kind: 'entity', locId: e.loc,
          at: e.position ? { x: e.position[0], y: e.position[1] } : undefined,
        };
      }
    }
  }
  return {
    curLoc: npc.loc,
    rooms: ws.rooms,
    target,
  };
}
