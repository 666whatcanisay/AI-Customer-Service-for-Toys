# RC5 Current Running Instance Protection Report

## 结论

最终界面验收前后的受保护状态对比为 **PASS**。本轮没有打开 PDD 登录页、读取真实 PDD 页面或发送真实消息。

> 离线治理收口补充：当前安装实例已用最终候选包完成事务式覆盖升级。升级前后 Agent ID、Device ID、Binding revision、Active Store、受保护文件、Profile identity、PDD Session 均未变化；候选包与已安装 Manifest/EXE/PYZ 一致，保护检查 11/11 PASS。Agent PID 因受控重启发生预期变化，不属于身份漂移。

| 保护项 | 验收前 | 验收后 | 结果 |
|---|---|---|---|
| Agent PID | `13308` | `13308`，存活 | PASS |
| Agent Identity | 同一 ID，ACTIVE | 同一 ID，ACTIVE | PASS |
| Device Binding | 同一 Device；revision 2 | 同一 Device；revision 2 | PASS |
| Active Store | 同一 store | 同一 store | PASS |
| 保护配置文件 SHA | 基线值 | 完全一致 | PASS |
| Edge Profile reference | 基线值 | 完全一致 | PASS |
| Profile identity SHA | 基线值 | 完全一致 | PASS |
| PDD Session 文件数 | `1` | `1` | PASS |
| PDD 读取浏览器 | disabled / 无 PID | disabled / 无 PID | PASS |
| Real Send | `false` | `false` | PASS |

运行状态为 `ONLINE / OBSERVING / ASSISTANT_READY`。状态文件中的 `observer_last_error_code` / `last_error_code` 表示最近一次历史错误，不代表当前仍离线；日志显示最近一次短暂连接错误随后出现 `CHANNEL_ENGINE_CONNECTION_RECOVERED`，后续最终 UI 和后端闭环均通过。

原始快照：

- `.runtime/rc5-final/final-state-20260812.json`
- `.runtime/rc5-final/final-state-20260812-post-ui.json`
- `.runtime/rc5-offline-stability/pre-transactional-upgrade.json`
- `.runtime/rc5-offline-stability/post-transactional-upgrade.json`

快照工具为只读：不启动/停止服务、不打开浏览器、不读取 PDD 页面、不修改数据库。
