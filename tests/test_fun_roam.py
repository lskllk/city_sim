"""第 3~5 步的测试: 闲逛(观察窗口) + 地点行 + 新奇量 + 选址公式。

旧的专用机制(try_wander / systems.roaming / roam Grant)已删 —— 现在闲逛是
**NPC 自己的事**: 走到目的地, 在那儿观察一段窗口(60t), 收工结算。
"""
from __future__ import annotations

import pathlib

from citysim.core.config import load_config
from citysim.core.types import Idle, Interact, Wander
from citysim.npc.brain.memory_io import place_id

from helpers import add_entity, add_npc, make_runtime

CFG = load_config(pathlib.Path("config/sim.toml"))


def _port(w, s):
    from citysim.world.edge.port import WorldPortImpl
    return WorldPortImpl(w, s, CFG)


# --- 观察窗口(committed goal) -------------------------------------------

def test_wandering_opens_a_window_and_cools_down_decisions() -> None:
    """闲逛 = committed goal + 一段观察窗口 → 期间饿到底也不切走(决策冷却)。

    窗口在 `_advance` 里开(到了目的地才开始计时) —— 不再有 world 侧 Grant。
    """
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places(["loc"])                  # 只有这一个可逛地点 → 就地开逛
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    port = _port(w, s)

    d = npc.decide(CFG, 0)
    assert isinstance(d.intent, Wander) and d.intent.dest == "loc"
    npc._execute(port, d, 0)                 # 已在该地 → 什么都不用做

    d2 = npc.decide(CFG, 1)                  # 推进一拍 → 开窗口
    assert isinstance(d2.intent, Wander)
    assert npc._goal.roam_until == 1 + CFG.fun_roam_ticks

    npc.set_signal("hunger", 0.0)            # 饿到底
    d3 = npc.decide(CFG, 2)
    assert not isinstance(d3.intent, Interact)   # 冷却: 不切去吃饭


def test_window_expires_then_settles_fun() -> None:
    """窗口到期 → 收工结算: 补 fun(基础 + 新奇), 然后才轮得到别的需求。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places(["loc"])
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    port = _port(w, s)
    npc._execute(port, npc.decide(CFG, 0), 0)
    npc.decide(CFG, 1)                        # 开窗口
    end = npc._goal.roam_until
    before = npc.signal("fun")
    npc.set_signal("hunger", 0.0)             # 窗口到期那一刻已经饿了
    d = npc.decide(CFG, end + 1)              # 越过窗口 → 结算 + 收工
    assert npc.signal("fun") > before         # 有回报(基础 + 新奇)
    assert isinstance(d.intent, Interact)     # 收工之后, 需求才抢得到


# --- 地点行 + 新奇量 -----------------------------------------------------

def test_place_row_is_written_and_stays_out_of_candidates() -> None:
    """观察会写一行地点记忆(去过凭证); 它 afford="" → 不进决策候选。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc")
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    row = next((r for r in npc.memory_dicts()
                if r["item_id"] == place_id("loc")), None)
    assert row is not None and row["located"] == "loc"
    assert row["afford"] == "" and "place" in row["tags"]
    assert npc._mem.get(place_id("loc")).attrs["visits"] >= 1
    assert npc.decide(CFG, 0).intent.__class__ is Idle   # 地点行不产生候选


def test_first_sight_is_max_novelty_repeat_is_near_zero() -> None:
    """新奇量: 第一次见 = 1/件; 立刻再看 ≈ 0(remember 已满)。"""
    from citysim.world.edge.perception import build_percept
    from citysim.npc.brain.memory_io import perceive_into
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "n", location="loc")
    first = perceive_into(npc._mem, build_percept(w, npc), 0)
    second = perceive_into(npc._mem, build_percept(w, npc), 1)
    assert first >= 2.0                        # 1 件货 + 1 行地点
    assert second == 0.0


