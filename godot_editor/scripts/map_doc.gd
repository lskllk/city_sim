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

# 进出口(资产逻辑定义): 观察器/后端 config/buildings/*.json 的 doors 段。
# 缺省南面; 编辑器在摆放时按主门自动朝向最近道路。
const DOOR_DEFAULT := {"side": "south", "offset": 0.0}
const SIDE_NORMAL := {
	"north": Vector2(0, -1), "south": Vector2(0, 1),
	"east": Vector2(1, 0), "west": Vector2(-1, 0),
}
const ROAD_SNAP_M := 3.0          # 画路点击吸附到既有道路的距离(米)

var bounds := Rect2(0.0, 0.0, 800.0, 600.0)
var grid_size := 1.0
var nodes: Dictionary = {}        # id -> {xy:Vector2, kind:String}
var edges: Dictionary = {}        # id -> {a,b,class,width,speed,oneway,geom:Array[Vector2]}
var buildings: Dictionary = {}    # id -> {type,center:Vector2,size:Vector2,rot:float,doors:Array[Vector2]}
var npcs: Dictionary = {}         # id -> {name,gender,birthday,role,money,home,personality,init,traits,tell_bias}
var items: Dictionary = {}        # id -> {type,at,owner,stock,price,persist_empty}
var building_types: Dictionary = {}
var name_pool: Dictionary = {}    # config/names/names.json
var item_types: Dictionary = {}    # config/items/*.json
var errors: Array = []             # validate() 结果: {level,msg,kind,id}

# 人物可选角色码(与后端 config/scenes 一致)
const ROLES := ["worker", "student", "engineer", "teacher", "doctor",
	"shopkeeper", "unemployed", "retired"]

var _seq := {"n": 0, "e": 0, "b": 0, "i": 0}


# --- 进出口几何 helper(资产逻辑) ---------------------------------------
func _type_doors(type_id: String) -> Array:
	var t: Dictionary = building_types.get(type_id, {})
	var ds: Variant = t.get("doors")
	if ds is Array and not (ds as Array).is_empty():
		return ds
	return [DOOR_DEFAULT.duplicate()]


## 门定义(side/offset) + 建筑尺寸 → 局部(未旋转)门点与朝外法线。
func door_local(b: Dictionary, d: Dictionary) -> Dictionary:
	var s: Vector2 = b["size"]
	var off := float(d.get("offset", 0.0))
	match String(d.get("side", "south")):
		"north":
			return {"pos": Vector2(s.x * off, -s.y * 0.5), "normal": Vector2(0, -1)}
		"east":
			return {"pos": Vector2(s.x * 0.5, s.y * off), "normal": Vector2(1, 0)}
		"west":
			return {"pos": Vector2(-s.x * 0.5, s.y * off), "normal": Vector2(-1, 0)}
		_:
			return {"pos": Vector2(s.x * off, s.y * 0.5), "normal": Vector2(0, 1)}


func _rot_vec(v: Vector2, deg: float) -> Vector2:
	var a := deg_to_rad(deg)
	return Vector2(v.x * cos(a) - v.y * sin(a), v.x * sin(a) + v.y * cos(a))


## 建筑所有门的【世界】门点+法线(导出/渲染共用)。
func door_worlds(b: Dictionary) -> Array:
	var out: Array = []
	var rot := float(b.get("rot", 0.0))
	for d in _type_doors(String(b["type"])):
		var ld: Dictionary = door_local(b, d)
		out.append({
			"pos": (b["center"] as Vector2) + _rot_vec(ld["pos"], rot),
			"normal": _rot_vec(ld["normal"], rot),
		})
	return out


func _sync_doors(b: Dictionary) -> void:
	var doors: Array = []
	for d in door_worlds(b):
		doors.append(d["pos"])
	b["doors"] = doors


## 最近道路段: {point, dir, width, edge, dist}; 无路返回 {}。
func nearest_road(p: Vector2) -> Dictionary:
	var best: Dictionary = {}
	var bd := INF
	for id in edges:
		var g: Array = (edges[id] as Dictionary)["geom"]
		for i in range(g.size() - 1):
			var a: Vector2 = g[i]
			var c: Vector2 = g[i + 1]
			var cp := _closest_on_seg(p, a, c)
			var d := p.distance_to(cp)
			if d < bd:
				bd = d
				best = {"point": cp, "dir": (c - a).normalized(),
					"width": float((edges[id] as Dictionary)["width"]),
					"edge": id, "dist": d}
	return best


