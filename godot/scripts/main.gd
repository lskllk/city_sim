# main.gd —— 观察器入场: 渲染初始化 + 挂载菜单层。
#
# WS 生命周期/消息分发已上移到 autoload `App`(场景切换不重复连接)。
# 本场景只负责: 世界布局(main.tscn) + 暂停/设置叠加层 + 可选冒烟探针。
extends Control


func _ready() -> void:
	RenderingServer.set_default_clear_color(Color("06080c"))
	_mount_menus()

	# 无头集成冒烟: CITYSIM_SMOKE=1 时挂载探针, 轮换选中以走完 Inspector 构建路径。
	if OS.get_environment("CITYSIM_SMOKE") == "1":
		var probe: Node = load("res://scripts/debug/smoke_probe.gd").new()
		probe.name = "SmokeProbe"
		add_child(probe)


func _mount_menus() -> void:
	var layer := CanvasLayer.new()
	layer.name = "MenuLayer"
	layer.layer = 10
	add_child(layer)
	var pause: Control = load("res://scenes/pause_menu.tscn").instantiate()
	layer.add_child(pause)
