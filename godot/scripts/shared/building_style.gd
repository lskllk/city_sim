# building_style.gd —— 建筑"资产"唯一样式真源 (single authority)。
#
# 谁用(同一 Godot 项目内):
#   - 观察器渲染: scripts/render/map_labels.gd
#   - 编辑器画布: scripts/editor/map_view.gd (底色/徽记/道路/门)
#   - 编辑器外壳: scripts/editor/main.gd   (资产列表着色)
# 这样"观察器怎么渲染, 编辑器就怎么渲染", 不再各自维护一份底色/徽记。
#
# 约束(保持自包含, 便于将来复用/单测):
#   - 只用 Godot 内建类型; 不反向依赖 editor/ 或 render/ 其它脚本;
#   - 不用 class_name / autoload(保持为纯静态工具类)。
# 视觉通道与 docs/design.md §2.9 对齐:
#   色相 = kind(类别), 面积 = capacity(后端算), 红度 = 占用率(观察器运行时有)。
extends RefCounted

const BG := Color("0d1016")
const HOT := Color("c0392b")
const HOT_EDGE := Color("ff8a7a")
const NAME_COLOR := Color("c7d2e2")
const MUTED_COLOR := Color("7f8ea3")
const DEFAULT_KIND := Color("3d4a60")
const ROAD_COLOR := Color("59636f")

## kind -> 底色(类别色相)。新类别只加这里一处。
const KIND_COLOR := {
	"home": Color("7a5a3a"),
	"shop": Color("2f7d78"),
	"factory": Color("6f7078"),
	"work": Color("8a5a34"),
	"public": Color("42557f"),
	"school": Color("6b5a8a"),
	"clinic": Color("3f7d8a"),
	"farm": Color("4f7a3a"),
}

## 进出口 side -> 房间局部(未旋转)朝外法线。north = -Y。
const SIDE_NORMAL := {
	"north": Vector2(0, -1),
	"south": Vector2(0, 1),
	"east": Vector2(1, 0),
	"west": Vector2(-1, 0),
}


static func kind_color(kind: String) -> Color:
	return KIND_COLOR.get(kind, DEFAULT_KIND)


## 道路折线: 粗线 + 每个顶点补半径=半宽的实心圆 → 圆角接头, 修补 T/十字"破边"。
static func draw_road(ci: CanvasItem, pts: PackedVector2Array, width_px: float,
		color: Color = ROAD_COLOR) -> void:
	if pts.size() < 2:
		return
	var w := maxf(width_px, 2.0)
	for i in range(pts.size() - 1):
		ci.draw_line(pts[i], pts[i + 1], color, w, true)
	for p in pts:
		ci.draw_circle(p, w * 0.5, color)


# ---------------------------------------------------------------------------
# 路网: 通用 N 叉路口圆角(填凹角)
#
# 关键: 十字/T 字路口的**外角是凹角(270°)** —— 是两股路之间缺了一块的"缺口",
# 所以要**填**上而不是切掉。给每个缺口补一块"两边相切 + 圆弧收口"的填充:
#   路宽 w → 半宽 a=w/2; 圆角半径 r = fillet_of_width × a
#   (缺省 fillet_of_width=0.5 → 圆角直径 = w/2, 半径 = w/4)
# 对 3/4/5/6 … 叉完全通用: 按极角排完序, 逐个"相邻方向对"的缺口各填一块。
# 夹角 >= 180°(直行) 或 < JUNCTION_EPS(近平行) 的缺口不填。
# 坐标全为**屏幕坐标**(与 draw_road 一致)。
# ---------------------------------------------------------------------------
const JUNCTION_EPS := 0.15
const FLAT_EPS := 0.05


