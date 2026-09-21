"""语义层(说什么) + 措辞层(怎么说)。

    act: STATE / INTENT / SURPRISE / DOUBT (+ REPORT 转述 / SAY 说者那半句)
    分层: npc/semantic.py 产【结构化事件】; gateway/lines.py 才拼句子。
    随机只在措辞层 —— 谁/什么行为/什么强度全部为真。

验收:
  · “来了发现与听说不符” → DOUBT
  · 台词不重复(组合式模板池 + 话题冷却)
  · ★ fact(传播真值) 里的价格是【数字】—— 一早就变成 "8块" 就没法衰减了
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.game import lines
from citysim.npc import semantic
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def _see(w, npc, tick: int = 10):
    from citysim.world.edge.perception import build_percept
    npc.perceive(build_percept(w, npc), tick)


# ---------------------------------------------------------------------------
# 措辞层
# ---------------------------------------------------------------------------
def test_render_is_deterministic_and_varied() -> None:
    """同一个人说同一件事 → 同一句话(可回放); 不同人 → 有变化(不千篇一律)。"""
    ev = semantic.surprise(100, "npc_a", "apple", "苹果", 5.0, 8.0)
    again = semantic.surprise(100, "npc_a", "apple", "苹果", 5.0, 8.0)
    assert lines.render(ev) == lines.render(again)            # 确定
    got = {lines.render(semantic.surprise(100, "npc_%d" % i,
                                          "apple", "苹果", 5.0, 8.0))
           for i in range(8)}
    assert len(got) > 1, got                                  # 池子真的被用到了


def test_render_only_uses_slot_values() -> None:
    """槽位只许真值: 渲染出来的人名/物品名必须来自槽位, 且不许留占位符。"""
    ev = semantic.doubt(1, "npc_a", "apple", "苹果", "王哥", 5.0, 8.0)
    text = lines.render(ev)
    assert "苹果" in text
    assert "小明" not in text          # 没这个槽, 就不许出现在台词里
    assert "{" not in text and "}" not in text   # 不许漏出未填的占位符


def test_money_word() -> None:
    assert lines.money_word(5) == "5块"
    assert lines.money_word(4.5) == "4.5块"
    assert lines.money_word(0) == "免费"


def test_words_are_made_at_render_time_not_in_the_event() -> None:
    """★ 关键分层: 事件里存【数字】, 说成"8块"是渲染的事。

    这是一条真约束 —— 设计决定 #18 要求“精度衰减按 remember 分桶, 只丢精度
    不造新信息”。价格如果早在事件里变成字符串, 衰减就只能改字了。
    """
    ev = semantic.surprise(100, "npc_a", "apple", "苹果", 5.0, 8.0,
                           fact={"item_id": "apple", "price": 8.0})
    assert ev.slots["now"] == 8.0, "事件里必须是数字"
    assert ev.fact["price"] == 8.0, "传播真值里也必须是数字"
    assert "8块" in lines.render(ev), "到了渲染才变成人话"
    # 渲染不改事件(纯函数)
    assert ev.slots["now"] == 8.0


# ---------------------------------------------------------------------------
# 触发点: 预期 vs 观察
# ---------------------------------------------------------------------------
def test_price_change_is_surprise() -> None:
    w, s, _ = make_runtime(CFG)
    e = add_entity(w, "apple", location="loc", affordances={"hunger": 0.5})
    e.price = 8.0
    npc = add_npc(w, s, "npc", location="loc")
    npc.note("apple", located="loc", afford="hunger", value=0.5,
             price=5.0, believe=1.0)
    _see(w, npc)
    ev = npc.pending_speech(10)
    assert ev is not None and ev.act == "SURPRISE", ev
    assert "8" in lines.render(ev)


def test_heard_price_then_refuted_is_doubt() -> None:
    """信念被现实推翻 —— 而且这条记忆本来是【别人说的】。"""
    w, s, _ = make_runtime(CFG)
    e = add_entity(w, "apple", location="loc", affordances={"hunger": 0.5})
    e.price = 8.0
    npc = add_npc(w, s, "npc", location="loc")
    npc.set_name_lookup(lambda pid: {"npc_wang": "王哥"}.get(str(pid), ""))
    npc.note("apple", located="loc", afford="hunger", value=0.5, price=5.0,
             believe=0.7, source="npc_wang")
    _see(w, npc)
    ev = npc.pending_speech(10)
    assert ev is not None and ev.act == "DOUBT", ev
    assert ev.source == "npc_wang"                  # 可追溯“该怪谁”
    assert "王哥" in lines.render(ev)


def test_sold_out_is_surprise() -> None:
    w, s, _ = make_runtime(CFG)
    e = add_entity(w, "apple", location="loc", affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", location="loc")
    npc.note("apple", located="loc", afford="hunger", value=0.5, stock=5)
    e.stock = 0
    _see(w, npc)
    ev = npc.pending_speech(10)
    assert ev is not None and ev.act == "SURPRISE"
    assert "卖光" in lines.render(ev)


def test_first_sight_says_nothing() -> None:
    """第一次见的东西没有“预期”, 谈不上落差 → 不说话。"""
    w, s, _ = make_runtime(CFG)
    add_entity(w, "apple", location="loc", affordances={"hunger": 0.5})
    npc = add_npc(w, s, "npc", location="loc")
    _see(w, npc)
    assert npc.pending_speech(10) is None


# ---------------------------------------------------------------------------
# 优先级 + 冷却
# ---------------------------------------------------------------------------
def test_doubt_beats_intent() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    npc._push_speech(semantic.intent(1, "npc", "hunger", "now"))
    npc._push_speech(semantic.doubt(2, "npc", "apple", "苹果", "王哥",
                                    5.0, 8.0))
    ev = npc.pending_speech(10)
    assert ev.act == "DOUBT"                        # 优先级高者先出


def test_topic_cooldown() -> None:
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc")
    npc._push_speech(semantic.intent(1, "npc", "hunger", "now",
                                     topic="hunger"))
    assert npc.pending_speech(10) is not None       # 第一次说
    npc._push_speech(semantic.intent(11, "npc", "hunger", "now",
                                     topic="hunger"))
    assert npc.pending_speech(20) is None           # 冷却内不复读
    assert npc.pending_speech(10 + 600) is not None  # 冷却过了再说


# ---------------------------------------------------------------------------
# 传播: 新闻要能带走
# ---------------------------------------------------------------------------
def test_gossip_carries_a_fact_not_my_own_furniture() -> None:
    """能转述的是“外面的货”, 不是我家里的床/马桶。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc", home="home")

    npc.note("bed_1", located="home", afford="energy", value=0.7)   # 自家家具
    npc.note("apple", located="market", afford="hunger", value=0.5,
             price=5.0, source="npc_wang")                          # 外面的新闻
    picked = semantic.pick_retellable(npc.memory_dicts(), home="home",
                                      knows=lambda _i: False)
    assert picked is not None and picked["item_id"] == "apple"


