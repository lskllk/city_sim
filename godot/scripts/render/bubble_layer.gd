# bubble_layer.gd —— NPC 头顶气泡层(屏幕坐标)。
#
# 铁律: 本层【只渲染】—— 台词是后端从真实内部状态长出来的(语义层 npc/semantic.py),
# 前端一个字都不改。谁冒泡 / 冒到什么时候, 全由快照里的 bubble{text, until, kind}
# 决定; 这里只负责画出来、到点消失。
#
# 零节点: 不用 PanelContainer, 走 draw_style_box(样式) + draw_multiline_string;
# 屏幕坐标 + 固定像素字号 → 缩放地图时气泡大小不变、始终清晰
# (与 entity_layer 画圆点同一策略)。
class_name BubbleLayer
extends Control

const FONT_PX := 11
const PAD_X := 7.0
const PAD_Y := 4.0
const MAX_W := 220.0          # 长文本自动换行宽度
const GAP := 16.0             # 气泡底边离头顶的距离(像素)
const FADE_TICKS := 10.0      # 最后这么多 tick 淡出

## 气泡样式(深底/圆角/描边)。在代码里建 —— 不依赖外部 .tres,
## 少一个“资源找不到就整层挂掉”的失败面。
var _style: StyleBoxFlat
var _font: Font
var camera: WorldCamera = null
var entity_layer: Control = null      # 可选: 在途的人要沿路点插值取位置


func setup(cam: WorldCamera, ents: Control = null) -> void:
	camera = cam
	entity_layer = ents


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_style = StyleBoxFlat.new()
	_style.bg_color = Color("0f151d", 0.94)
	_style.border_color = Color("4d6185", 1.0)
	_style.set_border_width_all(1)
	_style.set_corner_radius_all(6)
	_style.content_margin_left = PAD_X
	_style.content_margin_right = PAD_X
	_style.content_margin_top = PAD_Y
	_style.content_margin_bottom = PAD_Y


func _process(_delta: float) -> void:
	# 气泡会自己过期(until) —— 即使没有新快照也要重画让它消失。
	queue_redraw()


func _draw() -> void:
	if camera == null or Store.npcs.is_empty():
		return
	if _font == null:
		_font = get_theme_default_font()
		if _font == null:
			return
	var now := float(Store.tick)
	for pid in Store.npcs:
		var n := Store.npc(pid)
		var b := Protocol.as_dict(n.get("bubble", {}))
		if b.is_empty():
			continue
		var text := Protocol.s(b.get("text", ""))
		if text == "":
			continue
		var until := Protocol.num(b.get("until"), 0.0)
		if now >= until:
			continue
		var head = _head_pos(pid, n)
		if head == null:
			continue
		var sp: Vector2 = head
		if sp.x < -240.0 or sp.y < -120.0 \
				or sp.x > size.x + 240.0 or sp.y > size.y + 120.0:
			continue                      # 屏幕外不画
		_draw_bubble(sp, text, clampf((until - now) / FADE_TICKS, 0.0, 1.0))


## 头顶位置(屏幕坐标)。在途 → 沿路点插值; 在建筑里 → 建筑中心。
func _head_pos(pid: String, n: Dictionary):
	var tv := Protocol.as_dict(n.get("travel", null))
	if entity_layer != null and Protocol.as_array(tv.get("waypoints", [])).size() >= 2:
		return camera.world_to_screen(entity_layer.world_pos_of(pid))
	var loc := Protocol.s(n.get("loc", ""))
	var b := Protocol.as_dict(
		Protocol.as_dict(Store.map.get("buildings", {})).get(loc, {}))
	if not b.is_empty():
		var c := Protocol.as_array(b.get("center", []))
		if c.size() >= 2:
			return camera.world_to_screen(
				Vector2(Protocol.num(c[0]), Protocol.num(c[1])))
	var r := Store.room(loc)
	if r.is_empty():
		return null
	return camera.world_to_screen(Vector2(
		Protocol.num(r.get("x")) + Protocol.num(r.get("w")) * 0.5,
		Protocol.num(r.get("y")) + Protocol.num(r.get("h")) * 0.5))


func _draw_bubble(head: Vector2, text: String, alpha: float) -> void:
	var sz := _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, MAX_W, FONT_PX)
	var box := Rect2(0.0, 0.0, minf(sz.x, MAX_W) + PAD_X * 2.0,
		sz.y + PAD_Y * 2.0)
	box.position = Vector2(head.x - box.size.x * 0.5,
		head.y - GAP - box.size.y)
	draw_style_box(_style, box)
	draw_multiline_string(_font,
		box.position + Vector2(PAD_X, PAD_Y + sz.y * 0.8), text,
		HORIZONTAL_ALIGNMENT_LEFT, box.size.x - PAD_X * 2.0, FONT_PX, -1,
		Color(0.84, 0.89, 0.95, alpha))
