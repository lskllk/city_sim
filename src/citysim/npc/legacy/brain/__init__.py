"""Decision layer —— 大脑：间歇决策(清醒度/重评) + 交互裁决。

模块职责(与旧 GOAP 栈剥离后)：
  - arousal.py    清醒度(0..1, 昼夜×精力×饥饿), 决定重评频度
  - review.py     单个体自持重评时钟(距下次全量重评剩几 tick)
  - indicator.py  交互裁决器: 从世界容器实时取物品, 打分/排序/selector,
                  返回本 tick 该交互的目标物品(Person.update 决策入口)

design: Indicator 取代旧 UtilityBrain+GoapPlanner —— 它不保存数据, 物品清单
由世界实时供给, 状态从 Person.RealtimeState 派生, 直接产出"要去用的物品"。
"""
from .indicator import Indicator, Item, ItemSource, ScoredItem

__all__ = [
    "Indicator",
    "Item",
    "ItemSource",
    "ScoredItem",
]
