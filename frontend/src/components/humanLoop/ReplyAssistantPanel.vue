<template>
  <main class="reply-assistant" aria-label="AI 回复助手" data-testid="reply-assistant">
    <header class="assistant-header">
      <div>
        <p>AI REPLY ASSISTANT</p>
        <h1>回复副驾驶</h1>
      </div>
      <div class="mode-stack">
        <span>SUGGEST</span>
        <strong>HUMAN_CONFIRM_SEND</strong>
      </div>
    </header>

    <section class="context-bar" data-testid="workspace-context">
      <label>
        <span>店铺</span>
        <select :value="selectedStoreCode" :disabled="contextLoading" @change="emitSelect('store', $event)">
          <option value="">选择店铺</option>
          <option v-for="store in stores" :key="store.storeCode" :value="store.storeCode">{{ store.name }}</option>
        </select>
      </label>
      <label>
        <span>商品</span>
        <select :value="selectedProductId" :disabled="contextLoading || !selectedStoreCode" @change="emitSelect('product', $event)">
          <option value="">选择商品</option>
          <option v-for="product in products" :key="product.productId" :value="product.productId">{{ product.displayName }}</option>
        </select>
      </label>
      <label>
        <span>SKU（可选）</span>
        <select :value="selectedSkuId" :disabled="contextLoading || !selectedProductId" @change="emitSelect('sku', $event)">
          <option value="">不确定就留空</option>
          <option v-for="sku in skus" :key="sku.skuId" :value="sku.skuId">{{ sku.displayName }}</option>
        </select>
      </label>
      <div class="context-health" :class="{ warning: Boolean(contextError) }">
        <span>{{ contextLoading ? '读取中' : contextError ? '目录异常' : '上下文已绑定' }}</span>
        <small>{{ contextError || 'AI 只按当前店铺、商品和 SKU 检索。' }}</small>
      </div>
    </section>

    <section class="timeline" data-testid="message-timeline">
      <div class="timeline-heading">
        <div>
          <strong>{{ conversation?.customerLabel ?? '尚未选择会话' }}</strong>
          <span>{{ conversation?.source === 'MOCK' ? '模拟渠道消息' : 'Channel Agent' }}</span>
        </div>
        <span v-if="conversation">{{ conversation.messages.length }} 条消息</span>
      </div>
      <div class="messages">
        <article v-for="message in conversation?.messages ?? []" :key="message.messageId" class="customer-message">
          <div><span>{{ message.customerLabel }}</span><time>{{ formatTime(message.receivedAt) }}</time></div>
          <p>{{ message.content }}</p>
          <small>{{ message.source === 'MOCK' ? 'Mock Message · 不含真实客户数据' : 'Channel Agent' }}</small>
        </article>
        <div v-if="!conversation" class="timeline-empty">从左侧选择一条会话。</div>
      </div>
    </section>

    <section class="draft-card" :class="draftTone" data-testid="draft-card">
      <div class="draft-heading">
        <div>
          <span class="draft-state">{{ draftStateLabel }}</span>
          <h2>AI 回复草稿</h2>
        </div>
        <button
          v-if="canGenerate"
          type="button"
          class="generate-button"
          :disabled="busy || !selectedProductId"
          data-testid="generate-draft"
          @click="$emit('generate')"
        >
          {{ busy ? '生成中…' : '生成回复建议' }}
        </button>
        <button
          v-else-if="canRegenerate"
          type="button"
          class="secondary-button"
          :disabled="busy"
          data-testid="regenerate-draft"
          @click="$emit('regenerate')"
        >
          重新生成
        </button>
      </div>

      <div v-if="busy" class="generating-state">
        <i /><span>{{ draft?.state === 'UNDERSTANDING' ? '正在理解客户问题…' : '正在检索知识并生成建议…' }}</span>
      </div>

      <div v-else-if="draft?.originalAnswer" class="draft-body">
        <textarea
          :value="draft.editedAnswer"
          :readonly="!canReview"
          rows="6"
          aria-label="AI回复草稿"
          data-testid="reply-draft-editor"
          @input="$emit('edit', ($event.target as HTMLTextAreaElement).value)"
        />
        <p v-if="draft.state === 'EDITED'" class="edited-note">已修改：提交时将记录 AI 原稿与人工最终稿。</p>
        <p v-if="draft.warnings.length" class="warning-note">{{ draft.warnings.join('；') }}</p>
      </div>

      <div v-else class="draft-empty">
        <strong>等待生成建议</strong>
        <p>选择商品上下文后，AI 会返回草稿、引用和风险；不会自动发送。</p>
      </div>

      <p v-if="actionError" class="action-error" data-testid="workspace-action-error">{{ actionError }}</p>

      <footer v-if="canReview" class="review-actions">
        <button type="button" class="accept" :disabled="actionBusy || draft?.state === 'EDITED'" data-testid="direct-accept" @click="$emit('accept', 'DIRECT_ACCEPT')">采用原稿</button>
        <button type="button" class="edit-accept" :disabled="actionBusy || draft?.state !== 'EDITED'" data-testid="edited-accept" @click="$emit('accept', 'EDITED_ACCEPT')">修改后采用</button>
        <button type="button" class="reject" :disabled="actionBusy" data-testid="reject-draft" @click="$emit('reject')">拒绝并沉淀</button>
      </footer>
      <footer v-else-if="draft?.decisionState === 'APPROVED'" class="approved-actions">
        <span>采用结果已记录。请人工复制到渠道窗口，并再次核对后发送。</span>
        <button type="button" data-testid="copy-approved-reply" @click="$emit('copy')">复制已确认回复</button>
      </footer>
      <footer v-else-if="draft?.decisionState === 'REJECTED'" class="rejected-actions">
        本草稿已拒绝，反馈已沉淀；可等待客户新消息或重新生成。
      </footer>
    </section>

    <section class="evidence-section" data-testid="knowledge-evidence">
      <div class="evidence-heading">
        <div><span>KNOWLEDGE EVIDENCE</span><h2>为什么这样回答</h2></div>
        <strong>{{ draft?.citations.length ?? 0 }} 条依据</strong>
      </div>
      <div v-if="draft?.citations.length" class="evidence-grid">
        <article v-for="(citation, index) in draft.citations" :key="citation.chunkId ?? `${citation.file}-${index}`">
          <div><span :class="`source-${sourceKind(citation).code}`">{{ sourceKind(citation).label }}</span><small>#{{ index + 1 }}</small></div>
          <strong>{{ citation.file }}</strong>
          <p>{{ citation.summary }}</p>
          <footer><span>商品 {{ citation.productId ?? '未标注' }}</span><span>SKU {{ citation.skuId ?? '通用' }}</span></footer>
        </article>
      </div>
      <div v-else class="evidence-empty">生成建议后，这里会展示商品知识、FAQ 与安全规则依据。</div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { CatalogProduct, CatalogSku, CatalogStore } from '@/api/platformTypes'
