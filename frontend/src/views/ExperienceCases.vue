<template>
  <div class="experience-page" data-testid="experience-cases-page">
    <header>
      <p class="eyebrow">客服经验沉淀</p>
      <h1>我的案例</h1>
      <p>这里只显示本次浏览器会话中，经真实提交接口确认的最小摘要；不会保存问题、AI 回复或最终回复。</p>
      <RouterLink to="/ai-chat" class="capture-link">去收藏一条优秀案例</RouterLink>
    </header>

    <el-alert
      title="当前显示本次会话的已确认提交"
      description="案例历史不会由页面猜测或伪造。刷新后本地摘要会清空；远端历史在正式接入后再按冻结查询协议展示。"
      type="info"
      :closable="false"
      show-icon
    />

    <section class="case-journey" data-testid="experience-case-journey">
      <div><span>1</span><p><strong>选择采用结果</strong>直接采用或修改后采用的回复才可沉淀。</p></div>
      <div><span>2</span><p><strong>确认经验类型</strong>在表单中明确选择案例的实际使用方式。</p></div>
      <div><span>3</span><p><strong>等待人工审核</strong>提交成功不等于自动进入知识库。</p></div>
    </section>

    <section class="case-status-guide" data-testid="experience-case-status-guide">
      <strong>审核状态说明</strong>
      <ul>
        <li><b class="status-new">新建</b><span>已收到，等待处理。</span></li>
        <li><b class="status-reviewing">审核中</b><span>正在由人工确认。</span></li>
        <li><b class="status-approved">已通过</b><span>可进入后续知识运营流程。</span></li>
        <li><b class="status-rejected">未通过</b><span>不会自动进入知识库。</span></li>
      </ul>
    </section>

    <section v-if="submissions.length" class="case-list" data-testid="experience-case-list">
      <article v-for="item in submissions" :key="`${item.submittedAt}-${item.productId}`">
        <div class="case-title">
          <strong>{{ item.productId }}</strong>
          <span :class="`status-${item.reviewStatus.toLowerCase()}`">{{ EXPERIENCE_CASE_STATUS_LABELS[item.reviewStatus] }}</span>
        </div>
        <dl>
          <div><dt>店铺</dt><dd>{{ item.storeCode }}</dd></div>
          <div><dt>SKU</dt><dd>{{ item.skuId || '未选择' }}</dd></div>
          <div><dt>采用方式</dt><dd>{{ EXPERIENCE_FEEDBACK_LABELS[item.feedbackType] }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ item.submittedAt }}</dd></div>
        </dl>
      </article>
    </section>
    <section v-else class="empty-card" data-testid="experience-case-empty">
      <p>当前会话还没有成功提交的案例。请在 AI 回答的反馈区域选择采用方式后，点击“收藏案例”。</p>
      <RouterLink to="/ai-chat" class="empty-link">从 AI 回答开始</RouterLink>
    </section>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
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
.capture-link { display: inline-flex; margin-top: 14px; padding: 8px 12px; border-radius: 9px; background: #2e63d5; color: #fff; font-size: 13px; font-weight: 800; text-decoration: none; }
.case-journey { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }
.case-journey > div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; padding: 12px; border: 1px solid #dbe4ef; border-radius: 12px; background: #fafdff; }
.case-journey span { display: grid; width: 24px; height: 24px; place-items: center; border-radius: 50%; background: #e8f1ff; color: #285fc8; font-size: 12px; font-weight: 900; }
.case-journey p { margin: 0; color: #68758a; font-size: 12px; line-height: 1.55; }.case-journey strong { color: #243b5c; }
.case-status-guide { display: flex; align-items: center; gap: 16px; margin-top: 12px; padding: 12px; border: 1px solid #e0e8f3; border-radius: 12px; background: #fff; color: #243b5c; font-size: 12px; }.case-status-guide ul { display: flex; flex: 1; flex-wrap: wrap; gap: 8px 14px; margin: 0; padding: 0; list-style: none; }.case-status-guide li { display: flex; align-items: center; gap: 5px; color: #68758a; }.case-status-guide b { padding: 3px 6px; border-radius: 999px; font-size: 11px; }.status-new { background: #eef4fd; color: #315fbd; }.status-reviewing { background: #fff4dc; color: #8a5d00; }.status-approved { background: #eaf8f0; color: #1e7247; }.status-rejected { background: #fff0ef; color: #a33c36; }
.case-list { display: grid; gap: 12px; margin-top: 16px; } article, .empty-card { padding: 18px; border: 1px solid #dbe4ef; border-radius: 15px; background: #fff; }
.case-title { display: flex; justify-content: space-between; gap: 12px; } .case-title span { padding: 4px 8px; border-radius: 999px; background: #eef4fd; color: #315fbd; font-size: 11px; font-weight: 800; }.case-title .status-new { background: #eef4fd; color: #315fbd; }.case-title .status-reviewing { background: #fff4dc; color: #8a5d00; }.case-title .status-approved { background: #eaf8f0; color: #1e7247; }.case-title .status-rejected { background: #fff0ef; color: #a33c36; }
dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0 0; } dt { color: #7a8799; font-size: 11px; } dd { margin: 4px 0 0; overflow-wrap: anywhere; font-size: 13px; }
.empty-card { margin-top: 16px; color: #68758a; line-height: 1.65; }.empty-card p { margin: 0; }.empty-link { display: inline-flex; margin-top: 12px; color: #285fc8; font-size: 13px; font-weight: 800; text-decoration: none; } @media (max-width: 680px) { dl, .case-journey { grid-template-columns: 1fr 1fr; }.case-status-guide { align-items: flex-start; flex-direction: column; gap: 8px; } } @media (max-width: 480px) { .case-journey { grid-template-columns: 1fr; } }
</style>
