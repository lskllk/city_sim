# commands.gd —— 向 backend 发控制/查询命令的单例入口(autoload 名 `Commands`)。
#
# 镜像前端 protocol/commands.ts: Main 启动时注入 sender, UI 通过 cmd() 发命令,
# 不直接依赖 WS 客户端, 便于替换/测试。
extends Node

var _sender: Callable = Callable()

## 后端对每条命令的应答(ok / why)。以前被直接丢掉 → 点了没反应时无从判断。
## 面板把它显示成一行状态; reply_seq 变了说明来了新应答(页面据此决定要不要刷)。
var last_reply: Dictionary = {}
var reply_seq: int = 0
## 最近一条命令名。应答里不带命令名, 面板要靠它判断这条应答是不是自己的。
var last_cmd: String = ""


func note_reply(d: Dictionary) -> void:
	last_reply = d
	reply_seq += 1


func set_sender(fn: Callable) -> void:
	_sender = fn


func send(obj: Variant) -> bool:
	if not _sender.is_valid():
		return false
	_sender.call(obj)
	return true


func cmd(name: String, args: Dictionary = {}) -> bool:
	last_cmd = name
	return send({"name": name, "args": args, "req_id": 0})
