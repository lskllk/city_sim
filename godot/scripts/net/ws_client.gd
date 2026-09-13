# ws_client.gd —— WebSocket 客户端(autoload 名 `Net`)。
#
# 只管通信: connect / reconnect(backoff) / send / parse。
# 不修改任何 Store; 消息以 envelope 交给 Main 的 dispatch。
# 镜像前端 protocol/websocket.ts。
extends Node

signal message_received(envelope: Variant)
signal status_changed(status: String)

const BASE_BACKOFF := 0.5
const MAX_BACKOFF := 8.0

## 后端 WS 端点。可用环境变量 CITYSIM_WS_URL 覆盖。
var url := "ws://127.0.0.1:8765/ws"

var _peer: WebSocketPeer = null
var _started := false
var _closed := false
var _status := "closed"
var _attempt := 0
var _reconnect_in := -1.0


func _ready() -> void:
	# 不自动连接: 由 App 调用 start(), 保证 wiring 先就绪。
	pass


## 从 Settings(network/ws_url)读取端点; 环境变量 CITYSIM_WS_URL 仍最高优先。
func configure_from_settings() -> void:
	var env_url := OS.get_environment("CITYSIM_WS_URL").strip_edges()
	if env_url != "":
		url = env_url
	else:
		url = str(Settings.get_value("network", "ws_url", "ws://127.0.0.1:8765/ws"))

func start() -> void:
	if _started:
		return
	_started = true
	_open()


func status() -> String:
	return _status


func _process(delta: float) -> void:
	if not _started:
		return
	if _peer != null:
		_peer.poll()
		var state := _peer.get_ready_state()
		match state:
			WebSocketPeer.STATE_OPEN:
				if _status != "open":
					_attempt = 0
					_set_status("open")
				while _peer.get_available_packet_count() > 0:
					var pkt := _peer.get_packet()
					var msg: Variant = Protocol.parse_message(pkt.get_string_from_utf8())
					if msg != null:
						message_received.emit(msg)
			WebSocketPeer.STATE_CLOSED:
				_peer = null
				_set_status("closed")
				_schedule_reconnect()
			_:
				pass  # CONNECTING / CLOSING: 继续轮询
	elif _reconnect_in >= 0.0:
		_reconnect_in -= delta
		if _reconnect_in <= 0.0:
			_reconnect_in = -1.0
			_open()


func send(obj: Variant) -> bool:
	if _peer == null:
		return false
	if _peer.get_ready_state() != WebSocketPeer.STATE_OPEN:
		return false
	return _peer.send_text(JSON.stringify(obj)) == OK


func close() -> void:
	_closed = true
	_started = false
	if _peer != null:
		_peer.close()
		_peer = null
	_set_status("closed")


func _open() -> void:
	if _closed:
		return
	_peer = WebSocketPeer.new()
	var err := _peer.connect_to_url(url)
	_set_status("connecting")
	if err != OK:
		# 立即失败也要走重连节奏
		_peer = null
		_schedule_reconnect()


func _schedule_reconnect() -> void:
	if _closed or _reconnect_in >= 0.0:
		return
	_reconnect_in = min(BASE_BACKOFF * pow(2.0, float(_attempt)), MAX_BACKOFF)
	_attempt += 1


func _set_status(s: String) -> void:
	if _status == s:
		return
	_status = s
	status_changed.emit(s)
