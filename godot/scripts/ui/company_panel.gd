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
var _hr_list: VBoxContainer
var _decor_list: VBoxContainer
var _tab_goods: Control
var _tab_decor: Control
const STAFF_COLS := 7          # 员工行网格列数(见 _refresh_hr / _add_staff_cells)

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
	# 结果提示: 它是"刚才那条命令成功没有"的唯一回执 —— 大一点、加粗(以前太不显眼)
	_msg.add_theme_font_size_override("font_size", 13)
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
	# 4 家具管理(家具目录按公司类型过滤)
	# (原"价格调整"页已并入【货物管理】: 每行货就地改价, 少一次来回)
	_tab_decor = _build_decor()
	_tabs.add_child(_tab_decor)
	box.add_child(_tabs)


# --- 人员管理 ---------------------------------------------------------------
func _build_hr() -> Control:
	var v := _scroll_tab("人员管理",
		"员工名单 + 逐人时薪/排班。发布招聘启事(几名/时薪) → 每天【招人时刻】自动撮合, 岗位由系统自动分配。")
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


## 本地即时回执(不等服务端): 输入不合法时就地说明, 别让人以为"点了没反应"。
func _flash(text: String, ok: bool) -> void:
	_msg.text = ("✓ %s" % text) if ok else ("✗ %s" % text)
	_msg.add_theme_color_override("font_color",
		Color("7fe0a8") if ok else Color("e05252"))


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
	if not visible or not _pending_refresh:
		return
	# ★ 有人正在输入就别重建 —— _refresh_all 会销毁并重建所有输入框,
	#   把他刚打的字和焦点一起丢掉(实测: "改完 A 再改 B" 时 A 白打了)。
	#   点按钮会让输入框失焦, 所以正常流程不会卡住; 停在输入框里就一直等。
	if _editing():
		return
	_pending_refresh = false
	_refresh_all()


## 面板里现在有输入框拿着键盘焦点吗?
func _editing() -> bool:
	var f := get_viewport().gui_get_focus_owner() if get_viewport() != null else null
	return f != null and is_ancestor_of(f) and (f is LineEdit or f is TextEdit)


## 重建列表时保住滚动位置(否则改完一个人的薪, 列表跳回顶部 → 像"出问题")
func _scroll_of(node: Node) -> int:
	var sc := node.get_parent()
	return int((sc as ScrollContainer).scroll_vertical) if sc is ScrollContainer else 0


func _restore_scroll(node: Node, v: int) -> void:
	var sc := node.get_parent()
	if sc is ScrollContainer:
		(sc as ScrollContainer).scroll_vertical = v


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
		_set_hint(_tab_decor,
			"摆家具（工位/马桶…）—— 从公司账出钱，摆完就一直在厂里。工位越多，能同时上岗的人越多。")
	else:
		_set_hint(_tab_goods,
			"货架上的货 = 向批发市场进的货；每行右边可以就地改售价（顾客要看见或听人说才会知道新价）。")
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
	var keep := _scroll_of(_hr_list)
	_clear(_hr_list)
	if _cid == "":
		return
	var comp := Store.company(_cid)
	_hr_list.add_child(_head("员工名单"))
	var staff := Protocol.as_array(comp.get("staff", []))
	if staff.is_empty():
		_hr_list.add_child(_muted("还没招到人 —— 发布招聘启事, 等每天招人时刻自动撮合"))
	else:
		# ★ 用 GridContainer 列对齐 —— 以前一行一个 HBox, 宽窄靠互相挤,
		#   窄窗口下"时薪"会被压成竖排。网格让每列按最宽的那个对齐。
		var grid := GridContainer.new()
		grid.columns = STAFF_COLS
		grid.add_theme_constant_override("h_separation", 6)
		grid.add_theme_constant_override("v_separation", 4)
		grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		for h in ["姓名", "在岗", "时薪 ¥/时", "", "上班", "下班", ""]:
			grid.add_child(_muted(h))
		for it in staff:
			_add_staff_cells(grid, it, comp)
		_hr_list.add_child(grid)
	_hr_list.add_child(_head("招聘启事"))
	_hr_list.add_child(_hire_row(comp))
	_restore_scroll(_hr_list, keep)


