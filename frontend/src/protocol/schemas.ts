/**
 * schemas.ts —— 与 docs/observation_contract.md 对齐的后端数据契约(只读镜像)。
 * 不定义 backend 当前不存在的 required 字段; 可能为空的显式 T | null。
 */

export const PROTOCOL_VERSION = 1;

// ---------------------------------------------------------------------------
// 基础
// ---------------------------------------------------------------------------
export type SourceKind = 'INJECTED' | 'OBSERVED' | 'TOLD' | 'INFERRED';

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LocationInfo extends Rect {
  name: string;
  kind: string;
}

export interface CanvasInfo {
  w: number;
  h: number;
}

export interface HelloLocations {
  canvas: CanvasInfo;
  locations: Record<string, LocationInfo>;
}

export interface EntitySnapshot {
  id: string;
  name: string;
  loc: string;
  tags: string[];
  stock: number;
  claimed_by?: string | null;
  icon?: string;
  shelf_index?: number;
  position: [number, number] | null;
  // TASK004-ext: 只读静态属性/效果(itemdef/scene 已存在)
  affordances?: Record<string, number>;
  price?: number;
  owner?: string;
  duration_ticks?: number;
  attrs?: Record<string, unknown>;
  on_start?: Array<Record<string, unknown>>;
  on_complete?: Array<Record<string, unknown>>;
}

export interface ActiveInteraction {
  entity: string;
  remaining: number;
  total: number;
}

export interface TravelSnapshot {
  from: string;
  to: string;
  depart: number;
  arrive: number;
}

export interface TraceFact {
  id: string;
  subject: string;
  relation: string;
  obj: unknown;
  confidence: number;
  source_kind: string;
  source_ref: string[];
  tick: number;
}

export interface RankedOption {
  id: string;
  score: number;
}

export interface IntentSnapshot {
  kind: string;
  target: string | null;
  reason: string | null;
  ranked: RankedOption[];
  relevant_signals: [string, number][];
  used_facts: TraceFact[];
}

export interface LastPercept {
  tick: number;
  loc: string;
  position: [number, number];
  observed: string[];
}

export interface KbEdge {
  src: string;
  dst: string;
  relation: string;
  confidence: number;
  source_kind: SourceKind;
  tick: number;
}

export interface KbNode {
  id: string;
  label: string;
  kind: string;
}

export interface KnowledgeData {
  nodes: KbNode[];
  edges: KbEdge[];
}

export interface KbCounts {
  overlay: number;
  tombstones: number;
  archetype: number;
}

// ---------------------------------------------------------------------------
// Event(ui_events 条目 + canonical: type/source/target/event_id)
// ---------------------------------------------------------------------------
export interface EventData {
  event_id?: string;
  tick: number;
  type?: string;
  kind?: string;              // legacy: type 的别名
  subject?: string | null;    // legacy: source 的别名
  source?: string | null;
  target?: string | null;
  intent?: string;            // decision 特有(legacy)
  payload: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Snapshot / NPC
// ---------------------------------------------------------------------------
export interface NPCSnapshot {
  id: string;
  name: string;
  loc: string;
  position: [number, number];
  archetype: string;
  activity: string;
  act_class: string;
  signals: Record<string, number>;
  active: ActiveInteraction | null;
  travel: TravelSnapshot | null;
  intent: IntentSnapshot | null;
  last_percept: LastPercept | null;
  kb: KnowledgeData;
  kb_counts: KbCounts;
  events: EventData[];
}

export interface Snapshot {
  type: string;
  tick: number;
  day: number;
  hour_f: number;
  clock: string;
  speed: string;
  running: boolean;
  tps: number;
  entities: EntitySnapshot[];
  npcs: NPCSnapshot[];
  events: EventData[];   // TASK002 后恒空; 事件走独立 kind=event
}

export interface HelloMessage {
  type: string;
  protocol: number;
  scenario: string;
  seed: number;
  n_npc: number;
  kb_mode: string;
  tell_p: number;
  signals: string[];
  locations: HelloLocations;
}

// ---------------------------------------------------------------------------
// WS Envelope(TASK002)
// ---------------------------------------------------------------------------
export interface Envelope<T = unknown> {
  kind: string;
  protocol_version: number;
  payload: T;
}

export type AnyMessage =
  | Envelope<HelloMessage>
  | Envelope<Snapshot>
  | Envelope<EventData>
  | Envelope<ReplyPayload>
  | Envelope<unknown>;

export interface ReplyPayload {
  type: string;
  req_id?: number | string;
  ok: boolean;
  data: unknown;
  why?: string | null;
}

// 事件类型全集(contract 明确支持)
export const EVENT_TYPES = [
  'decision', 'perceived', 'learned', 'told', 'bought',
  'interaction_done', 'intent_failed', 'stock_changed', 'npc_died',
] as const;
export type EventType = (typeof EVENT_TYPES)[number];
