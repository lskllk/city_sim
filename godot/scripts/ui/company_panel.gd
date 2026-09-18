# company_panel.gd —— 公司运营界面(居中弹窗, 独立于右侧检查器)。
#
# 用户定的结构:
#   TabView 五个 tab:
#     1 实时监控   工位排(有员工=占位)+ 顾客排队 + 设施(马桶等)
#     2 HR 管理    员工名单 + 发布/撤回招聘(标题/时薪) + 立刻招一次
#     3 货物管理   在售货架/库存 + 向批发市场进货
#     4 价格调整   逐条改售价(只改世界真值)
#     5 家具管理   摆家具(马桶/销售前台/工位), 从公司账出钱
#
# 打开方式:
#   · 店铺【注册公司成功】→ 自动弹出
#   · 店铺详情里点「打开运营界面」→ 再打开
#
# 铁律:
#   · 监控页是自绘 Control(每帧只画, 不建控件);
#   · 货物/价格/家具三个列表只在【打开 / 收到应答】时重建 —— 绝不每帧增删控件;
#   · 面板只读 Store, 写操作一律走 Commands。
extends CanvasLayer

const MonitorScript := preload("res://scripts/ui/company_monitor.gd")

static var instance = null                    # 由 App 创建, 页面用静态方法打开

var _dim: ColorRect
var _panel: PanelContainer
var _title: Label
var _sub: Label
var _msg: Label
var _tabs: TabContainer
var _monitor: Control
var _goods_list: VBoxContainer
var _price_list: VBoxContainer
var _hr_list: VBoxContainer
var _decor_list: VBoxContainer
var _tab_goods: Control
var _tab_prices: Control
var _tab_decor: Control
var _cid := ""
var _shop := ""
var _seen_reply := 0
# 应答到了但快照还没到 → 等下一帧快照再刷列表(否则会用旧值重建, 比如刚改的售价)
var _pending_refresh := false


## 页面侧的统一入口(没创建时不报错, 只是打不开)
static func open_company(cid: String) -> void:
	if instance != null and instance.has_method("open_for"):
		instance.call("open_for", cid)


func _ready() -> void:
	instance = self
	layer = 100
	_build()
	visible = false
	set_process(true)
	Store.snapshot_applied.connect(_on_snapshot)


func _build() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_STOP       # 弹窗时挡住底下的点击
	add_child(root)

	_dim = ColorRect.new()
	_dim.color = Color(0, 0, 0, 0.55)
	_dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(_dim)

	_panel = PanelContainer.new()
	_panel.custom_minimum_size = Vector2(760, 520)
	_panel.set_anchors_preset(Control.PRESET_CENTER)
	_panel.offset_left = -380
	_panel.offset_right = 380
	_panel.offset_top = -260
	_panel.offset_bottom = 260
	root.add_child(_panel)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	_panel.add_child(box)

	# --- 标题行 ---
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	var tcol := VBoxContainer.new()
	tcol.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title = Label.new()
	_title.add_theme_font_size_override("font_size", 18)
	tcol.add_child(_title)
	_sub = Label.new()
	_sub.add_theme_color_override("font_color", Color("7f8ea3"))
	tcol.add_child(_sub)
	_msg = Label.new()
	_msg.add_theme_font_size_override("font_size", 12)
	tcol.add_child(_msg)
	head.add_child(tcol)
	var close := Button.new()
	close.text = "✕ 关闭"
	close.pressed.connect(close_panel)
	head.add_child(close)
	box.add_child(head)

	# --- TabView ---
	_tabs = TabContainer.new()
	_tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	# 1 实时监控: 自绘画布(工位行 + 排队 + 设施)
	_monitor = MonitorScript.new()
	_monitor.name = "实时监控"
	_monitor.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tabs.add_child(_monitor)
	# 2 人员管理(员工名单 + 工位分配 + 每人排班 + 发布/撤回招聘)
	_tabs.add_child(_build_hr())
	# 3 货物管理(零售=进货+货架 / 制造=产出库存)
	_tab_goods = _build_goods()
	_tabs.add_child(_tab_goods)
	# 4 价格调整(零售能改售价; 制造的价格由批发市场定)
	_tab_prices = _build_prices()
	_tabs.add_child(_tab_prices)
	# 5 家具管理(家具目录按公司类型过滤)
	_tab_decor = _build_decor()
	_tabs.add_child(_tab_decor)
	box.add_child(_tabs)