## 一个员工的 7 个格子(顺序必须和 STAFF_COLS 对齐)。
func _add_staff_cells(grid: GridContainer, it: Variant, comp: Dictionary) -> void:
	var pid := ""
	var wage := Protocol.num(comp.get("wage_per_hour", 0.0))
	if typeof(it) == TYPE_DICTIONARY:
		pid = Protocol.s((it as Dictionary).get("npc", ""))
		wage = Protocol.num((it as Dictionary).get("wage", wage))
	else:
		pid = Protocol.s(it)
	# 1 姓名(固定宽 + 截断, 不许它把整行吃掉)
	var name := Label.new()
	name.text = Store.name_of(pid)
	name.custom_minimum_size.x = 76
	name.clip_text = true
	name.tooltip_text = pid
	grid.add_child(name)
	# 2 在岗灯(窄, 色区分)
	var on_post := bool(Store.npc(pid).get("on_post", false))
	var st := Label.new()
	st.text = "在岗" if on_post else "——"
	st.custom_minimum_size.x = 30
	st.add_theme_color_override("font_color",
		Color("7fe0a8") if on_post else Color("4a5568"))
	st.tooltip_text = "正守着自己那个工位" if on_post else "不在岗(没到班 / 去吃饭睡觉)"
	grid.add_child(st)
	# 3 逐人时薪
	var w := LineEdit.new()
	w.text = _wage_txt(wage)
	w.custom_minimum_size.x = 50
	w.tooltip_text = "这个人的时薪(¥/时) —— 逐人, 不动公司默认时薪"
	grid.add_child(w)
	# 4 改薪
	var wb := Button.new()
	wb.text = "改"
	wb.tooltip_text = "按左边填的时薪给这个人改薪"
	wb.pressed.connect(func() -> void:
		var txt := w.text.strip_edges()
		if txt == "" or not txt.is_valid_float():     # ★ 空/乱填 → 不改(别悄悄归零)
			_flash("时薪要填数字", false)
			return
		Commands.cmd("company_wage", {"company": _cid, "npc": pid,
			"wage": txt.to_float()}))
	grid.add_child(wb)
	# 5/6 排班(只影响他自己, 不动公司营业时间)
	var work := Protocol.as_dict(Store.npc(pid).get("work", {}))
	var oe := LineEdit.new()
	oe.text = _hm(int(Protocol.num(work.get("open", 0))))
	oe.custom_minimum_size.x = 46
	grid.add_child(oe)
	var ce := LineEdit.new()
	ce.text = _hm(int(Protocol.num(work.get("close", 1440))))
	ce.custom_minimum_size.x = 46
	grid.add_child(ce)
	# 7 排班
	var sb := Button.new()
	sb.text = "排"
	sb.tooltip_text = "按左边填的上班/下班时刻给他排班"
	sb.pressed.connect(func() -> void:
		var a := _minutes(oe.text)
		var b := _minutes(ce.text)
		if a < 0 or b < 0 or a >= b:                  # ★ 时刻要合法(以前安静地排成空班)
			_flash("班次要像 08:00–19:00（且上班早于下班）", false)
			return
		Commands.cmd("company_schedule", {"company": _cid, "npc": pid,
			"open": a, "close": b}))
	grid.add_child(sb)


## 时薪显示: 保留小数, 但不要把 3.00 写成 3.00 —— 3 / 1.1 / 12.5 这样。
func _wage_txt(v: float) -> String:
	var s := "%.2f" % v
	while s.contains(".") and s.ends_with("0"):
		s = s.substr(0, s.length() - 1)
	if s.ends_with("."):
		s = s.substr(0, s.length() - 1)
	return s


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
		var txt := le.text.strip_edges()
		if txt == "" or not txt.is_valid_float():     # ★ 空/乱填 → 别把招聘时薪悄悄写成 0
			_flash("招聘时薪要填数字", false)
			return
		Commands.cmd("company_hire", {"company": _cid,
			"slots": int(sp.value), "wage_per_hour": txt.to_float()}))
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
	var price := Protocol.num(e.get("price", 0.0))
	if _is_mfg():
		# 加工厂不零售: 价由批发市场按物品定义定, 这里只显示(以前单独一页纯只读, 太浪费)
		var pl := Label.new()
		pl.text = "收购价 ¥%s（市场定）" % _wage_txt(price)
		pl.add_theme_color_override("font_color", Color("7f8ea3"))
		row.add_child(pl)
		return row
	# ★ 零售: 就地改售价(原"价格调整"页并入这里)
	var le := LineEdit.new()
	le.text = _wage_txt(price)
	le.custom_minimum_size.x = 62
	le.tooltip_text = "这个的售价 ¥ —— 顾客要看见或听人说, 才会知道新价格"
	row.add_child(le)
	var pb := Button.new()
	pb.text = "改价"
	var eid := Protocol.s(e.get("id", ""))
	pb.pressed.connect(func() -> void:
		var txt := le.text.strip_edges()
		if txt == "" or not txt.is_valid_float() or txt.to_float() <= 0.0:
			_flash("售价要填正数", false)         # 别把货改成 0 价(会被白拿)
			return
		Commands.cmd("set_price", {"entity": eid, "price": txt.to_float()}))
	row.add_child(pb)
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


## "HH:MM" → 当天分钟; 【非法返回 -1】(以前回 0 → 打错的时刻会安静地变成 00:00)
func _minutes(s: String) -> int:
	var parts := s.strip_edges().split(":")
	if parts.size() != 2 or not parts[0].is_valid_int() 			or not parts[1].is_valid_int():
		return -1
	var h := int(parts[0])
	var m := int(parts[1])
	if h < 0 or h > 24 or m < 0 or m > 59:
		return -1
	var v := h * 60 + m
	return v if v <= 1440 else -1


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
