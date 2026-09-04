# M5 测试进度（testm5.MD 执行状态）

## 2026-09-04 · 全条款执行完毕 → 结果见 docs/testM5result.md（全量 96 passed）

### 本轮补齐
- sim 补接线(均 kb!=None 才生效, M4 平价保持): 每日 decay(half_life=7天) +
  感知学 located_at + 感知修正「空 vs 占用」→ 修掉误证伪(DOT 佐证)
- 场景测试 test_m5_full.py(S1-S5 7条绿):
  S1 firstB1468>>A53/idle378≥2×30/day3-7收敛10vs10
  S2 每NPC恰1次扑空→4/4 refute→改道 eats13×4; off对照 eats0
  S3 p=0.1 knowers10/10 每跳≤0.8(0.5/0.4/0.32) 溯源10/10; p=0 恒1
  S4 假消息 6/6信→亲赴refute→归零 wasted6
  S5 主循环21天 conf=0.125000±0.02; INJECTED恒1.0
- 宏观 test_m5_macro.py(kb_metrics, 7天×6NPC): trace100% jaccard0.6
  overlay 2→2 峰值2≤12 全员吃到 空跑0 —— 已冻结
- 消融 test_m5_ablation.py(seed1-10×3档): off 0/40吃 stuck199k vs KB档40/40
  stuck0; full diversity .333 唯一>0; 无倒挂 —— 已冻结
- review 产物: narrate 3天文本 + 4场景log + KB DOT(2人×d1/4/7) +
  behavior_debt §4(3意外/3呆/2局限)

### 未达/待 M6(同根因: 无回家/日循环/换店 → behavior_debt 4b/4c/4d)
- 探索率 0.24%<5-30%; 熟悉偏好; S3 S曲线; 知识源按字母序(brain);
  S2 文档版跨天通勤; golden 升级 M5 版(M6 起点做)

