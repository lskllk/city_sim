"""制造公司(加工厂) + 商品原料 —— 城市的第一笔"外部收入"。

用户定的规矩:
  · 注册公司时选类型: retail(零售) / manufacture(制造)。
  · 制造公司**没有进货/上架** —— 只有【工人站工位产出原料】。
  · 产出的原料**不能给员工吃**(它没有 affordance → 谁都吃不了, 天然成立)。
  · 批发市场(= 城外)每天 collect_minute 按【物品定义里的价】全收 → 钱进城。
  · 产量按【在岗时间】算, 熟练度 2(新) → 5(老手)。
"""
from __future__ import annotations

import json
from pathlib import Path

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.sim.loop import run_tick
from citysim.world.econ.factory import skill_of
from citysim.world.econ.market import market_catalog, purchase, restock_all, wholesale_price
from citysim.world.model.itemdefs import load_item_defs

CFG = load_config(Path("config/sim.toml"))


# --- 物品与价格 ---------------------------------------------------------

def test_material_price_is_80_percent_of_the_good() -> None:
    """原料价 = 对应成品的 80% —— 差价就是城外加工业的利润(城市出口原料)。"""
    defs = load_item_defs()
    raw, good = defs["meal_simple_raw"], defs["meal_simple"]
    assert raw.price == good.price * 0.8


def test_material_cannot_be_eaten_or_used() -> None:
    """原料【没有 affordance】 → 谁都用不了 → "产出的货不能给员工吃"天然成立。"""
    raw = load_item_defs()["meal_simple_raw"]
    assert dict(raw.affordances) == {}
    assert "material" in raw.tags


def test_material_is_not_retailable() -> None:
    """原料不进零售目录, 也不能被零售公司进货(它只由批发市场收购)。"""
    assert not any(c["type"] == "meal_simple_raw" for c in market_catalog())


# --- 场景: 一家加工厂 ---------------------------------------------------

def _factory_scene(**over) -> dict:
    base = {
        "scene": "f", "display_name": "厂", "canvas": {"w": 600, "h": 400},
        "locations": {
            "plant": {"type": "factory_plant", "name": "加工厂",
                      "x": 300, "y": 100, "w": 40, "h": 40},
            "home": {"type": "home_small", "name": "家",
                     "x": 100, "y": 100, "w": 40, "h": 40},
        },
        "companies": [{
            "id": "org_plant", "name": "商品加工厂", "shops": ["plant"],
            "cash": 1000, "produces_item": "meal_simple_raw",
            "open": "08:00", "close": "19:00", "wage_per_hour": 1.5,
            "hiring_slots": 0, "staff": [{"npc": "a", "station": "w"}],
        }],
        "entities": [
            {"id": "w", "type": "station_workbench", "at": "plant"},
            {"id": "m", "type": "meal_simple", "at": "home", "stock": 99},
        ],
        "npcs": [{"id": "a", "name": "阿甲", "home": "home", "money": 100,
                  "init": {"hunger": 0.9}}],
        "travel": {"default": 20, "pairs": {}},
    }
    base.update(over)
    return base


def _load(tmp_path, data):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_scene(p)


def test_manufacture_company_from_scene(tmp_path) -> None:
    w, _s, _r = _load(tmp_path, _factory_scene())
    c = w.companies["org_plant"]
    assert c.kind == "manufacture" and c.produces_item == "meal_simple_raw"


def test_factory_produces_on_shift_and_market_collects_at_midnight(tmp_path) -> None:
    """端到端: 工人上岗 → 攒出原料 → 零点被批发市场按原料价全收 → 公司现金涨。

    这就是"钱从城外进来"的口子 —— 没有它, 城市只会一天天变穷。
    """
    w, s, rng = _load(tmp_path, _factory_scene())
    comp = w.companies["org_plant"]
    npc = w.npcs["a"]
    for _ in range(2 * 1440):
        run_tick(w, s, CFG, rng)
    assert npc.skill_ticks > 0, "上岗就该计时(工资/熟练度共用这把闸门)"
    assert s.production or comp.cash > 1000.0, "在生产, 或者已经交货换到钱"
    # 零点收货之后厂里不该还堆着货(全被收走)
    piles = [e for e in w.entities.values()
             if e.owner == "org_plant" and e.item_type == "meal_simple_raw"]
    assert sum(e.stock for e in piles) == 0 or w.clock_tick % 1440 != 0
    assert comp.cash > 1000.0, "收货的钱应该进公司账(城市经济来源)"


