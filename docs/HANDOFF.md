# 项目详细交接

## 一句话说明

AI-CS 负责“知道怎么回答”，AI-CE 负责“可靠地读取、组织上下文并受控发送”。两个项目已经合并到同一 Git 仓库，但仍保持清晰的模块边界。

## 接手顺序

1. 阅读根目录 `README.md`。
2. 执行 `scripts/windows/Doctor-PortableProject.ps1`。
3. 首次使用执行 `首次安装.cmd`。
4. 阅读 `docs/CURRENT_STATE.md`，确认当前版本行为与限制。
5. AI-CS 开发从 `backend/`、`platform_backend/`、`frontend/`、`admin_web/` 开始。
6. PDD/渠道开发从 `AI-CS-Channel-Execution-Engine/` 开始。

## 重要入口

| 目标 | 入口 |
| --- | --- |
| 首次安装 | `首次安装.cmd` |
| 仅启动 AI-CS | `启动AI客服.cmd` |
| 启动 AI-CS + 当前页 PDD Agent | `启动完整客服含PDD.cmd` |
| 停止受管服务 | `停止全部服务.cmd` |
| AI-CS 状态 | `scripts/windows/status_ai_customer_service.ps1` |
| AI-CE 当前页运行 | `AI-CS-Channel-Execution-Engine/scripts/manage_current_page_auto_production.py` |
| AI-CE 总说明 | `AI-CS-Channel-Execution-Engine/README.md` |

## 代码所有权

- A：`backend/**`、`docs/rag/**`
- B：`frontend/**`、`docs/customer/**`
- C：`platform_backend/**`、`admin_web/**`、`docs/platform/**`
- CONTROL/OPS：`contracts/**`、`scripts/**`、`docs/control/**`
- AI-CE：`AI-CS-Channel-Execution-Engine/**`

修改共享 Observation、Gateway、Decision、Approval、ExecutionPrepared 或 Receipt 契约前，必须补版本、兼容说明和两侧测试。

## 当前生产设计要点

- 只处理当前打开会话，自动导航禁用。
- PDD 店铺名称不作为授权依据；使用 PDD platform Store ID + AI-CS Store ID。
- 自动回复开关只决定是否允许逐消息签发 Grant。
- 每条新客户消息必须独立绑定 message、Decision、reply hash、Evidence hash、Store、conversation 和 customer。
- Sender 只有一条路径；TTL、nonce、单次尝试、单次成功和防重放保持启用。
- 结果 UNKNOWN 不重试；目标或页面无法唯一确认时停止。

## 数据库与知识

- 源码 Alembic 目标为 `0023_reply_readiness_v1`。
- 新电脑由 Bootstrap 创建空的、已绑定身份的本地数据库。
- 生产数据库升级必须先备份、核对实际 Schema，再迁移和绑定；不能只 stamp 版本号。
- 商品、SKU、FAQ、安全规则需要经 Admin 审核发布。
- 生产知识、向量和原始对话不进入 Git。

## 测试最小集合

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
platform_backend\.venv\Scripts\python.exe -m pytest platform_backend\tests

cd frontend
npm test
npm run typecheck
npm run build

cd ..\admin_web
pnpm test
pnpm typecheck
pnpm build

cd ..\AI-CS-Channel-Execution-Engine
.venv\Scripts\python.exe -m pytest
```

改动当前页 PDD 链路后至少增加：当前会话读取、商品识别、Operator 消息回显、去重、输入框暂停、UNKNOWN 不重试与禁止自动导航测试。

## Git 与发布

- 正式候选必须双模块测试通过、工作区 clean。
- GitHub 只保存源码与脱敏展示素材。
- Release/BOM 绑定最终 commit 和构建 SHA；Full Gate 后如改源码，原候选作废并重跑受影响 Gate。
- 不要求在其他电脑复用当前机器的 Runtime 身份；应重新初始化本地身份。

## 出现问题时先看

1. `git status --short`
2. `scripts/windows/Doctor-PortableProject.ps1 -RequireRuntime`
3. 客服助手“运行详情”中的 Agent、PDD、消息读取和真实发送状态
4. `.runtime/portable/logs/`（仅本机）
5. AI-CE `.runtime/` 与 `%LOCALAPPDATA%\AI-CS\ChannelAgent\runtime`（仅本机）

不要为了恢复服务直接删除数据库、浏览器 Profile 或 Runtime 根目录；先保留备份并定位具体身份/配置错误。
