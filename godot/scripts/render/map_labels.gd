# map_labels.gd —— 世界"矢量层": 在【屏幕坐标】里画(不受相机缩放, 文字始终清晰)。
#
# 渲染按【编辑器 MapView 的思路】: 道路(含圆角接头) → 建筑(支持 rot 的 OBB,
# 底色/徽记/名称/占用角标) → 进出口 → 人物标记 → 物件角标。
# 建筑/道路的样式与绘制都走观察器自己的 building_style.gd(唯一权威, 编辑器项目内也直接用)。
# 编辑器未导出 map 段时(如内置 elm_lane), 回退到按 locations 矩形绘制。
class_name MapLabels
extends Control

const BuildingStyle := preload("res://scripts/shared/building_style.gd")

const BG := BuildingStyle.BG
const C_ITEM := Color("9ad36b")

var camera: WorldCamera = null


func setup(cam: WorldCamera) -> void:
	camera = cam


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	Store.snapshot_applied.connect(queue_redraw)
	Store.selection_changed.connect(queue_redraw)


func _process(_delta: float) -> void:
	if camera != null:
		queue_redraw()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), BG, true)
	if camera == null:
		return
	var font := get_theme_default_font()
	if font == null:
		return
	var occ := _occupancy()
	_draw_roads()
	if _has_map():
		for id in Protocol.as_dict(Store.map.get("buildings", {})):
			_draw_map_building(font, String(id), occ)
	else:
		for id in Store.rooms:
			var r: Dictionary = Store.rooms[id]
			var rect := _room_screen_rect(r)
			if rect.size.x < 6.0 or rect.size.y < 6.0:
				continue
			_draw_room(font, id, r, rect, int(occ.get(id, 0)))
	_draw_item_badges(font)
	_draw_selection()


# ---------------------------------------------------------------------------
# 道路(编辑器同款: 粗线 + 顶点圆角接头)
# ---------------------------------------------------------------------------
func _draw_roads() -> void:
	var edges := Protocol.as_dict(Store.map.get("edges", {}))
	for eid in edges:
		var e := Protocol.as_dict(edges[eid])
		var w := maxf(Protocol.num(e.get("width"), 4.0) * camera.zoom, 2.0)
		var pts := PackedVector2Array()
		for p in Protocol.as_array(e.get("geom", [])):
			pts.append(camera.world_to_screen(_pt(p)))
		BuildingStyle.draw_road(self, pts, w)


# ---------------------------------------------------------------------------
# 建筑
# ---------------------------------------------------------------------------
func _has_map() -> bool:
	return not Protocol.as_dict(Store.map.get("buildings", {})).is_empty()


## 编辑器原图建筑: 支持 rot 的 OBB + 占用调制 + 徽记/名称/角标/门。
func _draw_map_building(font: Font, id: String, occ: Dictionary) -> void:
	var b := Protocol.as_dict(Protocol.as_dict(Store.map.get("buildings", {})).get(id, {}))
	if b.is_empty():
		return
	var c := _pt(b.get("center", [0, 0]))
	var s := _pt(b.get("size", [1, 1]))
	var pts := PackedVector2Array()
	for corner in BuildingGeom.obb_corners(c, s, Protocol.num(b.get("rot"), 0.0)):
		pts.append(camera.world_to_screen(corner))
	var rect := _aabb(pts)
	if rect.size.x < 6.0 or rect.size.y < 6.0:
		return
	var room := Store.room(id)
	var kind := Protocol.s(room.get("kind", ""))
	var base := BuildingStyle.kind_color(kind)
	var cap := maxi(1, int(Protocol.num(room.get("capacity"), 10.0)))
	var n := int(occ.get(id, 0))
	var fill := clampf(float(n) / float(cap), 0.0, 1.0)
	var body := base.lerp(BuildingStyle.HOT, fill * 0.75)
	draw_colored_polygon(pts, Color(body.r, body.g, body.b, 0.5 + 0.35 * fill))
	var outline := pts.duplicate()
	outline.append(pts[0])
	draw_polyline(outline, base.lightened(0.35).lerp(BuildingStyle.HOT_EDGE, fill), 2.0, true)
	if rect.size.x >= 52.0 and rect.size.y >= 52.0:
		BuildingStyle.draw_emblem(self, rect.get_center() + Vector2(0, -24), kind, base)
	var name := Protocol.s(room.get("name", id), id)
	var fsize := int(clampf(minf(rect.size.x, rect.size.y) / 8.0, 11.0, 18.0))
	BuildingStyle.draw_centered(self, font, name, rect.get_center(), fsize,
		Color.WHITE if n > 0 else BuildingStyle.NAME_COLOR)
	BuildingStyle.draw_badge(self, font, rect, "%d/%d" % [n, cap], base, fill)
	_draw_doors_for(id, room)


## 编辑器未导出 map 时的回退: 轴对齐矩形(locations)。
func _draw_room(font: Font, id: String, r: Dictionary, rect: Rect2, n: int) -> void:
	BuildingStyle.draw_room(self, font, rect,
		Protocol.s(r.get("kind", "")), Protocol.s(r.get("name", id), id),
		n, int(Protocol.num(r.get("capacity"), 10.0)))
	_draw_doors_for(id, r)