# --- 人员管理 ---------------------------------------------------------------
func _build_hr() -> Control:
	var v := _scroll_tab("人员管理",
		"员工名单 + 工位分配 + 每人排班(上班/下班时刻); 发布招聘启事(几名/时薪) → 每天【招人时刻】媒婆才撮合。")
	_hr_list = VBoxContainer.new()
	_hr_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_hr_list.add_theme_constant_override("separation", 4)
	(v.get_child(v.get_child_count() - 1) as ScrollContainer).add_child(_hr_list)
	return v


# --- 货物管理 --------------------------------------------------------------
func _build_goods() -> Control:
	var v := _scroll_tab("货物管理",
		"在售货架就是店里的货; 从【批发市场】进货 → 上架 → 顾客才能买。")
	_goods_list = VBoxContainer.new()
	_goods_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_goods_list.add_theme_constant_override("separation", 4)
	(v.get_child(v.get_child_count() - 1) as ScrollContainer).add_child(_goods_list)
	return v


# --- 价格调整 --------------------------------------------------------------
func _build_prices() -> Control:
	var v := _scroll_tab("价格调整",
		"改的是世界真值 —— 顾客要【看见】或【听人说】才会知道新价格。")
	_price_list = VBoxContainer.new()
	_price_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_price_list.add_theme_constant_override("separation", 4)
	(v.get_child(v.get_child_count() - 1) as ScrollContainer).add_child(_price_list)
	return v


# --- 家具管理 --------------------------------------------------------------
func _build_decor() -> Control:
	var v := _scroll_tab("家具管理",
		"摆家具(马桶/销售前台/工位…) —— 从公司账出钱, 摆完就一直在店里。")
	_decor_list = VBoxContainer.new()
	_decor_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_decor_list.add_theme_constant_override("separation", 4)
	(v.get_child(v.get_child_count() - 1) as ScrollContainer).add_child(_decor_list)
	return v


## 带提示文字 + 滚动区的 tab 骨架; 滚动区放在最后一个孩子, 调用方往里塞列表。
func _scroll_tab(title: String, hint: String) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.name = title
	v.add_theme_constant_override("separation", 6)
	var l := Label.new()
	l.text = hint
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", Color("7f8ea3"))
	v.add_child(l)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(scroll)
	return v


func _process(_delta: float) -> void:
	if not visible:
		return
	if Commands.reply_seq == _seen_reply:
		return
	_seen_reply = Commands.reply_seq
	var name := Commands.last_cmd
	if not (name.begins_with("company_") or name == "set_price"
			or name == "register_company" or name == "hire_now"):
		return
	var r: Dictionary = Commands.last_reply
	var ok := bool(r.get("ok", false))
	var why := Protocol.s(r.get("why", ""))
	_msg.text = ("✓ 完成" if ok else "✗ %s" % (why if why != "" else "失败"))
	_msg.add_theme_color_override("font_color",
		Color("7fe0a8") if ok else Color("e05252"))
	_pending_refresh = true          # 等下一帧快照到齐了再重建列表


func _on_snapshot() -> void:
	if visible and _pending_refresh:
		_pending_refresh = false
		_refresh_all()