func _closest_on_seg(p: Vector2, a: Vector2, b: Vector2) -> Vector2:
	var ab := b - a
	var l2 := ab.length_squared()
	if l2 < 0.0001:
		return a
	return a + ab * clampf((p - a).dot(ab) / l2, 0.0, 1.0)


## 把建筑按主门对齐到 hint 附近道路: 门朝路, 墙面贴路沿。
## 返回是否对齐成功(无路则 false)。
func align_to_road(b: Dictionary, hint: Vector2) -> bool:
	if edges.is_empty():
		return false
	var road := nearest_road(hint)
	if road.is_empty():
		return false
	var n := hint - (road["point"] as Vector2)
	if n.length() < 0.001:
		n = (road["dir"] as Vector2).orthogonal()
	n = n.normalized()
	# 主门朝外法线旋转后应指向道路 = -n
	var ld: Dictionary = door_local(b, _type_doors(String(b["type"]))[0])
	var local_n: Vector2 = ld["normal"]
	var theta := atan2(-n.y, -n.x) - atan2(local_n.y, local_n.x)
	b["rot"] = rad_to_deg(theta)
	# 门点贴路沿: center = 路沿 - R*local_door
	var rvec := _rot_vec(ld["pos"], float(b["rot"]))
	var curb := (road["point"] as Vector2) + n * (float(road["width"]) * 0.5)
	b["center"] = curb - rvec
	_sync_doors(b)
	return true


func _ready() -> void:
	load_building_types()
	load_name_pool()
	load_item_types()
	new_map()


func _config_root() -> String:
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()


func load_name_pool() -> void:
	name_pool = {}
	var p := _config_root().path_join("config").path_join("names").path_join("names.json")
	var j: Variant = JSON.parse_string(FileAccess.get_file_as_string(p))
	if j is Dictionary:
		name_pool = j
	else:
		push_warning("[MapDoc] 找不到姓名池: " + p)


## 物件类型库(复用后端 config/items)
func load_item_types() -> void:
	item_types.clear()
	var dir_path := _config_root().path_join("config").path_join("items")
	var d := DirAccess.open(dir_path)
	if d == null:
		push_warning("[MapDoc] 找不到物件目录: " + dir_path)
		return
	d.list_dir_begin()
	var fn := d.get_next()
	while fn != "":
		if fn.ends_with(".json"):
			var j: Variant = JSON.parse_string(
				FileAccess.get_file_as_string(dir_path.path_join(fn)))
			if j is Dictionary and j.has("item_type"):
				item_types[String(j["item_type"])] = j
		fn = d.get_next()
	d.list_dir_end()


func item_display(type_id: String) -> String:
	var d: Dictionary = item_types.get(type_id, {})
	return String(d.get("name", type_id))


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
	npcs.clear()
	items.clear()
	errors.clear()
	_seq = {"n": 0, "e": 0, "b": 0, "i": 0}
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


## 摆放建筑(规则: 必须先有路; 自动把主门对齐到最近道路)。无路返回 ""。
func add_building(type_id: String, world_pos: Vector2) -> String:
	if edges.is_empty():
		return ""
	_seq.b += 1
	var id := "bld_%03d" % int(_seq.b)
	buildings[id] = {"type": type_id, "center": world_pos,
		"size": default_size_for(type_id), "rot": 0.0, "doors": []}
	align_to_road(buildings[id], world_pos)
	_sync_doors(buildings[id])
	errors = validate()
	changed.emit()
	return id


## 拖拽中的自由移动(不吸附); 松手后调用 align_building 归位到路边。
func move_building(id: String, world_pos: Vector2) -> void:
	if not buildings.has(id):
		return
	buildings[id]["center"] = world_pos
	_sync_doors(buildings[id])
	errors = validate()
	changed.emit()


## 把已放置建筑重新对齐到最近道路。
func align_building(id: String) -> bool:
	if not buildings.has(id):
		return false
	var b: Dictionary = buildings[id]
	if not align_to_road(b, b["center"]):
		return false
	errors = validate()
	changed.emit()
	return true


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
	edges[id] = _make_edge(a, b, {})
	errors = validate()
	changed.emit()
	return id