## 进出口: 优先编辑器原图的旋转后门点(法线由中心指向门近似), 否则回退 room.door_points。
func _draw_doors_for(id: String, room: Dictionary) -> void:
	if camera == null:
		return
	var b := Protocol.as_dict(Protocol.as_dict(Store.map.get("buildings", {})).get(id, {}))
	var doors := Protocol.as_array(b.get("doors", [])) if not b.is_empty() else []
	if not doors.is_empty():
		var center := _pt(b.get("center", [0, 0]))
		for dd in doors:
			var wp := _pt(dd)
			var normal := Vector2(0, 1)
			if wp.distance_to(center) > 0.001:
				normal = (wp - center).normalized()
			BuildingStyle.draw_door(self, camera.world_to_screen(wp), normal,
				5.0, Color(1, 1, 1, 0.85))
		return
	for dd in Protocol.as_array(room.get("door_points", [])):
		var d := Protocol.as_dict(dd)
		if d.is_empty():
			continue
		var pos := camera.world_to_screen(Vector2(
			Protocol.num(d.get("x")), Protocol.num(d.get("y"))))
		BuildingStyle.draw_door(self, pos,
			Vector2(Protocol.num(d.get("nx")), Protocol.num(d.get("ny"))),
			5.0, Color(1, 1, 1, 0.85))


# ---------------------------------------------------------------------------
# 物件标记
# ---------------------------------------------------------------------------
func _draw_item_badges(font: Font) -> void:
	var counts := {}
	for eid in Store.entities:
		var loc := Protocol.s(Store.entities[eid].get("loc", ""))
		if loc != "":
			counts[loc] = int(counts.get(loc, 0)) + 1
	for loc in counts:
		var rect := _building_screen_rect(String(loc))
		if rect.size == Vector2.ZERO:
			continue
		var badge := BuildingGeom.item_badge_rect(rect.position)
		draw_rect(badge, Color(C_ITEM.r, C_ITEM.g, C_ITEM.b, 0.92), true)
		draw_rect(badge, Color(1, 1, 1, 0.35), false, 1.0)
		draw_string(font, badge.position + Vector2(4, 12), "物 %d" % int(counts[loc]),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color("12200a"))


# ---------------------------------------------------------------------------
# 选中
# ---------------------------------------------------------------------------
func _draw_selection() -> void:
	match Store.sel_kind:
		"location":
			_frame(Store.sel_location, Color("6fb7ff"))
		"entity":
			var e := Store.entity(Store.sel_entity)
			if not e.is_empty():
				_frame(Protocol.s(e.get("loc", "")), Color("6fb7ff"))
		"npc":
			var n := Store.npc(Store.sel_npc)
			if n.is_empty():
				return
			_frame(Protocol.s(n.get("loc", "")), Color("3ddc84"))
			var intent := Protocol.as_dict(n.get("intent", {}))
			var tid := Protocol.s(intent.get("target", ""))
			if Store.rooms.has(tid):
				_frame(tid, Color("ffc24d"))
			else:
				var te := Store.entity(tid)
				if not te.is_empty():
					_frame(Protocol.s(te.get("loc", "")), Color("ffc24d"))


func _frame(loc_id: String, color: Color) -> void:
	if loc_id == "" or camera == null:
		return
	var rect := _building_screen_rect(loc_id)
	if rect.size == Vector2.ZERO:
		return
	draw_rect(rect, Color(color.r, color.g, color.b, 0.9), false, 2.5)


# ---------------------------------------------------------------------------
# 几何 helper
# ---------------------------------------------------------------------------
func _occupancy() -> Dictionary:
	var out := {}
	for id in Store.npcs:
		var loc := Protocol.s(Store.npcs[id].get("loc", ""))
		if loc != "":
			out[loc] = int(out.get(loc, 0)) + 1
	return out


func _pt(v: Variant) -> Vector2:
	var a := Protocol.as_array(v)
	return Vector2(Protocol.num(a[0]), Protocol.num(a[1])) if a.size() >= 2 \
		else Vector2.ZERO


func _aabb(pts: PackedVector2Array) -> Rect2:
	if pts.is_empty():
		return Rect2()
	var mn := pts[0]
	var mx := pts[0]
	for p in pts:
		mn = Vector2(minf(mn.x, p.x), minf(mn.y, p.y))
		mx = Vector2(maxf(mx.x, p.x), maxf(mx.y, p.y))
	return Rect2(mn, mx - mn)


func _room_screen_rect(r: Dictionary) -> Rect2:
	var tl := camera.world_to_screen(Vector2(
		Protocol.num(r.get("x")), Protocol.num(r.get("y"))))
	var wh := Vector2(Protocol.num(r.get("w")), Protocol.num(r.get("h"))) * camera.zoom
	return Rect2(tl, wh)


## 建筑在屏幕上的外接矩形(优先编辑器 OBB; 否则 locations 矩形)。
func _building_screen_rect(id: String) -> Rect2:
	var b := Protocol.as_dict(Protocol.as_dict(Store.map.get("buildings", {})).get(id, {}))
	if not b.is_empty():
		var c := _pt(b.get("center", [0, 0]))
		var s := _pt(b.get("size", [1, 1]))
		var pts := PackedVector2Array()
		for corner in BuildingGeom.obb_corners(c, s, Protocol.num(b.get("rot"), 0.0)):
			pts.append(camera.world_to_screen(corner))
		return _aabb(pts)
	var r := Store.room(id)
	if r.is_empty():
		return Rect2()
	return _room_screen_rect(r)


## 地点中心(编辑器建筑中心优先), 无则 null。
func _loc_center(id: String) -> Variant:
	var b := Protocol.as_dict(Protocol.as_dict(Store.map.get("buildings", {})).get(id, {}))
	if not b.is_empty():
		return _pt(b.get("center", [0, 0]))
	var r := Store.room(id)
	if not r.is_empty():
		return Vector2(Protocol.num(r.get("x")) + Protocol.num(r.get("w")) * 0.5,
			Protocol.num(r.get("y")) + Protocol.num(r.get("h")) * 0.5)
	return null
