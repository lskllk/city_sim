"""TASK001 —— spatial observability: 连续位置 / 距离感知 / 交互门 / 事件化。"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.core.types import Buy, DecisionTrace, EntityView, Interact, Percept
from citysim.npc.knowledge import KnowledgeBase, Source
from citysim.npc.person import Identity, Person, full_signals
from citysim.sim.loop import _execute_buy, run_tick
from citysim.world.interaction import InteractionSystem
from citysim.world.perception import build_percept
from citysim.world.world import World

from helpers import add_entity, add_npc, make_runtime, seed_reviews

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")

HOME = {"home": {"x": 0.0, "y": 0.0, "w": 200.0, "h": 200.0,
                 "kind": "home", "name": "家"}}
PARK = {"park": {"x": 300.0, "y": 0.0, "w": 200.0, "h": 200.0,
                 "kind": "public", "name": "小公园"}}
DUO = {**HOME, **PARK}


def _spatial_world(regions=DUO) -> World:
    w = World()
    w.locations = {k: dict(v) for k, v in regions.items()}
    return w


def test_scene_loads_spatial_state() -> None:
    """elm_lane 场景: NPC 在 region 中心出生、实体锚点落在 region 内。"""
    from citysim.gateway.scenarios import load_scene
    w, _s, _r = load_scene(ROOT / "config" / "scenes" / "elm_lane.json", seed=3)
    wang = w.npcs["npc_wang"]
    assert wang.position == (170.0, 140.0)          # apt_101 中心
    for _eid, e in w.entities.items():
        r = w.locations[e.location_id]
        x, y = e.position
        assert r["x"] <= x <= r["x"] + r["w"]
        assert r["y"] <= y <= r["y"] + r["h"]


def test_same_region_visible_regardless_of_distance() -> None:
    """同 region 感知不受距离限制(既有语义保留)。"""
    w = _spatial_world()
    bed = add_entity(w, "bed_1", location="home", tags=("sleepable",),
                     affordances={"energy": 0.7})
    bed.position = (190.0, 190.0)                    # 距 npc 远超 radius
    npc = add_npc(w, None, "npc", location="home")
    npc.position = (10.0, 10.0)
    perc = build_percept(w, npc)
    assert {v.entity_id for v in perc.visible} == {"bed_1"}


def test_cross_region_not_visible() -> None:
    """感知为 region 局部: NPC 只看所在 location 的实体, 跨 region 不可见。"""
    w = _spatial_world()
    add_entity(w, "bench_1", location="park", tags=("fun",),
               affordances={"fun": 0.3})
    npc = add_npc(w, None, "npc", location="home")
    assert {v.entity_id for v in build_percept(w, npc).visible} == set()
    # 同 location 才可见
    add_entity(w, "bed_1", location="home", tags=("sleepable",),
               affordances={"energy": 0.7})
    npc2 = add_npc(w, None, "npc2", location="home")
    assert {v.entity_id for v in build_percept(w, npc2).visible} == {"bed_1"}


def test_travel_continuous_position_and_arrival_consistency() -> None:
    """travel 每 tick 线性推进; 到达 tick 位置=目标 region 中心且 location 落定。"""
    w, s, rng = make_runtime(CFG)
    w.locations = {"home": {**HOME["home"]},
                   "market": {"x": 300.0, "y": 0.0, "w": 200.0, "h": 200.0}}
    npc = add_npc(w, s, "npc", location="home", rng_pool=rng, seed=3)
    npc.position = (100.0, 100.0)
    from citysim.sim.loop import Travel
    s.travel["npc"] = Travel(from_loc="home", to_loc="market",
                             depart_tick=0, arrive_tick=10,
                             start_position=npc.position,
                             target_position=(400.0, 100.0))
    s.scheduler.schedule("npc", 10, now=0)           # 到达时重评
    for _ in range(5):                               # tick 5 → 一半
        run_tick(w, s, CFG, rng)
    assert npc.position[0] == 250.0                  # 线性中点
    for _ in range(5):
        run_tick(w, s, CFG, rng)
    assert npc.location_id == "market"               # 到达落 region
    assert npc.position == (400.0, 100.0)            # 位置与 region 一致


def test_perception_learns_actual_region_and_emits_learned() -> None:
    """感知落知识: located_at 记实体真实 region; 新知识发 learned 事件。"""
    w, s, rng = make_runtime(CFG, log=True)
    w.locations = {k: dict(v) for k, v in DUO.items()}
    add_entity(w, "bench_1", location="park", tags=("fun",),
               affordances={"fun": 0.3})
    npc = add_npc(w, s, "npc", location="park", rng_pool=rng, seed=3)
    seed_reviews(w, s)
    run_tick(w, s, CFG, rng)
    # located_at 学 park, 不是 npc 所在 home
    facts = npc.kb.query(subject="bench_1", relation="located_at")
    assert facts and str(facts[0].obj) == "park"
    assert any(l.startswith("E\t") and "\tlearned\t" in l
               and "relation=located_at" in l and "obj=park" in l
               for l in s.log_lines)


def test_interaction_no_distance_gate() -> None:
    """提交交互不再有跨 region 距离门(几何仅供可视化); claim/stock 仍是准入门。"""
    w = _spatial_world()
    add_entity(w, "bed_1", location="home", tags=("sleepable",),
               affordances={"energy": 0.7})
    add_entity(w, "far_bench", location="park", tags=("fun",),
               affordances={"fun": 0.3})

    npc = Person(identity=Identity(person_id="npc", name="npc"),
                 location_id="home")
    w.npcs["npc"] = npc
    isys = InteractionSystem()

    assert isys.submit(w, npc, Interact(target_id="bed_1"))      # 同 region 通过
    isys.release_active(w, "npc")
    assert isys.submit(w, npc, Interact(target_id="far_bench"))  # 跨 region 放行(无门)


def test_entity_anchor_stable_and_inside_region() -> None:
    """默认锚点由实体 id 决定: 跨世界一致、落在 region 内。"""
    pos = []
    for _ in range(2):
        w = _spatial_world()
        add_entity(w, "bed_1", location="home", tags=("sleepable",))
        add_entity(w, "wc_1", location="home", tags=("toilet",))
        w.layout_location("home")
        pos.append(w.entities["bed_1"].position)
    assert pos[0] == pos[1]
    x, y = pos[0]
    assert 0.0 <= x <= 200.0 and 0.0 <= y <= 200.0


def test_buy_moves_entity_anchor_into_new_region() -> None:
    """买回家后实体锚点落在新 region 内(不再沿用商店坐标)。"""
    w, s, rng = make_runtime(CFG)
    w.locations = {"apt": {"x": 0.0, "y": 0.0, "w": 200.0, "h": 200.0},
                   "market": {"x": 500.0, "y": 0.0, "w": 200.0, "h": 200.0}}
    tv = add_entity(w, "tv_1", location="market", tags=("entertain",),
                    affordances={"fun": 0.4})
    tv.price = 50.0
    tv.position = (600.0, 100.0)
    npc = add_npc(w, s, "npc", location="market", rng_pool=rng, seed=3,
                  fun=0.1)
    npc.home = "apt"
    npc.money = 100.0
    npc.position = (600.0, 100.0)
    _execute_buy(w, s, CFG, "npc", npc,
                 Buy(item_id="tv_1", trace=DecisionTrace()))
    assert tv.location_id == "apt"
    assert tv.position is not None
    x, y = tv.position
    assert 0.0 <= x <= 200.0 and 0.0 <= y <= 200.0


def test_decision_trace_structured_relevant_signals() -> None:
    """trace 携带结构化 relevant_signals(非仅字符串 reason)。"""
    from citysim.npc.brain import decide
    kb = KnowledgeBase()
    kb.learn(subject="rice_1", relation="affords", obj="hunger", value=0.4,
             confidence=1.0, source=Source(kind="OBSERVED"), tick=0)
    kb.learn(subject="rice_1", relation="located_at", obj="loc", value=0.0,
             confidence=1.0, source=Source(kind="OBSERVED"), tick=0)
    view = EntityView(entity_id="rice_1", name="rice_1", tags=frozenset(),
                      affordances={"hunger": 0.4}, duration_ticks=10,
                      location_id="loc")
    sig = full_signals(1.0)
    sig["hunger"] = 0.2
    intent = decide(Percept(tick=0, hour_f=12.0, location_id="loc",
                            visible=(view,)), sig, {}, kb, CFG)
    assert isinstance(intent, Interact) and intent.target_id == "rice_1"
    assert intent.trace.relevant_signals[0][0] == "hunger"
    assert abs(intent.trace.relevant_signals[0][1] - 0.8) < 1e-6


def test_snapshot_exports_spatial_fields() -> None:
    """snapshot 导出 position/relevant_signals/实体锚点(可 JSON)。"""
    import json
    from citysim.gateway.scenarios import build_scenario
    from citysim.gateway.snapshot import build_snapshot
    w, s, rng = build_scenario("elm_lane", seed=3)
    for _ in range(120):
        run_tick(w, s, CFG, rng)
    snap = build_snapshot(w, s, CFG, "1x", [])
    json.dumps(snap, ensure_ascii=False)
    n0 = snap["npcs"][0]
    assert len(n0["position"]) == 2
    if n0["intent"]:
        assert "relevant_signals" in n0["intent"]
    e0 = snap["entities"][0]
    assert "position" in e0 and (e0["position"] is None
                                 or len(e0["position"]) == 2)


def test_world_delta_stock_changed_event() -> None:
    """世界侧 set_stock 脉冲产生可观察 stock_changed 事件。"""
    from citysim.sim.pulses import normalize
    w, s, rng = make_runtime(CFG, log=True)
    add_entity(w, "market_1", location="home", tags=("edible",),
               affordances={"hunger": 0.4}, stock=10)
    s.pulses = normalize([{"at": "day 0 00:01", "op": "set_stock",
                           "target": "market_1", "value": 5}], 1440)
    run_tick(w, s, CFG, rng)                       # tick=1 命中 once 脉冲
    assert w.entities["market_1"].stock == 5
    assert any(l.startswith("E\t") and "\tstock_changed\t" in l
               and "stock_before=10" in l and "stock_after=5" in l
               for l in s.log_lines)
