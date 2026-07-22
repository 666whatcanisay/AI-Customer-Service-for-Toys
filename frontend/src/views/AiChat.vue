<template>
  <main class="workspace-shell">
    <header class="workspace-header">
      <div>
        <p class="eyebrow">木木小栈 · 客服工作台</p>
        <h1>RAG 回复助手</h1>
        <p class="subtitle">连接真实 RAG API，回复始终由客服确认、复制并人工发送。</p>
      </div>
      <div class="health-panel" data-testid="health-status">
        <el-tag :type="healthTagType" effect="light">{{ healthStatusText }}</el-tag>
        <el-button link :loading="healthLoading" @click="refreshHealth">刷新状态</el-button>
      </div>
    </header>

    <el-alert
      v-if="healthError"
      class="status-alert"
      :title="healthError"
      type="warning"
      :closable="false"
      show-icon
    />

    <section class="question-card">
      <label class="section-label" for="customer-question">客户问题</label>
      <el-input
        id="customer-question"
        v-model="customerQuestion"
        data-testid="question-input"
        type="textarea"
        :rows="4"
        maxlength="4000"
        show-word-limit
        placeholder="粘贴或输入客户的问题，例如：这个玩具适合几岁的小朋友？"
        :disabled="loading"
        @keydown.enter.exact.prevent="submitQuestion"
      />
      <div class="question-actions">
        <span class="input-hint">Enter 提交，Shift+Enter 换行</span>
        <el-button
          v-if="loading"
          data-testid="cancel-button"
          type="danger"
          plain
          @click="cancelRequest"
        >
          取消请求
        </el-button>
        <el-button
          data-testid="submit-button"
          type="primary"
          :loading="loading"
          :disabled="!canSubmit"
          @click="submitQuestion"
        >
          生成建议回复
        </el-button>
      </div>
    </section>

    <el-alert
      v-if="requestError"
      data-testid="request-error"
      class="status-alert"
      :title="requestError"
      type="error"
      :closable="false"
      show-icon
    />

    <section v-if="loading" class="loading-card" data-testid="loading-state">
      <div class="loading-dot" />
      <div>
        <strong>RAG 服务正在生成建议</strong>
        <p>请稍候；重复提交已禁用，可随时取消本次请求。</p>
      </div>
    </section>

    <section v-if="result" class="answer-card" data-testid="answer-card">
      <div class="answer-heading">
        <div>
          <p class="section-label">AI 建议回复</p>
          <div class="result-tags">
            <el-tag :type="actionTagType">{{ actionText }}</el-tag>
            <el-tag :type="riskTagType">{{ riskText }}</el-tag>
            <span v-if="result.model" class="latency">模型 {{ result.model }}</span>
            <span v-if="result.latencyMs !== null" class="latency">
              {{ Math.round(result.latencyMs) }} ms
            </span>
          </div>
        </div>
        <el-button data-testid="copy-button" type="primary" plain @click="copyReply">
          {{ copyStatus === 'copied' ? '已复制' : '一键复制' }}
        </el-button>
      </div>

      <el-input
        v-model="replyDraft"
        data-testid="reply-draft"
        class="reply-editor"
        type="textarea"
        :rows="6"
        maxlength="8000"
        show-word-limit
      />

      <el-alert
        v-if="result.warnings.length"
        class="result-alert"
        :title="result.warnings.join('；')"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="result.requiredFields.length"
        class="result-alert"
        :title="`仍需补充：${result.requiredFields.join('、')}`"
        type="info"
        :closable="false"
        show-icon
      />

      <div class="evidence-section">
        <div class="evidence-heading">
          <h2>引用依据</h2>
          <span>{{ result.citations.length }} 条</span>
        </div>
        <div v-if="result.citations.length" class="evidence-list">
          <article
            v-for="(citation, index) in result.citations"
            :key="`${citation.file}-${citation.page}-${index}`"
            class="evidence-item"
            data-testid="citation-item"
          >
            <div class="evidence-meta">
              <strong>{{ citation.file }}</strong>
              <span>{{ citation.page === null ? '页码未提供' : `第 ${citation.page} 页` }}</span>
              <span v-if="citation.chunkId">片段 {{ citation.chunkId }}</span>
              <span v-if="citation.knowledgeVersion">版本 {{ citation.knowledgeVersion }}</span>
            </div>
            <p>{{ citation.summary || 'API 未返回摘要。' }}</p>
          </article>
        </div>
        <el-empty v-else description="A API 本次未返回引用依据" :image-size="64" />
      </div>

      <div class="feedback-section">
        <div>
          <h2>采用结果</h2>
          <p>当前 A API 未发布反馈端点；选择会明确记录在本页，不会冒充远端提交成功。</p>
        </div>
        <div class="feedback-actions">
          <el-button data-testid="direct-accept" @click="recordAdoption('DIRECT_ACCEPT')">
            直接采用
          </el-button>
          <el-button data-testid="edited-accept" @click="recordAdoption('EDITED_ACCEPT')">
            修改后采用
          </el-button>
          <el-button data-testid="reject" @click="recordAdoption('REJECTED')">
            未采用
          </el-button>
        </div>
        <p v-if="adoptionMessage" class="feedback-result" data-testid="adoption-result">
          {{ adoptionMessage }}
        </p>
      </div>
    </section>

    <section v-else-if="!loading" class="empty-card">
      <h2>等待客户问题</h2>
      <p>回答、动作、风险和引用会在真实 API 返回后显示；生产运行没有 Mock 回退。</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ragClient } from '@/api/ragClient'
