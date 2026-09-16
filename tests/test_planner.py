"""TASK006: planner 接口骨架 + 规则模板降级 + 缓存/校验 单测。"""
from __future__ import annotations

import json

from citysim.npc.person import Identity, Person
from citysim.npc.planner import (KnownItem, Planner, PlannerInput, build_input,
                                 entries_from_spec, parse_clock, template_plan)

HOME_FOOD = KnownItem("food", "home", "hunger", 0.5)
HOME_BED = KnownItem("bed", "home", "energy", 0.7)


def _inp(known=(), home="home", **kw) -> PlannerInput:
    return PlannerInput(person_id="p", home=home, day_start_tick=0,
                        known=tuple(known), **kw)


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def plan(self, prompt: str) -> str:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return json.dumps(self.payload)


# --- 规则模板 ---------------------------------------------------------
def test_template_only_emits_commitments() -> None:
    """2026-09-14: 模板【删掉了三餐+睡觉】—— 那是需求, 归 utility。

    计划表只留【有事在等人】的承诺(上班/上学)。roles.json 还没做 →
    没有工作锚点 → 模板返回空(纯 utility 驱动)。
    """
    entries = template_plan(_inp(known=[HOME_FOOD, HOME_BED]))
    assert entries == []


def test_template_empty_when_no_known() -> None:
    assert template_plan(_inp(known=[])) == []


def test_template_prefers_home_location() -> None:
    away = KnownItem("food2", "market", "hunger", 0.9)
    entries = template_plan(_inp(known=[away, HOME_FOOD]))
    assert all(e.intent.target_id == "food" for e in entries)


# --- LLM spec 校验 ----------------------------------------------------
def test_entries_from_spec_valid() -> None:
    inp = _inp(known=[HOME_FOOD])
    spec = [{"id": "a", "at_minute": 480, "intent": "interact",
             "target": "food"},
            {"id": "b", "at_minute": 60, "intent": "move_to", "dest": "home"}]
    out = entries_from_spec(spec, inp)
    assert [e.at_tick for e in out] == [60, 480]        # 按时间排序
    assert out[1].intent.target_id == "food"


def test_entries_from_spec_accepts_clock_time() -> None:
    assert parse_clock("08:00") == 480
    assert parse_clock("23:59") == 1439
    assert parse_clock("24:00") is None
    assert parse_clock("nope") is None
    inp = _inp(known=[HOME_FOOD])
    out = entries_from_spec(
        [{"at": "08:00", "intent": "interact", "target": "food"}], inp)
    assert out[0].at_tick == 480
    # 非法时间 → 丢弃
    assert entries_from_spec(
        [{"at": "25:00", "intent": "interact", "target": "food"}], inp) == []


def test_entries_from_spec_buy() -> None:
    inp = _inp(known=[HOME_FOOD])
    out = entries_from_spec(
        [{"at": "12:00", "intent": "buy", "target": "food", "qty": 3}],
        inp)
    assert out[0].at_tick == 720
    assert out[0].intent.qty == 3


def test_entries_from_spec_rejects_unknown_target() -> None:
    inp = _inp(known=[HOME_FOOD])
    assert entries_from_spec(
        [{"at_minute": 1, "intent": "interact", "target": "ghost"}], inp) == []
    assert entries_from_spec(
        [{"at_minute": 1, "intent": "move_to", "dest": "nowhere"}], inp) == []
    assert entries_from_spec([{"at_minute": 9999, "intent": "interact",
                               "target": "food"}], inp) == []
    assert entries_from_spec("not a list", inp) == []


# --- Planner ----------------------------------------------------------
def test_llm_path_and_cache() -> None:
    client = _Client([{"id": "a", "at_minute": 480,
                       "intent": "interact", "target": "food"}])
    pl = Planner(client=client)
    inp = _inp(known=[HOME_FOOD])
    r1 = pl.plan_day(inp)
    r2 = pl.plan_day(inp)
    assert r1.source == "llm" and r1.entries[0].intent.target_id == "food"
    assert r2.source == "llm"
    assert client.calls == 1                     # 同输入命中缓存


def test_llm_failure_falls_back_to_template() -> None:
    pl = Planner(client=_Client(RuntimeError("boom")))
    res = pl.plan_day(_inp(known=[HOME_FOOD]))
    assert res.source == "template"             # 降级到模板(现在是空计划)


def test_no_client_uses_template() -> None:
    res = Planner().plan_day(_inp(known=[HOME_FOOD]))
    assert res.source == "template"


# --- build_input from Person -----------------------------------------
def test_build_input_reads_person() -> None:
    p = Person(identity=Identity("p", "p"), home="home")
    p.note("food", located="home", afford="hunger", value=0.5, believe=1.0)
    inp = build_input(p, 1440)
    assert inp.person_id == "p" and inp.home == "home"
    assert inp.day_start_tick == 1440
    assert any(k.item_id == "food" and k.located == "home"
               for k in inp.known)


def test_plan_for_person() -> None:
    p = Person(identity=Identity("p", "p"), home="home")
    p.note("bed", located="home", afford="energy", value=0.7, believe=1.0)
    res = Planner().plan_for_person(p, 1440)
    assert res.source == "template"
    assert all(e.at_tick >= 1440 for e in res.entries)
