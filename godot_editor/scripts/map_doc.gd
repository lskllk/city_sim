extends Node
## MapDoc —— 地图文档模型 (编辑器唯一真源, autoload 名 `MapDoc`)。
##
## 只做"作者态"数据: 节点 / 边 / 建筑。视图只读写它, 导出为 citysim.map JSON。
## 坐标单位: 米; 内部 Vector2(定点化留给导出时取整)。不参与任何 simulation。
##
## 地图格式 v1:
## {
##   "format":"citysim.map", "version":1,
##   "world":{"unit":"m","bounds":[x,y,w,h],"grid":1.0},
##   "nodes":{"n_001":{"xy":[x,y],"kind":"junction"}},
##   "edges":{"e_001":{"a":"n_001","b":"n_002","class":"local",
##                     "width":4.0,"speed":1.3,"oneway":false,"geom":[[x,y],...]}},
##   "buildings":{"bld_001":{"type":"home_standard","center":[x,y],
##                           "size":[w,h],"rot":0.0,"doors":[[x,y],...]}}
## }

signal changed

const SCHEMA := "citysim.map"
const VERSION := 1
const AREA_PER_CAPACITY := 20.0   # 1 capacity ≈ 20 m²(面积∝容量的起始比例, 可调)

var bounds := Rect2(0.0, 0.0, 800.0, 600.0)
var grid_size := 1.0
var nodes: Dictionary = {}        # id -> {xy:Vector2, kind:String}
var edges: Dictionary = {}        # id -> {a,b,class,width,speed,oneway,geom:Array[Vector2]}
var buildings: Dictionary = {}    # id -> {type,center:Vector2,size:Vector2,rot:float,doors:Array[Vector2]}
var building_types: Dictionary = {}
var errors: Array = []             # validate() 结果: {level,msg,kind,id}

var _seq := {"n": 0, "e": 0, "b": 0}


func _ready() -> void:
	load_building_types()
	new_map()


# --- 建筑类型库(复用后端 config/buildings) --------------------------------
func load_building_types() -> void:
	building_types.clear()
	var root := ProjectSettings.globalize_path("res://").path_join("..").simplify_path()
	var dir_path := root.path_join("config").path_join("buildings")
	var d := DirAccess.open(dir_path)
	if d == null:
		push_warning("[MapDoc] 找不到建筑类型目录: " + dir_path)
		return
	d.list_dir_begin()
	var fn := d.get_next()
	while fn != "":
		if fn.ends_with(".json"):
			var txt := FileAccess.get_file_as_string(dir_path.path_join(fn))
			var j: Variant = JSON.parse_string(txt)
			if j is Dictionary and j.has("type"):
				building_types[String(j["type"])] = j
		fn = d.get_next()
	d.list_dir_end()


func type_display(type_id: String) -> String:
	var t: Dictionary = building_types.get(type_id, {})
	return String(t.get("name", type_id))


# --- 文档操作 ------------------------------------------------------------
func new_map() -> void:
	nodes.clear()
	edges.clear()
	buildings.clear()
	errors.clear()
	_seq = {"n": 0, "e": 0, "b": 0}
	changed.emit()


func default_size_for(type_id: String) -> Vector2:
	var t: Dictionary = building_types.get(type_id, {})
	var cap := float(t.get("capacity", 6))
	var asp := float(t.get("aspect", 1.0))
	var area := cap * AREA_PER_CAPACITY
	return Vector2(sqrt(area * asp), sqrt(area / asp))


func snap(p: Vector2) -> Vector2:
	if grid_size <= 0.0:
		return p
	return p.snapped(Vector2(grid_size, grid_size))


func add_building(type_id: String, world_pos: Vector2) -> String:
	_seq.b += 1
	var id := "bld_%03d" % int(_seq.b)
	buildings[id] = {"type": type_id, "center": snap(world_pos),
		"size": default_size_for(type_id), "rot": 0.0, "doors": []}
	errors = validate()
	changed.emit()
	return id


func add_node(world_pos: Vector2, kind: String = "junction") -> String:
	_seq.n += 1
	var id := "n_%03d" % int(_seq.n)
	nodes[id] = {"xy": snap(world_pos), "kind": kind}
	errors = validate()
	changed.emit()
	return id


func add_edge(a: String, b: String) -> String:
	if a == b or not nodes.has(a) or not nodes.has(b):
		return ""
	_seq.e += 1
	var id := "e_%03d" % int(_seq.e)
	edges[id] = {"a": a, "b": b, "class": "local", "width": 4.0,
		"speed": 1.3, "oneway": false, "geom": [nodes[a]["xy"], nodes[b]["xy"]]}
	errors = validate()
	changed.emit()
	return id


