"""npc/brain/memory_io —— 记忆的写入与遗忘。

  perceive_into  感知 → 记忆: 现场为准, 整行覆盖, believe=1(亲眼所见最硬)
                 返回【本次的新奇量】= Σ(1 − 旧 remember) —— 闲逛靠它结算 fun
  forget         按【调用节奏】做一步半衰衰减, 低于阈值删行
"""
from __future__ import annotations

from citysim.core.types import Percept
from citysim.npc.memory import MemBase, MemItem

FORGET_DEFAULT = 0.1  # remember 低于此 → 遗忘删除(默认阈值)


def perceive_into(mem: MemBase, percept: Percept, tick: int,
                  only_affords: "set[str] | None" = None) -> float:
    """感知 → 记忆(写入): 按【为什么看】把看到的东西写进记忆。非纯函数。

    ★ 为什么要挑: 如果“看一眼”就把整个地点刷成新鲜, 那“看过一次”等于“永远知道”
      —— 用得上和没人碰的东西一视同仁, 知识永远不会旧。所以：
        探索(第一次来 / 闲逛) → 现场为准整行覆盖: 去过的地方知识保持新鲜
                                (这就是“闲逛 = 不断刷新 view”);
        找东西(缺某项需求才看) → 只记能解它的, 且已有的行不动(不算探索);
        用过了                → 只刷那一条(notify 里的反证, 不在本函数);
        不看的                → 自然变旧、被忘。
      盯着的代价是 stock 会过时 —— 那正好是“去了才发现没了”(InteractionFailed)
      这条修正路径存在的理由。
      但【听来的/广告】不算“已经知道”: 亲眼确认时整行覆盖(见下面的 row.source 分支)
      ——“听说便宜”到“亲眼看到”的提升就是 believe 的用法。

    现场发现的 → source=""(亲眼) 且 believe=1.0: 不管之前听谁说过, 亲眼所见最硬。

    ★ 写什么取决于【为什么看】:
      · only_affords=None(第一次来 / 闲逛 = 探索) → 全部记, 而且【现场为准整行覆盖】
        —— 这就是“闲逛 = 在建筑里不断刷新 view”: 去过的地方知识保持新鲜,
        不去的自然变旧被忘。
      · only_affords={...}(缺东西才看 = 找东西) → 只记能解这些需求的, 而且
        【已有的行不动】—— 找东西不算探索, 不刷已知的。
      两种情形的共同例外: 听来的/广告的行(row.source != "")遇到亲眼 → 总归覆盖。

    ★ `only_affords`: 只记【能解这些需求】的东西(其余连写都不写)。
      None = 探索(第一次来/闲逛): 全部记住并刷新现场。

    ★ 返回值 = 【本次的新奇量】= Σ(1 − 旧 remember)。
      它是"这些东西对我来说有多新"的度量 —— 第一次见 = 1.0/件。
      闲逛靠它结算 fun(见 Person 的闲逛收工), 也靠它更新"这地方值不值得再去"。
    """
    gain = 0.0
    for v in percept.visible:
        afford, value = (next(iter(v.affordances.items()), ("", 0.0)))
        if only_affords is not None and afford not in only_affords:
            continue                     # 为了找 X 才看的 → 不是 X 的不记
        row = mem.get(v.entity_id)
        if row is None:
            gain += 1.0
            mem.set(MemItem(
                item_id=v.entity_id, located=v.location_id,
                owner=v.owner, afford=afford, value=float(value),
                item_type=v.item_type, tags=tuple(sorted(v.tags)), source="",
                price=v.price, household=bool(v.household),
                free_use=bool(v.free_use), stock=int(v.stock),
                shelf_life_ticks=int(v.shelf_life_ticks),
                expires_tick=int(v.expires_tick),
                believe=1.0, remember=1.0, last_seen=tick))
        else:
            gain += max(0.0, 1.0 - float(row.remember))   # 只是“想起来”了
            if only_affords is None or row.source:
                # ① 探索(第一次来/闲逛): 现场为准, 整行覆盖 —— 知识保持新鲜。
                #    (这是“闲逛 = 不断刷新 view”; 不去的自然变旧被忘。)
                # ② 之前是【听来的/广告】: 亲眼确认最硬 —— believe 升到 1、source
                #    清成亲眼、补齐 owner/tags/…(听说的行情是不带 tags 的,
                #    不补就永远买不了/用不了)。
                # ③ 剩下那种(缺东西才看 + 已经是第一手)【不动】。
                mem.update(
                    v.entity_id, located=v.location_id, owner=v.owner,
                    afford=afford or row.afford,
                    value=float(value) if value else row.value,
                    item_type=v.item_type, tags=tuple(sorted(v.tags)), source="",
                    price=v.price, household=bool(v.household),
                    free_use=bool(v.free_use), stock=int(v.stock),
                    shelf_life_ticks=int(v.shelf_life_ticks),
                    expires_tick=int(v.expires_tick),
                    believe=1.0, remember=1.0, last_seen=tick)
    gain += _touch_place(mem, percept.location_id, tick)
    return gain


