# 08 — 护栏测试补全(event_objs 纯净)

**What to build:** 协议改造后确认网关仍是只读观察者：读 event_objs/drain 不消耗额外事件序号、日志与 headless 逐行相同。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 既有 test_gateway_readonly 在 event_objs 改造后仍绿
- [ ] 补断言: drain_log 后 bus.seq 不变、log_lines 不变
- [ ] 全量 pytest 绿