func move_node(id: String, world_pos: Vector2) -> void:
	if not nodes.has(id):
		return
	nodes[id]["xy"] = snap(world_pos)
	# 相邻边的端点几何跟随(仅当线段是直连两点)
	for eid in edges:
		var e: Dictionary = edges[eid]
		if e["a"] == id or e["b"] == id:
			var g: Array = e["geom"]
			if g.is_empty() or g.size() == 2:
				e["geom"] = [nodes[e["a"]]["xy"], nodes[e["b"]]["xy"]]
			else:
				if e["a"] == id:
					g[0] = nodes[id]["xy"]
				else:
					g[g.size() - 1] = nodes[id]["xy"]
	errors = validate()
	changed.emit()


func move_building(id: String, world_pos: Vector2) -> void:
	if not buildings.has(id):
		return
	buildings[id]["center"] = snap(world_pos)
	errors = validate()
	changed.emit()


func set_building_type(id: String, type_id: String) -> void:
	if not buildings.has(id):
		return
	buildings[id]["type"] = type_id
	buildings[id]["size"] = default_size_for(type_id)
	errors = validate()
	changed.emit()


func remove_node(id: String) -> void:
	nodes.erase(id)
	for eid in edges.keys():
		var e: Dictionary = edges[eid]
		if e["a"] == id or e["b"] == id:
			edges.erase(eid)
	errors = validate()
	changed.emit()


func remove_edge(id: String) -> void:
	edges.erase(id)
	errors = validate()
	changed.emit()


func remove_building(id: String) -> void:
	buildings.erase(id)
	errors = validate()
	changed.emit()


# --- 校验 (DRC) ----------------------------------------------------------
func validate() -> Array:
	var out: Array = []
	# 越界(用外接圆半径粗判)
	for id in buildings:
		var b: Dictionary = buildings[id]
		var c: Vector2 = b["center"]
		var s: Vector2 = b["size"]
		var r := 0.5 * Vector2(s.x, s.y).length()
		if (c.x - r < bounds.position.x or c.y - r < bounds.position.y
				or c.x + r > bounds.end.x or c.y + r > bounds.end.y):
			out.append({"level": "error", "msg": "建筑越界", "kind": "building", "id": id})
	# 建筑重叠 (OBB SAT)
	var bids: Array = buildings.keys()
	bids.sort()
	for i in range(bids.size()):
		for j in range(i + 1, bids.size()):
			if obb_overlap(buildings[bids[i]], buildings[bids[j]]):
				out.append({"level": "error", "msg": "建筑重叠", "kind": "building",
					"id": bids[i]})
				break
	# 路段过短
	for id in edges:
		var e: Dictionary = edges[id]
		var pa: Vector2 = nodes[e["a"]]["xy"]
		var pb: Vector2 = nodes[e["b"]]["xy"]
		if pa.distance_to(pb) < 3.0:
			out.append({"level": "warn", "msg": "路段过短", "kind": "edge", "id": id})
	# 建筑接入: 中心到最近路节点距离
	for id in buildings:
		var c: Vector2 = buildings[id]["center"]
		var best := INF
		for nid in nodes:
			best = minf(best, c.distance_to(nodes[nid]["xy"]))
		if best == INF or best > 40.0:
			out.append({"level": "warn", "msg": "建筑无邻近道路/接入", "kind": "building", "id": id})
	return out


func error_count(level: String = "") -> int:
	var n := 0
	for e in errors:
		if level == "" or e["level"] == level:
			n += 1
	return n


# --- 几何 helper ---------------------------------------------------------
func obb_corners(b: Dictionary) -> Array:
	var c: Vector2 = b["center"]
	var s: Vector2 = b["size"]
	var a := deg_to_rad(float(b.get("rot", 0.0)))
	var ux := Vector2(cos(a), sin(a))
	var uy := Vector2(-sin(a), cos(a))
	var hx := ux * (s.x * 0.5)
	var hy := uy * (s.y * 0.5)
	return [c + hx + hy, c - hx + hy, c - hx - hy, c + hx - hy]


func point_in_building(b: Dictionary, p: Vector2) -> bool:
	var d := p - (b["center"] as Vector2)
	var a := -deg_to_rad(float(b.get("rot", 0.0)))
	var lx := d.x * cos(a) - d.y * sin(a)
	var ly := d.x * sin(a) + d.y * cos(a)
	var s: Vector2 = b["size"]
	return absf(lx) <= s.x * 0.5 and absf(ly) <= s.y * 0.5


