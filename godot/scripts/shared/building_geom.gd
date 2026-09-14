# building_geom.gd —— 建筑几何/布局唯一实现 (geometry single authority)。
#
# 观察器(render/) 与编辑器(editor/) 共用; 纯静态函数, 无 Node 依赖, 不做 simulation。
# 抽自原先各自维护的四角/旋转/占用标记实现, 避免两处漂移。
class_name BuildingGeom
extends RefCounted


## OBB 四角。center/size 坐标系由调用方决定(世界或屏幕)。
## rot_deg 为角度。返回顺序: +ux+uy, -ux+uy, -ux-uy, +ux-uy。
static func obb_corners(center: Vector2, size: Vector2, rot_deg: float) -> Array:
	var a := deg_to_rad(rot_deg)
	var ux := Vector2(cos(a), sin(a))
	var uy := Vector2(-sin(a), cos(a))
	var hx := ux * (size.x * 0.5)
	var hy := uy * (size.y * 0.5)
	return [center + hx + hy, center - hx + hy, center - hx - hy, center + hx - hy]


## 点是否在 OBB 内。
static func point_in_obb(center: Vector2, size: Vector2, rot_deg: float, p: Vector2) -> bool:
	var d := p - center
	var a := -deg_to_rad(rot_deg)
	var lx := d.x * cos(a) - d.y * sin(a)
	var ly := d.x * sin(a) + d.y * cos(a)
	return absf(lx) <= size.x * 0.5 and absf(ly) <= size.y * 0.5


## 两个 OBB 是否重叠(分离轴定理 SAT)。
static func obb_overlap(a_center: Vector2, a_size: Vector2, a_rot: float,
		b_center: Vector2, b_size: Vector2, b_rot: float) -> bool:
	var pa := obb_corners(a_center, a_size, a_rot)
	var pb := obb_corners(b_center, b_size, b_rot)
	var axes: Array = []
	for poly in [pa, pb]:
		for i in 4:
			var e: Vector2 = poly[(i + 1) % 4] - poly[i]
			if e.length() > 0.0001:
				axes.append(Vector2(-e.y, e.x).normalized())
	for ax in axes:
		var amin := INF
		var amax := -INF
		var bmin := INF
		var bmax := -INF
		for p in pa:
			var d: float = p.dot(ax)
			amin = minf(amin, d)
			amax = maxf(amax, d)
		for p in pb:
			var d: float = p.dot(ax)
			bmin = minf(bmin, d)
			bmax = maxf(bmax, d)
		if amax < bmin or bmax < amin:
			return false
	return true


## 门定义(side/offset) + 尺寸 → 局部(未旋转)门点与朝外法线。side 缺省 south。
static func door_local(size: Vector2, side: String, offset: float) -> Dictionary:
	match side:
		"north":
			return {"pos": Vector2(size.x * offset, -size.y * 0.5), "normal": Vector2(0, -1)}
		"east":
			return {"pos": Vector2(size.x * 0.5, size.y * offset), "normal": Vector2(1, 0)}
		"west":
			return {"pos": Vector2(-size.x * 0.5, size.y * offset), "normal": Vector2(-1, 0)}
		_:
			return {"pos": Vector2(size.x * offset, size.y * 0.5), "normal": Vector2(0, 1)}


## 绕原点旋转向量(角度, 度)。
static func rotate_vec(v: Vector2, rot_deg: float) -> Vector2:
	var a := deg_to_rad(rot_deg)
	return Vector2(v.x * cos(a) - v.y * sin(a), v.x * sin(a) + v.y * cos(a))


## 屏幕坐标下 n 个 NPC 标记中第 idx 个的位置(以建筑中心为锚, 上方横排)。
static func npc_marker_pos(center: Vector2, idx: int, count: int,
		spacing: float, lift: float) -> Vector2:
	return center + Vector2((idx - (count - 1) * 0.5) * spacing, -lift)


# --- 角标缩放 / LOD ------------------------------------------------------
#
# 角标【贴合建筑框】: 尺寸不再固定像素, 而是随建筑在屏幕上的大小缩放 ——
# 放大时角标跟着长、缩小时跟着收, 看起来是"贴在楼上的标签"。
#
# 同时做【LOD 分层】: 楼太小的时候字必然糊, 那就干脆不画;
# 只有放到字能看清了才逐级显示更多东西。
#
#   scale = 建筑屏幕短边 / BADGE_REF_PX   (夹在 MIN~MAX)
#
# 层级(按 scale):
#   LOD_NAME   建筑名
#   LOD_EMBLEM 徽记
#   LOD_BADGE  占用角标 (人/容量)
#   LOD_DETAIL 物 N / 共 N 层

const BADGE_REF_PX := 60.0       # 建筑屏幕短边 = 此值 → scale = 1.0
const BADGE_MIN_SCALE := 0.75
const BADGE_MAX_SCALE := 2.4

const LOD_NAME := 0.62
const LOD_EMBLEM := 1.05
const LOD_BADGE := 0.85
const LOD_DETAIL := 1.15


## 角标缩放系数: 由建筑屏幕短边推出。
static func badge_scale(rect: Rect2) -> float:
	return clampf(minf(rect.size.x, rect.size.y) / BADGE_REF_PX,
		BADGE_MIN_SCALE, BADGE_MAX_SCALE)


## "物 N" 角标矩形(屏幕坐标, 以建筑左上角为锚)。
static func item_badge_rect(top_left: Vector2, size := Vector2(34.0, 16.0),
		scale := 1.0) -> Rect2:
	return Rect2(top_left + Vector2(2.0, 2.0) * scale, size * scale)


## 建筑角标排(屏幕坐标, 以建筑左上角为锚): 第 i 格。
## 约定 i: 0=人 N, 1=物 N, 2=共 N 层。
static func badge_rect(top_left: Vector2, i: int, width := 36.0,
		height := 16.0, scale := 1.0) -> Rect2:
	var gap := 2.0 * scale
	var w := width * scale
	return Rect2(top_left + Vector2(2.0 * scale + i * (w + gap), 2.0 * scale),
		Vector2(w, height * scale))
