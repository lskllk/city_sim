"""world/econ/company —— 公司经营: 工资/招聘/排班/分岗

工资按【在岗时间】发(出勤多少小时领多少; 没到岗=没收入, 不搞欠薪);
招聘 = 公司发启事 + 意愿撮合(架构只做媒婆, 名额/时薪都是公司给的);
分岗/排班只改世界真值, 守台由【班次闸门】驱动(Person 自己判)。
"""
from __future__ import annotations

from citysim.core.config import SimConfig
from citysim.core.types import Shift, Unwork, WagePaid, Work

from citysim.world.econ.shop import _counters



def pay_wages(world, cfg: SimConfig) -> None:
    """公司给店员发工资(每天一次, 由 tick 在 wage_minute 那一刻调)。

    钱从公司账上出 → 员工个人进账。**发不出就是发不出**(没有"欠薪"概念):
    公司现金不足 → 发事件 wage_failed, 那个人这天没收入(→ 会穷 → 会饿)。
    这是"惩罚 = 状态调制产出"的同一套: 不搞门禁, 让钱自己说话。
    """
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        for npc_id, wage in comp.staff:
            npc = world.npcs.get(npc_id)
            if npc is None:
                continue
            # ★ 一天结一次, 按【在岗时间】算: 出勤多少小时就领多少小时的钱。
            #   没到岗 = 没收入(不搞欠薪/扣款 —— 惩罚就是"少拿钱")。
            hours = npc.reset_worked() / 60.0
            due = round(hours * float(wage), 2)
            if due <= 0.0:
                continue                        # 一天没上班 → 不发也不记
            if comp.cash < due:
                world.bus.publish(world.bus.make(
                    world.clock_tick, "wage_failed", npc_id,
                    {"company": cid,
                     "wage": due, "hours": round(hours, 2),
                     "cash": round(comp.cash, 2)}))
                continue
            comp.cash -= due
            npc.notify(WagePaid(due))
            world.bus.publish(world.bus.make(
                world.clock_tick, "wage_paid", npc_id,
                {"company": cid, "wage": due,
                 "hours": round(hours, 2),
                 "cash": round(comp.cash, 2), "money": round(npc.money, 2)}))



def stations_of(world, company, shop_id: str) -> list:
    """这家公司在这个建筑里的【岗位】实体 —— 岗位长什么样由公司类型定:

      零售 → 销售前台(station_counter): 1 个岗 = 每 tick 成交 1 份
      制造 → 工位(station_workbench):   1 个岗 = 一份产出的进度槽
    两边的"谁站在岗上"是同一把闸门(见 tick_workstations), 所以工资/熟练度一致。
    """
    if company.kind == "manufacture":
        return [e for e in sorted(world.entities.values(), key=lambda x: x.entity_id)
                if (e.item_type == "station_workbench"
                    and e.location_id in company.shops)]
    return _counters(world, shop_id)


def vacant_counters(world, company) -> list:
    """公司旗下【空着的】岗位(没有任何员工绑定它)。= 还能招几个人。"""
    taken = {str(n) for n, _w in company.staff}
    out = []
    for shop_id in company.shops:
        for c in stations_of(world, company, shop_id):
            if not any(world.npcs.get(pid) is not None
                       and world.npcs[pid].work.get("station") == c.entity_id
                       for pid in taken):
                out.append((shop_id, c))
    return out



def _willing(world, pid: str) -> float:
    """应聘意愿: 没角色的都愿意(1.0); 已经有工作/角色的 = 0(不跳槽)。"""
    npc = world.npcs.get(pid)
    if npc is None:
        return 0.0
    if npc.work or npc.role:
        return 0.0
    return 1.0



def hire_at(world, systems, cfg: SimConfig) -> list[dict]:
    """每天一次的招聘桥接 —— 外面架构只是【媒婆】。

    ★ 用户定的规矩(这一版按它改):
      · **招不招人是公司说了算**: 只有【发布了招聘启事】的公司才参与撮合;
        有空工位 ≠ 要招人。启事上写着这次招几个、时薪多少。
      · **NPC 有意愿**才可能被匹配: 没角色的人意愿 = 1.0(已有工作的 = 0)。
      · 媒婆只做撮合: 名额、时薪都由公司给, 这边一个都不自己加。

    匹配规则先按【随机】(架构留好: 以后换成熟练度/距离/工资竞争力都在这一个
    函数里)。被招到: 写角色 + 绑定销售台 + 记进公司员工(守台由【班次闸门】驱动,
    不写进计划表 —— 见 Person.decide / plan_snapshot)。
    """
    hired: list[dict] = []
    rng = getattr(systems, "rng", None)
    if rng is None:
        return hired
    willing = [pid for pid in sorted(world.npcs) if _willing(world, pid) > 0.0]
    if not willing:
        return hired
    for cid in sorted(world.companies):
        comp = world.companies[cid]
        if not comp.hiring_open or comp.hiring_slots <= 0:
            continue                          # 没发布招聘 → 一个人也不招
        vac = vacant_counters(world, comp)
        if not vac:
            continue
        staff = list(comp.staff)
        quota = min(int(comp.hiring_slots), len(vac))
        got = 0
        for shop_id, counter in vac[:quota]:
            if not willing:
                break
            pick = willing.pop(rng.randrange(len(willing)))     # ← 随机匹配
            npc = world.npcs[pick]
            npc.assign(Work(cid, shop_id, counter.entity_id,
                            comp.open_minute, comp.close_minute,
                            comp.wage_per_hour))
            staff.append((pick, float(comp.wage_per_hour)))
            got += 1
            hired.append({"company": cid, "npc": pick, "shop": shop_id,
                          "station": counter.entity_id})
            world.bus.publish(world.bus.make(
                world.clock_tick, "hired", pick,
                {"company": cid, "shop": shop_id,
                 "station": counter.entity_id,
                 "wage_per_hour": float(comp.wage_per_hour)}))
        comp.staff = tuple(staff)
        comp.hiring_slots = max(0, int(comp.hiring_slots) - got)   # 招到几个扣几个
        if comp.hiring_slots <= 0 or not vacant_counters(world, comp):
            comp.hiring_open = False           # 招满 / 没空位 → 启事自动撤下
    return hired



