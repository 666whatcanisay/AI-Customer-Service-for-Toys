<template>
  <main class="feedback-guide" data-testid="feedback-guide">
    <section class="guide-hero">
      <p class="eyebrow">AI 客服平台 · 问题反馈</p>
      <h1>反馈一条需要改进的 AI 建议</h1>
      <p>请先在 AI 客服中完成一条咨询，并明确选择“未采用”。系统会在你确认原因后保存真实反馈。</p>
      <RouterLink to="/ai-chat" class="primary-action">进入 AI 客服</RouterLink>
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
  </main>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<style scoped>
.feedback-guide { width: min(900px, 100%); margin: 0 auto; color: #172033; }
.guide-hero, .guide-card { padding: clamp(20px, 4vw, 34px); border: 1px solid #d9e4f1; border-radius: 18px; background: #fff; box-shadow: 0 12px 32px rgb(31 61 109 / 7%); }
.guide-hero { background: radial-gradient(circle at 0 0, rgb(100 157 255 / 19%), transparent 24rem), #fff; }
.guide-card { margin-top: 18px; }
.eyebrow { margin: 0 0 8px; color: #2e63d5; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
h1 { margin: 0 0 10px; font-size: clamp(26px, 4vw, 36px); }
h2 { margin: 0 0 12px; font-size: 20px; }
.guide-hero > p:not(.eyebrow), li { color: #60708a; line-height: 1.65; }
ol { display: grid; gap: 9px; margin: 0; padding-left: 23px; }
.primary-action { display: inline-flex; margin-top: 18px; padding: 10px 16px; border-radius: 10px; background: #2e63d5; color: #fff; font-weight: 800; text-decoration: none; }
.boundary { margin: 18px 0 0; padding: 12px; border-radius: 10px; background: #fff8e7; color: #77510a; font-size: 13px; line-height: 1.6; }
</style>
