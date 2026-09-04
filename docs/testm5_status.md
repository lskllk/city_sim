# M5 测试进度（testm5.MD 执行状态, 2026-09-04）

## 已完成（机器可固化部分）
- 基础设施:
  - `tools/demo_scene.py::build_demo` 增 `kb_mode(off/archetype_only/full)` + `noise`
    (初始信号扰动 rng.uniform(-n,n), 破同相位); off 与 M4 golden 逐行一致(已验证)
  - `tools/narrate.py` 叙事日志(供人工 review)
  - 传闻引擎: `sim/loop.py::_rumor_pass`(tell_p 可关, 默认 0; 同地 idle 双 kb 分享
    overlay 最高置信事实, 接收 learn TOLD conf*0.8, 发 told 事件)
- 场景测试 `tests/test_m5_scenarios.py`(5 条绿):
  - S3-lite 传闻机制: 能传播、每跳 conf≤0.8、溯源回唯一 OBSERVED 根; tell_p=0 无传播
  - S5 遗忘: OBSERVED 3 半衰期后 conf≈0.125±0.02 且不再被 decide 引用;
    INJECTED 不衰减
  - S6 稀缺+知识=生存差: 有知识 2 人 market 吃到(stuck0 hunger<300), 无知 2 人
    饿(stuck0>1000)
- 全套 pytest 87 passed; soak(睡0.86/天 实体11->11) 与 golden(264 行) 零回归

## 未完成（需要继续, 依序）
- S1 新来者 vs 老住户(知识不对称/收敛曲线) —— 需场景剧本 + 阈值校准
- S2 过时知识纠错(4 NPC, day2 强清空, wasted_trips 按天, off 对照) —— 部分已由
  test_knowledge::test_stale_knowledge 覆盖单 NPC 版, 待扩 4 NPC + 传闻加速
- S4 假消息的生与死(注入假事实→传播→亲赴 refute→归零, wasted 有界) —— 机制已具备
- 宏观指标进 soak(探索率/空跑率/熟悉偏好/知识多样性/追溯完整性/KB 增长有界+断言)
- 消融矩阵(off/archetype_only/full × seed 1-10, 贴 PR)
- 人工 review 流程(narrate 3 天逐条、KB DOT 渲染、3 意外+3 呆行为记 debt)

## 阈值提醒
testm5 的 5-30%/≥60%/等为首次校准值, 固化前按实际分布调一次并冻结
(同 3b 记档: 回归网而非人性证明; 人性由 narrate/DOT 肉眼判断)。
