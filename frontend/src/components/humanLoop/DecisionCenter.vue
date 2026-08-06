<template>
  <aside class="decision-center" aria-label="决策中心" data-testid="decision-center">
    <header>
      <p>DECISION CENTER</p>
      <h2>人工决策</h2>
    </header>

    <section class="decision-status" :class="decisionTone">
      <span>当前状态</span>
      <strong>{{ decisionLabel }}</strong>
      <small>{{ nextStep }}</small>
    </section>

    <section class="metric-stack">
      <article>
        <span>风险等级</span>
        <strong :class="riskTone">{{ riskLabel }}</strong>
      </article>
      <article>
        <span>置信度</span>
        <strong>未提供</strong>
        <small>A 当前不返回置信度，不显示推测数值。</small>
      </article>
      <article>
        <span>知识覆盖</span>
        <strong>{{ evidenceCount > 0 ? `已找到 ${evidenceCount} 条依据` : '尚无依据' }}</strong>
        <small>{{ requiredFieldText }}</small>
      </article>
      <article>
        <span>建议动作</span>
        <strong>{{ actionLabel }}</strong>
      </article>
    </section>

    <section v-if="receiptId" class="receipt-card" data-testid="interaction-receipt">
      <span>反馈回执</span>
      <code>{{ receiptId }}</code>
      <small>已进入 Customer Feedback Loop。</small>
    </section>

    <section class="safety-card">
      <strong>发送边界</strong>
      <ul>
        <li>AI 只生成建议</li>
        <li>客服必须人工确认</li>
        <li>系统不自动发送</li>
        <li>不退款、不修改订单</li>
      </ul>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { ReplyDraft } from '@/stores/humanLoopWorkspace'

const props = defineProps<{
  draft: ReplyDraft | null
  receiptId: string
}>()

const evidenceCount = computed(() => props.draft?.citations.length ?? 0)

const decisionLabel = computed(() => {
  if (props.draft?.decisionState === 'APPROVED') return 'Approved'
  if (props.draft?.decisionState === 'REJECTED') return 'Rejected'
  return 'Waiting Human'
})

const decisionTone = computed(() => ({
  approved: props.draft?.decisionState === 'APPROVED',
  rejected: props.draft?.decisionState === 'REJECTED'
}))

const nextStep = computed(() => {
  if (!props.draft) return '选择一条会话开始处理。'
  if (props.draft.decisionState === 'APPROVED') return '已记录采用；请人工复制到渠道发送。'
  if (props.draft.decisionState === 'REJECTED') return '已记录拒绝；问题进入反馈闭环。'
  if (props.draft.state === 'MESSAGE_RECEIVED') return '生成 AI 回复建议。'
  if (['UNDERSTANDING', 'GENERATING'].includes(props.draft.state)) return 'AI 正在处理，请等待。'
  return '核对事实、引用和风险后再决定。'
})

const riskLabels: Record<string, string> = { LOW: '低', MEDIUM: '中', HIGH: '高' }
const actionLabels: Record<string, string> = {
  DIRECT_ANSWER: '可直接答复（仍需人工确认）',
  CONTROLLED_ANSWER: '受控答复',
  ASK_CLARIFY: '向客户追问',
  REQUIRE_LOOKUP: '补充查询',
  TRANSFER_HUMAN: '转人工判断',
  REFUSE: '礼貌拒绝'
}
const riskLabel = computed(() => riskLabels[props.draft?.riskLevel ?? ''] ?? '待判断')
const riskTone = computed(() => `risk-${(props.draft?.riskLevel ?? 'unknown').toLowerCase()}`)
const actionLabel = computed(() => actionLabels[props.draft?.action ?? ''] ?? '等待 AI 建议')
const requiredFieldText = computed(() => props.draft?.requiredFields.length
  ? `仍需补充：${props.draft.requiredFields.join('、')}`
  : '没有返回待补充字段。')
</script>

<style scoped>
.decision-center { min-width: 0; min-height: 0; padding: 20px 16px; overflow: auto; border-left: 1px solid #263653; background: #111a2c; }
header p { margin: 0 0 5px; color: #6f83a8; font-size: 9px; font-weight: 800; letter-spacing: .14em; }
header h2 { margin: 0 0 16px; color: #f3f7ff; font-size: 18px; }
.decision-status { display: grid; gap: 6px; padding: 15px; border: 1px solid #7b6229; border-radius: 12px; background: #2a2419; }
.decision-status.approved { border-color: #2e735c; background: #172c27; }
.decision-status.rejected { border-color: #7d424c; background: #301d25; }
.decision-status span, .metric-stack span, .receipt-card span { color: #8e9db7; font-size: 10px; }
.decision-status strong { color: #f2c96d; font-size: 17px; }
.decision-status.approved strong { color: #75d8b0; }
.decision-status.rejected strong { color: #ef8e9a; }
.decision-status small { color: #aeb9ca; font-size: 10px; line-height: 1.5; }
.metric-stack { display: grid; gap: 9px; margin-top: 12px; }
.metric-stack article { display: grid; gap: 5px; padding: 12px; border: 1px solid #293a57; border-radius: 10px; background: #151f34; }
.metric-stack strong { color: #e7eefb; font-size: 12px; line-height: 1.45; }
.metric-stack small { color: #7285a4; font-size: 9px; line-height: 1.45; }
.metric-stack .risk-low { color: #71d4ad; }
.metric-stack .risk-medium { color: #efca70; }
.metric-stack .risk-high { color: #f18a96; }
.receipt-card { display: grid; gap: 6px; margin-top: 12px; padding: 12px; border: 1px solid #315d52; border-radius: 10px; background: #142822; }
.receipt-card code { overflow-wrap: anywhere; color: #76d8b2; font-size: 10px; }
.receipt-card small { color: #8cae9f; font-size: 9px; }
.safety-card { margin-top: 12px; padding: 13px; border: 1px solid #32425e; border-radius: 10px; background: #151f33; }
.safety-card strong { color: #cad7ed; font-size: 11px; }
.safety-card ul { display: grid; gap: 6px; margin: 9px 0 0; padding-left: 17px; color: #8fa0bc; font-size: 10px; line-height: 1.4; }
</style>
