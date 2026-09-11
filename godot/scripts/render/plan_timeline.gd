# plan_timeline.gd —— 计划表时间线(只读 viz)。
#
# 一条横向等比例时间轴, 每个 NPC 一行:
#   - 已走过的时间线灰色, 还没走的蓝色;
#   - 同一时刻只画【一个圈】(按聚合状态着色), 多项用小角标计数;
#   - 悬浮该圈 → 列出该时刻的全部任务。
# 数据全部来自 Store(snapshot 只读镜像), 不计算任何 simulation。
# 对应 docs/plan_timeline_viz.md。
class_name PlanTimeline
extends Control

const DAY_TICKS := 1440.0
const COL_BG := Color("0b0f16")
const COL_ELAPSED := Color("9aa0a6")
const COL_REMAIN := Color("1e88e5")
const COL_ACTIVE := Color("ffb300")
const COL_DROP := Color("c0392b")
const COL_AXIS := Color("455065")
const COL_TEXT := Color("b9c2d6")
const COL_SEL := Color("6fb7ff")

const MARGIN_L := 78.0
const MARGIN_R := 14.0
const TOP := 24.0
const ROW_H := 26.0
const NODE_R := 4.5

var _hover_pos := Vector2(-9999.0, -9999.0)
var _hover: Dictionary = {}


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	clip_contents = true
	Store.snapshot_applied.connect(queue_redraw)
	Store.selection_changed.connect(queue_redraw)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		_hover_pos = (event as InputEventMouseMotion).position
		queue_redraw()


func _draw() -> void:
	_hover = {}
	draw_rect(Rect2(Vector2.ZERO, size), COL_BG, true)
	var font := get_theme_default_font()
	var fs := get_theme_default_font_size()
	if font == null or size.x < 120.0:
		return
	# 没选中 NPC → 只给提示, 不画时间线
	if Store.sel_kind != "npc" or Store.sel_npc == "":
		_hint(font, fs)
		return
	var x0 := MARGIN_L
	var x1 := size.x - MARGIN_R
	if x1 <= x0 + 20.0:
		return
	var span: float = x1 - x0
	var day_start := float(int(Store.tick / 1440) * 1440)
	var frac: float = clampf((float(Store.tick) - day_start) / DAY_TICKS, 0.0, 1.0)
	var now_x: float = x0 + frac * span

	_draw_axis(font, fs, x0, x1, span)
	_draw_row(font, fs, Store.sel_npc, Store.npc(Store.sel_npc),
		x0, x1, span, day_start, now_x, TOP)
	draw_line(Vector2(now_x, TOP - 6.0), Vector2(now_x, size.y - 4.0),
		Color(1, 1, 1, 0.25), 1.0)
	_draw_hover_tip(font, fs)


func _hint(font: Font, fs: int) -> void:
	var txt := "点建筑 → 右侧选人 → 这里显示他的计划时间线"
	var sz := font.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
	draw_string(font, Vector2((size.x - sz.x) * 0.5, size.y * 0.5),
		txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(COL_TEXT, 0.6))


func _draw_axis(font: Font, fs: int, x0: float, x1: float, span: float) -> void:
	for hr in range(0, 25, 3):
		var x: float = x0 + (float(hr * 60) / DAY_TICKS) * span
		draw_line(Vector2(x, TOP - 6.0), Vector2(x, size.y - 4.0),
			Color(COL_AXIS, 0.30), 1.0)
		var label := "%02d" % hr
		draw_string(font, Vector2(x - 7.0, TOP - 9.0), label,
			HORIZONTAL_ALIGNMENT_LEFT, -1, maxi(fs - 3, 8), Color(COL_TEXT, 0.65))


func _draw_row(font: Font, fs: int, id: String, n: Dictionary,
		x0: float, x1: float, span: float, day_start: float,
		now_x: float, y: float) -> void:
	if n.is_empty():
		return
	var selected := Store.sel_kind == "npc" and Store.sel_npc == id
	draw_string(font, Vector2(6.0, y + 4.0), Protocol.s(n.get("name", id)),
		HORIZONTAL_ALIGNMENT_LEFT, int(MARGIN_L - 12.0), fs,
		COL_SEL if selected else COL_TEXT)

	# 底轨 + 灰(已走) / 蓝(未走)
	draw_line(Vector2(x0, y), Vector2(x1, y), Color(COL_AXIS, 0.45), 2.0)
	draw_line(Vector2(x0, y), Vector2(now_x, y), COL_ELAPSED, 3.0)
	draw_line(Vector2(now_x, y), Vector2(x1, y), COL_REMAIN, 3.0)
	draw_circle(Vector2(now_x, y), 3.0, Color.WHITE)

	# 按时刻分组: 同一 at_tick 只画一个圈
	var plan := Protocol.as_array(n.get("plan", []))
	var groups: Dictionary = {}
	var order: Array = []
	for e in plan:
		var d := Protocol.as_dict(e)
		var at := Protocol.num(d.get("at_tick"), -1.0)
		if at < 0.0:
			continue
		var x: float = x0 + clampf((at - day_start) / DAY_TICKS, 0.0, 1.0) * span
		var key := int(round(x))
		if not groups.has(key):
			groups[key] = []
			order.append(key)
		groups[key].append({"x": x, "entry": d})
	for key in order:
		var arr: Array = groups[key]
		_draw_group(Vector2(arr[0]["x"], y), arr)


