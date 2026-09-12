class_name MapView
extends Control
## MapView —— 编辑画布: 栅格 / 路网 / 建筑 / 选中 / 校验高亮 + 交互。
##
## 只读写 MapDoc(autoload), 不碰 simulation。相机: 世界(米) -> 屏幕(px)。

signal selection_changed
signal status_message(msg)

enum Tool { SELECT, PLACE, ROAD }

const C_BG := Color("0f1319")
const C_GRID := Color("1b232d")
const C_GRID_MAJOR := Color("27313d")
const C_AXIS := Color("39485a")
const C_ROAD := Color("59636f")
const C_ROAD_SEL := Color("4aa3ff")
const C_BLDG := Color("7a5a3a")
const C_BLDG_SEL := Color("4aa3ff")
const C_NODE := Color("e8c07d")
const C_ERR := Color("e05252")
const C_WARN := Color("e8a34d")
const C_GHOST := Color(0.45, 0.8, 1.0, 0.35)

var tool: int = Tool.SELECT
var placing_type: String = ""
var sel_kind: String = ""          # "building" | "node" | "edge" | ""
var sel_id: String = ""

var cam_center := Vector2(400, 300)
var zoom := 6.0

var _mouse := Vector2.ZERO
var _mouse_world := Vector2.ZERO
var _panning := false
var _dragging := false
var _drag_off := Vector2.ZERO
var _road_from := ""


func _ready() -> void:
	focus_mode = Control.FOCUS_ALL
	clip_contents = true
	MapDoc.changed.connect(queue_redraw)
	MapDoc.changed.connect(_refresh_status)
	_refresh_status()


# --- 坐标变换 ------------------------------------------------------------
func w2s(p: Vector2) -> Vector2:
	return (p - cam_center) * zoom + size * 0.5


func s2w(sp: Vector2) -> Vector2:
	return (sp - size * 0.5) / zoom + cam_center


func set_tool(t: int) -> void:
	tool = t
	if t != Tool.ROAD:
		_road_from = ""
	status_message.emit(_tool_hint())
	queue_redraw()


func select(kind: String, id: String) -> void:
	sel_kind = kind
	sel_id = id
	selection_changed.emit()
	queue_redraw()


func clear_selection() -> void:
	select("", "")


func fit_to_content() -> void:
	var pts: Array = []
	for id in MapDoc.nodes:
		pts.append(MapDoc.nodes[id]["xy"])
	for id in MapDoc.buildings:
		pts.append(MapDoc.buildings[id]["center"])
	if pts.is_empty():
		cam_center = MapDoc.bounds.get_center()
		zoom = 6.0
	else:
		var r := Rect2(pts[0], Vector2.ZERO)
		for p in pts:
			r = r.expand(p)
		r = r.grow(20.0)
		cam_center = r.get_center()
		var zx := size.x / maxf(r.size.x, 1.0)
		var zy := size.y / maxf(r.size.y, 1.0)
		zoom = clampf(minf(zx, zy), 0.5, 200.0)
	queue_redraw()


# --- 绘制 ----------------------------------------------------------------
func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), C_BG)
	_draw_grid()
	_draw_bounds()
	_draw_edges()
	_draw_buildings()
	_draw_nodes()
	_draw_errors()
	_draw_ghost()


func _draw_grid() -> void:
	var step: float = maxf(MapDoc.grid_size, 0.01)
	while step * zoom < 8.0:
		step *= 5.0
	var tl := s2w(Vector2.ZERO)
	var br := s2w(size)
	var x := floorf(tl.x / step) * step
	while x <= br.x:
		var major := absf(fmod(x, step * 5.0)) < 0.001
		var col := C_GRID_MAJOR if major else C_GRID
		draw_line(Vector2(w2s(Vector2(x, tl.y)).x, 0.0),
			Vector2(w2s(Vector2(x, br.y)).x, size.y), col, 1.0)
		x += step
	var y := floorf(tl.y / step) * step
	while y <= br.y:
		var major2 := absf(fmod(y, step * 5.0)) < 0.001
		var col2 := C_GRID_MAJOR if major2 else C_GRID
		draw_line(Vector2(0.0, w2s(Vector2(tl.x, y)).y),
			Vector2(size.x, w2s(Vector2(br.x, y)).y), col2, 1.0)
		y += step


func _draw_bounds() -> void:
	var tl := w2s(MapDoc.bounds.position)
	var br := w2s(MapDoc.bounds.end)
	draw_rect(Rect2(tl, br - tl), C_AXIS, false, 2.0)


