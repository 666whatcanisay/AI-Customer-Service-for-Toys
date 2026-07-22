<template>
  <main class="workspace-shell">
    <header class="workspace-header">
      <div>
        <p class="eyebrow">木木小栈 · 客服工作台</p>
        <h1>商品范围问答助手</h1>
        <p class="subtitle">手动确认店铺、商品和 SKU 后，再向真实 RAG API 请求一条建议。</p>
      </div>
      <div class="health-panel">
        <div data-testid="rag-health-status">
          <el-tag :type="ragHealthTagType" effect="light">{{ ragHealthStatusText }}</el-tag>
          <el-button link :loading="ragHealthLoading" @click="refreshRagHealth">刷新</el-button>
        </div>
        <div data-testid="platform-health-status">
          <el-tag :type="platformHealthTagType" effect="light">
            {{ platformHealthStatusText }}
          </el-tag>
          <el-button link :loading="platformHealthLoading" @click="refreshPlatform">
            刷新
          </el-button>
        </div>
      </div>
    </header>

    <el-alert
      data-testid="safety-notice"
      class="safety-alert"
      title="测试数据 · 仅供建议 · 禁止自动发送 · 不可用于真实客户"
      description="本页面用于内部联调试用。客服必须核对商品范围、回复内容和引用，并且只能人工复制；系统不会向电商平台发送消息。"
      type="error"
      :closable="false"
      show-icon
    />

    <el-alert
      v-if="ragHealthError"
      class="status-alert"
      :title="`A 问答服务状态异常：${ragHealthError}`"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="platformError"
      data-testid="platform-error"
      class="status-alert"
      :title="`C 目录服务异常：${platformError}`"
      type="error"
      :closable="false"
      show-icon
    />

    <section class="context-card">
      <div class="section-heading">
        <div>
          <p class="section-label">第一步 · 选择测试范围</p>
          <h2>店铺、商品与可选 SKU</h2>
        </div>
        <el-tag type="warning" effect="dark">测试数据</el-tag>
      </div>

      <div class="context-grid">
        <label>
          <span>店铺</span>
          <el-select
            v-model="selectedStoreKey"
            data-testid="store-select"
            placeholder="先选择店铺"
            :loading="storesLoading"
            :disabled="loading"
            filterable
            @change="handleStoreChange"
          >
            <el-option
              v-for="store in stores"
              :key="storeKey(store)"
              :label="storeOptionLabel(store)"
              :value="storeKey(store)"
            />
          </el-select>
        </label>

        <label>
          <span>商品</span>
          <el-select
            v-model="selectedProductId"
            data-testid="product-select"
            placeholder="选择店铺后加载商品"
            :loading="productsLoading"
            :disabled="!selectedStore || loading"
            filterable
            @change="handleProductChange"
          >
            <el-option
              v-for="product in products"
              :key="product.productId"
              :label="productOptionLabel(product)"
              :value="product.productId"
              :disabled="!product.publishable"
            />
          </el-select>
        </label>

        <label>
          <span>SKU（可选）</span>
          <el-select
            v-model="selectedSkuId"
            data-testid="sku-select"
            placeholder="不确定款式时可以不选"
            :loading="skusLoading"
            :disabled="!selectedProduct || loading"
            clearable
            filterable
            @change="clearAnswer"
          >
            <el-option
              v-for="sku in skus"
              :key="sku.skuId"
              :label="skuOptionLabel(sku)"
              :value="sku.skuId"
              :disabled="!sku.publishable"
            />
          </el-select>
        </label>
      </div>

      <div v-if="selectedStore && selectedProduct" class="context-summary" data-testid="context-summary">
        <strong>本次请求范围</strong>
        <span>tenant_id={{ selectedStore.tenantId }}</span>
        <span>platform={{ selectedStore.platform }}</span>
        <span>store_code={{ selectedStore.storeCode }}</span>
        <span>product_id={{ selectedProduct.productId }}</span>
        <span>sku_id={{ selectedSku?.skuId ?? '未选择' }}</span>
      </div>
      <p v-else class="context-hint">店铺和商品为必选；SKU 可以留空，由 A 返回追问动作，不在前端猜测款式。</p>
    </section>

    <section class="question-card">
      <p class="section-label">第二步 · 输入问题</p>
      <label class="question-label" for="customer-question">客户问题</label>
      <el-input
        id="customer-question"
        v-model="customerQuestion"
        data-testid="question-input"
        type="textarea"
        :rows="4"
        maxlength="4000"
        show-word-limit
        placeholder="仅输入测试问题，例如：这个款式适合几岁的小朋友？"
        :disabled="loading"
        @keydown.enter.exact.prevent="submitQuestion"
      />
      <div class="question-actions">
        <span class="input-hint">店铺和商品必选；Enter 提交，Shift+Enter 换行</span>
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
        <strong>A 问答服务正在生成建议</strong>
        <p>重复提交已禁用，可随时取消。系统不会自动发送回复。</p>
      </div>
    </section>

    <section v-if="result" class="answer-card" data-testid="answer-card">
      <div class="answer-heading">
        <div>
          <p class="section-label">第三步 · 核对和人工处理</p>
          <h2>AI 建议回复</h2>
          <div class="result-tags">
            <el-tag :type="actionTagType" data-testid="action-tag">{{ actionText }}</el-tag>
            <el-tag :type="riskTagType" data-testid="risk-tag">{{ riskText }}</el-tag>
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

      <el-alert
        class="result-alert"
        title="仅供建议，禁止自动发送；请客服核对后人工复制。"
        type="warning"
        :closable="false"
        show-icon
      />

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
              <span v-if="citation.productId">商品 {{ citation.productId }}</span>
              <span v-if="citation.skuId">SKU {{ citation.skuId }}</span>
              <span v-if="citation.sourceIds.length">来源 ID {{ citation.sourceIds.join('、') }}</span>
            </div>
            <p>{{ citation.summary || 'API 未返回摘要。' }}</p>
          </article>
        </div>
        <el-empty v-else description="A API 本次未返回引用依据" :image-size="64" />
      </div>

      <div class="feedback-section">
        <div>
          <h2>采用结果</h2>
          <p>反馈端点尚未发布；选择只记录在本页，不会冒充远端提交成功。</p>
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
      <h2>等待完整测试上下文</h2>
      <p>选择店铺和商品后才能请求；SKU 留空时保留 A 的 ASK_CLARIFY，不自动猜测。</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ragClient } from '@/api/ragClient'
