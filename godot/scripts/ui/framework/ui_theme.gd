# ui_theme.gd —— UI 设计 token(唯一来源)。
#
# 铁律: 颜色/字号/间距/圆角只在这里定义, 组件不再各自写死字面量。
# 这样"换皮/统一观感"只改一处, 也避免同类控件在不同页面长得不一样。
class_name UiTheme
extends RefCounted

# --- 颜色 -----------------------------------------------------------------
const BG := Color("06080c")          # 世界/最底
const CARD := Color("0c1018")        # 卡片/面板
const BORDER := Color("232c3a")
const TEXT := Color("c7d2e2")
const TEXT_DIM := Color("7a8494")
const TEXT_TITLE := Color("f0f4fb")
const ACCENT := Color("6fb7ff")
const OK := Color("3ddc84")
const WARN := Color("e8a34d")
const BAD := Color("e05252")
const ROW_HOVER := Color("1a2230")     # 列表行悬浮
const ROW_PRESSED := Color("223047")   # 列表行按下

# --- 字号 -----------------------------------------------------------------
const FS_TITLE := 16
const FS_HEAD := 11
const FS_BODY := 12
const FS_SMALL := 11

# --- 尺寸 -----------------------------------------------------------------
const SEP := 10                      # 区段间距
const ROW_SEP := 10                  # 行内列间距
const ROW_H := 26                    # 可点行高
const RADIUS := 4
