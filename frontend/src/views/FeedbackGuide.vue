<template>
  <main class="feedback-guide" data-testid="feedback-guide">
    <section class="guide-hero">
      <p class="eyebrow">AI 客服平台 · 问题反馈</p>
      <h1>反馈一条需要改进的 AI 建议</h1>
      <p>请先在 AI 客服中完成一条咨询，并明确选择“未采用”。系统会在你确认原因后保存真实反馈。</p>
      <RouterLink to="/ai-chat" class="primary-action">进入 AI 客服</RouterLink>
    </section>

    <section class="feedback-path" data-testid="feedback-path">
      <div><span>1</span><strong>生成建议</strong><p>先选择商品上下文并获取 AI 回复。</p></div>
      <div><span>2</span><strong>选择未采用</strong><p>仅在确实不采用建议时进入问题反馈。</p></div>
      <div><span>3</span><strong>提交真实原因</strong><p>成功后才会显示“反馈已记录”。</p></div>
    </section>

    <section class="decision-card" data-testid="capture-feedback-boundary">
      <p class="eyebrow">先判断，再操作</p>
      <h2>优秀回复和 AI 问题反馈是两条独立路径</h2>
      <div class="decision-grid">
        <article>
          <strong>回复可用，值得沉淀</strong>
          <p>选择“直接采用”或“修改后采用”，再收藏为优秀案例，等待人工审核。</p>
        </article>
        <article>
          <strong>回复不采用，需要改进</strong>
          <p>选择“未采用”，再记录最接近的原因；不会变成优秀案例。</p>
        </article>
      </div>
    </section>

    <section class="guide-card">
      <h2>提交前请确认</h2>
      <ol>
        <li>已选择对应商品或 SKU，并获得 AI 建议。</li>
        <li>确实未采用该建议，而不是仅复制或暂未处理。</li>
        <li>选择最接近的原因：事实错误、缺少信息、表达问题、风险问题或其他。</li>
        <li>不要填写客户姓名、电话、地址、完整订单号或隐私截图内容。</li>
      </ol>
      <p class="boundary">反馈提交后由中台保存并进入后续人工确认与分析；不会自动修改 Prompt、知识或客户消息。</p>
    </section>

    <section class="reason-card" data-testid="feedback-reason-guide">
      <p class="eyebrow">选择原因</p>
      <h2>选择最接近的问题，不需要写成长说明</h2>
      <div class="reason-grid">
        <article><strong>事实错误</strong><span>商品、规则或描述与已知事实不一致。</span></article>
        <article><strong>缺少信息</strong><span>缺少回答当前问题所需的关键条件。</span></article>
        <article><strong>表达问题</strong><span>措辞不清楚、不适合直接发送或难以理解。</span></article>
        <article><strong>风险问题</strong><span>可能形成承诺、越权处理或需要人工介入。</span></article>
        <article><strong>其他</strong><span>仅在前四类都不适用时填写去标识化说明。</span></article>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<style scoped>
.feedback-guide { width: min(900px, 100%); margin: 0 auto; color: #172033; }
.guide-hero, .guide-card, .reason-card, .decision-card { padding: clamp(20px, 4vw, 34px); border: 1px solid #d9e4f1; border-radius: 18px; background: #fff; box-shadow: 0 12px 32px rgb(31 61 109 / 7%); }
.guide-hero { background: radial-gradient(circle at 0 0, rgb(100 157 255 / 19%), transparent 24rem), #fff; }
.guide-card, .reason-card, .decision-card { margin-top: 18px; }
.eyebrow { margin: 0 0 8px; color: #2e63d5; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
h1 { margin: 0 0 10px; font-size: clamp(26px, 4vw, 36px); }
h2 { margin: 0 0 12px; font-size: 20px; }
.guide-hero > p:not(.eyebrow), li { color: #60708a; line-height: 1.65; }
ol { display: grid; gap: 9px; margin: 0; padding-left: 23px; }
.primary-action { display: inline-flex; margin-top: 18px; padding: 10px 16px; border-radius: 10px; background: #2e63d5; color: #fff; font-weight: 800; text-decoration: none; }
.boundary { margin: 18px 0 0; padding: 12px; border-radius: 10px; background: #fff8e7; color: #77510a; font-size: 13px; line-height: 1.6; }
.feedback-path { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }.feedback-path > div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; padding: 14px; border: 1px solid #d9e4f1; border-radius: 14px; background: #fafdff; }.feedback-path span { display: grid; width: 24px; height: 24px; place-items: center; border-radius: 50%; background: #e8f1ff; color: #285fc8; font-size: 12px; font-weight: 900; }.feedback-path strong { font-size: 13px; }.feedback-path p { grid-column: 2; margin: -3px 0 0; color: #60708a; font-size: 12px; line-height: 1.5; }
.decision-card h2 { margin-bottom: 16px; }.decision-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.decision-grid article { padding: 14px; border: 1px solid #e0e8f3; border-radius: 12px; background: #fbfdff; }.decision-grid article:first-child { border-left: 3px solid #41a271; }.decision-grid article:last-child { border-left: 3px solid #dc8a46; }.decision-grid strong { color: #254671; font-size: 14px; }.decision-grid p { margin: 7px 0 0; color: #68758a; font-size: 12px; line-height: 1.55; }
.reason-card h2 { margin-bottom: 16px; }.reason-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.reason-grid article { display: grid; gap: 5px; padding: 13px; border: 1px solid #e0e8f3; border-radius: 12px; background: #fbfdff; }.reason-grid article:last-child { grid-column: span 2; }.reason-grid strong { color: #254671; font-size: 13px; }.reason-grid span { color: #68758a; font-size: 12px; line-height: 1.5; }
@media (max-width: 680px) { .feedback-path, .decision-grid, .reason-grid { grid-template-columns: 1fr; }.reason-grid article:last-child { grid-column: auto; } }
</style>
