<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  enableProductsForCustomerService,
  getProductKnowledgeOverview,
  listProductKnowledgeProducts,
  publishProductAiKnowledge,
  type AiKnowledgePublicationStatus,
  type ProductKnowledgeListItem,
  type ProductKnowledgeOverview,
} from '../api/client'
import { displayStatus } from '../presentation'

const overview = ref<ProductKnowledgeOverview | null>(null)
const products = ref<ProductKnowledgeListItem[]>([])
const activeStoreCode = ref('')
const loading = ref(true)
const productLoading = ref(false)
const error = ref('')
const operator = ref('')
const selectedProductIds = ref<string[]>([])
const pendingOnly = ref(false)
const actionBusy = ref(false)
const actionMessage = ref('')
const actionError = ref('')

const visibleProducts = computed(() => pendingOnly.value
  ? products.value.filter((product) => product.data_status === 'APPROVED' && product.customer_service_status === 'DISABLED')
  : products.value)

function isPendingCustomerEnable(product: ProductKnowledgeListItem): boolean {
  return product.data_status === 'APPROVED'
    && product.customer_service_status === 'DISABLED'
    && Boolean(productId(product))
}

const pendingProductCount = computed(() => products.value.filter(isPendingCustomerEnable).length)
const visiblePendingProductIds = computed(() => visibleProducts.value
  .filter(isPendingCustomerEnable)
  .map(productId))
const allVisiblePendingSelected = computed({
  get: () => visiblePendingProductIds.value.length > 0
    && visiblePendingProductIds.value.every((id) => selectedProductIds.value.includes(id)),
  set: (selected: boolean) => {
    const visibleIds = new Set(visiblePendingProductIds.value)
    selectedProductIds.value = selected
      ? [...new Set([...selectedProductIds.value, ...visiblePendingProductIds.value])]
      : selectedProductIds.value.filter((id) => !visibleIds.has(id))
  },
})

function productId(product: ProductKnowledgeListItem): string {
  return product.technical_details.product_id || ''
}

function aiKnowledgeLabel(status: AiKnowledgePublicationStatus): string {
  return {
    NOT_GENERATED: '未生成',
    GENERATING: '生成中',
    PUBLISHED: '已发布',
    SYNC_FAILED: '同步失败',
    NEED_RESYNC: '待重新同步',
  }[status]
}

function canPublish(product: ProductKnowledgeListItem): boolean {
  return product.data_status === 'APPROVED'
    && product.data_source !== 'UNKNOWN'
    && product.ai_knowledge.status !== 'GENERATING'
    && product.ai_knowledge.status !== 'PUBLISHED'
}

const metrics = [
  { key: 'store_count', label: '店铺数量' },
  { key: 'product_count', label: '商品数量' },
  { key: 'ai_usable_product_count', label: 'AI 可用商品' },
  { key: 'gap_count', label: '资料缺口' },
  { key: 'pending_review_count', label: '待审核资料' },
] as const

function metricValue(key: typeof metrics[number]['key']): string {
  const value = overview.value?.stats[key]
  return typeof value === 'number' ? String(value) : '暂无统计'
}

async function selectStore(storeCode: string): Promise<void> {
  if (productLoading.value) return
  activeStoreCode.value = storeCode
  selectedProductIds.value = []
  productLoading.value = true
  error.value = ''
  try {
    products.value = (await listProductKnowledgeProducts(storeCode)).items
  } catch (reason: unknown) {
    products.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    productLoading.value = false
  }
}

async function batchEnable(): Promise<void> {
  if (actionBusy.value) return
  if (!operator.value.trim()) {
    actionError.value = '请先填写本次操作人。'
    return
  }
  if (!selectedProductIds.value.length) {
    actionError.value = '请先选择至少一个“已审核、客服未启用”的商品。'
    return
  }
  if (!window.confirm(`确认启用当前选择的 ${selectedProductIds.value.length} 个商品供客服使用？`)) {
    return
  }
  actionBusy.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const result = await enableProductsForCustomerService(
      selectedProductIds.value,
      operator.value.trim(),
      `batch-enable-${crypto.randomUUID()}`,
    )
    actionMessage.value = `批量启用完成：成功 ${result.changed_count}，已是目标状态 ${result.unchanged_count}，失败 ${result.failed_count}。每个成功变化均已生成 activation receipt。客服工作台刷新目录后即可使用。`
    await selectStore(activeStoreCode.value)
  } catch (reason: unknown) {
    actionError.value = apiErrorMessage(reason)
  } finally {
    actionBusy.value = false
  }
}