func _make_edge(a: String, b: String, attrs: Dictionary) -> Dictionary:
	return {"a": a, "b": b,
		"class": String(attrs.get("class", "local")),
		"width": float(attrs.get("width", 4.0)),
		"speed": float(attrs.get("speed", 1.3)),
		"oneway": bool(attrs.get("oneway", false)),
		"geom": [nodes[a]["xy"], nodes[b]["xy"]]}


## 画路落点: 靠既有道路则打断道路插入 T/十字节点, 否则新建节点。
func add_road_node(world_pos: Vector2) -> String:
	var road := nearest_road(world_pos)
	if not road.is_empty() and float(road["dist"]) <= ROAD_SNAP_M:
		var p: Vector2 = road["point"]
		for nid in nodes:
			if (nodes[nid]["xy"] as Vector2).distance_to(p) < 0.5:
				return nid
		return _split_edge(String(road["edge"]), p)
	return add_node(world_pos)


func _split_edge(edge_id: String, point: Vector2) -> String:
	if not edges.has(edge_id):
		return add_node(point)
	var e: Dictionary = edges[edge_id]
	var attrs := {"class": e["class"], "width": e["width"],
		"speed": e["speed"], "oneway": e["oneway"]}
	var a_id := String(e["a"])
	var b_id := String(e["b"])
	_seq.n += 1
	var nid := "n_%03d" % int(_seq.n)
	nodes[nid] = {"xy": point, "kind": "junction"}
	edges.erase(edge_id)
	edges[_next_edge_id()] = _make_edge(a_id, nid, attrs)
	edges[_next_edge_id()] = _make_edge(nid, b_id, attrs)
	errors = validate()
	changed.emit()
	return nid


func _next_edge_id() -> String:
	_seq.e += 1
	return "e_%03d" % int(_seq.e)


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


func set_building_type(id: String, type_id: String) -> void:
	if not buildings.has(id):
		return
	buildings[id]["type"] = type_id
	buildings[id]["size"] = default_size_for(type_id)
	align_to_road(buildings[id], buildings[id]["center"])
	_sync_doors(buildings[id])
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
	# 解除引用: 人物住所 / 物件所在建筑
	for iid in items:
		if String(items[iid].get("at", "")) == id:
			items[iid]["at"] = ""
	for pid in npcs:
		if String(npcs[pid].get("home", "")) == id:
			npcs[pid]["home"] = ""
	errors = validate()
	changed.emit()


func building_name(bid: String) -> String:
	if not buildings.has(bid):
		return bid
	var b: Dictionary = buildings[bid]
	var custom := String(b.get("name", ""))
	return custom if custom != "" else type_display(String(b["type"]))


func set_building_name(bid: String, name: String) -> void:
	if buildings.has(bid):
		buildings[bid]["name"] = name
		changed.emit()


# --- 人物编辑 -----------------------------------------------------------
func _rng() -> RandomNumberGenerator:
	var r := RandomNumberGenerator.new()
	r.randomize()
	return r


func _pick(rng: RandomNumberGenerator, arr: Array) -> Variant:
	return arr[rng.randi_range(0, arr.size() - 1)] if not arr.is_empty() else null


## 随机人设: 姓名/性别/年龄→生日/角色/资金/性格倍率。
func random_person(rng: RandomNumberGenerator = null) -> Dictionary:
	var r := rng if rng != null else _rng()
	var gender := "female" if r.randf() < 0.5 else "male"
	var age := r.randi_range(18, 70)
	var year := 2026 - age
	var month := r.randi_range(1, 12)
	var day := r.randi_range(1, 28)
	var surnames: Array = name_pool.get("surnames", [])
	var givens: Array = name_pool.get(
		"given_female" if gender == "female" else "given_male", [])
	var nm := "无名"
	var pid := ""
	if not surnames.is_empty() and not givens.is_empty():
		var s: Dictionary = _pick(r, surnames)
		var g: Dictionary = _pick(r, givens)
		nm = String(s.get("hz", "")) + String(g.get("hz", ""))
		pid = "npc_%s_%s" % [String(s.get("py", "x")), String(g.get("py", "x"))]
	return {
		"id": pid, "name": nm, "gender": gender,
		"birthday": "%04d-%02d-%02d" % [year, month, day],
		"role": String(_pick(r, ROLES)),
		"money": float(r.randi_range(0, 500)),
		"home": "",
		"personality": {
			"hunger": snappedf(r.randf_range(0.8, 1.3), 0.1),
			"energy": snappedf(r.randf_range(0.8, 1.3), 0.1),
			"fun": snappedf(r.randf_range(0.7, 1.3), 0.1),
		},
		"init": {}, "traits": {}, "tell_bias": 1.0,
	}


