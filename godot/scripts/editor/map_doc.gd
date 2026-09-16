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
const MAX_FLOORS := 12            # 楼层上限(编辑器 UI 与导出都用它)

# 进出口(资产逻辑定义): 观察器/后端 config/buildings/*.json 的 doors 段。
# 缺省南面; 编辑器在摆放时按主门自动朝向最近道路。
const DOOR_DEFAULT := {"side": "south", "offset": 0.0}
const ROAD_SNAP_M := 3.0          # 画路点击吸附到既有道路中心线的距离(米)
const DOOR_SNAP_M := 4.0          # 画路点击吸附到建筑门的距离(米)

var bounds := Rect2(0.0, 0.0, 800.0, 600.0)
var grid_size := 1.0
var grid_snap := true             # 栅格捕获开关
var net_snap := true              # 路网吸附开关(既有节点 / 建筑门 / 道路中心线)
var scene_name := "editor_scene"   # 导入/导出的场景名(导出默认用它)
var scene_display := ""            # 场景展示名(导入时记住, 不在文件对话框里丢)
var nodes: Dictionary = {}        # id -> {xy:Vector2, kind:String}
var edges: Dictionary = {}        # id -> {a,b,class,width,speed,oneway,geom:Array[Vector2]}
var buildings: Dictionary = {}    # id -> {type,center:Vector2,size:Vector2,rot:float,doors:Array[Vector2],floors:int}
var npcs: Dictionary = {}         # id -> {name,gender,birthday,role,money,home,
								  #        personality,init,traits,tell_bias,memory}
var companies: Dictionary = {}    # cid -> {id,name,shops:[bid],cash,open,close,
								  #          wage_per_hour,hiring_slots,restock_to,staff:[npc]}
# memory: item_id -> {located/afford/value/price/stock/owner/believe}
# = 【这个人额外的记忆】。后端 scenarios 的 spec["memory"] 直接读它。
# 与 knowledge 段的区别: knowledge 是【批量】(所有人 / 一整户),
# memory 是【点名给某一个人】—— P8: 只写他的知识, 不碰世界真值。
var items: Dictionary = {}        # id -> {type,at,owner,stock,price,persist_empty}
var building_types: Dictionary = {}
var name_pool: Dictionary = {}    # config/names/names.json
var item_types: Dictionary = {}    # config/items/*.json
var errors: Array = []             # validate() 结果: {level,msg,kind,id}
# 场景级【初始认知】: [{who, from, items, believe}] —— 一次让一批人知道某处的货。
# 导出到 scene JSON 的 knowledge 段; 后端 scenarios._seed_knowledge 读它。
var knowledge: Array = []
var cur_floor := 1                 # 当前编辑楼层(建筑详情页; 地图角标也读它)
var cur_floor_bid := ""            # cur_floor 所属建筑

# 人物可选角色码(与后端 config/scenes 一致)。
# 注意: 随机生成的人一律 role="" (无) —— 只有手动指定才会带上角色。
const ROLES := ["worker", "student", "engineer", "teacher", "doctor",
	"shopkeeper", "unemployed", "retired"]


## 角色下拉的选项: 第 0 项 ""(= 无), 其后是 ROLES。
func role_options() -> Array:
	var out: Array = [""]
	out.append_array(ROLES)
	return out

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
	return BuildingGeom.door_local(
		b["size"], String(d.get("side", "south")), float(d.get("offset", 0.0)))


