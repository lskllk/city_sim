"""事件顺序契约回归(放行前置, 疑点修复踩过的坑)。

契约: 消耗品吃完的「回收」必须发生在 `interaction_done` 事件发布**之后**——
否则事件观察者(soak 分类 / 未来客户端)按实体查 tags 会查不到已回收的实体。
本测试直接锁死: interaction_done 回调那一刻, 被吃的实体仍可从 world 查到;
回调返回后实体才被移除。
"""
from __future__ import annotations

from pathlib import Path

from citysim.core.config import load_config
from citysim.sim.loop import run_tick

from helpers import add_entity, add_npc, make_runtime, seed_reviews

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "sim.toml")


def test_interaction_done_before_consumable_removed() -> None:
    world, systems, rng_pool = make_runtime(CFG)
    food = add_entity(world, "food_1", tags=("edible", "consumable"),
                      affordances={"hunger": 0.5}, duration_ticks=3, stock=1)
    seen_at_done: list[bool] = []

    def _on_ev(ev):
        if ev.kind == "interaction_done" \
                and ev.payload.get("entity") == "food_1":
            # 事件回调当下: 实体必须仍可观察(回收尚未执行)
            seen_at_done.append(food.entity_id in world.entities)

    world.bus.subscribe_log(_on_ev)
    add_npc(world, systems, "npc", rng_pool=rng_pool, seed=1, hunger=0.2)
    seed_reviews(world, systems)
    for _ in range(40):
        run_tick(world, systems, CFG, rng_pool)

    # 事件确实发生, 且回调时实体尚在(契约成立)
    assert seen_at_done, "未观察到 interaction_done(food_1)"
    assert all(seen_at_done), "interaction_done 回调时实体已被回收(时序契约破坏)"
    # 回调返回后(事件已发布)实体被移除 —— 无泄漏
    assert "food_1" not in world.entities