func obb_overlap(a: Dictionary, b: Dictionary) -> bool:
	var pa := obb_corners(a)
	var pb := obb_corners(b)
	var axes: Array = []
	for poly in [pa, pb]:
		for i in 4:
			var e: Vector2 = poly[(i + 1) % 4] - poly[i]
			if e.length() > 0.0001:
				axes.append(Vector2(-e.y, e.x).normalized())
	for ax in axes:
		var amin := INF
		var amax := -INF
		var bmin := INF
		var bmax := -INF
		for p in pa:
			var d: float = p.dot(ax)
			amin = minf(amin, d)
			amax = maxf(amax, d)
		for p in pb:
			var d: float = p.dot(ax)
			bmin = minf(bmin, d)
			bmax = maxf(bmax, d)
		if amax < bmin or bmax < amin:
			return false
	return true


# --- 序列化 --------------------------------------------------------------
func _v(p: Vector2) -> Array:
	return [snappedf(p.x, 0.001), snappedf(p.y, 0.001)]


func _vec(a) -> Vector2:
	if a is Array and a.size() >= 2:
		return Vector2(float(a[0]), float(a[1]))
	return Vector2.ZERO


func to_dict() -> Dictionary:
	var nd := {}
	for id in nodes:
		nd[id] = {"xy": _v(nodes[id]["xy"]), "kind": nodes[id]["kind"]}
	var ed := {}
	for id in edges:
		var e: Dictionary = edges[id]
		var g := []
		for p in e["geom"]:
			g.append(_v(p))
		ed[id] = {"a": e["a"], "b": e["b"], "class": e["class"],
			"width": e["width"], "speed": e["speed"],
			"oneway": e["oneway"], "geom": g}
	var bd := {}
	for id in buildings:
		var b: Dictionary = buildings[id]
		var doors := []
		for d in b["doors"]:
			doors.append(_v(d))
		bd[id] = {"type": b["type"], "center": _v(b["center"]),
			"size": _v(b["size"]), "rot": b["rot"], "doors": doors}
	return {"format": SCHEMA, "version": VERSION,
		"world": {"unit": "m",
			"bounds": [bounds.position.x, bounds.position.y, bounds.size.x, bounds.size.y],
			"grid": grid_size},
		"nodes": nd, "edges": ed, "buildings": bd}


func from_dict(d: Dictionary) -> void:
	new_map()
	var w: Dictionary = d.get("world", {})
	grid_size = float(w.get("grid", 1.0))
	var bd = w.get("bounds", [0, 0, 800, 600])
	if bd is Array and bd.size() >= 4:
		bounds = Rect2(float(bd[0]), float(bd[1]), float(bd[2]), float(bd[3]))
	var nd: Dictionary = d.get("nodes", {})
	for id in nd:
		nodes[String(id)] = {"xy": _vec(nd[id]["xy"]),
			"kind": String(nd[id].get("kind", "junction"))}
	var ed: Dictionary = d.get("edges", {})
	for id in ed:
		var e: Dictionary = ed[id]
		var g := []
		for p in e.get("geom", []):
			g.append(_vec(p))
		edges[String(id)] = {"a": String(e["a"]), "b": String(e["b"]),
			"class": String(e.get("class", "local")),
			"width": float(e.get("width", 4.0)),
			"speed": float(e.get("speed", 1.3)),
			"oneway": bool(e.get("oneway", false)), "geom": g}
	var bld: Dictionary = d.get("buildings", {})
	for id in bld:
		var b: Dictionary = bld[id]
		var doors := []
		for dd in b.get("doors", []):
			doors.append(_vec(dd))
		buildings[String(id)] = {"type": String(b["type"]),
			"center": _vec(b["center"]), "size": _vec(b["size"]),
			"rot": float(b.get("rot", 0.0)), "doors": doors}
	_recount()
	errors = validate()
	changed.emit()


func _recount() -> void:
	var mx := {"n": 0, "e": 0, "b": 0}
	for id in nodes:
		mx["n"] = maxi(mx["n"], int(String(id).get_slice("_", 1)))
	for id in edges:
		mx["e"] = maxi(mx["e"], int(String(id).get_slice("_", 1)))
	for id in buildings:
		mx["b"] = maxi(mx["b"], int(String(id).get_slice("_", 1)))
	_seq = mx


func save_map(path: String) -> bool:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		return false
	f.store_string(JSON.stringify(to_dict(), "  "))
	f.close()
	return true


func load_map(path: String) -> bool:
	var txt := FileAccess.get_file_as_string(path)
	if txt == "":
		return false
	var j: Variant = JSON.parse_string(txt)
	if not (j is Dictionary):
		return false
	from_dict(j)
	return true