func open_for(cid: String) -> void:
	_cid = cid
	_shop = _first_shop(cid)
	_seen_reply = Commands.reply_seq          # 不同步会把进来的旧应答当新的
	_msg.text = ""
	var comp := Store.company(cid)
	_title.text = "%s" % Protocol.s(comp.get("name", cid)) if not comp.is_empty() \
		else "公司 %s" % cid
	_sub.text = "%s · %s · 店铺 %s" % [Zh.company_kind_zh(_kind()), cid,
		", ".join(Protocol.as_array(comp.get("shops", [])).map(
			func(s): return Store.name_of(Protocol.s(s))))]
	if _is_mfg():
		_set_hint(_tab_goods,
			"加工厂：工人站在【工位】上按在岗时间产出原料。产出不进自家货架、也不给员工吃 —— 每天零点由批发市场按物品定义价【全部收走】，钱从城外进来。")
		_set_hint(_tab_prices,
			"加工厂的货价由批发市场定（= 物品定义价，通常是成品的 80%）—— 这一页是只读的。")
		_set_hint(_tab_decor,
			"摆家具（工位/马桶…）—— 从公司账出钱，摆完就一直在厂里。工位越多，能同时上岗的人越多。")
	else:
		_set_hint(_tab_goods, "货架上的货 = 向批发市场进的货; 顾客在销售台成交。")
		_set_hint(_tab_prices, "改货架上的【售价】—— 顾客按记忆里的价格决定来不来。")
		_set_hint(_tab_decor,
			"摆家具（销售前台/马桶…）—— 从公司账出钱，摆完就一直在店里。")
	if _monitor != null and _monitor.has_method("setup"):
		_monitor.call("setup", cid)
	_refresh_all()
	visible = true


func close_panel() -> void:
	visible = false
	_cid = ""


func _unhandled_key_input(event: InputEvent) -> void:
	if not visible or not (event is InputEventKey) or not event.pressed:
		return
	if (event as InputEventKey).keycode == KEY_ESCAPE:
		close_panel()
		get_viewport().set_input_as_handled()


func _refresh_all() -> void:
	_refresh_hr()
	_refresh_goods()
	_refresh_prices()
	_refresh_decor()


## 这家公司的类型: retail(零售) / manufacture(制造·加工厂)。
func _kind() -> String:
	return Protocol.s(Store.company(_cid).get("kind", "retail"))


func _is_mfg() -> bool:
	return _kind() == "manufacture"


## 这家公司能用的家具 —— 按公司类型过滤(kinds 空 = 通用, 谁都能摆)。
func _fixtures_here() -> Array:
	var k := _kind()
	var out: Array = []
	for f in Store.fixtures:
		var kinds := Protocol.as_array((f as Dictionary).get("kinds", []))
		if kinds.is_empty() or kinds.has(k):
			out.append(f)
	return out


## 改某个 tab 顶部的说明行(它是该 tab 的第 0 个子节点)。
func _set_hint(tab: Control, text: String) -> void:
	if tab != null and tab.get_child_count() > 0:
		var l := tab.get_child(0)
		if l is Label:
			(l as Label).text = text


## 店铺 id 列表的第一家(公司可能有多家店; 面板先只显示第一家)。
func _first_shop(cid: String) -> String:
	var comp := Store.company(cid)
	for s in Protocol.as_array(comp.get("shops", [])):
		return Protocol.s(s)
	return ""


func _clear(v: Node) -> void:
	for c in v.get_children():
		c.queue_free()


func _refresh_hr() -> void:
	if _hr_list == null:
		return
	_clear(_hr_list)
	if _cid == "":
		return
	var comp := Store.company(_cid)
	# 员工名单
	_hr_list.add_child(_head("员工名单"))
	var staff := Protocol.as_array(comp.get("staff", []))
	if staff.is_empty():
		_hr_list.add_child(_muted("还没招到人 —— 发布招聘启事, 等每天招人时刻匹配"))
	for it in staff:
		_hr_list.add_child(_staff_row(it, comp))
	# 招聘启事
	_hr_list.add_child(_head("招聘启事"))
	_hr_list.add_child(_hire_row(comp))


