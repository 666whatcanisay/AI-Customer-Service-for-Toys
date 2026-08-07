# 《AI-CS Customer PC Deployment Preparation V1》

- Requirement：`R030`
- Date：`2026-08-07`
- Gate：`PASS / AI_CS_CUSTOMER_PC_DEPLOYMENT_READY`
- Deployment class：`LOCAL_CONTROLLED_DEPLOYMENT`
- PDD：`NOT_CONNECTED`

## 1. Runtime基线

### AI-CS

- 仓库分支：`codex/ai-cs-user-experience-acceptance-final-v1`。
- 本轮业务源码核对锚点：`7c4651b307af8468066dd095f6632a2eed6ba0b4`；最终文档提交后以`git rev-parse HEAD`为唯一Runtime源码指纹，并要求工作树clean。
- A/B/C/Admin四服务使用R027受管配置，以`standard / LOCAL`模式运行；最终提交后重新执行stop/start/status和四服务Runtime SHA一致性检查。
- 数据库：Git忽略的R027隔离SQLite，revision `0016_production_hardening_v1`，完整性`ok`。
- RAG：`test_knowledge_v031`，维度512，70 embeddings，完整性`ok`。

### Channel Engine与Agent

- Agent/Windows Client 1.1.1候选提交：`0a5a041e72bb9daec9813d5d4b7f7907eb8ce86f`。
- 生产服务身份提交：`5c105dbe855c09dfe31c9d2bbf5d18caec40b32b`；Engine工作树clean。
- Engine仅监听`127.0.0.1:18020`，使用独立SQLite Runtime；不暴露公网。
- AI-CS通过C的服务端facade读取Agent状态，浏览器不持有Engine operator identity。

## 2. Agent状态

- Client版本：`1.1.1`。
- Agent：`agent-desktop-0345200`。
- Device：`device-desktop-0345200`。
- 身份状态：`ACTIVE`；运行状态：`ONLINE`；生产资格：true；绑定revision：2。
- Heartbeat：Engine已接收，AI-CS管理视图可见；用户已人工确认Workspace显示设备在线。
- Windows当前用户自启动：已启用。
- 公共配置保护：`message_read_enabled=false`、`send_enabled=false`、`browser_automation_enabled=false`。

## 3. 安装结果

- 安装方式：从clean候选重建Windows ZIP，使用包内正式安装流程安装，不直接运行源码。
- 安装目录：`C:\Users\EDY\AppData\Local\Programs\AI-CS\ChannelAgent`。
- 运行数据/日志目录：`C:\Users\EDY\AppData\Local\AI-CS\ChannelAgent`，受Git忽略且未纳入报告内容。
- ZIP：`AI-CS-Channel-Agent-1.1.1-windows-x64.zip`，SHA-256 `FD2D37746030584DC5EF34EFB7001E752B71FD4C9EC04FD25DD82F8943CD6138`，22,130,400 bytes。
- EXE SHA-256：`92252395A70B7415A524934A5661CB95C25F2ADB7B1CF69AA38E575AF392DF33`，5,632 bytes。
- 包manifest：1,626个文件，安装后逐项匹配，0 failures。
- Authenticode：`NotSigned`。本次仅因用户明确批准而允许在本机隔离环境安装；不可把该批准扩展为生产分发签名豁免。

## 4. 身份绑定

- 客服在Workspace使用`ux_kefu`登录，人工生成一次性绑定码，并在本机可见终端手工输入；系统未代填、未读取、未输出或持久化该码。
- 独立管理员通过受控服务身份激活；匿名Desktop Agent API保持HTTP 401，错误服务身份保持HTTP 403。
- 服务身份使用Runtime外置受限文件，启动时读取后仅保留摘要并使用常量时间比较；报告不记录secret、摘要或Session。
- 首次生成过程检测到不兼容随机数API造成的失败候选；该候选在任何服务启动或使用前被原子轮换并删除临时文件，随后以兼容的CSPRNG重新生成并复核ACL。该事件无凭据泄露、无服务使用、无Git写入。

