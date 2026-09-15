# page_location.gd —— 建筑详情(观察器)。
#
# 模板【按建筑类型绑定】(用户定的口径, 和编辑器同一套):
#   商铺 shop → 公司(可进"公司运营"页) + 线路(前台/在岗/排队) + 在店里的人
#               + 物件(含【在售库存】与【工位/销售前台】—— 交易靠它)
#   住宅 home → 楼层 + 住户 + 家里的东西
#   其它      → 权限 + 在场的人 (市场多一行"无限库存 · 只有公司能采购")
#
# 招牌信息【已从详情移除】(那是经营手段 → 归公司运营页的"广告", 后续做)。
#
# 铁律: 页面常驻; bind() 只改数值, 不重建控件(见 ui_page.gd)。
class_name InspLocationPage
extends UiPage

const PERSON_ROW := preload("res://scenes/components/person_row.tscn")
const ITEM_ROW := preload("res://scenes/components/item_row.tscn")

var _header: Control
var _floor_sec: Control
var _floor_sel: OptionButton
var _cur_bid := ""
var _cur_floor := 1
var _room: Dictionary = {}

var _perm: Label
var _cap: Label
var _cap_row: Control
var _p_sec: Control
var _p: UiList
var _p_empty: Label
var _i_sec: Control
var _i: UiList
var _i_empty: Label
var _comp_sec: Control
var _comp_body: VBoxContainer
var _lane_sec: Control
var _lane_body: VBoxContainer


