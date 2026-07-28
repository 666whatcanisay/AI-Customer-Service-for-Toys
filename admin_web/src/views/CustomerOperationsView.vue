<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">客服运营</p>
        <h1>客服运营工作台</h1>
        <p>查看客服沉淀的案例、AI 问题和运营改进建议。所有客户回复仍由客服人工确认与发送。</p>
      </div>
    </div>

    <section class="workspace-grid">
      <RouterLink class="workspace-card primary" to="/experience-cases">
        <strong>客服经验库</strong>
        <span>审核客服主动沉淀的优秀回复，保留版本和评测证据。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/ai-feedback-optimization-pool">
        <strong>AI 问题中心</strong>
        <span>查看客服未采用 AI 回答后提交的问题、分析原因和改进建议。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/suggestions">
        <strong>运营改进建议</strong>
        <span>汇总已提交建议，按运营流程确认、规划或关闭。</span>
      </RouterLink>
    </section>

    <section class="card boundary">
      <h2>本页不做自动化决策</h2>
      <p>案例审核和 AI 问题分析用于改进系统，不自动修改 Prompt、发布知识、训练模型或评价客服个人，也不触发任何客户、订单、退款或 ERP 操作。</p>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.workspace-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.workspace-card { display: grid; gap: 10px; min-height: 146px; padding: 19px; border: 1px solid #dbe4ef; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }
.workspace-card.primary { border-color: #92b5e8; background: linear-gradient(145deg, #f6faff, #fff); }
.workspace-card span { color: #617087; font-size: 13px; line-height: 1.6; }
.boundary { margin-top: 20px; border-left: 4px solid #d59b2c; }
.boundary h2 { margin-top: 0; color: #172554; }
.boundary p { margin-bottom: 0; color: #526279; line-height: 1.65; }
@media (max-width: 820px) { .workspace-grid { grid-template-columns: 1fr; } }
</style>
