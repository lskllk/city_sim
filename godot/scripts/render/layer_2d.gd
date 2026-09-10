# layer_2d.gd —— 渲染层基类: 提供世界坐标下的文本居中绘制。
#
# 各渲染层(Map/Entity/Overlay)继承它, 共享 draw_* 辅助。
class_name Layer2D
extends Node2D


## 在世界坐标 center 处居中绘制一行文本(基线按字形高度估算)。
func draw_centered(font: Font, text: String, center: Vector2, font_size: int, color: Color) -> void:
	if text == "":
		return
	var sz := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size)
	var pos := Vector2(center.x - sz.x * 0.5, center.y + sz.y * 0.35)
	draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, color)
