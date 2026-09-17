"""npc/person/work —— 工作: 雇佣 / 班次 / 出勤 + 好感

绑定公司/店/工位/时薪; 在岗计时算工资; 还有对店铺的慢变量好感。

我拥有的字段: _favor, _goal, _role, _schedule, _work, _worked_ticks
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from citysim.core.types import Plan, Role, Shift, Unwork, Wage, Work
from citysim.npc.schedule import Schedule

if TYPE_CHECKING:  # pragma: no cover
    # 只出现在类型标注里(运行时用不到) —— 别让清 import 的脚本删掉
    from citysim.core.config import SimConfig
    from citysim.npc.schedule import PlanEntry
    from typing import Sequence


class WorkMixin:
    """见文件头(它拥有哪些字段)。"""


    def assign(self, cmd) -> None:
        """★ world → NPC 的【指令口】: 上面的人(老板/作者/计划器)说“照这个做”。

        和 notify 的分工:
          notify  世界说“发生了什么”         → NPC 自己决定怎么改自己;
          assign  上面的人说“你以后照这个做”   → NPC 照做。
        这两条是 world 能碰 NPC 的**全部**入口(以前是散装 setter: set_work /
        set_shift / set_wage / set_role / clear_work / set_plan 共 6 个)。
        """
        if isinstance(cmd, Work):
            # 班次/时薪存在身上(不去问世界), 因为决策层要自己算“离岗要亏多少”
            self._work = {"company": cmd.company_id, "shop": cmd.shop_id,
                          "station": cmd.station_id,
                          "open": int(cmd.open_minute),
                          "close": int(cmd.close_minute),
                          "wage": float(cmd.wage_per_hour)}
            if cmd.role:
                self._role = str(cmd.role)
        elif isinstance(cmd, Unwork):
            self._work = {}
        elif isinstance(cmd, Shift):
            if self._work:
                self._work["open"] = max(0, min(1439, int(cmd.open_minute)))
                self._work["close"] = max(1, min(1440, int(cmd.close_minute)))
        elif isinstance(cmd, Wage):
            if self._work:
                self._work["wage"] = max(0.0, float(cmd.wage_per_hour))
        elif isinstance(cmd, Role):
            self._role = str(cmd.role)
        elif isinstance(cmd, Plan):
            self._apply_plan(cmd.entries)
        else:                                # pragma: no cover - 开发期挡错
            raise TypeError(f"未声明的指令 {cmd!r}")


    def _apply_plan(self, entries: "Sequence[PlanEntry]") -> None:
        """灌入当天计划(LLM 产物)，覆盖旧计划。

        ★ 只作废【计划来源】的 goal —— 不能碰需求 goal(如睡到一半跨 0 点,
          日计划器调到这里, 若把 sleep goal 也清了 → 下一 tick 重算需求,
          饿了就把床顶掉 = “睡觉被饥饿中止”)。
        """
        self._schedule = Schedule(entries)
        if self._goal is not None and self._goal.source == "plan":
            self._goal = None


    # --- 工作绑定的只读视图(决策层/观察层要看, 但只能走 assign 改) -------
    @property
    def work(self) -> dict:
        return dict(self._work)


    @property
    def role(self) -> str:
        """角色: assign 写上的优先, 否则看人设里的 traits.role。"""
        return self._role or str(self.identity.traits.get("role", ""))


    def worked(self, ticks: int = 1) -> None:
        """在岗计时(工资按在岗时间算)。"""
        self._worked_ticks += max(0, int(ticks))


    def reset_worked(self) -> int:
        """取走并清零"这一期在岗的 tick 数"(发工资时用)。"""
        n = self._worked_ticks
        self._worked_ticks = 0
        return n


    def _on_shift(self, now_tick: int, cfg: "SimConfig") -> bool:
        """现在是我的班次吗? (有工作 且 在 open..close 之间)"""
        if not self._work:
            return False
        minute = now_tick % max(1, cfg.ticks_per_day)
        return int(self._work.get("open", 0)) <= minute < int(self._work.get("close", 1440))


    # --- 好感度(对店铺的慢变量) ----------------------------------------
    def favor_of(self, shop_id: str, neutral: float = 1.0) -> float:
        """对某家店的好感度; 没记过 = 中性。"""
        if not shop_id:
            return neutral
        return float(self._favor.get(shop_id, neutral))


    def bump_favor(self, shop_id: str, delta: float, cfg) -> float:
        """好感度加减(自动夹在 min..max)。返回新值。"""
        if not shop_id or delta == 0.0:
            return self.favor_of(shop_id, cfg.favor_neutral)
        v = self.favor_of(shop_id, cfg.favor_neutral) + float(delta)
        v = max(cfg.favor_min, min(cfg.favor_max, v))
        self._favor[shop_id] = v
        return v