func _unique_person_id(base: String) -> String:
	if base == "":
		base = "npc_new"
	if not npcs.has(base):
		return base
	var i := 2
	while npcs.has("%s_%d" % [base, i]):
		i += 1
	return "%s_%d" % [base, i]


## home ""=无住所; 不传 spec 时用随机人设。返回 person id。
func add_npc(home: String = "", spec: Dictionary = {}) -> String:
	var s: Dictionary = spec.duplicate(true) if not spec.is_empty() else random_person()
	s["home"] = home if home != "" else String(s.get("home", ""))
	s["id"] = _unique_person_id(String(s.get("id", "")))
	npcs[String(s["id"])] = s
	errors = validate()
	changed.emit()
	return String(s["id"])


func update_npc(id: String, patch: Dictionary) -> void:
	if not npcs.has(id):
		return
	for k in patch:
		npcs[id][k] = patch[k]
	errors = validate()
	changed.emit()


## 重滚人设(id 稳定, 保留住所; 物品归属引用不受影响)。
func randomize_npc(id: String) -> void:
	if not npcs.has(id):
		return
	var home := String(npcs[id].get("home", ""))
	var s := random_person()
	s["id"] = id
	s["home"] = home
	npcs[id] = s
	errors = validate()
	changed.emit()


func remove_npc(id: String) -> void:
	npcs.erase(id)
	for iid in items:
		if String(items[iid].get("owner", "")) == id:
			items[iid]["owner"] = ""
	errors = validate()
	changed.emit()


func npc_display(id: String) -> String:
	var n: Dictionary = npcs.get(id, {})
	return "%s (%s)" % [String(n.get("name", id)), id]


func age_of(n: Dictionary) -> int:
	var parts := String(n.get("birthday", "")).split("-")
	return 2026 - int(parts[0]) if parts.size() >= 3 else 0


# --- 物件编辑 -----------------------------------------------------------
func add_item(type_id: String, at: String, owner: String = "") -> String:
	if not item_types.has(type_id) or not buildings.has(at):
		return ""
	var d: Dictionary = item_types[type_id]
	_seq.i += 1
	var id := "%s_%03d" % [type_id, int(_seq.i)]
	items[id] = {"type": type_id, "at": at, "owner": owner,
		"stock": int(d.get("stock", 1)), "price": float(d.get("price", 0.0)),
		"persist_empty": false}
	errors = validate()
	changed.emit()
	return id


func update_item(id: String, patch: Dictionary) -> void:
	if not items.has(id):
		return
	for k in patch:
		items[id][k] = patch[k]
	changed.emit()


func remove_item(id: String) -> void:
	items.erase(id)
	changed.emit()


func items_at(bid: String) -> Array:
	var out: Array = []
	for iid in items:
		if String(items[iid].get("at", "")) == bid:
			out.append(iid)
	return out


func npcs_at(bid: String) -> Array:
	var out: Array = []
	for pid in npcs:
		if String(npcs[pid].get("home", "")) == bid:
			out.append(pid)
	return out


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
	# 规则: 必须先画路再摆放建筑
	if not buildings.is_empty() and edges.is_empty():
		out.append({"level": "error", "msg": "先画路再摆放建筑",
			"kind": "building", "id": buildings.keys()[0]})
	# 进出口接入: 主门应落在某条路的【路沿】(中心线距离 ≈ 半宽)上
	for id in buildings:
		var ws: Array = door_worlds(buildings[id])
		if ws.is_empty():
			continue
		var aligned := false
		for dd in ws:
			var r := nearest_road(dd["pos"])
			if r.is_empty():
				continue
			if absf(float(r["dist"]) - float(r["width"]) * 0.5) <= 0.6:
				aligned = true
				break
		if not aligned:
			out.append({"level": "warn", "msg": "进出口未对齐道路",
				"kind": "building", "id": id})
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
	# 已知类型 → 按 doors 定义重算进出口世界点(不信任导入的旧值)
	for id in buildings:
		if building_types.has(String(buildings[id]["type"])):
			_sync_doors(buildings[id])
	errors = validate()
	changed.emit()


