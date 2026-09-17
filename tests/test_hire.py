"""招聘 = 媒婆：**公司发布了启事** 且 **NPC 有意愿** 才撮合。

用户定的规矩(纠正了"有空位就自动招人"):
  · 招不招人是公司说了算 —— 没发布招聘启事, 一个人也不会被招进来
  · 启事上写着这次招几个、时薪多少(时薪在招聘时确定, 之后按在岗小时结算)
  · NPC 有意愿才可能被匹配(没角色 = 意愿 1.0; 已有工作 = 0)
  · 媒婆只撮合, 名额/时薪都由公司给
  · 招到: 写角色 + 绑定销售台 + 记进员工(守台由班次闸门驱动; 计划表从 work 派生)
"""
from __future__ import annotations

import json

from citysim.core.config import load_config
from citysim.gateway.scenarios import load_scene
from citysim.world.run import engine as E
from citysim.world.econ.company import assign_station, hire_at, schedule_worker

CFG = load_config("config/sim.toml")


def _scene(n_npc: int = 3) -> dict:
    return {
        "scene": "t", "display_name": "招聘", "canvas": {"w": 400, "h": 300},
        "locations": {
            "shop": {"type": "shop_small", "name": "店", "x": 100, "y": 100,
                     "w": 40, "h": 40},
            "home": {"type": "home_small", "name": "家", "x": 200, "y": 100,
                     "w": 40, "h": 40},
        },
        "entities": [],
        "npcs": [{"id": "npc_%d" % i, "name": "人%d" % i, "home": "home",
                  "money": 100, "init": {}} for i in range(n_npc)],
        "travel": {"default": 20, "pairs": {}},
    }


def _load(tmp_path, data, counters: int = 2, hiring_slots: int = 0, wage=60.0):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    w, s, r = load_scene(p)
    from citysim.world.model.companies import Company
    comp = Company("org_a", "甲店", cash=5000.0, shops=("shop",),
                   open_minute=480, close_minute=1140, wage_per_hour=wage,
                   hiring_open=hiring_slots > 0, hiring_slots=hiring_slots)
    w.companies = {"org_a": comp}
    w.locations["shop"]["company"] = "org_a"
    from helpers import add_counter
    if counters:
        add_counter(w, "shop", counters)
    return w, s


def _run_to_hire(w, s):
    """跑到 hire_minute(0 点) 之后再几 tick。"""
    for _ in range(5):
        E.tick(w, s, CFG)


def test_no_notice_no_hire(tmp_path) -> None:
    """★ 没发布招聘启事 → 有空工位、有人愿意, 也一个人都不招。"""
    w, s = _load(tmp_path, _scene(), counters=2, hiring_slots=0)
    _run_to_hire(w, s)
    assert hire_at(w, s, CFG) == []
    assert w.companies["org_a"].staff == ()
    assert all(not p.work for p in w.npcs.values())


def test_notice_hires_only_the_posted_number(tmp_path) -> None:
    """发布了招 2 个 → 只招 2 个(哪怕有 3 个人愿意); 招满自动撤启事。"""
    w, s = _load(tmp_path, _scene(3), counters=2, hiring_slots=2)
    hired = hire_at(w, s, CFG)
    assert len(hired) == 2, hired
    assert len(w.companies["org_a"].staff) == 2
    assert not w.companies["org_a"].hiring_open        # 招满撤下


def test_hired_npc_gets_role_work_and_daily_plan(tmp_path) -> None:
    """被招到的人: 角色 + 工位绑定 + 计划时间线上能看到上班块(从 work 派生)。"""
    w, s = _load(tmp_path, _scene(1), counters=1, hiring_slots=1)
    hired = hire_at(w, s, CFG)
    assert len(hired) == 1
    npc = w.npcs[hired[0]["npc"]]
    assert npc.role == "worker"
    assert npc.work["company"] == "org_a"
    assert npc.work["shop"] == "shop"
    assert npc.work["station"] == hired[0]["station"]
    plan = npc.plan_snapshot()
    # 上班块(去/守台) + 下班块
    assert len(plan) == 3, plan
    assert [e["id"] for e in plan] == ["work_go", "work_stand", "work_off"], plan
    assert all(e["intent"] in ("move_to", "interact") for e in plan)
    assert plan[0]["at_tick"] % 1440 == 480 and plan[2]["at_tick"] % 1440 == 1140
    # 时薪在招聘时确定 = 公司启事上的时薪
    assert w.companies["org_a"].staff[0][1] == 60.0


def test_already_employed_are_not_rehired(tmp_path) -> None:
    """已经有工作/角色的人意愿 = 0 → 不参与撮合。"""
    w, s = _load(tmp_path, _scene(1), counters=2, hiring_slots=2)
    first = hire_at(w, s, CFG)
    assert len(first) == 1                             # 只有 1 个人愿意
    w.companies["org_a"].hiring_open = True
    w.companies["org_a"].hiring_slots = 1
    assert hire_at(w, s, CFG) == []                  # 剩下的都已有工作


def test_economy_block_exposes_staff_with_wage(tmp_path) -> None:
    """观测块 economy.companies.staff 带时薪 —— HR 面板直接读它显示员工名单。

    (契约: [{npc, wage}], 和 hello.companies 一致; 以前 economy 只给 npc id。)
    """
    from citysim.gateway.snapshot import economy_block
    w, s = _load(tmp_path, _scene(1), counters=1, hiring_slots=1, wage=60.0)
    hire_at(w, s, CFG)
    comp = economy_block(w, s)["companies"][0]
    assert comp["staff"] and comp["staff"][0]["wage"] == 60.0
    assert comp["staff"][0]["npc"]


def test_assign_station_reassigns_and_guards_taken(tmp_path) -> None:
    """分配工位: 可改到别的台; 台被占 / 非员工 → 拒绝; 空串 = 撤销分配。"""
    w, s = _load(tmp_path, _scene(2), counters=2, hiring_slots=2)
    hired = hire_at(w, s, CFG)
    a, b = hired[0]["npc"], hired[1]["npc"]
    ca, cb = hired[0]["station"], hired[1]["station"]
    comp = w.companies["org_a"]
    # 想把 b 的台给 a → b 还占着 → 拒绝
    assert not assign_station(w, s, CFG, comp, a, cb)["ok"]
    # 撤销 b → 台空出来
    assert assign_station(w, s, CFG, comp, b, "")["ok"]
    assert w.npcs[b].work.get("station", "") == ""
    # 现在 b 能回到那个台
    res = assign_station(w, s, CFG, comp, b, cb)
    assert res["ok"] and w.npcs[b].work["station"] == cb
    # 非员工拒绝
    assert not assign_station(w, s, CFG, comp, "nobody", ca)["ok"]


def test_schedule_worker_sets_personal_shift(tmp_path) -> None:
    """排班: 只改本人 _work.open/close, 立即影响 _on_shift(不影响公司营业时间)。"""
    w, s = _load(tmp_path, _scene(1), counters=1, hiring_slots=1)
    hire_at(w, s, CFG)
    npc = w.npcs[next(iter(w.npcs))]
    comp = w.companies["org_a"]
    res = schedule_worker(w, s, CFG, comp, npc.person_id, 600, 900)
    assert res["ok"] and res["open"] == 600 and res["close"] == 900
    assert npc.work["open"] == 600 and npc.work["close"] == 900
    assert npc._on_shift(600, CFG) and not npc._on_shift(500, CFG)
    assert comp.open_minute == 480                    # 公司营业时间没动