def test_produced_material_belongs_to_the_company(tmp_path) -> None:
    """产出归属公司 —— 员工拿不走(它没 affordance, 也进不了候选)。"""
    w, s, rng = _load(tmp_path, _factory_scene())
    for _ in range(1440):
        run_tick(w, s, CFG, rng)
    assert all(e.owner == "org_plant" for e in w.entities.values()
               if e.item_type == "meal_simple_raw")


def test_market_rejects_material_purchase(tmp_path) -> None:
    w, _s, _r = _load(tmp_path, _factory_scene())
    res = purchase(w, w.companies["org_plant"], "plant", "meal_simple_raw", 5)
    assert res["ok"] is False


def test_restock_skips_manufacture_company(tmp_path) -> None:
    """制造公司不进货 —— 它的货是自己产的(补货只属于零售公司)。"""
    w, _s, _r = _load(tmp_path, _factory_scene())
    before = w.companies["org_plant"].cash
    restock_all(w)
    assert w.companies["org_plant"].cash == before


# --- 产量与熟练度 -------------------------------------------------------

def test_skill_grows_from_min_to_max_and_never_beyond() -> None:
    assert skill_of(0, CFG) == CFG.produce_skill_min
    half = skill_of(CFG.produce_skill_full_ticks / 2.0, CFG)
    assert CFG.produce_skill_min < half < CFG.produce_skill_max
    assert skill_of(CFG.produce_skill_full_ticks, CFG) == CFG.produce_skill_max
    assert skill_of(CFG.produce_skill_full_ticks * 10, CFG) == CFG.produce_skill_max


def test_unit_ticks_make_a_newcomer_break_even(tmp_path) -> None:
    """一份的工时口径必须让【新手也养得活自己】:

      base = 一天在岗 ÷ 一天消耗份数 —— 于是 k=1 时他挣的刚好等于自己吃的,
      k=2/5 就是净赚倍数。若按"一份能顶多久"(360)算, 分母是全天消耗、
      分子只有在岗时间 → 新手必然入不敷出(实测过)。

      这里用【一整天都在工位上】的理想情形验算: 产出的钱 ≥ 吃掉的钱。
    """
    tpd = CFG.ticks_per_day
    on_shift = 660                       # 一天一班 11 小时(和场景里的 08:00-19:00 一致)
    afford = float(load_item_defs()["meal_simple"].affordances["hunger"])
    eat_per_day = tpd * abs(float(CFG.metabolism["hunger"])) / afford   # 一天吃几份
    for k in (CFG.produce_skill_min, CFG.produce_skill_max):
        made = on_shift / (CFG.produce_base_ticks / k)            # 这一班产几份
        income = made * wholesale_price(None, "meal_simple_raw")
        cost = eat_per_day * wholesale_price(None, "meal_simple")
        assert income > cost, "k=%s 时要养得活自己" % k


def test_manufacture_company_auto_assigns_workbenches(tmp_path) -> None:
    """作者只勾了"谁在这上班"、没指岗位时: 制造公司自动派【工位】

    (零售公司派销售台 —— 岗位长什么样由公司类型定, 见 company.stations_of)
    """
    scene = _factory_scene()
    scene["companies"][0]["staff"] = ["a"]            # ← 不给 station
    w, _s, _r = _load(tmp_path, scene)
    assert w.npcs["a"].work.get("station") == "w"


def test_fixture_catalog_is_tagged_by_company_kind() -> None:
    """装修件标了"归哪类公司用" —— 零售看到销售台, 加工厂看到工位, 马桶通用。

    靠物品 tag(不写死类型清单): 加新家具只要打 fixture + 类型 tag。
    """
    from citysim.world.econ.market import fixture_catalog
    k = {f["type"]: f["kinds"] for f in fixture_catalog()}
    assert k["station_counter"] == ["retail"]
    assert k["station_workbench"] == ["manufacture"]
    assert k["toilet_basic"] == []                     # 空 = 通用


def test_company_kind_is_decided_by_the_building(tmp_path) -> None:
    """类型由【建筑】定死: 店铺只能零售、工厂只能制造, 别处不能开公司。

    为什么: 类型和岗位对不上就招不到人(实测: 零售公司里摆工位 → 零岗位 → 无人应聘)。
    """
    from citysim.world.model.companies import kind_for_building
    assert kind_for_building("shop") == "retail"
    assert kind_for_building("factory") == "manufacture"
    assert kind_for_building("home") == "" and kind_for_building("market") == ""
    # 场景里把制造公司写在店铺上 → 以建筑为准, 纠正成零售
    scene = _factory_scene()
    scene["companies"][0]["kind"] = "manufacture"
    scene["locations"]["plant"]["type"] = "shop_small"
    w, _s, _r = _load(tmp_path, scene)
    assert w.companies["org_plant"].kind == "retail"
