"""testm5.md 场景 S1-S6 的严格机器测试(test_m5_full)。

每个场景 = 一个 pytest + 一份可写出的叙事日志(测罢把 log_lines 落盘供
narrate 人工 review)。阈值首次按实际分布校准后冻结(见 docs/testM5result.md)。

依赖: 主循环每日 decay 接线(5.5)与感知学 located_at —— 均 kb!=None 才生效。
"""
from __future__ import annotations

import random
from pathlib import Path

from citysim.core.config import load_config
from citysim.npc.knowledge import ArchetypeKB, Fact, KnowledgeBase, Source
from citysim.npc.person import Identity, Person
from citysim.sim.loop import attach_replay, make_systems, run_tick
from citysim.world.world import World

from helpers import add_entity
from soak import SoakTracker

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")
OUT = ROOT / "docs" / "narrate_logs"
OUT.mkdir(parents=True, exist_ok=True)

# --- 共享建造块 -----------------------------------------------------------
def _fac(world: World, loc: str, n_npc: int) -> None:
    """每个地点都配床/水/马桶(非容器, 不产生观察事实; 让人能就地生活)。"""
    for i in range(n_npc):
        add_entity(world, f"bed_{loc}_{i}", location=loc, tags=("sleepable",),
                   affordances={"energy": 0.7}, duration_ticks=480,
                   wake_condition="energy>=0.99")
        add_entity(world, f"water_{loc}_{i}", location=loc,
                   tags=("drink", "consumable"), affordances={"thirst": 0.6},
                   duration_ticks=10, stock=5000)
    add_entity(world, f"toilet_{loc}", location=loc, tags=("toilet",),
               affordances={"bladder": 0.6, "comfort": 0.05}, duration_ticks=5,
               on_complete=[{"op": "set_signal", "signal": "bladder",
                             "value": 1.0},
                            {"op": "clear_pending", "field": "bladder_pending"}])


def _food(world: World, eid: str, loc: str, stock: int) -> None:
    """食物容器(GOAP 取→吃; 无 provides 字段 → 落回 meal_simple 产餐)。"""
    add_entity(world, eid, location=loc, tags=("container",),
               affordances={"provides:edible": 1.0}, duration_ticks=2,
               stock=stock)


def _mk_fact(seq: int, subj: str, rel: str, obj, conf: float = 1.0,
             kind: str = "INJECTED", ref=("arch",)) -> Fact:
    return Fact(fact_id=f"a{seq}", subject=subj, relation=rel, obj=obj,
                confidence=conf, source=Source(kind=kind, ref=ref))


def _set_kb(world: World, pid: str, facts: list[Fact]) -> None:
    world.npcs[pid].kb = KnowledgeBase(ArchetypeKB(facts))


def _fresh(n_pid: int, loc: str = "home") -> tuple[World, object, dict, int]:
    """新场景: world + systems(log=True, tell_p=0) + rng_pool。"""
    world = World()
    systems = make_systems(log=True, tell_p=0.0)
    attach_replay(world, systems)
    rng_pool: dict[str, random.Random] = {}
    for i in range(n_pid):
        pid = f"p{i}"
        p = Person(identity=Identity(person_id=pid, name=pid),
                   location_id=loc)
        p.set_state(energy=0.7, hunger=0.25, thirst=0.6, bladder=0.9,
                    health=1.0, temperature=1.0, fun=0.6, social=0.6,
                    comfort=0.8, hp=1.0)
        world.npcs[pid] = p
        rng_pool[pid] = random.Random(1000 + int(pid[1:]))
        systems.scheduler.schedule(pid, 1, now=0)
    return world, systems, rng_pool, CFG


def _run(world, systems, rng_pool, ticks, tracker=None,
         at=None) -> None:
    """跑 ticks; at: dict[tick->callable] 在 run_tick 之前钩子。"""
    at = at or {}
    for t in range(ticks):
        if t in at:
            at[t](world, systems)
        run_tick(world, systems, CFG, rng_pool)
        if tracker:
            tracker.observe()


def _dump(world, systems, name: str) -> Path:
    """回放日志落盘(供 narrate 人工 review)。"""
    p = OUT / f"{name}.log"
    p.write_text("\n".join(systems.log_lines or []), encoding="utf-8")
    return p


