# backend.gd —— 可选: Godot 启动时自动拉起 Python 后端(autoload 名 `Backend`)。
#
# 行为:
#   1. 先探测 ws 端口是否已在监听(如 run.cmd 已起后端) → 在跑就不重复启动。
#   2. 没在跑 → OS.create_process 拉起 `python -m uvicorn ...`, 记住 pid。
#   3. Godot 退出时 OS.kill 收掉自己拉起的进程(不影响外部已存在的后端)。
#
# 环境变量:
#   CITYSIM_NO_AUTOSTART=1     关闭自动启动
#   CITYSIM_PYTHON=...         python 可执行文件(默认 "python", 失败回退 "py")
#   CITYSIM_WS_URL=ws://...    后端端点(默认 ws://127.0.0.1:8765/ws)
#   CITYSIM_BACKEND_CONSOLE=0  不弹后端控制台窗口(默认弹, 便于看日志)
extends Node

var _pid := -1
var _spawned := false


func _ready() -> void:
	if OS.get_environment("CITYSIM_NO_AUTOSTART") == "1":
		return
	call_deferred("_ensure")


func _ensure() -> void:
	var port := _port()
	if await _port_open("127.0.0.1", port, 600):
		print("[Backend] already listening on :%d — skip autostart" % port)
		return
	_spawn(port)


# --- 内部 --------------------------------------------------------------
func _port() -> int:
	var u := OS.get_environment("CITYSIM_WS_URL").strip_edges()
	if u == "":
		u = "ws://127.0.0.1:8765/ws"
	var no_scheme := u.trim_prefix("ws://").trim_prefix("wss://")
	var host_port := no_scheme.split("/")[0]
	var parts := host_port.split(":")
	if parts.size() >= 2 and parts[1].is_valid_int():
		return int(parts[1])
	return 8765


func _repo_root() -> String:
	# res:// = godot/ 目录; 仓库根 = 其上一级
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()


func _spawn(port: int) -> void:
	var root := _repo_root()
	OS.set_environment("PYTHONPATH", root.path_join("src"))
	var py := OS.get_environment("CITYSIM_PYTHON").strip_edges()
	if py == "":
		py = "python"
	var open_console := OS.get_environment("CITYSIM_BACKEND_CONSOLE") != "0"
	var args := PackedStringArray(["-m", "uvicorn",
		"citysim.gateway.server:app", "--port", str(port)])
	_pid = OS.create_process(py, args, open_console)
	if _pid <= 0 and py == "python":
		_pid = OS.create_process("py", args, open_console)   # Windows py launcher
	_spawned = _pid > 0
	if _spawned:
		print("[Backend] started: %s -m uvicorn citysim.gateway.server:app --port %d (pid=%d)"
			% [py, port, _pid])
	else:
		push_warning("[Backend] 自动启动失败: 请确认已安装 viz 依赖 "
			+ "(python -m pip install -e \".[viz]\"), 或手动运行 run.cmd")


func _port_open(host: String, port: int, timeout_ms: int) -> bool:
	var tcp := StreamPeerTCP.new()
	if tcp.connect_to_host(host, port) != OK:
		return false
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < timeout_ms:
		tcp.poll()
		var st := tcp.get_status()
		if st == StreamPeerTCP.STATUS_CONNECTED:
			tcp.disconnect_from_host()
			return true
		if st == StreamPeerTCP.STATUS_ERROR:
			return false
		await get_tree().process_frame
	return false


func _exit_tree() -> void:
	_kill()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_kill()


func _kill() -> void:
	if _spawned and _pid > 0:
		OS.kill(_pid)
		print("[Backend] stopped pid=%d" % _pid)
	_spawned = false
	_pid = -1
