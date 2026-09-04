# elm_lane · 榆树巷 大场景沙盒 —— 实现规格

状态：设计定稿（scope 已拍板）→ 待实现。
范围（拍板结论）：
- ❌ 不做经济/金钱/价格/工地上班（超市·食堂·便利店 = 免费吃源）。
- ✅ travel 距离矩阵、open_hours、pulses（场景脉冲）。
- ✅ 只保留 `elm_lane` 单一场景，无下拉。
- ❌ 不引入公共设施跨房如厕（各家自有设施足够）。

## 一、场景与加载器契约

`config/scenes/elm_lane.json` 定义一张地图。`gateway/scenarios.py` 退化为
通用加载器 `load_scene(path)`，不再手搓 Entity/NPC。

### 实体
```json
{"type":"<item_type>","at":"<location_id>","id":"<entity_id>",
 "stock":<int>?, "open_hours":"<HH:MM-HH:MM,...>"?}
```
- `type` 必须是 `config/items/*.json` 里的 `item_type`（M4 数据化规矩）。
- 装载：`itemdefs.load_item_defs()` + `entity_from_def(...)` + `world.spawn_entity`，
  scene 字段（stock/open_hours）覆盖 def 默认。
- `open_hours`：省略=全天；`"06:00-09:00,11:00-14:00"`=多窗口；`"closed"`/`[]`=永久关闭。

### NPC
```json
{"id":"npc_wang","name":"王二","home":"apt_101","start":"apt_101",
 "archetype":"worker","hour":<初相位0..24>?,
 "signals":{...}?,"personality":{...}?,
 "knowledge":[{"subject":"...","relation":"sells|contains|located_at",
               "obj":"...","conf":0.95}]}
```
- `knowledge` 以 INJECTED 注入，用于种子：跨区觅食地理、过时信念（触发改道/谣言）。
- 全局 `tell_p` 由 scene 顶层给。

### 移动距离
- `travel.default`（兜底 ticks）+ `travel.pairs`：`"from|to": ticks`（对称，
  loader 补反向）。替代原单值 `move_ticks`（保留作 default）。

### 脉冲 pulses（世界侧确定性脚本，按 tick 触发）
```json
{"at":"daily 07:30","op":"set_stock","target":"canteen_1","value":40}
{"at":"day 3 10:00","op":"close_forever","target":"canteen_1"}
```
- `at`：`daily HH:MM`（每日）或 `day N HH:MM`（第 N 天一次）。
- op：`set_stock` / `close_forever`(=永久 closed) /（可扩 `set_open`）。

## 二、引擎地基（Phase B）

1. **travel 矩阵**：`SimConfig`/Systems 持有 per-pair 距离；`run_tick` 生成
   `Travel` 时按 `(from,to)` 查表（loader 注入到 Systems.travel_ticks），缺省
   `move_ticks`。
2. **open_hours 门控**：Entity 增 `open_hours`；`build_percept` 判定当前是否营业
   —— 关/停 = 对该 NPC 呈现为 `stock==0`（stock_zero）且不可 claim。效果：
   NPC 去已关/停业的店 → OBSERVED 空 → `refute`（知识变旧）→ 改道其它食源。
3. **pulses 引擎**：挂进主循环（每 tick 开头查一次触发表）；改实体 stock/open，
   保证确定性；仅供世界观驱动知识失效（无需广播，感知自然发现）。

## 三、榆树巷认知展示矩阵（每个点对应一个体现）
| 地点 | 角色 | 体现 |
|---|---|---|
| apt_101 王二家 | 节律正常 | 生活节律、感知建库、本地吃（自家冰箱→便利店近食） |
| apt_102 李四家 | 冰箱空 | “自家有食”原型扑空 → refute → 靠外部 |
| apt_103 合租 | 张三+赵五 | 同房争厕/低库存冰箱 = claim 仲裁 |
| plaza 街心 | 闲人 2-3 | bench/社交 + TOLD 温床 |
| canteen 食堂 | day3 停业 | 全巷“食堂有食”→ 扑空 → tombstone → 改道 market/shop24（★核心剧情）|
| market 大超市 | day5 断货一天 | 已知真源再失效 → 次优（便利店）→ 谣言与反复 |
| arcade 棋牌室 | 乐子 | mahjong affords fun → OBSERVED → gossip 目标 |

## 四、文件清单
- ✅ Phase A：`config/items/{bench,shelf_meal,canteen_counter,market_shelf,mahjong}.json`
- Phase A：`config/scenes/elm_lane.json`（新建，含名册/pulses）
- Phase B：`src/citysim/world/world.py`(Entity.open_hours)、`perception.py`(营业门控)、
  `sim/loop.py`(travel 查表+pulses 挂载)、`sim/pulses.py`(新)、`core/config.py`(travel 承载)
- Phase C：`gateway/scenarios.py`→`load_scene`；`gateway/server.py`(单场景参数/去下拉)；
  `gateway/snapshot.py`(hello 用 scene canvas/locations)
- Phase D：前端 index.html 去下拉；受影响测试重指；回归。