func _draw_edges() -> void:
	for id in MapDoc.edges:
		var e: Dictionary = MapDoc.edges[id]
		var sel: bool = sel_kind == "edge" and sel_id == id
		var col := C_ROAD_SEL if sel else C_ROAD
		var w := maxf(e["width"] * zoom, 2.0)
		var g: Array = e["geom"]
		for i in range(g.size() - 1):
			draw_line(w2s(g[i]), w2s(g[i + 1]), col, w, true)
		if sel and g.size() >= 2:
			draw_dashed_line(w2s(g[0]), w2s(g[g.size() - 1]), C_ROAD_SEL, 1.5)


func _draw_buildings() -> void:
	for id in MapDoc.buildings:
		var b: Dictionary = MapDoc.buildings[id]
		var sel: bool = sel_kind == "building" and sel_id == id
		var pts := PackedVector2Array()
		for c in MapDoc.obb_corners(b):
			pts.append(w2s(c))
		var fill := C_BLDG
		fill.a = 0.55
		draw_colored_polygon(pts, fill)
		draw_polyline(pts + PackedVector2Array([pts[0]]),
			C_BLDG_SEL if sel else Color("c9b08a"), 3.0 if sel else 1.5, true)
		var ctr := w2s(b["center"])
		draw_circle(ctr, 2.5, C_BLDG_SEL if sel else Color("d8c7a8"))


func _draw_nodes() -> void:
	for id in MapDoc.nodes:
		var p := w2s(MapDoc.nodes[id]["xy"])
		var sel: bool = sel_kind == "node" and sel_id == id
		var r := 5.0 if sel else 3.5
		draw_circle(p, r, C_ROAD_SEL if sel else C_NODE)
		draw_arc(p, r, 0.0, TAU, 16, Color("0f1319"), 1.0)


func _draw_errors() -> void:
	for e in MapDoc.errors:
		var col: Color = C_ERR if e["level"] == "error" else C_WARN
		var id: String = e["id"]
		match e["kind"]:
			"building":
				if MapDoc.buildings.has(id):
					var pts := PackedVector2Array()
					for c in MapDoc.obb_corners(MapDoc.buildings[id]):
						pts.append(w2s(c))
					draw_polyline(pts + PackedVector2Array([pts[0]]), col, 2.5, true)
			"edge":
				if MapDoc.edges.has(id):
					var g: Array = MapDoc.edges[id]["geom"]
					draw_line(w2s(g[0]), w2s(g[g.size() - 1]), col, 2.5, true)
			"node":
				if MapDoc.nodes.has(id):
					draw_arc(w2s(MapDoc.nodes[id]["xy"]), 8.0, 0.0, TAU, 20, col, 2.0)


func _draw_ghost() -> void:
	if tool == Tool.PLACE and placing_type != "":
		var sz := MapDoc.default_size_for(placing_type)
		var c := MapDoc.snap(_mouse_world)
		var h := sz * 0.5
		var pts := PackedVector2Array([
			w2s(c + Vector2(-h.x, -h.y)), w2s(c + Vector2(h.x, -h.y)),
			w2s(c + Vector2(h.x, h.y)), w2s(c + Vector2(-h.x, h.y)),
			w2s(c + Vector2(-h.x, -h.y))])
		draw_polyline(pts, C_GHOST, 2.0, true)
	elif tool == Tool.ROAD and _road_from != "" and MapDoc.nodes.has(_road_from):
		var a := w2s(MapDoc.nodes[_road_from]["xy"])
		draw_line(a, w2s(MapDoc.snap(_mouse_world)), C_GHOST, 2.0)


# --- 交互 ----------------------------------------------------------------
func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		_mouse = event.position
		_mouse_world = s2w(_mouse)
		if _panning:
			cam_center -= event.relative / zoom
			queue_redraw()
		elif _dragging:
			var target := MapDoc.snap(s2w(_mouse) - _drag_off)
			if sel_kind == "building":
				MapDoc.move_building(sel_id, target)
			elif sel_kind == "node":
				MapDoc.move_node(sel_id, target)
		else:
			queue_redraw()
	elif event is InputEventMouseButton:
		_mouse = event.position
		_mouse_world = s2w(_mouse)
		if event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			_zoom_at(event.position, 1.15)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			_zoom_at(event.position, 1.0 / 1.15)
		elif event.button_index == MOUSE_BUTTON_MIDDLE:
			_panning = event.pressed
		elif event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
			if tool == Tool.ROAD and _road_from != "":
				_road_from = ""
				status_message.emit("已结束当前连线")
			else:
				clear_selection()
			queue_redraw()
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				_on_left_press(event.position)
			else:
				_dragging = false
				queue_redraw()
	elif event is InputEventKey and event.pressed:
		if event.keycode == KEY_DELETE or event.keycode == KEY_BACKSPACE:
			_delete_selected()
		elif event.keycode == KEY_ESCAPE:
			if _road_from != "":
				_road_from = ""
			else:
				clear_selection()
			queue_redraw()