## 5. 店铺绑定与权限

- AI-CS用户：`ux_kefu`，状态ACTIVE，角色集合严格为`CUSTOMER_SERVICE`。
- AI-CS Store绑定：仅`PDD-SM`，共1条且为唯一默认店铺。
- Channel Agent绑定Store：仅`PDD-SM`；与AI-CS授权Store集合完全一致。
- 客服无运营权限；绑定与状态展示继续由C服务端执行Bearer、RBAC和Store scope校验，前端按钮不是授权边界。

## 6. 网络链路

```text
Windows Client 1.1.1
  -> 127.0.0.1:18020 Channel Engine控制面
  -> AI-CS C Platform facade
  -> Customer Workspace设备状态
```

- AI-CS与Engine均为本机loopback受控链路，无公网开放。
- Agent外部Session引用位于AI-CS受管Runtime秘密目录并限制ACL；AI-CS与Engine需协调轮换和重启。
- 本轮仅验证设备控制面、身份、Store绑定、Heartbeat和Workspace投影；未把Mock/控制面状态解释为PDD消息回执。

## 7. 人工操作点

- 已人工完成：以`ux_kefu`登录、在Workspace申请一次性绑定、在本机Agent终端输入绑定码、确认Workspace显示设备在线。
- 系统完成：候选/hash核对、安装manifest验证、Engine管理员激活、Heartbeat/权限/Store集合核对、日志与状态收口。
- 本轮未自动输入密码、未绕过授权、未自行模拟页面点击。

## 8. 测试结果

- Channel Engine focused auth/API：11 passed。
- Channel Engine全量：559 passed，1条第三方Starlette warning。
- Channel Engine contracts：123 passed，1条第三方warning。
- `pip check`与`compileall`：PASS。
- AI-CS C Desktop Agent安全/API专项：9 passed，1条第三方Starlette warning。
- AI-CS B Desktop Adapter/Workspace专项：2 files / 19 passed；typecheck与production build PASS（保留既有大chunk warning）。
- AI-CS Desktop Workflow Contract：3 passed。
- Agent包manifest：1,626/1,626 matched。
- 运行验收：Agent ACTIVE/ONLINE、Heartbeat present、AI-CS管理投影ONLINE、Workspace人工确认在线。
- 安全验收：匿名401、错误服务身份403、客服角色/默认Store/Engine Store三方一致、发送/消息读取/浏览器自动化保持关闭。

## 9. 回滚与剩余风险

- 回滚Agent：使用安装包卸载流程，移除当前用户自启动；保留必要的受限诊断材料后再按隐私策略清理Runtime数据。
- 回滚Engine连接：停止loopback Engine并关闭R027配置中的Channel Agent Integration；不修改数据库、RAG或Gateway Contract。
- 未签名EXE仍是生产分发阻断；正式客服电脑推广前必须进行企业代码签名和发布渠道验证。
- Engine当前以隐藏的source/uvicorn进程运行，尚未形成Windows服务或受管自启动；重启电脑后Agent可能在Engine启动前显示DEGRADED。下一阶段应提供受控Engine Runtime wrapper/service及恢复测试。
- PDD Adapter、Browser Control、Message Listener、Send Executor均未启用或验证；真实PDD接入仍需独立Gate、observe-only阶段、kill switch和人工批准。

## 10. Final Decision

本机客服电脑部署准备的核心标准全部满足：clean可追溯Client、正式安装流程、人工身份绑定、唯一授权Store、Agent ONLINE、服务端Heartbeat、Workspace设备在线和权限隔离均通过。

最终状态：`AI_CS_CUSTOMER_PC_DEPLOYMENT_READY`。

该状态仅表示“本机受控客服电脑部署准备Ready”，不表示PDD、消息监听、浏览器控制、真实发送或生产分发签名Ready。
