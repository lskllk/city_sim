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
const C_FLOOR := Color("c9a4ff")    # 楼层角标

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
	var raw_nodes := Protocol.as_dict(Store.map.get("nodes", {}))
	var raw_edges := Protocol.as_dict(Store.map.get("edges", {}))
	var nodes_s := {}
	for nid in raw_nodes:
		nodes_s[nid] = camera.world_to_screen(
			_pt(Protocol.as_dict(raw_nodes[nid]).get("xy")))
	var edges_s := {}
	for eid in raw_edges:
		var e := Protocol.as_dict(raw_edges[eid])
		var pts := PackedVector2Array()
		for p in Protocol.as_array(e.get("geom", [])):
			pts.append(camera.world_to_screen(_pt(p)))
		BuildingStyle.draw_road(self, pts,
			maxf(Protocol.num(e.get("width"), 4.0) * camera.zoom, 2.0))
		edges_s[eid] = {
			"a": Protocol.s(e.get("a", "")), "b": Protocol.s(e.get("b", "")),
			"pts": pts,
			"width_px": maxf(Protocol.num(e.get("width"), 4.0) * camera.zoom, 2.0)}
	# 路口: 与编辑器同一套几何(通用 N 叉圆角)
	BuildingStyle.draw_junctions(self,
		BuildingStyle.build_junctions(nodes_s, edges_s), BuildingStyle.ROAD_COLOR)


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
	# 分过单元的: 父地点的 capacity 是【单层】容量 → 总容量 = 单层 × 层数
	# (不乘的话 9 个人住 3 层楼会显示成 9/3 超员)
	if Store.is_multi(id):
		cap *= Store.floor_units(id)
	var n := int(occ.get(id, 0))
	var fill := clampf(float(n) / float(cap), 0.0, 1.0)
	var body := base.lerp(BuildingStyle.HOT, fill * 0.75)
	draw_colored_polygon(pts, Color(body.r, body.g, body.b, 0.5 + 0.35 * fill))
	var outline := pts.duplicate()
	outline.append(pts[0])
	draw_polyline(outline, base.lightened(0.35).lerp(BuildingStyle.HOT_EDGE, fill), 2.0, true)
	# LOD 分层: 角标/名称/徽记随建筑【屏幕大小】缩放并分级; 字看不清就不画。
	# (k=1.0 对应建筑屏幕短边 60px)
	var k := BuildingGeom.badge_scale(rect)
	if k >= BuildingGeom.LOD_EMBLEM:
		BuildingStyle.draw_emblem_scaled(self,
			rect.get_center() + Vector2(0, -24.0 * k), kind, base, k)
	if k >= BuildingGeom.LOD_NAME:
		BuildingStyle.draw_centered(self, font,
			Protocol.s(room.get("name", id), id), rect.get_center(),
			maxi(9, int(round(11.0 * k))),
			Color.WHITE if n > 0 else BuildingStyle.NAME_COLOR)
	if k >= BuildingGeom.LOD_BADGE:
		BuildingStyle.draw_badge(self, font, rect, "%d/%d" % [n, cap], base, fill, k)
	# 招牌: 挂在门口的消息板(最多 3 条)。玩家要能一眼看出"这家店在吆喝什么"。
	_draw_sign(font, room, rect, k)
	_draw_doors_for(id, room)


