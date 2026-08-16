# 当前版本与限制

更新时间：2026-08-16

## 源码基线

- AI-CS 导入前基线：`be8b6993cf7aab9cc8bf2d138cfa62accd733440`
- AI-CE 导入基线：`a32430d22433e7c26ec38524a5e4150482165f14`
- 合并方式：Git subtree，目录 `AI-CS-Channel-Execution-Engine/`
- 共享 Gateway Wire：保持现有版本，不在本次可移植化中修改

最终发布 SHA、Tag 和 GitHub Release 以 Git 历史和 Release 页面为准。

## 发布候选验证

- AI Core：`268 passed, 3 skipped`
- Platform：`221 passed`
- 客服工作台：`236 passed`，typecheck/build 通过
- Admin：`117 passed`，typecheck/build 通过
- AI-CE：`948 passed, 2 skipped`
- 可移植 PowerShell 路径测试：通过

## 当前行为

- AI-CS A/C/B/Admin 可由根目录可移植脚本初始化并启动。
- AI-CE 当前页自动回复实现保留。
- PDD 自动会话导航明确禁用；不会使用 Shift+Tab 或循环点击左侧买家列表。
- 当前页识别、商品上下文、AI 回答、逐消息授权、唯一 Sender 和 Receipt 代码均在仓库内。
- 商品知识、数据库、PDD 登录态和生产凭据不在仓库内。

## 迁移到新电脑后必须重新完成

1. 安装 Channel Agent Windows 客户端。
2. 登录专属 PDD Edge。
3. 读取并核验 PDD `platform_store_id`。
4. 与 AI-CS `store_id` 建立唯一双 ID 绑定。
5. 重新生成本机 Credential Manager 凭据、Selector Evidence 与运行身份。
6. 通过一次当前会话读取、回答、发送与 Receipt 核对后再开启自动回复。

## 不应从 GitHub 恢复的内容

- `.runtime/`、SQLite 数据库与绑定文件
- `backend/vector_db/` 和知识源文件
- `.env`、密钥、Token、Cookie、证书私钥
- PDD 浏览器 Profile 与客户聊天内容
- `node_modules/`、`.venv/`、`dist/`、日志和测试截图

## 已知边界

- 本项目以 Windows 为主运行环境。
- 新克隆只提供空的本地开发数据库；业务数据需要受控导入。
- 未提供公开云部署；PDD 浏览器链路依赖本机 Edge 与页面结构。
- 页面/Selector 改版、身份不唯一、输入框有人操作或发送结果 UNKNOWN 时应停止自动发送。
