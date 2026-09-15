# page_location.gd —— 建筑详情页(常驻, 原地 bind)。
#
# 多楼层建筑: 顶部一个【楼层下拉】, 页面显示【选中楼层】的权限/人员/物件;
# 标题写成 "7 号 · 2层"。单层建筑不显示下拉(与以前一致)。
class_name InspLocationPage
extends UiPage

const PERSON_ROW := preload("res://scenes/components/person_row.tscn")
const ITEM_ROW := preload("res://scenes/components/item_row.tscn")

var _header: Control
var _floor_sec: Control
var _floor_sel: OptionButton
var _cur_bid := ""            # 当前楼层所属建筑(切建筑 → 回 1 层)
var _cur_floor := 1
var _room: Dictionary = {}     # 当前绑定的地点(建筑本体)
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
var _sign_sec: Control
var _sign_body: VBoxContainer


func build() -> void:
	_header = UiKit.header(self)

	# 楼层下拉(仅多楼层建筑显示)
	_floor_sec = UiKit.section(self, "楼层")
	_floor_sec.visible = false
	_floor_sel = OptionButton.new()
	_floor_sel.item_selected.connect(_on_floor_picked)
	_floor_sec.body().add_child(_floor_sel)

	var a: VBoxContainer = UiKit.section(self, "权限").body()
	_perm = UiKit.kv(a, "进入权限")
	_cap = UiKit.kv(a, "容量")
	_cap_row = _cap.get_parent()

	_p_sec = UiKit.section(self, "人员")
	UiKit.column_header(_p_sec.body(), [
		["姓名", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["年龄", UiKit.W_AGE, HORIZONTAL_ALIGNMENT_RIGHT],
		["角色", UiKit.W_ROLE, HORIZONTAL_ALIGNMENT_LEFT],
		["当前行为", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["生命", UiKit.W_HP, HORIZONTAL_ALIGNMENT_LEFT],
	])
	_p = UiList.new(_p_sec.body(), PERSON_ROW)
	_p_empty = UiKit.muted(_p_sec.body(), "无人")

	_i_sec = UiKit.section(self, "物件")
	UiKit.column_header(_i_sec.body(), [
		["名称", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["数量", UiKit.W_QTY, HORIZONTAL_ALIGNMENT_RIGHT],
		["价格", UiKit.W_PRICE, HORIZONTAL_ALIGNMENT_LEFT],
		["使用者", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
	])
	_i = UiList.new(_i_sec.body(), ITEM_ROW)
	_i_empty = UiKit.muted(_i_sec.body(), "无")

	# 公司：注册 / 参数 / 招聘(游戏内经营, 只改世界真值)
	_comp_sec = UiKit.section(self, "公司")

	# 招牌: 这家店在门口吆喝什么(数据来自后端 world.locations[bid].sign)
	_sign_sec = UiKit.section(self, "招牌")
	_sign_body = _sign_sec.body()


func bind(id: String) -> void:
	var room := Store.room(id)
	if room.is_empty():
		return
	_room = room
	var bid := Store.building_of(id)
	if bid != _cur_bid:
		_cur_bid = bid
		_cur_floor = 1                 # 换建筑 → 回到 1 层
	# 单层 → 直接显示(无下拉); 分过单元的 → 下拉选层(层数变化才重建选项)
	var multi := Store.is_multi(bid)
	_floor_sec.visible = multi
	if multi:
		var nf := Store.floor_units(bid)
		_cur_floor = clampi(_cur_floor, 1, nf)
		if _floor_sel.item_count != nf:
			_floor_sel.clear()
			for i in range(1, nf + 1):
				_floor_sel.add_item("第 %d 层" % i)
		if _floor_sel.selected != _cur_floor - 1:
			_floor_sel.select(_cur_floor - 1)   # select() 不发信号, 不会递归
	Store.set_floor(_cur_floor)      # 把“在盯哪一层”同步给观察集
	_render()


## 招牌: 归属公司 / 半径 / 相信度 / 挂着的几条消息(最多 3 条, 由后端定)。
## 公司名 + 现金(来自 hello.companies 的只读镜像)
func _company_text(cid: String) -> String:
	if cid == "":
		return "（未登记）"
	for c in Store.companies:
		var d: Dictionary = c
		if Protocol.s(d.get("id", "")) == cid:
			return "%s · 现金 ¥%.0f" % [Protocol.s(d.get("name", cid)),
				Protocol.num(d.get("cash", 0.0))]
	return cid


## 公司段: 没注册 → 一个按钮; 注册了 → 参数 + 招聘(游戏内经营动作)
func _render_company() -> void:
	if _comp_sec == null:
		return
	for c in _comp_sec.body().get_children():
		_comp_sec.body().remove_child(c)
		c.queue_free()
	var bid := Store.building_of(_cur_bid)
	var room := Store.room(bid)
	if Protocol.s(room.get("kind", "")) != "shop":
		_comp_sec.visible = false
		return
	_comp_sec.visible = true
	var cid := Protocol.s(room.get("company", ""))
	if cid == "":
		_comp_sec.set_title("公司 · 未注册")
		UiKit.muted(_comp_sec.body(), "没注册公司的店【不能卖东西、也不能招人】")
		var name_edit := LineEdit.new()
		name_edit.placeholder_text = "%s 公司" % Protocol.s(room.get("name", bid))
		UiKit.kv(_comp_sec.body(), "公司名").text = ""
		_comp_sec.body().add_child(name_edit)
		var reg := Button.new()
		reg.text = "注册公司（现金 ¥1000）"
		reg.pressed.connect(func() -> void:
			Commands.cmd("register_company", {"location": bid,
				"name": name_edit.text.strip_edges()})
		)
		_comp_sec.body().add_child(reg)
		return
	var comp := InspData.company(cid)
	if comp.is_empty():
		_comp_sec.set_title("公司 · %s" % cid)
		UiKit.muted(_comp_sec.body(), "（等下一帧快照）")
		return
	_comp_sec.set_title("公司 · %s" % Protocol.s(comp.get("name", cid)))
	UiKit.kv(_comp_sec.body(), "现金").text = "¥%.0f" % Protocol.num(comp.get("cash", 0.0))
	var staff: Array = Protocol.as_array(comp.get("staff", []))
	UiKit.kv(_comp_sec.body(), "员工").text = ("%d 人" % staff.size()) if staff.is_empty() 		else "%d 人：%s" % [staff.size(), ", ".join(staff.map(func(x): return Store.name_of(String(x))))]
	var open_m := int(Protocol.num(comp.get("open_minute", 480)))
	var close_m := int(Protocol.num(comp.get("close_minute", 1140)))
	var wage := Protocol.num(comp.get("wage_per_hour", 10.0))
	var hire_on := bool(comp.get("hiring_open", false))
	var slots := int(Protocol.num(comp.get("hiring_slots", 0)))
	UiKit.kv(_comp_sec.body(), "营业").text = "%02d:%02d - %02d:%02d" % [
		open_m / 60, open_m % 60, close_m / 60, close_m % 60]
	UiKit.kv(_comp_sec.body(), "时薪").text = "¥%.0f / 小时" % wage
	UiKit.kv(_comp_sec.body(), "招聘").text = ("招 %d 人" % slots) if hire_on else "未发布"
	# —— 参数编辑 ——
	var cash := _spin(0, 1000000, 100); cash.value = Protocol.num(comp.get("cash", 0.0))
	_comp_sec.body().add_child(_lrow("改成现金", cash))
	var om := _spin(0, 1439, 30); om.value = open_m
	_comp_sec.body().add_child(_lrow("开门(分)", om))
	var cm := _spin(1, 1440, 30); cm.value = close_m
	_comp_sec.body().add_child(_lrow("关门(分)", cm))
	var wg := _spin(1, 500, 1); wg.value = wage
	_comp_sec.body().add_child(_lrow("时薪", wg))
	var rs := _spin(0, 999, 10); rs.value = Protocol.num(comp.get("restock_to", 60))
	_comp_sec.body().add_child(_lrow("补货目标", rs))
	var save := Button.new()
	save.text = "保存参数"
	save.pressed.connect(func() -> void:
		Commands.cmd("company_update", {"company": cid, "cash": cash.value,
			"open_minute": int(om.value), "close_minute": int(cm.value),
			"wage_per_hour": wg.value, "restock_to": int(rs.value)}))
	_comp_sec.body().add_child(save)
	# —— 招聘: 招不招人是公司说了算 ——
	var hs := _spin(0, 99, 1); hs.value = slots
	_comp_sec.body().add_child(_lrow("要招几人", hs))
	var post := Button.new()
	post.text = "发布招聘" if not hire_on else "更新招聘"
	post.tooltip_text = "发布之后，每天新的一天那一刻与有意愿的 NPC 撮合（外面只做媒婆）"
	post.pressed.connect(func() -> void:
		Commands.cmd("company_hire", {"company": cid, "slots": int(hs.value),
			"wage_per_hour": wg.value}))
	_comp_sec.body().add_child(post)
	var cancel := Button.new()
	cancel.text = "撤回招聘"
	cancel.pressed.connect(func() -> void:
		Commands.cmd("company_hire", {"company": cid, "slots": 0}))
	_comp_sec.body().add_child(cancel)


## 面板里的小控件(观察器没有编辑器那套 _spin/_lrow, 这里补两个)
func _spin(mn: float, mx: float, step: float) -> SpinBox:
	var s := SpinBox.new()
	s.min_value = mn
	s.max_value = mx
	s.step = step
	return s


func _lrow(label: String, c: Control) -> Control:
	var row := HBoxContainer.new()
	var l := Label.new()
	l.text = label
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(l)
	row.add_child(c)
	return row


func _render_sign() -> void:
	if _sign_body == null:
		return
	for c in _sign_body.get_children():
		_sign_body.remove_child(c)
		c.queue_free()
	var sign := Protocol.as_dict(_room.get("sign", {}))
	_sign_sec.visible = not sign.is_empty()
	if sign.is_empty():
		return
	var msgs := Protocol.as_array(sign.get("messages", []))
	_sign_sec.set_title("招牌 · %d 条" % msgs.size())
	var cid := Protocol.s(sign.get("company", ""))
	UiKit.kv(_sign_body, "公司").text = _company_text(cid)
	UiKit.kv(_sign_body, "可见半径").text = "%.0f m" % Protocol.num(sign.get("radius", 0.0))
	UiKit.kv(_sign_body, "相信度").text = "%.2f" % Protocol.num(sign.get("believe", 0.0))
	for mid in msgs:
		var e := Store.entity(String(mid))
		if e.is_empty():
			UiKit.muted(_sign_body, "? %s（物件不存在）" % mid)
			continue
		var pr := Protocol.num(e.get("price", 0.0))
		UiKit.muted(_sign_body, "· %s %s" % [Protocol.s(e.get("name", mid)),
			("¥%d" % int(pr)) if pr > 0.0 else "有货"])


func _on_floor_picked(i: int) -> void:
	_cur_floor = i + 1
	Store.set_floor(_cur_floor)      # 切层 → 后端只推这一层的人
	_render()


func _render() -> void:
	var bid := _cur_bid
	var multi := Store.is_multi(bid)
	var unit := Store.unit_of(bid, _cur_floor)
	# 权限/容量取【该层】自己的地点(每层独立成户)
	# 注: 名字不能叫 r —— 下面两个 for 里都有 var r := _p.row(i),
	# GDScript 不允许内层块遮蔽外层的同名局部变量(报错, 不是警告)。
	var unit_room := Store.room(unit)
	if unit_room.is_empty():
		unit_room = _room
	var people := _at(Store.npcs, unit)
	var items := _at(Store.entities, unit)

	var cap := int(Protocol.num(unit_room.get("capacity"), 0.0))
	var title := Protocol.s(_room.get("name", bid))
	if multi:
		title = "%s · %d层" % [title, _cur_floor]
	_header.set_header(title, "%s · %d/%d 人 · %d 物件" % [
		Zh.kind_zh(Protocol.s(_room.get("kind", ""))),
		people.size(), cap, items.size()])

	_render_sign()
	_render_company()

	_perm.text = InspData.access_text(unit_room)
	_cap_row.visible = not bool(unit_room.get("public", true))
	_cap.text = "%d 人" % cap

	# --- 人员(行池) ---
	_p_sec.set_title("人员 %d" % people.size())
	_p_empty.visible = people.is_empty()
	for i in people.size():
		var k := String(people[i])
		var n := Store.npc(k)
		var age := Protocol.num(n.get("age"), -1.0)
		var hp := clampf(Protocol.num(
			Protocol.as_dict(n.get("signals", {})).get("hp"), 1.0), 0.0, 1.0)
		var r := _p.row(i)
		if not r.selected.is_connected(_on_person):
			r.selected.connect(_on_person)
		r.set_row(k, Protocol.s(n.get("name", k)),
			"—" if age < 0.0 else str(int(age)),
			Zh.role_zh(Protocol.s(n.get("role", ""))),
			InspData.activity_text(n), hp)
	_p.trim(people.size())

	# --- 物件(行池) ---
	_i_sec.set_title("物件 %d" % items.size())
	_i_empty.visible = items.is_empty()
	for i in items.size():
		var k := String(items[i])
		var e := Store.entity(k)
		var r := _i.row(i)
		if not r.selected.is_connected(_on_item):
			r.selected.connect(_on_item)
		r.set_row(k, InspData.item_name(e, k), InspData.qty_txt(e),
			InspData.price_txt(e), InspData.user_text(e))
	_i.trim(items.size())


## 按【该层点位】列人与物(精确匹配 —— 单层时 unit 就是建筑本体)。
func _at(d: Dictionary, unit: String) -> Array:
	var out: Array = []
	for k in d:
		if Protocol.s((d[k] as Dictionary).get("loc", "")) == unit:
			out.append(str(k))
	out.sort()
	return out


func _on_person(id: String) -> void:
	Store.select("npc", id)


func _on_item(id: String) -> void:
	Store.select("entity", id)
