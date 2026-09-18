# world_canvas.gd —— 世界画布: 相机 + 三层渲染 + 输入 + HUD。
#
# 节点树在 scenes/main.tscn 里静态定义(可在编辑器直接拖拽/改样式);
# 本脚本只做接线与运行时驱动: 数据来自 Store, 命令走 Commands。
# 镜像前端 views/WorldView.tsx + engine/pixi/SimulationStage.ts。
class_name WorldCanvas
extends Control

## HUD 速率按钮节点名 -> 后端 speed 档位。
const RATE_BY_NODE := {
	"RatePause": "pause",
	"Rate1x": "1x",
	"Rate10x": "10x",
	"Rate100x": "100x",
	"Rate1000x": "1000x",
}

@onready var camera_root: Node2D = %WorldRoot
@onready var map_layer: MapLayer = %MapLayer
@onready var entity_layer: EntityLayer = %EntityLayer
@onready var overlay_layer: OverlayLayer = %OverlayLayer
@onready var map_labels: MapLabels = %MapLabels
@onready var bubble_layer: Control = %BubbleLayer   # 不写 class_name 类型:
                                                           # 免依赖类注册表缓存

@onready var _reset_button: Button = %ResetButton
@onready var _sel_label: Label = %SelLabel
@onready var _money_label: Label = %MoneyLabel
@onready var _clock_label: Label = %ClockLabel
@onready var _net_label: Label = %NetLabel
@onready var _rate_bar: HBoxContainer = %RateBar
@onready var _conn_banner: Label = %ConnBanner
@onready var _hover_tip: PanelContainer = %HoverTip
@onready var _hover_label: Label = %HoverLabel

var camera: WorldCamera
var _rate_buttons: Dictionary = {}      # speed -> Button
var _panning := false
var _last_mouse := Vector2.ZERO
var _canvas_key := ""


const CompanyCanvasScript := preload("res://scripts/render/company_canvas.gd")

var company_canvas: Control = null      # 公司抽象画布(选中公司建筑时出现)


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_CLICK
	# 公司抽象画布: 代码创建(不动 main.tscn), 叠在最上层右上角
	company_canvas = CompanyCanvasScript.new()
	company_canvas.name = "CompanyCanvas"
	company_canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	company_canvas.anchor_left = 1.0
	company_canvas.anchor_right = 1.0
	company_canvas.offset_left = -420.0
	company_canvas.offset_right = -12.0
	# ★ 从 HUD 下面开始: 以前是 12, 而 HUD 占 8..40 → 公司画布正好盖住
	#   右上角的【时钟/吞吐/倍数条】(用户报的"悬浮栏遮住播放条")。
	company_canvas.offset_top = 52.0
	company_canvas.offset_bottom = 360.0
	company_canvas.visible = false
	add_child(company_canvas)

	# HUD 底衬: 顶栏是直接压在地图上的, 浅色建筑/道路上的数字几乎看不清。
	# 垫一条半透明横带 —— 插在【地图图层之后、HUD 之前】, 不盖任何别的东西。
	var hud_bg := ColorRect.new()
	hud_bg.name = "HudBackdrop"
	hud_bg.color = Color(0.055, 0.065, 0.085, 0.78)
	hud_bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud_bg.anchor_right = 1.0
	hud_bg.offset_left = 0.0
	hud_bg.offset_top = 0.0
	hud_bg.offset_right = 0.0
	hud_bg.offset_bottom = 48.0
	add_child(hud_bg)
	var hud := _rate_bar.get_parent()
	move_child(hud_bg, mini(hud.get_index(), get_child_count() - 1))

	# ★ 播放条挪到【底部】: 它是全屏最常用的控件, 却挤在右上角和公司画布抢位置,
	#   而且那里最容易被盖。底部一条是播放器的通用位置, 也最稳定。
	var bottom := HBoxContainer.new()
	bottom.name = "BottomBar"
	bottom.alignment = BoxContainer.ALIGNMENT_END
	bottom.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bottom.anchor_left = 0.0
	bottom.anchor_right = 1.0
	bottom.anchor_top = 1.0
	bottom.anchor_bottom = 1.0
	bottom.offset_left = 8.0
	bottom.offset_right = -12.0
	bottom.offset_top = -42.0
	bottom.offset_bottom = -8.0
	add_child(bottom)
	_rate_bar.get_parent().remove_child(_rate_bar)
	bottom.add_child(_rate_bar)

	camera = WorldCamera.new(camera_root)
	camera.resize(size.x, size.y)
	map_labels.setup(camera)      # 建筑矢量层跟随相机投影(屏幕坐标, 不受缩放影响)
	entity_layer.setup(camera)    # NPC 圆点层同坐标系, 但画在建筑之上
	bubble_layer.setup(camera, entity_layer)   # 气泡: 要沿路点取在途位置

	_reset_button.pressed.connect(reset_view)
	for node_name in RATE_BY_NODE:
		var spd: String = RATE_BY_NODE[node_name]
		var btn: Button = _rate_bar.get_node(String(node_name))
		_rate_buttons[spd] = btn
		btn.pressed.connect(func(): Commands.cmd("set_speed", {"speed": spd}))

	Net.rate_changed.connect(_refresh_net)      # 前后端吞吐率(HUD)
	Store.hello_received.connect(_refresh_world)
	Store.snapshot_applied.connect(_on_snapshot)
	Store.selection_changed.connect(_on_selection)
	Store.connection_changed.connect(_on_connection)
	mouse_exited.connect(func(): _hover_tip.visible = false)

	_refresh_world()
	_refresh_hud()
	_refresh_net()