## nodes: {id: Vector2}; edges: {id: {a, b, pts: PackedVector2Array, width_px}}。
## 返回 {node_id: Array[PackedVector2Array]} —— 每个路口要补的填充块。
static func build_junctions(nodes: Dictionary, edges: Dictionary,
		fillet_of_width: float = 0.5) -> Dictionary:
	var inc := {}                     # nid -> [{dir, half}]
	for eid in edges:
		var e: Dictionary = edges[eid]
		var pts: PackedVector2Array = e["pts"]
		if pts.size() < 2:
			continue
		var half := maxf(float(e.get("width_px", 2.0)), 2.0) * 0.5
		var na := String(e.get("a", ""))
		var nb := String(e.get("b", ""))
		if nodes.has(na):
			_inc_add(inc, na, pts[0].direction_to(pts[1]), half)
		if nodes.has(nb):
			_inc_add(inc, nb,
				pts[pts.size() - 1].direction_to(pts[pts.size() - 2]), half)

	var out := {}
	for nid in inc:
		var list: Array = inc[nid]
		if list.size() < 2:
			continue                   # 尽头: 没有缺口
		var pos: Vector2 = nodes[nid]
		var half := 0.0
		for it in list:
			half = maxf(half, float(it["half"]))
		var r := half * fillet_of_width
		var reach := half + r               # 圆心距 = (a+r)/sin(φ/2) 的分子
		list.sort_custom(func(p, q):
			return atan2(p["dir"].y, p["dir"].x) < atan2(q["dir"].y, q["dir"].x))
		var n := list.size()
		var blocks: Array = []
		for i in range(n):
			var d0: Vector2 = list[i]["dir"]
			var d1: Vector2 = list[(i + 1) % n]["dir"]
			var phi := d0.angle_to(d1)
			if phi <= 0.0:
				phi += TAU
			if phi < JUNCTION_EPS or phi > PI - FLAT_EPS:
				continue               # 近平行 / 直行: 没有缺口
			var cot_h := 1.0 / tan(phi * 0.5)
			var tang := reach * cot_h
			var cc := pos + d0.rotated(phi * 0.5) * (reach / sin(phi * 0.5))
			var t1 := pos + d0 * tang + d0.rotated(PI * 0.5) * half
			var t2 := pos + d1 * tang + d1.rotated(-PI * 0.5) * half
			var a0 := (t1 - cc).angle()
			var sweep := -(PI - phi)
			var steps := maxi(2, int(absf(sweep) / 0.18) + 1)
			var poly := PackedVector2Array([pos, t1])
			for k in range(1, steps):
				poly.append(cc + Vector2(r, 0.0).rotated(
					a0 + sweep * float(k) / float(steps)))
			poly.append(t2)
			blocks.append(poly)
		if not blocks.is_empty():
			out[nid] = blocks
	return out


static func _inc_add(inc: Dictionary, nid: String, dir: Vector2, half: float) -> void:
	if dir.length_squared() < 0.000001:
		return
	if not inc.has(nid):
		inc[nid] = []
	inc[nid].append({"dir": dir.normalized(), "half": half})


## 把路口圆角块填上(在路段画完之后调, 同色叠加)。
static func draw_junctions(ci: CanvasItem, junc: Dictionary,
		color: Color = ROAD_COLOR) -> void:
	for nid in junc:
		for poly in junc[nid]:
			if (poly as PackedVector2Array).size() >= 3:
				ci.draw_colored_polygon(poly, color)


static func side_normal(side: String) -> Vector2:
	return SIDE_NORMAL.get(side, Vector2(0, 1))


## 门口小标记(观察器/编辑器共用): 在门点沿法线画一小段门。
static func draw_door(ci: CanvasItem, pos: Vector2, normal: Vector2,
		size: float, color: Color) -> void:
	var n := normal.normalized()
	var t := Vector2(-n.y, n.x)
	ci.draw_line(pos - t * size, pos + t * size, color, maxf(1.5, size * 0.4))


## 类别徽记(矢量形状), center 为锚点。
static func draw_emblem(ci: CanvasItem, center: Vector2, kind: String, base: Color) -> void:
	var c := center
	var col := base.lightened(0.6)
	match kind:
		"home":
			ci.draw_colored_polygon(PackedVector2Array([
				c + Vector2(-10, 2), c + Vector2(0, -9), c + Vector2(10, 2)]), col)
			ci.draw_rect(Rect2(c + Vector2(-5, 2), Vector2(10, 8)), col, false, 1.5)
		"shop":
			ci.draw_rect(Rect2(c + Vector2(-10, -5), Vector2(20, 7)), col, false, 1.5)
			for i in range(1, 3):
				var x := c.x - 10.0 + float(i) * 6.6667
				ci.draw_line(Vector2(x, c.y - 5), Vector2(x, c.y + 2), col, 1.0)
		"factory":
			# 厂房: 屋顶锯齿 + 烟囱
			ci.draw_rect(Rect2(c + Vector2(-10, -3), Vector2(20, 9)), col, false, 1.5)
			for i in range(1, 4):
				var x := c.x - 10.0 + float(i) * 5.0
				ci.draw_line(Vector2(x, c.y - 3), Vector2(x + 2.5, c.y - 7), col, 1.0)
			ci.draw_rect(Rect2(c + Vector2(6, -11), Vector2(3, 8)), col, false, 1.5)
		"work":
			ci.draw_line(c + Vector2(-9, 7), c + Vector2(2, -9), col, 2.0)
			ci.draw_line(c + Vector2(-2, 9), c + Vector2(9, -7), col, 2.0)
		"public":
			ci.draw_circle(c + Vector2(0, -3), 6.0, col)
			ci.draw_line(c + Vector2(0, 3), c + Vector2(0, 10), col, 2.0)
		"school":
			ci.draw_rect(Rect2(c + Vector2(-9, -6), Vector2(18, 12)), col, false, 1.5)
			ci.draw_line(c + Vector2(0, -6), c + Vector2(0, 6), col, 1.0)
		"clinic":
			ci.draw_rect(Rect2(c + Vector2(-2, -8), Vector2(4, 16)), col, true)
			ci.draw_rect(Rect2(c + Vector2(-8, -2), Vector2(16, 4)), col, true)
		_:
			ci.draw_rect(Rect2(c + Vector2(-6, -6), Vector2(12, 12)), col, false, 1.5)


