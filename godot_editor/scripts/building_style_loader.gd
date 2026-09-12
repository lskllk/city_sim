extends Node
## AssetStyle —— 建筑"资产"样式加载器(autoload 名 `AssetStyle`)。
##
## 唯一权威在观察器项目 `godot/`(CitySim Observatory): 编辑器不自己定义建筑底色/徽记,
## 而是运行时加载观察器里的 `godot/scripts/render/building_style.gd`, 做到
## "观察器怎么渲染, 编辑器就怎么渲染"。
##
## 跨项目加载失败(观察器目录缺失)时退化为中性灰, 保证编辑器仍可用。

const REL_PATH := "godot/scripts/render/building_style.gd"
const ZH_PATH := "godot/scripts/ui/zh.gd"
const FALLBACK_COLOR := Color("3d4a60")

var _style: GDScript = null
var _zh: GDScript = null


func _ready() -> void:
	_style = _load(REL_PATH)
	_zh = _load(ZH_PATH)
	if _style == null:
		push_warning("[AssetStyle] 未找到观察器样式 %s, 使用中性回退" % REL_PATH)


func _load(rel: String) -> GDScript:
	var root := ProjectSettings.globalize_path("res://").path_join("..").simplify_path()
	var path := root.path_join(rel)
	if not FileAccess.file_exists(path):
		return null
	return load(path) as GDScript


func available() -> bool:
	return _style != null


func source_path() -> String:
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path() \
		.path_join(REL_PATH)


## kind -> 类别底色(与观察器完全一致)。
func kind_color(kind: String) -> Color:
	if _style != null:
		return _style.kind_color(kind)
	return FALLBACK_COLOR


## side -> 房间局部朝外法线。
func side_normal(side: String) -> Vector2:
	if _style != null:
		return _style.side_normal(side)
	match side:
		"north": return Vector2(0, -1)
		"east": return Vector2(1, 0)
		"west": return Vector2(-1, 0)
		_: return Vector2(0, 1)


func draw_emblem(ci: CanvasItem, center: Vector2, kind: String, base: Color) -> void:
	if _style != null:
		_style.draw_emblem(ci, center, kind, base)


func draw_centered(ci: CanvasItem, font: Font, text: String,
		center: Vector2, font_size: int, color: Color) -> void:
	if _style != null:
		_style.draw_centered(ci, font, text, center, font_size, color)


func draw_door(ci: CanvasItem, pos: Vector2, normal: Vector2,
		size: float, color: Color) -> void:
	if _style != null:
		_style.draw_door(ci, pos, normal, size, color)


## 道路折线(圆角接头)。共享实现; 观察器缺失时就地回退同一算法。
func draw_road(ci: CanvasItem, pts: PackedVector2Array, width_px: float,
		color: Color = Color("59636f")) -> void:
	if _style != null:
		_style.draw_road(ci, pts, width_px, color)
		return
	if pts.size() < 2:
		return
	var w := maxf(width_px, 2.0)
	for i in range(pts.size() - 1):
		ci.draw_line(pts[i], pts[i + 1], color, w, true)
	for p in pts:
		ci.draw_circle(p, w * 0.5, color)


## 展示文案复用观察器 zh.gd(与观察器完全一致)。
func kind_zh(kind: String) -> String:
	return _zh.kind_zh(kind) if _zh != null else kind


func role_zh(code: String) -> String:
	return _zh.role_zh(code) if _zh != null else code


func item_zh(type_id: String) -> String:
	return _zh.item_zh(type_id) if _zh != null else type_id
