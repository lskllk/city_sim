# zh.gd —— 展示文案映射(镜像前端 Inspector.tsx / EventStream.tsx / WorldView.tsx 中的表)。
#
# 纯查表; 不改任何状态。
class_name Zh
extends RefCounted

const SIGNAL := {
	"energy": "精力", "hunger": "饥饿", "thirst": "口渴",
	"bladder": "如厕", "fun": "娱乐", "hp": "生命",
}

const ROOM_KIND := {
	"home": "住宅", "apartment": "公寓", "shop": "商店", "market": "集市",
	"work": "工作", "public": "公共", "site": "工地",
}

const TAG := {
	"edible": "食物", "sleepable": "床铺", "toilet": "卫生间", "drink": "饮水",
	"entertain": "娱乐", "consumable": "消耗品", "fun": "娱乐", "work": "工作台",
}

const EVENT := {
	"decision": "决策", "perceived": "感知", "interaction_done": "完成",
	"intent_failed": "失败", "bought": "购买", "stock_changed": "补货",
	"npc_died": "死亡",
}

const EVENT_TYPE := {
	"decision": "决策", "perceived": "感知",
	"bought": "购买", "interaction_done": "完成", "intent_failed": "失败",
	"stock_changed": "补货", "npc_died": "死亡",
}


static func signal_zh(k: String) -> String:
	return SIGNAL.get(k, k)


static func room_kind_zh(k: String) -> String:
	return ROOM_KIND.get(k, k)


static func tag_zh(k: String) -> String:
	return TAG.get(k, k)


static func event_zh(k: String) -> String:
	return EVENT.get(k, k)


static func event_type_zh(k: String) -> String:
	return EVENT_TYPE.get(k, k)
