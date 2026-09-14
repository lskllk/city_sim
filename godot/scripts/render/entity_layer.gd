# entity_layer.gd —— NPC 圆点层(屏幕坐标绘制, 画在建筑/道路矢量层之上)。
#
# 规则: **只在路上显示**。人在建筑里不画圆点(否则点房子会误选到人)。
# 位置来自后端 travel.waypoints + depart/arrive, 本层只沿折线插值, 不算路径
# (寻路归后端 world/roads.py)。
# 帧间用本地 tick 时钟推进(delta × Store.tps), 按快照 tick 软纠偏 → 走起来连续。
#
# 为何用屏幕坐标: ① 不会被建筑/道路盖住 ② 圆点能按像素给最小尺寸
# (0.3 m 直径在缩放后不足 1 px) ③ 文字始终清晰。
class_name EntityLayer
extends Control

const DOT_M := 0.3            # 目标直径(米)
const DOT_MIN_PX := 4.0       # 屏幕最小直径(否则缩放后看不见)
const DOT_MAX_PX := 9.0
const PICK_MIN_PX := 9.0      # 命中半径(像素)
const SYNC_SNAP := 3.0        # 与快照 tick 偏差超过此值 → 硬同步
const FOLLOW_K := 8.0         # tick 软纠偏速率

const C_MOVING := Color("ffb347")
const C_SELECTED := Color("ffd166")
const C_EDGE := Color(0.05, 0.06, 0.09, 0.85)
const C_TEXT := Color(1, 1, 1, 0.92)

var camera: WorldCamera = null

var _tick_f: float = 0.0      # 本地插值时钟(单位: tick)
var _sel: String = ""


func setup(cam: WorldCamera) -> void:
	camera = cam


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(delta: float) -> void:
	_advance_clock(delta)
	queue_redraw()


# ---------------------------------------------------------------------------
# 时钟: 帧间推进 + 快照纠偏
# ---------------------------------------------------------------------------
func _advance_clock(delta: float) -> void:
	if Store.tps <= 0.0:                     # 暂停 → 直接对齐真值
		_tick_f = float(Store.tick)
		return
	var diff := float(Store.tick) - _tick_f
	if absf(diff) > SYNC_SNAP:               # 首帧 / 切场景 / 严重漂移
		_tick_f = float(Store.tick)
		return
	_tick_f += delta * Store.tps + diff * Interp.frame_alpha(delta, FOLLOW_K)


# ---------------------------------------------------------------------------
# 绘制
# ---------------------------------------------------------------------------
func _draw() -> void:
	if camera == null:
		return
	var r := _dot_radius()
	var font := get_theme_default_font()
	for pid in Store.npcs:
		if not _traveling(pid):
			continue                          # 在建筑里(含已到站) → 不画
		var sp := camera.world_to_screen(world_pos_of(pid))
		if sp.x < -32.0 or sp.y < -32.0 or sp.x > size.x + 32.0 or sp.y > size.y + 32.0:
			continue
		var sel: bool = pid == _sel
		draw_circle(sp, r + 0.8, C_EDGE)          # 描边(叠一个略大的深色圆, 不用 draw_arc)
		draw_circle(sp, r, C_SELECTED if sel else C_MOVING)
		if sel and font != null:
			var nm := Protocol.s(Store.npc(pid).get("name", pid), pid)
			draw_string(font, sp + Vector2(-24.0, -r - 5.0), nm,
					HORIZONTAL_ALIGNMENT_CENTER, 48.0, 11, C_TEXT)


func _dot_radius() -> float:
	var px := DOT_M * 0.5 * camera.zoom      # 0.3 m 直径 → 半径(屏幕像素)
	return clampf(px, DOT_MIN_PX * 0.5, DOT_MAX_PX * 0.5)


# ---------------------------------------------------------------------------
# 位置: 只在途中有意义
# ---------------------------------------------------------------------------
func _traveling(pid: String) -> bool:
	if not Store.npcs.has(pid):
		return false
	var tv := Protocol.as_dict(Store.npc(pid).get("travel", null))
	if Protocol.as_array(tv.get("waypoints", [])).size() < 2:
		return false
	# 到站即不再画: 观察驱动下可能丢帧, 客户端自己收尾
	# (否则到站帧被丢会留下一个永远在走的幽灵圆点)。
	return float(Store.tick) < Protocol.num(tv.get("arrive"))


## 沿 waypoints 按 (now - depart) / (arrive - depart) 插值(世界坐标)。
func world_pos_of(pid: String) -> Vector2:
	var tv := Protocol.as_dict(Store.npc(pid).get("travel", null))
	var wps := Protocol.as_array(tv.get("waypoints", []))
	if wps.size() < 2:
		return Vector2.ZERO
	var d := float(Protocol.num(tv.get("depart")))
	var a := float(Protocol.num(tv.get("arrive")))
	var t := 1.0 if a <= d else clampf((_tick_f - d) / (a - d), 0.0, 1.0)
	return _along(wps, t)


## 按弧长比例 t∈[0,1] 在折线上取点(折线 = 路中心线, 所以人始终走在路中间)。
static func _along(wps: Array, t: float) -> Vector2:
	var pts: Array[Vector2] = []
	for p in wps:
		pts.append(Interp.to_vec2(p))
	if pts.size() < 2:
		return pts[0] if pts.size() == 1 else Vector2.ZERO
	var total := 0.0
	for i in range(pts.size() - 1):
		total += pts[i].distance_to(pts[i + 1])
	if total <= 0.0001:
		return pts[0]
	var want := total * t
	var acc := 0.0
	for i in range(pts.size() - 1):
		var seg := pts[i].distance_to(pts[i + 1])
		if acc + seg >= want:
			var k := 0.0 if seg <= 0.0001 else (want - acc) / seg
			return pts[i].lerp(pts[i + 1], k)
		acc += seg
	return pts[pts.size() - 1]


# ---------------------------------------------------------------------------
# 对外契约(WorldCanvas 调用)
# ---------------------------------------------------------------------------
func reconcile() -> void:
	pass          # 位置是每帧从快照现算的, 无需增删节点


func apply_targets() -> void:
	queue_redraw()


func set_selected(id: String) -> void:
	_sel = id
	queue_redraw()


## 只命中【在路上】的 NPC → 点建筑不会误选到屋里的人。
func pick_npc(world_pos: Vector2) -> String:
	if camera == null:
		return ""
	var best := ""
	var best_d := PICK_MIN_PX / maxf(0.0001, camera.zoom)
	for pid in Store.npcs:
		if not _traveling(pid):
			continue
		var d := world_pos_of(pid).distance_to(world_pos)
		if d <= best_d:
			best_d = d
			best = pid
	return best


func pick_entity(_world_pos: Vector2) -> String:
	return ""
