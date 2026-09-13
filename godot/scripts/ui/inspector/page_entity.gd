# page_entity.gd —— 物件详情页(常驻, 原地 bind): 属性表。
class_name InspEntityPage
extends UiPage

const KEYS := ["id", "类型", "地点", "库存", "价格", "归属", "使用者",
	"交互时长", "标签", "信号效果"]

var _header: Control
var _kv: Dictionary = {}
var _eff_rows: Dictionary = {}     # "on_start"/"on_complete" -> Control(整行)


func build() -> void:
	_header = UiKit.header(self)
	var body: VBoxContainer = UiKit.section(self, "属性").body()
	for k in KEYS:
		_kv[k] = UiKit.kv(body, k)
	for eff in ["on_start", "on_complete"]:
		_kv[eff] = UiKit.kv(body, eff)
		_eff_rows[eff] = _kv[eff].get_parent()
		_eff_rows[eff].visible = false


func bind(id: String) -> void:
	var e := Store.entity(id)
	if e.is_empty():
		return
	_header.set_header(Protocol.s(e.get("name", id)),
		"%s · %s" % [InspData.item_name(e, id),
			Store.name_of(Protocol.s(e.get("loc", "")))])

	_kv["id"].text = id
	_kv["类型"].text = "%s（%s）" % [Protocol.s(e.get("item_type", "—")),
		InspData.item_name(e, id)]
	_kv["地点"].text = Store.name_of(Protocol.s(e.get("loc", "")))
	_kv["库存"].text = InspData.qty_txt(e)
	_kv["价格"].text = InspData.price_txt(e)
	var owner := Protocol.s(e.get("owner", ""))
	_kv["归属"].text = Store.name_of(owner) if owner != "" else "公共"
	_kv["使用者"].text = InspData.user_text(e)
	_kv["交互时长"].text = "%d tick" % int(Protocol.num(e.get("duration_ticks")))
	var tags := Protocol.as_array(e.get("tags", []))
	_kv["标签"].text = " / ".join(tags) if not tags.is_empty() else "—"
	var aff := Protocol.as_dict(e.get("affordances", {}))
	if aff.is_empty():
		_kv["信号效果"].text = "—"
	else:
		var parts := PackedStringArray()
		for ek in aff:
			parts.append("%s %+.2f" % [Zh.signal_zh(str(ek)), Protocol.num(aff[ek])])
		_kv["信号效果"].text = "，".join(parts)
	for eff in ["on_start", "on_complete"]:
		var effs := Protocol.as_array(e.get(eff, []))
		_eff_rows[eff].visible = not effs.is_empty()
		if not effs.is_empty():
			_kv[eff].text = str(effs)
