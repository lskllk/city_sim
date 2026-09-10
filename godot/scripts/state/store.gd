# store.gd —— 世界镜像 + 模拟/选择状态(autoload 名 `Store`)。
#
# 铁律: snapshot 是 authoritative, 本 store 只是只读镜像, 不含任何 simulation 逻辑。
# 对应前端 state/{worldStore,simulationStore,selectionStore}.ts 的合并。
#
# 信号:
#   hello_received      —— 收到 hello, 场景/画布/地点就绪
#   snapshot_applied    —— 收到一帧 snapshot, 世界真值已更新
#   selection_changed   —— 选中项变化
#   connection_changed  —— WS 连接状态变化
extends Node

signal hello_received
signal snapshot_applied
signal selection_changed
signal connection_changed(status: String)

# ---- 世界真值(snapshot 提供) ----
var entities: Dictionary = {}          # id -> Dictionary
var npcs: Dictionary = {}              # id -> Dictionary
var rooms: Dictionary = {}             # id -> Dictionary
var canvas: Dictionary = {"w": 1280.0, "h": 800.0}
var scenario: String = ""
var seed_value: int = 0
var n_npc: int = 0
var signals_list: Array = []

# ---- 模拟时间/控制状态 ----
var tick: int = 0
var day: int = 1
var clock: String = "00:00"
var speed: String = "pause"
var running: bool = false
var tps: float = 0.0
var connection: String = "connecting"

# ---- 选中(一次只选中 npc / location / entity 之一) ----
var sel_kind: String = ""
var sel_npc: String = ""
var sel_location: String = ""
var sel_entity: String = ""


func clear_world() -> void:
	entities = {}
	npcs = {}
	rooms = {}
	canvas = {"w": 1280.0, "h": 800.0}
	scenario = ""
	seed_value = 0
	n_npc = 0
	signals_list = []


func init_hello(h: Dictionary) -> void:
	scenario = Protocol.s(h.get("scenario"))
	seed_value = int(Protocol.num(h.get("seed")))
	n_npc = int(Protocol.num(h.get("n_npc")))
	var sigs: Variant = h.get("signals", [])
	signals_list = sigs if typeof(sigs) == TYPE_ARRAY else []

	var info := Protocol.as_dict(h.get("locations", {}))
	var locs := Protocol.as_dict(info.get("locations", {}))
	rooms = locs
	var cv := Protocol.as_dict(info.get("canvas", {}))
	if not cv.is_empty():
		canvas = {
			"w": Protocol.num(cv.get("w"), 1280.0),
			"h": Protocol.num(cv.get("h"), 800.0),
		}
	hello_received.emit()


func apply_snapshot(snap: Dictionary) -> void:
	npcs = _to_map(snap.get("npcs", []))
	entities = _to_map(snap.get("entities", []))
	tick = int(Protocol.num(snap.get("tick")))
	day = int(Protocol.num(snap.get("day"), 1.0))
	clock = Protocol.s(snap.get("clock"), "00:00")
	speed = Protocol.s(snap.get("speed"), "pause")
	running = Protocol.b(snap.get("running"))
	tps = Protocol.num(snap.get("tps"))
	snapshot_applied.emit()


func select(kind: String, id: String) -> void:
	sel_kind = kind
	sel_npc = id if kind == "npc" else ""
	sel_location = id if kind == "location" else ""
	sel_entity = id if kind == "entity" else ""
	selection_changed.emit()


func clear_selection() -> void:
	select("", "")


func set_connection(status: String) -> void:
	if connection == status:
		return
	connection = status
	connection_changed.emit(status)


# ---------------------------------------------------------------------------
# 只读查询
# ---------------------------------------------------------------------------
func npc(id: String) -> Dictionary:
	return entities_or(npcs, id)


func entity(id: String) -> Dictionary:
	return entities_or(entities, id)


func room(id: String) -> Dictionary:
	return entities_or(rooms, id)


func entities_or(d: Dictionary, id: String) -> Dictionary:
	var v: Variant = d.get(id, null)
	return v if typeof(v) == TYPE_DICTIONARY else {}


## id -> 显示名(entities > npcs > rooms > id)。镜像 Inspector.resolveName。
func name_of(id: String) -> String:
	if id == "":
		return "—"
	for d in [entities, npcs, rooms]:
		if d.has(id):
			return Protocol.s(d[id].get("name", id), id)
	return id


## 当前选中项的人类可读标签。镜像 WorldView.useSelectedName。
func selected_name() -> String:
	match sel_kind:
		"npc":
			var n := npc(sel_npc)
			if not n.is_empty():
				return "已选中：%s" % Protocol.s(n.get("name", sel_npc), sel_npc)
		"location":
			var r := room(sel_location)
			if not r.is_empty():
				return "已选中 地点：%s" % Protocol.s(r.get("name", sel_location), sel_location)
		"entity":
			var e := entity(sel_entity)
			if not e.is_empty():
				return "已选中 物品：%s" % Protocol.s(e.get("name", sel_entity), sel_entity)
	return "点选 NPC / 地点 / 物品"


func _to_map(arr: Variant) -> Dictionary:
	var out := {}
	if typeof(arr) != TYPE_ARRAY:
		return out
	for it in (arr as Array):
		if typeof(it) == TYPE_DICTIONARY and it.has("id"):
			out[str(it["id"])] = it
	return out
