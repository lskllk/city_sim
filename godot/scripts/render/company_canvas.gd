# company_canvas.gd —— 公司抽象画布(实时, 只读)。
#
# 用户要的: "点入公司 → 内部的人都在店内持有实际位置, 显示员工在哪里,
#            显示顾客排队情况"。这里画的是**抽象空间**(不是地图):
#     每个【销售前台】= 一条线路 = 一个方框(有人守 = 亮, 没人 = 灰)
#     守台的员工 = 框里的圆点 + 名字
#     排队的顾客 = 框右侧一列小点(按先后顺序)
# HUD: 公司名 / 现金 / 启事 / 在岗 / 排队
#
# 铁律: 只读 Store 镜像, 不计算 simulation(前台数、在岗、排队都是后端给的)。
extends Control

const C_BG := Color(0.06, 0.07, 0.09, 0.92)
const C_SLOT := Color(0.16, 0.18, 0.22)
const C_SLOT_ON := Color(0.14, 0.26, 0.18)
const C_EDGE := Color("6fb7ff")
const C_STAFF := Color("7fe0a8")
const C_QUEUE := Color("ffb347")
const C_TEXT := Color(0.9, 0.93, 0.97)
const C_DIM := Color("7f8ea3")

var _shop := ""            # 当前画布的公司主店(建筑 id)
var _company := ""


func setup(shop_id: String) -> void:
	var bid := Store.building_of(shop_id) if shop_id != "" else ""
	_shop = bid
	_company = Protocol.s(Store.room(bid).get("company", "")) if bid != "" else ""
	visible = _company != ""
	queue_redraw()


func _process(_delta: float) -> void:
	if visible and _company != "":
		queue_redraw()


func _draw() -> void:
	if _company == "":
		return
	var font := get_theme_default_font()
	if font == null:
		return
	var comp := _company_data()
	var econ := Store.economy
	var counters := _counters_of(_shop)
	var queues := Protocol.as_dict(econ.get("queues", {}))
	var queued: Array = Protocol.as_array(queues.get(_shop, []))
	# 兜底: company.shop 可能不是我们选中的那栋楼(一家公司可能有好几家店)
	if counters.is_empty():
		for sh in Protocol.as_array(comp.get("shops", [])):
			counters = _counters_of(Protocol.s(sh))
			if not counters.is_empty():
				_shop = Protocol.s(sh)
				break

	var pad := 12.0
	var w := size.x - pad * 2.0
	var box := Rect2(Vector2(pad, pad), Vector2(w, 64.0))
	draw_rect(box, C_BG, true)
	draw_rect(box, C_EDGE, false, 1.5)
	draw_string(font, box.position + Vector2(10, 22),
		"%s · 现金 ¥%.0f" % [Protocol.s(comp.get("name", _company)), 
			Protocol.num(comp.get("cash", 0.0))],
		HORIZONTAL_ALIGNMENT_LEFT, -1, 15, C_TEXT)
	var hire := "招聘：停" if not bool(comp.get("hiring_open", false)) else \
		"招聘：%d 人 @ ¥%.0f/时" % [int(Protocol.num(comp.get("hiring_slots", 0))),
			Protocol.num(comp.get("wage_per_hour", 0.0))]
	draw_string(font, box.position + Vector2(10, 42), hire + "     营业 " +
		"%02d:%02d - %02d:%02d" % [
			int(Protocol.num(comp.get("open_minute", 0))) / 60,
			int(Protocol.num(comp.get("open_minute", 0))) % 60,
			int(Protocol.num(comp.get("close_minute", 0))) / 60,
			int(Protocol.num(comp.get("close_minute", 0))) % 60],
		HORIZONTAL_ALIGNMENT_LEFT, -1, 12, C_DIM)

	# —— 线路(每个前台一格) ——
	var y := box.position.y + box.size.y + 18.0
	draw_string(font, Vector2(pad + 4, y), "线路 %d 条 · 排队 %d 人" % [
		counters.size(), queued.size()], HORIZONTAL_ALIGNMENT_LEFT, -1, 13, C_DIM)
	y += 14.0
	var cell := Vector2(maxf(120.0, w / maxf(1.0, float(maxi(1, counters.size()))) - 10.0), 96.0)
	for i in counters.size():
		var cid := String(counters[i])
		var staff_id := _staff_at(cid)
		var r := Rect2(Vector2(pad + i * (cell.x + 10.0), y), cell)
		draw_rect(r, C_SLOT_ON if staff_id != "" else C_SLOT, true)
		draw_rect(r, C_STAFF if staff_id != "" else C_DIM, false, 1.5)
		draw_string(font, r.position + Vector2(8, 18), "前台 %d" % (i + 1),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 12, C_DIM)
		if staff_id != "":
			var c := r.position + Vector2(r.size.x * 0.5, r.size.y * 0.55)
			draw_circle(c, 9.0, C_STAFF)
			draw_string(font, c + Vector2(-30, 26), Store.name_of(staff_id),
				HORIZONTAL_ALIGNMENT_CENTER, 60.0, 12, C_TEXT)
		else:
			draw_string(font, r.position + Vector2(8, r.size.y * 0.6),
				"（没人守台）", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, C_DIM)
	# 排队: 按顺序画在人最多的那条线右侧(抽象: 一条队按先后排开)
	var qy := y + cell.y * 0.5
	for i in queued.size():
		var p := Vector2(pad + counters.size() * (cell.x + 10.0) + 14.0 + i * 16.0, qy)
		if p.x > size.x - 10.0:
			break
		draw_circle(p, 5.0, C_QUEUE)
	if queued.size() > 0:
		draw_string(font, Vector2(pad + counters.size() * (cell.x + 10.0) + 14.0, qy - 14),
			"排队", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, C_QUEUE)


func _company_data() -> Dictionary:
	for c in Store.companies:
		var d: Dictionary = c
		if Protocol.s(d.get("id", "")) == _company:
			return d
	# 退一步: 用 hello.companies(结构一样)
	for c in Protocol.as_array(Store.companies):
		var d2: Dictionary = c
		if Protocol.s(d2.get("id", "")) == _company:
			return d2
	return {}


func _counters_of(shop: String) -> Array:
	var out: Array = []
	for e in Store.entities.values():
		var d: Dictionary = e
		if Protocol.s(d.get("item_type", "")) == "station_counter" \
				and Protocol.s(d.get("loc", "")) == shop:
			out.append(Protocol.s(d.get("id", "")))
	return out


## 这个台此刻是谁在守?(看 NPC 的 work 绑定 + 他是不是正站在那)
func _staff_at(counter_id: String) -> String:
	for pid in Store.npcs:
		var w := Protocol.as_dict(Protocol.as_dict(Store.npc(pid)).get("work", {}))
		if Protocol.s(w.get("station", "")) == counter_id:
			return String(pid)
	return ""