## 建筑所有门的【世界】门点+法线(导出/渲染共用)。
func door_worlds(b: Dictionary) -> Array:
	var out: Array = []
	var rot := float(b.get("rot", 0.0))
	for d in _type_doors(String(b["type"])):
		var ld: Dictionary = door_local(b, d)
		out.append({
			"pos": (b["center"] as Vector2) + BuildingGeom.rotate_vec(ld["pos"], rot),
			"normal": BuildingGeom.rotate_vec(ld["normal"], rot),
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
	var rvec := BuildingGeom.rotate_vec(ld["pos"], float(b["rot"]))
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


## 场景默认目录(编辑器导入/导出只认场景文件)。
func scenes_dir() -> String:
	return _config_root().path_join("config").path_join("scenes")


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
	companies.clear()
	items.clear()
	knowledge.clear()
	errors.clear()
	_seq = {"n": 0, "e": 0, "b": 0, "i": 0}
	changed.emit()

## 默认占地尺寸: 由【单层】容量算(1 capacity ≈ 20 m²)。
## 加楼层不改占地 → 密度上升而不是城市铺开, 这正是多层的用途。
func default_size_for(type_id: String) -> Vector2:
	var t: Dictionary = building_types.get(type_id, {})
	var cap := float(t.get("capacity", 6))
	var asp := float(t.get("aspect", 1.0))
	var area := cap * AREA_PER_CAPACITY
	return Vector2(sqrt(area * asp), sqrt(area / asp))


func snap(p: Vector2) -> Vector2:
	if not grid_snap or grid_size <= 0.0:
		return p
	return p.snapped(Vector2(grid_size, grid_size))


## 最近的建筑门点: {pos, building, index, dist}; 无建筑返回 {}。
func nearest_door(p: Vector2) -> Dictionary:
	var best: Dictionary = {}
	var bd := INF
	for bid in buildings:
		var ws: Array = door_worlds(buildings[bid])
		for i in range(ws.size()):
			var d := p.distance_to(ws[i]["pos"] as Vector2)
			if d < bd:
				bd = d
				best = {"pos": ws[i]["pos"], "building": bid, "index": i, "dist": d}
	return best


## 统一吸附解析(画路 / 预览共用)。优先级:
##   既有节点 > 建筑门 > 道路中心线 > 栅格/原始
## node_hit 由视图用屏幕像素半径算出("" = 未命中节点)。
## 返回 {kind, point, id, building, door_index, edge}。
func resolve_snap(world_pos: Vector2, node_hit: String = "") -> Dictionary:
	if net_snap and node_hit != "" and nodes.has(node_hit):
		return {"kind": "node", "point": nodes[node_hit]["xy"], "id": node_hit,
			"building": String(nodes[node_hit].get("door_of", "")),
			"door_index": int(nodes[node_hit].get("door_index", -1)), "edge": ""}
	if net_snap:
		var dw := nearest_door(world_pos)
		if not dw.is_empty() and float(dw["dist"]) <= DOOR_SNAP_M:
			return {"kind": "door", "point": dw["pos"], "id": "",
				"building": String(dw["building"]), "door_index": int(dw["index"]),
				"edge": ""}
		var rd := nearest_road(world_pos)
		if not rd.is_empty() and float(rd["dist"]) <= ROAD_SNAP_M:
			return {"kind": "road", "point": rd["point"], "id": "",
				"building": "", "door_index": -1, "edge": String(rd["edge"])}
	return {"kind": "free", "point": snap(world_pos), "id": "",
		"building": "", "door_index": -1, "edge": ""}


## 把建筑的第 index 个门变成路网节点(已存在则复用)。
## 带 door_of 的节点会跟随建筑(反之移动节点也会带着建筑走, 见 move_node)。
func node_at_door(bid: String, door_index: int) -> String:
	for nid in nodes:
		if String(nodes[nid].get("door_of", "")) == bid \
				and int(nodes[nid].get("door_index", 0)) == door_index:
			return nid
	if not buildings.has(bid):
		return ""
	var ws: Array = door_worlds(buildings[bid])
	if door_index < 0 or door_index >= ws.size():
		return ""
	_seq.n += 1
	var nid := "n_%03d" % int(_seq.n)
	nodes[nid] = {"xy": ws[door_index]["pos"], "kind": "junction",
		"door_of": bid, "door_index": door_index}
	return nid


## 原则: 没有边的节点不存在 → 清掉孤立节点。返回清除数量。
func prune_orphan_nodes() -> int:
	var used := {}
	for eid in edges:
		var e: Dictionary = edges[eid]
		used[String(e["a"])] = true
		used[String(e["b"])] = true
	var n := 0
	for nid in nodes.keys():
		if not used.has(nid):
			nodes.erase(nid)
			n += 1
	return n


## 摆放建筑(规则: 必须先有路; 自动把主门对齐到最近道路)。无路返回 ""。
func add_building(type_id: String, world_pos: Vector2) -> String:
	if edges.is_empty():
		return ""
	_seq.b += 1
	var id := "bld_%03d" % int(_seq.b)
	buildings[id] = {"type": type_id, "center": world_pos,
		"size": default_size_for(type_id), "rot": 0.0, "doors": [], "floors": 1}
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
	_push_building_to_nodes(id)
	errors = validate()
	changed.emit()


## 把已放置建筑重新对齐到最近道路。
func align_building(id: String) -> bool:
	if not buildings.has(id):
		return false
	var b: Dictionary = buildings[id]
	if not align_to_road(b, b["center"]):
		return false
	_push_building_to_nodes(id)
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


## 在道路中心线上打断该边, 插入 T/十字节点(附近已有节点则复用)。
func split_road_at(edge_id: String, point: Vector2) -> String:
	for nid in nodes:
		if (nodes[nid]["xy"] as Vector2).distance_to(point) < 0.5:
			return nid
	return _split_edge(edge_id, point)


## 画路落点: 统一吸附 → 复用节点 / 建门节点 / 打断道路 / 新建节点。
func add_road_node(world_pos: Vector2, node_hit: String = "") -> String:
	var s := resolve_snap(world_pos, node_hit)
	match String(s["kind"]):
		"node":
			return String(s["id"])
		"door":
			return node_at_door(String(s["building"]), int(s["door_index"]))
		"road":
			return split_road_at(String(s["edge"]), s["point"] as Vector2)
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


## 相邻边的端点几何跟随(仅当线段是直连两点, 折线则只改对应端点)。
func _follow_edges(nid: String) -> void:
	for eid in edges:
		var e: Dictionary = edges[eid]
		var is_a: bool = e["a"] == nid
		var is_b: bool = e["b"] == nid
		if not (is_a or is_b):
			continue
		var g: Array = e["geom"]
		if g.is_empty() or g.size() == 2:
			e["geom"] = [nodes[e["a"]]["xy"], nodes[e["b"]]["xy"]]
		elif is_a:
			g[0] = nodes[nid]["xy"]
		else:
			g[g.size() - 1] = nodes[nid]["xy"]


## 门节点 → 建筑: 平移建筑(不改朝向), 使它的门点落在这个节点上。
func _pull_building_to_node(nid: String) -> void:
	var bid := String(nodes[nid].get("door_of", ""))
	if bid == "" or not buildings.has(bid):
		return
	var b: Dictionary = buildings[bid]
	var idx := int(nodes[nid].get("door_index", 0))
	var ws: Array = door_worlds(b)
	if idx < 0 or idx >= ws.size():
		return
	b["center"] = (b["center"] as Vector2) \
		+ ((nodes[nid]["xy"] as Vector2) - (ws[idx]["pos"] as Vector2))
	_sync_doors(b)


## 建筑 → 门节点: 绑定的节点贴到建筑门上(建筑被移动/转向/换类型后调)。
func _push_building_to_nodes(bid: String) -> void:
	if not buildings.has(bid):
		return
	var ws: Array = door_worlds(buildings[bid])
	for nid in nodes:
		if String(nodes[nid].get("door_of", "")) != bid:
			continue
		var idx := int(nodes[nid].get("door_index", 0))
		if idx < 0 or idx >= ws.size():
			continue
		nodes[nid]["xy"] = ws[idx]["pos"]
		_follow_edges(nid)


## 移动节点: 相连的边跟随; 若是建筑门节点, 建筑也跟着平移。
func move_node(id: String, world_pos: Vector2) -> void:
	if not nodes.has(id):
		return
	nodes[id]["xy"] = snap(world_pos)
	_follow_edges(id)
	_pull_building_to_node(id)
	errors = validate()
	changed.emit()


func set_building_type(id: String, type_id: String) -> void:
	if not buildings.has(id):
		return
	buildings[id]["type"] = type_id
	buildings[id]["size"] = default_size_for(type_id)
	align_to_road(buildings[id], buildings[id]["center"])
	_sync_doors(buildings[id])
	_push_building_to_nodes(id)
	errors = validate()
	changed.emit()


func remove_node(id: String) -> void:
	nodes.erase(id)
	for eid in edges.keys():
		var e: Dictionary = edges[eid]
		if e["a"] == id or e["b"] == id:
			edges.erase(eid)
	prune_orphan_nodes()
	errors = validate()
	changed.emit()


func remove_edge(id: String) -> void:
	edges.erase(id)
	prune_orphan_nodes()          # 原则: 没有边的节点不存在
	errors = validate()
	changed.emit()


func remove_building(id: String) -> void:
	var units := unit_ids(id)      # 必须在 erase 之前算(unit_ids 依赖 buildings)
	buildings.erase(id)
	# 解绑门节点(节点本身留着, 只是不再是"某建筑的门")
	for nid in nodes:
		if String(nodes[nid].get("door_of", "")) == id:
			nodes[nid].erase("door_of")
			nodes[nid].erase("door_index")
	# 解除引用: 人物住所 / 物件所在建筑(含楼层单元)
	for iid in items:
		if units.has(String(items[iid].get("at", ""))):
			items[iid]["at"] = ""
	for pid in npcs:
		if units.has(String(npcs[pid].get("home", ""))):
			npcs[pid]["home"] = ""
	prune_orphan_nodes()
	errors = validate()
	changed.emit()


## 这个名字是不是【自动编号】(店铺1号 / 小屋2号 …)?
##
## 导出时会把自动编号【写进 name】(后端没有编号能力, 总得给它一个显示名),
## 于是在重新导入时就容易被当成"作者起的名字" —— 一旦如此, 自动编号就不再数它,
## 下一栋同类建筑会撞上同一个号(实测: 载入后新增商铺 → 三个“店铺1号”)。
func _is_auto_name(name: String, type_id: String) -> bool:
	var base := type_display(type_id)
	if base == "" or not name.begins_with(base):
		return false
	var tail := name.substr(base.length())
	if not tail.ends_with("号") or tail.length() < 2:
		return false
	return tail.substr(0, tail.length() - 1).is_valid_int()


## 作者起过名字吗? 三种都算“没起”: 空 / 等于类型默认名(小屋) / 是自动编号(小屋1号)。
func has_custom_name(bid: String) -> bool:
	if not buildings.has(bid):
		return false
	var b: Dictionary = buildings[bid]
	var nm := String(b.get("name", ""))
	var tp := String(b.get("type", ""))
	return nm != "" and nm != type_display(tp) and not _is_auto_name(nm, tp)


## 默认展示名 = 【类型名 + 同类型序号】号 —— 保证不重叠。
##
## 为什么不直接用类型名: 同类型十栋楼全叫“小屋”, 地图上分不清谁是谁,
## 点进去也对不上号(docs/naming.md §1“展示名与编号解耦”)。
## 序号只数【没起名字的】同类建筑(按 id 排序) → 1 号 2 号 连号, 没有空洞。
func default_building_name(bid: String) -> String:
	if not buildings.has(bid):
		return bid
	var b: Dictionary = buildings[bid]
	var tp := String(b.get("type", ""))
	var same: Array = []
	for k in buildings:
		if String(buildings[k].get("type", "")) == tp 				and not has_custom_name(String(k)):
			same.append(String(k))
	same.sort()
	var idx := same.find(bid) + 1
	if idx <= 0:
		idx = 1
	return "%s%d号" % [type_display(tp), idx]


func building_name(bid: String) -> String:
	if not buildings.has(bid):
		return bid
	if has_custom_name(bid):
		return String(buildings[bid].get("name", ""))
	return default_building_name(bid)


## 把“等于类型默认名的名字”清掉 → 回到自动编号。
## 老场景(编辑器早期把默认名写进了 name) 用这个一键修好。返回清掉几条。
func dedupe_building_names() -> int:
	var n := 0
	for bid in buildings:
		if not has_custom_name(String(bid)) and String(buildings[bid].get("name", "")) != "":
			buildings[bid]["name"] = ""      # 含"自动编号被烤进 name"的老场景
			n += 1
	if n > 0:
		errors = validate()
		changed.emit()
	return n


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
		"role": "",      # 新生成的居民一律【无角色】—— 岗位要靠后续发展获得
		"money": float(r.randi_range(0, 500)),
		"home": "",
		"personality": {
			"hunger": snappedf(r.randf_range(0.8, 1.3), 0.1),
			"energy": snappedf(r.randf_range(0.8, 1.3), 0.1),
		},
		"init": {}, "traits": {}, "tell_bias": 1.0,
		"memory": {},
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


# --- 某个人的额外记忆(逐条增删改) --------------------------------------

## 这个人身上的额外记忆: item_id -> {…}。
func memory_of(pid: String) -> Dictionary:
	var n: Dictionary = npcs.get(pid, {})
	if not n.has("memory"):
		n["memory"] = {}
	return n["memory"] as Dictionary


## 从场景里的一个物件推出【默认记忆字段】—— 免得让人手填一堆。
## 语义: “他见过/听说过这个东西” → 它是什么、能解什么、多少钱、还剩几件。
func memory_defaults(iid: String) -> Dictionary:
	var it: Dictionary = items.get(iid, {})
	var d: Dictionary = item_types.get(String(it.get("type", "")), {})
	var aff: Dictionary = d.get("affordances", {}) as Dictionary
	var out := {"located": String(it.get("at", "")),
		"price": float(it.get("price", 0.0)),
		"stock": int(it.get("stock", 1))}
	var own := String(it.get("owner", ""))
	if own != "":
		out["owner"] = own
	for k in aff:
		out["afford"] = String(k)
		out["value"] = float(aff[k])
		break
	return out


## 加一条(已存在则【覆盖】= 修改)。believe = 他有多信这条。
func add_memory(pid: String, iid: String, believe: float,
		extra: Dictionary = {}) -> void:
	if not npcs.has(pid) or iid == "":
		return
	var rec := memory_defaults(iid)
	if String(rec.get("located", "")) == "":
		return                  # 没地点 → 他走不到, 写进去是死记忆
	for k in extra:
		rec[k] = extra[k]
	rec["believe"] = clampf(believe, 0.0, 1.0)
	memory_of(pid)[iid] = rec
	errors = validate()
	changed.emit()


func remove_memory(pid: String, iid: String) -> void:
	var m := memory_of(pid)
	if m.has(iid):
		m.erase(iid)
		errors = validate()
		changed.emit()


func clear_memory(pid: String) -> void:
	memory_of(pid).clear()
	errors = validate()
	changed.emit()


## 一行记忆的中文描述(面板显示用)。
func memory_label(iid: String, rec: Dictionary) -> String:
	var nm := item_display(String(items.get(iid, {}).get("type", "")))
	var where := String(rec.get("located", ""))
	var loc_txt := unit_display(where) if where != "" else "没地点(用不上)"
	var bits: Array = ["%s · %s" % [nm, loc_txt]]
	if float(rec.get("price", 0.0)) > 0.0:
		bits.append("¥%d" % int(rec.get("price", 0.0)))
	var aff := String(rec.get("afford", ""))
	if aff != "":
		bits.append("%s +%.2f" % [aff, float(rec.get("value", 0.0))])
	var st := int(rec.get("stock", -1))
	if st >= 0:
		bits.append("存 %d" % st)
	bits.append("信 %.2f" % float(rec.get("believe", 1.0)))
	return " ".join(bits)


func npc_display(id: String) -> String:
	var n: Dictionary = npcs.get(id, {})
	return "%s (%s)" % [String(n.get("name", id)), id]


func age_of(n: Dictionary) -> int:
	var parts := String(n.get("birthday", "")).split("-")
	return 2026 - int(parts[0]) if parts.size() >= 3 else 0


# --- 物件编辑 -----------------------------------------------------------
func add_item(type_id: String, at: String, owner: String = "") -> String:
	if not item_types.has(type_id) or not is_valid_at(at):
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
	# 指向它的记忆变成悬空引用 → 一起清掉(否则后端拿不到 afford 就永远用不上)
	for pid in npcs:
		(memory_of(pid) as Dictionary).erase(id)
	changed.emit()


## ---- 公司(经营) ----------------------------------------------------------
## 作者直选“这栋商铺归哪家公司 + 谁在这上班”; 导出到场景 companies 段。
func company_for_shop(bid: String) -> Dictionary:
	for cid in companies:
		if (companies[cid].get("shops", []) as Array).has(bid):
			return companies[cid]
	return {}


func set_company(spec: Dictionary) -> String:
	var cid := String(spec.get("id", ""))
	if cid == "":
		var shops: Array = spec.get("shops", [])
		cid = "org_%s" % (String(shops[0]) if not shops.is_empty() else "x")
		spec["id"] = cid
	companies[cid] = spec
	changed.emit()
	return cid


func remove_company(cid: String) -> void:
	companies.erase(cid)
	changed.emit()


## 这个物件类型是不是【装修件】(fixture): 销售前台/货架/马桶…
func is_fixture(type_id: String) -> bool:
	var d: Dictionary = item_types.get(type_id, {})
	return (d.get("tags", []) as Array).has("fixture")


func items_at(bid: String) -> Array:
	var units := unit_ids(bid)
	var out: Array = []
	for iid in items:
		if units.has(String(items[iid].get("at", ""))):
			out.append(iid)
	return out


func npcs_at(bid: String) -> Array:
	var units := unit_ids(bid)
	var out: Array = []
	for pid in npcs:
		if units.has(String(npcs[pid].get("home", ""))):
			out.append(pid)
	return out


# --- 楼层 / 住户单元 -----------------------------------------------------
# 楼层是【编辑器编写概念】: 导出时 floors>1 的建筑会额外生成
# bld_007_f1..fN 这些【子地点】(带 part_of), 后端只当普通地点看。
# floors<=1 时单元就是建筑本身 id → 单层场景导出结果完全不变。

## 该建筑的住户单元 id 列表。floors<=1 → [bid]; 否则 [bid_f1 .. bid_fN]。
func unit_ids(bid: String) -> Array:
	if not buildings.has(bid):
		return []
	var n := int(buildings[bid].get("floors", 1))
	if n <= 1:
		return [bid]
	var out: Array = []
	for i in range(1, n + 1):
		out.append("%s_f%d" % [bid, i])
	return out


## 第 floor 层(1..N)对应的单元 id。floors<=1 时恒为 bid。
func unit_of(bid: String, floor: int) -> String:
	if not buildings.has(bid):
		return ""
	var n := int(buildings[bid].get("floors", 1))
	if n <= 1:
		return bid
	return "%s_f%d" % [bid, clampi(floor, 1, n)]


## at(建筑本体 或 楼层单元) → 所属建筑 id; 都不属于则 ""。
func building_of(at: String) -> String:
	if buildings.has(at):
		return at
	for bid in buildings:
		if unit_ids(bid).has(at):
			return bid
	return ""


## 这个 at 值是不是合法的地点(建筑本体 或 某建筑的楼层单元)。
func is_valid_at(at: String) -> bool:
	return building_of(at) != ""


## 地点显示名: 楼层单元 → "建筑名 · N层"; 否则建筑名。
func unit_display(at: String) -> String:
	if at == "":
		return "未放置"          # 孤儿物件(不属于任何地点)
	if buildings.has(at):
		return building_name(at)
	var bid := building_of(at)
	if bid != "":
		var units := unit_ids(bid)
		var k := units.find(at)
		if k >= 0:
			return "%s · %d层" % [building_name(bid), k + 1]
	return at


func set_floors(bid: String, n: int) -> void:
	if not buildings.has(bid):
		return
	var v := clampi(n, 1, MAX_FLOORS)
	var old := int(buildings[bid].get("floors", 1))
	if old == v:
		return                      # 无变化不 emit: 避免与 SpinBox 重建形成无限循环
	buildings[bid]["floors"] = v
	if v < old:
		# 减层: 楼上的人与物指向的单元没了 → 先清引用, 不留幽灵住所
		purge_invalid_refs()
	errors = validate()
	changed.emit()


## 所有合法地点(建筑本体 + 楼层单元)的集合, 给批量校验/清理用(避免逐条 O(N×B))。
func _valid_sites() -> Dictionary:
	var s := {}
	for b in buildings:
		s[String(b)] = true
		for u in unit_ids(b):
			s[String(u)] = true
	return s


## 清掉指向【不存在地点】的引用(减层遗留 / 导入旧坏数据 / 删楼遗漏)。
## 返回 {npcs, items}: 被解除住所的人数 / 被删掉的物件数。
func purge_invalid_refs() -> Dictionary:
	var sites := _valid_sites()
	var n_npc := 0
	var n_item := 0
	for pid in npcs:
		var h := String(npcs[pid].get("home", ""))
		if h != "" and not sites.has(h):
			npcs[pid]["home"] = ""
			n_npc += 1
	var kill: Array = []
	for iid in items:
		var at := String(items[iid].get("at", ""))
		if not sites.has(at):        # at == "" 的孤儿物件也一起收掉(没有这个地点)
			kill.append(iid)
	for iid in kill:
		items.erase(iid)
		n_item += 1
	# 悬空的记忆条目也一起清(指向已删物件 → 后端起不来 / 永远用不上)
	for pid in npcs:
		for mid in (memory_of(pid) as Dictionary).keys():
			if not items.has(String(mid)):
				(memory_of(pid) as Dictionary).erase(mid)
	if n_npc > 0 or n_item > 0:
		errors = validate()
		changed.emit()
	return {"npcs": n_npc, "items": n_item}


## 每层能住几人 = 建筑【单层】容量(类型 capacity 本身)。
## 多层是【垂直堆叠】: 总容量 = 单层容量 × 楼层数, 占地不变(密度而不是铺开)。
## 所以 home_small(3) 盖 3 层 = 每层 3 人 / 共 9 人。
## 这栋楼【是住宅】吗? —— 看类型库的 kind(数据驱动, 不写死 id)。
## ★ 为什么必须有这个: 办公楼 capacity=200, 但那 200 是【工位】不是床位。
##   以前 add_resident 不看 kind → 点办公楼也能塞“住户”(塞到 200 个),
##   一个场景里凭空多出一百多号人就是这么来的。
func is_home(bid: String) -> bool:
	var tp := String(buildings.get(bid, {}).get("type", ""))
	return String(building_types.get(tp, {}).get("kind", "")) == "home"


func unit_capacity(bid: String) -> int:
	var t: Dictionary = building_types.get(String(buildings.get(bid, {}).get("type", "")), {})
	return maxi(1, int(t.get("capacity", 3)))


## 整栋总容量 = 单层容量 × 楼层数。
func total_capacity(bid: String) -> int:
	return unit_capacity(bid) * maxi(1, unit_ids(bid).size())


# --- 初始认知(场景级 knowledge) ----------------------------------------
## 【有东西在卖的楼】= 至少一个实体的 price>0。数据驱动, 不看 kind。
func shops() -> Array:
	var out: Array = []
	for bid in buildings:
		var found := false
		for u in unit_ids(bid):
			for iid in items_at_unit(String(u)):
				if float(items[iid].get("price", 0.0)) > 0.0:
					found = true
					break
			if found:
				break
		if found:
			out.append(String(bid))
	out.sort()
	return out


## 让一批人“知道”某处的货。
##
## 作用范围(first 参数 bid)是【当前编辑的那一层】(target_unit):
##   · 该层住着人(住宅) → who="unit" —— 只让【这一家】知道;
##     这时 from 应该是【一家卖东西的店】(由 from_bid 指定),
##     语义 = “告诉这一家: 那家店在卖吃的”。
##   · 该层没人(商铺/公共) → who="all", from = 它自己 —— 相当于“打广告”。
func add_knowledge(bid: String, believe: float, from_bid: String = "") -> void:
	if not buildings.has(bid):
		return
	var unit := target_unit(bid)
	var has_people := not npcs_at_unit(unit).is_empty()
	var src := String(from_bid) if from_bid != "" else unit
	if not buildings.has(src):
		src = unit
	knowledge.append({
		"who": "unit" if has_people else "all",
		"unit": unit if has_people else "",
		"from": src, "items": [],
		"believe": clampf(believe, 0.05, 1.0)})
	errors = validate()
	changed.emit()


func remove_knowledge(i: int) -> void:
	if i < 0 or i >= knowledge.size():
		return
	knowledge.remove_at(i)
	errors = validate()
	changed.emit()


## 与该建筑相关的 knowledge 规则下标(from 指向本楼或它的某个楼层单元)。
func knowledge_at(bid: String) -> Array:
	var out: Array = []
	for i in knowledge.size():
		var f := String((knowledge[i] as Dictionary).get("from", ""))
		if f == bid or (f.begins_with(bid + "_f") and buildings.has(bid)):
			out.append(i)
	return out


## 规则的人类可读说明: “谁” + “关于哪里的货”。
func knowledge_label(rule: Dictionary) -> String:
	var who := String(rule.get("who", "all"))
	var src := String(rule.get("from", ""))
	var who_txt := "所有人"
	if who == "unit":
		var u := String(rule.get("unit", ""))
		who_txt = "这一家人(%s)" % (unit_display(u) if u != "" else "?")
	return "%s ← 知道 %s 的货 · %.2f" % [who_txt, unit_display(src),
		float(rule.get("believe", 0.8))]


## 没有住所(或住所已不存在)的人。**编辑器以前只在"建筑的住户列表"里显示人**
## → 这些人一个都看不到(实测一个场景 114 人里 108 个是这种), 于是
## “场景里没这么多人”的错觉就来了。给他们一个面板。
func homeless_npcs() -> Array:
	var sites := _valid_sites()
	var out: Array = []
	for pid in npcs:
		var h := String(npcs[pid].get("home", ""))
		if h == "" or not sites.has(h):
			out.append(String(pid))
	out.sort()
	return out


## 把所有空闲床位(每层容量 − 现有住户)分给无住所的人。返回 {assigned, left}。
func assign_homeless() -> Dictionary:
	var free_slots: Array = []
	var bids: Array = buildings.keys()
	bids.sort()
	for bid in bids:
		if not is_home(String(bid)):
			continue                 # 办公楼/商铺的 capacity 不是床位
		for unit in unit_ids(String(bid)):
			var cap := unit_capacity(String(bid))
			var used := npcs_at_unit(String(unit)).size()
			for i in range(maxi(0, cap - used)):
				free_slots.append(String(unit))
	var assigned := 0
	for pid in homeless_npcs():
		if free_slots.is_empty():
			break
		npcs[pid]["home"] = free_slots.pop_front()
		assigned += 1
	if assigned > 0:
		errors = validate()
		changed.emit()
	return {"assigned": assigned, "left": homeless_npcs().size()}


## 删掉所有无住所的人(和删单人一样, 顺手清掉他名下的物件归属)。
func remove_homeless() -> int:
	var kill := homeless_npcs()
	for pid in kill:
		remove_npc(String(pid))
	return kill.size()


func npcs_at_unit(unit: String) -> Array:
	var out: Array = []
	for pid in npcs:
		if String(npcs[pid].get("home", "")) == unit:
			out.append(pid)
	return out


func items_at_unit(unit: String) -> Array:
	var out: Array = []
	for iid in items:
		if String(items[iid].get("at", "")) == unit:
			out.append(iid)
	return out


## 只夹取当前楼层, 不 emit(供检查器构建时调用)。换建筑 → 回到 1 层。
func clamp_cur_floor(bid: String) -> void:
	if not buildings.has(bid):
		return
	if bid != cur_floor_bid:
		cur_floor_bid = bid
		cur_floor = 1
	cur_floor = clampi(cur_floor, 1, maxi(1, unit_ids(bid).size()))


## 切换当前编辑楼层(越界夹取)。变了才 emit changed, 避免与控件重建形成循环。
func set_cur_floor(bid: String, floor: int) -> void:
	if not buildings.has(bid):
		return
	var f := clampi(floor, 1, maxi(1, unit_ids(bid).size()))
	if bid == cur_floor_bid and f == cur_floor:
		return
	cur_floor_bid = bid
	cur_floor = f
	changed.emit()


## 点某建筑时“往哪一层放东西”的目标单元:
## 正是当前编辑的建筑 → 当前层; 其它建筑 → 1 层。
func target_unit(bid: String) -> String:
	return unit_of(bid, cur_floor if bid == cur_floor_bid else 1)


## 往建筑的【当前编辑层】加 1 个随机居民(非当前建筑则用 1 层)。
## 到容量上限不加。返回 {ok, unit, pid, reason} —— 调用方只需读 ok/pid/reason。
func add_resident(bid: String) -> Dictionary:
	if not buildings.has(bid):
		return {"ok": false, "reason": "无此建筑"}
	if not is_home(bid):
		return {"ok": false,
			"reason": "这里不是住宅 —— 办公楼/商铺的 capacity 是工位/客流, 不住人"}
	var unit := target_unit(bid)
	var cap := unit_capacity(bid)
	if npcs_at_unit(unit).size() >= cap:
		return {"ok": false, "unit": unit,
			"reason": "已住满 (%d 人上限) —— 加楼层或先删人" % cap}
	var pid := add_npc(unit)
	return {"ok": pid != "", "unit": unit, "pid": pid, "reason": ""}


## 一键: 所有住宅建筑的每个住户单元补满随机居民(到每层容量)。
## 返回 {homes, units, added}。
func fill_residents() -> Dictionary:
	var homes := 0
	var units_n := 0
	var added := 0
	for bid in buildings:
		var kind := String(building_types.get(String(buildings[bid]["type"]), {}).get("kind", ""))
		if kind != "home":
			continue
		homes += 1
		var cap := unit_capacity(bid)
		for u in unit_ids(bid):
			units_n += 1
			var have := npcs_at_unit(String(u)).size()
			for _i in range(have, cap):
				if add_npc(String(u)) != "":
					added += 1
	return {"homes": homes, "units": units_n, "added": added}


## 把 bid 第 floor 层的物件复制到该栋其它楼层(不复制整层 NPC)。
## 复制品的 owner 改为目标层的户主(若有), 否则置空 —— 否则 2 楼的床会归 1 楼的人。
## 返回复制条数。
func copy_floor_items(bid: String, floor: int) -> int:
	var units := unit_ids(bid)
	if units.size() <= 1:
		return 0
	var src := unit_of(bid, floor)
	if src == "" or not units.has(src):
		return 0
	var src_items: Array = []
	for iid in items:
		if String(items[iid].get("at", "")) == src:
			src_items.append(iid)
	if src_items.is_empty():
		return 0
	var n := 0
	for u in units:
		var dst := String(u)
		if dst == src:
			continue
		var dwellers := npcs_at_unit(dst)
		var owner := String(dwellers[0]) if not dwellers.is_empty() else ""
		for iid in src_items:
			var it: Dictionary = items[iid]
			_seq.i += 1
			var nid := "%s_%03d" % [String(it["type"]), int(_seq.i)]
			items[nid] = {"type": String(it["type"]), "at": dst, "owner": owner,
				"stock": int(it.get("stock", 1)), "price": float(it.get("price", 0.0)),
				"persist_empty": bool(it.get("persist_empty", false))}
			n += 1
	errors = validate()
	changed.emit()
	return n


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
	# 无住所的人: 不算错误(合法状态 —— 出生空白), 但必须让人看见
	var n_homeless := homeless_npcs().size()
	if n_homeless > 0:
		out.append({"level": "warn",
			"msg": "%d 人没有住所(右边「无住所的人」可以分配或删除)" % n_homeless,
			"kind": "npc", "id": ""})
	# 引用指向不存在的地点(典型: 减层后遗留的 bld_001_f7)
	var sites := _valid_sites()
	for pid in npcs:
		var h := String(npcs[pid].get("home", ""))
		if h != "" and not sites.has(h):
			out.append({"level": "error", "msg": "住所不存在: %s" % h,
				"kind": "npc", "id": pid})
	for iid in items:
		var at := String(items[iid].get("at", ""))
		if at != "" and not sites.has(at):
			out.append({"level": "error", "msg": "物件所在地不存在: %s" % at,
				"kind": "item", "id": iid})
	# 认知规则: 指向的地点必须存在
	for ki in knowledge.size():
		var kf := String((knowledge[ki] as Dictionary).get("from", ""))
		if kf != "" and not sites.has(kf):
			out.append({"level": "error", "msg": "认知指向不存在的地点: %s" % kf,
				"kind": "knowledge", "id": str(ki)})
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
	return BuildingGeom.obb_corners(b["center"], b["size"], float(b.get("rot", 0.0)))


func point_in_building(b: Dictionary, p: Vector2) -> bool:
	return BuildingGeom.point_in_obb(
		b["center"], b["size"], float(b.get("rot", 0.0)), p)


func obb_overlap(a: Dictionary, b: Dictionary) -> bool:
	return BuildingGeom.obb_overlap(
		a["center"], a["size"], float(a.get("rot", 0.0)),
		b["center"], b["size"], float(b.get("rot", 0.0)))


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
		var n: Dictionary = nodes[id]
		var rec := {"xy": _v(n["xy"]), "kind": n["kind"]}
		if String(n.get("door_of", "")) != "":
			rec["door_of"] = n["door_of"]
			rec["door_index"] = int(n.get("door_index", 0))
		nd[id] = rec
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
		var rec := {"type": b["type"], "center": _v(b["center"]),
			"size": _v(b["size"]), "rot": b["rot"], "doors": doors,
			"floors": int(b.get("floors", 1))}
		if has_custom_name(String(id)):              # 作者起的名字要留在 .map 里
			rec["name"] = String(b.get("name", ""))
		bd[id] = rec
	return {"format": SCHEMA, "version": VERSION,
		"world": {"unit": "m",
			"bounds": [bounds.position.x, bounds.position.y, bounds.size.x, bounds.size.y],
			"grid": grid_size, "grid_snap": grid_snap, "net_snap": net_snap},
		"nodes": nd, "edges": ed, "buildings": bd}


func from_dict(d: Dictionary) -> void:
	new_map()
	var w: Dictionary = d.get("world", {})
	grid_size = float(w.get("grid", 1.0))
	grid_snap = bool(w.get("grid_snap", true))
	net_snap = bool(w.get("net_snap", true))
	var bd = w.get("bounds", [0, 0, 800, 600])
	if bd is Array and bd.size() >= 4:
		bounds = Rect2(float(bd[0]), float(bd[1]), float(bd[2]), float(bd[3]))
	var nd: Dictionary = d.get("nodes", {})
	for id in nd:
		var n: Dictionary = nd[id]
		var rec := {"xy": _vec(n["xy"]),
			"kind": String(n.get("kind", "junction"))}
		if String(n.get("door_of", "")) != "":
			rec["door_of"] = String(n["door_of"])
			rec["door_index"] = int(n.get("door_index", 0))
		nodes[String(id)] = rec
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
	# 老场景兼容: 早期编辑器把“类型默认名”写进了 name(于是满城“小屋”)
	# → 载入时视作【没起名字】, 交给 default_building_name 自动编号。
	var bld_raw: Dictionary = d.get("buildings", {})
	for _k in bld_raw:
		var _b = bld_raw[_k]
		if not (_b is Dictionary):
			continue
		var _tp := String(_b.get("type", ""))
		var _nm := String(_b.get("name", ""))
		# 自动编号 / 类型默认名 → 视作没起名字, 交回 default_building_name(避免撞号)
		if _nm != "" and (_nm == type_display(_tp) or _is_auto_name(_nm, _tp)):
			_b["name"] = ""
	var bld: Dictionary = bld_raw
	for id in bld:
		var b: Dictionary = bld[id]
		var doors := []
		for dd in b.get("doors", []):
			doors.append(_vec(dd))
		var rec := {"type": String(b["type"]),
			"center": _vec(b["center"]), "size": _vec(b["size"]),
			"rot": float(b.get("rot", 0.0)), "doors": doors,
			"floors": maxi(1, int(b.get("floors", 1)))}
		if String(b.get("name", "")) != "":
			rec["name"] = String(b["name"])
		buildings[String(id)] = rec
	_recount()
	# 已知类型 → 按 doors 定义重算进出口世界点(不信任导入的旧值)
	for id in buildings:
		if building_types.has(String(buildings[id]["type"])):
			_sync_doors(buildings[id])
	prune_orphan_nodes()          # 原则: 没有边的节点不存在
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
func to_scene_dict(scene_name_arg: String = "") -> Dictionary:
	var nm := scene_name_arg if scene_name_arg != "" else scene_name
	var locs := {}
	for bid in buildings:
		var b: Dictionary = buildings[bid]
		var cs: Array = obb_corners(b)
		var minp: Vector2 = cs[0]
		var maxp: Vector2 = cs[0]
		for p in cs:
			minp = Vector2(minf(minp.x, p.x), minf(minp.y, p.y))
			maxp = Vector2(maxf(maxp.x, p.x), maxf(maxp.y, p.y))
		var geo := {"x": snappedf(minp.x, 0.01), "y": snappedf(minp.y, 0.01),
			"w": snappedf(maxp.x - minp.x, 0.01),
			"h": snappedf(maxp.y - minp.y, 0.01)}
		var base := {"type": String(b["type"]), "name": building_name(bid)}
		base.merge(geo)
		locs[bid] = base
		# floors>1: 每层额外导出一个【子地点】(同 footprint + part_of)。
		# 后端只当普通地点, ``part_of`` 仅用于编辑器重导入时跳过(不会重复造楼)。
		var units := unit_ids(bid)
		if units.size() > 1:
			for k in units.size():
				var u := String(units[k])
				var d := {"type": String(b["type"]),
					"name": "%s · %d层" % [building_name(bid), k + 1],
					"part_of": bid}
				d.merge(geo)
				locs[u] = d
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
		# 只有真写过记忆才导出这一段(否则 114 个人各多一行空字典)
		var mmem: Dictionary = p.get("memory", {})
		if not mmem.is_empty():
			ppl[ppl.size() - 1]["memory"] = mmem.duplicate(true)
	# 旅行成本: 建筑中心直线距离 / 10 粗估(缺省 20; 无路网时的降级)
	var pairs := {}
	var bids: Array = buildings.keys()
	bids.sort()
	for i in range(bids.size()):
		for j in range(i + 1, bids.size()):
			var a: Vector2 = buildings[bids[i]]["center"]
			var b2: Vector2 = buildings[bids[j]]["center"]
			pairs["%s|%s" % [bids[i], bids[j]]] = maxi(1, int(a.distance_to(b2) / 10.0))
	var comps: Array = []
	var cids: Array = companies.keys()
	cids.sort()
	for cid in cids:
		comps.append((companies[cid] as Dictionary).duplicate(true))
	return {"scene": nm, "display_name": scene_display if scene_display != "" else nm,
		"canvas": {"w": bounds.size.x, "h": bounds.size.y},
		"locations": locs, "travel": {"default": 20, "pairs": pairs},
		"entities": ents, "pulses": [], "plans": {}, "npcs": ppl,
		"companies": comps,
		"knowledge": knowledge.duplicate(true),
		"map": to_dict()}


func save_scene(path: String, scene_name: String = "") -> bool:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		return false
	f.store_string(JSON.stringify(to_scene_dict(scene_name), "  "))
	f.close()
	return true


## 导入编辑器场景(config/scenes 格式)。
## map 段还原路网/建筑; 无 map 段时用 locations 矩形兜底; entities/npcs 还原物件与人物。
func load_scene_dict(d: Dictionary) -> bool:
	if not d.has("locations") and not d.has("map"):
		return false
	scene_name = String(d.get("scene", "editor_scene"))
	scene_display = String(d.get("display_name", ""))
	new_map()
	var m: Variant = d.get("map")
	if m is Dictionary and not (m as Dictionary).is_empty():
		from_dict(m)          # ★ from_dict 内部还会 new_map() 一次 → 所以
	_load_buildings_from_locations(d)   # knowledge/companies 必须放在它【之后】导
	_load_items(d)
	_load_npcs(d)
	# 放在所有“会 new_map 的”载入之后 —— 否则会被冲掉(以前 knowledge 就这么丢的)
	knowledge = (d.get("knowledge", []) as Array).duplicate(true)
	for c in (d.get("companies", []) as Array):
		if c is Dictionary and String((c as Dictionary).get("id", "")) != "":
			var cid := String((c as Dictionary).get("id"))
			companies[cid] = (c as Dictionary).duplicate(true)
	_recount()
	errors = validate()
	changed.emit()
	return true


## locations 段 → 建筑: 已有(来自 map)的只补自定义名; 缺的按矩形造一个。
func _load_buildings_from_locations(d: Dictionary) -> void:
	var locs: Dictionary = d.get("locations", {})
	# 先数一遍子地点(楼层单元): 无 map 段的旧场景里, 靠它恢复 floors。
	var children := {}
	for lid in locs:
		var p := String((locs[lid] as Dictionary).get("part_of", ""))
		if p != "":
			children[p] = int(children.get(p, 0)) + 1
	for bid in locs:
		var loc: Dictionary = locs[bid]
		var t := String(loc.get("type", ""))
		if not building_types.has(t):
			continue
		# 楼层单元(part_of 指向父建筑): 不是独立建筑, 跳过 —— 否则会重复造楼。
		if String(loc.get("part_of", "")) != "":
			continue
		if buildings.has(bid):
			var nm0 := String(loc.get("name", ""))
			if nm0 != "" and nm0 != type_display(t) 					and not _is_auto_name(nm0, t):
				buildings[bid]["name"] = nm0
			continue
		var w := float(loc.get("w", 0.0))
		var h := float(loc.get("h", 0.0))
		if w <= 0.0 or h <= 0.0:
			var sz := default_size_for(t)
			w = sz.x
			h = sz.y
		var b := {"type": t,
			"center": Vector2(float(loc.get("x", 0.0)) + w * 0.5,
				float(loc.get("y", 0.0)) + h * 0.5),
			"size": Vector2(w, h), "rot": 0.0, "doors": [],
			"floors": maxi(1, int(children.get(bid, 0)))}
		var nm := String(loc.get("name", ""))
		if nm != "" and nm != type_display(t) and not _is_auto_name(nm, t):
			b["name"] = nm
		buildings[bid] = b
		_sync_doors(b)


func _load_items(d: Dictionary) -> void:
	items.clear()
	for e in d.get("entities", []):
		if not (e is Dictionary):
			continue
		var iid := String(e.get("id", ""))
		if iid == "":
			continue
		items[iid] = {"type": String(e.get("type", "")),
			"at": String(e.get("at", "")),
			"owner": String(e.get("owner", "")),
			"stock": int(e.get("stock", 1)),
			"price": float(e.get("price", 0.0)),
			"persist_empty": bool(e.get("persist_empty", false))}


func _load_npcs(d: Dictionary) -> void:
	npcs.clear()
	for p in d.get("npcs", []):
		if not (p is Dictionary):
			continue
		var pid := String(p.get("id", ""))
		if pid == "":
			continue
		npcs[pid] = {"name": String(p.get("name", pid)),
			"gender": String(p.get("gender", "")),
			"birthday": String(p.get("birthday", "")),
			"role": String(p.get("role", "")),
			"money": float(p.get("money", 100.0)),
			"home": String(p.get("home", "")),
			"personality": p.get("personality", {}),
			"init": p.get("init", {}),
			"traits": p.get("traits", {}),
			"tell_bias": float(p.get("tell_bias", 1.0)),
			"memory": (p.get("memory", {}) as Dictionary).duplicate(true)}