import type { RagCitation } from '@/api/ragTypes'
import type { ReplyDraft, WorkspaceConversation } from '@/stores/humanLoopWorkspace'

const props = defineProps<{
  conversation: WorkspaceConversation | null
  draft: ReplyDraft | null
  stores: CatalogStore[]
  products: CatalogProduct[]
  skus: CatalogSku[]
  selectedStoreCode: string
  selectedProductId: string
  selectedSkuId: string
  contextLoading: boolean
  contextError: string
  busy: boolean
  actionBusy: boolean
  actionError: string
}>()

const emit = defineEmits<{
  selectStore: [value: string]
  selectProduct: [value: string]
  selectSku: [value: string]
  generate: []
  regenerate: []
  edit: [value: string]
  accept: [type: 'DIRECT_ACCEPT' | 'EDITED_ACCEPT']
  reject: []
  copy: []
}>()

const draftStateLabels: Record<string, string> = {
  MESSAGE_RECEIVED: 'Message Received',
  UNDERSTANDING: 'Understanding',
  GENERATING: 'Generating',
  DRAFT_READY: 'Draft Ready',
  HUMAN_REVIEW: 'Waiting Human',
  EDITED: 'Edited',
  ACCEPTED: 'Accepted',
  EXPIRED: 'Expired'
}
const draftStateLabel = computed(() => draftStateLabels[props.draft?.state ?? ''] ?? 'Idle')