## 时薪显示: 保留小数, 但不要把 3.00 写成 3.00 —— 3 / 1.1 / 12.5 这样。
func _wage_txt(v: float) -> String:
	var s := "%.2f" % v
	while s.contains(".") and s.ends_with("0"):
		s = s.substr(0, s.length() - 1)
	if s.ends_with("."):
		s = s.substr(0, s.length() - 1)
	return s


func _staff_row(it: Variant, comp: Dictionary) -> Control:
	var pid := ""
	var wage := Protocol.num(comp.get("wage_per_hour", 0.0))
	if typeof(it) == TYPE_DICTIONARY:
		pid = Protocol.s((it as Dictionary).get("npc", ""))
		wage = Protocol.num((it as Dictionary).get("wage", wage))
	else:
		pid = Protocol.s(it)
	var station := Protocol.s(Protocol.as_dict(
		Store.npc(pid).get("work", {})).get("station", ""))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var name := Label.new()
	name.text = Store.name_of(pid)
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name)
	# 【分配工位】: 下拉选定这个员工守哪个销售台(或“未分配")
	var ob := OptionButton.new()
	var ids: Array = [""]
	ob.add_item("未分配")
	var counters := _company_counters()
	var slot_name := "工位" if _is_mfg() else "销售台"
	for i in counters.size():
		var cid2 := Protocol.s((counters[i] as Dictionary).get("id", ""))
		ids.append(cid2)
		ob.add_item("%s %d%s" % [slot_name, i + 1,
			"（占用）" if _station_taken(cid2, pid) else ""])
		if cid2 == station:
			ob.select(i + 1)
	ob.custom_minimum_size.x = 150
	ob.item_selected.connect(func(k: int) -> void:
		Commands.cmd("company_assign", {"company": _cid, "npc": pid,
			"station": Protocol.s(ids[k]) if k < ids.size() else ""}))
	row.add_child(ob)
	var w := LineEdit.new()
	w.text = _wage_txt(wage)          # ★ 保留小数(以前 "%.0f" 把 1.1 显示成 1)
	w.custom_minimum_size.x = 52
	w.tooltip_text = "这个人的时薪(¥/时) —— 逐人, 不动公司默认时薪"
	row.add_child(w)
	row.add_child(_muted("¥/时"))
	var wb := Button.new()
	wb.text = "改薪"
	wb.pressed.connect(func() -> void:
		# ★ 命令名要对: 以前发的是 `company` + op, 服务端没这个名字 → 按了没反应
		Commands.cmd("company_wage", {"company": _cid, "npc": pid,
			"wage": w.text.strip_edges().to_float()}))
	row.add_child(wb)
	var on_post := bool(Store.npc(pid).get("on_post", false))
	var st := Label.new()
	st.text = "在岗" if on_post else "不在岗"
	st.add_theme_color_override("font_color",
		Color("7fe0a8") if st.text == "在岗" else Color("e8a34d"))
	row.add_child(st)
	# 【排班】: 每人一个班次(上班/下班 HH:MM; 只影响他自己, 不动公司营业时间)
	var work := Protocol.as_dict(Store.npc(pid).get("work", {}))
	var oe := LineEdit.new()
	oe.text = _hm(int(Protocol.num(work.get("open", 0))))
	oe.custom_minimum_size.x = 48
	row.add_child(oe)
	row.add_child(_muted("–"))
	var ce := LineEdit.new()
	ce.text = _hm(int(Protocol.num(work.get("close", 1440))))
	ce.custom_minimum_size.x = 48
	row.add_child(ce)
	var sb := Button.new()
	sb.text = "排班"
	sb.pressed.connect(func() -> void:
		# ★ 同上: 以前发到不存在的 `company` 命令 → 按了没反应
		Commands.cmd("company_schedule", {"company": _cid, "npc": pid,
			"open": _minutes(oe.text), "close": _minutes(ce.text)}))
	row.add_child(sb)
	return row


