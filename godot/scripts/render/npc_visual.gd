# npc_visual.gd —— 单个 NPC 的可视化(场景 scenes/world/npc_visual.tscn)。
#
# 只负责改颜色/选中环; 位置与平滑由 EntityLayer 驱动。
extends Node2D

@onready var _body: Polygon2D = $Body
@onready var _ring: Line2D = $Ring


func set_color(c: Color) -> void:
	_body.color = c


func set_selected(selected: bool) -> void:
	_ring.visible = selected
