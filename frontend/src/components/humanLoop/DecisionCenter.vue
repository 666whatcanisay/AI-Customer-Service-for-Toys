<template>
  <aside
    class="decision-center"
    :class="{ collapsed, 'needs-attention': needsReview || draft?.riskLevel === 'HIGH' }"
    aria-label="决策中心"
    data-testid="decision-center"
  >
    <button
      v-if="collapsed"
      type="button"
      class="decision-rail"
      :aria-label="`展开人工确认：${decisionLabel}`"
      data-testid="decision-panel-expand"
      @click="$emit('toggle')"
    >
      <span class="rail-kicker">人工确认</span>
      <strong>{{ decisionLabel }}</strong>
      <span data-testid="active-conversation-status">{{ conversationStatusLabel }}</span>
      <span class="rail-risk" :class="riskTone">风险 {{ riskLabel }}</span>
      <b v-if="needsReview">待确认 1</b>
      <small>REAL_SEND<br />OFF</small>
      <i aria-hidden="true">‹</i>
    </button>

    <template v-else>
      <header class="decision-header">
        <div><p>回复确认</p><h2>人工确认</h2></div>
        <button type="button" aria-label="收起人工确认" data-testid="decision-panel-collapse" @click="$emit('toggle')">›</button>
      </header>

      <section class="decision-status" :class="decisionTone">
        <span>当前状态</span>
        <strong>{{ decisionLabel }}</strong>
        <small>{{ nextStep }}</small>
      </section>

      <section v-if="draft?.editedAnswer" class="reply-preview">
        <span>{{ isManualReply ? '人工回复' : 'AI 回复' }}</span>
        <p>{{ draft.editedAnswer }}</p>
      </section>

      <section class="essential-metrics">
        <article>
          <span>会话</span>
          <strong data-testid="active-conversation-status">{{ conversationStatusLabel }}</strong>
        </article>
        <article>
          <span>风险</span>
          <strong :class="riskTone">{{ riskLabel }}</strong>
        </article>
        <article>
          <span>依据</span>
          <strong>{{ evidenceCount > 0 ? `${evidenceCount} 条` : '无' }}</strong>
        </article>
        <article>
          <span>动作</span>
          <strong>{{ actionLabel }}</strong>
        </article>
      </section>

      <button
        v-if="confirmAction"
        type="button"
        class="decision-confirm"
        :disabled="actionBusy || !canConfirm"
        data-testid="decision-confirm"
        @click="$emit('confirm', confirmAction)"
      >{{ confirmLabel }}</button>
      <p class="send-boundary">REAL_SEND = OFF · 确认不代表真实发送</p>

      <details class="decision-details">
        <summary>查看判断详情</summary>
        <dl>
          <div><dt>下一步</dt><dd>{{ conversationNextStep }}</dd></div>
          <div><dt>置信度</dt><dd>{{ isManualReply ? '不适用' : '未提供，需人工判断' }}</dd></div>
          <div><dt>知识覆盖</dt><dd>{{ requiredFieldText }}</dd></div>
        </dl>
      </details>

      <section v-if="receiptId" class="receipt-card" data-testid="interaction-receipt">
        <span>反馈回执</span>
        <strong>采用结果已记录</strong>
        <small>可在客服反馈记录中查看。</small>
      </section>

      <section v-if="draft?.preparationId" class="receipt-card" data-testid="execution-preparation">
        <span>执行准备</span>
        <strong>已准备，尚未发送真实 PDD 消息</strong>
        <small>准备编号 {{ draft.preparationId }}</small>
      </section>

      <section v-if="feedbackReceiptId" class="receipt-card issue-receipt" data-testid="decision-feedback-receipt">
        <span>问题反馈回执</span>
        <strong>问题反馈已记录</strong>
        <small>运营可在 AI 问题中心查看。</small>
      </section>

      <section v-if="conversation" class="conversation-actions">
        <button
          v-if="conversation.status === 'WAITING_REPLY' && !draft?.preparationId"
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
        <small v-if="conversation.status === 'WAITING_REPLY' && !draft?.preparationId">复制不等于发送；请在外部渠道完成处理后再点击。</small>
        <small v-else-if="draft?.preparationId" data-testid="prepared-send-boundary">执行已准备；真实 PDD 发送未启用，不能标记为已发送。</small>
      </section>

      <details class="safety-card">
        <summary>完整发送边界</summary>
        <ul>
          <li>AI 只生成建议</li>
          <li>客服必须人工确认</li>
          <li>人工确认仅生成执行准备，不代表发送成功</li>
          <li>真实 PDD 发送与真实 Receipt 当前均关闭</li>
          <li>不退款、不修改订单</li>
        </ul>
      </details>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { ReplyDraft, WorkspaceConversation } from '@/stores/humanLoopWorkspace'
