# AI-CS C Admin Navigation Simplification V1 任务卡

## 任务

AI-CS C Admin Navigation Simplification V1

## 目标

在不改变任何路由、业务能力和数据语义的前提下，为 C Admin 增加默认简洁导航与可切换的高级导航，使普通运营优先看到 6 个高频入口，管理员仍可访问全部现有正式页面。

## 基线与分支

- 代码基线：`8fe36b109d533131e11609841f2ce5ec1b2d6f00`
- 设计依据：`AI-CS UI Information Architecture Optimization Plan V1`
- 实施分支：`codex/c-admin-navigation-simplification-v1`
- 目标 Gate：`C_ADMIN_NAVIGATION_SIMPLIFIED_V1`

## 范围

- 修改：`admin_web/src/App.vue`、对应 Admin 测试、C/Control 文档。
- 简洁模式：运营工作台、商品、知识、导入、客服运营、AI状态。
- 高级模式：知识治理、运营复盘、系统诊断。
- 保留全部原路由、旧 URL、书签与页面。

## 不包含

- API、数据库、migration、contracts、R006、R009、A、RAG、Prompt、B 或 Runtime 修改。
- 新模块、新权限、新鉴权或业务流程变化。
- 将测试工具入口暴露给运营。

## 成功标准

1. 首次使用默认显示 6 个简洁入口。
2. 高级模式显示全部原导航能力，并使用冻结后的中文展示名称。
3. 模式偏好仅保存在浏览器本地，存储不可用时安全回退简洁模式。
4. 原正式路由逐项可解析，不删除页面。
5. Import Center 六模板与 R009 资料上传入口保持。
6. Admin 单测、typecheck、build 和隔离浏览器回归通过。

## 风险与缓解

- 高级模式被误认为权限：页面明确说明“只改变导航显示，不改变权限”。
- 旧入口不可发现：高级模式保留全部旧入口，原 URL 和深链不变。
- 本地偏好损坏：只接受 `simple/advanced`，其他值回退 `simple`。
- 正式 Runtime 被影响：在独立 Worktree 和非标准测试端口验收，不重启或切换正式服务。

## 验收

代码、测试、浏览器证据、文档与 diff 范围均已通过：

- Admin：28 个测试文件、65 项测试通过；typecheck、build 通过。
- 浏览器：简洁 6 项、高级 3 组/8 项、14 个原路由、六模板、R009 上传入口及模式持久化通过；控制台 0 error。
- 范围：仅 `admin_web/**` 与 C/Control 治理文档；正式 Runtime 未修改。

Gate：`C_ADMIN_NAVIGATION_SIMPLIFIED_V1`。
