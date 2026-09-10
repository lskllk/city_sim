# map_layer.gd —— 街区渲染(读 Store.rooms / Store.canvas)。
#
# 只画背景 + 建筑矩形 + 建筑名; 只在 rooms/canvas 结构变化时重绘(带 key 缓存)。
class_name MapLayer
extends Layer2D

const BG_FILL := Color("0d1016")
const ROOM_FILL := Color("1d2531")
const ROOM_STROKE := Color("3d4a60")
const LABEL_COLOR := Color("9fb0c4")

var _key := ""


func rebuild() -> void:
	var w := Protocol.num(Store.canvas.get("w"), 1280.0)
	var h := Protocol.num(Store.canvas.get("h"), 800.0)
	var ids := Store.rooms.keys()
	ids.sort()
	var k := "%dx%d|%s" % [w, h, ",".join(ids)]
	if k == _key:
		return
	_key = k
	queue_redraw()


func world_size() -> Vector2:
	return Vector2(
		Protocol.num(Store.canvas.get("w"), 1280.0),
		Protocol.num(Store.canvas.get("h"), 800.0)
	)


func _draw() -> void:
	var size := world_size()
	# 背景覆盖比画布更大的范围, 平移时不露底
	draw_rect(Rect2(-2000, -2000, size.x + 4000, size.y + 4000), BG_FILL)

	var font := Fonts.ui_font()
	for id in Store.rooms:
		var r: Dictionary = Store.rooms[id]
		var rect := Rect2(
			Protocol.num(r.get("x")), Protocol.num(r.get("y")),
			Protocol.num(r.get("w")), Protocol.num(r.get("h"))
		)
		var sb := StyleBoxFlat.new()
		sb.bg_color = Color(ROOM_FILL.r, ROOM_FILL.g, ROOM_FILL.b, 0.35)
		sb.set_corner_radius_all(6)
		sb.set_border_width_all(2)
		sb.border_color = ROOM_STROKE
		draw_style_box(sb, rect)

		var name := Protocol.s(r.get("name", id), id)
		draw_centered(font, name, Vector2(rect.position.x + rect.size.x * 0.5, rect.position.y + 12.0), 11, LABEL_COLOR)


## 命中测试: 返回包含该世界点的 location id, 否则 ""。
func hit_test(p: Vector2) -> String:
	for id in Store.rooms:
		var r: Dictionary = Store.rooms[id]
		var x := Protocol.num(r.get("x"))
		var y := Protocol.num(r.get("y"))
		var w := Protocol.num(r.get("w"))
		var h := Protocol.num(r.get("h"))
		if p.x >= x and p.x <= x + w and p.y >= y and p.y <= y + h:
			return id
	return ""
