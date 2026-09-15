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
signal event_received(ev: Dictionary)   # 后端事件流(死亡/成交/失败…)

# ---- 世界真值(snapshot 提供) ----
var entities: Dictionary = {}          # id -> Dictionary
var npcs: Dictionary = {}              # id -> Dictionary
var rooms: Dictionary = {}             # id -> Dictionary
var floors: Dictionary = {}            # 建筑 id -> 楼层单元数(由 locations[].part_of 统计)
var map: Dictionary = {}               # 编辑器原始地图 {nodes,edges,buildings}; 无则 {}
var canvas: Dictionary = {"w": 1280.0, "h": 800.0}
var scenario: String = ""
## 后端场景加载失败的原因(空 = 正常)。后端不闪退了, 原因走这里给界面显示。
var scene_error: String = ""
## 公司(只读镜像): [{id,name,cash,owner,shops,staff}] —— 经营面板以后读它
var companies: Array = []
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
var sel_floor: int = 1                   # 建筑页正在看第几层(影响观察集)
var history: Array = []                  # 浏览历史 [{kind, id}], 供「返回」


func clear_world() -> void:
	entities = {}
	npcs = {}
	rooms = {}
	floors = {}
	history = []
	map = {}
	canvas = {"w": 1280.0, "h": 800.0}
	scenario = ""
	seed_value = 0
	n_npc = 0
	signals_list = []
	history = []


func init_hello(h: Dictionary) -> void:
	scenario = Protocol.s(h.get("scenario"))
	# 后端场景坏了也能起来(不闪退), 原因走这里; 界面负责显示
	scene_error = Protocol.s(h.get("scene_error"))
	companies = Protocol.as_array(h.get("companies", []))
	seed_value = int(Protocol.num(h.get("seed")))
	n_npc = int(Protocol.num(h.get("n_npc")))
	var sigs: Variant = h.get("signals", [])
	signals_list = sigs if typeof(sigs) == TYPE_ARRAY else []

	var info := Protocol.as_dict(h.get("locations", {}))
	var locs := Protocol.as_dict(info.get("locations", {}))
	rooms = locs
	map = Protocol.as_dict(h.get("map", {}))
	# 楼层单元统计: bld_007_f1/f2/f3 → floors["bld_007"] = 3
	floors = {}
	for lid in rooms:
		var p := Protocol.s((rooms[lid] as Dictionary).get("part_of", ""))
		if p != "":
			floors[p] = int(floors.get(p, 0)) + 1
	var cv := Protocol.as_dict(info.get("canvas", {}))
	if not cv.is_empty():
		canvas = {
			"w": Protocol.num(cv.get("w"), 1280.0),
			"h": Protocol.num(cv.get("h"), 800.0),
		}
	hello_received.emit()


func apply_snapshot(snap: Dictionary) -> void:
	# 【合并】而非整体替换: 后端采用【观察驱动】下发 —— 渲染状态未变的 NPC
	# (典型: 在家不动的) 不出现在这一帧。不合并的话它们会被清掉。
	_merge_into(npcs, snap.get("npcs", []))
	_merge_into(entities, snap.get("entities", []))
	# 消失的 id(死亡/被消耗): 合并式更新不会自动删, 必须要后端显式告知
	var gone := Protocol.as_dict(snap.get("gone", {}))
	for gid in Protocol.as_array(gone.get("npcs", [])):
		remove_npc(str(gid))
	for gid in Protocol.as_array(gone.get("entities", [])):
		remove_entity(str(gid))
	tick = int(Protocol.num(snap.get("tick")))
	day = int(Protocol.num(snap.get("day"), 1.0))
	clock = Protocol.s(snap.get("clock"), "00:00")
	speed = Protocol.s(snap.get("speed"), "pause")
	running = Protocol.b(snap.get("running"))
	tps = Protocol.num(snap.get("tps"))
	snapshot_applied.emit()


func select(kind: String, id: String) -> void:
	if kind == sel_kind and id == _sel_id():
		return
	history.append({"kind": sel_kind, "id": _sel_id()})   # 记账, 供返回
	_apply(kind, id)
	sel_floor = 1                    # 换选中 → 从 1 层开始
	_notify_focus()
	selection_changed.emit()


## 建筑页切楼层: 改的是“在盯哪一层”, 要重新上报观察集。
func set_floor(f: int) -> void:
	var v := clampi(f, 1, 1)
	if sel_kind == "location":
		v = clampi(f, 1, floor_units(building_of(sel_location)))
	if v == sel_floor:
		return
	sel_floor = v
	_notify_focus()