func _group_status(entries: Array) -> String:
	var statuses := {}
	for e in entries:
		statuses[Protocol.s((e as Dictionary)["entry"].get("status", "pending"))] = true
	if statuses.has("active"):
		return "active"
	if statuses.has("pending"):
		return "pending"
	if statuses.has("dropped") and not statuses.has("done"):
		return "dropped"
	return "done"


func _draw_group(pos: Vector2, entries: Array) -> void:
	match _group_status(entries):
		"dropped":
			draw_line(pos + Vector2(-4, -4), pos + Vector2(4, 4), COL_DROP, 2.0)
			draw_line(pos + Vector2(-4, 4), pos + Vector2(4, -4), COL_DROP, 2.0)
		"pending":
			draw_arc(pos, NODE_R, 0.0, TAU, 16, COL_REMAIN, 2.0, true)
		"active":
			draw_circle(pos, NODE_R, COL_ACTIVE)
			draw_arc(pos, NODE_R + 3.0, 0.0, TAU, 18,
				Color(COL_ACTIVE, 0.5), 1.5, true)
		_:
			draw_circle(pos, NODE_R, COL_ELAPSED)
	if entries.size() > 1:
		# 同刻多项: 外圈 + 角标数字
		draw_arc(pos, NODE_R + 2.0, 0.0, TAU, 18, Color(COL_TEXT, 0.9), 1.0, true)
		var font := get_theme_default_font()
		if font != null:
			draw_string(font, pos + Vector2(7.0, -6.0), str(entries.size()),
				HORIZONTAL_ALIGNMENT_LEFT, -1, 9, COL_TEXT)
	if _hover_pos.distance_to(pos) <= 9.0:
		_hover = {"pos": pos, "entries": entries}


func _itype(target: String) -> String:
	var e := Store.entity(target)
	return Protocol.s(e.get("item_type", "")) if not e.is_empty() else ""


func _draw_hover_tip(font: Font, fs: int) -> void:
	if _hover.is_empty():
		return
	var entries: Array = _hover["entries"]
	var first: Dictionary = Protocol.as_dict(entries[0]["entry"])
	var at := int(Protocol.num(first.get("at_tick"), 0.0))
	var minute := ((at % 1440) + 1440) % 1440
	var lines := PackedStringArray()
	if entries.size() == 1:
		var t0 := Protocol.s(first.get("target", ""))
		lines.append("%02d:%02d  %s" % [minute / 60, minute % 60,
			Zh.action_text(Protocol.s(first.get("intent", "")),
				Store.name_of(t0), _itype(t0))])
	else:
		lines.append("%02d:%02d  %d 项" % [minute / 60, minute % 60, entries.size()])
	for e in entries:
		var d := Protocol.as_dict((e as Dictionary)["entry"])
		var target := Protocol.s(d.get("target", ""))
		lines.append("· %s（%s）" % [
			Zh.action_text(Protocol.s(d.get("intent", "")),
				Store.name_of(target), _itype(target)),
			_status_zh(Protocol.s(d.get("status", "")))])
	var pad := 8.0
	var lh := float(fs) + 4.0
	var w := 0.0
	for l in lines:
		w = maxf(w, font.get_string_size(l, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x)
	var box := Vector2(w + pad * 2.0, lh * float(lines.size()) + pad * 2.0)
	var pos: Vector2 = _hover["pos"] + Vector2(10.0, -box.y - 8.0)
	if pos.x + box.x > size.x - 4.0:
		pos.x = size.x - box.x - 4.0
	if pos.y < 4.0:
		pos.y = _hover["pos"].y + 12.0
	draw_rect(Rect2(pos, box), Color("121826"), true)
	draw_rect(Rect2(pos, box), Color("2b3550"), false, 1.0)
	for i in lines.size():
		draw_string(font, pos + Vector2(pad, pad + float(i + 1) * lh - 5.0),
			lines[i], HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color("c9d4e6"))


func _status_zh(status: String) -> String:
	match status:
		"done":
			return "已完成"
		"active":
			return "进行中"
		"dropped":
			return "已跳过"
		_:
			return "未开始"
