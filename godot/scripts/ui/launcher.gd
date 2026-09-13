# launcher.gd —— 启动界面(主菜单): 列 config/scenes 下的场景, 选择后进入观察器。
#
# 对标游戏"选择地图"界面: 左侧场景列表, 右侧详情 + 开始按钮, 底部设置/退出。
# 设置以叠加层(settings_menu.tscn)打开, 关闭后回到本界面。
extends Control

var _scenes: Array = []
var _settings: Control = null


func _ready() -> void:
	%SceneList.item_selected.connect(_on_select)
	%SceneList.item_activated.connect(func(_i: int) -> void: _start())
	%RefreshButton.pressed.connect(_refresh)
	%StartButton.pressed.connect(_start)
	%EditorButton.pressed.connect(func() -> void: App.open_editor())
	%SettingsButton.pressed.connect(_open_settings)
	%QuitButton.pressed.connect(_quit)
	Store.connection_changed.connect(_update_status)
	_refresh()
	_update_status(Store.connection)


# --- 场景列表 -------------------------------------------------------------
func _refresh() -> void:
	_scenes = SceneCatalog.list_scenes()
	%SceneList.clear()
	for s in _scenes:
		var suffix := "" if bool(s["ok"]) else "   ⚠ " + str(s["error"])
		%SceneList.add_item("%s    %d NPC · %d 地点 · %d 物品%s" % [
			s["name"], s["npcs"], s["locations"], s["entities"], suffix])
	if _scenes.is_empty():
		%DetailTitle.text = "未找到场景"
		%DetailMeta.text = "把编辑器导出的 .json 放到：\n%s" % SceneCatalog.scenes_dir()
		%DetailPath.text = ""
		%StartButton.disabled = true
		return
	%SceneList.select(0)
	_on_select(0)


func _on_select(index: int) -> void:
	if index < 0 or index >= _scenes.size():
		return
	var s: Dictionary = _scenes[index]
	%DetailTitle.text = str(s["name"])
	%DetailMeta.text = "%d NPC · %d 地点 · %d 物品" % [
		s["npcs"], s["locations"], s["entities"]]
	%DetailPath.text = str(s["rel"])
	%StartButton.disabled = not bool(s["ok"])


func _start() -> void:
	var sel: PackedInt32Array = %SceneList.get_selected_items()
	if sel.is_empty():
		return
	var s: Dictionary = _scenes[sel[0]]
	if not bool(s["ok"]):
		return
	App.start_game(str(s["rel"]))


# --- 其它 -----------------------------------------------------------------
func _open_settings() -> void:
	if _settings != null and is_instance_valid(_settings):
		return
	_settings = load("res://scenes/settings_menu.tscn").instantiate()
	add_child(_settings)
	_settings.closed.connect(func() -> void:
		_settings.queue_free()
		_settings = null)


func _quit() -> void:
	get_tree().quit()


func _update_status(status: String) -> void:
	match status:
		"open":
			%StatusLabel.text = "● 后端已连接"
		"connecting":
			%StatusLabel.text = "○ 正在连接后端…"
		_:
			%StatusLabel.text = "○ 后端未连接"
