# company_monitor.gd —— 公司运营弹窗的【实时监控】页(抽象画布, 只读)。
#
# 用户要的效果:
#   · 每一排 = 一个【工位/销售前台】; 工位上有员工就占位(绿点 + 名字), 没人 = 灰
#   · 工位"后面"是顾客排队 —— 顾客画成工位右侧的一排小点
#   · 多个工位就往下排(一行一个)
#   · 通用设施(马桶等)单独一栏, 显示谁在用(claimed_by)
#
# 铁律: 只读 Store 镜像, 不计算 simulation。
#   · 工位数/位置 = Store.entities 里的 station_counter
#   · 谁在守台     = NPC 的 work.station
#   · 排队         = Store.economy.queues[shop](后端每帧给的 FIFO)
#   · 设施占用     = 实体 claimed_by
#
# 关于排队: 后端是【一个店一条 FIFO】(多个前台 = 多个服务位, 从队首取人)。
# 画面上把队列【轮转分摊】到各在岗工位后面 —— 纯展示, 让"多条线路"看起来
# 是并排的; 不影响任何模拟。
extends Control

const C_BG := Color(0.06, 0.07, 0.09, 0.92)
const C_SLOT := Color("1b202a")
const C_SLOT_OFF := Color("14181f")
const C_EDGE := Color("6fb7ff")
const C_STAFF := Color("7fe0a8")
const C_CUST := Color("ffb347")
const C_TEXT := Color("e6edf7")
const C_DIM := Color("7a8494")

var _cid := ""
var _shop := ""


func setup(cid: String) -> void:
	_cid = cid
	_shop = ""
	var comp := Store.company(cid)
	for s in Protocol.as_array(comp.get("shops", [])):
		_shop = Protocol.s(s)
		break
	queue_redraw()


func _process(_delta: float) -> void:
	if visible:
		queue_redraw()


func _draw() -> void:
	if _cid == "":
		return
	var font := get_theme_default_font()
	if font == null:
		return
	var comp := Store.company(_cid)
	draw_rect(Rect2(Vector2.ZERO, size), C_BG, true)
	var pad := 14.0
	var y := pad

	# --- 顶部: 店名 / 现金 / 营业 / 在岗 ---
	y = _draw_head(font, comp, pad, y)

	# --- 工位行 ---
	var counters := _counters()
	var queue := _queue()
	var rows := _staff_rows(counters)
	draw_string(font, Vector2(pad, y + 12), "工位 %d · 在岗 %d · 排队 %d" % [
		counters.size(), rows.size(), queue.size()],
		HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_HEAD, C_DIM)
	y += 20.0
	if counters.is_empty():
		draw_string(font, Vector2(pad, y + 16), "还没有工位 —— 去【装修管理】摆一个销售前台",
			HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_BODY, C_DIM)
		y += 30.0
	else:
		var lines := _split_queue(queue, rows)
		for i in counters.size():
			y = _draw_counter_row(font, i, counters[i], rows, lines, pad, y)
			if y > size.y - 70.0:
				break

	# --- 设施(马桶等) ---
	y += 10.0
	_draw_facilities(font, pad, y)


func _draw_head(font: Font, comp: Dictionary, pad: float, y: float) -> float:
	var econ := Store.economy
	var on_duty := int(Protocol.num(
		Protocol.as_dict(econ.get("on_duty", {})).get(_shop, 0)))
	draw_string(font, Vector2(pad, y + 16),
		"%s" % Protocol.s(comp.get("name", _cid)),
		HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_TITLE, C_TEXT)
	draw_string(font, Vector2(pad, y + 36),
		"现金 ¥%.0f · 营业 %02d:%02d-%02d:%02d · 在岗 %d" % [
			Protocol.num(comp.get("cash", 0.0)),
			int(Protocol.num(comp.get("open_minute", 0))) / 60,
			int(Protocol.num(comp.get("open_minute", 0))) % 60,
			int(Protocol.num(comp.get("close_minute", 0))) / 60,
			int(Protocol.num(comp.get("close_minute", 0))) % 60,
			on_duty],
		HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_SMALL, C_DIM)
	return y + 46.0


func _draw_counter_row(font: Font, i: int, counter_id: String, rows: Array,
		lines: Dictionary, pad: float, y: float) -> float:
	var h := 44.0
	var box := Rect2(Vector2(pad, y), Vector2(168.0, h))
	var staff := _staff_at(counter_id)
	draw_rect(box, C_SLOT if staff != "" else C_SLOT_OFF, true)
	draw_rect(box, C_STAFF if staff != "" else C_DIM, false, 1.5)
	draw_string(font, box.position + Vector2(10, 18), "工位 %d" % (i + 1),
		HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_HEAD, C_DIM)
	if staff != "":
		draw_circle(box.position + Vector2(16, h * 0.66), 7.0, C_STAFF)
		draw_string(font, box.position + Vector2(30, h * 0.66 + 5),
			Store.name_of(staff), HORIZONTAL_ALIGNMENT_LEFT, -1,
			UiTheme.FS_BODY, C_TEXT)
	else:
		draw_string(font, box.position + Vector2(10, h * 0.66 + 5), "空岗",
			HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_BODY, C_DIM)

	# 这一排后面的顾客(轮转分摊; 没在岗 → 这排没有队)
	var line: Array = Protocol.as_array(lines.get(i, []))
	var cx := box.position.x + box.size.x + 18.0
	for k in line.size():
		var p := Vector2(cx + k * 18.0, box.position.y + h * 0.5)
		if p.x > size.x - pad:
			break
		draw_circle(p, 6.0, C_CUST)
	if staff != "" and line.size() > 0:
		draw_string(font, Vector2(cx, box.position.y + 12),
			"排队", HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_HEAD, C_CUST)
	return y + h + 8.0


