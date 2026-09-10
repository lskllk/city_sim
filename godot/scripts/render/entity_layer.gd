# entity_layer.gd —— NPC / 世界实体的渲染与命中(实体为场景实例, 可在编辑器里改样式)。
#
# 数据驱动: 数量/位置/图标来自 Store; 本层只做 reconcile / 平滑 / 拾取。
# 视觉模板: scenes/world/{npc_visual,entity_visual}.tscn。
class_name EntityLayer
extends Node2D

const NPC_SCENE: PackedScene = preload("res://scenes/world/npc_visual.tscn")
const ENTITY_SCENE: PackedScene = preload("res://scenes/world/entity_visual.tscn")

const ENT_FALLBACK := "▪"

const NPC_COLORS: Array[Color] = [
	Color("5bb0ff"), Color("ffb35c"), Color("5bd6a0"), Color("ee7d9a"),
	Color("c08bff"), Color("79e0e0"), Color("f0e05e"), Color("ff8a5c"),
	Color("a0d96b"), Color("ffd1dc"),
]

# id -> { node: Node2D, cur: Vector2, target: Vector2 }
var _npc_vis: Dictionary = {}
# id -> { node: Node2D, target: Vector2 }
var _ent_vis: Dictionary = {}
var _selected := ""


func set_selected(id: String) -> void:
	if _selected == id:
		return
	var prev := _selected
	_selected = id
	if _npc_vis.has(prev):
		_npc_vis[prev]["node"].set_selected(false)
	if _npc_vis.has(id):
		_npc_vis[id]["node"].set_selected(true)


## 结构 reconcile: 增删视觉实例 + 实体按建筑内顺序摆放。每次 snapshot 调用。
func reconcile() -> void:
	var npcs := Store.npcs
	var ents := Store.entities

	for id in _npc_vis.keys():
		if not npcs.has(id):
			_free_visual(_npc_vis[id]["node"])
			_npc_vis.erase(id)
	for id in _ent_vis.keys():
		if not ents.has(id):
			_free_visual(_ent_vis[id]["node"])
			_ent_vis.erase(id)

	for id in npcs:
		if not _npc_vis.has(id):
			var node: Node2D = NPC_SCENE.instantiate()
			add_child(node)
			node.set_color(_npc_color(id))
			var p := Interp.to_vec2(npcs[id].get("position"))
			node.position = p
			_npc_vis[id] = {"node": node, "cur": p, "target": p}
			if id == _selected:
				node.set_selected(true)
	for id in ents:
		if not _ent_vis.has(id):
			var node: Node2D = ENTITY_SCENE.instantiate()
			add_child(node)
			var icon := Protocol.s(ents[id].get("icon", ""), ENT_FALLBACK)
			if icon == "":
				icon = ENT_FALLBACK
			node.config(icon, _tag_color(ents[id]))
			_ent_vis[id] = {"node": node, "target": Vector2.ZERO}

	_layout_entities(ents, Store.rooms)


## snapshot 到达: 更新 NPC 目标位置(实体位置由摆放决定)。
func apply_targets() -> void:
	for id in Store.npcs:
		if _npc_vis.has(id):
			_npc_vis[id]["target"] = Interp.to_vec2(Store.npcs[id].get("position"))


func _process(delta: float) -> void:
	var alpha := Interp.frame_alpha(delta, 10.0)
	for id in _npc_vis:
		var v: Dictionary = _npc_vis[id]
		var cur: Vector2 = v["cur"]
		var target: Vector2 = v["target"]
		if cur.distance_squared_to(target) > 0.0001:
			cur = cur.lerp(target, alpha)
			v["cur"] = cur
			v["node"].position = cur


# ---------------------------------------------------------------------------
# 命中(世界坐标)
# ---------------------------------------------------------------------------
func pick_npc(world_pos: Vector2) -> String:
	return _pick(_npc_vis, world_pos, true)


func pick_entity(world_pos: Vector2) -> String:
	return _pick(_ent_vis, world_pos, false)


func _pick(table: Dictionary, world_pos: Vector2, use_cur: bool) -> String:
	var best := ""
	var best_d := 14.0
	for id in table:
		var p: Vector2 = table[id]["cur"] if use_cur else table[id]["target"]
		var d := world_pos.distance_to(p)
		if d < best_d:
			best = id
			best_d = d
	return best


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------
func _layout_entities(ents: Dictionary, rooms: Dictionary) -> void:
	var by_room: Dictionary = {}
	for id in ents:
		var loc := Protocol.s(ents[id].get("loc", ""))
		if not by_room.has(loc):
			by_room[loc] = []
		by_room[loc].append(ents[id])

	for loc in by_room:
		var list: Array = by_room[loc]
		list.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			var ai := Protocol.num(a.get("shelf_index"), 1.0e9)
			var bi := Protocol.num(b.get("shelf_index"), 1.0e9)
			if ai != bi:
				return ai < bi
			return Protocol.s(a.get("id")) < Protocol.s(b.get("id"))
		)

		if not rooms.has(loc):
			# 建筑矩形缺失: 回退到后端真实坐标
			for e in list:
				var eid := Protocol.s(e.get("id"))
				if _ent_vis.has(eid):
					_set_ent_pos(eid, Interp.to_vec2(e.get("position")))
			continue

		var r: Dictionary = rooms[loc]
		var count := list.size()
		var rw := Protocol.num(r.get("w"))
		var step := minf(40.0, (rw - 20.0) / float(maxi(1, count)))
		var start_x := Protocol.num(r.get("x")) + rw * 0.5 - ((count - 1) * step) * 0.5
		var y := Protocol.num(r.get("y")) + Protocol.num(r.get("h")) - 16.0
		for i in range(count):
			var eid := Protocol.s(list[i].get("id"))
			if _ent_vis.has(eid):
				_set_ent_pos(eid, Vector2(start_x + i * step, y))


func _set_ent_pos(id: String, p: Vector2) -> void:
	_ent_vis[id]["target"] = p
	_ent_vis[id]["node"].position = p


func _free_visual(node: Node) -> void:
	if is_instance_valid(node):
		remove_child(node)
		node.queue_free()


func _npc_color(id: String) -> Color:
	return NPC_COLORS[absi(id.hash()) % NPC_COLORS.size()]


func _tag_color(e: Dictionary) -> Color:
	var tags: Variant = e.get("tags", [])
	var t: Array = tags if typeof(tags) == TYPE_ARRAY else []
	if t.has("edible") or t.has("food"):
		return Color("7ed58a")
	if t.has("sleepable"):
		return Color("8f9fd8")
	if t.has("toilet"):
		return Color("5bc9c9")
	if t.has("drink"):
		return Color("69a8f0")
	if t.has("entertain") or t.has("fun"):
		return Color("b78beb")
	if t.has("work"):
		return Color("d0b26a")
	return Color("55637c")