func _hire_row(comp: Dictionary) -> Control:
	var wage := Protocol.num(comp.get("wage_per_hour", 10.0))
	var slots := int(Protocol.num(comp.get("hiring_slots", 0)))
	var is_open := bool(comp.get("hiring_open", false))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	# 用 GridContainer 两列: 标签列 + 控件列 —— 之前挤在 HBox 里, 短标签被
	# autowrap 压成一字一行(用户报的"挤成竖着")。
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 6)
	grid.add_child(_lbl("时薪 ¥/小时"))
	var le := LineEdit.new()
	le.text = "%d" % int(wage)
	le.custom_minimum_size = Vector2(120, 0)
	le.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	grid.add_child(le)
	grid.add_child(_lbl("这次招几名"))
	var sp := SpinBox.new()
	sp.min_value = 0
	sp.max_value = 99
	sp.value = slots
	sp.custom_minimum_size = Vector2(120, 0)
	sp.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	grid.add_child(sp)
	grid.add_child(_lbl("空工位"))
	grid.add_child(_lbl("%d 个" % _vacant_count()))
	box.add_child(grid)

	var btns := HBoxContainer.new()
	btns.add_theme_constant_override("separation", 8)
	var pub := Button.new()
	pub.text = "发布 / 更新招聘"
	pub.pressed.connect(func() -> void:
		Commands.cmd("company_hire", {"company": _cid,
			"slots": int(sp.value), "wage_per_hour": le.text.strip_edges().to_float()}))
	btns.add_child(pub)
	var stop := Button.new()
	stop.text = "撤回招聘"
	stop.pressed.connect(func() -> void:
		Commands.cmd("company_hire", {"company": _cid, "slots": 0}))
	btns.add_child(stop)
	var now := Button.new()
	now.text = "立刻招一次"
	now.tooltip_text = "不等招人时刻, 马上让媒婆匹配一次(看效果用)"
	now.pressed.connect(func() -> void: Commands.cmd("hire_now", {}))
	btns.add_child(now)
	box.add_child(btns)

	var state := Label.new()
	state.text = ("招聘中 · 名额 %d · 时薪 ¥%.0f" % [slots, wage]) if is_open \
		else "未发布招聘(一个也不会被招进来)"
	state.add_theme_color_override("font_color",
		Color("7fe0a8") if is_open else Color("7f8ea3"))
	box.add_child(state)
	return box


# --- 货物管理 --------------------------------------------------------------
func _refresh_goods() -> void:
	if _goods_list == null:
		return
	_clear(_goods_list)
	if _shop == "":
		_goods_list.add_child(_muted("这家公司还没登记店铺"))
		return
	if _is_mfg():
		# 加工厂: 地上堆的是【产出】(工人站工位产出的原料), 不是进货
		_goods_list.add_child(_head("产出库存"))
		var piles := _shelves()
		if piles.is_empty():
			_goods_list.add_child(_muted("厂里还没有产出 —— 去【人员管理】把工人派到工位, 他站着就会产"))
		for e in piles:
			_goods_list.add_child(_shelf_row(e))
		# 工业机器: 一台配一个工位 → 产量 ×3(多余机器没用)
		var machines := 0
		var benches := 0
		for e in Store.entities.values():
			var d: Dictionary = e
			if Store.building_of(Protocol.s(d.get("loc", ""))) != _shop:
				continue
			var t := Protocol.s(d.get("item_type", ""))
			if t == "industry_machine":
				machines += 1
			elif t == "station_workbench":
				benches += 1
		if machines > 0 or benches > 0:
			_goods_list.add_child(_muted(
				"工业机器 %d 台 / 工位 %d 个 —— 每台机器给一个工位产量 ×3；多余机器没用（想再提就再加机器 + 工位）"
				% [machines, benches]))
		_goods_list.add_child(_muted("每天零点批发市场按物品定义价全部收走 → 钱进公司账。"))
		return
	# 在售货架
	_goods_list.add_child(_head("在售货架"))
	var shelves := _shelves()
	if shelves.is_empty():
		_goods_list.add_child(_muted("货架上还没有货 —— 从下面进一批"))
	for e in shelves:
		_goods_list.add_child(_shelf_row(e))
	# 向市场进货
	_goods_list.add_child(_head("向批发市场进货"))
	if not bool(Store.market.get("exists", false)):
		_goods_list.add_child(_muted("城里还没有批发市场(编辑器放一栋 kind=market 的建筑)"))
		return
	for item in Protocol.as_array(Store.market.get("items", [])):
		_goods_list.add_child(_market_row(item))


