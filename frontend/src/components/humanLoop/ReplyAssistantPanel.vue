<template>
  <main class="reply-assistant" aria-label="AI 回复助手" data-testid="reply-assistant">
    <header class="assistant-header">
      <div>
        <p>AI 回复建议</p>
        <h1>回复助手</h1>
      </div>
      <div class="mode-stack">
        <span>仅供建议</span>
        <strong>人工确认后使用</strong>
      </div>
    </header>

    <section class="context-bar" data-testid="workspace-context">
      <label>
        <span>店铺</span>
        <select :value="selectedStoreId ?? ''" :disabled="contextLoading" @change="emitSelect('store', $event)">
          <option value="">选择店铺</option>
          <option v-for="store in stores" :key="store.storeId" :value="store.storeId">{{ store.storeName }}</option>
        </select>
      </label>
      <label>
        <span>{{ products.length > 1 ? '商品（请确认）' : '商品（自动识别）' }}</span>
        <select :value="selectedProductId" :disabled="contextLoading || !selectedStoreId || products.length < 2" @change="emitSelect('product', $event)">
          <option value="">等待识别</option>
          <option v-for="product in products" :key="product.productId" :value="product.productId">{{ product.displayName }}</option>
        </select>
      </label>
      <label>
        <span>{{ skus.length > 1 ? 'SKU（请确认）' : 'SKU（自动识别）' }}</span>
        <select :value="selectedSkuId" :disabled="contextLoading || !selectedProductId || skus.length < 2" @change="emitSelect('sku', $event)">
          <option value="">无需 SKU / 等待识别</option>
          <option v-for="sku in skus" :key="sku.skuId" :value="sku.skuId">{{ sku.displayName }}</option>
        </select>
      </label>
      <div class="context-health" :class="{ warning: Boolean(contextError) }">
        <span>{{ contextLoading ? '识别中' : contextError ? '需要处理' : contextStatus }}</span>
        <small>{{ contextError || '店铺自动加载；商品与 SKU 由消息识别，歧义时人工确认。' }}</small>
      </div>
    </section>

    <section class="timeline" data-testid="message-timeline">
      <div class="timeline-heading">
        <div>
          <strong>{{ conversation?.customerLabel ?? '尚未选择会话' }}</strong>
          <span>{{ conversation ? sourceLabel(conversation.source) : '等待会话' }}</span>
        </div>
        <span v-if="conversation">{{ conversationStatusLabel }} · {{ conversation.messages.length }} 条消息</span>
      </div>
      <div class="messages">
        <article v-for="message in conversation?.messages ?? []" :key="message.messageId" class="customer-message">
          <div><span>{{ message.customerLabel }}</span><time>{{ formatTime(message.receivedAt) }}</time></div>
          <p>{{ message.content }}</p>
          <small>{{ sourceLabel(message.source) }}</small>
        </article>
        <div v-if="!conversation" class="timeline-empty">从左侧选择一条会话。</div>
      </div>
    </section>

    <section class="draft-card" :class="draftTone" data-testid="draft-card">
      <div class="draft-heading">
        <div>
          <span class="draft-state">{{ draftStateLabel }}</span>
          <h2>回复草稿</h2>
        </div>
        <div class="draft-heading-actions">
          <span v-if="draft?.replySource" class="reply-source" :class="draft.replySource.toLowerCase()">
            {{ draft.replySource === 'AI' ? 'AI 建议' : '人工输入' }}
          </span>
          <button
            v-if="canGenerate"
            type="button"
            class="generate-button"
            :disabled="busy || !selectedStoreId || agentStatus === 'OFFLINE' || !canGenerateReply"
            data-testid="generate-draft"
            @click="$emit('generate')"
          >
            {{ busy ? '生成中…' : '生成 AI 建议' }}
          </button>
          <button
            v-else-if="canRegenerate"
            type="button"
            class="secondary-button"
            :disabled="busy"
            data-testid="regenerate-draft"
            @click="$emit('regenerate')"
          >
            {{ draft?.replySource === 'MANUAL' ? '改用 AI 建议' : '重新生成' }}
          </button>
        </div>
      </div>

      <div v-if="busy" class="generating-state">
        <i /><span>{{ draft?.state === 'UNDERSTANDING' ? '正在理解客户问题…' : '正在检索知识并生成建议…' }}</span>
      </div>

      <div v-else-if="draft" class="draft-body">
        <textarea
          :value="draft.editedAnswer"
          :readonly="!canEditText"
          rows="6"
          aria-label="回复草稿"
          :placeholder="draftPlaceholder"
          data-testid="reply-draft-editor"
          @input="handleDraftInput"
        />
        <p v-if="draft.replySource === 'MANUAL'" class="manual-note">人工回复不会作为 AI 采用记录；确认后请复制到渠道窗口发送。</p>
        <p v-else-if="draft.state === 'EDITED'" class="edited-note">已修改：提交时将记录 AI 原稿与人工最终稿。</p>
        <p v-else-if="canComposeManually" class="manual-hint">商品无法识别也不影响处理：可直接在上方输入人工回复。</p>
        <p v-if="draft.warnings.length" class="warning-note">{{ draft.warnings.map(warningLabel).join('；') }}</p>
      </div>

      <div v-else class="draft-empty">
        <strong>等待生成建议</strong>
        <p>系统将先识别店铺、商品和 SKU，再生成草稿、引用和风险；不会自动发送。</p>
      </div>

      <p v-if="actionError" class="action-error" data-testid="workspace-action-error">{{ actionError }}</p>

      <footer v-if="canReview" class="review-actions">
        <template v-if="draft?.replySource === 'MANUAL'">
          <button type="button" class="accept manual-accept" :disabled="actionBusy || !hasManualAnswer" data-testid="manual-accept" @click="$emit('accept', 'MANUAL_ACCEPT')">确认人工回复</button>
          <span class="manual-boundary">不会自动发送，也不会计入 AI 采用数据。</span>
        </template>
        <template v-else>
          <button type="button" class="accept" :disabled="actionBusy || draft?.state === 'EDITED' || !canSubmitFeedback" data-testid="direct-accept" @click="$emit('accept', 'DIRECT_ACCEPT')">采用回复</button>
          <button v-if="draft?.state !== 'EDITED'" type="button" class="edit-accept" :disabled="actionBusy" data-testid="edit-draft" @click="$emit('startEdit')">修改回复</button>
          <button v-else type="button" class="edit-accept" :disabled="actionBusy || !hasEditedAnswer || !canSubmitFeedback" data-testid="edited-accept" @click="$emit('accept', 'EDITED_ACCEPT')">采用修改</button>
          <button type="button" class="reject" :disabled="actionBusy || !canSubmitFeedback" data-testid="reject-draft" @click="openFeedback('REJECT')">拒绝回复</button>
          <button type="button" class="flag" :disabled="actionBusy || !canSubmitFeedback" data-testid="flag-issue" @click="openFeedback('ISSUE')">标记问题</button>
        </template>
      </footer>
      <footer v-else-if="draft?.decisionState === 'APPROVED'" class="approved-actions">
        <span>采用结果已记录。请人工复制到渠道窗口，并再次核对后发送。</span>
        <button type="button" data-testid="copy-approved-reply" @click="$emit('copy')">复制已确认回复</button>
      </footer>
      <footer v-else-if="draft?.decisionState === 'REJECTED'" class="rejected-actions">
        本草稿已拒绝，反馈已沉淀；可等待客户新消息或重新生成。
      </footer>

      <form v-if="feedbackMode" class="feedback-form" data-testid="feedback-form" @submit.prevent="submitFeedback">
        <div>
          <strong>{{ feedbackMode === 'REJECT' ? '拒绝原因' : '标记 AI 问题' }}</strong>
          <button type="button" aria-label="关闭" @click="feedbackMode = null">×</button>
        </div>
        <label for="feedback-type">问题类型</label>
        <select id="feedback-type" v-model="feedbackType" data-testid="feedback-type">
          <option value="FACT_ERROR">事实错误</option>
          <option value="MISSING_INFO">信息缺失</option>
          <option value="STYLE_ISSUE">表达问题</option>
          <option value="RISK_ISSUE">风险问题</option>
          <option value="OTHER">其他</option>
        </select>
        <label for="feedback-note">补充说明（请勿填写客户隐私）</label>
        <textarea id="feedback-note" v-model="feedbackNote" rows="2" maxlength="240" data-testid="feedback-note" />
        <button type="submit" :disabled="feedbackBusy || (feedbackType === 'OTHER' && !feedbackNote.trim())" data-testid="feedback-submit">
          {{ feedbackBusy ? '记录中…' : feedbackMode === 'REJECT' ? '确认拒绝并记录' : '提交问题标记' }}
        </button>
      </form>
      <p v-if="feedbackReceiptId" class="feedback-receipt" data-testid="feedback-receipt">问题反馈已记录。</p>
    </section>

    <section class="evidence-section" data-testid="knowledge-evidence">
      <div class="evidence-heading">
        <div><span>商品与知识依据</span><h2>为什么这样回答</h2></div>
        <strong>{{ draft?.citations.length ?? 0 }} 条依据</strong>
      </div>
      <div v-if="draft?.citations.length" class="evidence-grid">
        <article v-for="(citation, index) in draft.citations" :key="citation.chunkId ?? `${citation.file}-${index}`">
          <div><span :class="`source-${sourceKind(citation).code}`">{{ sourceKind(citation).label }}</span><small>#{{ index + 1 }}</small></div>
          <strong>{{ citation.file }}</strong>
          <p>{{ citation.summary }}</p>
          <footer><span>{{ citation.productId ? '已匹配当前商品' : '通用知识' }}</span><span>{{ citation.skuId ? '已匹配当前规格' : '适用全部规格' }}</span></footer>
        </article>
      </div>
      <div v-else class="evidence-empty">
        {{ draft?.replySource === 'MANUAL' ? '本次为人工直接回复，未调用 AI，也没有 AI 知识依据。' : '生成建议后，这里会展示商品知识、FAQ 与安全规则依据。' }}
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { AiResponseFeedbackType } from '@/api/aiResponseFeedbackTypes'
import type { ProductContextCandidate, SkuContextCandidate, WorkspaceStoreContext } from '@/api/storeContextTypes'
import type { RagCitation } from '@/api/ragTypes'
import type { ReplyDraft, WorkspaceConversation } from '@/stores/humanLoopWorkspace'
import {
  CONVERSATION_STATUS_LABELS,
  type AgentStatus
} from '@/workspace/customerSession'
import type { ChannelMessageSource } from '@/workspace/channelMessageAdapter'

