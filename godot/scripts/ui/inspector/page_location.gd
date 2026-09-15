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