func _shelf_row(e: Dictionary) -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var name := Label.new()
	name.text = Protocol.s(e.get("name", e.get("id", "")))
	name.custom_minimum_size.x = 170
	row.add_child(name)
	var stock := int(Protocol.num(e.get("stock", 0)))
	var sl := Label.new()
	# 家具数量恒为 1(不显示库存); 货物才报数
	var is_fur := Protocol.as_array(e.get("tags", [])).has("fixture")
	sl.text = "" if is_fur else "库存 %s" % str(stock)
	sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sl.add_theme_color_override("font_color", Color("7f8ea3"))
	row.add_child(sl)
	var pl := Label.new()
	pl.text = "售价 ¥%.0f" % Protocol.num(e.get("price", 0.0))
	row.add_child(pl)
	return row


func _market_row(item: Dictionary) -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var name := Label.new()
	name.text = "%s　批发 ¥%.0f" % [Protocol.s(item.get("name", item.get("type", ""))),
		Protocol.num(item.get("price", 0.0))]
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name)
	var qty := SpinBox.new()
	qty.min_value = 1
	qty.max_value = 999
	qty.value = 10
	qty.custom_minimum_size.x = 80
	row.add_child(qty)
	var btn := Button.new()
	btn.text = "进货"
	var itype := Protocol.s(item.get("type", ""))
	btn.pressed.connect(func() -> void:
		Commands.cmd("company_restock", {"company": _cid, "shop": _shop,
			"item_type": itype, "qty": int(qty.value)}))
	row.add_child(btn)
	return row


# --- 价格调整 --------------------------------------------------------------
func _refresh_prices() -> void:
	if _price_list == null:
		return
	_clear(_price_list)
	if _shop == "":
		_price_list.add_child(_muted("这家公司还没登记店铺"))
		return
	var shelves := _shelves()
	if _is_mfg():
		_price_list.add_child(_muted("加工厂不零售 —— 产出全部卖给批发市场, 价由物品定义定。"))
		for e in shelves:
			_price_list.add_child(_muted("· %s　收购价 ¥%.0f" % [
				Protocol.s(e.get("name", e.get("id", ""))),
				Protocol.num(e.get("price", 0.0))]))
		return
	if shelves.is_empty():
		_price_list.add_child(_muted("货架上还没有货 —— 先去【货物管理】进货"))
		return
	for e in shelves:
		_price_list.add_child(_price_row(e))


func _price_row(e: Dictionary) -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var name := Label.new()
	name.text = Protocol.s(e.get("name", e.get("id", "")))
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name)
	var le := LineEdit.new()
	le.text = "%d" % int(Protocol.num(e.get("price", 0.0)))
	le.custom_minimum_size.x = 80
	row.add_child(le)
	var btn := Button.new()
	btn.text = "保存"
	var eid := Protocol.s(e.get("id", ""))
	btn.pressed.connect(func() -> void:
		Commands.cmd("set_price", {"entity": eid,
			"price": le.text.strip_edges().to_float()}))
	row.add_child(btn)
	return row


