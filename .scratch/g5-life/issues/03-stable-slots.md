# 03 — 稳定槽位 + 迁移缓动

**What to build:** NPC 在房间内不因他人进出而"洗牌瞬移"——每人确定性槽号；切房间旧→新位置 400ms 缓动。

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] `slot(npc_id) = hash%SLOTS`(冲突线性探测), 与同屋人数无关
- [ ] 换房间时旧位置→新位置 400ms 缓动, 无瞬移
- [ ] gossip/演示场景肉眼无"集体跳位"