def assign_station(world, systems, cfg: SimConfig, company,
                   npc_id: str, station_id: str) -> dict:
    """把员工【分派到】某个销售台(或 station_id="" 撤销分配)。

    用户要的: 招来的人得能手动指定站哪个台, 否则可能没位置(或分错台)。
    只改世界真值(work 绑定), 不做任何模拟计算(守台由班次闸门驱动)。
    返回 {"ok", "why", "npc", "station"(, "shop")}。
    """
    npc = world.npcs.get(npc_id)
    if npc is None:
        return {"ok": False, "why": "没有这个人", "npc": npc_id, "station": ""}
    if npc_id not in [n for n, _w in company.staff]:
        return {"ok": False, "why": "不是这家公司的员工",
                "npc": npc_id, "station": ""}
    if station_id == "":
        npc.assign(Unwork())
        return {"ok": True, "why": "", "npc": npc_id, "station": ""}
    shop_id = ""
    for sid in company.shops:
        for c in stations_of(world, company, sid):     # 零售=前台 / 制造=工位
            if c.entity_id == station_id:
                shop_id = sid
                break
        if shop_id:
            break
    if not shop_id:
        return {"ok": False, "why": "这个岗位不是公司的",
                "npc": npc_id, "station": ""}
    for other in world.npcs.values():
        if other.person_id == npc_id:
            continue
        if other.work.get("station") == station_id:
            return {"ok": False, "why": "这个台已经有别人在守",
                    "npc": npc_id, "station": ""}
    # ★ 时薪取【这个人自己的】(comp.staff 里那条), 不是公司的默认时薪 ——
    #   以前这里写 company.wage_per_hour, 于是"换个工位/重派一下"就把他被调过的
    #   逐人时薪冲掉了(面板上看到的就是"改薪之后自己变回去了")。
    wage = next((float(w) for n, w in company.staff if n == npc_id),
                float(company.wage_per_hour))
    npc.assign(Work(company.company_id, shop_id, station_id,
                     int(npc.work.get("open", company.open_minute)),
                     int(npc.work.get("close", company.close_minute)),
                     wage))
    return {"ok": True, "why": "", "npc": npc_id, "station": station_id,
            "shop": shop_id}



def schedule_worker(world, systems, cfg: SimConfig, company,
                    npc_id: str, open_minute: int, close_minute: int) -> dict:
    """给某员工【排班】(只改他自己的班次, 不动公司营业时间)。

    只改世界真值(_work.open/close); 守台仍由班次闸门驱动。
    返回 {"ok", "why", "npc", "open", "close"}。
    """
    npc = world.npcs.get(npc_id)
    if npc is None:
        return {"ok": False, "why": "没有这个人", "npc": npc_id}
    if npc_id not in [n for n, _w in company.staff]:
        return {"ok": False, "why": "不是这家公司的员工", "npc": npc_id}
    npc.assign(Shift(int(open_minute), int(close_minute)))
    return {"ok": True, "why": "", "npc": npc_id,
            "open": int(npc.work.get("open", 0)),
            "close": int(npc.work.get("close", 1440))}



def tick_workstations(world, systems, cfg: SimConfig) -> None:
    """在岗计时: 谁站在【他该站的工位】上, 这一 tick 就算上班。

    销售前台和生产工位走同一把闸门(都是"人站在 work["station"] 那件东西上"),
    所以工资/熟练度对两种岗位一致 —— 柜台服务只关心前台, 生产只关心工位。
    """
    for pid in sorted(systems.interaction.active):
        act = systems.interaction.active.get(pid)
        npc = world.npcs.get(pid)
        if act is None or npc is None:
            continue
        if str(npc.work.get("station", "")) != act.entity_id:
            continue                      # 站的不是自己该站的工位
        npc.worked(1)


def _hire_due(world, cfg: SimConfig, last_tick: int) -> bool:
    """到点了吗(每天 hire_minute 一次)。"""
    day, minute = divmod(world.clock_tick, max(1, cfg.ticks_per_day))
    if minute != int(cfg.hire_minute):
        return False
    return last_tick < day * cfg.ticks_per_day + cfg.hire_minute



def _wage_due(world, cfg: SimConfig, last_tick: int) -> bool:
    """挂工资那一刻: 恰好跨过当天的 wage_minute。用 tick 判, 不存状态。"""
    day, minute = divmod(world.clock_tick, max(1, cfg.ticks_per_day))
    if minute != int(cfg.wage_minute):
        return False
    # 同一 tick 只发一次(引擎每 tick 只调一次, 这里再兜一层: 当天未发过)
    return last_tick < day * cfg.ticks_per_day + cfg.wage_minute
