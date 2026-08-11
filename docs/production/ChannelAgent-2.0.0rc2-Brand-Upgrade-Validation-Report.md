# 《ChannelAgent 2.0.0rc2 Brand Upgrade Validation Report》

## 1. 结论

本次品牌资源白名单原位升级已完成，结果为 `UPGRADE_PASSED`。

- 客户端资源版本：`2.0.0rc2`
- Agent Runtime 核心版本：保持 `2.0.0rc1`
- Agent Control 协议：保持 `2.1`
- Gateway Contract：未修改
- 设备身份：保持 `ACTIVE`
- 回滚：未触发

本次没有整包覆盖，没有调用普通安装脚本或 Agent `stop` 命令。只短暂重启了托盘进程，Python Agent Runtime、配置、设备身份、游标、缓存和浏览器 Profile 均未重新初始化。

## 2. 使用的正式品牌包

- 包：`AI-CS-Channel-Agent-2.0.0rc2-windows-x64.zip`
- 最终 SHA256：`50b52f3bcbd13400c7cad000746b72bf1879d50e56c5d8d4307c4204cdc14066`
- 品牌状态：`official`
- Brand Asset Gate：通过
- EXE File Version：`2.0.0.2`
- EXE Product Version：`2.0.0rc2`
- 已安装 EXE SHA256：`324300e67d5a716cc4cdd4607f0d946c3e01e7751e763bd3be9d8c73f3564c49`

审计阶段记录的旧包 SHA `38d68f10c96b61eefc485c8e5a402e5f59855fe74b1ca747f356292bf952f38a` 未直接安装。为满足 RC2 PE 版本信息和品牌专用升级器要求，重新生成了正式包；最终安装文件已与上述最终包逐文件核对一致。

## 3. 升级前后状态

| 验证项 | 升级前 | 升级后 | 结果 |
|---|---|---|---|
| Agent Runtime PID | `21720` | `21720` | 保持 |
| 托盘 PID | `6376` | `12236` | 仅托盘重启 |
| Agent ID | `agent-a8c230a7f58d4e7ea312153c3f29fa32` | 相同 | 保持 |
| Device ID | `device-2254aa0b078f42b3a0a1f85e7dff96a9` | 相同 | 保持 |
| 身份状态 | `ACTIVE` | `ACTIVE` | 保持 |
| Binding Revision | `2` | `2` | 保持 |
| 授权店铺 | `c-store-6639df2982014226`, `PDD-SM` | 相同 | 保持 |
| 当前店铺 | 未选择 | 未选择 | 保持 |
| Browser Profile 引用 | `browser/profiles/agent-a8c230a7f58d4e7ea312153c3f29fa32-b467ed9eae5a/edge` | 相同 | 保持 |
| PDD 登录状态 | `LOGIN_FAILED` | `LOGIN_FAILED` | 原样保持，未尝试登录 |
| Desktop Assistant | `RUNNING` | `RUNNING` | 正常 |

## 4. 受保护文件 Hash

| 文件 | 升级前 SHA256 | 升级后 SHA256 | 结果 |
|---|---|---|---|
| `%LOCALAPPDATA%/AI-CS/ChannelAgent/config/agent.json` | `8dcd84d63d13e1e393e40b7f6aa454539ee52c179edbceb893e284d086f18eac` | 相同 | 未修改 |
| `app/channel-agent.pyz` | `a2f5f89f3656eeab2ad46deea39805de8d067e8978f5ee6f80e0f3839d75a31a` | 相同 | 未修改 |

数据目录、游标、缓存、Identity、浏览器 Profile 和 PDD Session 均未删除或清理。当前没有正在运行的受管 PDD Edge 会话，升级未尝试修复或重新登录。

## 5. 品牌资源验证

- `ChannelAgent.exe` 已嵌入 RC2 Windows PE 图标和版本信息。
- 基础 `.ico` 与正常、提醒、故障、离线四套托盘图标 Hash 全部通过。
- `ui/channel-agent-avatar.png` 已安装。
- 现有 `ui/index.html` 仅注入头像 favicon，原 JS/CSS 引用未替换。
- 本地头像资源 HTTP 返回 `200`。
- 客服助手页面 HTTP 返回 `200`。
- 已创建桌面快捷方式 `AI-CS 客服助手.lnk`，目标和 `IconLocation` 均指向当前 `ChannelAgent.exe`。
- 安装目录品牌白名单文件与最终正式包逐文件一致。

## 6. 测试结果

### 已通过

- Brand Asset Gate：通过。
- 最终包 ValidateOnly：通过。
- PowerShell 升级脚本语法检查：通过。
- 品牌资源与 Desktop Assistant 专项：`12 passed`。
- 实际白名单升级：`UPGRADE_PASSED`。
- Runtime PID、身份、配置和 pyz Hash 保持验证：通过。
- 单托盘进程验证：通过。
- Desktop Assistant 页面及头像资源连通性：通过。

### 既存非品牌风险

一次包含旧 Windows Runtime 测试的并行回归出现临时文件 `PermissionError`，结果为 `20 passed, 2 failed`；随后该旧生命周期测试存在一次悬挂。故障位于 pytest 临时目录的状态文件共享锁，不涉及正式数据目录，也不是本次品牌文件替换造成。

根据“只升级品牌、不修改业务逻辑”的边界，本次未修改 Windows 状态存储实现。品牌发布 Gate 和实际运行验收已通过；该测试稳定性问题应作为独立 Runtime 维护项处理，不阻止本次品牌资源原位升级结论。

## 7. 回滚验证

- 升级过程未触发自动回滚。
- 升级器已为 EXE、favicon、品牌资源、快捷方式和品牌 Manifest 建立备份及回滚路径。
- 回滚逻辑不会调用 Agent `stop`，不会清理身份、Profile 或 PDD Session。
- 若后续品牌 Hash 异常，只回滚品牌白名单资源，不影响核心业务 Gate。

## 8. 最终状态

`CHANNEL_AGENT_2_0_0RC2_BRAND_UPGRADE_VALIDATED`

注意：该状态只表示客户端品牌资源升级完成。Agent Runtime 核心仍为 `2.0.0rc1`，不代表业务核心已升级至 RC2。
