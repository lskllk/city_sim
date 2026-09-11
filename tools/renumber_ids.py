"""第二趟改名: 地点/实体改为 `<slug>_<NNN>` / `<itemtype>_<NNN>`(全局编号, 不带人名/地点)。

跑一次: python tools/renumber_ids.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "config" / "scenes" / "elm_lane.json"

LOC2 = {
    "loc_apt101": "apt_001",
    "loc_apt102": "apt_002",
    "loc_market": "market_001",
    "loc_plaza": "plaza_001",
    "loc_site": "site_001",
}
ENT2 = {
    "ent_bed_basic_apt101": "bed_basic_001",
    "ent_meal_simple_apt101": "meal_simple_001",
    "ent_media_tv_apt101": "media_tv_001",
    "ent_toilet_basic_apt101": "toilet_basic_001",
    "ent_drink_dispenser_apt101": "drink_dispenser_001",
    "ent_bed_basic_apt102": "bed_basic_002",
    "ent_meal_simple_apt102": "meal_simple_002",
    "ent_toilet_basic_apt102": "toilet_basic_002",
    "ent_drink_dispenser_apt102": "drink_dispenser_002",
    "ent_seat_bench_plaza": "seat_bench_001",
    "ent_meal_simple_market": "meal_simple_003",
    "ent_media_tv_market": "media_tv_002",
    "ent_station_workbench_site": "station_workbench_001",
}


def L(v: str) -> str:
    return LOC2.get(v, v)


def E(v: str) -> str:
    return ENT2.get(v, v)


def main() -> None:
    d = json.loads(SCENE.read_text(encoding="utf-8"))

    d["locations"] = {L(k): v for k, v in d["locations"].items()}

    pairs = d.get("travel", {}).get("pairs", {})
    d["travel"]["pairs"] = {"|".join(L(x) for x in k.split("|")): n
                            for k, n in pairs.items()}

    for e in d.get("entities", []):
        e["id"] = E(e["id"])
        e["at"] = L(e["at"])

    for npc in d.get("npcs", []):
        npc["home"] = L(npc.get("home", ""))
        mem = npc.get("memory", {})
        npc["memory"] = {E(k): {**r, **({"located": L(r["located"])}
                                       if r.get("located") else {})}
                         for k, r in mem.items()}

    plans = d.get("plans", {})
    for npc_id, items in plans.items():
        for it in items:
            if "target" in it:
                it["target"] = E(it["target"])
            if "dest" in it:
                it["dest"] = L(it["dest"])

    SCENE.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    print("locations:", list(d["locations"]))
    print("entities:", [e["id"] for e in d["entities"]])


if __name__ == "__main__":
    main()
