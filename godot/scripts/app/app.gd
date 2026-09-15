# app.gd —— 应用状态机 + WS 消息分发(autoload 名 `App`)。
#
# 职责(标准游戏框架里的 "Game"/"Session" 单例):
#   - 状态机: 启动界面(LAUNCHER) / 观察器(GAME) / 编辑器(EDITOR);
#   - 持有唯一的网络 wiring(Net -> Store), 场景切换不重复连接;
#   - start_game(scene_rel): 让后端 reset 到该场景, 再切到观察器场景;
#   - open_editor(): 切到地图编辑器;
#   - return_to_launcher(): 暂停仿真 + 清空世界 + 切回启动界面;
#   - UI 通过 Commands 发命令, 不直接碰 Net。
extends Node

enum State { LAUNCHER, GAME, EDITOR }
signal state_changed(state: int)

var state: int = State.LAUNCHER
var current_scene_rel: String = ""
var _pending_scene: String = ""

# 断线自愈: 后端可能挂了/被手动杀了, 而 Godot 只在启动时拉过一次。
# 连不上超过 REENSURE_SEC 就再叫一次 Backend.ensure()(幂等: 端口在就跳过)。
const REENSURE_SEC := 8.0
var _down_for := 0.0


func _process(delta: float) -> void:
	if Net.status() == "open":
		_down_for = 0.0
		return
	_down_for += delta
	if _down_for >= REENSURE_SEC:
		_down_for = 0.0
		if OS.get_environment("CITYSIM_NO_AUTOSTART") != "1":
			Backend.call_deferred("ensure")


func _ready() -> void:
	Net.message_received.connect(_on_message)
	Net.status_changed.connect(_on_status)
	Commands.set_sender(func(obj: Variant) -> void: Net.send(obj))
	Settings.changed.connect(_on_settings_changed)
	Net.configure_from_settings()
	Net.start()


# --- 状态迁移 -------------------------------------------------------------
func start_game(scene_rel: String) -> void:
	current_scene_rel = scene_rel
	_pending_scene = scene_rel
	Store.clear_world()
	_try_load_pending()
	# 若后端还没起来(设置里关了自动启动 / 启动失败), 点开始时兜底拉起。
	if Net.status() != "open" and OS.get_environment("CITYSIM_NO_AUTOSTART") != "1":
		Backend.call_deferred("ensure")
	if state != State.GAME:
		state = State.GAME
		state_changed.emit(state)
	get_tree().change_scene_to_file("res://scenes/main.tscn")


## 进入地图编辑器(不依赖后端; 后端连接保留, 便于返回后直接开始)。
func open_editor() -> void:
	Commands.cmd("set_speed", {"speed": "pause"})
	if state != State.EDITOR:
		state = State.EDITOR
		state_changed.emit(state)
	get_tree().change_scene_to_file("res://scenes/editor/editor.tscn")


func return_to_launcher() -> void:
	Commands.cmd("set_speed", {"speed": "pause"})
	_pending_scene = ""
	current_scene_rel = ""
	Store.clear_world()
	if state != State.LAUNCHER:
		state = State.LAUNCHER
		state_changed.emit(state)
	get_tree().change_scene_to_file("res://scenes/launcher.tscn")


## 连接就绪后把待加载场景告诉后端(场景参数走 reset 命令的 scenario 字段)。
func _try_load_pending() -> void:
	if _pending_scene == "" or Net.status() != "open":
		return
	# 概率类参数: < 0 表示"跟随 config/sim.toml [social]" → 【不下发】,
	# 免得像以前那样用面板里的默认值把配置文件盖掉。
	var args := {
		"scenario": _pending_scene,
		"seed": int(Settings.get_value("game", "seed", 3)),
	}
	for k in ["tell_p", "listen_p", "tell_same_home", "tell_stranger"]:
		var v := float(Settings.get_value("game", k, -1.0))
		if v >= 0.0:
			args[k] = v
	Commands.cmd("reset", args)
	_pending_scene = ""


func _on_settings_changed(section: String, key: String, _value: Variant) -> void:
	if section == "network" and key == "ws_url":
		Net.configure_from_settings()


# --- 网络回调(镜像 App.tsx::dispatch) --------------------------------------
func _on_status(status: String) -> void:
	Store.set_connection(status)
	if status == "open":
		_try_load_pending()


func _on_message(envelope: Variant) -> void:
	var env := Protocol.as_dict(envelope)
	if env.is_empty():
		return
	var kind := Protocol.s(env.get("kind"))
	var payload: Variant = env.get("payload", {})
	match kind:
		"hello":
			Store.clear_world()
			Store.init_hello(Protocol.as_dict(payload))
		"snapshot":
			var snap := Protocol.as_dict(payload)
			if snap.has("tick"):
				Store.apply_snapshot(snap)
		"event":
			# 事件流: 死亡等要反映到镜像上(npcs/entities 的删除)
			Store.apply_event(Protocol.as_dict(payload))
		"reply", "pong":
			pass  # 应答可忽略
		_:
			push_warning("[App] unknown message kind: %s" % kind)
