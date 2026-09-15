"""world/companies —— 公司: 店铺属于它、钱进它的账、工资从它出。

为什么需要这一层(用户拍板: "经济做成公司的单位"):
    NPC 花出去的钱以前**凭空消失** —— 城里只有支出没有收入, 于是所有人慢慢破产饿死。
    现在成交时把钱记到【店铺所属公司】的账上, 公司每天给店员发工资 → 钱开始循环。

数据在 config/companies.json(与场景分离: 场景是地图, 公司是经营关系)。
id 规则见 docs/naming.md: org_<kind>_<slug>。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Company:
    """一个经营单位。cash 是它的账; shops 是旗下店铺(建筑 id); staff 是雇员+日薪。"""
    company_id: str
    name: str = ""
    cash: float = 0.0
    owner: str = ""                       # 老板 npc(以后玩家化身就是他)
    shops: tuple[str, ...] = ()
    staff: tuple[tuple[str, float], ...] = ()   # ((npc_id, 日薪), ...)

    def display(self) -> str:
        return self.name or self.company_id


def load_companies(path: str | Path) -> dict[str, Company]:
    """读 config/companies.json。文件不存在 → 空表(没有公司, 世界照常跑)。"""
    p = Path(path)
    if not p.is_file():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = raw.get("companies", raw) if isinstance(raw, dict) else raw
    out: dict[str, Company] = {}
    for rec in items or []:
        if not isinstance(rec, dict):
            continue
        cid = str(rec.get("id", ""))
        if not cid:
            continue
        staff = []
        for s in rec.get("staff") or []:
            if isinstance(s, dict) and str(s.get("npc", "")):
                staff.append((str(s["npc"]), float(s.get("wage", 0.0))))
            elif isinstance(s, str):
                staff.append((s, 0.0))
        out[cid] = Company(
            company_id=cid,
            name=str(rec.get("name", "")),
            cash=float(rec.get("cash", 0.0)),
            owner=str(rec.get("owner", "")),
            shops=tuple(str(x) for x in (rec.get("shops") or [])),
            staff=tuple(staff),
        )
    return out
