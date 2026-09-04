# 02 — 前端消费层修复（颜色查表 + 事件流/弧线 + 状态/详情拆分）

**What to build:** 事件不重不漏、told 弧线能画、知识面板有内容、中文名硬编码清出 JS、右面板不卡顿不闪。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 颜色按服务端 `act_class` 查表(删 JS 里 includes("床")等中文判断)
- [ ] 事件流/弧线/💬 从结构化 payload 读(audience 真数组)
- [ ] 右面板拆分: `npc_state`(信号+意图)1Hz 实时；`npc_detail`(含 KB/事件)只在切人或切页签时拉一次；kb 页签单次渲染
- [ ] 页面刷新无 JS error
