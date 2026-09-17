"""★ 多件同类型物件 = 多人可同时用。

bug: 编辑器在家里摆 3 张床/多份食物, load_scene 会把同类型物件【合并成一个
实体】并把数量记在 stock 上。旧占用模型 `claimed_by` 只能记一个人 → 第二个人
就被判“已被他人占用”, 于是 3 张床只睡 1 个人、多份食物只吃 1 个人。

修法(定死): 实体的【同时占用容量 = stock】(-1 = 无限)。一件实体代表 stock 个
可用单位, 因此最多 stock 人可同时占用它。
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.core.types import Interact
from citysim.gateway.scenarios import load_scene

CFG = load_config("config/sim.toml")


def _scene(item_type: str, n: int, *, stock: int | None = None) -> dict:
    ents = []
    for i in range(1, n + 1):
        e = {"id": f"{item_type}_{i:03d}", "type": item_type, "at": "home"}
        if stock is not None:
            e["stock"] = stock
        ents.append(e)
    return {
        "canvas": {"w": 400, "h": 300},
        "locations": {"home": {"type": "home_standard", "name": "家",
                               "x": 100, "y": 100, "w": 40, "h": 40}},
        "entities": ents,
        "npcs": [{"id": "a", "name": "甲", "home": "home", "money": 100},
                 {"id": "b", "name": "乙", "home": "home", "money": 100},
                 {"id": "c", "name": "丙", "home": "home", "money": 100}],
    }


def _load(tmp_path, data: dict):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_scene(p)


def _claim_all(w, s, entity_id: str, pids=("a", "b", "c")) -> list[bool]:
    out = []
    for pid in pids:
        w.place_npc(pid, "home")
        out.append(s.interaction.submit(
            w, w.npcs[pid], Interact(target_id=entity_id)))
    return out


def test_three_beds_merge_to_stock3_and_three_can_sleep(tmp_path) -> None:
    w, s, _r = _load(tmp_path, _scene("bed_basic", 3))
    beds = [e for e in w.entities.values() if e.item_type == "bed_basic"]
    assert len(beds) == 1, "同类型同地点的床应先合并成一个实体"
    bed = beds[0]
    assert bed.stock == 3, "合并后的库存应等于床数"

    assert _claim_all(w, s, bed.entity_id) == [True, True, True]
    assert bed.claimants == {"a", "b", "c"}
    # 容量 = 3 → 第四个人不行(这里用不存在的 d 直接查容量)
    assert bed.claimable_by("d") is False
    # 一个还没走, 就有床被占满
    assert bed.claimable_by("a") is True       # 自己已在用 → 可继续


def test_three_meals_merge_to_stock3_and_three_can_eat(tmp_path) -> None:
    w, s, _r = _load(tmp_path, _scene("meal_simple", 3))
    meals = [e for e in w.entities.values() if e.item_type == "meal_simple"]
    assert len(meals) == 1 and meals[0].stock == 3
    meal = meals[0]
    assert _claim_all(w, s, meal.entity_id) == [True, True, True]
    assert meal.claimants == {"a", "b", "c"}


def test_single_food_still_exclusive(tmp_path) -> None:
    """库存 1 的东西仍然是独占的(不能因为放开并发就变成随便抢)。"""
    w, s, _r = _load(tmp_path, _scene("toilet_basic", 1))
    toilet = [e for e in w.entities.values()
              if e.item_type == "toilet_basic"][0]
    assert toilet.stock == 1
    ok = _claim_all(w, s, toilet.entity_id)
    assert ok[0] is True
    assert ok[1] is False and ok[2] is False       # 后来者被占


def test_infinite_stock_allows_unlimited_concurrent(tmp_path) -> None:
    """stock=-1(无限) → 任意多个人可同时用。"""
    w, s, _r = _load(tmp_path, _scene("bed_basic", 1, stock=-1))
    bed = [e for e in w.entities.values() if e.item_type == "bed_basic"][0]
    assert bed.stock == -1
    assert _claim_all(w, s, bed.entity_id) == [True, True, True]
    assert bed.claimable_by("d") is True


def test_release_frees_a_slot(tmp_path) -> None:
    """release 后腾出一个名额, 下一个人能顶上。"""
    w, s, _r = _load(tmp_path, _scene("bed_basic", 1))
    bed = [e for e in w.entities.values() if e.item_type == "bed_basic"][0]
    w.place_npc("a", "home")
    w.place_npc("b", "home")
    assert s.interaction.submit(w, w.npcs["a"], Interact(target_id=bed.entity_id))
    assert not s.interaction.submit(w, w.npcs["b"], Interact(target_id=bed.entity_id))
    s.interaction.release_active(w, "a")
    assert s.interaction.submit(w, w.npcs["b"], Interact(target_id=bed.entity_id))
    assert bed.claimants == {"b"}


def test_eat_consumes_bed_does_not(tmp_path) -> None:
    """★ 区分"消耗"与"占用":
    - 食物: 吃完 stock-1; 三人同时吃 → 吃完 stock 归 0, 实体回收;
    - 床: 睡完 stock 不变; 三人同时睡 → 醒来 stock 仍是 3, 实体还在, 可再用。
    两者共用同一套 [当前占用人数 < stock] 名额判定 —— 所以都对。
    """
    w, s, _r = _load(tmp_path, _scene("meal_simple", 3))
    meal = [e for e in w.entities.values()
            if e.item_type == "meal_simple"][0]
    meal.duration_ticks = 1
    assert _claim_all(w, s, meal.entity_id) == [True, True, True]
    # 完成由 NPC 消化驱动(world 只收尾) —— 这里直接触发收尾, 测消耗账。
    for pid in ("a", "b", "c"):
        s.interaction.finish(w, pid, s.interaction.active[pid].handle)
    assert meal.stock == 0                       # 3 份被吃光
    assert meal.entity_id not in w.entities      # 空食物回收
    assert meal.claimants == set()

    w2, s2, _r2 = _load(tmp_path, _scene("bed_basic", 3))
    bed = [e for e in w2.entities.values() if e.item_type == "bed_basic"][0]
    bed.duration_ticks = 1
    assert _claim_all(w2, s2, bed.entity_id) == [True, True, True]
    for pid in ("a", "b", "c"):
        s2.interaction.finish(w2, pid, s2.interaction.active[pid].handle)
    assert bed.stock == 3                        # 床不消耗, 还是 3 张
    assert bed.entity_id in w2.entities
    assert bed.claimants == set()                # 但都醒了, 名额全空
    assert bed.claimable_by("d") is True
