# pause_menu.gd —— 观察器内暂停菜单(Esc 打开)。
#
# 标准游戏暂停面板: 继续 / 设置 / 返回主菜单 / 退出。
# "设置"以叠加层打开; "返回主菜单"经 App.return_to_launcher() 回到启动界面。
extends Control

var _settings: Control = null


func _ready() -> void:
	visible = false
	%Resume.pressed.connect(_resume)
	%SettingsButton.pressed.connect(_open_settings)
	%MainMenu.pressed.connect(func() -> void: App.return_to_launcher())
	%Quit.pressed.connect(func() -> void: get_tree().quit())


func _unhandled_input(event: InputEvent) -> void:
	if not event.is_action_pressed("ui_cancel"):
		return
	if _settings != null and is_instance_valid(_settings):
		return  # 设置叠加层自己处理 Esc
	_toggle()
	get_viewport().set_input_as_handled()


func _toggle() -> void:
	visible = not visible
	if visible:
		Commands.cmd("set_speed", {"speed": "pause"})


func _resume() -> void:
	visible = false


func _open_settings() -> void:
	if _settings != null and is_instance_valid(_settings):
		return
	_settings = load("res://scenes/settings_menu.tscn").instantiate()
	add_child(_settings)
	_settings.closed.connect(func() -> void:
		_settings.queue_free()
		_settings = null)
