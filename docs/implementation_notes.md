# TASK001 实施记录

> 按 task001.md：非阻塞问题记录于此，不阻塞主流程。冻结设计优先于本文件判断。

## 已确认非阻塞观察项

1. **NPC↔NPC 感知仍走 region 共在（gossip 圈）**。距离感知只作用于「跨 region 的实体」；
   `perception_radius` 语义是"邻居/街区近距"，不生成 NPC-NPC 距离感知。属未来任务。

2. **travel 途中不感知**（冻结设计 #6 维持）：位置连续，但 percept/decision 仍只在重评点发生。
   "路上撞见/半路社交"需后续单独加"travel 感知窗"任务。

3. **`perceived` 事件未发布**，改为 `Person.last_percept`(PerceptionRecord) 单份最近感知随
   snapshot 暴露。理由：同 region 可见集几乎每评不变，逐评广播噪声大；需要历史流时再补。

4. **`learned` 事件只在新 overlay 事实(新 fact_id)产生时发**；同键 upsert 刷新/强化不发
   （避免每次重评重复广播）。若要观察"置信度刷新"，需再开一个事件通道。

5. **world_delta 最小化**：只为 pulses `set_stock/close_forever` 补了 `stock_changed`
   (audience=[]，只进日志/UI 流)；bought/interaction_done/npc_died 复用既有事件，未建 diff 引擎。

6. **半径取值依赖 elm_lane 尺度**：perception=100 / interaction=30（scene 单位）。两户中心距
   >300，故稳态跨区感知基本不发生（刻意保守，保行为不回退）；同区恒可见/可交互不变。
   若未来地图改大/缩小或引入"街距可见"需求，应先校半径。

7. **实体锚点 = region 内 id 哈希**(确定性、与数量/顺序无关、防搬家抖动)。视觉上允许重叠；
   需要真实摆位时在 scene json 给 entity 写显式 `position`（优先级高于自动锚点）。

8. **买回家重排锚点**：`_execute_buy` 置 `ent.position=None` 后重 layout 目标 region；
   无几何世界(helpers/纯 region 字符串)下 no-op，语义不变。

9. **旧前端(static/) 会见到新字段**(npc.position/archetype/last_percept/intent.relevant_signals、
   entity.position、事件 learned/stock_changed) —— 旧 JS 忽略未知字段与事件，不崩溃；
   展示层利用属 Observatory Phase 2，不在本任务范围。

10. **DecisionTrace.relevant_signals 只含「有缺口(need>0)且进入过候选」的信号**；
    结构化尚缺 selected_option 的显示级字段(可从 intent kind/target 派生)，未复制进 trace。

## 风险备注

- 距离感知生效条件 = 双方 region 都注册了几何 + 有坐标；无几何世界整体退回旧行为，
  因此老测试/无图世界行为不变 —— 这是"空间升级不破坏旧语义"的护栏，也是未来排障提示。

---

## TASK002 追加记录

1. **WS Envelope 变更已落地**：全部出站消息 = {kind, protocol_version:1, payload}。
   为兼容旧观察器，payload 内保留旧字段(type/protocol/intent/...)，且 static/app.js
   增加 3 行解包 + 事件消息路由(属于兼容性维护，非新前端)。
2. **事件不再内嵌 snapshot**：snapshot.events 恒为 []；事件逐条独立推送(kind=event)。
   旧全局事件流已由 app.js onEvent 承接；各 NPC 近况事件仍在 snapshot 的 npc[].events。
3. **perceived 事件每重评必发**(含相同可见集)，噪声可控(重评分钟级)但未做去重；
   若未来 100+ NPC 高频重评，需要节流/去重策略。
