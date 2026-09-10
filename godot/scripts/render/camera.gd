# camera.gd —— pan(drag) / zoom(wheel, 锚定鼠标) / reset(fit world)。
#
# 只管 world<->screen 变换; 不含任何 simulation 语义。镜像前端 engine/pixi/Camera.ts。
class_name WorldCamera
extends RefCounted

const MIN_ZOOM := 0.15
const MAX_ZOOM := 8.0
const PAD := 24.0

var root: Node2D
var zoom := 1.0
var tx := 0.0
var ty := 0.0
var view_w := 1.0
var view_h := 1.0
var last_w := 1280.0
var last_h := 800.0


func _init(world_root: Node2D) -> void:
	root = world_root


func resize(w: float, h: float) -> void:
	view_w = max(1.0, w)
	view_h = max(1.0, h)
	apply()


func fit_world(world_w: float, world_h: float) -> void:
	last_w = world_w
	last_h = world_h
	if world_w <= 0.0 or world_h <= 0.0:
		return
	var z := minf(
		(view_w - PAD * 2.0) / world_w,
		minf((view_h - PAD * 2.0) / world_h, MAX_ZOOM)
	)
	zoom = clampf(z, MIN_ZOOM, MAX_ZOOM)
	tx = (view_w - world_w * zoom) / 2.0
	ty = (view_h - world_h * zoom) / 2.0
	apply()


func reset() -> void:
	fit_world(last_w, last_h)


func apply() -> void:
	if root == null:
		return
	root.position = Vector2(tx, ty)
	root.scale = Vector2(zoom, zoom)


func screen_to_world(p: Vector2) -> Vector2:
	return (p - Vector2(tx, ty)) / zoom


func world_to_screen(p: Vector2) -> Vector2:
	return p * zoom + Vector2(tx, ty)


func pan_by(delta: Vector2) -> void:
	tx += delta.x
	ty += delta.y
	apply()


func zoom_at(factor: float, screen_pos: Vector2, world_w: float = 1280.0, world_h: float = 800.0) -> void:
	last_w = world_w
	last_h = world_h
	# 保持鼠标下的世界点不动
	var w := (screen_pos - Vector2(tx, ty)) / zoom
	zoom = clampf(zoom * factor, MIN_ZOOM, MAX_ZOOM)
	tx = screen_pos.x - w.x * zoom
	ty = screen_pos.y - w.y * zoom
	apply()