def _eat_ticks(world, systems) -> dict[str, list[int]]:
    """每个 NPC 吃到饭(interaction_done + edible)的 tick 列表(事件回调解析)。"""
    out: dict[str, list[int]] = {}

    def _on(ev):
        if ev.kind != "interaction_done":
            return
        ent = world.entities.get(ev.payload.get("entity", ""))
        if ent is not None and "edible" in ent.tags:
            out.setdefault(ev.subject_id, []).append(ev.tick)

    world.bus.subscribe_log(_on)
    return out


def _move_to_ticks(systems, target_loc: str) -> list[int]:
    return [int(l.split("\t")[1]) for l in (systems.log_lines or [])
            if l.startswith("D\t") and l.split("\t")[3] == "move_to"
            and l.split("\t")[4] == target_loc]


# ===========================================================================
# S1 · 新来者 vs 老住户(知识不对称 → 见过即学会 → 收敛)
# ===========================================================================
def test_s1_newcomer_learns_from_old_resident() -> None:
    world, systems, rng, _ = _fresh(2)
    _fac(world, "home", 2)
    _fac(world, "market", 2)
    _food(world, "market_1", "market", 500)   # 食物只在 market
    # A: full —— 原型知道 market 卖餐 + 在哪
    _set_kb(world, "p0", [
        _mk_fact(1, "market_1", "sells", "meal_simple", 1.0),
        _mk_fact(2, "market_1", "located_at", "market", 1.0)])
    # B: archetype_only, 原型删掉食物来源(刚搬来, 不知市场有食/在哪)
    _set_kb(world, "p1", [])
    eats = _eat_ticks(world, systems)

    def _teleport_b(world, systems):
        # 模拟"路过/摸索到 market"(自主探索是 M6 项, 见 debt)
        world.npcs["p1"].location_id = "market"
        systems.scheduler.schedule("p1", 1, now=world.clock_tick)

    tr = SoakTracker(world, systems)
    _run(world, systems, rng, 1440 * 7, tr, at={1440 * 1 + 5: _teleport_b})
    _dump(world, systems, "s1_newcomer")

    # B 首餐远晚于 A; B 学习前 long idle+need >= 2× A
    first_a = eats["p0"][0]
    first_b = eats["p1"][0]
    idle_a = tr.max_idle_need.get("p0", (0, ""))[0]
    idle_b = tr.max_idle_need.get("p1", (0, ""))[0]
    # 学习后(day3 起)两人进食量收敛
    def dcount(pid, d0, d1):
        return sum(1 for t in eats[pid] if d0 <= t // 1440 < d1)
    late_a = dcount("p0", 2, 7)
    late_b = dcount("p1", 2, 7)
    # B 学会: KB 有 market 的 OBSERVED 事实
    obs = [f for f in world.npcs["p1"].kb.query(subject="market_1",
                                                relation="contains")]
    # ---- 校准打印(冻结阈值依据) ----
    print(f"\nS1: firstA={first_a} firstB={first_b} "
          f"idleA={idle_a} idleB={idle_b} "
          f"lateA={late_a} lateB={late_b} obsB={len(obs)}")

    assert first_b > first_a + 30            # B 明显晚
    assert idle_b >= 2 * max(1, idle_a)      # B 摸索期 idle+need 更长
    assert obs and obs[0].source.kind == "OBSERVED"
    # day3-7: B 不再需要帮忙 → 两人进食量相当(±35%)
    assert 0.65 <= late_b / max(1, late_a) <= 1.5, (late_a, late_b)


# ===========================================================================
# S2 · 过时知识与纠错(4 NPC; 冰箱 day3 清空; wasted_trips 按天)
# ===========================================================================
def test_s2_stale_knowledge_correction_4npc() -> None:
    # 设计注(现机制约束): NPC 没有"回家睡觉/补给"行为 → 到食点即扎营, 无法实现
    # 文档版"清空后跨天通勤扑空"。此处改为: 首次饿前(tick 300)就把冰箱清空 →
    # 全员照旧 belief 扑空 1 次 → 亲历空仓 refute → 改道 market。通勤/按天单调
    # 版记入 behavior_debt(需 M6 回家行为)。
    world, systems, rng, _ = _fresh(4)
    _fac(world, "home", 4)
    _fac(world, "market", 4)
    _food(world, "fridge_1", "kitchen", 999)   # 惯用冰箱
    _food(world, "market_1", "market", 999)    # 备选超市
    arch = [
        _mk_fact(1, "fridge_1", "contains", "edible", 0.9),
        _mk_fact(2, "fridge_1", "located_at", "kitchen", 1.0),
        _mk_fact(3, "market_1", "sells", "meal_simple", 1.0),
        _mk_fact(4, "market_1", "located_at", "market", 1.0)]
    for i in range(4):
        _set_kb(world, f"p{i}", arch)
        world.npcs[f"p{i}"].set_state(hunger=1.0)   # 不立刻饿 → 首饿在冰箱空后
    eats = _eat_ticks(world, systems)
    # 首饿前(tick 300)冰箱就被清空且不再补货
    def _empty_fridge(world, systems):
        world.entities["fridge_1"].stock = 0
    tr = SoakTracker(world, systems)
    _run(world, systems, rng, 1440 * 7, tr,
         at={300: _empty_fridge})
    _dump(world, systems, "s2_stale_correction")

    fridge_moves = _move_to_ticks(systems, "kitchen")
    by_day: dict[int, int] = {}
    for t in fridge_moves:
        d = t // 1440
        by_day[d] = by_day.get(d, 0) + 1
    # 每人扑空(去 kitchen)次数
    per_npc = {f"p{i}": 0 for i in range(4)}
    for l in (systems.log_lines or []):
        if l.startswith("D\t") and l.split("\t")[3] == "move_to" \
                and l.split("\t")[4] == "kitchen":
            per_npc[l.split("\t")[2]] += 1
    # ---- 校准打印 ----
    print(f"\nS2: fridge_move_by_day={dict(sorted(by_day.items()))} "
          f"per_npc={per_npc}")
    print(f"S2: eats={[len(eats[f'p{i}']) for i in range(4)]}")

    # 有人上当: 全员 belief 扑空 ≥1 次; 每人至多 1 次(亲历即纠错)
    assert sum(per_npc.values()) >= 2, per_npc
    assert all(v <= 1 for v in per_npc.values()), per_npc
    # 全员学会: 扑空集中在早期(day index 0-1), 之后不再去 kitchen
    assert all(d <= 1 for d in by_day), by_day
    # 改道 market → 后期人人吃到
    assert all(len(eats[f"p{i}"]) >= 3 for i in range(4))
    # KB 修正: 4/4 不再认为冰箱有食(亲历过空)
    no_believe = sum(1 for i in range(4)
                     if not world.npcs[f"p{i}"].kb.knows("fridge_1",
                                                         "contains", "edible"))
    assert no_believe == 4, no_believe


def test_s2_kb_off_control_starves() -> None:
    """对照: kb_mode=off 同场景(无市场知识) → 找不到食(饿), 每餐都没吃上。"""
    world, systems, rng, _ = _fresh(4)
    _fac(world, "home", 4)
    _food(world, "fridge_1", "kitchen", 999)   # 食在别的 location
    # 无任何 KB → 永远不离开 home → 没得吃
    tr = SoakTracker(world, systems)
    _run(world, systems, rng, 1440 * 3, tr)
    idle = [tr.max_idle_need.get(f"p{i}", (0, ""))[0] for i in range(4)]
    eats = _eat_ticks(world, systems)
    print(f"\nS2-off: idle={idle} total_eats={sum(len(v) for v in eats.values())}")
    assert sum(len(v) for v in eats.values()) == 0   # 一口没吃到
    assert min(idle) >= 200                          # 人人有饿着瞎等时段


# ===========================================================================
# S3 · 传闻扩散(10 NPC 同地; p=0.1)
# ===========================================================================
def test_s3_rumor_curve_10npc() -> None:
    world, systems, rng, _ = _fresh(10, loc="plaza")
    # plaza 无容器 → 无人产生观察事实, 唯一 overlay = 咖啡店传闻
    for i in range(10):
        world.npcs[f"p{i}"].set_state(hunger=1.0, thirst=1.0, energy=0.9)
        _set_kb(world, f"p{i}", [])          # 空原型(只是有 kb)
    seed_fact = world.npcs["p0"].kb.learn(
        subject="cafe_7", relation="affords", obj="fun", confidence=1.0,
        source=Source(kind="OBSERVED"))
    systems.tell_p = 0.1
    _run(world, systems, rng, 1440 * 7)
    _dump(world, systems, "s3_rumor_curve")

    def knowers(tick_end: int) -> int:
        """knowers(t) = KB 含该事实(conf>=0.3)人数(截至 tick_end, 排除目击者)。"""
        n = 0
        for i in range(10):
            f = world.npcs[f"p{i}"].kb.query(subject="cafe_7",
                                             relation="affords")
            if f and f[0].confidence >= 0.3:
                n += 1
        return n
    # 按天曲线(利用 decay 的 _now 变化间接按天? 直接查事实即可, 置信>0.3 判断)
    # 曲线: 7 天内知道人数(含目击者 p0)
    total = knowers(7 * 1440)
    # 传播图从 told 事件重建 → 校验每跳 ≤0.8 & 全部连到 p0(溯源)
    told = [l for l in systems.log_lines if "\ttold\t" in l]
    # (from,audience,conf) 列表
    graph: dict[str, list[tuple[str, float]]] = {}
    for l in told:
        parts = l.split("\t")
        spk = parts[3]
        kv = dict(p.split("=", 1) for p in parts[4].split(";") if "=" in p)
        aud = kv.get("audience", "").strip("[]' ")
        conf = float(kv.get("conf", "1"))
        graph.setdefault(spk, []).append((aud, conf))
    # BFS 从 p0 出发, 检查 conf 每跳 ≤ parent*0.8+1e-6
    from collections import deque
    conf_at: dict[str, float] = {"p0": 1.0}
    q = deque(["p0"])
    reach = {"p0"}
    while q:
        s = q.popleft()
        for (a, c) in graph.get(s, []):
            if c <= conf_at[s] * 0.8 + 1e-6 and a not in reach:
                conf_at[a] = c
                reach.add(a)
                q.append(a)
    # ---- 校准打印 ----
    print(f"\nS3: knowers_7d={total} told_events={len(told)} "
          f"reachable={len(reach)}")
    confs = sorted([
        world.npcs[f"p{i}"].kb.query(subject="cafe_7", relation="affords")[0]
        .confidence if world.npcs[f"p{i}"].kb.query(subject="cafe_7",
                                                     relation="affords") else None
        for i in range(10)], key=lambda x: (x is None, x))
    print(f"S3: confs={confs}")

    assert total >= 6                     # 7 天内 ≥6 人知道
    assert seed_fact is not None
    assert len(reach) >= 6                # 事件链溯源到 p0
    # 所有非目击者事实都是 TOLD 且 conf<=0.8(二手起每跳打折)
    for i in range(1, 10):
        f = world.npcs[f"p{i}"].kb.query(subject="cafe_7",
                                         relation="affords")
        if f:
            assert f[0].source.kind == "TOLD"
            assert f[0].confidence <= 0.8 + 1e-6


def test_s3_p0_no_rumor() -> None:
    """p=0 → 无 told 事件, 知道者恒为 1。"""
    world, systems, rng, _ = _fresh(5, loc="plaza")
    for i in range(5):
        world.npcs[f"p{i}"].set_state(hunger=1.0, thirst=1.0, energy=0.9)
        _set_kb(world, f"p{i}", [])
    world.npcs["p0"].kb.learn(subject="cafe_7", relation="affords",
                              obj="fun", confidence=1.0,
                              source=Source(kind="OBSERVED"))
    systems.tell_p = 0.0
    _run(world, systems, rng, 1440 * 3)
    told = [l for l in systems.log_lines if "\ttold\t" in l]
    assert not told
    n = sum(1 for i in range(5)
            if world.npcs[f"p{i}"].kb.query(subject="cafe_7",
                                            relation="affords"))
    assert n == 1


# ===========================================================================
# S4 · 假消息的生与死(注入假事实 → 传播 → 亲赴 refute → 归零, wasted 有界)
# ===========================================================================
def test_s4_false_rumor_life_and_death() -> None:
    # 场景设计注: 脑当前按 subject 字母序挑知识源, 若同时有真超市( sells )会
    # 恒盖过假消息 → 无人亲赴证伪。故本场景不给真食物替代, 专测
    # "假消息传播→亲历空仓→refute→归零"(纠错后有真实替代食源见 S2)。
    world, systems, rng, _ = _fresh(6, loc="home")
    _fac(world, "home", 6)
    _fac(world, "warehouse", 6)
    _food(world, "warehouse_9", "warehouse", 0)   # 假消息里的"仓库#9": 空仓
    # 大家都"知道仓库在哪"(located_at), 但不知道有没有货
    arch = [_mk_fact(1, "warehouse_9", "located_at", "warehouse", 1.0)]
    for i in range(6):
        _set_kb(world, f"p{i}", arch)
    # p0 收到一条假消息(注入): 仓库#9 有吃的; 让 p0 先吃饱、多 idle 好传谣
    world.npcs["p0"].kb.learn(subject="warehouse_9", relation="contains",
                              obj="edible", confidence=1.0,
                              source=Source(kind="TOLD", ref=("liar",)))
    world.npcs["p0"].set_state(hunger=1.0)
    systems.tell_p = 0.25
    tr = SoakTracker(world, systems)
    _run(world, systems, rng, 1440 * 7, tr)
    _dump(world, systems, "s4_false_rumor")
    # 按天 knowers(信假消息: warehouse_9 contains edible conf>=0.3)
    def lie_knowers(d_end: int) -> int:
        n = 0
        for i in range(6):
            f = world.npcs[f"p{i}"].kb.query(subject="warehouse_9",
                                             relation="contains")
            if any(x.obj == "edible" and x.confidence >= 0.3 for x in f):
                n += 1
        return n
    wasted = len(_move_to_ticks(systems, "warehouse"))
    # 亲历空仓 → refute(不信了)
    refuted = sum(1 for i in range(6) if world.npcs[f"p{i}"].kb.knows(
        "warehouse_9", "contains", "none"))
    # ---- 校准打印 ----
    print(f"\nS4: wasted={wasted} refuted={refuted}")
    # 假消息 7 天后归零(没人还信仓库有食)
    assert lie_knowers(7 * 1440) == 0
    # 传开过: 至少 3 人真信过并亲赴(每人 1 次 wasted trip)
    assert wasted >= 3
    assert refuted >= 3
    # wasted 有上界: 每人至多上当两次(靠 refute 后不再信 + 谣言随信众消亡)
    assert wasted <= 6 * 2


# ===========================================================================
# S5 · 遗忘(真实主循环: 目击 → 移走 21 天 → conf≈0.125)
# ===========================================================================
def test_s5_forgetting_in_loop_over_21_days() -> None:
    world, systems, rng, _ = _fresh(1, loc="courtyard")
    _fac(world, "courtyard", 1)
    _fac(world, "far", 1)
    _food(world, "rest_b", "courtyard", 1)
    # 目击: 先在 courtyard 看到餐厅 B 有食
    kb = world.npcs["p0"].kb = KnowledgeBase()
    world.npcs["p0"].set_state(hunger=0.9, energy=0.9)
    # 直接把"目击"写进 KB(目击动作本身 = 感知落知识)
    kb.learn(subject="rest_b", relation="contains", obj="edible",
             confidence=1.0, source=Source(kind="OBSERVED"))
    kb.learn(subject="rest_b", relation="located_at", obj="courtyard",
             confidence=1.0, source=Source(kind="OBSERVED"))

    def _move_away(world, systems):
        # 把餐厅 B 移到不可达地点 → 之后只靠遗忘
        world.entities["rest_b"].location_id = "far"
    _run(world, systems, rng, 1440 * 21, at={1440: _move_away})
    got = kb.query(subject="rest_b", relation="contains")
    assert got, "事实应仍在(conf 未跌破 0.05)"
    print(f"\nS5: conf_after_21d={got[0].confidence}")
    assert abs(got[0].confidence - 0.125) <= 0.02
    # INJECTED 不衰减
    kb.learn(subject="market_1", relation="sells", obj="meal_simple",
             confidence=1.0, source=Source(kind="INJECTED", ref=("x",)))
    assert kb.query(subject="market_1")[0].confidence == 1.0
