# CitySim Observation Contract (TASK002)

> 后端 → Observatory 前端 的唯一数据契约。simulation 是唯一真相源；
> 前端只消费 Snapshot / Event / Trace，不得自行推断 perception/knowledge/decision。

## 1. 消息 Envelope（WS 全消息统一外壳）

```json
{
  "kind": "snapshot | event | hello | reply | pong",
  "protocol_version": 1,
  "payload": { "...": "该 kind 的内容" }
}
```

- `protocol_version`：统一为 `1`（常量 `snapshot.PROTOCOL_VERSION`）。协议变化时递增。
- payload 内保留旧观察器兼容字段（如 `type`、`protocol`），新增 consumer 一律读 `kind`。
- 消息类型彼此独立，不混成一个模糊对象。

### 消息种类

| kind | payload 内容 |
|---|---|
| `hello` | 场景/seed/n_npc/kb_mode/tell_p/signals/locations(几何) |
| `snapshot` | 当前 tick 世界状态(见 §2) |
| `event` | 单条 Event(见 §3)；每 tick 产生的每条事件独立推送 |
| `reply` | query 请求的应答(req_id/ok/data) |

## 2. Snapshot ——「当前世界状态」

Snapshot 表示某一个 tick 的现状；**不含事件流、不含历史/因果**。
事件统一走 `event` 消息。

顶层字段（payload）：
```
protocol_version, tick, day, hour_f, clock, speed, running, tps,
entities[], npcs[], events=[]   # events 恒空(事件已独立); 各 NPC.events 为近况
```

`entities[]`：id, name, loc, tags, stock, claimed_by, icon, shelf_index, position(x,y|null)

`npcs[]` 至少：
```
id, name, loc, position[x,y], archetype, activity, act_class,
signals{0..1}, active, travel{from,to,depart,arrive},
intent{kind,target,reason,ranked,relevant_signals,used_facts},
last_percept{tick,loc,position,observed[]},
kb{nodes,edges}, kb_counts{overlay,tombstones,archetype}, events(近况50)
```

## 3. Event ——「刚刚发生了什么」

canonical（`snapshot.encode_event`，只加不删，保留旧字段）：
```
event_id, tick, type, source, target(无则 null), payload{...}
```

事件类型（现有全集，禁止删）：

| type | 来源 | 关键 payload |
|---|---|---|
| `perceived` | loop(重评感知后) | observed_entity_ids, location_id, position |
| `learned` | loop(新 fact_id 产生时) | fact_id, subject, relation, obj, source_kind, confidence |
| `decision` | loop(每次重评) | intent, target (event_id=dec:tick:npc) |
| `told` | loop(gossip) | audience, from, subject, relation, obj, conf, origin, fact_id, short |
| `bought` | loop(_execute_buy) | item, price, home, money |
| `npc_died` | loop(_kill) | name, loc |
| `intent_failed` | interaction/loop | target, why |
| `interaction_done` | interaction | entity |
| `stock_changed` | pulses | op, stock_before, stock_after (audience=[]) |

语义：
- `perceived`/`learned`/`stock_changed`：observer 向事件(`audience=[]`，不塞 NPC 信箱)。
- 事件按 `tick` 稳定有序；同 tick 按 EventBus 产生顺序，不做额外排序。
- 旧字段保留（`kind`=type、`subject`=source、`intent`/`target` 等），供旧观察器零改读取。

## 4. Trace ——「NPC 为什么这么决定」

Trace 是**解释数据结构**，不是决策算法本身（未来可换 utility/rule/state-machine）。

最小字段（`DecisionTrace`，TASK001 已结构化）：
```
trace: {
  reason,            # explanation(人类可读)
  ranked,            # considered_options: [(entity_id, score)...] 降序
  relevant_signals,  # [(signal, need=1-value)...] 降序
  used_fact_ids,     # relevant_knowledge 溯源(经 export_trace_chain 展开成事实树)
}
```
- `considered_options` = `ranked`；`selected_option`/`decision` 由 intent 的 kind+target 表达。
- 尚未单独序列化的条目：`relevant_knowledge` 展开树 = query `npc_detail` / `trace` 的 `used_facts`。
- 交付通道：① snapshot 随选中 NPC 的 `intent`；② `query{what:npc_detail|trace}` 应答(`reply`)。

## 5. 数据流

```
simulation
  → EventBus / systems.ui_events(单源, attach_replay)
  → gateway.drain_log()   → envelope(kind=event, …)
  → build_snapshot()      → envelope(kind=snapshot, …)
  → WebSocket client
```

- 不新建第二套 bus；不实现 generic world diff。
- gateway 只做 serialize/validate/broadcast，不做 decision/perception/mutation。
