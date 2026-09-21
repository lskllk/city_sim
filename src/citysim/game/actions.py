"""game/actions —— 经营动词: 老板(玩家或对手 NPC)能对世界做的事。

**铁律: 这一层只改世界真值, 不做任何模拟计算。**

改完价不等于顾客知道了 —— 顾客要**看见**或**听人说**才知道(见 npc/memory
的"观察有条件")。"定价 / 雇人 / 装修"之所以能成为玩法, 正是因为它们只改
真值、不直接改认知: 你的优势来自情报, 不来自点一下就生效。

这一层同时是【玩家面板】和【对手老板 AI】的**同一个接口** —— 设计决定 #19
说对手是"和你受同样约束的对称 agent"。所以这里的函数不许有任何只有玩家
才有的特权(比如直接读全城行情)。谁调用它, 拿到的能力都一模一样。

全部走 `citysim.api`, 不摸内核深层模块(gateway/ 除外 —— 那是纯数据桥)。
"""
from __future__ import annotations

from citysim import api

COMPANY_KINDS = ("retail", "manufacture")   # 零售 / 制造(加工厂)


def company_list(world) -> list:
    """全部公司的面板视图(给前端刷新用)。只读。"""
    return [{"id": cid, "name": c.name, "cash": round(c.cash, 2),
             "owner": c.owner, "shops": list(c.shops),
             "kind": c.kind, "produces_item": c.produces_item,
             "open_minute": c.open_minute, "close_minute": c.close_minute,
             "wage_per_hour": c.wage_per_hour, "restock_to": c.restock_to,
             "hiring_open": c.hiring_open, "hiring_slots": c.hiring_slots,
             "staff": [{"npc": n, "wage": w} for n, w in c.staff]}
            for cid, c in sorted(world.companies.items())]


def register_company(world, args: dict) -> dict:
    """点一个商铺建筑 → 注册公司。

    公司类型【由建筑定死】(店铺→零售 / 工厂→制造); args 里的 kind 只做
    一致性检查, 不给你改。制造公司必须指定产出什么。
    """
    loc = str(args.get("location", ""))
    loc_rec = world.locations.get(loc)
    if not loc_rec:
        return {"ok": False, "why": "没有这个建筑", "company": ""}
    if loc_rec.get("company"):
        return {"ok": False, "why": "这栋楼已经登记过公司了",
                "company": str(loc_rec["company"])}
    bkind = str(loc_rec.get("kind", ""))
    if not api.kind_for_building(bkind):
        return {"ok": False, "why": "这栋楼不能开公司(要【店铺】或【工厂】)",
                "company": ""}
    name = str(args.get("name", "")).strip()
    if name == "":
        return {"ok": False, "why": "公司名不能空", "company": ""}
    kind = api.kind_for_building(bkind)
    if "kind" in args and str(args["kind"]) not in ("", kind):
        return {"ok": False,
                "why": "这栋楼只能开【%s】公司(类型由建筑定)" % kind,
                "company": ""}
    produces = str(args.get("produces_item", ""))
    if kind == "manufacture" and produces == "":
        return {"ok": False, "why": "制造公司要指定产出什么(produces_item)",
                "company": ""}
    cid = "org_%s" % loc
    world.companies[cid] = api.Company(
        company_id=cid, name=name, kind=kind, produces_item=produces,
        cash=float(args.get("cash", 1000.0)), shops=(loc,))
    loc_rec["company"] = cid
    return {"ok": True, "why": None, "company": cid,
            "companies": company_list(world)}


