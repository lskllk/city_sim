"""world/model/companies —— 公司: 店铺属于它、钱进它的账、工资从它出。

为什么需要这一层(用户拍板: "经济做成公司的单位"):
    NPC 花出去的钱以前**凭空消失** —— 城里只有支出没有收入, 于是所有人慢慢破产饿死。
    现在成交时把钱记到【店铺所属公司】的账上, 公司每天给店员发工资 → 钱开始循环。

★ 公司是【游戏内注册】出来的(点建筑 → 注册公司), 没有配置文件 ——
  手写的公司表只会变成第二份真相, 而且编辑器/面板改不动它。

  注册流程(用户在游戏模式里做): 点一个商铺建筑 → 注册公司 →
  公司落到 world.companies + 那个建筑挂上 location["company"] →
  然后才谈得上装修(摆销售前台)、发布招聘、进货。

id 规则: org_<kind>_<slug>。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Company:
    """一个经营单位。cash 是它的账; shops 是旗下店铺(建筑 id); staff 是雇员+日薪。"""
    company_id: str
    name: str = ""
    cash: float = 0.0
    owner: str = ""                       # 老板 npc(以后玩家化身就是他)
    shops: tuple[str, ...] = ()
    staff: tuple[tuple[str, float], ...] = ()   # ((npc_id, 时薪), ...)
    # —— 营业(用户拍板: 编辑器可编) ——
    open_minute: int = 480          # 开门(游戏分钟)
    close_minute: int = 1140        # 关门
    wage_per_hour: float = 10.0     # 时薪: 招聘时确定(按小时算)
    # —— 公司类型(注册时定; 决定用哪套运营界面/接口) ——
    #   "retail"      零售: 向市场进货 → 上架 → 卖给居民
    #   "manufacture" 制造(加工厂): 工人站工位产出【原料】→ 只能卖给批发市场
    kind: str = "retail"
    produces_item: str = ""         # 制造: 产出哪种货(空 = 不产; 见 world/econ/factory)

    # —— 招聘启事(公司说了算; 外面架构只做媒婆) ——
    #   没发布 = 一个人也不会被招进来, 哪怕有工位、也有人愿意干。
    hiring_open: bool = False
    hiring_slots: int = 0           # 这次想招几个人(不能超过空着的销售前台)
    slots: int = 2                  # 销售位: 1 位 = 1 tick 成交 1 份, 需要 1 个店员
    restock_to: int = 60            # 开门前把货架补到几份(简单经营规则)