func build() -> void:
	_header = UiKit.header(self)

	# 楼层(仅住宅显示)
	_floor_sec = UiKit.section(self, "楼层")
	_floor_sec.visible = false
	_floor_sel = OptionButton.new()
	_floor_sel.item_selected.connect(_on_floor_picked)
	_floor_sec.body().add_child(_floor_sel)

	var a: VBoxContainer = UiKit.section(self, "权限").body()
	_perm = UiKit.kv(a, "进入权限")
	_cap = UiKit.kv(a, "容量")
	_cap_row = _cap.get_parent()

	# 公司(商铺): 摘要 + 进"公司运营"页
	_comp_sec = UiKit.section(self, "公司")
	_comp_body = _comp_sec.body()

	# 线路(商铺): 前台 = 销售位; 有员工守着才开台
	_lane_sec = UiKit.section(self, "线路")
	_lane_body = _lane_sec.body()

	# 在店里的人(全部类型都显示)
	_p_sec = UiKit.section(self, "在店里的人")
	UiKit.column_header(_p_sec.body(), [
		["姓名", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["年龄", UiKit.W_AGE, HORIZONTAL_ALIGNMENT_RIGHT],
		["角色", UiKit.W_ROLE, HORIZONTAL_ALIGNMENT_LEFT],
		["当前行为", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["生命", UiKit.W_HP, HORIZONTAL_ALIGNMENT_LEFT],
	])
	_p = UiList.new(_p_sec.body(), PERSON_ROW)
	_p_empty = UiKit.muted(_p_sec.body(), "无人")

	# 物件(在售库存 / 工位 / 货架) —— 商铺也有: 交易靠工位
	_i_sec = UiKit.section(self, "物件")
	UiKit.column_header(_i_sec.body(), [
		["名称", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["数量", UiKit.W_QTY, HORIZONTAL_ALIGNMENT_RIGHT],
		["价格", UiKit.W_PRICE, HORIZONTAL_ALIGNMENT_LEFT],
		["使用者", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
	])
	_i = UiList.new(_i_sec.body(), ITEM_ROW)
	_i_empty = UiKit.muted(_i_sec.body(), "无")


func bind(id: String) -> void:
	var room := Store.room(id)
	if room.is_empty():
		return
	_room = room
	var bid := Store.building_of(id)
	if bid != _cur_bid:
		_cur_bid = bid
		_cur_floor = 1
	var multi := Store.is_multi(bid)
	var is_home := Zh.kind_zh(Protocol.s(room.get("kind", ""))) == "住所"
	_floor_sec.visible = multi and is_home
	if _floor_sec.visible:
		var nf := Store.floor_units(bid)
		_cur_floor = clampi(_cur_floor, 1, nf)
		if _floor_sel.item_count != nf:
			_floor_sel.clear()
			for i in range(1, nf + 1):
				_floor_sel.add_item("第 %d 层" % i)
		if _floor_sel.selected != _cur_floor - 1:
			_floor_sel.select(_cur_floor - 1)
	if is_home:
		Store.set_floor(_cur_floor)
	_render()


func _on_floor_picked(i: int) -> void:
	_cur_floor = i + 1
	Store.set_floor(_cur_floor)
	_render()


func _render() -> void:
	var bid := _cur_bid
	var multi := Store.is_multi(bid)
	var unit := Store.unit_of(bid, _cur_floor)
	var unit_room := Store.room(unit)
	if unit_room.is_empty():
		unit_room = _room
	var kind := Protocol.s(_room.get("kind", ""))
	var is_home := Zh.kind_zh(kind) == "住所"
	# 商铺: 看整栋(前台/货架摆在店里, 不分层); 住宅: 看当前层
	var people := _at(Store.npcs, unit if is_home else bid)
	var items := _at(Store.entities, unit if is_home else bid)

	var cap := int(Protocol.num(unit_room.get("capacity"), 0.0))
	var title := Protocol.s(_room.get("name", bid))
	if is_home and multi:
		title = "%s · %d层" % [title, _cur_floor]
	_header.set_header(title, "%s · %d 人 · %d 物件" % [
		Zh.kind_zh(kind), people.size(), items.size()])

	_render_company(kind, bid)
	_render_lane(kind, bid)

	_perm.text = InspData.access_text(unit_room)
	_cap_row.visible = not bool(unit_room.get("public", true))
	_cap.text = "%d 人" % cap

	# --- 在店里的人(商铺: 店员/顾客; 住宅: 住户) ---
	_p_sec.set_title(("住户 %d" if is_home else "在店里的人 %d") % people.size())
	_p_empty.visible = people.is_empty()
	for i in people.size():
		var k := String(people[i])
		var n := Store.npc(k)
		var age := Protocol.num(n.get("age"), -1.0)
		var hp := clampf(Protocol.num(
			Protocol.as_dict(n.get("signals", {})).get("hp"), 1.0), 0.0, 1.0)
		var work := Protocol.as_dict(n.get("work", {}))
		var act := Protocol.s(n.get("activity", ""))
		if Protocol.s(work.get("station", "")) != "" and act == "working":
			act = "在岗"
		elif Protocol.s(work.get("station", "")) != "":
			act = "店员·不在岗"
		_p.row(i).set_row(k, String(n.get("name", k)),
			"—" if age < 0.0 else str(int(age)),
			Zh.role_zh(Protocol.s(n.get("role", ""))), act, hp)
	_p.trim(people.size())

	# --- 物件: 在售(含库存) + 工位/销售前台 ---
	_i_sec.visible = true
	_i_sec.set_title("物件 %d" % items.size())
	_i_empty.visible = items.is_empty()
	for i in items.size():
		var e := Store.entity(String(items[i]))
		var st := int(Protocol.num(e.get("stock", 1.0)))
		var pr := Protocol.num(e.get("price", 0.0))
		var lane := Store.entity(String(items[i]))
		var qty := "∞" if st < 0 else str(st)
		if Protocol.s(e.get("item_type", "")) == "station_counter":
			qty = "工位"                      # 销售前台: 交易靠它
		_i.row(i).set_row(String(items[i]), String(e.get("name", items[i])),
			qty, "—" if pr <= 0.0 else "¥%d" % int(pr),
			Store.name_of(Protocol.s(e.get("claimed_by", ""))))
	_i.trim(items.size())


## 公司块(商铺): 摘要 + 一个按钮进"公司运营"页
func _render_company(kind: String, bid: String) -> void:
	for c in _comp_body.get_children():
		_comp_body.remove_child(c)
		c.queue_free()
	var cid := Protocol.s(_room.get("company", ""))
	if kind != "shop":
		_comp_sec.visible = false
		return
	_comp_sec.visible = true
	if cid == "":
		_comp_sec.set_title("公司 · 未注册")
		UiKit.muted(_comp_body, "没注册公司的店【不能卖、不能招人】")
		var name_edit := LineEdit.new()
		name_edit.placeholder_text = "%s 公司" % Protocol.s(_room.get("name", bid))
		_comp_body.add_child(name_edit)
		var reg := Button.new()
		reg.text = "注册公司（现金 ¥1000）"
		reg.pressed.connect(func() -> void:
			Commands.cmd("register_company", {"location": bid,
				"name": name_edit.text.strip_edges()})
		)
		_comp_body.add_child(reg)
		return
	var comp := Store.company(cid)
	_comp_sec.set_title("公司 · %s" % Protocol.s(comp.get("name", cid)))
	UiKit.kv(_comp_body, "现金").text = "¥%.0f" % Protocol.num(comp.get("cash", 0.0))
	var staff: Array = Protocol.as_array(comp.get("staff", []))
	UiKit.kv(_comp_body, "员工").text = "0 人" if staff.is_empty() else \
		"%d 人：%s" % [staff.size(), ", ".join(staff.map(
			func(x): return String(Store.name_of(Protocol.s(x)))))]
	var open_m := int(Protocol.num(comp.get("open_minute", 480)))
	var close_m := int(Protocol.num(comp.get("close_minute", 1140)))
	UiKit.kv(_comp_body, "营业").text = "%02d:%02d - %02d:%02d" % [
		open_m / 60, open_m % 60, close_m / 60, close_m % 60]
	var hire_on := bool(comp.get("hiring_open", false))
	var slots := int(Protocol.num(comp.get("hiring_slots", 0)))
	UiKit.kv(_comp_body, "招聘").text = ("招 %d 人" % slots) if hire_on else "未发布"
	var go := Button.new()
	go.text = "打开公司运营（HR / 价格）"
	go.pressed.connect(func() -> void: Store.select("company", cid))
	_comp_body.add_child(go)


## 线路块(商铺): 前台 = 销售位; 有人在台前才开台
func _render_lane(kind: String, bid: String) -> void:
	for c in _lane_body.get_children():
		_lane_body.remove_child(c)
		c.queue_free()
	if kind != "shop":
		_lane_sec.visible = false
		return
	_lane_sec.visible = true
	var counters: Array = []
	for i in Store.entities.values():
		var e: Dictionary = i
		if Protocol.s(e.get("item_type", "")) == "station_counter" \
				and Store.building_of(Protocol.s(e.get("loc", ""))) == bid:
			counters.append(Protocol.s(e.get("id", "")))
	var econ := Store.economy
	var on_duty := int(Protocol.num(
		Protocol.as_dict(econ.get("on_duty", {})).get(bid, 0.0)))
	var queue: Array = Protocol.as_array(
		Protocol.as_dict(econ.get("queues", {})).get(bid, []))
	_lane_sec.set_title("线路 %d 条 · 在岗 %d · 排队 %d" % [
		counters.size(), on_duty, queue.size()])
	if counters.is_empty():
		UiKit.muted(_lane_body, "还没有销售前台 —— 没有它谁也买不到东西")
		return
	for i in counters.size():
		var cid := String(counters[i])
		var keeper := ""
		for pid in Store.npcs:
			var w := Protocol.as_dict(Protocol.as_dict(Store.npc(pid)).get("work", {}))
			if Protocol.s(w.get("station", "")) == cid:
				keeper = String(pid)
				break
		UiKit.muted(_lane_body, "前台 %d：%s" % [i + 1,
			("● " + String(Store.name_of(keeper))) if keeper != "" else "○ 没人守台"])


func _at(d: Dictionary, unit: String) -> Array:
	var out: Array = []
	for k in d:
		var rec: Dictionary = d[k]
		var loc := Protocol.s(rec.get("loc", ""))
		if loc == unit or Store.building_of(loc) == unit:
			out.append(String(k))
	out.sort()
	return out
