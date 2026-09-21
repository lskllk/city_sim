"""api —— citysim 内核【唯一的公开门面】。

这个文件是"读到哪儿为止"的答案。**门外的代码只许 import 这里导出的名字**:

    from citysim import api                      # ✓ 唯一正确的进法
    from citysim.world.econ.market import ...    # ✗ 绕过门面, 视为违规

谁算"门外":

    citysim/game/**   游戏服务端层        ← 只许 from citysim import api
    tools/**          开发仪器            ← 同上
    仓库外的一切       别的项目 / 别人的代码  ← 同上

谁算"门内"(可以不经过 api):

    core/ npc/ world/ sim/ gateway/       内核自身, 直接 import 兄弟模块

为什么 gateway/ 不能 import api: `api` 本身依赖 `gateway.scenarios` 和
`gateway.snapshot` —— 反过来 import 就是循环。所以 gateway/ 是内核的一部分
(纯数据桥: 场景装载 + 快照投影), 不是消费者。
且 `game/` 不在门面上: api 是【内核】的公开面, game 在内核之上 ——
api 永远不许 import game(有测试看着)。

## 四条规则

1. **门面的形状由消费者决定, 不由内核目录结构决定。**
   分组按"我要干什么"(推进 / 认知 / 经营 / 观测), 不按文件路径。
   所以改内核目录不会打断游戏侧的 import。

2. **只导出有真实消费者的名字, 或明确属于契约的名字。**
   - 有消费者 = `game/` 或 `tools/` 已经在用(见 `tests/test_api.py` 的覆盖测试)
   - 属于契约 = 两个口的词汇(`Work`/`Wage`… 与 `Bought`/`WagePaid`…)
     和五个动词(`Idle`/`MoveTo`/`Interact`/`Buy`/`Wander`)
   其余一律不加 —— 想加先拿出消费者。**门面小才守得住。**

3. **门面本身零第三方依赖。** 内核是零依赖的, `import citysim.api`
   不得拉进 fastapi / uvicorn(那些只在 `game/server.py` 里,
   属于 viz extra)。有测试守着。

4. **门面不许 import `citysim.game`。** api 是内核的公开面, game 在它之上。
   一旦 api 反向依赖 game, 包就变成一团。有测试守着。

## 它不导出什么

- 内核内部推理产物(`Percept` / `DecisionTrace` / `Decision` / `EntityView`)
  —— 没人在门外需要它们。
- `gateway.server`(FastAPI 应用) —— 它依赖 viz extra, 会破坏规则 3。
  (它已经搬到 `game/server.py` —— 游戏服务端不属于内核。)
- `citysim.game.*` —— 见规则 4。
- 任何 `_` 开头的实现细节。

需要新东西时: 在下面找到对应的分组加一行, 写清楚"谁在用", 然后跑
`pytest tests/test_api.py`。
"""
from __future__ import annotations

# ── 配置 ────────────────────────────────────────────────────────────────
# 数值与内容全在 config/ 里; 这里只给"怎么读进来"。
from citysim.core.config import SIGNALS, SimConfig, load_config

# ── 契约: 两个口 + 五个动词 ─────────────────────────────────────────────
# 这是内核对外唯一的"语言"。改这里等于改协议, 要谨慎。
#
#   assign(cmd)  人对 NPC 下令【你以后照这个做】(绑定与承诺)
#   notify(ev)   世界对 NPC 说事实【发生了什么】(NPC 自己决定怎么改自己)
#
# 消费者: 老板面板 / 玩家化身 / 以后的任务系统都从这组名字发货。
from citysim.core.types import (
    # assign: 身份与义务
    Plan,
    Role,
    Shift,
    Unwork,
    Wage,
    Work,
    # notify: 世界说发生了什么
    Bought,
    InteractionDone,
    InteractionFailed,
    ItemGone,
    WagePaid,
    # 五个动词: NPC(含玩家)能对世界做的全部请求
    Buy,
    Idle,
    Interact,
    MoveTo,
    Wander,
    # 动词的读法(前端只读, 不解析)
    intent_kind,
    intent_target,
    # 表达层的接口: 内核产出结构化事件, 台词由【游戏层】渲染
    # (game/lines.py 是当前唯一的消费者)
    SemanticEvent,
)

# ── 推进: 世界的时钟 ────────────────────────────────────────────────────
# 确定性推进的唯一入口。attach_replay 用于录制/回放(世界指纹可校验)。
from citysim.sim.loop import Systems, attach_replay, make_systems, run_tick