def test_forgot_place_becomes_novel_again() -> None:
    """忘了的旧东西再看 → 也算新奇(1 − remember)。"""
    from citysim.world.edge.perception import build_percept
    from citysim.npc.brain.memory_io import perceive_into
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible",), affordances={"hunger": 0.5})
    npc = add_npc(w, s, "n", location="loc")
    perceive_into(npc._mem, build_percept(w, npc), 0)
    npc._mem.update(place_id("loc"), remember=0.3)      # 假装忘了
    again = perceive_into(npc._mem, build_percept(w, npc), 999)
    assert again > 0.5                                   # ≈ 0.7


# --- 选址公式 -----------------------------------------------------------

def test_wander_dest_prefers_never_visited_over_visited_empty() -> None:
    """没去过的(乐观初值) 比【去过但空空如也】的明显更容易被抽到。

    这就是"没什么东西的建筑 → 很小概率会去"那条 —— 去过一次之后, 乐观初值
    没了, 只剩那条地点行本身(权重 1); 而没去过的是乐观初值(权重 3)。
    """
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="home", fun=0.2)
    npc.set_places(["fresh", "empty_done"])
    npc.note(place_id("empty_done"), located="empty_done", afford="", stock=1,
             tags=("place",))                    # 去过但没东西(只有地点行)
    hits = {"fresh": 0, "empty_done": 0}
    for t in range(0, 6000, 60):
        hits[npc._wander_dest(CFG, t)] += 1
    assert hits["fresh"] > 0 and hits["empty_done"] > 0     # 都是加权随机
    assert hits["fresh"] > hits["empty_done"]               # 但没去过的更常去


def test_wander_dest_deterministic() -> None:
    def pick() -> list[str]:
        w, s, _ = make_runtime(CFG)
        npc = add_npc(w, s, "same", location="a", fun=0.2)
        npc.set_places(["b", "c", "d"])
        return [npc._wander_dest(CFG, t) for t in (0, 60, 120, 180)]
    assert pick() == pick()


# ---------------------------------------------------------------------------
# fun 的收支 + 闲逛的优先级(这些不随机制改动而变)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# fun 收支
# ---------------------------------------------------------------------------
def test_work_raises_fun() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "station", location="loc", tags=("work", "station"),
               affordances={}, duration_ticks=600)
    npc = add_npc(w, s, "n", location="loc", fun=0.5)
    npc.intake_add(_port(w, s).try_take("n", "station"))
    npc.heartbeat(600, CFG)                        # 10:00
    assert npc.signal("fun") > 0.5


def test_idle_drops_fun() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", fun=0.5)
    npc.heartbeat(600, CFG)
    assert npc.signal("fun") < 0.5


def test_eating_does_not_change_fun() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", hunger=0.2, fun=0.5)
    npc.intake_add(_port(w, s).try_take("n", "meal"))
    npc.heartbeat(600, CFG)
    assert npc.signal("fun") == 0.5               # 吃饭既不涨也不掉


def test_sleeping_does_not_change_fun() -> None:
    w, s, _ = make_runtime(CFG)
    add_entity(w, "bed", location="loc", tags=("sleepable",),
               affordances={}, duration_ticks=100)
    npc = add_npc(w, s, "n", location="loc", energy=0.3, fun=0.5)
    npc.intake_add(_port(w, s).try_take("n", "bed"))
    npc.heartbeat(1200, CFG)
    assert npc.signal("fun") == 0.5


# ---------------------------------------------------------------------------
# 闲逛: 最低优先级 / 可被任何需求打断
# ---------------------------------------------------------------------------
def test_low_fun_falls_back_to_wander() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="home", fun=0.2)
    npc.set_places(["plaza", "far"])
    npc.set_travel_costs({"home|plaza": 10, "home|far": 200})
    d = npc.decide(CFG, 100)
    assert isinstance(d.intent, Wander)
    assert d.intent.dest != "home"                # 不在“原地闲逛”
    assert d.intent.dest in ("plaza", "far")