func _zoom_at(pos: Vector2, factor: float) -> void:
	var before := s2w(pos)
	zoom = clampf(zoom * factor, 0.3, 300.0)
	var after := s2w(pos)
	cam_center += before - after
	queue_redraw()


func _on_left_press(pos: Vector2) -> void:
	match tool:
		Tool.PLACE:
			if placing_type != "":
				MapDoc.add_building(placing_type, MapDoc.snap(s2w(pos)))
				status_message.emit("已放置: " + MapDoc.type_display(placing_type))
		Tool.ROAD:
			var nid := _node_at(pos)
			if nid == "":
				nid = MapDoc.add_node(MapDoc.snap(s2w(pos)))
			if _road_from == "":
				_road_from = nid
				status_message.emit("起点: %s — 点下一个节点连线 (右键/Esc 结束)" % nid)
			else:
				var made := MapDoc.add_edge(_road_from, nid)
				if made != "":
					status_message.emit("连线 %s → %s" % [_road_from, nid])
				_road_from = nid
			queue_redraw()
		_:
			var hit := _hit(pos)
			if hit.is_empty():
				clear_selection()
			else:
				select(hit["kind"], hit["id"])
				if hit["kind"] in ["building", "node"]:
					_dragging = true
					var center: Vector2 = MapDoc.buildings[hit["id"]]["center"] \
						if hit["kind"] == "building" else MapDoc.nodes[hit["id"]]["xy"]
					_drag_off = s2w(pos) - center
					grab_focus()


func _node_at(pos: Vector2) -> String:
	var best := ""
	var bd := 10.0
	for id in MapDoc.nodes:
		var d := w2s(MapDoc.nodes[id]["xy"]).distance_to(pos)
		if d < bd:
			bd = d
			best = id
	return best


func _hit(pos: Vector2) -> Dictionary:
	var nid := _node_at(pos)
	if nid != "":
		return {"kind": "node", "id": nid}
	var wp := s2w(pos)
	var bids: Array = MapDoc.buildings.keys()
	bids.sort()
	bids.reverse()
	for id in bids:
		if MapDoc.point_in_building(MapDoc.buildings[id], wp):
			return {"kind": "building", "id": id}
	# edge: 距离折线 < 6px
	for id in MapDoc.edges:
		var g: Array = MapDoc.edges[id]["geom"]
		for i in range(g.size() - 1):
			var a := w2s(g[i])
			var b := w2s(g[i + 1])
			if _dist_to_seg(pos, a, b) <= 6.0:
				return {"kind": "edge", "id": id}
	return {}


func _dist_to_seg(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var l2 := ab.length_squared()
	if l2 < 0.0001:
		return p.distance_to(a)
	var t := clampf((p - a).dot(ab) / l2, 0.0, 1.0)
	return p.distance_to(a + ab * t)


func _delete_selected() -> void:
	match sel_kind:
		"building":
			MapDoc.remove_building(sel_id)
		"node":
			MapDoc.remove_node(sel_id)
		"edge":
			MapDoc.remove_edge(sel_id)
		_:
			return
	status_message.emit("已删除 %s" % sel_id)
	clear_selection()


func _tool_hint() -> String:
	match tool:
		Tool.PLACE:
			return "放置模式: 在画布点击放置建筑"
		Tool.ROAD:
			return "连线模式: 点击落节点; 连续点成路; 右键/Esc 结束"
		_:
			return "选择模式: 点击选中, 拖动移动, Delete 删除"


func _refresh_status() -> void:
	if not is_inside_tree():
		return
	status_message.emit("节点 %d · 路段 %d · 建筑 %d · 错误 %d" % [
		MapDoc.nodes.size(), MapDoc.edges.size(), MapDoc.buildings.size(),
		MapDoc.error_count("error")])
