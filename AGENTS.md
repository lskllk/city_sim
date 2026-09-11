# AGENTS.md — pi 定位向导

`sim_city` = `citysim`：确定性、数据驱动的城市/NPC 认知模拟内核。
本文用于帮 pi 依据需求快速定位文件。数据/规则大量从 JSON 导入，Python 只做解释与组装，改动优先改数据。

> 依赖红线：`npc/` 严禁 `import citysim.world`(违者 CI 挂，见 `tests/test_import_layers.py`)。

## 目录树与职责

```
src/citysim/
  core/config.py     SIGNALS 信号全集 + SimConfig(读 config/sim.toml)
  core/types.py      NPC↔世界数据契约(frozen+slots) + 意图多态 Intent=Idle|MoveTo|Interact|Buy
  core/ids.py        占位(空)

  npc/person.py      Person 门面: signals 单一真源 + 计划表执行/中断仲裁 + 失败日志
  npc/brain.py       decide() 兜底 reflex 纯函数(fallback_need 触发; 节律已删)
  npc/schedule.py    PlanEntry + Schedule(当天 (at_tick, Intent) 脚本)
  npc/planner.py     LLM 日计划生成器(PlannerInput 纯数据 + 规则模板降级 + 缓存/校验)

  world/world.py     World 容器 + Entity + itemdef→Entity(世界唯一事实源)
  world/buildings.py 建筑类型库(config/buildings) + 面积∝容量 自动布局
  world/names.py     中文姓名池(config/names) + 生成规则(姓+名, id=拼音)
  world/itemdefs.py  config/items/*.json 校验+加载(ItemDef)
  world/effects.py   副作用 op 表 + apply_effects
  world/interaction.py InteractionSystem: 执行/claim/affordance 推进/消耗/睡眠唤醒
                       + abort(硬中止)/suspend/resume(reflex 抢占高保真恢复)
  world/perception.py 建 Percept + 感知→记忆写入
  world/events.py    EventBus 事件→NPC 信箱
  world/drive.py     执行驱动: 每 tick 所有非旅行 NPC 决策(交互中也跑, 供抢占)

  sim/loop.py        run_tick 唯一推进入口 + Travel + 购物成交 + 传闻gossip
  sim/pulses.py      世界侧定时脚本(set_stock/close_forever)
  sim/lod.py, sim/soa.py, nn/*(features/modulator) = M7/M8 占位(空)

  gateway/server.py  FastAPI+WS, SimRunner 独占推进(纯读观察器)
  gateway/scenarios.py 场景装配(读 scenes/elm_lane.json)
  gateway/snapshot.py 纯读 world→JSON 快照/query(禁 build_percept/碰 rng)
  viz/kb_export.py   知识图 JSON/DOT 导出
  viz/trace_export.py 决策追溯链导出

config/
  sim.toml            魔法数字(改数值首选这里)
  items/*.json        物品定义(含副作用 on_start/on_complete)
  buildings/*.json    建筑类型库(kind/capacity/pattern/aspect)
  names/names.json    姓名池(姓/名, hanzi+pinyin)
  scenes/elm_lane.json 单场景装配: locations(只写 type)/entities/npcs/travel/pulses
  (无 archetypes/: 出生空白记忆, NPC 特质/初始记忆走场景 memory 段或建居民接口)

tests/
  helpers.py          搭最小 world 的辅助(make_runtime/add_npc/add_entity)
  test_*.py           内核/契约测试; test_behavior_soak.py=7天行为安全网
  test_import_layers.py  层隔离检查(0.2); test_replay.py=seed 固定回放
tools/
  demo_scene.py       build_demo/build_scarce 可复现 demo 世界(测试/观察共用)
  watch.py/narrate.py/soak*.py/scarcity_check/check_imports  观测统计

godot/                独立 Godot 4 观察器前端(方案A: 只读订阅 gateway /ws)
  scenes/*.tscn       静态布局/组件/世界可视(Node2D可视化实例), 编辑器可直接改
  resources/*.tres     字体(CJK/Emoji)+主题
  scripts/net/         ws_client(Net autoload)+commands(Commands autoload)
  scripts/state/       store.gd(Store autoload): 只读镜像 world/sim/selection
  scripts/render/      world_canvas + camera/map/entity/overlay 层, *_visual
  scripts/ui/          inspector + components/* + fonts/zh/emojis
  (铁律: Godot 只渲染/发命令, 不计算 simulation; 见 godot/README.md)
```

## 主要调用关系

```
config/sim.toml          core/config.py → SimConfig(进所有 run_tick/decide)
config/items/*.json      world/itemdefs.py ──> world/world.py::entity_from_def → Entity
                         └─ on_start/on_complete → world/effects.py::apply_effects
config/scenes/elm_lane.json → gateway/scenarios.py::load_scene → (World+Systems+rng_pool)

run_tick(sim/loop.py):
  1 代谢 person.apply_metabolism + hp
  → 排泄 → 交互 InteractionSystem.step
  → 决策: build_percept(perception) + perceive(obs→记忆)
              → decide: 致命 reflex > 计划表 > idle (docs/task006.md)
              → 仲裁执行: 继续/挂起(suspend)/硬中止(abort)/提交/旅行
  → 每日 KB.decay(knowledge)

观察器(gateway): SimRunner 独占跑 run_tick → snapshot.build_snapshot(纯读 world)
                 → WS 推给前端; query 走 snapshot.do_query
Godot 观察器(godot/): Net 收 envelope → main.dispatch → Store(镜像) → WorldCanvas/Inspector
                 UI 经 Commands.cmd 发 set_speed/step/reset
```

数据契约(core/types.py)是 NPC/世界间桥梁：世界造 `Percept`，brain 读它产出 `Intent`，
交互侧消费 `Intent`；其中 `used_fact_ids` 供 knowledge.trace 追溯。
新增意图/契约当先看 `core/types.py`(同时同步 `sim/loop.py` 与 `brain.py`)。