func _draw_facilities(font: Font, pad: float, y: float) -> void:
	var f := _facilities()
	draw_string(font, Vector2(pad, y + 12), "设施 %d" % f.size(),
		HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_HEAD, C_DIM)
	y += 20.0
	if f.is_empty():
		draw_string(font, Vector2(pad, y + 16), "没有设施 —— 去【装修管理】加一个",
			HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_BODY, C_DIM)
		return
	var w := 132.0
	var h := 38.0
	for i in f.size():
		var col := i % 5
		var row := i / 5
		var r := Rect2(Vector2(pad + col * (w + 8.0), y + row * (h + 8.0)),
			Vector2(w, h))
		if r.position.y > size.y - 10.0:
			break
		var users := _users_of(String(f[i]))
		draw_rect(r, C_SLOT if users.is_empty() else Color("1d2a1f"), true)
		draw_rect(r, C_DIM if users.is_empty() else C_STAFF, false, 1.5)
		var e := Store.entity(String(f[i]))
		draw_string(font, r.position + Vector2(8, 15),
			Protocol.s(e.get("name", f[i])),
			HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_BODY, C_TEXT)
		draw_string(font, r.position + Vector2(8, 30),
			"—" if users.is_empty()
			else ", ".join(users.map(func(n): return Store.name_of(n))),
			HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FS_SMALL,
			C_DIM if users.is_empty() else C_STAFF)


# --- 数据(只读镜像) ------------------------------------------------------
## 这家公司的【岗位】长什么样: 零售 = 销售前台; 制造 = 工位。
func _station_type() -> String:
	return ("station_workbench" if Protocol.s(Store.company(_cid).get(
		"kind", "retail")) == "manufacture" else "station_counter")


func _counters() -> Array:
	var st := _station_type()
	var out: Array = []
	for e in Store.entities.values():
		var d: Dictionary = e
		if Protocol.s(d.get("item_type", "")) == st \
				and Store.building_of(Protocol.s(d.get("loc", ""))) == _shop:
			out.append(Protocol.s(d.get("id", "")))
	out.sort()
	return out


func _facilities() -> Array:
	var out: Array = []
	for e in Store.entities.values():
		var d: Dictionary = e
		if Protocol.s(d.get("item_type", "")) == _station_type():
			continue
		if Store.building_of(Protocol.s(d.get("loc", ""))) != _shop:
			continue
		var tags: Array = Protocol.as_array(d.get("tags", []))
		if tags.has("fixture") or tags.has("toilet"):
			out.append(Protocol.s(d.get("id", "")))
	out.sort()
	return out


func _queue() -> Array:
	var econ := Store.economy
	var queues := Protocol.as_dict(econ.get("queues", {}))
	return Protocol.as_array(queues.get(_shop, []))


## 在岗的工位下标(有员工绑定这个台)。
func _staff_rows(counters: Array) -> Array:
	var out: Array = []
	for i in counters.size():
		if _staff_at(counters[i]) != "":
			out.append(i)
	return out


## 把一条共享队列【轮转分摊】到各在岗行 —— 纯展示。
## 没有在岗行时, 全部归第 0 行(至少能看出有人在等)。
func _split_queue(queue: Array, rows: Array) -> Dictionary:
	var out: Dictionary = {}
	if queue.is_empty():
		return out
	if rows.is_empty():
		out[0] = queue
		return out
	for k in queue.size():
		var row: int = rows[k % rows.size()]
		if not out.has(row):
			out[row] = []
		out[row].append(queue[k])
	return out


## 这个台此刻是谁在守?(NPC 的 work.station 指向它)
func _staff_at(counter_id: String) -> String:
	# 只有【此刻人真的在那个台前】(on_post)才显示; 光有工位绑定不算。
	for pid in Store.npcs:
		var n := Protocol.as_dict(Store.npc(pid))
		var w := Protocol.as_dict(n.get("work", {}))
		if bool(n.get("on_post", false)) 				and Protocol.s(w.get("station", "")) == counter_id:
			return String(pid)
	return ""


## 谁在用这件设施?(claimed_by 是后端给的占用者)
func _users_of(entity_id: String) -> Array:
	var e := Store.entity(entity_id)
	var by := Protocol.s(e.get("claimed_by", ""))
	return [] if by == "" else [by]
