<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  apiErrorMessage,
  getProductKnowledgeOverview,
  getProductKnowledgeProduct,
  listProductKnowledgeProducts,
  uploadKnowledgeMaterial,
  type KnowledgeMaterialType,
  type KnowledgeTemplateType,
  type ProductKnowledgeDetail,
  type ProductKnowledgeListItem,
  type StoreKnowledgeSummary,
} from '../api/client'
import { displayStatus } from '../presentation'

type EditableTemplate = 'PRODUCT_KNOWLEDGE' | 'SKU_DIFFERENCE' | 'FAQ' | 'SAFETY_RULE'

const route = useRoute()
const stores = ref<StoreKnowledgeSummary[]>([])
const products = ref<ProductKnowledgeListItem[]>([])
const productDetail = ref<ProductKnowledgeDetail | null>(null)
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const receipt = ref('')

const scope = reactive({ store_code: '', product_id: '', sku_id: '' })
const governance = reactive({ source: '', source_date: '', submitted_by: '', confirmed: '是' })
const form = reactive({
  template_type: 'PRODUCT_KNOWLEDGE' as EditableTemplate,
  product_summary: '', selling_points: '', age: '', material: '', safety: '', package_contents: '', usage: '', play: '',
  color_style: '已确认无差异', specification_difference: '已确认无差异', package_difference: '已确认无差异',
  quantity_difference: '已确认无差异', size_difference: '已确认无差异', play_difference: '已确认无差异', sku_faq: '', sku_safety: '',
  question: '', answer: '', scenario: '', risk_level: '中', manual_confirmation: '否',
  safety_topic: '', forbidden_claim: '', confirmation_condition: '', handoff_condition: '',
})

const templateOptions: Array<{ value: EditableTemplate; description: string }> = [
  { value: 'PRODUCT_KNOWLEDGE', description: '补充商品简介、卖点、年龄、材质、包装和使用说明' },
  { value: 'SKU_DIFFERENCE', description: '只记录具体SKU与其他款式的差异' },
  { value: 'FAQ', description: '维护有事实依据的客户问题和标准回答' },
  { value: 'SAFETY_RULE', description: '维护安全提醒、禁止承诺和转人工条件' },
]

const scopedProducts = computed(() => products.value.filter((item) => item.technical_details.store_code === scope.store_code))
const selectedStore = computed(() => stores.value.find((item) => item.technical_details.store_code === scope.store_code))
const selectedProduct = computed(() => products.value.find((item) => item.technical_details.product_id === scope.product_id))
const selectedSku = computed(() => productDetail.value?.skus.find((item) => item.technical_details.sku_id === scope.sku_id))
const skuRequired = computed(() => form.template_type === 'SKU_DIFFERENCE')

async function loadProductDetail(): Promise<void> {
  productDetail.value = scope.product_id ? await getProductKnowledgeProduct(scope.product_id) : null
  if (!productDetail.value?.skus.some((item) => item.technical_details.sku_id === scope.sku_id)) scope.sku_id = ''
}

async function changeStore(): Promise<void> {
  scope.product_id = ''
  scope.sku_id = ''
  productDetail.value = null
}

function materialType(templateType: KnowledgeTemplateType): KnowledgeMaterialType {
  if (templateType === 'FAQ') return 'FAQ_SOURCE'
  if (templateType === 'SAFETY_RULE') return 'SAFETY_INSTRUCTION'
  return 'PRODUCT_SPEC'
}

function buildRow(): Record<string, string> {
  const common = {
    店铺名称: selectedStore.value?.store_name || '',
    商品名称: selectedProduct.value?.product_name || '',
  }
  if (form.template_type === 'PRODUCT_KNOWLEDGE') {
    return {
      ...common, 商品简介: form.product_summary, 核心卖点: form.selling_points, 适用年龄: form.age,
      材质信息: form.material, 安全提醒: form.safety, 包装内容: form.package_contents, 使用说明: form.usage,
      玩法介绍: form.play, 客户常问问题: form.question, 推荐回答方向: form.answer,
      资料来源: governance.source, 来源日期: governance.source_date, 是否人工确认: governance.confirmed, 备注: '',
    }
  }
  if (form.template_type === 'SKU_DIFFERENCE') {
    return {
      ...common, SKU名称: selectedSku.value?.sku_name || '', 颜色款式: form.color_style,
      规格区别: form.specification_difference, 包装区别: form.package_difference, 数量区别: form.quantity_difference,
      尺寸区别: form.size_difference, 玩法区别: form.play_difference, SKU常见问题: form.sku_faq,
      SKU安全提醒: form.sku_safety, 资料来源: governance.source, 来源日期: governance.source_date,
      确认状态: governance.confirmed === '是' ? '已确认' : '待确认', 备注: '',
    }
  }
  if (form.template_type === 'FAQ') {
    return {
      ...common, SKU名称: selectedSku.value?.sku_name || '全部SKU', 客户常问问题: form.question,
      标准回答: form.answer, 适用场景: form.scenario, 是否需要人工确认: form.manual_confirmation,
      风险等级: form.risk_level, 资料来源: governance.source, 来源日期: governance.source_date,
      事实确认状态: governance.confirmed === '是' ? '已确认' : '待确认', 备注: '',
    }
  }
  return {
    ...common, 适用年龄: form.age, 安全主题: form.safety_topic, 风险等级: form.risk_level,
    安全提醒: form.safety, 禁止承诺内容: form.forbidden_claim, 需要人工确认情况: form.confirmation_condition,
    必须转人工情况: form.handoff_condition, 资料来源: governance.source, 来源日期: governance.source_date,
    事实确认状态: governance.confirmed === '是' ? '已确认' : '待确认', 备注: '',
  }
}