4. **learned 仍只在新 fact_id 时发**(TASK002 #9 冻结)；upsert 刷新不发。
5. **decision 无 event_id 的旧布局已补**：生产侧事件均带 event_id；drain 兜底 g{seq}。
6. **Trace 的 selected_option/relevant_knowledge 树**由 intent + query(trace/npc_detail)
   派生，未复制成独立 WS kind；若前端需要被动推送完整 trace，再做 kind=trace。

---

## TASK003 追加记录

1. **新增 frontend/**(React+TS+Vite+Zustand+PixiJS)，观察器 MVP：地图/实体/Pixi 渲染、
   NPC 平滑插值(纯表现)、选择→Inspector、事件流、工具栏/时间线、reconnect(backoff)。
2. **legacy gateway/static 保留未动**；新前端 dev 用 vite 代理 /ws→localhost:8765。
   默认后端端口与旧一致；若改端口设 VITE_WS_URL 或改 vite proxy。
3. **dev 冒烟已验证**：hello→snapshot(带 position)→event(decision/perceived/learned)
   全链路(经 vite ws 代理)。
4. 非阻塞观察：
   - Pixi v7 旧 API 差异(Application 同步构造/view 需转 Node)已就地兼容；
   - chunk >500k 告警(全部打进单 bundle)，后续可 dynamic import 拆分；
   - 事件日志在 React 侧每事件 set 一次(60Hz 量小，暂可)；量大需节流；
   - NPC 平滑为指数跟随(k=10)，在高倍速下轨迹有轻微拖尾(视觉仅表现)；
   - 未实现 query/npc_detail 的显式拉取(Inspector 数据全来自 snapshot 内嵌)；
     事件面板"选中 NPC 的实时近况"部分依赖下一帧 snapshot 同步。
   - 环境坑：旧 uvicorn 进程占用 8765 会导致新代码不生效 —— 重启前先杀端口。

---

## TASK004 追加记录

1. **纯 frontend 完成**(Inspector 行为解释层级 + 地图空间语义高亮 + 联动/空状态)。
2. backend 未改(字段足够; snapshot 含 intent.ranked/relevant_signals/used_facts)。
3. 新建纯函数解释层 `frontend/src/ui/Inspector/explain.ts`(无 React/store 依赖,
   可单测): narrative/stateLabel/needWord/orNa/action*。
4. 新增 vitest(dev, ^2.1.9, 兼容 vite5); `npm test` = vitest run; 6 个格式化/空态用例。
5. 遗留观察项:
   - “点击历史 decision → 还原当时 Why”不可行(无 seek/历史), 本版仅: 选中当前 NPC
     最新决策事件 & 滚动定位; Why 区展示的是“最近一次快照的 intent”。
   - 地图 target 连线是 npc.position→目标锚点(直线); 明确未命名为 navigation path。
   - All Knowledge/All Signals 默认折叠; Recent Events 默认 5 条 + Show more。
   - SimulationStage destroy 显式移除 canvas, 兼容 React StrictMode 双挂载。

---

## TASK005(最小空间图 Node/Edge)记录

1. **新增空间图**(backend): World.nodes/edges + SpatialNode{id,position,capacity}
   / SpatialEdge{id,from_node,to_node,width}; World.distance(a,b) 欧氏距离(不缓存,
   缺失节点→inf)。Entity/Person 增 node_id(默认随 region 镜像)。
2. **命名兼容决策**: scene 已占用顶层 `locations`(region 几何 dict), 因此 node 用
   独立顶层键 `nodes`/`edges`(数组)。节点 id 取 region id、position=region 中心,
   使 node_id 与 location_id 镜像、entity/npc 无需额外改表即可对号入座。
3. scene elm_lane 增 nodes(5)/edges(8); 运行时位置变更(buy 归家 / travel 到达)
   同步 node_id。
4. snapshot 增 nodes/edges 数组; 前端 schemas/worldStore 透传(仅存, 不渲染)。
5. 本 TASK 只搭最小空间闭环, 未做 pathfinding/travel 动画/traffic/physics
   (留给后续 TASK)。前端 UI/Pixi 未改。

---

## TASK006(沿边移动 + 极简 BFS 寻路)记录

1. **TravelState**(core/types): dest_node/route(有序 edge ids)/index/progress/speed;
   Person 持有 travel_state(None=未走)。旧 systems.travel/Travel(depart/arrive)
   已移除 —— 旅行改由"沿空间边逐 tick 推进 progress"承担。
2. 每 tick: progress += speed/edge_length; 边尾→下一条/到达; 到达置
   travel_state=None、node/location=dest、position=dest、尽快重评(不影响 brain)。
   位置统一计算: from.position + (to-from)*progress(不缓存)。
3. 路径: world/pathfinding.find_path(edges, start, end) 纯 BFS 无权; 不可达/无图
   → 降级立即落点防卡死。
4. snapshot 旅行改为 {edge, progress, from_node, to_node, dest_node};
   前端 schemas 已同步, 无渲染改动。
5. speed 入 config [motion] travel_speed=45(世界单位/tick)。
6. 迁移说明: 为与既有 node/region 兼容, 落点逻辑保持 node_id↔location_id 镜像;
   边端点 node 位置来自 TASK005 scene nodes(位置=region 中心)。

---

## TASK007(Spatial Observatory Frontend)记录

1. backend 仅补 npc snapshot 的 node_id(必需字段); 其余为前端。
2. 新增纯空间模块 frontend/src/spatial/: spatialTransform.ts(world↔canvas 比例/
   缩放/平移, 不写后端坐标) + layers/{NodeLayer,EdgeLayer,NpcLayer}.ts(纯布局)。
   Node 圆半径=base+sqrt(capacity), 恒定色(不按 id/type 上色); Edge 线宽=width。
3. 集成进既有 SimulationStage(非重做 UI): 在房间上/实体下新增 graphG 画边+节点;
   加 hoverAt/focusNpc/focusAtWorld; NPC 已按 backend position 沿道路平滑移动
   (travel 不自行插速度)。
4. WorldView 增: 左 NPC rail(名+状态, 点击 focus 选中)、空间 hover tooltip
   (Node: id/capacity/实体数/NPC数; NPC: id/node/intent/travel from→to/progress)。
5. 测试: frontend/src/spatial/spatial.test.ts(11 例)覆盖 Node/Edge 布局、共享端点
   连接、progress 坐标转换、fit/zoom/pan 比例保持、snapshot 更新→布局变化。

---

## TASK007(精简观察界面/聚焦世界)记录

1. 纯前端; backend 未改。目标 = “城市观察窗”, 收敛掉管理面板。
2. 布局: App 只保留 `WorldView + Inspector`(grid 1fr + 400px)。Toolbar / EventStream /
   Timeline 文件仍在(能力保留)但不再渲染; 仅角落一个极小 transport(▶/⏸ + 连接点
   + 复位), 不加时钟/seed/tick 状态栏。
3. WorldView 收敛: 移除 NPC rail 与顶部 HUD; hover 只在小点上出现; 移动仍可用。
4. Inspector 收敛成单一 4 区: Status(信号条) / Decision(决策候选+score) /
   Cognitive Memory(KB edges, 来源/置信) / Event Log(近况)。对象与建筑给最小状态。
5. Renderer: 建筑=容器矩形(只一个克制小标签, 去掉 id/kind 文字); 物件=小圆点
   重新显示在建筑容器内(不再因“散落”而全隐藏); NPC 去掉常驻名字标签(仅 hover/
   选中提示); 交互中 NPC→Object 画淡琥珀连线(纯表现, 不改变 simulation)。
6. 旧多层/多标签观察器文件(Why/Knowledge Graph 等)保留未使用, 便于需要时复用。

---

## TASK004-ext(Location/Entity 可视化)记录

1. **最小只读 contract 扩充**(无语义改动): snapshot.entities[] 增加
   affordances/price/owner/duration_ticks/attrs/on_start/on_complete —— 均为
   runtime Entity/ itemdef 已存在数据, 仅导出供展示。pytest/serializable 未回归。
2. **点击拾取升级**: NPC→实体(方块)→地点(矩形)→空白平移; 一次只选中一类。
3. **新增分派侧栏 Inspector.tsx**: NPC(原) / Location / Entity 检查器。
4. Location 检查器: name/kind/尺寸 + occupants(可跳选 NPC) + 本地实体(可跳选)。
5. Entity 检查器: name/标签/location/使用中/库存/时长/价格/归属/position +
   affordance 属性 + attrs + on_start/on_complete effects(op/字段/值)。
6. 地图: location 增 semantic label(kind: 住宅/公寓/商店/集市/工作/公共);
   OverlayRenderer 支持非 NPC 选中高亮(地点/实体).
7. 空状态与防 undefined 沿用 explain.orNa 约定; UI 不再展示 undefined/null。

---

## ⚠️ REVERT(回退到 task005 之前)
用户判定 task005(空间图 Node/Edge)、task006(沿边移动 TravelState/BFS)、task007(空间前端)
为错误决策, 已全部撤销:
- 后端恢复 TASK001 region 连续位置旅行(legacy Travel depart/arrive lerp);
  node_id/SpatialNode/SpatialEdge/World.nodes/edges/distance(travel_speed/TravelState/pathfinding) 移除。
- 场景 elm_lane.json 移除 nodes/edges 数组。
- 前端移除 spatial 模块(transform/Node/Edge/NpcLayer)、节点+边+主干道渲染、
  graphG/hover/rail/focus、实体散落改 node 归属等; 恢复"房间矩形 + 实体方块/NPC圆 +
  overlay 选中高亮 + Inspector(NPC/Location/Entity)" 的 004-ext 呈现。
- 校验: backend pytest 113 passed; frontend vitest 6 passed; build PASS。
- 保留(不受回退影响): legacy gateway/static 删除、dev.sh/dev.cmd、README、004-ext 的
  Location/Entity 检查器与节点选择。上文 005/006/007 的记录仅供历史参考, 不代表当前代码。
