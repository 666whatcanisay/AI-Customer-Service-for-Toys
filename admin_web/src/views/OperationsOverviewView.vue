<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAdminOverview,
  getHealth,
  listAiFeedbackAnalysisResults,
  listKnowledgeMaterials,
  listKnowledgeQualityAssessments,
  type AdminOverview,
} from '../api/client'

const overview = ref<AdminOverview | null>(null)
const loading = ref(false)
const overviewError = ref('')
const platformAvailable = ref<'loading' | 'available' | 'unavailable'>('loading')
const materialTotal = ref<number | null>(null)
const materialUnavailable = ref(false)
const qualityTotal = ref<number | null>(null)
const qualityUnavailable = ref(false)
const feedbackTotal = ref<number | null>(null)
const feedbackUnavailable = ref(false)

const catalogMetrics = computed(() => overview.value ? [
  { label: '店铺', value: overview.value.counts.stores },
  { label: '商品', value: overview.value.counts.products },
  { label: 'SKU', value: overview.value.counts.skus },
  { label: 'FAQ', value: overview.value.counts.faqs },
] : [])

function displayedTotal(total: number | null, unavailable: boolean): string {
  if (unavailable || total === null) return '暂无法读取'
  return String(total)
}

async function load(): Promise<void> {
  if (loading.value) return
  loading.value = true
  overviewError.value = ''
  materialTotal.value = null
  materialUnavailable.value = false
  qualityTotal.value = null
  qualityUnavailable.value = false
  feedbackTotal.value = null
  feedbackUnavailable.value = false

  const [overviewResult, healthResult, materialsResult, qualityResult, feedbackResult] = await Promise.allSettled([
    getAdminOverview(),
    getHealth(),
    listKnowledgeMaterials({ page: 1, size: 1 }),
    listKnowledgeQualityAssessments(),
    listAiFeedbackAnalysisResults(),
  ])

  if (overviewResult.status === 'fulfilled') overview.value = overviewResult.value
  else {
    overview.value = null
    overviewError.value = apiErrorMessage(overviewResult.reason)
  }
  platformAvailable.value = healthResult.status === 'fulfilled' ? 'available' : 'unavailable'
  if (materialsResult.status === 'fulfilled') materialTotal.value = materialsResult.value.total
  else materialUnavailable.value = true
  if (qualityResult.status === 'fulfilled') qualityTotal.value = qualityResult.value.total
  else qualityUnavailable.value = true
  if (feedbackResult.status === 'fulfilled') feedbackTotal.value = feedbackResult.value.total
  else feedbackUnavailable.value = true
  loading.value = false
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI客服平台 · 运营首页</p>
        <h1>今天从哪里开始？</h1>
        <p>先看商品资料和待处理问题，再进入客服与 AI 工作区。所有数据均来自当前平台；不会展示虚构趋势。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新概览' }}</button>
    </div>

    <p v-if="loading && !overview" class="notice" role="status">正在读取运营概览…</p>
    <section v-else-if="overviewError" class="card unavailable" role="alert">
      <h2>运营数据暂时无法读取</h2>
      <p>{{ overviewError }}</p>
      <p>这不是“暂无数据”。请先检查平台服务状态，再重新刷新。</p>
    </section>

    <template v-else-if="overview">
      <p class="notice warning">{{ overview.test_data_mode ? '当前为测试环境：仅使用测试或已去标识化资料。' : '当前不是测试数据模式：仍请保持人工审核和确认。' }} {{ overview.production_usable ? '生产可用标记已开启。' : '生产可用标记未开启。' }}</p>
      <section class="metrics" aria-label="已导入业务资料">
        <article v-for="metric in catalogMetrics" :key="metric.label" class="metric"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></article>
      </section>

      <section class="next-grid" aria-label="运营待办">
        <RouterLink class="next-card primary" to="/knowledge-center">
          <span>商品知识</span><strong>{{ displayedTotal(materialTotal, materialUnavailable) }}</strong>
          <small>{{ materialUnavailable ? '资料记录接口暂时不可用，请稍后刷新。' : '份受控资料记录，进入知识中心继续审核。' }}</small>
        </RouterLink>
        <RouterLink class="next-card" to="/knowledge-quality-pool">
          <span>知识质量</span><strong>{{ displayedTotal(qualityTotal, qualityUnavailable) }}</strong>
          <small>{{ qualityUnavailable ? '质量分析接口暂时不可用，请稍后刷新。' : '条已完成分析，查看待补充项和修正建议。' }}</small>
        </RouterLink>
        <RouterLink class="next-card" to="/ai-feedback-optimization-pool">
          <span>AI 问题</span><strong>{{ displayedTotal(feedbackTotal, feedbackUnavailable) }}</strong>
          <small>{{ feedbackUnavailable ? 'AI 问题接口暂时不可用，请稍后刷新。' : '条已分析反馈，查看原因与建议。' }}</small>
        </RouterLink>
        <RouterLink class="next-card" to="/customer-operations">
          <span>客服运营</span><strong>{{ overview.counts.suggestions.submitted }}</strong>
          <small>条已提交运营建议；查看客服案例、问题和建议。</small>
        </RouterLink>
      </section>

      <section class="workbench-grid">
        <RouterLink class="workbench-link" to="/import-center"><strong>导入中心</strong><span>下载模板，预检商品与 SKU，或准备待审核资料。</span></RouterLink>
        <RouterLink class="workbench-link" to="/knowledge-materials"><strong>资料上传与审核</strong><span>查看识别摘要，人工确认后才可供 AI 分析。</span></RouterLink>
        <RouterLink class="workbench-link" to="/ai-capabilities"><strong>AI 控制中心</strong><span>查看模型、知识、运行和评测状态；不提供自动化操作。</span></RouterLink>
      </section>
    </template>

    <section class="card service-status">
      <h2>平台状态</h2>
      <p><span class="badge">C 平台</span> {{ platformAvailable === 'available' ? '可用' : platformAvailable === 'loading' ? '检测中' : '暂时不可用' }}</p>
      <p>AI 状态请在“AI 控制中心”查看。该页只使用 A 冻结的只读控制面，不以 C 的探测结果替代 AI 真实状态。</p>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.warning { margin-bottom: 20px; color: #75570a; background: #fff8df; }
.unavailable { border-left: 5px solid #c77a16; }
.unavailable h2, .service-status h2 { margin-top: 0; color: #172554; }
.metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0 0 20px; }
.metric { display: grid; gap: 7px; border: 1px solid #dfe7f2; background: #fff; }
.metric span, .next-card span { color: #617087; font-size: 13px; }
.next-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.next-card { display: grid; gap: 7px; min-height: 150px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }
.next-card.primary { border-color: #92b5e8; background: linear-gradient(145deg, #f5f9ff, #fff); }
.next-card strong { color: #172554; font-size: 28px; }
.next-card small { color: #617087; line-height: 1.55; }
.workbench-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
.workbench-link { display: grid; gap: 8px; min-height: 116px; padding: 17px; border: 1px solid #dbe4ef; border-radius: 12px; color: #25466f; background: #fff; text-decoration: none; }
.workbench-link span, .service-status p { color: #617087; font-size: 13px; line-height: 1.55; }
.service-status { margin-top: 20px; }
@media (max-width: 1050px) { .metrics, .next-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .workbench-grid { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .metrics, .next-grid { grid-template-columns: 1fr; } }
</style>
