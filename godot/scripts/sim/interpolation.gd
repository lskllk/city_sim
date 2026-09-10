# interpolation.gd —— 纯视觉插值(镜像 simulation/interpolation.ts)。
#
# interpolation 只是表现处理, 不是 simulation: 不修改任何后端状态。
class_name Interp
extends RefCounted


static func lerp(a: float, b: float, t: float) -> float:
	return a + (b - a) * t


## 帧率无关平滑系数: alpha = 1 - exp(-dt*k)。dt 秒。
static func frame_alpha(dt_seconds: float, k: float) -> float:
	return 1.0 - exp(-dt_seconds * k)


static func dist(a: Vector2, b: Vector2) -> float:
	return a.distance_to(b)


## 后端 position 是 [x, y] 或 null; 统一成 Vector2。
static func to_vec2(p: Variant) -> Vector2:
	if typeof(p) == TYPE_ARRAY and (p as Array).size() >= 2:
		return Vector2(Protocol.num(p[0]), Protocol.num(p[1]))
	return Vector2.ZERO