async function submit(): Promise<void> {
  if (submitting.value || !selectedStore.value || !selectedProduct.value || (skuRequired.value && !selectedSku.value)) return
  submitting.value = true
  error.value = ''
  receipt.value = ''
  try {
    const row = buildRow()
    const file = new File([JSON.stringify(row)], `${displayStatus(form.template_type)}补充.json`, { type: 'application/json' })
    const result = await uploadKnowledgeMaterial(file, {
      store_code: scope.store_code,
      product_id: scope.product_id,
      sku_id: scope.sku_id || undefined,
      material_type: materialType(form.template_type),
      template_type: form.template_type,
      display_name: `${selectedProduct.value.product_name} · ${displayStatus(form.template_type)}补充`,
      submitted_by: governance.submitted_by,
    })
    receipt.value = `已保存为待审核资料，识别到 ${result.recognition_summary.detected_fields.length} 项知识字段。`
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const [overview, productPage] = await Promise.all([getProductKnowledgeOverview(), listProductKnowledgeProducts()])
    stores.value = overview.stores
    products.value = productPage.items
    const requestedStore = typeof route.query.store === 'string' ? route.query.store : ''
    const requestedProduct = typeof route.query.product === 'string' ? route.query.product : ''
    if (stores.value.some((item) => item.technical_details.store_code === requestedStore)) scope.store_code = requestedStore
    if (products.value.some((item) => item.technical_details.product_id === requestedProduct)) {
      scope.product_id = requestedProduct
      await loadProductDetail()
    }
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div><p class="eyebrow">商品知识补充</p><h1>中文知识维护</h1><p>按业务名称选择范围，只填写已核实事实；提交后进入人工审核，不会自动发布。</p></div>
      <RouterLink class="button secondary" :to="{ path: '/knowledge-review', query: { store: scope.store_code, product: scope.product_id } }">查看审核队列</RouterLink>
    </div>

    <p v-if="loading" class="notice" role="status">正在读取店铺和商品…</p>
    <form v-else class="card editor" @submit.prevent="submit">
      <section>
        <h2>1. 选择知识范围</h2>
        <div class="form-grid">
          <label>店铺<select v-model="scope.store_code" required @change="changeStore"><option value="">请选择店铺</option><option v-for="store in stores" :key="store.store_name" :value="store.technical_details.store_code || ''">{{ store.store_name }}</option></select></label>
          <label>商品<select v-model="scope.product_id" required :disabled="!scope.store_code" @change="loadProductDetail"><option value="">请选择商品</option><option v-for="product in scopedProducts" :key="product.product_name" :value="product.technical_details.product_id || ''">{{ product.product_name }}</option></select></label>
          <label>SKU{{ skuRequired ? '（必选）' : '（可选）' }}<select v-model="scope.sku_id" :required="skuRequired" :disabled="!scope.product_id"><option value="">适用于全部SKU</option><option v-for="sku in productDetail?.skus || []" :key="sku.sku_name" :value="sku.technical_details.sku_id || ''">{{ sku.sku_name }}</option></select></label>
        </div>
      </section>

      <section>
        <h2>2. 选择补充内容</h2>
        <div class="template-tabs">
          <label v-for="option in templateOptions" :key="option.value" :class="{ active: form.template_type === option.value }"><input v-model="form.template_type" type="radio" :value="option.value"><strong>{{ displayStatus(option.value) }}</strong><span>{{ option.description }}</span></label>
        </div>
      </section>

      <section class="form-grid knowledge-fields">
        <template v-if="form.template_type === 'PRODUCT_KNOWLEDGE'">
          <label class="wide">商品简介<textarea v-model.trim="form.product_summary" required></textarea></label><label>核心卖点<textarea v-model.trim="form.selling_points"></textarea></label><label>适用年龄<input v-model.trim="form.age" placeholder="资料未提供时可留空"></label><label>材质信息<input v-model.trim="form.material"></label><label>包装内容<input v-model.trim="form.package_contents"></label><label>使用说明<textarea v-model.trim="form.usage"></textarea></label><label>安全提醒<textarea v-model.trim="form.safety"></textarea></label>
        </template>
        <template v-else-if="form.template_type === 'SKU_DIFFERENCE'">
          <p class="notice wide">每项都要写实际差异；没有差异时保留“已确认无差异”，不能留空。</p><label>颜色款式<input v-model.trim="form.color_style" required></label><label>规格区别<input v-model.trim="form.specification_difference" required></label><label>包装区别<input v-model.trim="form.package_difference" required></label><label>数量区别<input v-model.trim="form.quantity_difference" required></label><label>尺寸区别<input v-model.trim="form.size_difference" required></label><label>玩法区别<input v-model.trim="form.play_difference" required></label><label>SKU常见问题<textarea v-model.trim="form.sku_faq"></textarea></label><label>SKU安全提醒<textarea v-model.trim="form.sku_safety"></textarea></label>
        </template>
        <template v-else-if="form.template_type === 'FAQ'">
          <label class="wide">客户常问问题<textarea v-model.trim="form.question" required></textarea></label><label class="wide">标准回答<textarea v-model.trim="form.answer" required></textarea></label><label>适用场景<input v-model.trim="form.scenario" required></label><label>风险等级<select v-model="form.risk_level"><option>低</option><option>中</option><option>高</option></select></label><label>是否需要人工确认<select v-model="form.manual_confirmation"><option>否</option><option>是</option></select></label>
        </template>
        <template v-else>
          <label>适用年龄<input v-model.trim="form.age"></label><label>安全主题<input v-model.trim="form.safety_topic" required></label><label>风险等级<select v-model="form.risk_level"><option>低</option><option>中</option><option>高</option></select></label><label class="wide">安全提醒<textarea v-model.trim="form.safety" required></textarea></label><label>禁止承诺内容<textarea v-model.trim="form.forbidden_claim" required></textarea></label><label>需要人工确认情况<textarea v-model.trim="form.confirmation_condition"></textarea></label><label class="wide">必须转人工情况<textarea v-model.trim="form.handoff_condition" required></textarea></label>
        </template>
      </section>

      <section>
        <h2>3. 来源与确认</h2>
        <div class="form-grid"><label class="wide">资料来源<input v-model.trim="governance.source" required placeholder="例如：商品说明书第2页、包装警示标签"></label><label>来源日期<input v-model="governance.source_date" required type="date"></label><label>是否人工确认<select v-model="governance.confirmed"><option>是</option><option>否</option></select></label><label>提交人<input v-model.trim="governance.submitted_by" required placeholder="运营人员姓名或账号"></label></div>
        <p class="notice boundary">资料不足可以保存，但不得猜测。安全高风险资料必须有来源；审核通过也不等于已发布到RAG。</p>
        <p v-if="error" class="notice error" role="alert">{{ error }}</p><p v-if="receipt" class="notice success" role="status">{{ receipt }}</p>
        <button class="button" type="submit" :disabled="submitting || !scope.product_id || (skuRequired && !scope.sku_id)">{{ submitting ? '正在保存…' : '保存并提交审核' }}</button>
      </section>
    </form>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.editor { display: grid; gap: 26px; }.editor section + section { padding-top: 22px; border-top: 1px solid #e2e8f0; }.editor h2 { margin: 0 0 15px; color: #172554; }.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }.form-grid label { display: grid; align-content: start; gap: 6px; color: #526279; font-size: 13px; }.form-grid input, .form-grid select, .form-grid textarea { min-height: 41px; padding: 9px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }.form-grid textarea { min-height: 92px; resize: vertical; }.form-grid .wide { grid-column: span 2; }.template-tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }.template-tabs label { display: grid; gap: 6px; padding: 14px; border: 1px solid #dbe4ef; border-radius: 10px; cursor: pointer; }.template-tabs label.active { border-color: #3973c4; background: #f4f8ff; }.template-tabs input { position: absolute; opacity: 0; }.template-tabs strong { color: #25466f; }.template-tabs span { color: #617087; font-size: 12px; line-height: 1.5; }.boundary { margin-top: 15px; color: #75570a; background: #fff8df; }.knowledge-fields { margin-top: 15px; }
@media (max-width: 900px) { .form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.template-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .form-grid, .template-tabs { grid-template-columns: 1fr; }.form-grid .wide { grid-column: span 1; } }
</style>
