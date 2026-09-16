# page_location.gd —— 建筑详情(观察器)。
#
# 模板【按建筑类型绑定】(用户定的口径, 和编辑器同一套):
#   商铺 shop → 公司(可进"公司运营"页) + 在店里的人(店员/顾客, 可点进详情)
#               + 物件(商品/家具/工位, 可点进详情)
#   住宅 home → 楼层 + 住户 + 家里的东西(都可点进详情)
#   其它      → 权限 + 在场的人 (市场多一行"无限库存 · 只有公司能采购")
#
# 招牌信息【已从详情移除】(那是经营手段 → 归公司运营页的"广告", 后续做)。
#
# 铁律: 页面常驻; bind() 只改数值, 不重建控件(见 ui_page.gd)。
class_name InspLocationPage
extends UiPage

const PERSON_ROW := preload("res://scenes/components/person_row.tscn")
## 公司运营弹窗: 用 preload 调它的静态入口(不依赖 class_name 的全局类表)
const CompanyPanelScript := preload("res://scripts/ui/company_panel.gd")
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

# 公司段: 两种形态的控件【各建一次】(未注册 / 已注册), bind 只切 visible + 改文字。
# —— 铁律: bind() 绝不增删控件, 否则按钮每 100ms 被重建一次 = 闪烁 + 点不中。
var _reg_hint: Label
var _reg_name: LineEdit
var _reg_btn: Button
var _go_btn: Button
var _company_id := ""                # 当前店铺已注册到的公司(解析后的真 id)
var _msg: Label                       # 上一步命令的结果(后端应答)
var _seen_reply := 0


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

	# 公司(商铺): 未注册 → 只有【注册公司】; 注册了 → 只有【打开运营界面】。
	# 其他经营信息(线路/员工/货物/价格)全在【弹窗里的运营界面】, 这里一律不显示。
	_comp_sec = UiKit.section(self, "公司")
	_comp_body = _comp_sec.body()
	_reg_hint = UiKit.muted(_comp_body, "没注册公司的店【不能卖、不能招人】")
	_reg_name = LineEdit.new()
	_comp_body.add_child(_reg_name)
	_reg_btn = Button.new()
	_reg_btn.text = "注册公司（现金 ¥1000）"
	_reg_btn.pressed.connect(func() -> void:
		Commands.cmd("register_company", {"location": _cur_bid,
			"name": _reg_name.text.strip_edges()}))
	# 【必须填公司名】: 名字空 → 按钮禁用(并说明为什么)
	_reg_name.text_changed.connect(func(_s: String) -> void: _sync_reg_btn())
	_sync_reg_btn()
	_comp_body.add_child(_reg_btn)
	_go_btn = Button.new()
	_go_btn.text = "打开运营界面"
	# 【用解析后的 _company_id】而不是 _room.company —— 房间表只随 hello 下发,
	# 游戏内注册后不会更新, 直接读它会拿到空串(点了打不开)。
	_go_btn.pressed.connect(func() -> void:
		CompanyPanelScript.open_company(_company_id))
	_comp_body.add_child(_go_btn)
	_msg = UiKit.muted(_comp_body, "")

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
		# 【换店就清状态】: 公司名输入框 / 上一步应答 / 已注册公司都是【按店】的,
		# 不清的话上一家填的名字会带到下一家(实测: 注册一家, 其他全被同一名字覆盖)。
		_reg_name.text = ""
		_msg.text = ""
		_seen_reply = Commands.reply_seq
		_company_id = ""
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


## 点人员行 → 进 NPC 详情(以前忘了连 selected → 点了没反应)。
func _on_person(id: String) -> void:
	Store.select("npc", id)


## 点物件行 → 进物件详情。
func _on_item(id: String) -> void:
	Store.select("entity", id)


