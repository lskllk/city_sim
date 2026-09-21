"""commands —— **玩家说的话**: WS 指令 → 动作 → reply。

这一层是"玩家能干什么"的清单。加一个玩家动词 = 在 `handle_cmd` 里加一个
分支(经营类动词则只在 `_COMPANY_OPS` 加一行)。别的文件都不用动。

两类指令, 分得很清楚:

    **会话类**(set_speed / step / reset / query / select / ping)
        只是告诉 runner 怎么推进、在看谁。不改世界。

    **经营类**(_COMPANY_OPS + hire_now + set_price)
        真的改世界 —— 全部委派给 `actions.py`, 这里只负责
        ① 调它 ② 成功就叫 `note_world_changed()`(暂停时也要把新状态推出去)
        ③ 把结果包成 reply

铁律: **未知指令也要回一句 why**, 不许静默忽略 —— 否则前端点了没反应,
分不清是自己拼错了还是后端进程没重启(实测踩过)。
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from citysim import api
from citysim.game.actions import admin_company, hire_now, set_price
from citysim.game.clock import SPEED_TPS

if TYPE_CHECKING:                       # 只为类型标注, 不在运行期依赖
    from fastapi import WebSocket

    from citysim.game.runner import SimRunner


async def send(ws: "WebSocket", payload: dict) -> None:
    """统一出口: 全部 WS 消息都走 envelope(kind/protocol_version/payload)。

    注意它 **pop 掉 payload["kind"]** 当作消息类型 —— 所以传进来的 dict
    会被就地改掉(与历史行为一致)。
    """
    await ws.send_text(json.dumps(api.envelope(payload.pop("kind", "message"),
                                               payload), ensure_ascii=False))


async def _reply(ws: "WebSocket", rid, res: dict, *, data) -> None:
    """把一次动作的结果包成 reply 发出去。

    `data` 显式传: 经营动作回整个 res(含 companies 列表), 而 set_price /
    hire_now 只回自己的 data —— 历史形状就是这样, 前端按它解析。
    """
    await send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                    "ok": res["ok"], "data": data, "why": res["why"]})


# 经营动作: WS 指令名 → actions.admin_company 的 op。
# 表驱动是故意的 —— 指令与动作一一对应, 加一个经营动词只改这一行。
_COMPANY_OPS = {
    "register_company": "register",
    "company_update": "update",
    "company_hire": "hire",
    "company_restock": "restock",
    "company_decorate": "decorate",
    "company_assign": "assign",
    "company_wage": "wage",
    "company_schedule": "schedule",
}


async def handle_cmd(r: "SimRunner", ws: "WebSocket", cmd: dict) -> None:
    name, args, rid = cmd.get("name"), cmd.get("args", {}), cmd.get("req_id")
    if name == "set_speed" and args.get("speed") in SPEED_TPS:
        r.speed = args["speed"]
    elif name == "step":
        r.advance(max(1, min(int(args.get("ticks", 1)), 5000)))
        await r.push()
    elif name == "reset":
        r.params.update({k: v for k, v in args.items() if k in r.params})
        r.speed = "pause"
        r._build()
        await send(ws, {"kind": "hello", **api.hello_payload(r)})
        await r.push()
    elif name == "query":
        # 台词要渲染好再给 Inspector(god 面板看的是人话, 不是事件)
        data = api.do_query(r, args, getattr(r, "render_line", None))
        await send(ws, {"kind": "reply",
                        "type": "reply", "req_id": rid,
                        "ok": data is not None,
                        "data": data,
                        "why": None if data is not None else "not found"})
    elif name in _COMPANY_OPS:
        # 经营动作(注册公司 / 改参数 / 进人 / 进薪 / 排班 / 进货 / 装修 …)
        res = admin_company(r.world, r.systems, r.cfg,
                            _COMPANY_OPS[name], args)
        if res["ok"]:
            r.note_world_changed()   # 暂停时也要把新公司/新价格推给前端
        await _reply(ws, rid, res, data=res)
    elif name == "hire_now":
        res = hire_now(r.world, r.systems, r.cfg)
        r.note_world_changed()       # 新员工/公司名额变了 → 暂停时也要推
        await _reply(ws, rid, res, data=res["data"])
    elif name == "set_price":
        # 价格管理: 改一个在售实体的售价 —— 【只改真值】, 顾客要看见/听人才知道
        res = set_price(r.world, str(args.get("entity", "")),
                        args.get("price", 0.0))
        if res["ok"]:
            r.note_world_changed()   # 暂停时也要把新价格推给前端
        await _reply(ws, rid, res, data=res["data"])
    elif name == "select":
        # 观察驱动: 客户端告知“我在看谁 / 看哪栋楼” → 这些每帧全量下发。
        r.focus_npc = str(args.get("npc", ""))
        r.focus_loc = str(args.get("location", ""))
    elif name == "ping":
        await send(ws, {"kind": "pong", "type": "pong", "req_id": rid})
    else:
        # 以前是"静默忽略" → 前端点了没反应, 也不知道是自己发错了还是后端太旧。
        # 现在回一句, 前端会把 why 显示出来(最常见的两种: 后端进程没重启 / 名字拼错)。
        await send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                        "ok": False, "data": None,
                        "why": "未知指令 %s（后端是否需要重启?）" % name})
