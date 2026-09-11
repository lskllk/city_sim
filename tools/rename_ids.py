"""一次性改名迁移: 按 docs/naming.md 统一 id。

规则:
- 实例(loc/ent/npc)带前缀; 类型(item/building)不带全局前缀, 用 category_variant。
- ent id = ent_<itemtype>_<locslug>(不带 loc_ 前缀)。

跑一次即可: python tools/rename_ids.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "config" / "items"
BLDS = ROOT / "config" / "buildings"
SCENE = ROOT / "config" / "scenes" / "elm_lane.json"

ITEM_MAP = {           # 旧 item_type -> 新 item_type
    "apple": "food_apple",
    "pear": "food_pear",
    "water_dispenser": "drink_dispenser",
    "toilet": "toilet_basic",
    "tv": "media_tv",
    "bench": "seat_bench",
    "mahjong": "game_mahjong",
    "work_bench": "station_workbench",
    "_delete": "grocery",
}
BLD_MAP = {
    "home": "home_standard",
    "supermarket": "shop_supermarket",
    "shop": "shop_small",
    "plaza": "public_plaza",
    "office": "work_office",
    "school": "school_basic",
    "clinic": "clinic_basic",
}
LOC_MAP = {
    "apt_101": "loc_apt101", "apt_102": "loc_apt102",
    "plaza": "loc_plaza", "market": "loc_market", "site": "loc_site",
}
NPC_MAP = {"npc_wang": "npc_wang_er", "npc_li": "npc_li_si"}


def _ent(t: str, loc: str) -> str:
    return f"ent_{t}_{loc[len('loc_'):] if loc.startswith('loc_') else loc}"


ENT_MAP = {
    "bed_wang": _ent("bed_basic", "loc_apt101"),
    "food_wang": _ent("meal_simple", "loc_apt101"),
    "tv_wang": _ent("media_tv", "loc_apt101"),
    "wc_101": _ent("toilet_basic", "loc_apt101"),
    "water_101": _ent("drink_dispenser", "loc_apt101"),
    "bed_li": _ent("bed_basic", "loc_apt102"),
    "food_li": _ent("meal_simple", "loc_apt102"),
    "wc_102": _ent("toilet_basic", "loc_apt102"),
    "water_102": _ent("drink_dispenser", "loc_apt102"),
    "bench_1": _ent("seat_bench", "loc_plaza"),
    "meal_market": _ent("meal_simple", "loc_market"),
    "tv_market": _ent("media_tv", "loc_market"),
    "site_1": _ent("station_workbench", "loc_site"),
}


def _sub(value: str, mapping: dict, default: str) -> str:
    return mapping.get(value, default if value not in mapping else value)


def rename_items() -> None:
    for p in list(ITEMS.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        t = d.get("item_type")
        if t in ITEM_MAP.values() or t not in ITEM_MAP:
            continue
        new = ITEM_MAP[t]
        d["item_type"] = new
        for grp in ("on_start", "on_complete"):
            for eff in d.get(grp, []) or []:
                if isinstance(eff, dict) and eff.get("item_type") in ITEM_MAP:
                    eff["item_type"] = ITEM_MAP[eff["item_type"]]
        p.unlink()
        (ITEMS / f"{new}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    g = ITEMS / "grocery.json"
    if g.exists():
        g.unlink()


def rename_buildings() -> None:
    for p in list(BLDS.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        t = d.get("type")
        if t in BLD_MAP.values() or t not in BLD_MAP:
            continue
        new = BLD_MAP[t]
        d["type"] = new
        p.unlink()
        (BLDS / f"{new}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rename_scene() -> None:
    d = json.loads(SCENE.read_text(encoding="utf-8"))

    d["locations"] = {LOC_MAP.get(k, k): v for k, v in d["locations"].items()}
    for v in d["locations"].values():
        if v.get("type") in BLD_MAP:
            v["type"] = BLD_MAP[v["type"]]

    pairs = d.get("travel", {}).get("pairs", {})
    d["travel"]["pairs"] = {
        "|".join(LOC_MAP.get(x, x) for x in k.split("|")): n
        for k, n in pairs.items()}

    for e in d.get("entities", []):
        e["id"] = ENT_MAP.get(e["id"], e["id"])
        if e.get("type") in ITEM_MAP:
            e["type"] = ITEM_MAP[e["type"]]
        e["at"] = LOC_MAP.get(e["at"], e["at"])
        if "owner" in e:
            e["owner"] = NPC_MAP.get(e["owner"], e["owner"])

    for npc in d.get("npcs", []):
        npc["id"] = NPC_MAP.get(npc["id"], npc["id"])
        npc["home"] = LOC_MAP.get(npc.get("home", ""), npc.get("home", ""))
        mem = npc.get("memory", {})
        new_mem = {}
        for k, rec in mem.items():
            rec = dict(rec)
            if "located" in rec:
                rec["located"] = LOC_MAP.get(rec["located"], rec["located"])
            new_mem[ENT_MAP.get(k, k)] = rec
        if new_mem:
            npc["memory"] = new_mem

    plans = d.get("plans", {})
    d["plans"] = {}
    for npc_id, items in plans.items():
        out = []
        for it in items:
            it = dict(it)
            if "target" in it:
                it["target"] = ENT_MAP.get(it["target"], it["target"])
            if "dest" in it:
                it["dest"] = LOC_MAP.get(it["dest"], it["dest"])
            out.append(it)
        d["plans"][NPC_MAP.get(npc_id, npc_id)] = out

    SCENE.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")


if __name__ == "__main__":
    rename_items()
    rename_buildings()
    rename_scene()
    print("renamed. items:", sorted(p.stem for p in ITEMS.glob("*.json")))
    print("buildings:", sorted(p.stem for p in BLDS.glob("*.json")))
