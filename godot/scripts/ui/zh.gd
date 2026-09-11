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
	"interaction_aborted": "中止", "npc_died": "死亡",
}

const EVENT_TYPE := {
	"decision": "决策", "perceived": "感知",
	"bought": "购买", "interaction_done": "完成", "intent_failed": "失败",
	"stock_changed": "补货", "interaction_aborted": "中止", "npc_died": "死亡",
}

# 角色码 -> 中文(前端语义解释层; 后续可扩展到工程师/老师等)
const ROLE := {
	"worker": "工人", "engineer": "工程师", "programmer": "程序员",
	"teacher": "老师", "student": "学生", "doctor": "医生",
	"shopkeeper": "店主", "farmer農": "农民", "farmer": "农民",
	"unemployed": "失业", "dropout": "辍学", "retired": "退休",
}

# 货物/item_type -> 中文(前端语义解释层; 优先用实体自带的 name)
const ITEM := {
	"meal_simple": "简餐", "food_apple": "苹果", "food_pear": "梨",
	"media_tv": "电视", "bed_basic": "床", "toilet_basic": "马桶",
	"drink_dispenser": "饮水机", "seat_bench": "长椅", "game_mahjong": "麻将",
	"station_workbench": "工位",
}

# item_type 的类别(第一段) -> 语义动词(按“用什么”解释: 吃/睡/用…)
const VERB := {
	"bed": "睡", "meal": "吃", "food": "吃", "drink": "喝",
	"toilet": "上厕所", "media": "看", "game": "玩", "seat": "坐",
	"station": "工作", "shop": "买",
}

# 建筑 kind -> 中文
const KIND := {
	"home": "住所", "shop": "商业", "work": "工作", "public": "公共",
	"school": "学校", "clinic": "医疗", "farm": "农业",
}


static func signal_zh(k: String) -> String:
	return SIGNAL.get(k, k)


static func room_kind_zh(k: String) -> String:
	return ROOM_KIND.get(k, k)


static func tag_zh(k: String) -> String:
	return TAG.get(k, k)


static func event_zh(k: String) -> String:
	return EVENT.get(k, k)


static func role_zh(code: String) -> String:
	if code == "":
		return "—"
	return ROLE.get(code, code)


static func item_zh(t: String) -> String:
	if t == "":
		return "—"
	return ITEM.get(t, t)


## item_type -> 语义动词(按类别; 未知则“用”)。
static func verb_zh(item_type: String) -> String:
	if item_type == "":
		return "用"
	var parts := item_type.split("_")
	return VERB.get(str(parts[0]), "用")


## 把意图翻译成人话: 吃 简餐 / 睡 床 / 上厕所 马桶 / 买 简餐 / 前往 大超市。
static func action_text(intent: String, target_name: String,
		item_type: String = "") -> String:
	match intent:
		"move_to":
			return "前往 %s" % target_name
		"buy":
			return "买 %s" % target_name
		"interact":
			return "%s %s" % [verb_zh(item_type), target_name]
		"idle", "":
			return "空闲"
		_:
			return "%s %s" % [intent, target_name]


static func kind_zh(k: String) -> String:
	return KIND.get(k, k)


static func event_type_zh(k: String) -> String:
	return EVENT_TYPE.get(k, k)