const props = defineProps<{
  conversation: WorkspaceConversation | null
  draft: ReplyDraft | null
  stores: WorkspaceStoreContext[]
  products: ProductContextCandidate[]
  skus: SkuContextCandidate[]
  selectedStoreId: number | null
  selectedProductId: string
  selectedSkuId: string
  contextLoading: boolean
  contextError: string
  contextStatus: string
  busy: boolean
  actionBusy: boolean
  actionError: string
  agentStatus: AgentStatus
  canGenerateReply: boolean
  canSubmitFeedback: boolean
  feedbackBusy: boolean
  feedbackReceiptId: string
}>()

const emit = defineEmits<{
  selectStore: [value: number]
  selectProduct: [value: string]
  selectSku: [value: string]
  generate: []
  regenerate: []
  startEdit: []
  manualEdit: [value: string]
  edit: [value: string]
  accept: [type: 'DIRECT_ACCEPT' | 'EDITED_ACCEPT' | 'MANUAL_ACCEPT']
  feedback: [payload: { mode: 'REJECT' | 'ISSUE'; feedbackType: AiResponseFeedbackType; note: string | null }]
  copy: []
}>()

const feedbackMode = ref<'REJECT' | 'ISSUE' | null>(null)
const feedbackType = ref<AiResponseFeedbackType>('FACT_ERROR')
const feedbackNote = ref('')

