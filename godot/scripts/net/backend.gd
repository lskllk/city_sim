# backend.gd —— 可选: Godot 启动时自动拉起 Python 后端(autoload 名 `Backend`)。
#
# 行为:
#   1. 先探测 ws 端口是否已在监听(如 run.cmd 已起后端) → 在跑就不重复启动。
#   2. 没在跑 → 按候选解释器依次拉起 uvicorn, 拉起后等端口就绪才算成功;
#      失败的候选(如 Windows Store 的 python 占位符 / 缺依赖)会被跳过并试下一个。
#   3. Godot 退出时 OS.kill 收掉自己拉起的进程(不影响外部已存在的后端)。
#
# 环境变量:
#   CITYSIM_NO_AUTOSTART=1     关闭自动启动
#   CITYSIM_PYTHON=...         python 可执行文件(显式指定, 最高优先)
#   CITYSIM_WS_URL=ws://...    后端端点(默认 ws://127.0.0.1:8765/ws)
#   CITYSIM_BACKEND_CONSOLE=0  不弹后端控制台窗口(默认弹, 便于看日志)
extends Node

const READY_TIMEOUT_MS := 8000

var _pid := -1
var _spawned := false
var _ensuring := false


func _ready() -> void:
	if OS.get_environment("CITYSIM_NO_AUTOSTART") == "1":
		return
	if not bool(Settings.get_value("backend", "autostart", true)):
		return
	call_deferred("ensure")


## 确保后端在跑(幂等; 供 App 开始游戏时兜底调用)。
func ensure() -> void:
	if _ensuring:
		return
	_ensuring = true
	var port := _port()
	if await _port_open("127.0.0.1", port, 600):
		print("[Backend] already listening on :%d — skip autostart" % port)
		_ensuring = false
		return
	await _spawn(port)
	_ensuring = false


# --- 内部 --------------------------------------------------------------
func _port() -> int:
	var u := OS.get_environment("CITYSIM_WS_URL").strip_edges()
	if u == "":
		u = str(Settings.get_value("network", "ws_url", "ws://127.0.0.1:8765/ws"))
	var no_scheme := u.trim_prefix("ws://").trim_prefix("wss://")
	var host_port := no_scheme.split("/")[0]
	var parts := host_port.split(":")
	if parts.size() >= 2 and parts[1].is_valid_int():
		return int(parts[1])
	return 8765


func _repo_root() -> String:
	# res:// = godot/ 目录; 仓库根 = 其上一级
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()


## 候选解释器, 按优先级:
##   显式指定 → 仓库 .venv(依赖装在这里) → 本机真实安装 → PATH 的 python / py。
func _candidates() -> Array:
	var out: Array = []
	var explicit := OS.get_environment("CITYSIM_PYTHON").strip_edges()
	if explicit == "":
		explicit = str(Settings.get_value("backend", "python", ""))
	if explicit != "":
		out.append({"exe": explicit, "pre": PackedStringArray()})
	var venv := _venv_python()
	if venv != "":
		out.append({"exe": venv, "pre": PackedStringArray()})
	for p in _discover_windows_pythons():
		out.append({"exe": p, "pre": PackedStringArray()})
	out.append({"exe": "python", "pre": PackedStringArray()})
	out.append({"exe": "py", "pre": PackedStringArray(["-3"])})
	return out


## 仓库自带虚拟环境解释器(Windows Scripts/ 或 Unix bin/); 不存在返回 ""。
func _venv_python() -> String:
	var root := _repo_root()
	var win := root.path_join(".venv").path_join("Scripts").path_join("python.exe")
	if FileAccess.file_exists(win):
		return win
	var unix := root.path_join(".venv").path_join("bin").path_join("python")
	if FileAccess.file_exists(unix):
		return unix
	return ""


## Windows: %LOCALAPPDATA%\Programs\Python\Python3*\python.exe(新→旧)。
func _discover_windows_pythons() -> PackedStringArray:
	var found := PackedStringArray()
	var base := OS.get_environment("LOCALAPPDATA")
	if base == "":
		return found
	var dir := base.path_join("Programs").path_join("Python")
	if not DirAccess.dir_exists_absolute(dir):
		return found
	for sub in DirAccess.get_directories_at(dir):
		if not sub.begins_with("Python3"):
			continue
		var exe := dir.path_join(sub).path_join("python.exe")
		if FileAccess.file_exists(exe):
			found.append(exe)
	found.sort()
	found.reverse()
	return found


func _spawn(port: int) -> void:
	var root := _repo_root()
	OS.set_environment("PYTHONPATH", root.path_join("src"))
	var open_console := OS.get_environment("CITYSIM_BACKEND_CONSOLE") != "0"
	if OS.get_environment("CITYSIM_BACKEND_CONSOLE") == "":
		open_console = bool(Settings.get_value("backend", "console", true))
	var tried: Array = []
	for cand in _candidates() as Array:
		var exe: String = cand["exe"]
		var args := PackedStringArray(cand["pre"])
		args.append_array(PackedStringArray(["-m", "uvicorn",
			"citysim.gateway.server:app", "--port", str(port)]))
		tried.append(exe)
		var pid := OS.create_process(exe, args, open_console)
		if pid <= 0:
			continue
		# 拉起 ≠ 成功(可能是 Store 占位符 / 缺依赖): 等端口就绪再判定。
		if await _port_open("127.0.0.1", port, READY_TIMEOUT_MS):
			_pid = pid
			_spawned = true
			print("[Backend] started via '%s' (pid=%d): ws://127.0.0.1:%d/ws"
				% [exe, pid, port])
			return
		OS.kill(pid)
		push_warning("[Backend] '%s' 拉起后端口 %d 未就绪, 尝试下一个解释器" % [exe, port])
	push_warning("[Backend] 自动启动失败(已尝试: %s)。请确认已安装 viz 依赖 "
		% ", ".join(tried)
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