# --- 家具管理 --------------------------------------------------------------
func _refresh_decor() -> void:
	if _decor_list == null:
		return
	_clear(_decor_list)
	if _shop == "":
		_decor_list.add_child(_muted("这家公司还没登记店铺"))
		return
	# 店里【已摆】的家具 —— 按【所属】分两区: 内部(公司) / 公共(谁都能用)
	var mine: Array = []
	var pub: Array = []
	var other: Array = []
	for e in Store.entities.values():
		var d: Dictionary = e
		if not _is_fixture(Protocol.s(d.get("item_type", ""))):
			continue
		if Store.building_of(Protocol.s(d.get("loc", ""))) != _shop:
			continue
		var o := Protocol.s(d.get("owner", ""))
		if o == "":
			pub.append(d)
		elif o == _cid:
			mine.append(d)
		else:
			other.append(d)
	_decor_list.add_child(_head("内部 · 公司自有 (%d)" % mine.size()))
	_decor_list.add_child(_muted("owner=公司 → 只有本公司店员能免费用"))
	_decor_list.add_child(_placed_rows(mine))
	_decor_list.add_child(HSeparator.new())
	_decor_list.add_child(_head("公共 · 谁都能用 (%d)" % pub.size()))
	_decor_list.add_child(_muted("owner 留空 → 路人/顾客/谁都行(如门口马桶、过道长凳)"))
	_decor_list.add_child(_placed_rows(pub))
	if not other.is_empty():
		_decor_list.add_child(HSeparator.new())
		_decor_list.add_child(_head("个人 · 别人的 (%d)" % other.size()))
		_decor_list.add_child(_placed_rows(other, true))
	_decor_list.add_child(HSeparator.new())
	_decor_list.add_child(_head("家具目录 · 放置"))
	var cat := _fixtures_here()
	if cat.is_empty():
		_decor_list.add_child(_muted("没有可用的家具(config/items 里打 fixture 标签)"))
	for f in cat:
		_decor_list.add_child(_decor_row(f))


## 一区里已摆的家具: 按类型汇总成 "· 销售前台 ×2"。
func _placed_rows(rows: Array, show_owner: bool = false) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	if rows.is_empty():
		box.add_child(_muted("  （空）"))
		return box
	var by := {}
	for r in rows:
		var d: Dictionary = r
		var t := Protocol.s(d.get("item_type", ""))
		var o := Protocol.s(d.get("owner", "")) if show_owner else ""
		by["%s|%s" % [t, o]] = int(by.get("%s|%s" % [t, o], 0)) + 1
	var keys := by.keys()
	keys.sort()
	for k in keys:
		var parts := String(k).split("|")
		var txt := "  · %s ×%d" % [_type_name(parts[0]), by[k]]
		if parts.size() > 1 and parts[1] != "":
			txt += "（%s）" % Store.name_of(parts[1])
		var l := Label.new()
		l.text = txt
		l.add_theme_color_override("font_color", Color("9fb0c4"))
		box.add_child(l)
	return box


func _decor_row(fd: Dictionary) -> Control:
	var itype := Protocol.s(fd.get("type", ""))
	var price := Protocol.num(fd.get("price", 0.0))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name := Label.new()
	name.text = "%s　¥%d" % [Protocol.s(fd.get("name", itype)), int(price)]
	name.custom_minimum_size.x = 170
	row.add_child(name)
	var cnt := Label.new()
	cnt.text = "已有 %d" % _count_fixture(itype)
	cnt.add_theme_color_override("font_color", Color("7f8ea3"))
	cnt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(cnt)
	row.add_child(_place_btn(itype, false, "摆内部"))
	row.add_child(_place_btn(itype, true, "摆公共"))
	return row


func _place_btn(itype: String, public: bool, text: String) -> Button:
	var b := Button.new()
	b.text = text
	b.tooltip_text = "任何人都能用(owner 留空)" if public \
		else "只有本公司店员免费用(owner=公司)"
	b.pressed.connect(func() -> void:
		Commands.cmd("company_decorate", {"company": _cid, "shop": _shop,
			"item_type": itype, "public": public}))
	return b


## 这个物品类型是不是家具(在 fixtures 目录里)。
func _is_fixture(itype: String) -> bool:
	for f in Store.fixtures:
		if Protocol.s((f as Dictionary).get("type", "")) == itype:
			return true
	return false


## 家具类型的显示名。
func _type_name(itype: String) -> String:
	for f in Store.fixtures:
		var d: Dictionary = f
		if Protocol.s(d.get("type", "")) == itype:
			return Protocol.s(d.get("name", itype))
	return itype