## 排序权重: 店员(0) 在 顾客/其他(1) 前面。
func _people_rank(id: String) -> int:
	var n := Store.npc(id)
	var w := Protocol.as_dict(n.get("work", {}))
	if Protocol.s(w.get("company", "")) != "" \
			or Protocol.s(w.get("station", "")) != "":
		return 0
	var role := Protocol.s(n.get("role", ""))
	if role == "worker" or role == "shopkeeper":
		return 0
	return 1


## 排序权重: 商品(售价>0) 在 家具/设施 前面。
func _items_rank(id: String) -> int:
	return 0 if Protocol.num(Store.entity(id).get("price", 0.0)) > 0.0 else 1


func _render() -> void:
	var bid := _cur_bid
	var multi := Store.is_multi(bid)
	var unit := Store.unit_of(bid, _cur_floor)
	var unit_room := Store.room(unit)
	if unit_room.is_empty():
		unit_room = _room
	var kind := Protocol.s(_room.get("kind", ""))
	var is_home := Zh.kind_zh(kind) == "住所"
	# 商居都把这一层的人和物列出来
	var people := _at(Store.npcs, unit if is_home else bid)
	var items := _at(Store.entities, unit if is_home else bid)

	var cap := int(Protocol.num(unit_room.get("capacity"), 0.0))
	var title := Protocol.s(_room.get("name", bid))
	if is_home and multi:
		title = "%s · %d层" % [title, _cur_floor]
	# 商铺/住宅都把这一层的【人 + 物】总结出来(用户要的)
	_header.set_header(title, "%s · %d 人 · %d 物件" % [
		Zh.kind_zh(kind), people.size(), items.size()])

	_sync_company(kind, bid)

	_perm.text = InspData.access_text(unit_room)
	_cap_row.visible = not bool(unit_room.get("public", true))
	_cap.text = "%d 人" % cap

	# --- 在店里的人 / 住户: 全部显示; 店员在前、顾客在后, 各自按名字排 ---
	people.sort_custom(func(a, b) -> bool:
		var ra := _people_rank(String(a))
		var rb := _people_rank(String(b))
		if ra != rb:
			return ra < rb
		return Store.name_of(String(a)) < Store.name_of(String(b)))
	_p_sec.visible = true
	_p_sec.set_title(("住户 %d" if is_home else "在店里的人 %d") % people.size())
	_p_empty.visible = people.is_empty()
	for i in people.size():
		var k := String(people[i])
		var n := Store.npc(k)
		var age := Protocol.num(n.get("age"), -1.0)
		var hp := clampf(Protocol.num(
			Protocol.as_dict(n.get("signals", {})).get("hp"), 1.0), 0.0, 1.0)
		var work := Protocol.as_dict(n.get("work", {}))
		var staffed := Protocol.s(work.get("company", "")) != "" \
			or Protocol.s(work.get("station", "")) != ""
		# 当前行为: 用统一的 activity_text(act_class 驱动), 与实际一致。
		# 店员离开工位时额外标“不在岗”, 但后面仍是他【真正在做的事】。
		var act := InspData.activity_text(n)
		if staffed and not bool(n.get("on_post", false)):
			act = "不在岗 · " + act
		# 【字段标注】店里的人写清【店员 / 顾客】, 住宅里标【店员 / 住户】
		var label := Zh.role_zh(Protocol.s(n.get("role", "")))
		if not is_home:
			label = "店员" if staffed else "顾客"
		elif staffed:
			label = "店员"
		var row = _p.row(i)
		if not row.selected.is_connected(_on_person):
			row.selected.connect(_on_person)
		row.set_row(k, String(n.get("name", k)),
			"—" if age < 0.0 else str(int(age)), label, act, hp)
	_p.trim(people.size())

	# --- 物件: 商品(售价>0)在前, 家具/设施在后; 各自按名字排 ---
	items.sort_custom(func(a, b) -> bool:
		var ra := _items_rank(String(a))
		var rb := _items_rank(String(b))
		if ra != rb:
			return ra < rb
		return Store.name_of(String(a)) < Store.name_of(String(b)))
	_i_sec.visible = true
	_i_sec.set_title("物件 %d" % items.size())
	_i_empty.visible = items.is_empty()
	for i in items.size():
		var e := Store.entity(String(items[i]))
		var st := int(Protocol.num(e.get("stock", 1.0)))
		var pr := Protocol.num(e.get("price", 0.0))
		var qty := "∞" if st < 0 else str(st)
		var nm := String(e.get("name", items[i]))
		if Protocol.s(e.get("item_type", "")) == "station_counter":
			qty = "工位"                      # 销售前台: 交易靠它
		elif Protocol.as_array(e.get("tags", [])).has("fixture"):
			nm = "%s（家具）" % nm            # 装修件: 标注一下
		var row = _i.row(i)
		if not row.selected.is_connected(_on_item):
			row.selected.connect(_on_item)
		row.set_row(String(items[i]), nm,
			qty, "—" if pr <= 0.0 else "¥%d" % int(pr),
			Store.name_of(Protocol.s(e.get("claimed_by", ""))))
	_i.trim(items.size())


