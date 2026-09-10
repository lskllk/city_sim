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

@onready var _reset_button: Button = %ResetButton
@onready var _sel_label: Label = %SelLabel
@onready var _rate_bar: HBoxContainer = %RateBar
@onready var _conn_banner: Label = %ConnBanner
@onready var _hover_tip: PanelContainer = %HoverTip
@onready var _hover_label: Label = %HoverLabel

var camera: WorldCamera
var _rate_buttons: Dictionary = {}      # speed -> Button
var _panning := false
var _last_mouse := Vector2.ZERO
var _canvas_key := ""


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_CLICK

	camera = WorldCamera.new(camera_root)
	camera.resize(size.x, size.y)

	_reset_button.pressed.connect(reset_view)
	for node_name in RATE_BY_NODE:
		var spd: String = RATE_BY_NODE[node_name]
		var btn: Button = _rate_bar.get_node(String(node_name))
		_rate_buttons[spd] = btn
		btn.pressed.connect(func(): Commands.cmd("set_speed", {"speed": spd}))

	Store.hello_received.connect(_refresh_world)
	Store.snapshot_applied.connect(_on_snapshot)
	Store.selection_changed.connect(_on_selection)
	Store.connection_changed.connect(_on_connection)
	mouse_exited.connect(func(): _hover_tip.visible = false)

	_refresh_world()
	_refresh_hud()


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
			var stock := Protocol.num(e.get("stock"), -1.0)
			if stock >= 0.0:
				out.append("库存 %d" % int(stock))
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