const draftStateLabels: Record<string, string> = {
  MESSAGE_RECEIVED: '已收到客户消息',
  UNDERSTANDING: '正在理解问题',
  GENERATING: '正在生成建议',
  DRAFT_READY: '建议已生成',
  HUMAN_REVIEW: '等待人工确认',
  EDITED: '人工已修改',
  ACCEPTED: '已采用',
  EXPIRED: '建议已失效'
}
const draftStateLabel = computed(() => {
  if (props.draft?.replySource === 'MANUAL' && props.draft.state === 'EDITED') return '人工回复编辑中'
  if (props.draft?.replySource === 'MANUAL' && props.draft.decisionState === 'APPROVED') return '人工回复已确认'
  return draftStateLabels[props.draft?.state ?? ''] ?? '等待客户消息'
})

const canGenerate = computed(() => props.draft?.state === 'MESSAGE_RECEIVED')
const canRegenerate = computed(() => ['HUMAN_REVIEW', 'EDITED', 'EXPIRED'].includes(props.draft?.state ?? ''))
const canReview = computed(() => ['HUMAN_REVIEW', 'EDITED'].includes(props.draft?.state ?? ''))
const canComposeManually = computed(() => ['MESSAGE_RECEIVED', 'EXPIRED'].includes(props.draft?.state ?? ''))
const canEditText = computed(() => props.draft?.state === 'EDITED' || canComposeManually.value)
const hasManualAnswer = computed(() => Boolean(props.draft?.editedAnswer.trim()))
const hasEditedAnswer = computed(() => Boolean(
  props.draft?.editedAnswer.trim()
  && props.draft.editedAnswer.trim() !== props.draft.originalAnswer.trim()
))
const conversationStatusLabel = computed(() => props.conversation
  ? CONVERSATION_STATUS_LABELS[props.conversation.status]
  : '')