## 注册按钮: 名字空就不能点(用户定: 一定要输入公司名字)
func _sync_reg_btn() -> void:
	if _reg_btn == null:
		return
	var blank := _reg_name.text.strip_edges() == ""
	_reg_btn.disabled = blank
	_reg_btn.tooltip_text = "先填公司名" if blank else "注册后直接进入公司管理"


## 公司段(商铺): 未注册 → 注册按钮; 注册了 → 只显示【进入公司管理】。
## ★ 只切 visible / 改文字 —— 绝不在这里 new/free(否则按钮闪烁点不中)
func _sync_company(kind: String, bid: String) -> void:
	if _msg != null and Commands.reply_seq != _seen_reply:
		_seen_reply = Commands.reply_seq
		var r: Dictionary = Commands.last_reply
		var ok := bool(r.get("ok", false))
		var why := Protocol.s(r.get("why", ""))
		_msg.text = ("✓ 成功" if ok else "✗ %s" % (why if why != "" else "失败"))
		_msg.add_theme_color_override("font_color",
			Color("7fe0a8") if ok else Color("e05252"))
		# 注册成功 → 【直接进入运营界面】(用户定的流程)
		var new_cid := Protocol.s(Protocol.as_dict(r.get("data", {})).get("company", ""))
		if ok and new_cid != "":
			CompanyPanelScript.open_company(new_cid)      # 注册成功 → 直接进运营界面
	var cid := Protocol.s(_room.get("company", ""))
	_comp_sec.visible = kind == "shop"
	if kind != "shop":
		return
	# 兜底: location 上的 company 还没同步到, 但某家公司已把这栋楼列进 shops
	# → 也算已注册(否则会出现"注册过了还显示注册按钮")
	if cid == "":
		for c in Store.companies:
			var cd: Dictionary = c
			if Protocol.as_array(cd.get("shops", [])).has(bid):
				cid = Protocol.s(cd.get("id", ""))
				break
	var registered := cid != ""
	_company_id = cid                  # 供【进入公司管理】按钮使用
	# 注册组 / 管理组: 二选一, 绝不同时出现
	_reg_hint.visible = not registered
	_reg_name.visible = not registered
	_reg_btn.visible = not registered
	_go_btn.visible = registered
	_comp_sec.set_title("公司管理" if registered else "公司 · 未注册")
	if registered:
		_go_btn.text = "进入公司管理（%s）" % Protocol.s(
			Store.company(cid).get("name", cid))
	else:
		_sync_reg_btn()
		if not _reg_name.has_focus():
			_reg_name.placeholder_text = "%s 公司" % Protocol.s(_room.get("name", bid))


func _at(d: Dictionary, unit: String) -> Array:
	var out: Array = []
	for k in d:
		var rec: Dictionary = d[k]
		var loc := Protocol.s(rec.get("loc", ""))
		if loc == unit or Store.building_of(loc) == unit:
			out.append(String(k))
	out.sort()
	return out
