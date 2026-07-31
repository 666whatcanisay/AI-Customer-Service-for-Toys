<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import {
  apiErrorMessage,
  checkProductAiKnowledge,
  getProductKnowledgeProduct,
  listCatalogActivationReceipts,
  listProductAiKnowledgeReceipts,
  publishProductAiKnowledge,
  setProductCustomerServiceStatus,
  updateProductBasicInfo,
  type CatalogActivationReceipt,
  type AiKnowledgePublicationReceipt,
  type AiKnowledgePublicationStatus,
  type CustomerServiceStatus,
  type ProductKnowledgeDetail,
  type TopicCoverage,
} from '../api/client'
import { displayStatus } from '../presentation'

const props = defineProps<{ productId: string }>()
const detail = ref<ProductKnowledgeDetail | null>(null)
const error = ref('')
const loading = ref(true)
const editingBasicInfo = ref(false)
const savingBasicInfo = ref(false)
const saveError = ref('')
const saveReceipt = ref('')
const activationOperator = ref('')
const activationBusy = ref(false)
const activationMessage = ref('')
const activationError = ref('')
const activationReceipts = ref<CatalogActivationReceipt[]>([])
const receiptsVisible = ref(false)
const publicationBusy = ref(false)
const publicationMessage = ref('')
const publicationError = ref('')
const publicationReceipts = ref<AiKnowledgePublicationReceipt[]>([])
const publicationReceiptsVisible = ref(false)
const basicInfo = reactive({
  product_display_name: '',
  product_summary: '',
  store_display_name: '',
  store_remarks: '',
})

const aTopics = computed(() => detail.value?.topic_coverage.filter((item) => item.level === 'A') ?? [])
const bTopics = computed(() => detail.value?.topic_coverage.filter((item) => item.level === 'B') ?? [])

function topicStatusLabel(topic: TopicCoverage): string {
  return {
    SUPPORTED: '可回答',
    PARTIAL: '可基础回答',
    MISSING: '资料缺失',
  }[topic.status]
}