import { CONVERSATION_STATUS_LABELS } from '@/workspace/customerSession'

const props = withDefaults(defineProps<{
  draft: ReplyDraft | null
  conversation: WorkspaceConversation | null
  receiptId: string
  feedbackReceiptId: string
  collapsed?: boolean
  actionBusy?: boolean
  canConfirm?: boolean
}>(), {
  collapsed: false,
  actionBusy: false,
  canConfirm: true
})

defineEmits<{
  toggle: []
  confirm: [type: 'DIRECT_ACCEPT' | 'EDITED_ACCEPT' | 'MANUAL_ACCEPT']
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
  if (props.draft?.preparationId) return '执行准备已生成；真实 PDD 发送仍关闭。'
  if (props.conversation.status === 'NEW') return '打开会话开始处理。'
  if (props.conversation.status === 'PROCESSING') return '生成并人工审核回复。'
  if (props.conversation.status === 'WAITING_REPLY') return '等待客服确认并发送。'
  return '会话已由客服显式完成。'
})

const decisionLabel = computed(() => {
  if (!props.conversation) return '未选择会话'
  if (props.draft?.preparationId) return '执行已准备'
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
    : props.draft.preparationId
      ? '已生成 EXECUTION_PREPARED；真实 PDD 消息尚未发送。'
      : '请核对目标会话后准备执行。'
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
const riskLabel = computed(() => !props.conversation ? '—' : isManualReply.value ? '人工判断' : riskLabels[props.draft?.riskLevel ?? ''] ?? '待判断')
const riskTone = computed(() => `risk-${(props.draft?.riskLevel ?? 'unknown').toLowerCase()}`)
const actionLabel = computed(() => isManualReply.value ? '人工直接回复' : actionLabels[props.draft?.action ?? ''] ?? '等待 AI 建议')
const requiredFieldText = computed(() => props.draft?.requiredFields.length
  ? `仍需补充：${props.draft.requiredFields.join('、')}`
  : isManualReply.value ? '人工回复未调用 AI 知识检索。' : '没有返回待补充字段。')
const needsReview = computed(() => Boolean(
  props.draft
  && props.draft.decisionState === 'WAITING_HUMAN'
  && ['DRAFT_READY', 'HUMAN_REVIEW', 'EDITED'].includes(props.draft.state)
))
const confirmAction = computed<'DIRECT_ACCEPT' | 'EDITED_ACCEPT' | 'MANUAL_ACCEPT' | null>(() => {
  if (!needsReview.value || !props.draft) return null
  if (props.draft.replySource === 'MANUAL') return 'MANUAL_ACCEPT'
  if (props.draft.state === 'EDITED') return 'EDITED_ACCEPT'
  return 'DIRECT_ACCEPT'
})
const confirmLabel = computed(() => ({
  DIRECT_ACCEPT: props.draft?.decisionId ? '人工确认并准备执行（不发送）' : '采用回复',
  EDITED_ACCEPT: '采用修改',
  MANUAL_ACCEPT: '确认人工回复'
}[confirmAction.value ?? 'DIRECT_ACCEPT']))
</script>

<style scoped>
.decision-center { min-width: 0; min-height: 0; padding: 14px 12px; overflow: auto; border-left: 1px solid var(--workspace-border); color: var(--workspace-text); background: var(--workspace-panel-soft); }
.decision-center.collapsed { padding: 0; overflow: hidden; }
.decision-rail { display: flex; width: 100%; height: 100%; min-height: 0; flex-direction: column; align-items: center; gap: 10px; padding: 16px 8px; border: 0; color: var(--workspace-text); background: var(--workspace-panel-soft); cursor: pointer; }
.decision-rail:hover { background: #e8f4eb; }.decision-center.needs-attention .decision-rail { box-shadow: inset 3px 0 #d49325; background: #fff9e9; }
.rail-kicker { color: var(--workspace-accent); font-size: 8px; font-weight: 900; letter-spacing: .08em; writing-mode: vertical-rl; }
.decision-rail > strong { max-width: 86px; color: var(--workspace-text); font-size: 13px; line-height: 1.35; text-align: center; }.decision-rail > span:not(.rail-kicker):not(.rail-risk) { color: var(--workspace-muted); font-size: 9px; text-align: center; }
.rail-risk { padding: 5px 7px; border-radius: 999px; color: var(--workspace-muted); background: #fff; font-size: 9px; white-space: nowrap; }.rail-risk.risk-low{color:var(--workspace-accent)}.rail-risk.risk-medium{color:var(--workspace-warning)}.rail-risk.risk-high{color:var(--workspace-danger);background:var(--workspace-danger-soft)}
.decision-rail b { padding: 5px 7px; border-radius: 999px; color: #8b5c00; background: #fff0c9; font-size: 9px; }.decision-rail small { margin-top: auto;color:var(--workspace-danger);font-size:8px;font-weight:900;line-height:1.45;text-align:center}.decision-rail i{display:grid;width:25px;height:25px;place-items:center;border:1px solid var(--workspace-border);border-radius:8px;background:#fff;color:var(--workspace-accent);font-size:18px;font-style:normal}
.decision-header { display:flex;align-items:flex-start;justify-content:space-between;gap:10px }.decision-header p { margin: 0 0 4px; color: var(--workspace-accent); font-size: 8px; font-weight: 800; letter-spacing: .14em; }.decision-header h2 { margin: 0 0 12px; color: var(--workspace-text); font-size: 17px; }.decision-header button{display:grid;width:28px;height:28px;place-items:center;border:1px solid var(--workspace-border);border-radius:8px;background:#fff;color:var(--workspace-accent);font-size:18px;cursor:pointer}
.decision-status { display: grid; gap: 5px; padding: 12px; border: 1px solid #dfbd71; border-radius: 11px; background: var(--workspace-warning-soft); }
.decision-status.approved { border-color: #8fbea0; background: #e3f3e7; }
.decision-status.rejected { border-color: #dfa8ae; background: var(--workspace-danger-soft); }
.decision-status span, .essential-metrics span, .receipt-card span,.reply-preview span { color: var(--workspace-muted); font-size: 9px; }
.decision-status strong { color: #8d6117; font-size: 15px; }
.decision-status.approved strong { color: var(--workspace-accent-strong); }
.decision-status.rejected strong { color: var(--workspace-danger); }
.decision-status small { color: var(--workspace-text-soft); font-size: 9px; line-height: 1.45; }
.reply-preview{display:grid;gap:5px;margin-top:10px;padding:10px;border:1px solid var(--workspace-border);border-radius:9px;background:#fff}.reply-preview p{display:-webkit-box;margin:0;overflow:hidden;color:var(--workspace-text-soft);font-size:10px;line-height:1.55;-webkit-box-orient:vertical;-webkit-line-clamp:4}
.essential-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:10px}.essential-metrics article{display:grid;gap:4px;min-width:0;padding:9px;border:1px solid var(--workspace-border);border-radius:9px;background:#fff}.essential-metrics strong{overflow:hidden;color:var(--workspace-text);font-size:10px;line-height:1.35;text-overflow:ellipsis}.essential-metrics .risk-low{color:var(--workspace-accent)}.essential-metrics .risk-medium{color:var(--workspace-warning)}.essential-metrics .risk-high{color:var(--workspace-danger)}
.decision-confirm{width:100%;margin-top:10px;padding:9px;border:0;border-radius:8px;color:#fff;background:var(--workspace-accent);font-size:9px;font-weight:900;cursor:pointer}.decision-confirm:disabled{cursor:not-allowed;opacity:.45}.send-boundary{margin:7px 0 0;padding:6px;border-radius:7px;color:var(--workspace-danger);background:var(--workspace-danger-soft);font-size:8px;font-weight:800;text-align:center}
.decision-details{margin-top:10px;border:1px solid var(--workspace-border);border-radius:9px;background:#fff}.decision-details summary,.safety-card summary{padding:9px;color:var(--workspace-accent-strong);font-size:9px;font-weight:800;cursor:pointer}.decision-details dl{display:grid;gap:7px;margin:0;padding:0 9px 10px}.decision-details dl div{display:grid;gap:3px}.decision-details dt{color:var(--workspace-muted);font-size:8px}.decision-details dd{margin:0;color:var(--workspace-text-soft);font-size:9px;line-height:1.45}
.receipt-card { display: grid; gap: 6px; margin-top: 12px; padding: 12px; border: 1px solid #9fc3aa; border-radius: 10px; background: #e8f5eb; }
.receipt-card code { overflow-wrap: anywhere; color: var(--workspace-accent); font-size: 10px; }
.receipt-card small { color: var(--workspace-text-soft); font-size: 9px; }
.issue-receipt { border-color: #dfc17d; background: #fff7e4; }.issue-receipt code { color: var(--workspace-warning); }
.conversation-actions { display: grid; gap: 7px; margin-top: 12px; }.conversation-actions button { padding: 9px; border: 1px solid var(--workspace-accent); border-radius: 8px; color: #fff; background: var(--workspace-accent); font-size: 9px; font-weight: 800; cursor: pointer; }.conversation-actions small { color: var(--workspace-muted); font-size: 8px; line-height: 1.45; }
.safety-card { margin-top: 10px; border: 1px solid var(--workspace-border); border-radius: 9px; background: #eaf5ec; }
.safety-card ul { display: grid; gap: 5px; margin: 0; padding: 0 12px 11px 25px; color: var(--workspace-text-soft); font-size: 9px; line-height: 1.4; }
</style>