import { toRagClientError } from '@/api/errorMapper'
import type {
  AdoptionRecord,
  AdoptionType,
  RagAction,
  RagChatResult,
  RagHealth,
  RiskLevel
} from '@/api/ragTypes'

const actionLabels: Record<RagAction, string> = {
  DIRECT_ANSWER: '直接回答',
  CONTROLLED_ANSWER: '受控回答',
  ASK_CLARIFY: '需要追问',
  REQUIRE_LOOKUP: '需要查询',
  TRANSFER_HUMAN: '转人工',
  REFUSE: '拒答'
}

const riskLabels: Record<RiskLevel, string> = {
  LOW: '低风险',
  MEDIUM: '中风险',
  HIGH: '高风险'
}

const adoptionLabels: Record<AdoptionType, string> = {
  DIRECT_ACCEPT: '直接采用',
  EDITED_ACCEPT: '修改后采用',
  REJECTED: '未采用'
}

const customerQuestion = ref('')
const loading = ref(false)
const healthLoading = ref(false)
const health = ref<RagHealth | null>(null)
const healthError = ref('')
const requestError = ref('')
const result = ref<RagChatResult | null>(null)
const replyDraft = ref('')
const copyStatus = ref<'idle' | 'copied'>('idle')
const adoption = ref<AdoptionRecord | null>(null)
let activeController: AbortController | null = null

const canSubmit = computed(() => Boolean(customerQuestion.value.trim()) && !loading.value)

const healthStatusText = computed(() => {
  if (healthLoading.value) return '正在检查 RAG API'
  if (healthError.value) return 'RAG API 不可用'
  if (health.value?.ready) return 'RAG API 已就绪'
  if (health.value) return 'RAG API 初始化中'
  return 'RAG API 状态未知'
})

const healthTagType = computed(() => {
  if (healthError.value) return 'danger'
  if (health.value?.ready) return 'success'
  return 'warning'
})

const actionText = computed(() =>
  result.value?.action ? actionLabels[result.value.action] : '动作未分类'
)

const riskText = computed(() =>
  result.value?.riskLevel ? riskLabels[result.value.riskLevel] : '风险未分类'
)

const actionTagType = computed(() =>
  result.value?.action === 'TRANSFER_HUMAN' || result.value?.action === 'REFUSE'
    ? 'danger'
    : result.value?.action
      ? 'primary'
      : 'info'
)

const riskTagType = computed(() => {
  if (result.value?.riskLevel === 'HIGH') return 'danger'
  if (result.value?.riskLevel === 'MEDIUM') return 'warning'
  if (result.value?.riskLevel === 'LOW') return 'success'
  return 'info'
})

const adoptionMessage = computed(() =>
  adoption.value
    ? `已在本页记录：${adoptionLabels[adoption.value.type]}（反馈 API 待发布）`
    : ''
)

const refreshHealth = async () => {
  healthLoading.value = true
  healthError.value = ''
  try {
    health.value = await ragClient.getHealth()
  } catch (error) {
    health.value = null
    healthError.value = toRagClientError(error).message
  } finally {
    healthLoading.value = false
  }
}

