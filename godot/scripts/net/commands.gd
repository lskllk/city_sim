# commands.gd —— 向 backend 发控制/查询命令的单例入口(autoload 名 `Commands`)。
#
# 镜像前端 protocol/commands.ts: Main 启动时注入 sender, UI 通过 cmd() 发命令,
# 不直接依赖 WS 客户端, 便于替换/测试。
extends Node

var _sender: Callable = Callable()


func set_sender(fn: Callable) -> void:
	_sender = fn


func send(obj: Variant) -> bool:
	if not _sender.is_valid():
		return false
	_sender.call(obj)
	return true


func cmd(name: String, args: Dictionary = {}) -> bool:
	return send({"name": name, "args": args, "req_id": 0})
