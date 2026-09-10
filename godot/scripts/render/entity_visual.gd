# entity_visual.gd —— 单个世界实体的可视化(场景 scenes/world/entity_visual.tscn)。
#
# 只负责底色/emoji 图标; 位置与摆放由 EntityLayer 驱动。
extends Node2D

@onready var _box: Polygon2D = $Box
@onready var _icon: Label = $Icon


func config(icon_text: String, color: Color) -> void:
	_box.color = color
	_icon.text = icon_text
