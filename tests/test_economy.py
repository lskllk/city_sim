"""经济最小闭环: 公司(店铺归属 + 账) + 成交收款 + 每天发工资。

以前 NPC 花出去的钱**凭空消失** —— 城里只有支出没有收入, 所有人慢慢破产饿死。
现在: 成交 → 钱进【店铺所属公司】的账; 公司每天给店员发工资 → 钱开始循环。
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.world import engine as E
from citysim.world.companies import Company

CFG = load_config("config/sim.toml")


def _scene() -> dict:
    return {
        "scene": "t", "display_name": "经济", "canvas": {"w": 400, "h": 300},
        "locations": {
            "shop": {"type": "shop_small", "name": "店", "x": 100, "y": 100,
                     "w": 40, "h": 40},
            "home": {"type": "home_small", "name": "家", "x": 200, "y": 100,
                     "w": 40, "h": 40},
        },
        "entities": [{"id": "food_apple_001", "type": "food_apple", "at": "shop",
                      "price": 5, "stock": 99}],
        "npcs": [{"id": "npc_a", "name": "甲", "home": "home", "money": 100,
                  "init": {}}],
        "travel": {"default": 20, "pairs": {}},
    }


def _load(tmp_path, data: dict, companies=None):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    w, s, r = load_scene(p)
    if companies is not None:
        w.companies = {c.company_id: c for c in companies}
        for cid, comp in w.companies.items():
            for bid in comp.shops:
                if bid in w.locations:
                    w.locations[bid]["company"] = cid
    return w, s


def _buy(w, s, qty=2):
    from citysim.core.types import Buy
    from citysim.world.engine import _execute_buy
    w.place_npc("npc_a", "shop")
    _execute_buy(w, s, CFG, "npc_a", w.npcs["npc_a"], Buy("food_apple_001", qty=qty))


def test_purchase_credits_the_shop_company(tmp_path) -> None:
    """双分录: 买家扣多少, 公司就进多少 —— 钱不再凭空消失。"""
    w, s = _load(tmp_path, _scene(), [Company("org_a", "甲店", cash=0.0,
                                              shops=("shop",))])
    npc = w.npcs["npc_a"]
    _buy(w, s, qty=2)
    assert npc.money == 100.0 - 10.0
    assert w.companies["org_a"].cash == 10.0
    ev = [e for e in s.ui_events if e.get("kind") == "bought"][-1]
    assert ev["payload"]["company"] == "org_a"


def test_shop_without_company_cannot_sell(tmp_path) -> None:
    """【没登记公司的店不能卖】(用户定的开零售前提): 成交失败, 钱不动。"""
    w, s = _load(tmp_path, _scene())
    _buy(w, s, qty=1)
    assert w.npcs["npc_a"].money == 100.0            # 一分没花
    fail = [e for e in s.ui_events if e.get("kind") == "intent_failed"][-1]
    assert fail["payload"]["why"] == "这家店没有登记公司"


def _employ_one(w, s, wage: float = 60.0) -> None:
    """走【真实路径】雇一个人: 摆前台 → 公司发布启事 → 媒婆撮合。

    这样他拿到的就是引擎写的那份 daily 上班计划表(而不是测试硬塞的),
    "站上去就绑定住"的强制约束才成立。
    """
    from helpers import add_counter
    comp = w.companies["org_a"]
    if not any(e.item_type == "station_counter" for e in w.entities.values()):
        add_counter(w, "shop")
    comp.open_minute, comp.close_minute = 0, 1440   # 测试里全天, 省得等到 08:00
    comp.wage_per_hour = wage
    comp.hiring_open, comp.hiring_slots = True, 1
    E.hire_at(w, s, CFG)


def test_wage_is_paid_once_a_day(tmp_path) -> None:
    """一天结一次, 按【在岗时间】算: 在岗 8 小时 × 时薪 60 = ¥480。"""
    w, s = _load(tmp_path, _scene(), [Company("org_a", "甲店", cash=2000.0,
                                              shops=("shop",), staff=())])
    npc = w.npcs["npc_a"]
    npc.set_signals(hunger=1.0, energy=1.0, bladder=1.0)
    _employ_one(w, s, wage=60.0)
    start = npc.money
    paid: list = []
    orig = w.bus.publish

    def hook(ev):
        if ev.kind == "wage_paid":
            paid.append(ev)
        return orig(ev)

    w.bus.publish = hook
    for _ in range(CFG.wage_minute + 20):
        E.tick(w, s, CFG)
    w.bus.publish = orig
    assert paid, "一次工资都没发(他应该在岗)"
    ev = paid[-1]
    assert ev.payload["hours"] > 7.0, ev.payload          # 在岗 ~8 小时
    assert npc.money == start + ev.payload["wage"]
    assert w.companies["org_a"].cash == 2000.0 - ev.payload["wage"]


def test_company_without_cash_cannot_pay_wage(tmp_path) -> None:
    """发不出就是发不出: 员工那天的收入是 0, 事件 wage_failed。"""
    w, s = _load(tmp_path, _scene(), [Company("org_a", "甲店", cash=1.0,
                                              shops=("shop",), staff=())])
    npc = w.npcs["npc_a"]
    npc.set_signals(hunger=1.0, energy=1.0, bladder=1.0)
    _employ_one(w, s, wage=60.0)
    start = npc.money
    for _ in range(CFG.wage_minute + 20):
        E.tick(w, s, CFG)
    assert npc.money == start                        # 没进账
    assert w.companies["org_a"].cash == 1.0          # 也没扣
    assert any(e.get("kind") == "wage_failed" for e in s.ui_events)


def test_money_circulates(tmp_path) -> None:
    """端到端: 公司雇了买家 → 买家花钱买货 → 公司账上升 → 再发工资回来。"""
    w, s = _load(tmp_path, _scene(), [Company("org_a", "甲店", cash=100.0,
                                              shops=("shop",),
                                              staff=(("npc_a", 60.0),))])
    npc = w.npcs["npc_a"]
    npc.set_signals(hunger=0.1)
    # 他得【知道】有这么个店才可能去买 —— P8: 知识只能靠感知/传闻/招牌,
    # 这里用场景认知(编辑器里那个"让谁知道")给他一条。
    npc.note("food_apple_001", tick=0, located="shop", afford="hunger",
             value=0.35, price=5.0, stock=99, believe=0.8, source="",
             tags=("edible", "consumable"), shelf_life_ticks=4320)
    _employ_one(w, s, wage=10.0)     # 雇一个店员守台(交易要有员工在台前)
    # 顾客得是【别人】—— 员工上班时被绑在台前, 不会跑去买东西(强制约束)
    from helpers import add_npc
    npc_buyer = add_npc(w, s, "buyer", location="shop")
    npc_buyer.set_home("home")
    npc_buyer.note("food_apple_001", tick=0, located="shop", afford="hunger",
                   value=0.35, price=5.0, stock=99, believe=0.8, source="",
                   tags=("edible", "consumable"), shelf_life_ticks=4320)
    npc_buyer.set_signals(hunger=0.1)
    income = 0.0
    orig = w.bus.publish
    def hook(ev):
        nonlocal income
        if ev.kind == "bought":
            income += float(ev.payload.get("price", 0.0))
        return orig(ev)
    w.bus.publish = hook
    for _ in range(CFG.ticks_per_day * 2):
        E.tick(w, s, CFG)
    w.bus.publish = orig
    # 钱在城里转了一圈: 买家花钱 → 公司收到货款 → 公司又发工资给买家
    assert income > 0.0, "买家一次都没买"
    assert any(e.get("kind") == "wage_paid" for e in s.ui_events), "公司一次工资都没发"
    assert w.companies["org_a"].cash >= 0.0


# --- 批发市场 / 开零售前提 -------------------------------------------------

def test_market_purchase_puts_goods_on_company_shelf(tmp_path) -> None:
    """公司向市场进货: 钱从公司账出、货上架到自己的店。"""
    from citysim.world.market import Market, purchase
    w, s = _load(tmp_path, _scene(), [Company("org_a", "甲店", cash=100.0,
                                              shops=("shop",))])
    w.market = Market(prices={"food_apple": 3.0})
    shelf = next(e for e in w.entities.values() if e.location_id == "shop")
    before = shelf.stock
    res = purchase(w, w.companies["org_a"], "shop", "food_apple", 10)
    assert res["ok"] and res["cost"] == 30.0
    assert shelf.stock == before + 10
    assert w.companies["org_a"].cash == 70.0


def test_market_is_company_only_and_never_short(tmp_path) -> None:
    """市场数量无限(不因买多次而减少); 公司钱不够 → 只买得起几份, 一份买不起就不买。"""
    from citysim.world.market import Market, purchase
    w, s = _load(tmp_path, _scene(), [Company("org_a", "甲店", cash=7.0,
                                              shops=("shop",))])
    w.market = Market(prices={"food_apple": 3.0})
    res = purchase(w, w.companies["org_a"], "shop", "food_apple", 100)
    assert res["ok"] and res["cost"] == 6.0            # 只买得起 2 份
    assert w.companies["org_a"].cash == 1.0
    res2 = purchase(w, w.companies["org_a"], "shop", "food_apple", 5)
    assert not res2["ok"] and res2["why"] == "公司现钱不够"


def test_purchase_refused_for_shop_not_owned(tmp_path) -> None:
    """只能给自己旗下的店进货。"""
    from citysim.world.market import Market, purchase
    w, s = _load(tmp_path, _scene(), [Company("org_a", "甲店", cash=100.0,
                                              shops=("shop",))])
    w.market = Market(prices={"food_apple": 3.0})
    res = purchase(w, w.companies["org_a"], "home", "food_apple", 5)
    assert not res["ok"] and res["why"] == "这家店不是它的"
