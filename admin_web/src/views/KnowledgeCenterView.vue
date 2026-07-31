<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getProductKnowledgeOverview,
  listProductKnowledgeProducts,
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
        <p>请先按现有试点流程导入并审核可核对的商品资料。页面不会生成示例统计或虚构商品。</p>
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
          <p v-else-if="products.length === 0" class="notice">该店铺暂无已导入商品。</p>
          <div v-else class="product-grid">
            <article v-for="product in products" :key="product.technical_details.product_id || product.product_name" class="product-card">
              <div class="product-heading">
                <div>
                  <small>{{ product.store_name }} → 商品</small>
                  <h3>{{ product.product_name }}</h3>
                </div>
                <div class="status-pair">
                  <span class="state-pill data">资料：{{ displayStatus(product.data_status) }}</span>
                  <span :class="['state-pill', product.ai_status.toLowerCase()]">AI：{{ displayStatus(product.ai_status) }}</span>
                  <span class="state-pill data">客服：{{ product.customer_service_status === 'ENABLED' ? '已启用' : '已禁用' }}</span>
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
.store-tabs { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }.store-tab { display: grid; gap: 5px; min-width: 240px; padding: 13px 15px; border: 1px solid #d7e1ee; border-radius: 10px; color: #25466f; background: #fff; text-align: left; cursor: pointer; }.store-tab.active { border-color: #3973c4; box-shadow: inset 0 0 0 1px #3973c4; background: #f4f8ff; }.store-tab small { color: #617087; }
.catalog-section { margin-top: 8px; }.product-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }.product-card { display: grid; gap: 15px; padding: 20px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }.product-heading small { color: #617087; }.product-heading h3 { margin-top: 5px; font-size: 18px; }.state-pill { padding: 5px 9px; border-radius: 999px; font-size: 12px; white-space: nowrap; background: #e7f5ec; color: #217447; }.state-pill.basic_available { background: #eaf2ff; color: #285493; }.state-pill.needs_completion { background: #fff1df; color: #9a5c0d; }
.summary { margin: 0; color: #526279; line-height: 1.65; }.label { display: block; margin-bottom: 8px; color: #334965; font-size: 13px; }.tag-row, .sku-row { display: flex; flex-wrap: wrap; gap: 7px; }.tag, .sku-row span { padding: 5px 8px; border-radius: 7px; background: #f1f5fa; color: #425b78; font-size: 12px; }.missing-text { margin: 0; color: #a56a1e; font-size: 13px; }.status-pair { display: grid; justify-items: end; gap: 6px; }.state-pill.data { color: #365174; background: #edf2f8; }.state-pill.partially_available { color: #285493; background: #eaf2ff; }.state-pill.missing_knowledge, .state-pill.unconfirmed { color: #9a5c0d; background: #fff1df; }.fact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 0; }.fact-grid div { padding: 10px; border-radius: 8px; background: #f7f9fc; }.fact-grid dt { color: #617087; font-size: 11px; }.fact-grid dd { margin: 4px 0 0; color: #334965; font-size: 13px; line-height: 1.45; }
.coverage-row { display: grid; gap: 8px; }.coverage-row > div:first-child { display: flex; justify-content: space-between; align-items: baseline; }.coverage-row strong { color: #285493; font-size: 22px; }.coverage-row span { color: #617087; font-size: 13px; }.progress { height: 7px; overflow: hidden; border-radius: 999px; background: #e7edf5; }.progress i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #3269b3, #42a67a); }
.knowledge-summary { display: flex; gap: 16px; color: #28704c; font-size: 13px; }.knowledge-summary .warning { color: #a56618; }.boundary { margin-top: 20px; color: #75570a; background: #fff8df; line-height: 1.6; }
@media (max-width: 1050px) { .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 760px) { .product-grid { grid-template-columns: 1fr; }.metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.section-heading { display: block; }.section-heading > span { display: block; margin-top: 6px; } }
</style>
