<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">客服运营</p>
        <h1>客服运营工作台</h1>
        <p>从回复质量、Badcase、知识缺口和反馈分析四个入口完成复盘。所有客户回复仍由客服人工确认与发送。</p>
      </div>
    </div>

    <section class="workspace-grid">
      <RouterLink class="workspace-card primary" to="/experience-cases">
        <strong>AI 回复质量</strong>
        <span>查看客服采用和沉淀的优秀回复，核对人工最终稿与评测证据。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/ai-feedback-optimization-pool">
        <strong>Badcase</strong>
        <span>查看客服未采用 AI 回答后提交的问题、分析原因和改进建议。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/knowledge-gaps">
        <strong>知识缺口</strong>
        <span>查看当前缺失、待补充和需要重新确认的商品知识。</span>
      </RouterLink>
      <RouterLink class="workspace-card" to="/ai-issues">
        <strong>Feedback 分析</strong>
        <span>确认客服拒绝形成的问题，创建知识优化任务并记录改善结果。</span>
      </RouterLink>
    </section>

    <section class="card improvement-flow">
      <p class="eyebrow">持续改善流程</p>
      <ol>
        <li><span>1</span><strong>客服采用、修改或拒绝</strong></li>
        <li><span>2</span><strong>问题与 Badcase 沉淀</strong></li>
        <li><span>3</span><strong>运营补充知识并人工审核</strong></li>
        <li><span>4</span><strong>重新发布后人工复验</strong></li>
      </ol>
    </section>

    <section class="card boundary">
      <h2>本页不做自动化决策</h2>
      <p>案例审核和 AI 问题分析用于改进系统，不自动修改 Prompt、发布知识、训练模型或评价客服个人，也不触发任何客户、订单、退款或 ERP 操作。</p>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.workspace-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.workspace-card { display: grid; gap: 10px; min-height: 146px; padding: 19px; border: 1px solid #dbe4ef; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }
.workspace-card.primary { border-color: #92b5e8; background: linear-gradient(145deg, #f6faff, #fff); }
.workspace-card span { color: #617087; font-size: 13px; line-height: 1.6; }
.improvement-flow { margin-top: 20px; }
.improvement-flow ol { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
.improvement-flow li { display: flex; align-items: center; gap: 9px; padding: 12px; border-radius: 10px; color: #314f76; background: #f4f8fd; font-size: 12px; }
.improvement-flow li span { display: grid; flex: 0 0 auto; width: 24px; height: 24px; place-items: center; border-radius: 999px; color: #fff; background: #315f9f; font-size: 10px; }
.boundary { margin-top: 20px; border-left: 4px solid #d59b2c; }
.boundary h2 { margin-top: 0; color: #172554; }
.boundary p { margin-bottom: 0; color: #526279; line-height: 1.65; }
@media (max-width: 1050px) { .workspace-grid, .improvement-flow ol { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 820px) { .workspace-grid, .improvement-flow ol { grid-template-columns: 1fr; } }
</style>
