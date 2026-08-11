<template>
  <aside class="decision-center" aria-label="决策中心" data-testid="decision-center">
    <header>
      <p>回复确认</p>
      <h2>人工确认</h2>
    </header>

    <section class="decision-status" :class="decisionTone">
      <span>当前状态</span>
      <strong>{{ decisionLabel }}</strong>
      <small>{{ nextStep }}</small>
    </section>

    <section class="metric-stack">
      <article>
        <span>会话状态</span>
        <strong data-testid="active-conversation-status">{{ conversationStatusLabel }}</strong>
        <small>{{ conversationNextStep }}</small>
      </article>
      <article>
        <span>风险等级</span>
        <strong :class="riskTone">{{ riskLabel }}</strong>
      </article>
      <article>
        <span>置信度</span>
        <strong>{{ isManualReply ? '不适用' : '未提供' }}</strong>
        <small>{{ isManualReply ? '本次内容由客服人工输入，请按业务规范自行核对。' : '系统不提供可靠置信度，请结合商品依据和风险提示判断。' }}</small>
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
      <strong>采用结果已记录</strong>
      <small>可在客服反馈记录中查看。</small>
    </section>

    <section v-if="executionReceiptId" class="receipt-card" data-testid="execution-receipt">
      <span>执行回执</span>
      <strong>已确认发送到当前 PDD 会话</strong>
      <small>回执 {{ executionReceiptId }}</small>
    </section>

    <section v-if="feedbackReceiptId" class="receipt-card issue-receipt" data-testid="decision-feedback-receipt">
      <span>问题反馈回执</span>
      <strong>问题反馈已记录</strong>
      <small>运营可在 AI 问题中心查看。</small>
    </section>

    <section v-if="conversation" class="conversation-actions">
      <button
        v-if="conversation.status === 'WAITING_REPLY'"
        type="button"
        data-testid="complete-conversation"
        @click="$emit('complete')"
      >已在渠道处理，标记完成</button>
      <button
        v-else-if="conversation.status === 'COMPLETED'"
        type="button"
        data-testid="reopen-conversation"
        @click="$emit('reopen')"
      >重新打开会话</button>
      <small v-if="conversation.status === 'WAITING_REPLY'">复制不等于发送；请在外部渠道完成处理后再点击。</small>
    </section>

    <section class="safety-card">
      <strong>发送边界</strong>
      <ul>
        <li>AI 只生成建议</li>
        <li>客服必须人工确认</li>
        <li>仅在客服点击“确认发送”后执行单条回复</li>
        <li>不退款、不修改订单</li>
      </ul>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { ReplyDraft, WorkspaceConversation } from '@/stores/humanLoopWorkspace'
import { CONVERSATION_STATUS_LABELS } from '@/workspace/customerSession'

const props = defineProps<{
  draft: ReplyDraft | null
  conversation: WorkspaceConversation | null
  receiptId: string
  executionReceiptId: string
  feedbackReceiptId: string
}>()

defineEmits<{
  complete: []
  reopen: []
}>()

const evidenceCount = computed(() => props.draft?.citations.length ?? 0)
const isManualReply = computed(() => props.draft?.replySource === 'MANUAL')
const conversationStatusLabel = computed(() => props.conversation
  ? CONVERSATION_STATUS_LABELS[props.conversation.status]
  : '未选择')
const conversationNextStep = computed(() => {
  if (!props.conversation) return '从左侧选择会话。'
  if (props.conversation.status === 'NEW') return '打开会话开始处理。'
  if (props.conversation.status === 'PROCESSING') return '生成并人工审核回复。'
  if (props.conversation.status === 'WAITING_REPLY') return '等待客服确认并发送。'
  return '会话已由客服显式完成。'
})

const decisionLabel = computed(() => {
  if (props.draft?.decisionState === 'APPROVED') return isManualReply.value ? '人工回复已确认' : '已采用'
  if (props.draft?.decisionState === 'REJECTED') return '已拒绝'
  return '等待人工确认'
})

const decisionTone = computed(() => ({
  approved: props.draft?.decisionState === 'APPROVED',
  rejected: props.draft?.decisionState === 'REJECTED'
}))

