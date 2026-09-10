# smoke_probe.gd —— 无头冒烟探针(仅在 CITYSIM_SMOKE=1 时由 main 挂载)。
#
# 作用: 无 GUI 环境下轮换选中 NPC / 实体 / 地点, 强制走完 Inspector 三条构建路径,
# 用于 CI 集成冒烟。不参与正常观察器逻辑。
extends Node

var _step := 0


func _ready() -> void:
	Store.snapshot_applied.connect(_on_snapshot)


func _on_snapshot() -> void:
	_step += 1
	match _step % 3:
		1:
			_select_first(Store.npcs, "npc")
		2:
			_select_first(Store.entities, "entity")
		0:
			_select_first(Store.rooms, "location")


func _select_first(table: Dictionary, kind: String) -> void:
	var keys := table.keys()
	keys.sort()
	if keys.size() > 0:
		Store.select(kind, String(keys[0]))
