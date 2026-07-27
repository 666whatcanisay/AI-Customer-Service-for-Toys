<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { apiErrorMessage, createPilotStore, listPilotStores, type PilotStore, type PilotStoreSetupStatus } from '../api/client'

const stores = ref<PilotStore[]>([])
const loading = ref(true)
const listError = ref('')
const createError = ref('')
const creating = ref(false)
const form = reactive({ store_code: '', store_name: '', platform: '' })

const summary = computed(() => ({
  total: stores.value.length,
  needsProduct: stores.value.filter((store) => store.setup_status === 'NEEDS_PRODUCT_IMPORT').length,
  needsKnowledge: stores.value.filter((store) => store.setup_status === 'NEEDS_KNOWLEDGE').length,
  observable: stores.value.filter((store) => store.setup_status === 'OBSERVABLE').length,
}))

const statusText: Record<PilotStoreSetupStatus, string> = {
  NEEDS_PRODUCT_IMPORT: '待导入商品',
  NEEDS_KNOWLEDGE: '待维护知识',
  OBSERVABLE: '可观察',
}

function formatDate(value: string | null): string { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '暂无导入记录' }

async function load(): Promise<void> {
  loading.value = true
  listError.value = ''
  try {
    const response = await listPilotStores()
    stores.value = response.items
  } catch (reason: unknown) {
    stores.value = []
    listError.value = apiErrorMessage(reason)
  } finally { loading.value = false }
}

async function submit(): Promise<void> {
  if (creating.value) return
  createError.value = ''
  creating.value = true
  try {
    await createPilotStore({ store_code: form.store_code.trim(), store_name: form.store_name.trim(), platform: form.platform.trim() })
    form.store_code = ''; form.store_name = ''; form.platform = ''
    await load()
  } catch (reason: unknown) { createError.value = apiErrorMessage(reason) }
  finally { creating.value = false }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>店铺中心</h1><p>按“创建店铺 → 导入商品 → 维护知识 → 观察客服与 AI 问题”完成多店铺试运行准备。商品导入只进入待审核暂存区。</p></div><button class="button secondary" type="button" @click="load">刷新状态</button></div>
    <p class="notice trial-note">仅限测试/试运行：不发布知识、不自动启用 AI、不写入 ERP 或订单。当前效率事件不含店铺维度，因此单店 AI 使用显示为待启用。</p>
    <section class="summary-grid" aria-label="店铺准备状态"><article><span>试运行店铺</span><strong>{{ loading ? '读取中' : summary.total }}</strong></article><article><span>待导入商品</span><strong>{{ loading ? '读取中' : summary.needsProduct }}</strong></article><article><span>待维护知识</span><strong>{{ loading ? '读取中' : summary.needsKnowledge }}</strong></article><article><span>可观察</span><strong>{{ loading ? '读取中' : summary.observable }}</strong></article></section>

    <section class="card create-card"><div><h2>创建试运行店铺</h2><p>创建后可从该店铺卡片进入目标绑定的商品导入。店铺编码需与 Excel 数据行一致。</p></div><form @submit.prevent="submit"><label>店铺编码<input v-model="form.store_code" required maxlength="96" /></label><label>店铺名称<input v-model="form.store_name" required maxlength="255" /></label><label>平台<input v-model="form.platform" required maxlength="32" placeholder="例如：pdd" /></label><button class="button" :disabled="creating" type="submit">{{ creating ? '创建中…' : '创建店铺' }}</button></form><p v-if="createError" class="notice error" role="alert">{{ createError }}</p></section>

    <p v-if="loading" class="notice" role="status">正在读取多店铺状态…</p><p v-else-if="listError" class="notice error" role="alert">暂时无法读取店铺状态。{{ listError }}</p><p v-else-if="stores.length === 0" class="notice">待启用：尚未创建试运行店铺。先创建店铺，再导入与维护该店铺的测试数据。</p>
    <section v-else class="store-grid"><article v-for="store in stores" :key="store.store_code" class="card store-card"><div class="store-heading"><div><h2>{{ store.store_name }}</h2><p>{{ store.store_code }} · {{ store.platform }}</p></div><span class="badge">{{ statusText[store.setup_status] }}</span></div><div class="store-metrics"><div><span>商品暂存</span><strong>{{ store.staged_product_count }}</strong><small>SKU {{ store.staged_sku_count }}</small></div><div><span>已导入目录</span><strong>{{ store.catalog_product_count }}</strong><small>SKU {{ store.catalog_sku_count }}</small></div><div><span>FAQ / 规则</span><strong>{{ store.faq_count }} / {{ store.safety_rule_count }}</strong><small>知识包维护</small></div><div><span>案例 / 问题</span><strong>{{ store.experience_case_count }} / {{ store.ai_feedback_count }}</strong><small>按店铺真实记录</small></div></div><p class="subtle">最近商品导入：{{ formatDate(store.latest_product_imported_at) }}</p><p class="subtle">单店 AI 使用：待启用（效率事件为内容无关全局汇总，未记录店铺字段）。</p><div class="store-actions"><RouterLink class="button" :to="`/imports/new?store_code=${encodeURIComponent(store.store_code)}`">导入商品</RouterLink><RouterLink class="button secondary" :to="`/test-data-packages?store_code=${encodeURIComponent(store.store_code)}`">维护知识</RouterLink><RouterLink class="button secondary" to="/experience-cases">审核案例</RouterLink><RouterLink class="button secondary" to="/ai-feedback-optimization-pool">查看 AI 问题</RouterLink></div></article></section>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 18px; color: #76580e; background: #fff8df; }.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }.summary-grid article { padding: 16px; border: 1px solid #dfe7f2; border-radius: 12px; background: #fff; }.summary-grid span { display: block; color: #64748b; font-size: 13px; }.summary-grid strong { display: block; margin-top: 6px; color: #172554; font-size: 25px; }.create-card { display: grid; grid-template-columns: 1fr auto; gap: 22px; margin-bottom: 18px; }.create-card h2 { margin: 0 0 5px; color: #172554; font-size: 18px; }.create-card p { margin: 0; color: #64748b; line-height: 1.5; }.create-card form { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; }.create-card label { display: grid; gap: 5px; color: #526279; font-size: 12px; }.create-card input { min-height: 38px; min-width: 135px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; }.create-card .notice { grid-column: 1 / -1; }.store-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 18px; }.store-card { display: grid; gap: 15px; }.store-heading { display: flex; justify-content: space-between; gap: 12px; }.store-heading h2 { margin: 0 0 4px; color: #172554; font-size: 19px; }.store-heading p, .subtle { margin: 0; color: #64748b; font-size: 13px; }.store-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }.store-metrics div { padding: 11px; border-radius: 9px; background: #f6f8fc; }.store-metrics span, .store-metrics small { display: block; color: #64748b; font-size: 12px; }.store-metrics strong { display: block; margin: 4px 0; color: #172554; font-size: 20px; }.store-actions { display: flex; flex-wrap: wrap; gap: 9px; }.store-actions .button { min-height: 36px; padding: 7px 11px; font-size: 13px; }@media (max-width: 850px) { .summary-grid { grid-template-columns: repeat(2, 1fr); }.create-card { grid-template-columns: 1fr; } }@media (max-width: 520px) { .summary-grid, .store-metrics { grid-template-columns: 1fr; } }
</style>
