<!-- edge-walker-managed-skill:v2 -->
# 接近提醒

本 Skill 消费角色 A 已完成的端侧安全判决，不用 LLM 估算距离、TTC 或修改等级。

## 何时使用

- 雷达本地判决、人工告警和合成目标需要追踪或说明时。
- NONE 是解除事件，也必须保留追踪记录。

## 边界与调用

1. 常驻 ew_safety 独立读取雷达、运行 ew_decide/ew_hold，并直接维护蜂鸣安全下限；切换 WARN/CHAT/WIFI 或断网不会关闭该任务。
2. 本地主程序用 ew_agent_emit_decision 接收完整 ew_decision_t。source 是本地追踪信封：radar/fake/manual/serial/agent；event_id 是本次运行内非零数字，原 reason 不为空时保留。
3. 本地 C Tool 调用不等于真实 packages/ai_agent registry 调用。独立 ai_agent 的 approach_alert Tool 由构建脚本注册，用 EWA1 IPC 交给主应用消费。
4. 独立 Tool 参数只允许 level、reason、event_id。不得使用字符串 evt-* ID，也不得将本地 source 塞入此 JSON schema。

```json
{"level":"strong","reason":"strong_range_or_ttc","event_id":1001}
```

level 支持 none/soft/strong/emergency 或整数 0–3。reason 的 UTF-8 编码须少于 96 字节。

## 成功与失败

- 独立 Tool 的 queued 只证明请求发布；busy/invalid_input/queue_failed 都是失败。
- 消费回调完成后写带 ID 的 applied/rejected ACK。applied 不能代替声波、屏幕像素或道路实测。
- ACK 瞬态失败只补写结果，不重放执行器；未知锁或未落盘结果保持关闭，不能声称任意断电后 exactly-once。
- 人工或 Agent 请求不得降低当前雷达安全等级。人工告警是持久测试模式，需在允许时用 level=none 显式解除。
- 本地雷达事件通知是有界遥测队列；UI 阻塞时可能被标为 superseded 或丢弃并计数，不能宣称所有事件都经过独立 registry。

## 无板示例与实板验收

`ew fake 10 20` 产生 STRONG；`ew fake 10 2` 低于最低速度，产生 NONE。PC 对应用 `@fake 10 20`。

主机测试和合成回放验证代码行为，不证明雷达方向标定、实际声音、屏幕响应或道路误报/漏报。完整板端链路仍需逐事件记录、真实观测及三次连续演示。