## 上报【观察集】给后端(观察驱动)。
##
## 后端只推“渲染状态变了的” + “我正在看的”; 而 signals(进度条/生命条)
## 每 tick 都在变但不属于渲染状态 —— 所以**正在看的**必须报上去,
## 否则静止 NPC 的进度条永远不刷新。
## 视图偏好, 不是 simulation; 只在选中变化时发。
func _notify_focus() -> void:
	# 只报【当前页面真正在展示的东西】:
	#   npc 页   → 就那一个人(不要把整栋楼拖进来: 那是 60x 的流量)
	#   建筑页   → 那栋楼的人(列表上要画生命条)
	#   物件页   → 不需要任何人
	var npc := ""
	var loc := ""
	match sel_kind:
		"npc":
			npc = sel_npc
		"location":
			# 只报【当前那一层】的单元(bld_x_fN) —— 建筑页一次只看一层,
		# 报整栋楼会白白把全楼住户(可达百人)都拉进观察集。
			loc = unit_of(building_of(sel_location), sel_floor)
	Commands.cmd("select", {"npc": npc, "location": loc})


## 回退到上一个选中项。
func back() -> void:
	if history.is_empty():
		return
	var prev: Dictionary = history.pop_back()
	_apply(Protocol.s(prev.get("kind", "")), Protocol.s(prev.get("id", "")))
	selection_changed.emit()


func can_go_back() -> bool:
	return not history.is_empty()


func _sel_id() -> String:
	match sel_kind:
		"npc":
			return sel_npc
		"location":
			return sel_location
		"entity":
			return sel_entity
		_:
			return ""


func _apply(kind: String, id: String) -> void:
	sel_kind = kind
	sel_npc = id if kind == "npc" else ""
	sel_location = id if kind == "location" else ""
	sel_entity = id if kind == "entity" else ""


func clear_selection() -> void:
	select("", "")


## NPC 从世界消失(死亡/被删): 从镜像移除; 若正被选中 → 退回去。
func remove_npc(id: String) -> void:
	if not npcs.has(id):
		return
	npcs.erase(id)
	if sel_kind == "npc" and sel_npc == id:
		history.clear()
		select("", "")


func remove_entity(id: String) -> void:
	if not entities.has(id):
		return
	entities.erase(id)
	if sel_kind == "entity" and sel_entity == id:
		history.clear()
		select("", "")


## 处理后端事件流(观察器把它当“看得见的通知”)。
## npc_died: 立刻移除(不等 gone 字段; 事件与快照同帧到达, 先到先做)。
func apply_event(ev: Dictionary) -> void:
	var kind := Protocol.s(ev.get("kind", ev.get("type", "")))
	match kind:
		"npc_died":
			remove_npc(Protocol.s(ev.get("subject", "")))
	event_received.emit(ev)


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


## 楼层单元(bld_007_f2) → 所属建筑(bld_007); 普通地点 → 它自己。
## 多楼层场景里 NPC/物件住在子地点里, 画建筑/算占用时必须先归到父建筑。
func building_of(loc_id: String) -> String:
	if loc_id == "":
		return ""
	var p := Protocol.s(room(loc_id).get("part_of", ""))
	return p if p != "" else loc_id


## 该建筑是否被分成楼层单元。
## 注意用【>0】而不是【>1】: 只有 1 个单元(bld_007_f1)也是分过的,
## 这时人住在 f1 里而不是 bld_007 本体上 —— 用 >1 会一个都找不到。
func is_multi(bid: String) -> bool:
	return int(floors.get(bid, 0)) > 0


## 楼层数(单层建筑返回 1)。
func floor_units(bid: String) -> int:
	return maxi(1, int(floors.get(bid, 0)))


## 第 floor 层(1-based)对应的点位: 多楼层 → bld_x_fN; 单层 → 建筑本体。
func unit_of(bid: String, floor: int) -> String:
	if not is_multi(bid):
		return bid
	return "%s_f%d" % [bid, clampi(floor, 1, floor_units(bid))]


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
	return "点建筑 → 右侧选人"


func _to_map(arr: Variant) -> Dictionary:
	var out := {}
	_merge_into(out, arr)
	return out


## 把 [{id, ...}] 逐条并进 dst: 同 id 的【按字段】更新(保留上次未下发的字段)。
func _merge_into(dst: Dictionary, arr: Variant) -> void:
	if typeof(arr) != TYPE_ARRAY:
		return
	for it in (arr as Array):
		if typeof(it) != TYPE_DICTIONARY or not it.has("id"):
			continue
		var key := str(it["id"])
		if dst.has(key) and typeof(dst[key]) == TYPE_DICTIONARY:
			for k in (it as Dictionary):
				dst[key][k] = it[k]
		else:
			dst[key] = it