import { platformClient } from '@/api/platformClient'
import {
  PlatformClientError,
  toPlatformClientError,
  toRagClientError
} from '@/api/errorMapper'
import type {
  CatalogProduct,
  CatalogSku,
  CatalogStore,
  PlatformHealth
} from '@/api/platformTypes'
import type {
  AdoptionRecord,
  AdoptionType,
  RagAction,
  RagChatContext,
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

const platformLabels: Record<string, string> = {
  pdd: '拼多多',
  taobao: '淘宝',
  douyin: '抖音',
  jd: '京东',
  offline: '线下',
  other: '其他'
}

const customerQuestion = ref('')
const selectedStoreKey = ref('')
const selectedProductId = ref('')
const selectedSkuId = ref('')
const stores = ref<CatalogStore[]>([])
const products = ref<CatalogProduct[]>([])
const skus = ref<CatalogSku[]>([])
const loading = ref(false)
const storesLoading = ref(false)
const productsLoading = ref(false)
const skusLoading = ref(false)
const ragHealthLoading = ref(false)
const platformHealthLoading = ref(false)
const ragHealth = ref<RagHealth | null>(null)
const platformHealth = ref<PlatformHealth | null>(null)
const ragHealthError = ref('')
const platformError = ref('')
const requestError = ref('')
const result = ref<RagChatResult | null>(null)
const replyDraft = ref('')
const copyStatus = ref<'idle' | 'copied'>('idle')
const adoption = ref<AdoptionRecord | null>(null)
let activeRagController: AbortController | null = null
let activeCatalogController: AbortController | null = null

const storeKey = (store: CatalogStore) =>
  `${store.tenantId}::${store.platform}::${store.storeCode}`

const selectedStore = computed(() =>
  stores.value.find((store) => storeKey(store) === selectedStoreKey.value) ?? null
)
const selectedProduct = computed(() =>
  products.value.find((product) => product.productId === selectedProductId.value) ?? null
)
const selectedSku = computed(() =>
  skus.value.find((sku) => sku.skuId === selectedSkuId.value) ?? null
)

const canSubmit = computed(() =>
  Boolean(
    customerQuestion.value.trim() &&
    selectedStore.value &&
    selectedProduct.value &&
    !loading.value
  )
)

const platformName = (platform: string) => platformLabels[platform] ?? platform
const storeOptionLabel = (store: CatalogStore) =>
  `${platformName(store.platform)} → ${store.name}${store.testDataMode ? '（测试数据）' : ''}`
const productOptionLabel = (product: CatalogProduct) =>
  `${product.displayName}${product.publishable ? '' : '（待发布）'}`
const skuOptionLabel = (sku: CatalogSku) =>
  `${sku.displayName}${sku.publishable ? '' : '（待发布）'}`

const ragHealthStatusText = computed(() => {
  if (ragHealthLoading.value) return '正在检查 A 问答服务'
  if (ragHealthError.value) return 'A 问答服务不可用'
  if (ragHealth.value?.ready) return 'A 问答服务已就绪'
  if (ragHealth.value) return 'A 问答服务初始化中'
  return 'A 问答服务状态未知'
})

const platformHealthStatusText = computed(() => {
  if (platformHealthLoading.value || storesLoading.value) return '正在检查 C 目录服务'
  if (platformError.value) return 'C 目录服务不可用'
  if (platformHealth.value?.status === 'ok' && stores.value.length) return 'C 目录服务已就绪'
  if (platformHealth.value?.status === 'ok') return 'C 服务在线，目录待发布'
  return 'C 目录服务状态未知'
})

const ragHealthTagType = computed(() => {
  if (ragHealthError.value) return 'danger'
  if (ragHealth.value?.ready) return 'success'
  return 'warning'
})

const platformHealthTagType = computed(() => {
  if (platformError.value) return 'danger'
  if (platformHealth.value?.status === 'ok' && stores.value.length) return 'success'
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
    : result.value?.action === 'ASK_CLARIFY' || result.value?.action === 'REQUIRE_LOOKUP'
      ? 'warning'
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

const clearAnswer = () => {
  result.value = null
  replyDraft.value = ''
  adoption.value = null
  copyStatus.value = 'idle'
  requestError.value = ''
}

const refreshRagHealth = async () => {
  ragHealthLoading.value = true
  ragHealthError.value = ''
  try {
    ragHealth.value = await ragClient.getHealth()
  } catch (error) {
    ragHealth.value = null
    ragHealthError.value = toRagClientError(error).message
  } finally {
    ragHealthLoading.value = false
  }
}

const loadStores = async () => {
  activeCatalogController?.abort()
  const controller = new AbortController()
  activeCatalogController = controller
  storesLoading.value = true
  platformError.value = ''
  try {
    const nextStores = await platformClient.listStores(controller.signal)
    const unsafeStore = nextStores.find((store) =>
      !store.trialEnabled ||
      !store.testDataMode ||
      store.productionUsable ||
      store.responseMode !== 'SUGGESTION_ONLY' ||
      store.allowAutoSend
    )
    if (unsafeStore) {
      throw new PlatformClientError(
        'contract',
        `店铺 ${unsafeStore.storeCode} 不符合 B-T03 测试/建议/禁止自动发送边界`
      )
    }
    stores.value = nextStores
  } catch (error) {
    if (!controller.signal.aborted) {
      stores.value = []
      platformError.value = toPlatformClientError(error).message
    }
  } finally {
    if (activeCatalogController === controller) activeCatalogController = null
    storesLoading.value = false
  }
}

const refreshPlatform = async () => {
  platformHealthLoading.value = true
  platformError.value = ''
  try {
    platformHealth.value = await platformClient.getHealth()
  } catch (error) {
    platformHealth.value = null
    platformError.value = toPlatformClientError(error).message
  } finally {
    platformHealthLoading.value = false
  }
  await loadStores()
}

const handleStoreChange = async () => {
  activeCatalogController?.abort()
  products.value = []
  skus.value = []
  selectedProductId.value = ''
  selectedSkuId.value = ''
  clearAnswer()
  if (!selectedStore.value) return

  const controller = new AbortController()
  activeCatalogController = controller
  productsLoading.value = true
  platformError.value = ''
  try {
    const store = selectedStore.value
    const nextProducts = await platformClient.listProducts(store, controller.signal)
    if (nextProducts.some((product) =>
      product.platform !== store.platform || product.storeCode !== store.storeCode
    )) {
      throw new PlatformClientError('contract', 'C 商品列表与所选店铺范围不一致')
    }
    products.value = nextProducts
  } catch (error) {
    if (!controller.signal.aborted) {
      platformError.value = toPlatformClientError(error).message
    }
  } finally {
    if (activeCatalogController === controller) activeCatalogController = null
    productsLoading.value = false
  }
}

const handleProductChange = async () => {
  activeCatalogController?.abort()
  skus.value = []
  selectedSkuId.value = ''
  clearAnswer()
  if (!selectedStore.value || !selectedProduct.value) return

  const controller = new AbortController()
  activeCatalogController = controller
  skusLoading.value = true
  platformError.value = ''
  try {
    const store = selectedStore.value
    const product = selectedProduct.value
    const nextSkus = await platformClient.listSkus(
      store,
      product,
      controller.signal
    )
    if (nextSkus.some((sku) => sku.productId !== product.productId)) {
      throw new PlatformClientError('contract', 'C SKU 列表与所选商品范围不一致')
    }
    skus.value = nextSkus
  } catch (error) {
    if (!controller.signal.aborted) {
      platformError.value = toPlatformClientError(error).message
    }
  } finally {
    if (activeCatalogController === controller) activeCatalogController = null
    skusLoading.value = false
  }
}

const submitQuestion = async () => {
  const message = customerQuestion.value.trim()
  const store = selectedStore.value
  const product = selectedProduct.value
  if (!message || !store || !product || loading.value) return

  activeRagController?.abort()
  activeRagController = new AbortController()
  const controller = activeRagController
  loading.value = true
  requestError.value = ''
  clearAnswer()

  const expectedContext: RagChatContext = {
    tenant_id: store.tenantId,
    platform: store.platform,
    store_code: store.storeCode,
    product_id: product.productId,
    sku_id: selectedSku.value?.skuId ?? null
  }

  try {
    const response = await ragClient.chat(
      {
        question: message,
        context: expectedContext
      },
      controller.signal
    )
    const contextMatches = Object.entries(expectedContext).every(
      ([key, value]) => response.context[key as keyof RagChatContext] === value
    )
    if (!contextMatches) {
      requestError.value = 'A 问答服务返回的 context 与所选店铺、商品或 SKU 不一致，已停止展示答案'
      return
    }
    result.value = response
    replyDraft.value = response.answer
  } catch (error) {
    requestError.value = controller.signal.aborted
      ? 'A 问答请求已取消，可重新提交'
      : `A 问答服务失败：${toRagClientError(error).message}`
  } finally {
    if (activeRagController === controller) activeRagController = null
    loading.value = false
  }
}

const cancelRequest = () => {
  activeRagController?.abort()
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
    ElMessage.success('建议回复已复制，请由客服核对并人工发送')
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
  void refreshRagHealth()
  void refreshPlatform()
})

onBeforeUnmount(() => {
  activeRagController?.abort()
  activeCatalogController?.abort()
})
</script>

<style scoped>
.workspace-shell {
  width: min(1120px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 56px;
  color: #172033;
}

.workspace-header,
.answer-heading,
.question-actions,
.evidence-heading,
.section-heading {
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
.loading-card p,
.context-hint {
  color: #697386;
}

.subtitle,
.loading-card p,
.feedback-section p,
.empty-card p,
.context-hint {
  margin-bottom: 0;
}

.health-panel {
  display: grid;
  gap: 8px;
  min-width: 250px;
}

.health-panel > div,
.result-tags,
.feedback-actions,
.evidence-meta,
.context-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.safety-alert {
  border: 2px solid #d93025;
}

.context-card,
.question-card,
.answer-card,
.empty-card,
.loading-card {
  border: 1px solid #dce3f0;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 10px 30px rgb(43 62 101 / 8%);
}

.context-card,
.question-card,
.answer-card {
  padding: 24px;
}

.context-card,
.question-card,
.status-alert,
.answer-card,
.empty-card,
.loading-card {
  margin-top: 18px;
}

.context-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.context-grid label {
  display: grid;
  gap: 8px;
  font-weight: 700;
}

.context-grid .el-select {
  width: 100%;
}

.context-summary {
  margin-top: 18px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #eef4ff;
  color: #2b416f;
  font-size: 13px;
}

.context-summary span {
  padding-left: 8px;
  border-left: 1px solid #b8c8eb;
}

.context-hint {
  margin-top: 14px;
}

.question-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 700;
}

.question-actions {
  margin-top: 14px;
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

.reply-editor,
.result-alert {
  margin-top: 14px;
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

@media (max-width: 820px) {
  .context-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .workspace-shell {
    width: min(100% - 20px, 1120px);
    padding-top: 18px;
  }

  .workspace-header,
  .answer-heading,
  .question-actions,
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .health-panel,
  .question-actions .el-button,
  .answer-heading .el-button {
    width: 100%;
  }
}
</style>
