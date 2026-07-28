<script setup lang="ts">
const templates = [
  {
    title: '商品资料模板',
    description: '整理名称、适用年龄、安全提示、包装和使用说明等已核实事实。',
    href: '/templates/product-material-template.csv',
    nextStep: '可在“资料上传与审核”中作为受控资料上传，再由运营人工审核。',
  },
  {
    title: 'SKU 资料模板',
    description: '整理颜色、款式、规格、组合关系和上架状态等 SKU 事实。',
    href: '/templates/sku-material-template.csv',
    nextStep: '可在“资料上传与审核”中作为受控资料上传，再由运营人工审核。',
  },
  {
    title: 'FAQ 模板',
    description: '整理客户常见问题、已核实回复要点和人工确认要求。',
    href: '/templates/faq-material-template.csv',
    nextStep: '用于问答资料准备，不是商品批量导入文件；请提交资料审核。',
  },
  {
    title: '安全规则模板',
    description: '整理必须提醒、禁止承诺和人工复核说明。',
    href: '/templates/safety-rule-template.csv',
    nextStep: '用于安全资料准备，不是商品批量导入文件；请提交资料审核。',
  },
]
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">资料准备与导入</p>
        <h1>导入中心</h1>
        <p>先准备可核对的事实，再选择正确入口提交。下载模板或上传资料都不会自动发布到 AI。</p>
      </div>
      <RouterLink class="button" to="/imports/new">商品与 SKU 批量导入</RouterLink>
    </div>

    <section class="steps card">
      <h2>三步完成资料准备</h2>
      <ol>
        <li>下载下方对应模板，保留第一行标题；一行只填写一个已核实事实。</li>
        <li>在“事实来源说明”写明可复核来源，不要填写客户姓名、电话、地址、订单号或支付信息。</li>
        <li>商品与 SKU 批量导入请先预检；其他资料请提交“资料上传与审核”，再由运营人工确认。</li>
      </ol>
    </section>

    <section class="template-grid" aria-label="资料模板下载">
      <article v-for="template in templates" :key="template.href" class="template-card">
        <h2>{{ template.title }}</h2>
        <p>{{ template.description }}</p>
        <a class="button secondary" :href="template.href" download>下载 CSV 模板</a>
        <small>{{ template.nextStep }}</small>
      </article>
    </section>

    <section class="entry-grid">
      <RouterLink class="entry-card primary" to="/imports/new">
        <strong>商品与 SKU 批量导入</strong>
        <span>只接受该入口公布的专用 Excel 格式。系统会先预检；通过后仍进入人工审核区。</span>
      </RouterLink>
      <RouterLink class="entry-card" to="/knowledge-materials">
        <strong>资料上传与审核</strong>
        <span>用于商品资料、SKU 资料、FAQ 和安全规则等受控资料准备，需人工审核后才可供 AI 做质量分析。</span>
      </RouterLink>
      <RouterLink class="entry-card" to="/test-data-packages">
        <strong>测试数据包</strong>
        <span>仅用于已验证的测试 ZIP；不适用于日常商品资料填写或生产数据导入。</span>
      </RouterLink>
    </section>

    <section class="card boundary">
      <h2>导入后会发生什么？</h2>
      <p>系统只进行格式检查、受控保存、识别和人工审核。不会自动修改知识、训练模型、修改 Prompt、发送客户消息、退款、订单或 ERP 数据。</p>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.steps { margin-bottom: 20px; background: #f8fbff; }
.steps h2, .template-card h2, .boundary h2 { margin-top: 0; color: #172554; }
.steps ol { display: grid; gap: 9px; margin-bottom: 0; padding-left: 22px; color: #526279; line-height: 1.65; }
.template-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.template-card { display: grid; gap: 12px; min-height: 218px; padding: 19px; border: 1px solid #dbe4ef; border-radius: 13px; background: #fff; }
.template-card h2 { margin-bottom: 0; font-size: 18px; }
.template-card p { margin: 0; color: #526279; line-height: 1.6; }
.template-card small { margin-top: auto; color: #617087; line-height: 1.5; }
.entry-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
.entry-card { display: grid; gap: 9px; min-height: 132px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }
.entry-card.primary { border-color: #92b5e8; background: linear-gradient(145deg, #f5f9ff, #fff); }
.entry-card span { color: #617087; font-size: 13px; line-height: 1.55; }
.boundary { margin-top: 20px; border-left: 4px solid #d59b2c; }
.boundary p { margin-bottom: 0; color: #526279; line-height: 1.65; }
@media (max-width: 860px) { .entry-grid { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .template-grid { grid-template-columns: 1fr; } }
</style>