def test_no_worthwhile_news_stays_silent() -> None:
    """没话可说就不说 —— 旧版是“硬抄一行记忆”(于是张嘴就是自家马桶)。"""
    w, s, _ = make_runtime(CFG)
    npc = add_npc(w, s, "npc", location="loc", home="home")

    npc.note("bed_1", located="home", afford="energy", value=0.7)
    assert semantic.pick_retellable(npc.memory_dicts(), home="home",
                                    knows=lambda _i: False) is None


def test_render_is_used_for_bubbles_end_to_end() -> None:
    """端到端: 看到价格变了 → 气泡里挂着的那条事件能渲染成一句人话。"""
    w, s, rng = make_runtime(CFG, log=True)
    e = add_entity(w, "apple", location="loc", affordances={"hunger": 0.5})
    e.price = 8.0
    npc = add_npc(w, s, "npc", location="loc", rng_pool=rng)
    npc.note("apple", located="loc", afford="hunger", value=0.5, price=5.0)
    run_tick(w, s, CFG, rng)
    line, _until, kind = npc.bubble
    assert kind == "SURPRISE"
    assert isinstance(line, semantic.SemanticEvent), \
        "气泡里挂的应当是【事件】, 不是渲染好的文本"
    assert "8" in lines.render(line, ticks_per_day=CFG.ticks_per_day)
