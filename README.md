# AI Customer Service for Toys

[![Portable Monorepo](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/actions/workflows/portable-monorepo.yml/badge.svg)](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/actions/workflows/portable-monorepo.yml)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Node 22](https://img.shields.io/badge/Node.js-22-339933?logo=nodedotjs&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows)
![Release](https://img.shields.io/badge/release-V1.0.0-1f7a4d)

面向玩具电商的 AI 客服系统。这个仓库同时包含 AI-CS（知识、模型、运营与客服工作台）和 AI-CE（渠道读取、上下文、授权、Sender 与 Receipt），可在 Windows 新电脑上从同一个 Git 克隆继续开发。

![AI 客服工作台](docs/showcase/images/01-customer-workbench.png)

## 能做什么

- 管理店铺、商品、SKU、FAQ、安全规则与发布版本。
- 通过 RAG、固定规则和质量门生成有依据的客服回答。
- 在绿色客服助手中查看会话、商品上下文、AI 建议和人工状态。
- AI-CE 维护 Observation、Spool、ACK/Cursor、CustomerContext、逐消息授权、唯一 Sender 与 Receipt。
- 当前生产策略仅处理客服电脑上**当前打开的 PDD 会话**；自动跳转会话已禁用。
- 自动发送仍受店铺/会话/客户唯一性、单消息单授权、防重放、输入框占用和 Kill Switch 约束。

## 架构

![系统架构](docs/showcase/architecture.svg)

```text
PDD 当前会话
  → PDD Read Adapter
  → Normalized Observation
  → Channel Agent / Spool / ACK-Cursor
  → Channel Engine Host / CustomerContext
  → AI-CS Reply Router / RAG / Quality / Evidence
  → 绿色客服助手
  → 单消息 Grant
  → 唯一 Sender
  → Receipt
```

详细说明见 [架构文档](docs/ARCHITECTURE.md)。

## 仓库结构

| 目录 | 作用 |
| --- | --- |
| `backend/` | A：RAG、模型调用、Reply Router、质量与 Evidence |
| `platform_backend/` | C：IAM、Store/Product/SKU、知识发布和业务 API |
| `frontend/` | 客服工作台与 Channel Agent UI |
| `admin_web/` | 运营管理中心 |
| `contracts/` | AI-CS 共享契约 |
| `AI-CS-Channel-Execution-Engine/` | AI-CE：渠道 Agent、Host、自动回复授权、Sender、Receipt |
| `scripts/windows/` | 新电脑安装、启动、停止和运行诊断 |
| `docs/` | 架构、开发、交接、当前状态和历史验收记录 |

## Windows 快速开始

### 1. 安装前置软件

- Git
- Python 3.12 x64
- Node.js 22
- pnpm 11：`npm install -g pnpm@11`
- Ollama，以及项目当前使用的模型：`ollama pull qwen3.5:9b`

### 2. 克隆并初始化

```powershell
git clone https://github.com/666whatcanisay/AI-Customer-Service-for-Toys.git
cd AI-Customer-Service-for-Toys
.\首次安装.cmd
```

初始化脚本会创建三个本地 Python 虚拟环境、安装前端依赖、构建三个前端、创建 Git 忽略的开发数据库与随机服务密钥。不会下载或覆盖生产数据库、客户数据与 PDD 登录态。

### 3. 启动

```powershell
.\启动AI客服.cmd
```

默认地址：

- AI Core：`http://127.0.0.1:8420`
- Platform API：`http://127.0.0.1:8421`
- 客服工作台：`http://127.0.0.1:8422`
- 运营管理中心：`http://127.0.0.1:8423`

已安装 Channel Agent 且已完成本机 PDD 配置后，可运行：

```powershell
.\启动完整客服含PDD.cmd
```

停止全部受管服务：

```powershell
.\停止全部服务.cmd
```

完整步骤与故障排查见 [Windows 开发环境指南](docs/GETTING_STARTED_WINDOWS.md)。

## 开发验证

```powershell
# AI Core
backend\.venv\Scripts\python.exe -m pytest backend\tests

# Platform
platform_backend\.venv\Scripts\python.exe -m pytest platform_backend\tests

# Customer UI
cd frontend
npm run test
npm run typecheck
npm run build

# Admin UI
cd ..\admin_web
pnpm test
pnpm typecheck
pnpm build

# Channel Engine
cd ..\AI-CS-Channel-Execution-Engine
.venv\Scripts\python.exe -m pytest
```

## 安全与数据边界

本仓库不包含生产数据库、向量库、模型、知识源文件、客户消息、浏览器 Profile、Cookie、Token、密钥、日志、构建产物或依赖目录。GitHub 展示图片和静态 Demo 全部使用脱敏演示数据。

真实 PDD 发送不是“仓库下载后自动开启”的能力。新电脑必须重新完成登录、双 Store ID 绑定、Selector/页面身份检查和本机授权；Sender 结果为 `UNKNOWN` 时不自动重试。

## 项目文档

- [Windows 开发环境指南](docs/GETTING_STARTED_WINDOWS.md)
- [系统架构](docs/ARCHITECTURE.md)
- [项目详细交接](docs/HANDOFF.md)
- [当前版本与限制](docs/CURRENT_STATE.md)
- [GitHub 展示素材说明](docs/showcase/README.md)
- [AI-CE 说明](AI-CS-Channel-Execution-Engine/README.md)

## 许可

当前为私有项目，未授予开源许可。未经所有者明确授权，不得复制、分发或用于第三方生产环境。
