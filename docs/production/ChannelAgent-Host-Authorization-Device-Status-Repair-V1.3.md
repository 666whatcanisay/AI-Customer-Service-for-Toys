# ChannelAgent 主机授权与设备状态修复 V1.3 完成报告

## 结论

本次代码实施完成。正式设备管理链固定为：

```text
18020 运营控制台
→ AI-CS 管理员 RBAC
→ AI-CS 服务身份签名
→ 18443 V2 Host Control
→ 权威设备状态
```

18020 不再拥有可写设备 Repository；18443 不可用、管理员未登录或签名失败时，设备查询和管理操作均 Fail Closed。

## 状态模型

设备后台独立保存：

- `identity_status`：`REGISTERED | BOUND | ACTIVE | DISABLED`
- `connectivity_status`：`ONLINE | OFFLINE`

连接中断只改变 `connectivity_status`。例如 `ACTIVE + OFFLINE` 表示设备仍然有效且已启用，只是当前没有心跳。旧 `UNBOUND` 只作为输入兼容，并统一迁移为 `REGISTERED`；V2 不返回 `UNBOUND`。

运营界面仅组合展示状态文案，不持久化组合状态，也不使用组合文案参与权限判断。

## 管理操作

- 禁用：保留 `DISABLED` 身份、审计、历史心跳和 Receipt。
- 恢复：仅允许 `DISABLED → REGISTERED`。
- 恢复确认短语：`确认恢复为待绑定`。
- 恢复后清空旧客服、授权店铺和当前店铺，必须重新完成人工绑定。
- OFFLINE 不触发身份降级；心跳恢复只变更连接状态。

## 运营控制台

18020 新增进程内管理员会话：

- 使用 AI-CS 账号完成管理员 RBAC 校验。
- HttpOnly、SameSite Strict Cookie 仅保存随机本地会话编号。
- AI-CS Access Token 仅存在 18020 进程内存，不落盘。
- 设备页显示权威来源、身份状态、连接状态和最后心跳。
- 未登录时引导管理员登录；18443 不可用时禁止写操作。

## 正式主机启动

Windows 启动器现在按下列顺序执行：

1. 配置 Windows Credential 引用与 CA 证书。
2. 启动 AI-CS。
3. 启动 18443 Host Control。
4. 使用 AI-CS 服务身份签名查询 V2 设备接口。
5. 仅在签名查询通过后启动 18020 正式运营控制台。
6. 写入 Host、Discovery 和 Operations 三个受管进程状态。

检测到旧版 `channel_engine.app:app` 占用 18020 时，启动器只会停止这个已识别的旧开发进程；其他未知进程占用端口时停止并提示，不会误杀。

## 测试结果

- Channel Engine 全量：`678 passed, 1 skipped, 0 failed`
- AI-CS 平台后端全量：`163 passed, 0 failed`
- AI-CS 前端：`43 test files, 195 tests passed`
- TypeScript 类型检查：通过
- Python compileall：通过
- PowerShell 启动、停止、状态脚本语法：通过
- 生产架构检查：V1 未挂载、UNKNOWN Receipt、安全锁、Gateway SHA 均通过

## 当前安全状态

保持：

```text
manual_approval_required=true
auto_reply_enabled=false
real_send_enabled=false
real_platform_activation_allowed=false
```

本次没有登录 PDD，没有关闭 Edge，没有修改 Profile/Session，也没有触发真实发送。

## 部署说明

代码和一键启动链已准备完成。当前终端不是管理员会话，因此未替用户执行需要 Windows 防火墙和凭据权限的正式切换。正式启用时应以管理员身份运行“启动局域网AI客服主机”，验证 18443 签名链后再打开 18020 设备管理页。

真实 PDD 激活仍因缺少生产 Selector Evidence 保持 `BLOCKED`；该阻断与本次设备状态修复相互独立。