# ── 世界: 容器与实体 ────────────────────────────────────────────────────
from citysim.world.world import Entity, World, entity_from_def

# ── 世界模型: 建筑 / 道路 / 物件定义 ────────────────────────────────────
# 场景侧的"世界长什么样"。编辑器导出的几何要经这里变成可跑的世界。
from citysim.world.model.buildings import build_locations
from citysim.world.model.itemdefs import load_item_defs
from citysim.world.model.roads import RoadGraph

# ── 认知: 人 ───────────────────────────────────────────────────────────
# Person 是门面(聚合根)。玩家化身就是接管某个 Person 的 decide()。
from citysim.npc.person import Identity, Person, signals_as_percent
from citysim.npc.planner import ScriptedPlanner

# ── 经济: 公司 ─────────────────────────────────────────────────────────
# 公司 = 经济单位(它的 cash 是账; 店铺属于它; 工资从它出)。
# 类型由建筑定死: 店铺→零售 / 工厂→制造。
from citysim.world.model.companies import Company, kind_for_building

# ── 经营动词: 老板面板 / 老板 NPC 用 ───────────────────────────────────
# 全部【只改世界真值】, 不做任何模拟计算 —— 决策在 NPC 侧。
#   purchase  向批发市场进货, 上架到自己的某家店
#   decorate  给自己的店摆一件装修件(柜台/工位/机器…), 从公司账出钱
#   hire_at   招聘桥接(每天一次; 只撮合【发布了招聘启事】的公司)
#   assign_station  把员工分派到某个销售台(""=撤销)
#   schedule_worker 给某员工排班(只改他自己的班次, 不动公司营业时间)
#   vacant_counters 还有哪些空台
from citysim.world.econ.company import (
    assign_station,
    hire_at,
    schedule_worker,
    vacant_counters,
)
from citysim.world.econ.market import (
    decorate,
    fixture_catalog,
    market_catalog,
    market_places,
    purchase,
)
from citysim.world.econ.shop import COUNTER_ITEM, staffed_counters

# ── 场景: JSON → 可跑的世界 ─────────────────────────────────────────────
# 编辑器导出的 scene JSON 经此变成 (World + Systems + rng)。
# 加载器只组装, 不做决策。
from citysim.gateway.scenarios import (
    DEFAULT_SCENE,
    build_scenario,
    default_scene_path,
    load_scene,
)

# ── 观测: 世界 → JSON(给前端) ──────────────────────────────────────────
# 游戏契约的落地点(demo-plan §六): 读一个 NPC / 问一个 NPC / 事件编码。
# 快照里【不该给玩家看的东西, 一个字都不能发】—— 上帝版与发行版的差别
# 是数据源, 不是 UI。裁剪在服务端做。
from citysim.gateway.snapshot import (
    PROTOCOL_VERSION,
    build_npc_state,
    build_snapshot,
    do_query,
    encode_event,
    envelope,
    hello_payload,
)

# ── 观测: 读世界的只读小工具 ───────────────────────────────────────────
from citysim.emojis import SEMANTIC_EMOJI
from citysim.world.run.engine import act_class_of


__all__ = [
    # 配置
    "SIGNALS", "SimConfig", "load_config",
    # 契约: assign
    "Plan", "Role", "Shift", "Unwork", "Wage", "Work",
    # 契约: notify
    "Bought", "InteractionDone", "InteractionFailed", "ItemGone", "WagePaid",
    # 契约: 动词
    "Buy", "Idle", "Interact", "MoveTo", "Wander",
    "intent_kind", "intent_target", "SemanticEvent",
    # 推进
    "Systems", "attach_replay", "make_systems", "run_tick",
    # 世界
    "Entity", "World", "entity_from_def",
    # 世界模型
    "build_locations", "load_item_defs", "RoadGraph",
    # 认知
    "Identity", "Person", "signals_as_percent", "ScriptedPlanner",
    # 经济
    "Company", "kind_for_building",
    # 经营动词
    "assign_station", "hire_at", "schedule_worker", "vacant_counters",
    "decorate", "fixture_catalog", "market_catalog", "market_places", "purchase",
    "COUNTER_ITEM", "staffed_counters",
    # 场景
    "DEFAULT_SCENE", "build_scenario", "default_scene_path", "load_scene",
    # 观测
    "PROTOCOL_VERSION", "build_npc_state", "build_snapshot", "do_query",
    "encode_event", "envelope", "hello_payload",
    "SEMANTIC_EMOJI", "act_class_of",
]