async function publishKnowledge(product: ProductKnowledgeListItem): Promise<void> {
  const id = productId(product)
  if (!id || actionBusy.value) return
  if (!operator.value.trim()) {
    actionError.value = '请先填写本次操作人。'
    return
  }
  actionBusy.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const result = await publishProductAiKnowledge(
      id,
      operator.value.trim(),
      `publish-${id}-${crypto.randomUUID()}`,
    )
    actionMessage.value = result.publication_receipt
      ? `AI 知识已增量发布，收据：${result.publication_receipt.publication_receipt_id}`
      : '当前审核版本已发布，无需重复生成向量。'
    await selectStore(activeStoreCode.value)
  } catch (reason: unknown) {
    actionError.value = apiErrorMessage(reason)
  } finally {
    actionBusy.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    overview.value = await getProductKnowledgeOverview()
    const firstStore = overview.value.stores[0]?.technical_details.store_code
    if (firstStore) await selectStore(firstStore)
  } catch (reason: unknown) {
    overview.value = null
    products.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI 商品知识运营</p>
        <h1>商品知识中心</h1>
        <p>按店铺、商品和 SKU 查看 AI 已具备的回答依据、当前缺口和下一步补充重点。</p>
      </div>
      <RouterLink class="button" to="/knowledge-materials">补充并审核资料</RouterLink>
    </div>

    <p v-if="loading" class="notice" role="status">正在汇总商品知识状态…</p>
    <p v-else-if="error && !overview" class="notice error" role="alert">暂时无法读取商品知识。{{ error }}</p>

    <template v-else-if="overview">
      <section class="metric-grid" aria-label="商品知识统计">
        <article v-for="metric in metrics" :key="metric.key" class="metric-card">
          <span>{{ metric.label }}</span>
          <strong :class="{ empty: metricValue(metric.key) === '暂无统计' }">{{ metricValue(metric.key) }}</strong>
        </article>
      </section>

      <section v-if="!overview.has_data" class="card empty-state">
        <h2>暂无商品知识数据</h2>
        <p>请先按现有运营流程导入并审核可核对的商品资料。页面不会生成示例统计或虚构商品。</p>
        <RouterLink class="button secondary" to="/import-center">查看中文资料模板</RouterLink>
      </section>

      <template v-else>
        <section class="card navigator">
          <div class="section-heading">
            <div>
              <p class="eyebrow">第 1 级</p>
              <h2>选择店铺</h2>
            </div>
            <span>默认展示完整业务名称</span>
          </div>
          <div class="store-tabs">
            <button
              v-for="store in overview.stores"
              :key="store.technical_details.store_code || store.store_name"
              type="button"
              :class="['store-tab', { active: activeStoreCode === store.technical_details.store_code }]"
              @click="selectStore(store.technical_details.store_code || '')"
            >
              <strong>{{ store.store_name }}</strong>
              <small>{{ store.platform_name }} · {{ store.product_count }} 个商品 · {{ store.gap_count }} 个缺口 · {{ store.pending_review_count }} 项待审核</small>
            </button>
          </div>
        </section>

        <section class="card activation-toolbar" aria-label="商品上线操作">
          <div>
            <p class="eyebrow">商品上线</p>
            <h2>资料审核 → 客服可用 → AI 可用</h2>
            <p>三个状态相互独立。启用客服不会自动发布 AI 知识；发布 AI 知识也不会自动启用客服。</p>
          </div>
          <label>本次操作人<input v-model.trim="operator" maxlength="128" placeholder="填写姓名或运营账号" data-testid="knowledge-activation-operator"></label>
          <div class="toolbar-actions">
            <span class="pending-count" data-testid="pending-enable-count">当前待启用：{{ pendingProductCount }} 个</span>
            <label class="check-label"><input v-model="pendingOnly" type="checkbox">只看待客服启用</label>
            <label class="check-label">
              <input
                v-model="allVisiblePendingSelected"
                type="checkbox"
                :disabled="visiblePendingProductIds.length === 0"
                data-testid="select-all-filtered-products"
              >
              全选当前筛选结果（{{ visiblePendingProductIds.length }}）
            </label>
            <button class="button" type="button" :disabled="actionBusy || selectedProductIds.length === 0" data-testid="batch-enable-products" @click="batchEnable">批量启用客服（{{ selectedProductIds.length }}）</button>
          </div>
          <p v-if="actionMessage" class="notice success" role="status">{{ actionMessage }}</p>
          <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>
        </section>

        <section class="catalog-section">
          <div class="section-heading">
            <div>
              <p class="eyebrow">第 2—3 级</p>
              <h2>商品与 SKU</h2>
            </div>
            <span>选择商品查看完整知识详情</span>
          </div>
          <p v-if="productLoading" class="notice" role="status">正在读取该店铺商品…</p>
          <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
          <p v-else-if="visibleProducts.length === 0" class="notice">{{ pendingOnly ? '该店铺暂无待客服启用的已审核商品。' : '该店铺暂无已导入商品。' }}</p>
          <div v-else class="product-grid">
            <article v-for="product in visibleProducts" :key="product.technical_details.product_id || product.product_name" class="product-card">
              <div class="product-heading">
                <div>
                  <label v-if="product.data_status === 'APPROVED' && product.customer_service_status === 'DISABLED' && productId(product)" class="select-product">
                    <input v-model="selectedProductIds" type="checkbox" :value="productId(product)" :data-testid="`select-product-${productId(product)}`">
                    选择批量启用
                  </label>
                  <small>{{ product.store_name }} → 商品</small>
                  <h3>{{ product.product_name }}</h3>
                </div>
                <div class="status-pair">
                  <span class="state-pill data">资料：{{ displayStatus(product.data_status) }}</span>
                  <span :class="['state-pill', product.ai_status.toLowerCase()]">资料覆盖：{{ displayStatus(product.ai_status) }}</span>
                  <span class="state-pill data">客服：{{ product.customer_service_status === 'ENABLED' ? '已启用' : '已禁用' }}</span>
                  <span :class="['state-pill', `publication-${product.ai_knowledge.status.toLowerCase()}`]">AI知识：{{ aiKnowledgeLabel(product.ai_knowledge.status) }}</span>
                </div>
              </div>
              <p class="summary">{{ product.product_summary || '当前资料未提供商品简介。' }}</p>
              <div>
                <strong class="label">核心卖点</strong>
                <div v-if="product.core_selling_points.length" class="tag-row">
                  <span v-for="point in product.core_selling_points" :key="point" class="tag">{{ point }}</span>
                </div>
                <p v-else class="missing-text">尚未补充</p>
              </div>
              <dl class="fact-grid">
                <div><dt>适用年龄</dt><dd>{{ product.applicable_age || '当前资料未提供' }}</dd></div>
                <div><dt>材质安全</dt><dd>{{ product.material_safety || '当前资料未提供' }}</dd></div>
                <div><dt>包装内容</dt><dd>{{ product.package_contents || '当前资料未提供' }}</dd></div>
                <div><dt>FAQ</dt><dd>{{ product.faq_count }} 条</dd></div>
              </dl>
              <div class="coverage-row">
                <div><strong>{{ product.coverage_percent }}%</strong><span>AI 核心知识覆盖度</span></div>
                <div class="progress"><i :style="{ width: `${product.coverage_percent}%` }"></i></div>
              </div>
              <div>
                <strong class="label">SKU</strong>
                <div v-if="product.sku_names.length" class="sku-row">
                  <span v-for="sku in product.sku_names" :key="sku">{{ product.product_name }} → {{ sku }}</span>
                </div>
                <p v-else class="missing-text">暂无 SKU</p>
              </div>
              <div class="knowledge-summary">
                <span>可回答 {{ product.answerable_topics.length }} 项</span>
                <span class="warning">缺失 {{ product.missing_topics.length }} 项</span>
                <span>RAG chunks {{ product.ai_knowledge.chunk_count }}</span>
              </div>
              <div class="card-actions">
                <button v-if="canPublish(product)" class="button" type="button" :disabled="actionBusy" :data-testid="`publish-product-${productId(product)}`" @click="publishKnowledge(product)">{{ product.ai_knowledge.status === 'NEED_RESYNC' ? '重新同步AI知识' : '同步AI知识' }}</button>
                <span v-else-if="product.ai_knowledge.status === 'PUBLISHED'" class="published-note">AI 知识已发布</span>
                <span v-else-if="product.data_status !== 'APPROVED'" class="pending-note">资料审核通过后才能发布 AI 知识</span>
              </div>
              <RouterLink
                v-if="product.technical_details.product_id"
                class="button secondary"
                :to="`/knowledge-center/products/${encodeURIComponent(product.technical_details.product_id)}`"
              >查看 AI 知识详情</RouterLink>
            </article>
          </div>
        </section>

        <p class="notice boundary">{{ overview.boundary_note }}资料不完整时仍可提供有依据的基础回答；缺失信息必须提示人工确认。</p>
      </template>
    </template>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 20px; }
