<template>
  <div class="experience-page" data-testid="experience-cases-page">
    <header>
      <p class="eyebrow">客服经验沉淀</p>
      <h1>我的案例</h1>
      <p>这里只显示本次浏览器会话中，经真实提交接口确认的最小摘要；不会保存问题、AI 回复或最终回复。</p>
    </header>

    <el-alert
      title="案例查询接口尚未声明"
      description="当前页面不猜测 GET 协议，也不提供本地 Mock 记录。刷新页面后，请等待中台发布按 created_by 查询的冻结接口。"
      type="info"
      :closable="false"
      show-icon
    />

    <section v-if="submissions.length" class="case-list" data-testid="experience-case-list">
      <article v-for="item in submissions" :key="`${item.submittedAt}-${item.productId}`">
        <div class="case-title"><strong>{{ item.productId }}</strong><span>{{ EXPERIENCE_CASE_STATUS_LABELS[item.status] }}</span></div>
        <dl>
          <div><dt>店铺</dt><dd>{{ item.storeCode }}</dd></div>
          <div><dt>SKU</dt><dd>{{ item.skuId || '未选择' }}</dd></div>
          <div><dt>采用方式</dt><dd>{{ EXPERIENCE_FEEDBACK_LABELS[item.feedbackType] }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ item.submittedAt }}</dd></div>
        </dl>
      </article>
    </section>
    <section v-else class="empty-card" data-testid="experience-case-empty">
      当前会话还没有成功提交的案例。请在 AI 回答的反馈区域选择采用方式后，点击“收藏案例”。
    </section>
  </div>
</template>

<script setup lang="ts">
import { EXPERIENCE_CASE_STATUS_LABELS, EXPERIENCE_FEEDBACK_LABELS } from '@/workspace/experienceCasePresentation'
import { useExperienceCaseSubmissions } from '@/workspace/experienceCaseSession'
import { useTesterIdentity } from '@/workspace/testerIdentity'

const { identity } = useTesterIdentity()
const { submissions } = useExperienceCaseSubmissions(identity.value.reporterId)
</script>

<style scoped>
.experience-page { width: min(1000px, 100%); margin: 0 auto; color: #172033; }
header { margin-bottom: 16px; } .eyebrow { margin: 0 0 6px; color: #315fbd; font-size: 12px; font-weight: 800; letter-spacing: .1em; }
h1 { margin: 0 0 8px; font-size: 30px; } header > p:last-child { margin: 0; color: #68758a; }
.case-list { display: grid; gap: 12px; margin-top: 16px; } article, .empty-card { padding: 18px; border: 1px solid #dbe4ef; border-radius: 15px; background: #fff; }
.case-title { display: flex; justify-content: space-between; gap: 12px; } .case-title span { padding: 4px 8px; border-radius: 999px; background: #eef4fd; color: #315fbd; font-size: 11px; font-weight: 800; }
dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0 0; } dt { color: #7a8799; font-size: 11px; } dd { margin: 4px 0 0; overflow-wrap: anywhere; font-size: 13px; }
.empty-card { margin-top: 16px; color: #68758a; line-height: 1.65; } @media (max-width: 680px) { dl { grid-template-columns: 1fr 1fr; } }
</style>