# --- 只读镜像查询 ----------------------------------------------------------
## 店里的【货】(售价 > 0 的实体; 家具售价为 0, 不算货)。
func _shelves() -> Array:
	var out: Array = []
	for e in Store.entities.values():
		var d: Dictionary = e
		if Protocol.num(d.get("price", 0.0)) <= 0.0:
			continue
		if Store.building_of(Protocol.s(d.get("loc", ""))) != _shop:
			continue
		out.append(d)
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return Protocol.s(a.get("id", "")) < Protocol.s(b.get("id", "")))
	return out


## "HH:MM" <-> 当天分钟数(排班用)。
func _hm(minutes: int) -> String:
	return "%02d:%02d" % [minutes / 60, minutes % 60]


func _minutes(s: String) -> int:
	var parts := s.strip_edges().split(":")
	if parts.size() != 2 or not parts[0].is_valid_int() 			or not parts[1].is_valid_int():
		return 0
	return int(parts[0]) * 60 + int(parts[1])


## 公司旗下【空着的】销售前台数(= 还能招几个人)。已绑员工的台不算。
func _vacant_count() -> int:
	var taken := {}
	for it in Protocol.as_array(Store.company(_cid).get("staff", [])):
		var pid := Protocol.s((it as Dictionary).get("npc", "")) \
			if typeof(it) == TYPE_DICTIONARY else Protocol.s(it)
		if pid == "":
			continue
		var station := Protocol.s(Protocol.as_dict(
			Store.npc(pid).get("work", {})).get("station", ""))
		if station != "":
			taken[station] = true
	var n := 0
	for e in Store.entities.values():
		var d: Dictionary = e
		if Protocol.s(d.get("item_type", "")) != "station_counter":
			continue
		if not _owns_shop(Protocol.s(d.get("loc", ""))):
			continue
		if not taken.has(Protocol.s(d.get("id", ""))):
			n += 1
	return n


## 这个地点是不是公司旗下的店(按父建筑归)。
func _owns_shop(loc: String) -> bool:
	var b := Store.building_of(loc)
	return Protocol.as_array(
		Store.company(_cid).get("shops", [])).has(b)


## 公司旗下【所有】销售台(按 id 排)—— 分配工位的下拉列表。
func _company_counters() -> Array:
	var shops := Protocol.as_array(Store.company(_cid).get("shops", []))
	# 岗位长什么样由公司类型定: 零售=销售台, 制造=工位
	var want := "station_workbench" if _is_mfg() else "station_counter"
	var out: Array = []
	for e in Store.entities.values():
		var d: Dictionary = e
		if Protocol.s(d.get("item_type", "")) != want:
			continue
		if not shops.has(Store.building_of(Protocol.s(d.get("loc", "")))):
			continue
		out.append(d)
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return Protocol.s(a.get("id", "")) < Protocol.s(b.get("id", "")))
	return out


## 这个台是不是已经被【别人】占了(except_pid = 自己, 不算)。
func _station_taken(station_id: String, except_pid: String) -> bool:
	for pid in Store.npcs:
		if String(pid) == except_pid:
			continue
		var w := Protocol.as_dict(Store.npc(pid).get("work", {}))
		if Protocol.s(w.get("station", "")) == station_id:
			return true
	return false


## 不换行的短标签(用于表单同行; autowrap 在窄行里会把字挤成一列)。
func _lbl(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_color_override("font_color", Color("7f8ea3"))
	return l


func _count_fixture(itype: String) -> int:
	var n := 0
	for e in Store.entities.values():
		var d: Dictionary = e
		if Protocol.s(d.get("item_type", "")) == itype \
				and Store.building_of(Protocol.s(d.get("loc", ""))) == _shop:
			n += 1
	return n


func _head(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", UiTheme.FS_HEAD)
	l.add_theme_color_override("font_color", Color("6fb7ff"))
	return l


func _muted(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", Color("7f8ea3"))
	return l
