# map_labels.gd —— 建筑"矢量层": 在【屏幕坐标】里画。
#
# 为什么: WorldRoot 里的 Node2D 会被相机整体缩放(zoom≈0.87), 字体纹理被缩放后就发糊,
# 看起来像贴图。本层是 WorldCanvas 的普通 Control 子节点(不受相机影响), 自己把
# 世界矩形投影到屏幕再画 —— 文字/描边/角标在任何 zoom 下都是原生分辨率, 清晰。
class_name MapLabels
extends Control

const BG := Color("0d1016")
const HOT := Color("c0392b")
const HOT_EDGE := Color("ff8a7a")
const NAME_COLOR := Color("c7d2e2")
const MUTED_COLOR := Color("7f8ea3")
const DEFAULT_KIND := Color("3d4a60")

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
	for id in Store.rooms:
		var r: Dictionary = Store.rooms[id]
		var tl := camera.world_to_screen(Vector2(
			Protocol.num(r.get("x")), Protocol.num(r.get("y"))))
		var wh := Vector2(Protocol.num(r.get("w")),
			Protocol.num(r.get("h"))) * camera.zoom
		if wh.x < 6.0 or wh.y < 6.0:
			continue
		_draw_room(font, id, r, Rect2(tl, wh), int(occ.get(id, 0)))
	_draw_selection()


## 选中框(屏幕坐标, 画在建筑之上)。绿=当前 NPC 所在, 橙=意图目标, 蓝=焦点。
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
	var r := Store.room(loc_id)
	if r.is_empty():
		return
	var tl := camera.world_to_screen(Vector2(
		Protocol.num(r.get("x")), Protocol.num(r.get("y"))))
	var wh := Vector2(Protocol.num(r.get("w")),
		Protocol.num(r.get("h"))) * camera.zoom
	draw_rect(Rect2(tl, wh), Color(color.r, color.g, color.b, 0.9), false, 2.5)


func _draw_room(font: Font, id: String, r: Dictionary, rect: Rect2, n: int) -> void:
	var cap := maxi(1, int(Protocol.num(r.get("capacity"), 10.0)))
	var fill := clampf(float(n) / float(cap), 0.0, 1.0)
	var base := _kind_color(Protocol.s(r.get("kind", "")))
	var body := base.lerp(HOT, fill * 0.75)

	draw_rect(rect, Color(body.r, body.g, body.b, 0.5 + 0.35 * fill), true)
	draw_rect(rect, base.lightened(0.35).lerp(HOT_EDGE, fill), false, 2.0)

	if rect.size.x >= 52.0 and rect.size.y >= 52.0:
		_draw_emblem(rect, Protocol.s(r.get("kind", "")), base)

	var size := int(clampf(minf(rect.size.x, rect.size.y) / 8.0, 11.0, 18.0))
	var name := Protocol.s(r.get("name", id), id)
	_draw_centered(font, name,
		Vector2(rect.position.x + rect.size.x * 0.5,
			rect.position.y + rect.size.y * 0.5),
		size, Color.WHITE if n > 0 else NAME_COLOR)
	_draw_badge(font, rect, "%d/%d" % [n, cap], base, fill)


func _draw_centered(font: Font, text: String, center: Vector2,
		font_size: int, color: Color) -> void:
	if text == "":
		return
	var sz := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size)
	draw_string(font, Vector2(center.x - sz.x * 0.5, center.y + sz.y * 0.35),
		text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, color)


## 类别徽记(矢量形状)。
func _draw_emblem(rect: Rect2, kind: String, base: Color) -> void:
	var c := Vector2(rect.position.x + rect.size.x * 0.5,
		rect.position.y + rect.size.y * 0.5 - 24.0)
	var col := base.lightened(0.6)
	match kind:
		"home":
			draw_colored_polygon(PackedVector2Array([
				c + Vector2(-10, 2), c + Vector2(0, -9), c + Vector2(10, 2)]), col)
			draw_rect(Rect2(c + Vector2(-5, 2), Vector2(10, 8)), col, false, 1.5)
		"shop":
			draw_rect(Rect2(c + Vector2(-10, -5), Vector2(20, 7)), col, false, 1.5)
			for i in range(1, 3):
				var x := c.x - 10.0 + float(i) * 6.6667
				draw_line(Vector2(x, c.y - 5), Vector2(x, c.y + 2), col, 1.0)
		"work":
			draw_line(c + Vector2(-9, 7), c + Vector2(2, -9), col, 2.0)
			draw_line(c + Vector2(-2, 9), c + Vector2(9, -7), col, 2.0)
		"public":
			draw_circle(c + Vector2(0, -3), 6.0, col)
			draw_line(c + Vector2(0, 3), c + Vector2(0, 10), col, 2.0)
		"school":
			draw_rect(Rect2(c + Vector2(-9, -6), Vector2(18, 12)), col, false, 1.5)
			draw_line(c + Vector2(0, -6), c + Vector2(0, 6), col, 1.0)
		"clinic":
			draw_rect(Rect2(c + Vector2(-2, -8), Vector2(4, 16)), col, true)
			draw_rect(Rect2(c + Vector2(-8, -2), Vector2(16, 4)), col, true)
		_:
			draw_rect(Rect2(c + Vector2(-6, -6), Vector2(12, 12)), col, false, 1.5)


func _draw_badge(font: Font, rect: Rect2, text: String, base: Color, fill: float) -> void:
	var label_size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 10)
	var box := Rect2(rect.position + Vector2(rect.size.x - label_size.x - 14.0, 8.0),
		Vector2(label_size.x + 10.0, 17.0))
	var bg := base.darkened(0.15).lerp(HOT, fill)
	draw_rect(box, Color(bg.r, bg.g, bg.b, 0.95), true)
	draw_rect(box, Color(1, 1, 1, 0.22), false, 1.0)
	_draw_centered(font, text,
		Vector2(box.position.x + box.size.x * 0.5,
			box.position.y + box.size.y * 0.5), 10, Color.WHITE)


func _occupancy() -> Dictionary:
	var out := {}
	for id in Store.npcs:
		var loc := Protocol.s(Store.npcs[id].get("loc", ""))
		if loc != "":
			out[loc] = int(out.get(loc, 0)) + 1
	return out


func _kind_color(kind: String) -> Color:
	match kind:
		"home":
			return Color("7a5a3a")
		"shop":
			return Color("2f7d78")
		"work":
			return Color("8a5a34")
		"public":
			return Color("42557f")
		"school":
			return Color("6b5a8a")
		"clinic":
			return Color("3f7d8a")
		"farm":
			return Color("4f7a3a")
		_:
			return DEFAULT_KIND