const draftTone = computed(() => ({
  ready: canReview.value,
  accepted: props.draft?.decisionState === 'APPROVED',
  expired: props.draft?.state === 'EXPIRED'
}))
const draftPlaceholder = computed(() => canComposeManually.value
  ? '可生成 AI 建议；如果商品无法识别，也可在这里直接输入人工回复…'
  : props.draft?.replySource === 'MANUAL' ? '请输入人工回复…' : 'AI 回复建议')

const handleDraftInput = (event: Event): void => {
  const value = (event.target as HTMLTextAreaElement).value
  if (props.draft?.replySource === 'MANUAL' || canComposeManually.value) emit('manualEdit', value)
  else emit('edit', value)
}

const emitSelect = (kind: 'store' | 'product' | 'sku', event: Event) => {
  const value = (event.target as HTMLSelectElement).value
  if (kind === 'store') emit('selectStore', Number(value))
  if (kind === 'product') emit('selectProduct', value)
  if (kind === 'sku') emit('selectSku', value)
}

const openFeedback = (mode: 'REJECT' | 'ISSUE'): void => {
  feedbackMode.value = mode
  feedbackType.value = 'FACT_ERROR'
  feedbackNote.value = ''
}

const submitFeedback = (): void => {
  if (!feedbackMode.value) return
  emit('feedback', {
    mode: feedbackMode.value,
    feedbackType: feedbackType.value,
    note: feedbackNote.value.trim() || null
  })
}

watch(() => props.feedbackReceiptId, (value, previous) => {
  if (value && value !== previous) feedbackMode.value = null
})

const sourceLabel = (source: ChannelMessageSource): string => {
  if (source === 'MANUAL') return '人工录入 · 当前页面内存'
  if (source === 'VALIDATION_FIXTURE') return '验收数据 · 不含真实客户数据'
  return '客服连接程序'
}

const warningLabel = (warning: string): string => ({
  SUGGESTION_ONLY: 'AI 内容仅供建议，请人工核对',
  AUTO_SEND_DISABLED: '系统不会自动发送',
  NO_SCOPED_KNOWLEDGE: '未找到与当前商品直接相关的可靠知识',
  KNOWLEDGE_NOT_PUBLISHED: '该商品的 AI 知识尚未发布',
  LLM_REQUEST_FAILED: 'AI 回复生成失败',
  RAG_RUNTIME_ERROR: 'AI 服务暂时异常',
}[warning] ?? '存在需要人工核对的风险提示')

const formatTime = (value: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--:--'
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(date)
}

const sourceKind = (citation: RagCitation): { code: string; label: string } => {
  const text = `${citation.file} ${citation.summary}`.toLowerCase()
  if (text.includes('faq') || text.includes('常见问题')) return { code: 'faq', label: 'FAQ' }
  if (text.includes('safety') || text.includes('安全') || text.includes('风险')) return { code: 'rule', label: '安全规则' }
  return { code: 'product', label: '商品知识' }
}
</script>