const canGenerate = computed(() => props.draft?.state === 'MESSAGE_RECEIVED')
const canRegenerate = computed(() => ['HUMAN_REVIEW', 'EDITED', 'EXPIRED'].includes(props.draft?.state ?? ''))
const canReview = computed(() => ['HUMAN_REVIEW', 'EDITED'].includes(props.draft?.state ?? ''))
const draftTone = computed(() => ({
  ready: canReview.value,
  accepted: props.draft?.decisionState === 'APPROVED',
  expired: props.draft?.state === 'EXPIRED'
}))

const emitSelect = (kind: 'store' | 'product' | 'sku', event: Event) => {
  const value = (event.target as HTMLSelectElement).value
  if (kind === 'store') emit('selectStore', value)
  if (kind === 'product') emit('selectProduct', value)
  if (kind === 'sku') emit('selectSku', value)
}

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
.reply-assistant { min-width: 0; min-height: 0; padding: 18px; overflow: auto; color: #dfe8f7; background: radial-gradient(circle at 70% 0, #1a2c4b 0, #0d1525 34%, #0b1220 100%); }
.assistant-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 13px; }
.assistant-header p, .evidence-heading span { margin: 0 0 5px; color: #6680a8; font-size: 9px; font-weight: 900; letter-spacing: .14em; }
.assistant-header h1 { margin: 0; color: #f4f7fd; font-size: 21px; }
.mode-stack { display: flex; gap: 7px; align-items: center; }
.mode-stack span, .mode-stack strong { padding: 6px 8px; border-radius: 7px; font-size: 9px; letter-spacing: .05em; }
.mode-stack span { border: 1px solid #406497; color: #8db8ff; }
.mode-stack strong { background: #234d3f; color: #84ddb8; }
.context-bar { display: grid; grid-template-columns: 1fr 1.25fr 1fr 1.2fr; gap: 9px; padding: 11px; border: 1px solid #293b59; border-radius: 12px; background: #111c2f; }
.context-bar label { display: grid; gap: 5px; min-width: 0; }
.context-bar label > span, .context-health > span { color: #8fa0ba; font-size: 9px; font-weight: 800; }
.context-bar select { min-width: 0; height: 34px; padding: 0 8px; border: 1px solid #344965; border-radius: 8px; outline: none; color: #dce6f5; background: #0c1626; font-size: 10px; }
.context-bar select:focus { border-color: #5d91dc; }
.context-health { display: grid; align-content: center; gap: 4px; padding: 0 6px; }
.context-health > span { color: #68d2aa; }
.context-health small { color: #778ba9; font-size: 9px; line-height: 1.4; }
.context-health.warning > span, .context-health.warning small { color: #e9b966; }
.timeline { margin-top: 11px; border: 1px solid #283a57; border-radius: 12px; background: #111b2d; }
.timeline-heading { display: flex; justify-content: space-between; align-items: center; padding: 11px 13px; border-bottom: 1px solid #253550; }
.timeline-heading div { display: flex; gap: 8px; align-items: center; }
.timeline-heading strong { color: #dfe8f7; font-size: 11px; }
.timeline-heading span { color: #7185a4; font-size: 9px; }
.messages { display: grid; gap: 8px; max-height: 160px; padding: 12px; overflow: auto; }
.customer-message { max-width: 78%; padding: 10px 12px; border-radius: 4px 12px 12px; background: #1b2a43; }
.customer-message div { display: flex; justify-content: space-between; gap: 12px; }
.customer-message div span { color: #85adf0; font-size: 9px; font-weight: 800; }
.customer-message time, .customer-message small { color: #627696; font-size: 8px; }
.customer-message p { margin: 7px 0; color: #e5ebf5; font-size: 11px; line-height: 1.55; }
.timeline-empty { padding: 15px; color: #7285a4; font-size: 10px; text-align: center; }
.draft-card { margin-top: 11px; padding: 14px; border: 1px solid #2d405f; border-radius: 13px; background: linear-gradient(145deg, #141f33, #111a2a); transition: border-color 160ms ease, box-shadow 160ms ease; }
.draft-card.ready { border-color: #3f6ca8; box-shadow: 0 0 0 1px rgb(77 132 211 / 10%), 0 16px 36px rgb(0 0 0 / 16%); }
.draft-card.accepted { border-color: #377762; }
.draft-card.expired { border-color: #65454c; }
.draft-heading { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.draft-heading h2 { margin: 3px 0 0; color: #eef4fd; font-size: 15px; }
.draft-state { color: #78a8ef; font-size: 9px; font-weight: 900; letter-spacing: .08em; }
.generate-button, .secondary-button, .review-actions button, .approved-actions button { padding: 8px 11px; border: 0; border-radius: 8px; color: #fff; font-size: 10px; font-weight: 800; cursor: pointer; }
.generate-button { background: linear-gradient(135deg, #3e7ad2, #5b8ee0); }
.secondary-button { border: 1px solid #3a5479; background: #1b2b44; }
button:disabled { opacity: .4; cursor: not-allowed; }
.generating-state { display: flex; gap: 10px; align-items: center; min-height: 110px; justify-content: center; color: #9eb5d6; font-size: 11px; }
.generating-state i { width: 13px; height: 13px; border: 2px solid #344c70; border-top-color: #70a2ef; border-radius: 50%; animation: spin .8s linear infinite; }
.draft-body { margin-top: 12px; }
.draft-body textarea { width: 100%; resize: vertical; padding: 13px; border: 1px solid #344967; border-radius: 10px; outline: none; color: #edf3fc; background: #0c1524; font-size: 12px; line-height: 1.65; }
.draft-body textarea:focus { border-color: #5c8ed8; box-shadow: 0 0 0 3px rgb(78 132 210 / 12%); }
.draft-body textarea:read-only { color: #bcc8d9; }
.edited-note, .warning-note, .action-error { margin: 7px 0 0; font-size: 9px; line-height: 1.5; }
.edited-note { color: #edc875; }.warning-note, .action-error { color: #ed9ca5; }
.draft-empty { display: grid; min-height: 100px; place-content: center; text-align: center; }
.draft-empty strong { color: #9badc7; font-size: 12px; }.draft-empty p { margin: 7px 0 0; color: #667a99; font-size: 9px; }
.review-actions { display: flex; gap: 8px; margin-top: 11px; padding-top: 11px; border-top: 1px solid #293a57; }
.review-actions .accept { background: #2e765d; }.review-actions .edit-accept { background: #8d6a27; }.review-actions .reject { margin-left: auto; background: #7e3945; }
.approved-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 11px; padding-top: 11px; border-top: 1px solid #315244; color: #8fc6ae; font-size: 9px; }
.approved-actions button { background: #2d725b; }.rejected-actions { margin-top: 11px; color: #d5939c; font-size: 9px; }
.evidence-section { margin-top: 11px; padding: 13px; border: 1px solid #283a56; border-radius: 12px; background: #101a2b; }
.evidence-heading { display: flex; justify-content: space-between; align-items: end; }
.evidence-heading h2 { margin: 0; color: #e9f0fb; font-size: 14px; }.evidence-heading strong { color: #7f96b7; font-size: 10px; }
.evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.evidence-grid article { min-width: 0; padding: 11px; border: 1px solid #2a3d5b; border-radius: 9px; background: #142036; }
.evidence-grid article > div, .evidence-grid footer { display: flex; justify-content: space-between; gap: 8px; }
.evidence-grid article > div span { padding: 3px 6px; border-radius: 999px; font-size: 8px; font-weight: 900; }
.source-product { color: #88b4ff; background: #203d65; }.source-faq { color: #86d8bb; background: #1c493d; }.source-rule { color: #f2ca77; background: #493b1d; }
.evidence-grid small, .evidence-grid footer { color: #6f82a0; font-size: 8px; }
.evidence-grid article > strong { display: block; margin-top: 8px; overflow: hidden; color: #d8e3f3; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-grid p { margin: 6px 0 9px; color: #92a3bc; font-size: 9px; line-height: 1.5; }
.evidence-empty { padding: 18px; color: #6f82a0; font-size: 10px; text-align: center; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1120px) { .context-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }.evidence-grid { grid-template-columns: 1fr; } }
</style>