const nextStep = computed(() => {
  if (!props.draft) return '选择一条会话开始处理。'
  if (props.draft.decisionState === 'APPROVED') return isManualReply.value
    ? '请核对目标会话后完成发送。'
    : props.executionReceiptId ? '已发送并生成不可变回执。' : '请核对目标会话后确认发送。'
  if (props.draft.decisionState === 'REJECTED') return '已记录拒绝；问题进入反馈闭环。'
  if (props.draft.state === 'MESSAGE_RECEIVED') return '可生成 AI 建议，也可直接输入人工回复。'
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
const riskLabel = computed(() => isManualReply.value ? '人工判断' : riskLabels[props.draft?.riskLevel ?? ''] ?? '待判断')
const riskTone = computed(() => `risk-${(props.draft?.riskLevel ?? 'unknown').toLowerCase()}`)
const actionLabel = computed(() => isManualReply.value ? '人工直接回复' : actionLabels[props.draft?.action ?? ''] ?? '等待 AI 建议')
const requiredFieldText = computed(() => props.draft?.requiredFields.length
  ? `仍需补充：${props.draft.requiredFields.join('、')}`
  : isManualReply.value ? '人工回复未调用 AI 知识检索。' : '没有返回待补充字段。')
</script>

<style scoped>
.decision-center { min-width: 0; min-height: 0; padding: 20px 16px; overflow: auto; border-left: 1px solid var(--workspace-border); color: var(--workspace-text); background: var(--workspace-panel-soft); }
header p { margin: 0 0 5px; color: var(--workspace-accent); font-size: 9px; font-weight: 800; letter-spacing: .14em; }
header h2 { margin: 0 0 16px; color: var(--workspace-text); font-size: 18px; }
.decision-status { display: grid; gap: 6px; padding: 15px; border: 1px solid #dfbd71; border-radius: 12px; background: var(--workspace-warning-soft); }
.decision-status.approved { border-color: #8fbea0; background: #e3f3e7; }
.decision-status.rejected { border-color: #dfa8ae; background: var(--workspace-danger-soft); }
.decision-status span, .metric-stack span, .receipt-card span { color: var(--workspace-muted); font-size: 10px; }
.decision-status strong { color: #8d6117; font-size: 17px; }
.decision-status.approved strong { color: var(--workspace-accent-strong); }
.decision-status.rejected strong { color: var(--workspace-danger); }
.decision-status small { color: var(--workspace-text-soft); font-size: 10px; line-height: 1.5; }
.metric-stack { display: grid; gap: 9px; margin-top: 12px; }
.metric-stack article { display: grid; gap: 5px; padding: 12px; border: 1px solid var(--workspace-border); border-radius: 10px; background: #fff; }
.metric-stack strong { color: var(--workspace-text); font-size: 12px; line-height: 1.45; }
.metric-stack small { color: var(--workspace-muted); font-size: 9px; line-height: 1.45; }
.metric-stack .risk-low { color: var(--workspace-accent); }
.metric-stack .risk-medium { color: var(--workspace-warning); }
.metric-stack .risk-high { color: var(--workspace-danger); }
.receipt-card { display: grid; gap: 6px; margin-top: 12px; padding: 12px; border: 1px solid #9fc3aa; border-radius: 10px; background: #e8f5eb; }
.receipt-card code { overflow-wrap: anywhere; color: var(--workspace-accent); font-size: 10px; }
.receipt-card small { color: var(--workspace-text-soft); font-size: 9px; }
.issue-receipt { border-color: #dfc17d; background: #fff7e4; }.issue-receipt code { color: var(--workspace-warning); }
.conversation-actions { display: grid; gap: 7px; margin-top: 12px; }.conversation-actions button { padding: 9px; border: 1px solid var(--workspace-accent); border-radius: 8px; color: #fff; background: var(--workspace-accent); font-size: 9px; font-weight: 800; cursor: pointer; }.conversation-actions small { color: var(--workspace-muted); font-size: 8px; line-height: 1.45; }
.safety-card { margin-top: 12px; padding: 13px; border: 1px solid var(--workspace-border); border-radius: 10px; background: #eaf5ec; }
.safety-card strong { color: var(--workspace-text); font-size: 11px; }
.safety-card ul { display: grid; gap: 6px; margin: 9px 0 0; padding-left: 17px; color: var(--workspace-text-soft); font-size: 10px; line-height: 1.4; }
</style>