def admin_company(world, systems, cfg, op: str, args: dict) -> dict:
    """经营动作总入口(上帝视角 / 老板面板 / 对手 AI 共用)。**只改世界真值**。

    op:
      register  点一个商铺建筑 → 注册公司 {location, name, cash?,
                kind?, produces_item?}  kind: retail(默认)/manufacture(加工厂)
      update    改参数 {company, cash/open_minute/close_minute/wage_per_hour/
                        restock_to/kind/produces_item}
      wage      改【某个员工】的时薪 {company, npc, wage}  ← 逐人, 不动公司默认时薪
      hire      发布/撤回招聘启事 {company, slots, wage_per_hour?} ← 招不招人公司说了算
      assign    给员工分派销售台 {company, npc, station}("" = 撤销)
      schedule  给员工排班 {company, npc, open, close}  ← 只改他自己
      restock   向市场进货 {company, shop?, item_type, qty}
      decorate  给店摆装修件 {company, shop?, item_type, public?}
    注: 招聘只是【发布启事】, 真正撮合还是每天 hire_minute 那次(媒婆)。
    """
    if op == "register":
        return register_company(world, args)
    cid = str(args.get("company", ""))
    comp = world.companies.get(cid)
    if comp is None:
        return {"ok": False, "why": "没有这家公司", "company": cid}
    if op == "update":
        for k in ("cash", "wage_per_hour", "restock_to"):
            if k in args:
                setattr(comp, k, float(args[k]))
        for k in ("open_minute", "close_minute"):
            if k in args:
                setattr(comp, k, int(args[k]))
        if "kind" in args and str(args["kind"]) in COMPANY_KINDS:
            comp.kind = str(args["kind"])
        if "produces_item" in args:
            comp.produces_item = str(args["produces_item"])
        if args.get("name"):
            comp.name = str(args["name"])
        return {"ok": True, "why": None, "company": cid,
                "companies": company_list(world)}
    if op == "wage":
        # 逐人时薪(和公司时薪 wage_per_hour 是两回事): 改公司的 payroll
        # + 本人的 _work(决策层用它算"离岗亏多少钱")。
        nid = str(args.get("npc", ""))
        npc = world.npcs.get(nid)
        if npc is None:
            return {"ok": False, "why": "没有这个人", "company": cid}
        if nid not in [n for n, _ in comp.staff]:
            return {"ok": False, "why": "这个人不是本公司员工", "company": cid}
        try:
            wage = max(0.0, float(args.get("wage", 0.0)))
        except (TypeError, ValueError):
            return {"ok": False, "why": "时薪要填数字", "company": cid}
        comp.staff = tuple((n, wage if n == nid else w) for n, w in comp.staff)
        npc.assign(api.Wage(wage))
        return {"ok": True, "why": None, "company": cid,
                "companies": company_list(world)}
    if op == "hire":
        slots = max(0, int(args.get("slots", 0)))
        comp.hiring_slots = slots
        comp.hiring_open = slots > 0
        if "wage_per_hour" in args:
            comp.wage_per_hour = float(args["wage_per_hour"])
        return {"ok": True, "why": None, "company": cid,
                "companies": company_list(world)}
    if op == "restock":
        shop = str(args.get("shop", "") or (comp.shops[0] if comp.shops else ""))
        item = str(args.get("item_type", ""))
        qty = int(args.get("qty", 0))
        res = api.purchase(world, comp, shop, item, qty)
        res["company"] = cid
        return res
    if op == "assign":
        res = api.assign_station(world, systems, cfg, comp,
                                 str(args.get("npc", "")),
                                 str(args.get("station", "")))
        res["company"] = cid
        return res
    if op == "schedule":
        res = api.schedule_worker(world, systems, cfg, comp,
                                  str(args.get("npc", "")),
                                  int(args.get("open", 0)),
                                  int(args.get("close", 1440)))
        res["company"] = cid
        return res
    if op == "decorate":
        shop = str(args.get("shop", "") or (comp.shops[0] if comp.shops else ""))
        item = str(args.get("item_type", ""))
        public = bool(args.get("public", False))   # 家具权限: True=公共
        res = api.decorate(world, comp, shop, item, public=public)
        res["company"] = cid
        return res
    return {"ok": False, "why": "未知操作 %s" % op, "company": cid}


def set_price(world, entity_id: str, price) -> dict:
    """改一个在售实体的售价。**只改真值** —— 顾客要看见/听人才知道。

    这就是这个游戏的核心机制的手动版: 你降价了, 但只有【看见过或听说过】
    的人知道; 隔壁那条街的人记得的还是旧价(设计决定 #8)。
    """
    ent = world.entities.get(str(entity_id))
    if ent is None:
        return {"ok": False, "why": "没有这个物件", "data": None}
    ent.price = max(0.0, float(price))
    world.layout_location(ent.location_id)
    return {"ok": True, "why": None,
            "data": {"entity": ent.entity_id, "price": ent.price}}


def hire_now(world, systems, cfg) -> dict:
    """立刻跑一次招聘撮合(不等每天 hire_minute 那一次)。

    只是【把媒婆提前叫来】—— 招不招人仍然是公司说了算(要发布过启事)。
    """
    return {"ok": True, "why": None,
            "data": {"hired": api.hire_at(world, systems, cfg)}}