const submitQuestion = async () => {
  const message = customerQuestion.value.trim()
  if (!message || loading.value) return

  activeController?.abort()
  activeController = new AbortController()
  const controller = activeController
  loading.value = true
  requestError.value = ''
  result.value = null
  replyDraft.value = ''
  adoption.value = null
  copyStatus.value = 'idle'

  try {
    const response = await ragClient.chat({ message }, controller.signal)
    result.value = response
    replyDraft.value = response.answer
  } catch (error) {
    requestError.value = controller.signal.aborted
      ? '请求已取消，可重新提交'
      : toRagClientError(error).message
  } finally {
    if (activeController === controller) activeController = null
    loading.value = false
  }
}

const cancelRequest = () => {
  activeController?.abort()
}

const copyReply = async () => {
  const text = replyDraft.value.trim()
  if (!text) {
    ElMessage.warning('没有可复制的回复')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    copyStatus.value = 'copied'
    ElMessage.success('建议回复已复制，请由客服人工发送')
  } catch {
    copyStatus.value = 'idle'
    ElMessage.error('复制失败，请手动选择回复文本')
  }
}

const recordAdoption = (type: AdoptionType) => {
  if (!result.value) return
  const originalAnswer = result.value.answer
  const finalAnswer = type === 'REJECTED'
    ? ''
    : type === 'DIRECT_ACCEPT'
      ? originalAnswer
      : replyDraft.value.trim()

  if (type === 'EDITED_ACCEPT' && !finalAnswer) {
    ElMessage.warning('修改后的回复不能为空')
    return
  }

  adoption.value = {
    requestId: result.value.requestId,
    type,
    originalAnswer,
    finalAnswer
  }
}

onMounted(() => {
  void refreshHealth()
})

onBeforeUnmount(() => {
  activeController?.abort()
})
</script>

<style scoped>
.workspace-shell {
  width: min(1040px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 56px;
  color: #172033;
}

.workspace-header,
.answer-heading,
.question-actions,
.evidence-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.workspace-header {
  margin-bottom: 22px;
}

.eyebrow,
.section-label {
  margin: 0 0 6px;
  color: #3157c8;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 8px;
  font-size: clamp(28px, 4vw, 42px);
}

h2 {
  margin-bottom: 8px;
  font-size: 18px;
}

.subtitle,
.input-hint,
.latency,
.feedback-section p,
.empty-card p,
.loading-card p {
  color: #697386;
}

.subtitle,
.loading-card p,
.feedback-section p,
.empty-card p {
  margin-bottom: 0;
}

.health-panel,
.result-tags,
.feedback-actions,
.evidence-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.question-card,
.answer-card,
.empty-card,
.loading-card {
  border: 1px solid #dce3f0;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 10px 30px rgb(43 62 101 / 8%);
}

.question-card,
.answer-card {
  padding: 24px;
}

.question-actions {
  margin-top: 14px;
}

.status-alert,
.answer-card,
.empty-card,
.loading-card {
  margin-top: 18px;
}

.loading-card,
.empty-card {
  padding: 28px;
}

.loading-card {
  display: flex;
  align-items: center;
  gap: 16px;
}

.loading-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #3157c8;
  box-shadow: 0 0 0 8px rgb(49 87 200 / 12%);
  animation: pulse 1.2s infinite ease-in-out;
}

.reply-editor {
  margin-top: 18px;
}

.result-alert {
  margin-top: 12px;
}

.evidence-section,
.feedback-section {
  margin-top: 26px;
  padding-top: 22px;
  border-top: 1px solid #e7ebf2;
}

.evidence-heading span {
  color: #697386;
  font-size: 13px;
}

.evidence-list {
  display: grid;
  gap: 12px;
}

.evidence-item {
  padding: 16px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #f8fafc;
}

.evidence-item p {
  margin: 10px 0 0;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
}

.evidence-meta span {
  color: #697386;
  font-size: 12px;
}

.feedback-actions {
  margin-top: 14px;
}

.feedback-result {
  margin-top: 12px;
  color: #246b3f !important;
  font-weight: 600;
}

@keyframes pulse {
  0%, 100% { opacity: 0.45; transform: scale(0.88); }
  50% { opacity: 1; transform: scale(1); }
}

@media (max-width: 700px) {
  .workspace-shell {
    width: min(100% - 20px, 1040px);
    padding-top: 18px;
  }

  .workspace-header,
  .answer-heading,
  .question-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .question-actions .el-button,
  .answer-heading .el-button {
    width: 100%;
  }
}
</style>