function dataSourceLabel(value: 'TEST' | 'PILOT' | 'UNKNOWN'): string {
  return { TEST: '历史测试', PILOT: '试运行', UNKNOWN: '待确认' }[value]
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

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value))
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    detail.value = await getProductKnowledgeProduct(props.productId)
    resetBasicInfoForm()
  } catch (reason: unknown) {
    detail.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function resetBasicInfoForm(): void {
  if (!detail.value) return
  Object.assign(basicInfo, {
    product_display_name: detail.value.product.product_name,
    product_summary: detail.value.product.product_summary || '',
    store_display_name: detail.value.store.store_name,
    store_remarks: detail.value.store.remarks || '',
  })
}

function beginBasicInfoEdit(): void {
  resetBasicInfoForm()
  saveError.value = ''
  saveReceipt.value = ''
  editingBasicInfo.value = true
}

function cancelBasicInfoEdit(): void {
  editingBasicInfo.value = false
  saveError.value = ''
  resetBasicInfoForm()
}

async function saveBasicInfo(): Promise<void> {
  if (savingBasicInfo.value) return
  savingBasicInfo.value = true
  saveError.value = ''
  saveReceipt.value = ''
  try {
    detail.value = await updateProductBasicInfo(props.productId, basicInfo)
    resetBasicInfoForm()
    editingBasicInfo.value = false
    saveReceipt.value = '基础信息已保存并同步显示；商品知识发生变化时会进入待审核，不会自动发布到 AI 或 RAG。'
  } catch (reason: unknown) {
    saveError.value = apiErrorMessage(reason)
  } finally {
    savingBasicInfo.value = false
  }
}

async function changeCustomerServiceStatus(status: CustomerServiceStatus): Promise<void> {
  const operator = activationOperator.value.trim()
  if (!operator) {
    activationError.value = '请先填写本次操作人。'
    return
  }
  activationBusy.value = true
  activationError.value = ''
  activationMessage.value = ''
  try {
    const result = await setProductCustomerServiceStatus(
      props.productId,
      status,
      operator,
      `product-${props.productId}-${status}-${crypto.randomUUID()}`,
    )
    activationMessage.value = result.changed && result.activation_receipt
      ? `客服状态已更新，收据：${result.activation_receipt.activation_receipt_id}`
      : '商品已经是目标客服状态，没有重复生成收据。'
    await load()
    await viewActivationReceipts()
  } catch (reason: unknown) {
    activationError.value = apiErrorMessage(reason)
  } finally {
    activationBusy.value = false
  }
}

async function viewActivationReceipts(): Promise<void> {
  activationError.value = ''
  try {
    const result = await listCatalogActivationReceipts('PRODUCT', props.productId)
    activationReceipts.value = result.items
    receiptsVisible.value = true
  } catch (reason: unknown) {
    activationReceipts.value = []
    activationError.value = apiErrorMessage(reason)
  }
}

async function publishAiKnowledge(): Promise<void> {
  const operator = activationOperator.value.trim()
  if (!operator) {
    publicationError.value = '请先填写本次操作人。'
    return
  }
  publicationBusy.value = true
  publicationError.value = ''
  publicationMessage.value = ''
  try {
    const result = await publishProductAiKnowledge(
      props.productId,
      operator,
      `publish-${props.productId}-${crypto.randomUUID()}`,
    )
    publicationMessage.value = result.publication_receipt
      ? `AI 知识已增量发布，收据：${result.publication_receipt.publication_receipt_id}`
      : '当前审核版本已发布，无需重复生成向量。'
    await load()
    await viewPublicationReceipts()
  } catch (reason: unknown) {
    publicationError.value = apiErrorMessage(reason)
  } finally {
    publicationBusy.value = false
  }
}

async function checkAiKnowledge(): Promise<void> {
  const operator = activationOperator.value.trim()
  if (!operator) {
    publicationError.value = '请先填写本次操作人。'
    return
  }
  publicationBusy.value = true
  publicationError.value = ''
  publicationMessage.value = ''
  try {
    const result = await checkProductAiKnowledge(props.productId, operator)
    publicationMessage.value = `AI 知识检查完成：${aiKnowledgeLabel(result.ai_knowledge.status)}，chunks ${result.ai_knowledge.chunk_count}，embeddings ${result.ai_knowledge.embedding_count}。`
    await load()
  } catch (reason: unknown) {
    publicationError.value = apiErrorMessage(reason)
  } finally {
    publicationBusy.value = false
  }
}

async function viewPublicationReceipts(): Promise<void> {
  publicationError.value = ''
  try {
    const result = await listProductAiKnowledgeReceipts(props.productId)
    publicationReceipts.value = result.items
    publicationReceiptsVisible.value = true
  } catch (reason: unknown) {
    publicationReceipts.value = []
    publicationError.value = apiErrorMessage(reason)
  }
}

watch(() => props.productId, load)
onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">商品知识详情</p>
        <h1>{{ detail?.product.product_name || '商品知识' }}</h1>
        <p v-if="detail">{{ detail.store.store_name }} → {{ detail.product.product_name }} → {{ detail.skus.map((sku) => sku.sku_name).join(' / ') || '暂无 SKU' }}</p>
      </div>
      <RouterLink class="button secondary" to="/knowledge-center">返回商品知识中心</RouterLink>
    </div>

    <p v-if="loading" class="notice" role="status">正在读取商品知识详情…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取商品知识详情。{{ error }}</p>

    <template v-else-if="detail">
      <section class="answer-grid" aria-label="AI 可回答能力摘要">
        <article class="answer-card supported">
          <span>1. AI 现在能回答什么？</span>
          <strong>{{ detail.answerable_topics.length }} 项</strong>
          <div class="topic-chips">
            <span v-for="topic in detail.answerable_topics" :key="topic">✓ {{ topic }}</span>
          </div>
        </article>
        <article class="answer-card missing">
          <span>2. AI 不能回答什么？</span>
          <strong>{{ detail.missing_topics.length }} 项</strong>
          <div class="topic-chips">
            <span v-for="topic in detail.missing_topics" :key="topic">⚠ {{ topic }}</span>
            <span v-if="detail.missing_topics.length === 0">暂无规则内缺失项</span>
          </div>
        </article>
        <article class="answer-card action">
          <span>3. 运营下一步补什么？</span>
          <strong>{{ detail.next_actions.length }} 项</strong>
          <ul>
            <li v-for="action in detail.next_actions.slice(0, 4)" :key="action">{{ action }}</li>
            <li v-if="detail.next_actions.length === 0">当前无需补充核心资料。</li>
          </ul>
        </article>
      </section>

      <section class="card overview-card">
        <div class="section-heading">
          <div>
            <p class="eyebrow">商品概览</p>
            <h2>{{ detail.product.product_name }}</h2>
            <div class="status-row">
              <span class="status-pill">资料：{{ displayStatus(detail.data_status) }}</span>
              <span class="status-pill ai">资料覆盖：{{ displayStatus(detail.ai_status) }}</span>
              <span class="status-pill">来源：{{ dataSourceLabel(detail.product.data_source) }}</span>
              <span class="status-pill">客服：{{ detail.product.customer_service_status === 'ENABLED' ? '已启用' : '已禁用' }}</span>
              <span :class="['status-pill', `publication-${detail.ai_knowledge.status.toLowerCase()}`]">AI知识：{{ aiKnowledgeLabel(detail.ai_knowledge.status) }}</span>
            </div>
          </div>
          <div class="overview-actions">
            <button v-if="!editingBasicInfo" class="button secondary" type="button" @click="beginBasicInfoEdit">编辑基础信息</button>
            <div class="coverage-score"><strong>{{ detail.coverage_percent }}%</strong><span>AI 核心知识覆盖度</span></div>
          </div>
        </div>
        <form v-if="editingBasicInfo" class="basic-info-form" @submit.prevent="saveBasicInfo">
          <div class="form-grid">
            <label>商品展示名称<input v-model.trim="basicInfo.product_display_name" required minlength="2" maxlength="255"></label>
            <label>店铺展示名称<input v-model.trim="basicInfo.store_display_name" required minlength="2" maxlength="255"></label>
            <label class="wide">商品简介<textarea v-model.trim="basicInfo.product_summary" maxlength="4000" placeholder="资料未提供时可以留空"></textarea></label>
            <label class="wide">店铺展示备注<textarea v-model.trim="basicInfo.store_remarks" maxlength="1000" placeholder="可填写该店铺在知识运营中的展示说明"></textarea></label>
          </div>
          <p class="notice boundary">只维护中文业务展示信息。商品和 SKU 的内部身份不会改变；保存后进入人工审核，不会自动发布。</p>
          <p v-if="saveError" class="notice error" role="alert">{{ saveError }}</p>
          <div class="form-actions"><button class="button" type="submit" :disabled="savingBasicInfo">{{ savingBasicInfo ? '正在保存…' : '保存基础信息' }}</button><button class="button secondary" type="button" :disabled="savingBasicInfo" @click="cancelBasicInfoEdit">取消</button></div>
        </form>
        <p v-if="saveReceipt" class="notice success" role="status">{{ saveReceipt }}</p>
        <section class="activation-panel" aria-label="商品客服使用状态">
          <div>
            <strong>客服使用控制</strong>
            <p>由运营确认商品是否进入 B 客服目录；不会自动发布知识或发送客户消息。</p>
          </div>
          <label>本次操作人<input v-model.trim="activationOperator" maxlength="128" placeholder="填写姓名或运营账号"></label>
          <div class="form-actions">
            <button class="button secondary" type="button" :disabled="activationBusy || detail.product.data_source === 'UNKNOWN' || (detail.product.customer_service_status === 'DISABLED' && detail.data_status !== 'APPROVED')" @click="changeCustomerServiceStatus(detail.product.customer_service_status === 'ENABLED' ? 'DISABLED' : 'ENABLED')">{{ detail.product.customer_service_status === 'ENABLED' ? '关闭客服使用' : '启用客服使用' }}</button>
            <button class="text-button" type="button" @click="viewActivationReceipts">查看 activation receipt</button>
          </div>
          <p v-if="activationMessage" class="notice success" role="status">{{ activationMessage }}</p>
          <p v-if="activationError" class="notice error" role="alert">{{ activationError }}</p>
          <div v-if="receiptsVisible" class="receipt-list">
            <p v-if="activationReceipts.length === 0" class="notice">该商品尚无客服状态变更收据。</p>
            <article v-for="item in activationReceipts" v-else :key="item.activation_receipt_id">
              <strong>{{ item.customer_service_status === 'ENABLED' ? '启用客服使用' : '关闭客服使用' }}</strong>
              <span>{{ formatDate(item.confirmed_at) }} · {{ item.confirmed_by }}</span>
              <code>{{ item.activation_receipt_id }}</code>
              <p>{{ item.confirmation_note }}</p>
            </article>
          </div>
        </section>
        <section class="activation-panel ai-publication-panel" aria-label="商品AI知识发布状态">
          <div>
            <strong>AI 知识发布</strong>
            <p>仅将已审核商品的当前版本增量发布到 RAG。不会全量重建，不会自动启用客服，也不会修改 Prompt。</p>
          </div>
          <dl class="publication-evidence">
            <div><dt>发布状态</dt><dd>{{ aiKnowledgeLabel(detail.ai_knowledge.status) }}</dd></div>
            <div><dt>向量状态</dt><dd>{{ detail.ai_knowledge.embedding_status }}</dd></div>
            <div><dt>Chunks</dt><dd>{{ detail.ai_knowledge.chunk_count }}</dd></div>
            <div><dt>Embeddings</dt><dd>{{ detail.ai_knowledge.embedding_count }}</dd></div>
            <div><dt>Collection</dt><dd><code>{{ detail.ai_knowledge.active_collection || '尚未发布' }}</code></dd></div>
            <div><dt>当前 fingerprint</dt><dd><code>{{ detail.ai_knowledge.current_fingerprint || '—' }}</code></dd></div>
            <div><dt>已发布 fingerprint</dt><dd><code>{{ detail.ai_knowledge.indexed_fingerprint || '—' }}</code></dd></div>
            <div><dt>更新时间</dt><dd>{{ detail.ai_knowledge.updated_at ? formatDate(detail.ai_knowledge.updated_at) : '尚未检查' }}</dd></div>
          </dl>
          <div class="form-actions">
            <button class="button" type="button" :disabled="publicationBusy || detail.data_status !== 'APPROVED' || detail.product.data_source === 'UNKNOWN' || detail.ai_knowledge.status === 'GENERATING'" data-testid="publish-ai-knowledge" @click="publishAiKnowledge">{{ detail.ai_knowledge.status === 'NEED_RESYNC' ? '重新同步AI知识' : '同步AI知识' }}</button>
            <button class="button secondary" type="button" :disabled="publicationBusy" data-testid="check-ai-knowledge" @click="checkAiKnowledge">检查RAG状态</button>
            <button class="text-button" type="button" @click="viewPublicationReceipts">查看发布收据</button>
          </div>
          <p v-if="detail.data_status !== 'APPROVED'" class="notice boundary">资料审核通过后才能发布 AI 知识。</p>
          <p v-if="publicationMessage" class="notice success" role="status">{{ publicationMessage }}</p>
          <p v-if="publicationError" class="notice error" role="alert">{{ publicationError }}</p>
          <div v-if="publicationReceiptsVisible" class="receipt-list">
            <p v-if="publicationReceipts.length === 0" class="notice">该商品尚无 AI 知识发布收据。</p>
            <article v-for="item in publicationReceipts" v-else :key="item.publication_receipt_id">
              <strong>AI 知识已发布</strong>
              <span>{{ formatDate(item.created_at) }} · {{ item.operator }} · {{ item.chunk_count }} chunks</span>
              <code>{{ item.publication_receipt_id }}</code>
              <p>Collection：{{ item.active_collection }}</p>
            </article>
          </div>
        </section>
        <p class="summary">{{ detail.product.product_summary || '当前资料未提供商品简介。' }}</p>
        <dl class="business-facts">
          <div><dt>核心卖点</dt><dd>{{ detail.product.core_selling_points.join('；') || '当前资料未提供' }}</dd></div>
          <div><dt>适用年龄</dt><dd>{{ detail.product.applicable_age || '当前资料未提供，回答时需提示人工确认' }}</dd></div>
          <div><dt>材质与安全</dt><dd>{{ detail.product.material || '当前资料未提供' }}</dd></div>
          <div><dt>包装内容</dt><dd>{{ detail.product.package_contents || '当前资料未提供' }}</dd></div>
          <div><dt>基础使用说明</dt><dd>{{ detail.product.usage_instructions || '当前资料未提供' }}</dd></div>
        </dl>
      </section>

      <section class="card section-card">
        <div class="section-heading"><div><p class="eyebrow">SKU 信息</p><h2>规格和款式差异</h2></div><span>{{ detail.skus.length }} 个 SKU</span></div>
        <p v-if="detail.skus.length === 0" class="notice">当前商品暂无 SKU 资料。</p>
        <div v-else class="sku-grid">
          <article v-for="sku in detail.skus" :key="sku.technical_details.sku_id || sku.sku_name" class="sku-card">
            <h3>{{ sku.sku_name }}</h3>
            <p><strong>差异结论：</strong>{{ sku.specification_difference || '当前资料未说明与其他 SKU 的差异。' }}</p>
            <p><strong>颜色款式：</strong>{{ sku.color_style || '当前资料未提供' }}</p>
            <p><strong>包装差异：</strong>{{ sku.package_difference || '当前资料未提供' }}</p>
            <p><strong>SKU专属FAQ：</strong>{{ sku.faq_count }} 条</p>
            <p v-if="sku.specification_difference === '已确认无差异'" class="confirmed">✓ 已确认无差异</p>
            <div class="topic-chips"><span v-for="attribute in sku.attributes" :key="attribute">{{ attribute }}</span></div>
          </article>
        </div>
      </section>

      <section class="coverage-layout">
        <article class="card section-card">
          <p class="eyebrow">A级 · AI 客服核心信息</p>
          <h2>核心覆盖情况</h2>
          <div class="coverage-list">
            <div v-for="topic in aTopics" :key="topic.key" :class="['coverage-item', topic.status.toLowerCase()]">
              <span>{{ topic.name }}</span><strong>{{ topicStatusLabel(topic) }}</strong>
            </div>
          </div>
        </article>
        <article class="card section-card">
          <p class="eyebrow">B级 · 回答效果增强</p>
          <h2>增强信息覆盖</h2>
          <div class="coverage-list">
            <div v-for="topic in bTopics" :key="topic.key" :class="['coverage-item', topic.status.toLowerCase()]">
              <span>{{ topic.name }}</span><strong>{{ topicStatusLabel(topic) }}</strong>
            </div>
          </div>
        </article>
      </section>

      <section class="card section-card">
        <div class="section-heading"><div><p class="eyebrow">AI 问题缺口</p><h2>缺失信息与安全回答</h2></div><RouterLink class="button" :to="{ path: '/knowledge-editor', query: { product: detail.product.technical_details.product_id || '', store: detail.store.technical_details.store_code || '' } }">补充知识</RouterLink></div>
        <p v-if="detail.gaps.length === 0" class="notice success">当前规则范围内未发现待补充缺口。</p>
        <div v-else class="gap-list">
          <article v-for="gap in detail.gaps" :key="`${gap.source}-${gap.key}`" class="gap-card">
            <div><strong>⚠ {{ gap.title }}</strong><span>{{ displayStatus(gap.severity) }}</span></div>
            <p>{{ gap.description }}</p>
            <p><b>运营建议：</b>{{ gap.recommended_action }}</p>
            <blockquote>{{ gap.safe_fallback }}</blockquote>
          </article>
        </div>
      </section>

      <section class="lower-grid">
        <article class="card section-card">
          <p class="eyebrow">常见问题 FAQ</p><h2>已核对问答</h2>
          <p v-if="detail.faqs.length === 0" class="notice">当前商品暂无结构化 FAQ。</p>
          <details v-for="faq in detail.faqs" v-else :key="faq.question" class="faq-item">
            <summary>{{ faq.question }}</summary>
            <p>{{ faq.recommended_reply }}</p>
            <small>{{ faq.sku_name ? `适用SKU：${faq.sku_name} · ` : '适用全部SKU · ' }}回答策略：{{ displayStatus(faq.answer_strategy) }} · 风险：{{ displayStatus(faq.risk_level) }}</small>
          </details>
        </article>
        <article class="card section-card">
          <p class="eyebrow">安全信息</p><h2>回答边界与提示</h2>
          <p v-if="detail.safety_information.length === 0" class="notice">当前商品暂无单独安全说明。</p>
          <div v-for="item in detail.safety_information" v-else :key="`${item.title}-${item.content}`" class="safety-item">
            <strong>{{ item.title }}</strong><p>{{ item.content }}</p><p v-if="item.forbidden_claim"><b>禁止承诺：</b>{{ item.forbidden_claim }}</p><p v-if="item.handoff_condition"><b>必须转人工：</b>{{ item.handoff_condition }}</p><small v-if="item.risk_level">风险：{{ displayStatus(item.risk_level) }}</small>
          </div>
        </article>
      </section>

      <section class="card section-card">
        <p class="eyebrow">资料来源</p><h2>可追溯依据</h2>
        <p v-if="detail.sources.length === 0" class="notice">当前商品尚未登记独立资料来源。</p>
        <div v-else class="source-grid">
          <article v-for="source in detail.sources" :key="source.technical_details.source_id || source.technical_details.material_id || source.source_name">
            <strong>{{ source.source_name }}</strong><span>{{ displayStatus(source.source_type) }} · {{ source.review_status ? displayStatus(source.review_status) : '未标注审核状态' }}</span>
          </article>
        </div>
      </section>

      <p class="notice boundary">{{ detail.boundary_note }}页面只显示有来源的现有事实；缺失字段不会自动补全或编造。</p>
    </template>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.answer-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 20px; }.answer-card { display: grid; align-content: start; gap: 10px; min-height: 180px; padding: 19px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }.answer-card > span { color: #526279; font-size: 13px; }.answer-card > strong { color: #172554; font-size: 26px; }.answer-card.supported { border-top: 4px solid #3d9b6b; }.answer-card.missing { border-top: 4px solid #d69735; }.answer-card.action { border-top: 4px solid #3973c4; }.answer-card ul { margin: 0; padding-left: 18px; color: #526279; line-height: 1.55; }
.topic-chips { display: flex; flex-wrap: wrap; gap: 6px; }.topic-chips span { padding: 5px 8px; border-radius: 7px; background: #f1f5fa; color: #425b78; font-size: 12px; }.section-heading { display: flex; justify-content: space-between; gap: 18px; align-items: start; }.section-heading h2, .section-card h2 { margin: 0; color: #172554; }.coverage-score { display: grid; justify-items: end; }.coverage-score strong { color: #2e6db0; font-size: 30px; }.coverage-score span { color: #617087; font-size: 12px; }.status-row { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }.status-pill { padding: 5px 9px; border-radius: 999px; color: #365174; background: #edf2f8; font-size: 12px; }.status-pill.ai, .status-pill.publication-generating { color: #285493; background: #eaf2ff; }.status-pill.publication-published { color: #217447; background: #e7f5ec; }.status-pill.publication-sync_failed { color: #a23d3d; background: #fff0f0; }.status-pill.publication-not_generated, .status-pill.publication-need_resync { color: #9a5c0d; background: #fff1df; }.summary { color: #526279; line-height: 1.65; }.business-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.business-facts div { padding: 13px; border-radius: 9px; background: #f7f9fc; }.business-facts dt { color: #617087; font-size: 12px; }.business-facts dd { margin: 5px 0 0; color: #2f4259; line-height: 1.5; }
.overview-actions { display: grid; justify-items: end; gap: 12px; }.basic-info-form { display: grid; gap: 14px; margin: 18px 0; padding: 18px; border: 1px solid #b9cde9; border-radius: 11px; background: #f8fbff; }.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; }.form-grid label { display: grid; gap: 6px; color: #526279; font-size: 13px; }.form-grid input, .form-grid textarea { min-height: 41px; padding: 9px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }.form-grid textarea { min-height: 92px; resize: vertical; }.form-grid .wide { grid-column: 1 / -1; }.form-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.activation-panel { display: grid; gap: 12px; margin: 18px 0; padding: 16px; border: 1px solid #cbd7e6; border-radius: 10px; background: #f8fbff; }.activation-panel > div > p { margin: 5px 0 0; color: #617087; }.activation-panel label { display: grid; gap: 6px; max-width: 360px; color: #526279; font-size: 13px; }.activation-panel input { min-height: 41px; padding: 9px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }.text-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; cursor: pointer; }.receipt-list { display: grid; gap: 9px; }.receipt-list article { display: grid; gap: 5px; padding: 12px; border-radius: 8px; background: #fff; }.receipt-list span, .receipt-list code { color: #617087; font-size: 12px; }.receipt-list p { margin: 0; color: #425b78; }
.ai-publication-panel { border-color: #b9cde9; }.publication-evidence { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 0; }.publication-evidence div { padding: 10px; border-radius: 8px; background: #fff; }.publication-evidence dt { color: #617087; font-size: 12px; }.publication-evidence dd { margin: 4px 0 0; overflow-wrap: anywhere; color: #334965; }.publication-evidence code { font-size: 11px; }
.section-card { margin-top: 20px; }.section-card > .eyebrow + h2 { margin-bottom: 16px; }.sku-grid, .source-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }.sku-card, .source-grid article { padding: 15px; border: 1px solid #e0e7f0; border-radius: 10px; }.sku-card h3 { margin: 0; color: #25466f; }.sku-card p { color: #526279; line-height: 1.55; }.sku-card .confirmed { color: #217447; font-weight: 700; }.coverage-layout, .lower-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }.coverage-list { display: grid; gap: 8px; margin-top: 16px; }.coverage-item { display: flex; justify-content: space-between; padding: 10px 12px; border-radius: 8px; background: #edf7f1; color: #276a49; }.coverage-item.partial { background: #eef4ff; color: #315f9d; }.coverage-item.missing { background: #fff5e7; color: #9a641c; }.coverage-item strong { font-size: 12px; }
.gap-list { display: grid; gap: 10px; margin-top: 16px; }.gap-card { padding: 15px; border-left: 4px solid #d69735; border-radius: 8px; background: #fffaf2; }.gap-card > div { display: flex; justify-content: space-between; gap: 12px; color: #704911; }.gap-card p { margin: 8px 0; color: #526279; line-height: 1.55; }.gap-card blockquote { margin: 10px 0 0; padding: 10px 12px; border-radius: 7px; background: #fff; color: #75570a; }.faq-item { padding: 11px 0; border-bottom: 1px solid #e5ebf2; }.faq-item summary { color: #25466f; cursor: pointer; }.faq-item p, .safety-item p { color: #526279; line-height: 1.55; }.faq-item small, .safety-item small { color: #617087; }.safety-item { padding: 12px 0; border-bottom: 1px solid #e5ebf2; }.source-grid article { display: grid; gap: 6px; }.source-grid article > span { color: #617087; font-size: 12px; }.boundary { margin-top: 20px; color: #75570a; background: #fff8df; line-height: 1.6; }
@media (max-width: 900px) { .answer-grid, .coverage-layout, .lower-grid { grid-template-columns: 1fr; }.business-facts, .sku-grid, .source-grid, .form-grid { grid-template-columns: 1fr; }.form-grid .wide { grid-column: span 1; } }
</style>