static func draw_centered(ci: CanvasItem, font: Font, text: String,
		center: Vector2, font_size: int, color: Color) -> void:
	if text == "" or font == null:
		return
	var sz := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size)
	ci.draw_string(font, Vector2(center.x - sz.x * 0.5, center.y + sz.y * 0.35),
		text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, color)


## 占用角标(右上角)。scale 让角标【贴合建筑框】: 字/框/边距一起缩放。
static func draw_badge(ci: CanvasItem, font: Font, rect: Rect2, text: String,
		base: Color, fill: float, scale := 1.0) -> void:
	var fs := maxi(8, int(round(10.0 * scale)))
	var label_size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
	var box := Rect2(
		rect.position + Vector2(rect.size.x - label_size.x - 14.0 * scale,
			8.0 * scale),
		Vector2(label_size.x + 10.0 * scale, 17.0 * scale))
	var bg := base.darkened(0.15).lerp(HOT, fill)
	ci.draw_rect(box, Color(bg.r, bg.g, bg.b, 0.95), true)
	ci.draw_rect(box, Color(1, 1, 1, 0.22), false, 1.0)
	draw_centered(ci, font, text,
		Vector2(box.position.x + box.size.x * 0.5,
			box.position.y + box.size.y * 0.5), fs, Color.WHITE)


## 徽记(可缩放): 用 draw_set_transform 缩放后复用 draw_emblem。
static func draw_emblem_scaled(ci: CanvasItem, center: Vector2, kind: String,
		base: Color, scale: float) -> void:
	ci.draw_set_transform(center, 0.0, Vector2(scale, scale))
	draw_emblem(ci, Vector2.ZERO, kind, base)
	ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


## 一座矩形建筑的完整渲染(观察器路径)。编辑器对旋转 OBB 复用底层原语。
## n = 当前占用人数, cap = 容量; fill = n/cap 决定红度。
static func draw_room(ci: CanvasItem, font: Font, rect: Rect2,
		kind: String, name: String, n: int, cap: int,
		scale := 1.0, lod_name := 0.62, lod_emblem := 1.05,
		lod_badge := 0.85) -> void:
	var capacity := maxi(1, cap)
	var fill := clampf(float(n) / float(capacity), 0.0, 1.0)
	var base := kind_color(kind)
	var body := base.lerp(HOT, fill * 0.75)

	ci.draw_rect(rect, Color(body.r, body.g, body.b, 0.5 + 0.35 * fill), true)
	ci.draw_rect(rect, base.lightened(0.35).lerp(HOT_EDGE, fill), false, 2.0)

	if scale >= lod_emblem:
		draw_emblem_scaled(ci, Vector2(rect.position.x + rect.size.x * 0.5,
			rect.position.y + rect.size.y * 0.5 - 24.0 * scale), kind, base,
			scale)

	if scale >= lod_name:
		draw_centered(ci, font, name,
			Vector2(rect.position.x + rect.size.x * 0.5,
				rect.position.y + rect.size.y * 0.5),
			maxi(9, int(round(11.0 * scale))),
			Color.WHITE if n > 0 else NAME_COLOR)
	if scale >= lod_badge:
		draw_badge(ci, font, rect, "%d/%d" % [n, capacity], base, fill, scale)