<style scoped>
.reply-assistant { min-width: 0; min-height: 0; padding: 18px; overflow: auto; color: var(--workspace-text); background: linear-gradient(145deg, #f8fcf8, #edf7ef); }
.assistant-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 13px; }
.assistant-header p, .evidence-heading span { margin: 0 0 5px; color: var(--workspace-accent); font-size: 9px; font-weight: 900; letter-spacing: .14em; }
.assistant-header h1 { margin: 0; color: var(--workspace-text); font-size: 21px; }
.mode-stack { display: flex; gap: 7px; align-items: center; }
.mode-stack span, .mode-stack strong { padding: 6px 8px; border-radius: 7px; font-size: 9px; letter-spacing: .05em; }
.mode-stack span { border: 1px solid #9cbfb0; color: #356a50; background: #f7fcf8; }
.mode-stack strong { background: var(--workspace-accent-soft); color: var(--workspace-accent-strong); }
.context-bar { display: grid; grid-template-columns: 1fr 1.25fr 1fr 1.2fr; gap: 9px; padding: 11px; border: 1px solid var(--workspace-border); border-radius: 12px; background: #fbfefb; box-shadow: 0 5px 15px rgb(48 95 61 / 6%); }
.context-bar label { display: grid; gap: 5px; min-width: 0; }
.context-bar label > span, .context-health > span { color: var(--workspace-text-soft); font-size: 9px; font-weight: 800; }
.context-bar select { min-width: 0; height: 34px; padding: 0 8px; border: 1px solid var(--workspace-border); border-radius: 8px; outline: none; color: var(--workspace-text); background: #fff; font-size: 10px; }
.context-bar select:focus { border-color: var(--workspace-accent); box-shadow: 0 0 0 3px rgb(47 125 87 / 9%); }
.context-health { display: grid; align-content: center; gap: 4px; padding: 0 6px; }
.context-health > span { color: var(--workspace-accent); }
.context-health small { color: var(--workspace-muted); font-size: 9px; line-height: 1.4; }
.context-health.warning > span, .context-health.warning small { color: var(--workspace-warning); }
.timeline { margin-top: 11px; border: 1px solid var(--workspace-border); border-radius: 12px; background: #fbfefb; }
.timeline-heading { display: flex; justify-content: space-between; align-items: center; padding: 11px 13px; border-bottom: 1px solid #253550; }
.timeline-heading div { display: flex; gap: 8px; align-items: center; }
.timeline-heading { border-bottom-color: var(--workspace-border); }
.timeline-heading strong { color: var(--workspace-text); font-size: 11px; }
.timeline-heading span { color: var(--workspace-muted); font-size: 9px; }
.messages { display: grid; gap: 8px; max-height: 160px; padding: 12px; overflow: auto; }
.customer-message { max-width: 78%; padding: 10px 12px; border: 1px solid #d0e3d4; border-radius: 4px 12px 12px; background: #e8f4eb; }
.customer-message div { display: flex; justify-content: space-between; gap: 12px; }
.customer-message div span { color: var(--workspace-accent-strong); font-size: 9px; font-weight: 800; }
.customer-message time, .customer-message small { color: var(--workspace-muted); font-size: 8px; }
.customer-message p { margin: 7px 0; color: var(--workspace-text); font-size: 11px; line-height: 1.55; }
.timeline-empty { padding: 15px; color: var(--workspace-muted); font-size: 10px; text-align: center; }
.draft-card { margin-top: 11px; padding: 14px; border: 1px solid var(--workspace-border-strong); border-radius: 13px; background: #fff; box-shadow: 0 8px 24px rgb(47 100 60 / 8%); transition: border-color 160ms ease, box-shadow 160ms ease; }
.draft-card.ready { border-color: var(--workspace-accent); box-shadow: 0 0 0 1px rgb(47 125 87 / 8%), 0 16px 34px rgb(47 100 60 / 10%); }
.draft-card.accepted { border-color: #5a9b76; }
.draft-card.expired { border-color: #d9aeb2; }
.draft-heading { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.draft-heading h2 { margin: 3px 0 0; color: var(--workspace-text); font-size: 15px; }
.draft-heading-actions { display: flex; align-items: center; gap: 8px; }
.draft-state { color: var(--workspace-accent); font-size: 9px; font-weight: 900; letter-spacing: .08em; }
.reply-source { padding: 5px 8px; border-radius: 999px; font-size: 9px; font-weight: 900; }.reply-source.ai { color: #2f6079; background: #e0f1f6; }.reply-source.manual { color: #805c16; background: #fff1c9; }
.generate-button, .secondary-button, .review-actions button, .approved-actions button { padding: 8px 11px; border: 0; border-radius: 8px; color: #fff; font-size: 10px; font-weight: 800; cursor: pointer; }
.generate-button { background: linear-gradient(135deg, #2f7d57, #4b966e); }
.secondary-button { border: 1px solid #8eb6a0; color: var(--workspace-accent-strong); background: #e8f4eb; }
button:disabled { opacity: .4; cursor: not-allowed; }
.generating-state { display: flex; gap: 10px; align-items: center; min-height: 110px; justify-content: center; color: var(--workspace-text-soft); font-size: 11px; }
.generating-state i { width: 13px; height: 13px; border: 2px solid #b8d1bf; border-top-color: var(--workspace-accent); border-radius: 50%; animation: spin .8s linear infinite; }
.draft-body { margin-top: 12px; }
.draft-body textarea { box-sizing: border-box; width: 100%; min-height: 128px; resize: vertical; padding: 13px; border: 1px solid #b7d1bd; border-radius: 10px; outline: none; color: var(--workspace-text); background: #fafffb; font-size: 12px; line-height: 1.65; }
.draft-body textarea:focus { border-color: var(--workspace-accent); box-shadow: 0 0 0 3px rgb(47 125 87 / 11%); }
.draft-body textarea:read-only { color: var(--workspace-text-soft); background: #f2f7f3; }
.edited-note, .manual-note, .manual-hint, .warning-note, .action-error { margin: 7px 0 0; font-size: 9px; line-height: 1.5; }
.edited-note { color: var(--workspace-warning); }.manual-note { color: #6e551b; }.manual-hint { color: var(--workspace-accent-strong); }.warning-note, .action-error { color: var(--workspace-danger); }
.draft-empty { display: grid; min-height: 100px; place-content: center; text-align: center; }
.draft-empty strong { color: var(--workspace-text-soft); font-size: 12px; }.draft-empty p { margin: 7px 0 0; color: var(--workspace-muted); font-size: 9px; }
.review-actions { display: flex; gap: 8px; align-items: center; margin-top: 11px; padding-top: 11px; border-top: 1px solid var(--workspace-border); }
.review-actions .accept { background: var(--workspace-accent); }.review-actions .edit-accept { background: #a77521; }.review-actions .reject { margin-left: auto; background: #a94c56; }.review-actions .flag { background: #4f7d91; }.manual-boundary { color: var(--workspace-muted); font-size: 9px; }
.approved-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 11px; padding-top: 11px; border-top: 1px solid var(--workspace-border); color: var(--workspace-accent-strong); font-size: 9px; }
.approved-actions button { background: var(--workspace-accent); }.rejected-actions { margin-top: 11px; color: var(--workspace-danger); font-size: 9px; }
.feedback-form { display: grid; gap: 7px; margin-top: 11px; padding: 11px; border: 1px solid #e3c37b; border-radius: 10px; background: #fff8e8; }.feedback-form > div { display: flex; align-items: center; justify-content: space-between; }.feedback-form strong { color: #8d6219; font-size: 11px; }.feedback-form > div button { border: 0; color: #8c7955; background: transparent; cursor: pointer; }.feedback-form label { color: #806f50; font-size: 9px; }.feedback-form select, .feedback-form textarea { padding: 7px; border: 1px solid #d9bd80; border-radius: 7px; color: #4d4029; background: #fff; font-size: 9px; }.feedback-form > button { padding: 8px; border: 0; border-radius: 7px; color: #fff; background: #a77521; font-size: 9px; font-weight: 800; cursor: pointer; }.feedback-form > button:disabled { opacity: .45; }.feedback-receipt { margin: 9px 0 0; color: var(--workspace-accent); font-size: 9px; }
.evidence-section { margin-top: 11px; padding: 13px; border: 1px solid var(--workspace-border); border-radius: 12px; background: #fbfefb; }
.evidence-heading { display: flex; justify-content: space-between; align-items: end; }
.evidence-heading h2 { margin: 0; color: var(--workspace-text); font-size: 14px; }.evidence-heading strong { color: var(--workspace-muted); font-size: 10px; }
.evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.evidence-grid article { min-width: 0; padding: 11px; border: 1px solid var(--workspace-border); border-radius: 9px; background: #f2f8f3; }
.evidence-grid article > div, .evidence-grid footer { display: flex; justify-content: space-between; gap: 8px; }
.evidence-grid article > div span { padding: 3px 6px; border-radius: 999px; font-size: 8px; font-weight: 900; }
.source-product { color: #2f6079; background: #dff0f5; }.source-faq { color: #286a4c; background: #dcefe1; }.source-rule { color: #86601b; background: #fff0c9; }
.evidence-grid small, .evidence-grid footer { color: var(--workspace-muted); font-size: 8px; }
.evidence-grid article > strong { display: block; margin-top: 8px; overflow: hidden; color: var(--workspace-text); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-grid p { margin: 6px 0 9px; color: var(--workspace-text-soft); font-size: 9px; line-height: 1.5; }
.evidence-empty { padding: 18px; color: var(--workspace-muted); font-size: 10px; text-align: center; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1120px) { .context-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }.evidence-grid { grid-template-columns: 1fr; } }
</style>
