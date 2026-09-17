"""npc/person/speech —— 说话: 气泡 / 语义草稿 / 惊讶检测

攒「值得说的事」按优先级取; 措辞本身交给 npc/semantic。

我拥有的字段: _bubble, _said_at, _say_queue
我只读的字段: _mem, _name_of
"""
from __future__ import annotations

from citysim.core.types import intent_target
from citysim.npc import semantic


class SpeechMixin:
    """见文件头(它拥有哪些字段)。"""


    def _push_speech(self, ev) -> None:
        self._say_queue.append(ev)
        if len(self._say_queue) > 12:        # 只留最近的一小把
            self._say_queue = self._say_queue[-12:]


    def _queue_intent_speech(self, tick: int, intent) -> None:
        """打算干什么 → 一条 INTENT(只在真的开始新动作时排一次)。"""
        tid = intent_target(intent)
        row = self._mem.get(tid) if tid else None
        if row is None:
            return
        words = semantic.GOAL_WORDS.get(row.afford)
        if words is None:
            return
        # 措辞必须跟【真实驱动】一致: 不饿却去补货时说“家里快没吃的了”,
        # 不许说“有点饿”。driver 由 brain 标注(见 _gather_candidates)。
        goal = words[0]
        trace = getattr(intent, "trace", None)
        feats = getattr(trace, "features", None) or {}
        why = words[2] if feats.get("driver") == "future" else words[1]
        self._push_speech(semantic.intent(
            tick, self.person_id, goal, why,
            topic=f"intent.{row.afford}"))


    def pending_speech(self, now_tick: int, cooldown: int = 600):
        """取一件【值得说】的事(优先级最高 + 不在话题冷却里); 没有则 None。

        优先级: DOUBT > SURPRISE > INTENT > STATE。说完记冷却 ——
        NPC 不会短时间复读自己(上下文决定论 C 的 said_recently)。
        """
        best, best_rank, best_i = None, -1, -1
        for i, ev in enumerate(self._say_queue):
            if now_tick - self._said_at.get(ev.topic, -(10 ** 9)) < cooldown:
                continue                       # 这个话题刚说过
            r = semantic.PRIORITY.get(ev.act, 0)
            if r > best_rank:
                best, best_rank, best_i = ev, r, i
        if best is None:
            # 剩下的都说过/过时了 → 丢掉太旧的, 别让它堆着
            self._say_queue = [e for e in self._say_queue
                               if now_tick - e.tick < cooldown]
            return None
        self._say_queue.pop(best_i)
        self._said_at[best.topic] = now_tick
        return best


    def said_at(self, topic: str, default: int = -(10 ** 9)) -> int:
        """这个话题上次是什么时候说的(默认很久以前)。"""
        return self._said_at.get(topic, default)


    def mark_said(self, topic: str, now_tick: int) -> None:
        self._said_at[topic] = int(now_tick)


    # --- 气泡(显示态) --------------------------------------------------
    def set_bubble(self, text: str, until_tick: int, kind: str) -> None:
        """头顶冒一句话(瞬时事件, 不是“当前在做什么”的状态)。

        渲染层只负责画和到点消失; 台词由后端从真实内部状态长出(铁律)。
        """
        self._bubble = (str(text), int(until_tick), str(kind))


    @property
    def bubble(self) -> tuple[str, int, str] | None:
        return self._bubble


    def _spot_surprises(self, percept, tick: int) -> list:
        """【预期 vs 观察】—— 语义层最值钱的两个 act 就长在这儿。

        · 现场与记忆不符 → SURPRISE(单纯意外)
        · 不符的那条记忆本来是【别人说的】→ DOUBT(信念被推翻; 优先级更高)
        第一次见到的东西没有“预期”, 谈不上落差, 不说。
        """
        out = []
        for v in percept.visible:
            row = self._mem.get(v.entity_id)
            if row is None:
                continue
            fact = {"item_id": v.entity_id, "located": v.location_id,
                    "afford": row.afford, "value": row.value,
                    "price": float(v.price), "item_type": v.item_type,
                    "stock": int(v.stock),
                    # 这是【刚亲眼看到】的事实 → 我自己信满(不是旧记忆里那个分)
                    "believe": 1.0, "source": ""}
            if abs(float(v.price) - float(row.price)) > 0.005:
                was = semantic.money_word(row.price)
                now = semantic.money_word(v.price)
                who = row.source
                if who and who != self.person_id and not who.startswith("ad:"):
                    name = ""
                    if self._name_of is not None:
                        name = str(self._name_of(who) or "")
                    if name:
                        out.append(semantic.doubt(
                            tick, self.person_id, v.entity_id, v.name, name,
                            was, now, fact=fact, source=who))
                        continue
                out.append(semantic.surprise(
                    tick, self.person_id, v.entity_id, v.name,
                    was, now, fact=fact))
            elif int(row.stock) > 0 and int(v.stock) == 0:
                out.append(semantic.surprise(
                    tick, self.person_id, v.entity_id, v.name,
                    "还有货", "卖光了", fact=dict(fact, stock=0)))
        return out
