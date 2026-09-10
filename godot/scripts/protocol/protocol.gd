# protocol.gd —— 与前端 protocol/schemas.ts 对齐的只读镜像 + 消息解析。
#
# 纯工具层: 不持有状态、不碰场景。对应 docs/observation_contract.md。
class_name Protocol
extends RefCounted

const PROTOCOL_VERSION := 1

## 档位 -> 真实 ticks/秒(与后端 server.SPEED_TPS 一致, 供 UI 外推)。
const SPEED_TPS := {"pause": 0, "1x": 1, "10x": 10, "100x": 100, "1000x": 1000}

## 观察器渲染的事件类型全集(contract 明确支持)。
const EVENT_TYPES := [
	"decision", "perceived", "bought",
	"interaction_done", "intent_failed", "stock_changed", "npc_died",
]


## 解析一条原始 WS 文本为 envelope {kind, protocol_version, payload}; 失败返回 null。
## 镜像 websocket.ts::parseMessage(含极老格式兼容: 顶层 type 推导 kind)。
static func parse_message(raw: String) -> Variant:
	var obj: Variant = JSON.parse_string(raw)
	if typeof(obj) != TYPE_DICTIONARY:
		return null
	var d := obj as Dictionary
	var kind: Variant = d.get("kind", null)
	if typeof(kind) != TYPE_STRING:
		var legacy: Variant = d.get("type", null)
		if typeof(legacy) != TYPE_STRING:
			return null
		return {"kind": legacy, "protocol_version": -1, "payload": d}
	var pv: Variant = d.get("protocol_version", -1)
	if typeof(pv) != TYPE_FLOAT and typeof(pv) != TYPE_INT:
		pv = -1
	var payload: Variant = d.get("payload", d)
	return {"kind": kind, "protocol_version": pv, "payload": payload}


# ---------------------------------------------------------------------------
# 宽容取值(后端 optional 字段缺失不崩溃)
# ---------------------------------------------------------------------------
static func as_dict(v: Variant) -> Dictionary:
	return v if typeof(v) == TYPE_DICTIONARY else {}


static func as_array(v: Variant) -> Array:
	return v if typeof(v) == TYPE_ARRAY else []


static func num(v: Variant, def: float = 0.0) -> float:
	match typeof(v):
		TYPE_FLOAT, TYPE_INT:
			return float(v)
		TYPE_BOOL:
			return 1.0 if v else 0.0
		TYPE_STRING:
			return float(v) if v.is_valid_float() else def
		_:
			return def


static func s(v: Variant, def: String = "") -> String:
	return str(v) if v != null else def


static func b(v: Variant, def: bool = false) -> bool:
	return v if typeof(v) == TYPE_BOOL else def
