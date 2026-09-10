# main.gd —— 入口: WS 生命周期 + 消息分发。
#
# 布局/节点树在 scenes/main.tscn 静态定义; 本脚本只做 wiring:
#   Net(通信) --message_received--> dispatch --> Store(镜像) --signals--> UI/渲染层
#   UI --Commands.cmd--> sender --> Net.send
# 镜像前端 app/App.tsx 的 dispatch。
extends Control


func _ready() -> void:
	RenderingServer.set_default_clear_color(Color("06080c"))

	Net.message_received.connect(_on_message)
	Net.status_changed.connect(_on_status)
	Commands.set_sender(_send)
	Net.start()

	# 无头集成冒烟: CITYSIM_SMOKE=1 时挂载探针, 轮换选中以走完 Inspector 构建路径。
	if OS.get_environment("CITYSIM_SMOKE") == "1":
		var probe: Node = load("res://scripts/debug/smoke_probe.gd").new()
		probe.name = "SmokeProbe"
		add_child(probe)


func _send(obj: Variant) -> void:
	Net.send(obj)


# ---------------------------------------------------------------------------
# 消息分发(镜像 App.tsx::dispatch)
# ---------------------------------------------------------------------------
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
			else:
				push_warning("[main] snapshot payload invalid; ignored")
		"event":
			pass  # 全局事件流不在 observer 布局内; NPC 事件随 snapshot 携带
		"reply", "pong":
			pass  # MVP 不主动 query; 应答可忽略
		_:
			push_warning("[main] unknown message kind: %s" % kind)


func _on_status(status: String) -> void:
	Store.set_connection(status)