## HUD: 前后端数据吞吐率(WS 载荷字节/秒)。
func _refresh_net() -> void:
	_net_label.text = "↓ %s/s · ↑ %s/s" % [_fmt_bytes(Net.rx_rate()),
		_fmt_bytes(Net.tx_rate())]


static func _fmt_bytes(v: float) -> String:
	if v >= 1048576.0:
		return "%.2f MB" % (v / 1048576.0)
	if v >= 1024.0:
		return "%.1f KB" % (v / 1024.0)
	return "%d B" % int(v)


func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED and camera != null:
		camera.resize(size.x, size.y)
		# 首次拿到有效视口时补一次 fit(hello 可能早于首次布局到达)
		if _canvas_key == "":
			var w := Protocol.num(Store.canvas.get("w"), 1280.0)
			var h := Protocol.num(Store.canvas.get("h"), 800.0)
			if w > 0.0 and h > 0.0 and size.x > 1.0 and size.y > 1.0:
				_canvas_key = "%sx%s" % [w, h]
				camera.fit_world(w, h)


# ---------------------------------------------------------------------------
# 刷新
# ---------------------------------------------------------------------------
func _on_snapshot() -> void:
	_refresh_world()
	_refresh_hud()


func _on_selection() -> void:
	entity_layer.set_selected(Store.sel_npc if Store.sel_kind == "npc" else "")
	overlay_layer.refresh()
	_refresh_hud()
	_refresh_company_canvas()


## 选中【登记过公司的建筑】时, 右上角浮出公司抽象画布(员工在哪/谁在排队)
func _refresh_company_canvas() -> void:
	if company_canvas == null:
		return
	var loc: String = Store.sel_location if Store.sel_kind == "location" else ""
	company_canvas.setup(loc)


func _on_connection(_status: String) -> void:
	_refresh_hud()


func _refresh_world() -> void:
	map_layer.rebuild()
	entity_layer.reconcile()
	entity_layer.apply_targets()
	overlay_layer.refresh()

	var size_w := Protocol.num(Store.canvas.get("w"), 1280.0)
	var size_h := Protocol.num(Store.canvas.get("h"), 800.0)
	var key := "%sx%s" % [size_w, size_h]
	var view_ok := camera.view_w > 1.0 and camera.view_h > 1.0
	if key != _canvas_key and view_ok and size_w > 0.0 and size_h > 0.0:
		_canvas_key = key
		camera.fit_world(size_w, size_h)


func reset_view() -> void:
	var w := Protocol.num(Store.canvas.get("w"), 1280.0)
	var h := Protocol.num(Store.canvas.get("h"), 800.0)
	camera.fit_world(w, h)


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------
func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		_handle_button(event as InputEventMouseButton)
	elif event is InputEventMouseMotion:
		_handle_motion(event as InputEventMouseMotion)


func _handle_button(mb: InputEventMouseButton) -> void:
	if mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
		_zoom(1.15, mb.position)
		return
	if mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
		_zoom(1.0 / 1.15, mb.position)
		return

	if mb.button_index == MOUSE_BUTTON_LEFT:
		if mb.pressed and mb.double_click:
			reset_view()
			accept_event()
			return
		if mb.pressed:
			_on_press(mb.position)
		else:
			_panning = false
		return

	if mb.button_index == MOUSE_BUTTON_MIDDLE:
		_panning = mb.pressed
		_last_mouse = mb.position
		return


