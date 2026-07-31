# AI-CS GitHub Presentation V1 Task Card

任务：`AI-CS GitHub Presentation V1`

目标：让 GitHub 默认展示材料能够清晰说明 AI-CS V1.0.0 的定位、能力、架构、技术栈、运行方式和版本范围，并提供完全脱敏、可复现生成的五张 Demo 截图。

范围：仅修改 `README.md`、`docs/showcase/**` 和本任务报告；不修改 A/B/C 业务代码、Contracts、Migration、Runtime、数据库或业务数据。

所有者：Control / Documentation / QA。

成功标准：

1. README 包含项目介绍、核心能力、系统架构、技术栈、运行方式和版本说明。
2. 五张截图分别展示客服工作台、运营知识中心、商品导入、AI 发布状态和 RAG 引用。
3. 截图和 README 不包含公司名称、真实店铺、真实商品、客户、订单、内部地址、数据库路径或真实运行标识。
4. 架构图明确展示 Excel → Knowledge Management → AI Publishing → Vector Database → RAG → Customer Assistant。
5. 所有展示数据明确标记为 Demo，并通过独立内容与视觉复核。
6. Git diff 仅包含展示材料，GitHub 分支推送后可正确渲染。

风险与缓解：

- 误用正式页面数据 → 使用独立静态 Demo 页面，不访问正式 API。
- 图片残留内部信息 → 使用禁词扫描、OCR/可见文本复核和人工视觉检查。
- README 误导运行能力 → 明确本地依赖、数据不随 Git 分发和人工确认边界。
- 展示改动影响 V1.0.0 Tag → Tag 保持不变，展示材料作为发布分支的后续文档提交。

Gate：`GITHUB_PRESENTATION_SCOPE_READY`
