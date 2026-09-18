"""★ 货物可合并、家具各摆各的 —— 两条路都保证"多件 = 多人能同时用"。

历史 bug: 编辑器摆 3 张床, load_scene 把同类型物件合并成一个实体、数量记在
stock 上; 旧的 `claimed_by` 只记一个人 → 3 张床只睡 1 个人。

现在的模型(用户拍板):
  · 【货物】(食物/原料…): 同类型同地点同归属同售价 → 数量合并成一个实体,
    stock = 总数; 可被消耗; 容量 = stock → 一"堆"货能被 N 人同时取。
  · 【家具】(床/马桶/工位/销售台…): 一件一个实体, stock 恒为 1, 永不合并,
    永不消耗 —— 3 张床就是 3 个实体, 3 个人各占一个。
  · 没有"无限库存"(-1)这回事。
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


def test_three_beds_stay_three_entities_so_three_can_sleep(tmp_path) -> None:
    """床是【家具】: 不合并、每件 stock=1 —— 3 张床 = 3 个实体, 3 人各占一个。"""
    w, s, _r = _load(tmp_path, _scene("bed_basic", 3))
    beds = sorted((e for e in w.entities.values() if e.item_type == "bed_basic"),
                  key=lambda e: e.entity_id)
    assert len(beds) == 3, "家具不合并: 三张床就是三个实体"
    assert all(b.stock == 1 for b in beds), "家具数量恒为 1"
    # 一人一张床 → 都睡得下(各占各的实体)
    for pid, bed in zip(("a", "b", "c"), beds):
        w.place_npc(pid, "home")
        assert s.interaction.submit(w, w.npcs[pid],
                                    Interact(target_id=bed.entity_id)) is True
    # 一张床仍然只能一个人用
    assert beds[0].claimable_by("d") is False


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


def test_furniture_stock_is_normalized_to_one(tmp_path) -> None:
    """家具数量恒为 1 —— 场景里写 -1/5 都会被归一, 且一次只一个人用。

    (没有"无限库存"这回事: 想多一个就多摆一件。)
    """
    w, s, _r = _load(tmp_path, _scene("toilet_basic", 1, stock=-1))
    t = [e for e in w.entities.values() if e.item_type == "toilet_basic"][0]
    assert t.stock == 1 and t.is_furniture
    assert _claim_all(w, s, t.entity_id) == [True, False, False]


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
    - 食物(货物): 吃完 stock-1; 三人同时吃一堆 → 吃完 stock 归 0;
      ★ 有价的货(在售/货架)归 0 也留壳 —— 不然"开门前补货"再也找不到该补什么
        (实测: 店里苹果卖空那一刻实体被销毁 → 永远不再进货 → 全城饿死)
    - 床(家具):   睡完 stock 不变(恒为 1), 实体还在, 可以再睡。
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
    # 有价的货 = 货架: 留壳等补货(免费的食物才回收)
    assert meal.entity_id in w.entities
    assert meal.claimants == set()

    w2, s2, _r2 = _load(tmp_path, _scene("bed_basic", 1))
    bed = [e for e in w2.entities.values() if e.item_type == "bed_basic"][0]
    bed.duration_ticks = 1
    w2.place_npc("a", "home")
    assert s2.interaction.submit(w2, w2.npcs["a"],
                                 Interact(target_id=bed.entity_id)) is True
    s2.interaction.finish(w2, "a", s2.interaction.active["a"].handle)
    assert bed.stock == 1                        # 家具不消耗, 还是 1
    assert bed.entity_id in w2.entities
    assert bed.claimants == set()                # 睡醒 → 名额空出来
    assert bed.claimable_by("d") is True