## 招牌可视化 —— 三段随缩放变化(以前只在"建筑短边 ≥51px"时才画, 缩远就看不见,
## 用户反馈"加了招牌前端什么都没有"就是这么来的):
##   k <  LOD_NAME  → 右上角一个小黄点(知道这家有招牌)
##   k >= LOD_NAME  → 一块小牌子, 只写「招牌 N」
##   k >= LOD_EMBLEM→ 展开写每一行「货 ¥价」(最多 3 行)
## 数据全部来自后端(world.locations[bid].sign); 前端不猜不算。
func _draw_sign(font: Font, room: Dictionary, rect: Rect2, k: float) -> void:
	var sign := Protocol.as_dict(room.get("sign", {}))
	if sign.is_empty():
		return
	var msgs := Protocol.as_array(sign.get("messages", []))
	if msgs.is_empty():
		return
	if k < BuildingGeom.LOD_NAME:
		# 太远: 只留一个记号, 免得整张图看过去"这家店没有招牌"
		draw_circle(rect.position + Vector2(rect.size.x - 3.0, 2.0), 2.5,
			Color("ffcf5a"))
		return
	var detailed := k >= BuildingGeom.LOD_EMBLEM
	var lines: Array[String] = []
	if detailed:
		for mid in msgs:
			var e := Store.entity(String(mid))
			if e.is_empty():
				lines.append("? " + String(mid))
				continue
			var pr := Protocol.num(e.get("price", 0.0))
			lines.append("%s %s" % [Protocol.s(e.get("name", mid)),
				("¥%d" % int(pr)) if pr > 0.0 else "有货"])
	else:
		lines.append("招牌 %d" % msgs.size())
	var fs := maxi(8, int(round(9.0 * k)))
	var w := 0.0
	for ln in lines:
		w = maxf(w, font.get_string_size(ln, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x)
	var pad := 3.0 * k
	# 挂在建筑【右上角外侧】: 角标在左上角, 这里不会打架; 再往上抬一点避开边框
	var box := Rect2(rect.position + Vector2(rect.size.x + 3.0 * k, -2.0 * k),
		Vector2(w + pad * 2.0, (fs + 3.0 * k) * lines.size() + pad * 2.0))
	draw_rect(box, Color(0.10, 0.09, 0.06, 0.9), true)
	draw_rect(box, Color("ffcf5a"), false, 1.5)
	# 一条细线连回建筑, 一眼看出牌子是谁家的
	draw_line(rect.position + Vector2(rect.size.x, 0.0), box.position,
		Color("ffcf5a"), 1.0)
	var y := box.position.y + pad + fs * 0.9
	for ln in lines:
		draw_string(font, Vector2(box.position.x + pad, y), ln,
			HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color("ffe9b0"))
		y += fs + 3.0 * k


## 编辑器未导出 map 时的回退: 轴对齐矩形(locations)。
func _draw_room(font: Font, id: String, r: Dictionary, rect: Rect2, n: int) -> void:
	var k := BuildingGeom.badge_scale(rect)
	BuildingStyle.draw_room(self, font, rect,
		Protocol.s(r.get("kind", "")), Protocol.s(r.get("name", id), id),
		n, int(Protocol.num(r.get("capacity"), 10.0)),
		k, BuildingGeom.LOD_NAME, BuildingGeom.LOD_EMBLEM,
		BuildingGeom.LOD_BADGE)
	_draw_sign(font, r, rect, k)          # 没导出 map 的场景也要看得见招牌
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
		# 同理: 楼层里的物件也算到整栋
		var bid := Store.building_of(Protocol.s(Store.entities[eid].get("loc", "")))
		if bid != "":
			counts[bid] = int(counts.get(bid, 0)) + 1
	for bid in counts:
		var rect := _building_screen_rect(String(bid))
		if rect.size == Vector2.ZERO:
			continue
		# LOD: 物/层角标只在字能看清时才画(随建筑缩放贴合)
		var k := BuildingGeom.badge_scale(rect)
		if k < BuildingGeom.LOD_DETAIL:
			continue
		var fs := maxi(8, int(round(10.0 * k)))
		var badge := BuildingGeom.item_badge_rect(rect.position,
			Vector2(34.0, 16.0), k)
		_badge_box(badge, C_ITEM, "物 %d" % int(counts[bid]), fs)
		# 多楼层建筑: 附一个 "共 N 层" 角标(仅真正 ≥2 层才加)
		var n := int(Store.floors.get(String(bid), 0))
		if n > 1:
			var fb := BuildingGeom.badge_rect(rect.position, 1, 34.0, 16.0, k)
			_badge_box(fb, C_FLOOR, "共 %d 层" % n, fs)


func _badge_box(box: Rect2, col: Color, text: String, fs: int) -> void:
	draw_rect(box, Color(col.r, col.g, col.b, 0.92), true)
	draw_rect(box, Color(1, 1, 1, 0.35), false, 1.0)
	var font := get_theme_default_font()
	if font != null:
		draw_string(font, box.position + Vector2(4.0 * float(fs) / 10.0,
			box.size.y * 0.75), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs,
			Color("101820"))


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
	# 选中楼层单元(如 NPC 在 bld_007_f2) → 框整栋楼, 而不是一个看不见的子地点
	var rect := _building_screen_rect(Store.building_of(loc_id))
	if rect.size == Vector2.ZERO:
		return
	draw_rect(rect, Color(color.r, color.g, color.b, 0.9), false, 2.5)


# ---------------------------------------------------------------------------
# 几何 helper
# ---------------------------------------------------------------------------
func _occupancy() -> Dictionary:
	var out := {}
	for id in Store.npcs:
		# 楼层单元归到父建筑: 住 bld_007_f2 的人要算到 bld_007 的占用上
		var bid := Store.building_of(Protocol.s(Store.npcs[id].get("loc", "")))
		if bid != "":
			out[bid] = int(out.get(bid, 0)) + 1
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