func _handle_motion(mm: InputEventMouseMotion) -> void:
	if _panning:
		camera.pan_by(mm.position - _last_mouse)
		_last_mouse = mm.position
	_update_hover(mm.position)


func _zoom(factor: float, screen_pos: Vector2) -> void:
	camera.zoom_at(
		factor, screen_pos,
		Protocol.num(Store.canvas.get("w"), 1280.0),
		Protocol.num(Store.canvas.get("h"), 800.0)
	)


func _on_press(screen_pos: Vector2) -> void:
	var wp := camera.screen_to_world(screen_pos)
	var npc_id := entity_layer.pick_npc(wp)
	if npc_id != "":
		Store.select("npc", npc_id)
		return
	var ent_id := entity_layer.pick_entity(wp)
	if ent_id != "":
		Store.select("entity", ent_id)
		return
	var loc_id := map_layer.hit_test(wp)
	if loc_id != "":
		Store.select("location", loc_id)
		return
	Store.clear_selection()
	_panning = true
	_last_mouse = screen_pos


## 世界坐标命中(kind/id), 未命中返回 {}。
func hover_at(screen_pos: Vector2) -> Dictionary:
	var wp := camera.screen_to_world(screen_pos)
	var npc_id := entity_layer.pick_npc(wp)
	if npc_id != "":
		return {"kind": "npc", "id": npc_id}
	var ent_id := entity_layer.pick_entity(wp)
	if ent_id != "":
		return {"kind": "entity", "id": ent_id}
	var loc_id := map_layer.hit_test(wp)
	if loc_id != "":
		return {"kind": "location", "id": loc_id}
	return {}


# ---------------------------------------------------------------------------
# HUD / 悬浮提示
# ---------------------------------------------------------------------------
func _refresh_hud() -> void:
	if _sel_label != null:
		_sel_label.text = Store.selected_name()
	if _money_label != null:
		var sel_n := Store.npc(Store.sel_npc) if Store.sel_kind == "npc" else {}
		_money_label.text = ("¥%d" % int(Protocol.num(sel_n.get("money")))) if not sel_n.is_empty() else ""
	if _clock_label != null:
		_clock_label.text = "Day %d · %s" % [Store.day, Store.clock]
	var connected := Store.connection == "open"
	for spd in _rate_buttons:
		var b: Button = _rate_buttons[spd]
		b.disabled = not connected
		b.button_pressed = (Store.speed == spd)
	if _conn_banner != null:
		if connected:
			_conn_banner.visible = false
		else:
			_conn_banner.visible = true
			_conn_banner.text = "Simulation connecting…" if Store.connection == "connecting" \
				else "Simulation disconnected — 自动重连中"


func _update_hover(screen_pos: Vector2) -> void:
	var hit := hover_at(screen_pos)
	if hit.is_empty():
		_hover_tip.visible = false
		return
	var lines := _hover_lines(hit)
	if lines.is_empty():
		_hover_tip.visible = false
		return
	_hover_label.text = "\n".join(lines)
	_hover_tip.visible = true
	_hover_tip.position = screen_pos + Vector2(14, 14)


func _hover_lines(hit: Dictionary) -> PackedStringArray:
	var out := PackedStringArray()
	match hit.get("kind", ""):
		"entity":
			var e := Store.entity(hit["id"])
			if e.is_empty():
				return out
			var icon := Protocol.s(e.get("icon", ""))
			out.append(("%s %s" % [icon, Protocol.s(e.get("name"))]).strip_edges())
			var tags: Variant = e.get("tags", [])
			if typeof(tags) == TYPE_ARRAY and (tags as Array).size() > 0:
				var zh := PackedStringArray()
				for t in (tags as Array):
					zh.append(Zh.tag_zh(str(t)))
				out.append("、".join(zh))
			# 家具一件一个, 不报库存; 货物才报份数(没有"无限"这回事)
			if not (tags as Array).has("fixture"):
				out.append("库存 %d" % int(Protocol.num(e.get("stock"), 1.0)))
			if Protocol.s(e.get("claimed_by", "")) != "":
				out.append("使用中")
		"npc":
			var n := Store.npc(hit["id"])
			if n.is_empty():
				return out
			out.append(Protocol.s(n.get("name")))
			out.append("地点 %s" % Store.name_of(Protocol.s(n.get("loc", ""))))
		"location":
			out.append(Store.name_of(hit["id"]))
	return out
