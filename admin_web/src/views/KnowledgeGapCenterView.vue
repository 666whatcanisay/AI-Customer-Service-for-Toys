<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  getProductKnowledgeOverview,
  listProductKnowledgeGaps,
  type KnowledgeGapWorkflowStatus,
  type ProductKnowledgeGapListItem,
  type StoreKnowledgeSummary,
} from '../api/client'
import { displayStatus } from '../presentation'

const stores = ref<StoreKnowledgeSummary[]>([])
const gaps = ref<ProductKnowledgeGapListItem[]>([])
const loading = ref(true)
const error = ref('')
const filters = reactive({ store_code: '', priority: '' as '' | 'P0' | 'P1' | 'P2' | 'P3', workflow_status: '' as '' | KnowledgeGapWorkflowStatus })

const pendingCount = computed(() => gaps.value.filter((item) => item.workflow_status === 'PENDING').length)
const highPriorityCount = computed(() => gaps.value.filter((item) => item.priority === 'P0' || item.priority === 'P1').length)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    gaps.value = (await listProductKnowledgeGaps(filters)).items
  } catch (reason: unknown) {
    gaps.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    stores.value = (await getProductKnowledgeOverview()).stores
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  }
  await load()
})
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div><p class="eyebrow">AI回答缺口</p><h1>知识缺口中心</h1><p>按出现影响和风险排序，帮助运营判断下一步先补什么。</p></div>
      <RouterLink class="button" to="/knowledge-editor">补充商品知识</RouterLink>
    </div>

    <section class="metrics" aria-label="知识缺口统计">
      <article><span>当前缺口</span><strong>{{ gaps.length }}</strong></article>
      <article><span>高优先级</span><strong>{{ highPriorityCount }}</strong></article>
      <article><span>待处理</span><strong>{{ pendingCount }}</strong></article>
    </section>

    <form class="card filters" @submit.prevent="load">
      <label>店铺<select v-model="filters.store_code"><option value="">全部店铺</option><option v-for="store in stores" :key="store.store_name" :value="store.technical_details.store_code || ''">{{ store.store_name }}</option></select></label>
      <label>优先级<select v-model="filters.priority"><option value="">全部优先级</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select></label>
      <label>处理状态<select v-model="filters.workflow_status"><option value="">全部状态</option><option value="PENDING">待处理</option><option value="IN_PROGRESS">补充中</option><option value="PENDING_VERIFICATION">待验证</option><option value="RESOLVED">已解决</option></select></label>
      <button class="button secondary" type="submit">筛选</button>
    </form>

    <p v-if="loading" class="notice" role="status">正在汇总知识缺口…</p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-else-if="gaps.length === 0" class="notice success">当前筛选范围内没有知识缺口。</p>
    <section v-else class="gap-list">
      <article v-for="gap in gaps" :key="`${gap.store_name}-${gap.product_name}-${gap.sku_name}-${gap.missing_topic}`" class="gap-card">
        <div class="gap-heading"><div><small>{{ gap.store_name }} → {{ gap.product_name }} → {{ gap.sku_name }}</small><h2>{{ gap.missing_topic }}</h2></div><div class="badges"><span :class="['priority', gap.priority.toLowerCase()]">{{ gap.priority }}</span><span>{{ displayStatus(gap.workflow_status) }}</span></div></div>
        <p>{{ gap.description }}</p>
        <dl><div><dt>出现次数</dt><dd>{{ gap.occurrence_count }}</dd></div><div><dt>影响程度</dt><dd>{{ gap.impact_level }}</dd></div><div><dt>下一步补充</dt><dd>{{ gap.recommended_action }}</dd></div></dl>
        <blockquote>{{ gap.safe_fallback }}</blockquote>
      </article>
    </section>

    <p class="notice boundary">缺口来自现有结构化事实、待审核资料和已保存的质量分析证据。页面不会生成假缺口，也不会自动补写商品事实。</p>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }.metrics article { display: grid; gap: 6px; padding: 17px; border: 1px solid #dbe4ef; border-radius: 12px; background: #fff; }.metrics span { color: #617087; font-size: 12px; }.metrics strong { color: #172554; font-size: 26px; }.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 11px; margin-bottom: 18px; }.filters label { display: grid; gap: 5px; min-width: 170px; color: #526279; font-size: 13px; }.filters select { min-height: 40px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }.gap-list { display: grid; gap: 13px; }.gap-card { padding: 19px; border: 1px solid #dbe4ef; border-left: 4px solid #d69735; border-radius: 12px; background: #fff; }.gap-heading { display: flex; justify-content: space-between; gap: 16px; }.gap-heading small { color: #617087; }.gap-heading h2 { margin: 5px 0 0; color: #172554; font-size: 18px; }.badges { display: flex; gap: 7px; align-items: start; }.badges span { padding: 5px 8px; border-radius: 999px; color: #526279; background: #edf2f8; font-size: 12px; }.badges .priority { color: #855314; background: #fff1df; font-weight: 800; }.badges .p0 { color: #9b2929; background: #fff0f0; }.gap-card > p { color: #526279; line-height: 1.6; }.gap-card dl { display: grid; grid-template-columns: 110px 110px minmax(0, 1fr); gap: 10px; }.gap-card dl div { padding: 10px; border-radius: 8px; background: #f7f9fc; }.gap-card dt { color: #617087; font-size: 11px; }.gap-card dd { margin: 4px 0 0; color: #334965; line-height: 1.45; }.gap-card blockquote { margin: 12px 0 0; padding: 10px 12px; border-radius: 8px; color: #75570a; background: #fff8df; }.boundary { margin-top: 18px; color: #75570a; background: #fff8df; }
@media (max-width: 700px) { .metrics { grid-template-columns: 1fr; }.gap-card dl { grid-template-columns: 1fr; }.gap-heading { display: grid; } }
</style>
