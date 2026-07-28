<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAdminOverview,
  getAiKnowledgeStatistics,
  getAiRuntimeStatus,
  getHealth,
  type AdminOverview,
} from '../api/client'
import ProductEmptyState from '../components/ProductEmptyState.vue'

const overview = ref<AdminOverview | null>(null)
const platformStatus = ref<'loading' | 'ok' | 'unavailable'>('loading')
const aiStatus = ref<'loading' | 'ready' | 'not-ready' | 'unavailable'>('loading')
const aiKnowledgeChunks = ref<number | null>(null)
const aiModelConfigured = ref<boolean | null>(null)
const error = ref('')
const aiError = ref('')
const loading = ref(false)

const metrics = computed(() => overview.value ? [
  ['店铺', overview.value.counts.stores, '已导入业务资料'],
  ['商品', overview.value.counts.products, '可核对的商品事实'],
  ['SKU', overview.value.counts.skus, '商品规格与组合关系'],
  ['FAQ', overview.value.counts.faqs, '可追溯的常见问题'],
  ['安全规则', overview.value.counts.safety_rules, '客服回答边界'],
  ['待处理冲突', overview.value.counts.conflicts, '需要人工核对'],
] : [])

const testModeLabel = computed(() => {
  if (!overview.value) return '环境未确认'
  return overview.value.test_data_mode ? '测试 / 试运行数据' : '生产准备数据'
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  aiError.value = ''
  const [overviewResult, platformResult, aiRuntimeResult, aiKnowledgeResult] = await Promise.allSettled([
    getAdminOverview(),
    getHealth(),
    getAiRuntimeStatus(),
    getAiKnowledgeStatistics(),
  ])
  if (overviewResult.status === 'fulfilled') overview.value = overviewResult.value
  else error.value = apiErrorMessage(overviewResult.reason)
  platformStatus.value = platformResult.status === 'fulfilled' ? 'ok' : 'unavailable'
  if (aiRuntimeResult.status === 'fulfilled') {
    aiModelConfigured.value = aiRuntimeResult.value.modelConfigured
    aiStatus.value = aiRuntimeResult.value.ready && aiRuntimeResult.value.modelConfigured ? 'ready' : 'not-ready'
  } else {
    aiStatus.value = 'unavailable'
    aiModelConfigured.value = null
  }
  if (aiKnowledgeResult.status === 'fulfilled') aiKnowledgeChunks.value = aiKnowledgeResult.value.chunkCount
  else aiKnowledgeChunks.value = null
  const failures = [aiRuntimeResult, aiKnowledgeResult]
    .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
  if (failures.length) aiError.value = `AI 运行信息暂时不可读取：${apiErrorMessage(failures[0].reason)}`
  loading.value = false
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI 客服平台 / 首页</p>
        <h1>AI 运营中心</h1>
        <p>查看已经导入的业务资料、待处理事项和 AI 的当前运行信号。这里不展示虚构趋势，也不代表正式生产运营报表。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新概览' }}</button>
    </div>

    <p v-if="error" class="notice error" role="alert">运营数据暂时不可读取：{{ error }}</p>
    <p v-else-if="loading && !overview" class="notice" role="status">正在读取运营数据…</p>

    <template v-if="overview">
      <section class="notice environment-note">
        <strong>{{ testModeLabel }}</strong>：生产可用={{ overview.production_usable ? '是' : '否' }}。当前页面只展示接口返回的即时事实；所有客户和业务动作仍需人工确认。
      </section>
      <section class="metrics" aria-label="业务资料统计">
        <article v-for="metric in metrics" :key="metric[0]" class="metric">
          <span>{{ metric[0] }}</span>
          <strong>{{ metric[1] }}</strong>
          <small>{{ metric[2] }}</small>
        </article>
      </section>

      <section class="overview-grid">
        <article class="card">
          <p class="card-label">待处理事项</p>
          <h2>需要运营关注</h2>
          <dl class="facts">
            <div><dt>数据冲突</dt><dd>{{ overview.counts.conflicts }}</dd></div>
            <div><dt>已提交客服建议</dt><dd>{{ overview.counts.suggestions.submitted }}</dd></div>
            <div><dt>审核中的建议</dt><dd>{{ overview.counts.suggestions.reviewing }}</dd></div>
            <div><dt>最近资料导入</dt><dd>{{ overview.recent_imported_at || '暂无导入记录' }}</dd></div>
          </dl>
        </article>
        <article class="card">
          <p class="card-label">AI 运行状态</p>
          <h2>{{ aiStatus === 'ready' ? 'AI 服务已就绪' : aiStatus === 'not-ready' ? 'AI 服务未满足运行条件' : aiStatus === 'unavailable' ? 'AI 服务不可读取' : '正在读取 AI 状态' }}</h2>
          <dl class="facts">
            <div><dt>模型已配置</dt><dd>{{ aiModelConfigured === null ? '未取得' : aiModelConfigured ? '是' : '否' }}</dd></div>
            <div><dt>运行时知识块</dt><dd>{{ aiKnowledgeChunks ?? '未取得' }}</dd></div>
            <div><dt>平台服务</dt><dd>{{ platformStatus === 'ok' ? '可用' : platformStatus === 'unavailable' ? '不可用' : '检测中' }}</dd></div>
          </dl>
          <p class="subtle">知识块为 A 当前接口统计，不是历史调用量、采用率或质量趋势。</p>
          <RouterLink class="text-link" to="/ai-capabilities">查看 AI 控制中心</RouterLink>
        </article>
      </section>
      <p v-if="aiError" class="notice error" role="alert">{{ aiError }}</p>
    </template>

    <ProductEmptyState
      v-if="!loading && !error && !overview"
      title="暂无可显示的运营数据"
      description="平台服务没有返回运营概览。请先确认测试数据包和商品资料导入状态，页面不会用虚构零值补齐。"
      action-label="前往商品资料导入"
      to="/imports"
    />
  </main>
</template>

<style scoped>
.eyebrow, .card-label { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.environment-note { margin-bottom: 18px; color: #75570a; background: #fff8df; }.metric small { display: block; margin-top: 5px; color: #6b7b91; font-size: 12px; line-height: 1.45; }.overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }.overview-grid h2 { margin: 0 0 15px; color: #172554; font-size: 20px; }.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 0; }.facts dt { color: #617087; font-size: 12px; }.facts dd { margin: 4px 0 0; overflow-wrap: anywhere; font-size: 18px; font-weight: 700; }.subtle { margin: 16px 0 0; color: #6b7b91; font-size: 12px; line-height: 1.55; }.text-link { display: inline-block; margin-top: 10px; font-size: 13px; font-weight: 700; }
@media (max-width: 760px) { .overview-grid, .facts { grid-template-columns: 1fr; } }
</style>