func _recount() -> void:
	var mx := {"n": 0, "e": 0, "b": 0, "i": 0}
	for id in nodes:
		mx["n"] = maxi(mx["n"], int(String(id).get_slice("_", 1)))
	for id in edges:
		mx["e"] = maxi(mx["e"], int(String(id).get_slice("_", 1)))
	for id in buildings:
		mx["b"] = maxi(mx["b"], int(String(id).get_slice("_", 1)))
	for id in items:
		var parts := String(id).split("_")
		mx["i"] = maxi(mx["i"], int(parts[parts.size() - 1]))
	_seq = mx


## 导出为后端可加载的场景(config/scenes 格式) + 原始路网。
## 建筑按 OBB 的外接矩形写成显式 x/y/w/h, 后端 build_locations 会原样保留。
func to_scene_dict(scene_name: String = "editor_scene") -> Dictionary:
	var locs := {}
	for bid in buildings:
		var b: Dictionary = buildings[bid]
		var cs: Array = obb_corners(b)
		var minp: Vector2 = cs[0]
		var maxp: Vector2 = cs[0]
		for p in cs:
			minp = Vector2(minf(minp.x, p.x), minf(minp.y, p.y))
			maxp = Vector2(maxf(maxp.x, p.x), maxf(maxp.y, p.y))
		locs[bid] = {"type": String(b["type"]),
			"name": building_name(bid),
			"x": snappedf(minp.x, 0.01), "y": snappedf(minp.y, 0.01),
			"w": snappedf(maxp.x - minp.x, 0.01),
			"h": snappedf(maxp.y - minp.y, 0.01)}
	var ents: Array = []
	for iid in items:
		var it: Dictionary = items[iid]
		var e := {"id": iid, "type": String(it["type"]), "at": String(it.get("at", ""))}
		var own := String(it.get("owner", ""))
		if own != "":
			e["owner"] = own
		var st := int(it.get("stock", 1))
		if st != 1:
			e["stock"] = st
		var pr := float(it.get("price", 0.0))
		if pr > 0.0:
			e["price"] = pr
		if bool(it.get("persist_empty", false)):
			e["persist_empty"] = true
		ents.append(e)
	var ppl: Array = []
	for pid in npcs:
		var p: Dictionary = npcs[pid]
		ppl.append({"id": pid, "name": String(p.get("name", pid)),
			"gender": String(p.get("gender", "")),
			"birthday": String(p.get("birthday", "")),
			"role": String(p.get("role", "")),
			"money": float(p.get("money", 100.0)),
			"home": String(p.get("home", "")),
			"personality": p.get("personality", {}),
			"init": p.get("init", {}),
			"traits": p.get("traits", {}),
			"tell_bias": float(p.get("tell_bias", 1.0))})
	# 旅行成本: 建筑中心直线距离 / 10 粗估(缺省 20; 无路网时的降级)
	var pairs := {}
	var bids: Array = buildings.keys()
	bids.sort()
	for i in range(bids.size()):
		for j in range(i + 1, bids.size()):
			var a: Vector2 = buildings[bids[i]]["center"]
			var b2: Vector2 = buildings[bids[j]]["center"]
			pairs["%s|%s" % [bids[i], bids[j]]] = maxi(1, int(a.distance_to(b2) / 10.0))
	return {"scene": scene_name, "display_name": scene_name,
		"canvas": {"w": bounds.size.x, "h": bounds.size.y},
		"locations": locs, "travel": {"default": 20, "pairs": pairs},
		"entities": ents, "pulses": [], "plans": {}, "npcs": ppl,
		"map": to_dict()}


func save_scene(path: String, scene_name: String = "editor_scene") -> bool:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		return false
	f.store_string(JSON.stringify(to_scene_dict(scene_name), "  "))
	f.close()
	return true


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
