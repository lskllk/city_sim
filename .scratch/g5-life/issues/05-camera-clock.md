# 05 — 摄像机与时钟稳定

**What to build:** 消除"每帧缩放的跳变"与"时间阶跃"。view 固定、tickNow 用真实 tps、信号条线性插值。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] view 只在 hello/reset/resize 按全部房间 bbox 算一次, draw 不再改 view
- [ ] `tickNow = lastTick + (now-recv)/1000*tps`(服务端 tps), 不再反推
- [ ] 信号条按 tickNow 在两次快照间线性插值平滑走
