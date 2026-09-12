# building_style.gd —— 建筑"资产"唯一样式真源 (single authority)。
#
# 谁用:
#   - 观察器(godot/)   : `const BuildingStyle = preload("res://scripts/render/building_style.gd")`
#   - 地图编辑器(godot_editor/) : 运行时 load 观察器项目里的同一文件, 见 building_style_loader.gd
# 这样"观察器怎么渲染, 编辑器就怎么渲染", 不再各自维护一份底色/徽记。
#
# 约束(必须自包含, 供跨项目加载):
#   - 只用 Godot 内建类型; 不 preload 项目内其它资源;
#   - 不用 class_name / autoload(跨项目加载时不注册全局类)。
# 视觉通道与 docs/building_abstraction.md 对齐:
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
## 编辑器与观察器共用(屏幕坐标, width_px = 路宽 × zoom)。
static func draw_road(ci: CanvasItem, pts: PackedVector2Array, width_px: float,
		color: Color = ROAD_COLOR) -> void:
	if pts.size() < 2:
		return
	var w := maxf(width_px, 2.0)
	for i in range(pts.size() - 1):
		ci.draw_line(pts[i], pts[i + 1], color, w, true)
	for p in pts:
		ci.draw_circle(p, w * 0.5, color)


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


static func draw_badge(ci: CanvasItem, font: Font, rect: Rect2, text: String,
		base: Color, fill: float) -> void:
	var label_size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 10)
	var box := Rect2(rect.position + Vector2(rect.size.x - label_size.x - 14.0, 8.0),
		Vector2(label_size.x + 10.0, 17.0))
	var bg := base.darkened(0.15).lerp(HOT, fill)
	ci.draw_rect(box, Color(bg.r, bg.g, bg.b, 0.95), true)
	ci.draw_rect(box, Color(1, 1, 1, 0.22), false, 1.0)
	draw_centered(ci, font, text,
		Vector2(box.position.x + box.size.x * 0.5,
			box.position.y + box.size.y * 0.5), 10, Color.WHITE)


## 一座矩形建筑的完整渲染(观察器路径)。编辑器对旋转 OBB 复用底层原语。
## n = 当前占用人数, cap = 容量; fill = n/cap 决定红度。
static func draw_room(ci: CanvasItem, font: Font, rect: Rect2,
		kind: String, name: String, n: int, cap: int) -> void:
	var capacity := maxi(1, cap)
	var fill := clampf(float(n) / float(capacity), 0.0, 1.0)
	var base := kind_color(kind)
	var body := base.lerp(HOT, fill * 0.75)

	ci.draw_rect(rect, Color(body.r, body.g, body.b, 0.5 + 0.35 * fill), true)
	ci.draw_rect(rect, base.lightened(0.35).lerp(HOT_EDGE, fill), false, 2.0)

	if rect.size.x >= 52.0 and rect.size.y >= 52.0:
		draw_emblem(ci, Vector2(rect.position.x + rect.size.x * 0.5,
			rect.position.y + rect.size.y * 0.5 - 24.0), kind, base)

	var size := int(clampf(minf(rect.size.x, rect.size.y) / 8.0, 11.0, 18.0))
	draw_centered(ci, font, name,
		Vector2(rect.position.x + rect.size.x * 0.5,
			rect.position.y + rect.size.y * 0.5),
		size, Color.WHITE if n > 0 else NAME_COLOR)
	draw_badge(ci, font, rect, "%d/%d" % [n, capacity], base, fill)
