<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">商品知识</p>
        <h1>商品知识中心</h1>
        <p>把可核对的商品事实整理、审核并持续补充。所有知识操作都需要人工核对，不会自动发布到 AI。</p>
      </div>
      <RouterLink class="button" to="/knowledge-materials">上传并审核资料</RouterLink>
    </div>

    <section class="guide card">
      <h2>运营处理顺序</h2>
      <ol>
        <li><strong>准备资料：</strong>选择商品、SKU、FAQ 或安全规则模板，只填写已核实事实和来源。</li>
        <li><strong>上传并审核：</strong>系统识别字段后，由运营确认适用商品、缺失内容和资料来源。</li>
        <li><strong>查看缺口：</strong>AI 只对已审核版本提出补充建议；建议不会自动改写知识或客服回复。</li>
      </ol>
    </section>

    <section class="workspace-grid">
      <RouterLink class="workspace-card primary" to="/knowledge-materials">
        <strong>资料上传与审核</strong>
        <span>上传商品规格、拼装说明、FAQ 或安全资料，查看识别结果并完成人工审核。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/knowledge-quality-pool">
        <strong>知识质量中心</strong>
        <span>查看资料完整度、已识别的知识缺口和建议修正操作。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/products">
        <strong>商品与 SKU</strong>
        <span>查询已导入的商品、款式和 SKU 事实，核对资料适用范围。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/faqs">
        <strong>FAQ 与安全规则</strong>
        <span>查看已导入的问答与安全规则；修改前需按资料审核流程确认来源。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/sources">
        <strong>来源与冲突</strong>
        <span>查看来源元数据和待处理冲突，不提供原始资料下载或自动确认。</span>
      </RouterLink>
    </section>

    <section class="card boundary">
      <h2>重要边界</h2>
      <p>资料上传、审核和质量分析都不等于 AI 知识已发布。当前系统不会自动训练模型、修改 Prompt、发送客户消息、修改订单或写入 ERP。</p>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.guide { margin-bottom: 20px; background: #f8fbff; }
.guide h2, .boundary h2 { margin-top: 0; color: #172554; }
.guide ol { display: grid; gap: 10px; margin-bottom: 0; padding-left: 22px; }
.guide li, .boundary p { color: #526279; line-height: 1.65; }
.workspace-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.workspace-card { display: grid; gap: 9px; min-height: 138px; padding: 18px; border: 1px solid #dae4f0; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }
.workspace-card:hover { border-color: #92b5e8; box-shadow: 0 10px 20px rgb(39 86 150 / 9%); }
.workspace-card.primary { border-color: #8fb3e6; background: linear-gradient(145deg, #f6faff, #fff); }
.workspace-card strong { color: #172554; }
.workspace-card span { color: #617087; font-size: 13px; line-height: 1.55; }
.boundary { margin-top: 20px; border-left: 4px solid #d59b2c; }
.boundary p { margin-bottom: 0; }
@media (max-width: 980px) { .workspace-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .workspace-grid { grid-template-columns: 1fr; } }
</style>