.metric-card { display: grid; gap: 7px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 13px; background: #fff; }
.metric-card span { color: #617087; font-size: 13px; }.metric-card strong { color: #172554; font-size: 27px; }.metric-card strong.empty { font-size: 16px; color: #8090a5; }
.empty-state { text-align: center; }.empty-state h2 { color: #172554; }.empty-state p { color: #617087; }
.navigator { margin-bottom: 22px; }.section-heading, .product-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }.section-heading h2, .product-heading h3 { margin: 0; color: #172554; }.section-heading > span { color: #718096; font-size: 13px; }
.activation-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) 260px auto; gap: 16px; align-items: end; margin-bottom: 22px; }.activation-toolbar h2 { margin: 0; color: #172554; }.activation-toolbar p { margin-bottom: 0; color: #617087; }.activation-toolbar label { display: grid; gap: 6px; color: #526279; font-size: 13px; }.activation-toolbar input { min-height: 39px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }.toolbar-actions { display: grid; gap: 8px; }.toolbar-actions .check-label { display: flex; align-items: center; gap: 7px; }.toolbar-actions .check-label input, .select-product input { min-height: auto; }.pending-count { color: #334965; font-size: 13px; font-weight: 700; }.activation-toolbar .notice { grid-column: 1 / -1; margin: 0; }
.store-tabs { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }.store-tab { display: grid; gap: 5px; min-width: 240px; padding: 13px 15px; border: 1px solid #d7e1ee; border-radius: 10px; color: #25466f; background: #fff; text-align: left; cursor: pointer; }.store-tab.active { border-color: #3973c4; box-shadow: inset 0 0 0 1px #3973c4; background: #f4f8ff; }.store-tab small { color: #617087; }
.catalog-section { margin-top: 8px; }.product-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }.product-card { display: grid; gap: 15px; padding: 20px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }.product-heading small { color: #617087; }.product-heading h3 { margin-top: 5px; font-size: 18px; }.state-pill { padding: 5px 9px; border-radius: 999px; font-size: 12px; white-space: nowrap; background: #e7f5ec; color: #217447; }.state-pill.basic_available { background: #eaf2ff; color: #285493; }.state-pill.needs_completion { background: #fff1df; color: #9a5c0d; }
.summary { margin: 0; color: #526279; line-height: 1.65; }.label { display: block; margin-bottom: 8px; color: #334965; font-size: 13px; }.tag-row, .sku-row { display: flex; flex-wrap: wrap; gap: 7px; }.tag, .sku-row span { padding: 5px 8px; border-radius: 7px; background: #f1f5fa; color: #425b78; font-size: 12px; }.missing-text { margin: 0; color: #a56a1e; font-size: 13px; }.status-pair { display: grid; justify-items: end; gap: 6px; }.select-product { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; color: #285493; font-size: 12px; }.state-pill.data { color: #365174; background: #edf2f8; }.state-pill.partially_available { color: #285493; background: #eaf2ff; }.state-pill.missing_knowledge, .state-pill.unconfirmed, .state-pill.publication-not_generated, .state-pill.publication-need_resync { color: #9a5c0d; background: #fff1df; }.state-pill.publication-published { color: #217447; background: #e7f5ec; }.state-pill.publication-sync_failed { color: #a23d3d; background: #fff0f0; }.state-pill.publication-generating { color: #285493; background: #eaf2ff; }.fact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 0; }.fact-grid div { padding: 10px; border-radius: 8px; background: #f7f9fc; }.fact-grid dt { color: #617087; font-size: 11px; }.fact-grid dd { margin: 4px 0 0; color: #334965; font-size: 13px; line-height: 1.45; }.card-actions { display: flex; align-items: center; gap: 10px; }.published-note { color: #217447; font-size: 13px; }.pending-note { color: #9a5c0d; font-size: 13px; }
.coverage-row { display: grid; gap: 8px; }.coverage-row > div:first-child { display: flex; justify-content: space-between; align-items: baseline; }.coverage-row strong { color: #285493; font-size: 22px; }.coverage-row span { color: #617087; font-size: 13px; }.progress { height: 7px; overflow: hidden; border-radius: 999px; background: #e7edf5; }.progress i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #3269b3, #42a67a); }
.knowledge-summary { display: flex; gap: 16px; color: #28704c; font-size: 13px; }.knowledge-summary .warning { color: #a56618; }.boundary { margin-top: 20px; color: #75570a; background: #fff8df; line-height: 1.6; }
@media (max-width: 1050px) { .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 760px) { .product-grid { grid-template-columns: 1fr; }.metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.section-heading { display: block; }.section-heading > span { display: block; margin-top: 6px; }.activation-toolbar { grid-template-columns: 1fr; } }
</style>