def place_id(loc: str) -> str:
    """地点记忆行的 id(和实体行共用一个库, 但 afford="" 不进决策候选)。"""
    return "loc:" + loc


def _touch_place(mem: MemBase, loc: str, tick: int) -> float:
    """写一行【地点记忆】("我逛过这里") —— 返回它这次的新奇量。

    为什么需要它:
      · 它是"我来过"的凭证 —— 闲逛选址靠它判断"**没去过**"(没去过才给乐观加成);
      · 它是"上次在这儿收获多少"的账(attrs["gain"]) —— 选址的第二项;
      · afford="" → **不进决策候选**(不会干扰吃饭睡觉);
      · 它自己也参与遗忘 → 忘了 = 重新变成"没去过" → 会再去看看。
    """
    pid = place_id(loc)
    row = mem.get(pid)
    if row is None:
        mem.set(MemItem(item_id=pid, located=loc, afford="",
                        tags=("place",), believe=1.0, remember=1.0,
                        last_seen=tick, attrs={"visits": 1, "gain": 0.0}))
        return 1.0
    gain = max(0.0, 1.0 - float(row.remember))
    mem.update(pid, remember=1.0, last_seen=tick)
    return gain


def forget(mem: MemBase, half_life_ticks: int, step_ticks: int = 1440,
           forget_threshold: float = FORGET_DEFAULT,
           keep_located: str = "") -> int:
    """遗忘策略: 按【调用的间隔】做一步半衰衰减, 低于阈值删行。

    返回值 = 本次被遗忘删除的 item 数。何时调用/半衰/阈值由上层定(如每游戏日)。

    ★ `keep_located`: 落在这个地点上的行【不衰减也不删除】—— 传"家"的 id。
      家 = 身份性的常识("我住那儿, 那儿有什么"), 不该随时间淡掉 —— 否则
      "忘了自家的床 → 困了也想不到回家"会变成死锁(而且越不回越没记忆)。
      别处的知识照常变旧/被忘: 常用的靠"用过就刷"(notify 的反证)维持,
      没人碰的就忘掉 —— 想不起来时再由"此地缺东西就先看一眼"当场补看。


    ★ 为什么是"一步"而不是"按距上次观察的 dt":
      本函数由上层【按固定节奏】调(现在 = 每个游戏日 0:00)。早先的实现用
      `remember × 0.5^(dt/half_life)`, 而 dt 是"距上次观察的全量时间"、remember
      是【已经衰减过的值】→ 同一段时间被算了两遍, 衰减比名义快:
      半衰 2 天 / 阈值 0.1 时, **4 天就删行**(本该 ~6.6 天)。
      现在按步长: `remember × 0.5^(step_ticks / half_life_ticks)`。
    """
    step = max(1, int(step_ticks))
    factor = 0.5 ** (step / max(1.0, float(half_life_ticks)))
    gone = 0
    for r in mem.items():
        if keep_located and r.located == keep_located:
            continue                     # 家: 不衰减, 也不删
        rem = float(r.remember) * factor
        if rem < forget_threshold:
            mem.delete(r.item_id)
            gone += 1
        else:
            mem.update(r.item_id, remember=rem)
    return gone