def test_need_beats_wander() -> None:
    """闲逛最低优先级: 饿了 → 去吃饭, 不是去闲逛。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "meal", location="loc", tags=("edible", "consumable"),
               affordances={"hunger": 0.5}, duration_ticks=20)
    npc = add_npc(w, s, "n", location="loc", fun=0.2, hunger=0.1)
    npc.set_places(["plaza"])
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)        # 先看见饭
    d = npc.decide(CFG, 100)
    assert isinstance(d.intent, Interact) and d.intent.target_id == "meal"


def test_wandering_reports_activity_class() -> None:
    """闲逛期间: 行为大类 = wander(前端时间线靠它上色)。

    判据是 goal(一段观察窗口), 不再是 roam Grant —— 所以 activity() 要看 goal。
    """
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc", fun=0.2)
    npc.set_places(["loc"])
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), 0)
    port = _port(w, s)
    npc._execute(port, npc.decide(CFG, 0), 0)
    npc.decide(CFG, 1)                       # 开窗口
    assert npc.activity() == ("wander", "闲逛")
    assert npc.activity_class == "wander"


# --- 家里的东西不衰减(常识), 别处的照常丢 ---------------------------------


# --- 观察的三个理由(并且只有这三个) -------------------------------------

def test_look_reasons_are_first_visit_wander_and_missing_here() -> None:
    """要不要看一眼环境? 只有三种理由:

      ① 第一次来(记忆里没这个地点的地点行)  ② 正在这儿逛  ③ 此地缺东西

    ★ 没有"记不太清了就再看一眼"这种按时间的定期刷新 —— 那会把同地点的所有
      东西整批刷成新鲜, 用得上和用不上的东西一视同仁(知识永远不旧)。
    """
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc", home="home")

    # ① 第一次来 → 看
    assert npc._need_look("loc", CFG) is True
    # 有了地点行 + 需求都满 → 不看
    npc.note(place_id("loc"), located="loc", afford="", stock=1)
    assert npc._need_look("loc", CFG) is False
    # 时间过去了知识变旧 → 【仍然不看】(这正是不再需要定期刷新的意思)
    npc._mem.update(place_id("loc"), remember=0.01)
    assert npc._need_look("loc", CFG) is False

    # ③ 这儿缺东西(饿着, 而此地记忆里没有能解 hunger 的) → 看
    npc.set_signal("hunger", 0.1)
    assert npc._missing_here("loc", CFG) is True
    assert npc._need_look("loc", CFG) is True
    # 此地有能解它的(记忆行落在这儿) → 不看
    npc.note("apple", located="loc", afford="hunger", value=0.35, stock=1)
    assert npc._need_look("loc", CFG) is False
    # 但那个东西在【别处】不算 —— 本地缺就是缺(→ 看了再做决策, 本地真没有才去外地)
    npc._mem.update("apple", located="elsewhere")
    assert npc._need_look("loc", CFG) is True

    # ② 正在这儿逛 → 看(哪怕什么都不缺)
    npc.set_signal("hunger", 1.0)
    npc.note("apple", located="loc", afford="hunger", value=0.35, stock=1)
    npc.set_places(["loc"])
    from citysim.core.types import Wander
    from citysim.npc.person.goal import _Goal
    npc._goal = _Goal("fun", Wander("loc"))
    assert npc._need_look("loc", CFG) is True
    npc._goal = _Goal("fun", Wander("other"))
    assert npc._need_look("loc", CFG) is False


def test_using_something_refreshes_its_memory() -> None:
    """反证(交互结果)除了改 stock, 也要刷 remember —— 【用过 = 记得】。

    这是"常用 vs 没人碰"唯一的分水岭: 没有按时间的定期刷新之后, 常用的东西
    靠这一条活下去, 没人碰的东西自然变旧/被忘。
    """
    from citysim.core.types import InteractionDone
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc")
    npc.note("apple", located="loc", afford="hunger", value=0.35, stock=5)
    npc._mem.update("apple", remember=0.2)                 # 快忘了
    npc.notify(InteractionDone(entity_id="apple", tick=100, stock=4))
    row = npc._mem.get("apple")
    assert row.stock == 4                                  # 还剩几个 ✓
    assert row.remember == 1.0 and row.last_seen == 100    # 用过了 → 记得 ✓


def test_home_rows_never_decay() -> None:
    """家 = 常识: 落在家的行【不衰减也不删】; 别处的行照常变旧/被删。

    为什么: 家是身份性的知识("我住那儿, 那儿有什么"), 不该随时间淡掉 ——
    否则"忘了自家的床 → 困了也想不起回家"会变成死锁, 而且不可逆(越不回家越没记忆)。
    """
    from citysim.npc.brain.memory_io import forget
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="home", home="home")
    npc.note("bed_home", located="home", afford="energy", value=0.5, stock=1)
    npc.note("apple_shop", located="shop", afford="hunger", value=0.35, stock=1)
    for _ in range(30):                                    # 30 个游戏日
        forget(npc._mem, CFG.half_life_ticks, CFG.ticks_per_day,
               keep_located=npc.home)
    assert npc._mem.get("bed_home") is not None            # 家的: 还在 ✓
    assert npc._mem.get("bed_home").remember == 1.0        # 一点没淡 ✓
    assert npc._mem.get("apple_shop") is None              # 别处的: 早丢了 ✓


def test_seeing_it_yourself_upgrades_a_hearsay_row() -> None:
    """"看"不刷新【已有的第一手记忆】, 但必须能【升级听来的】。

    ★ 这个坑是实测踩出来的: 传闻(gossip)写记忆行时**不带 tags**, 而"能不能买"
      的判据要 tags 里有 consumable。如果亲眼看到也不覆盖, 那条听来的行就
      永远补不上 tags → 店里的苹果永远买不了 → 全镇饿死。
      believe 的语义本来就是"听说 < 亲眼", 所以: source != "" → 整行覆盖。
    """
    from citysim.core.types import EntityView, Percept
    from citysim.npc import brain
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc")
    # 听来的: 没有 tags
    npc.note("apple", located="loc", afford="hunger", value=0.35,
             price=5.0, stock=10, source="someone", believe=0.5)
    # 亲眼看到
    view = EntityView(entity_id="apple", name="苹果", location_id="loc",
                      item_type="food_apple", tags=frozenset({"consumable", "edible"}),
                      affordances={"hunger": 0.35}, duration_ticks=12,
                      price=5.0, stock=9)
    percept = Percept(tick=7, hour_f=8.0, location_id="loc", visible=(view,))
    brain.perceive_into(npc._mem, percept, tick=7)
    row = npc._mem.get("apple")
    assert row.believe == 1.0 and row.source == ""      # 亲眼最硬 ✓
    assert "consumable" in row.tags                     # tags 补上了 ✓
    assert row.stock == 9                               # 现场为准 ✓


def test_need_triggered_look_only_writes_what_the_need_wants() -> None:
    """记什么取决于【为什么看】:

      第一次来 / 闲逛 → 探索, 全部记住;
      本地缺东西     → 只是来找那样东西的, 别的一概不记(不算探索)。
    """
    from citysim.core.types import EntityView, Percept
    from citysim.npc import brain
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "n", location="loc", home="home")
    npc.note(place_id("loc"), located="loc", afford="", stock=1)   # 不是第一次来
    npc.set_signal("hunger", 0.1)
    assert npc._look_reason("loc", CFG) == "need"                  # 本地缺吃的 → 找
    views = tuple(
        EntityView(entity_id=eid, name=eid, location_id="loc",
                   item_type=t, tags=frozenset({"consumable"}),
                   affordances={af: 0.4}, duration_ticks=10, stock=5)
        for eid, t, af in (("apple", "food_apple", "hunger"),
                           ("bed", "bed_basic", "energy"),
                           ("toilet", "toilet_basic", "bladder"))
    )
    percept = Percept(tick=1, hour_f=8.0, location_id="loc", visible=views)
    # 缺 hunger 才看的 → 只记苹果
    brain.perceive_into(npc._mem, percept, 1, only_affords=npc._needed(CFG))
    assert npc._mem.get("apple") is not None                       # ✓ 能解需求
    assert npc._mem.get("bed") is None                             # ✗ 与这次无关
    assert npc._mem.get("toilet") is None                          # ✗

    # 第一次来 / 闲逛 → 全部记
    npc._mem.clear()
    brain.perceive_into(npc._mem, percept, 1, only_affords=None)
    assert all(npc._mem.get(i) is not None for i in ("apple", "bed", "toilet"))
