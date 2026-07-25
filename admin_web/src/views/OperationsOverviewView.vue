<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAdminOverview,
  getHealth,
  listAiModules,
  type AdminOverview,
} from '../api/client'

const overview = ref<AdminOverview | null>(null)
const platformStatus = ref<'loading' | 'ok' | 'unavailable'>('loading')
const aiStatus = ref<'loading' | 'ok' | 'unavailable'>('loading')
const error = ref('')
const metrics = computed(() => overview.value ? [
  ['Stores', overview.value.counts.stores],
  ['Products', overview.value.counts.products],
  ['SKUs', overview.value.counts.skus],
  ['FAQs', overview.value.counts.faqs],
  ['Safety rules', overview.value.counts.safety_rules],
  ['Sources', overview.value.counts.sources],
  ['Open conflicts', overview.value.counts.conflicts],
  ['Import batches', overview.value.counts.import_batches],
] : [])

async function load(): Promise<void> {
  error.value = ''
  const [overviewResult, platformResult, aiResult] = await Promise.allSettled([
    getAdminOverview(),
    getHealth(),
    listAiModules(),
  ])
  if (overviewResult.status === 'fulfilled') overview.value = overviewResult.value
  else error.value = apiErrorMessage(overviewResult.reason)
  platformStatus.value = platformResult.status === 'fulfilled' ? 'ok' : 'unavailable'
  aiStatus.value = aiResult.status === 'fulfilled' ? 'ok' : 'unavailable'
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>运营概览</h1>
        <p>只展示本地已导入的测试数据；不包含虚构趋势或生产指标。</p>
      </div>
      <button class="button secondary" type="button" @click="load">刷新</button>
    </div>

    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-else-if="!overview" class="notice" role="status">正在读取运营数据…</p>
    <template v-else>
      <p class="notice warning">测试数据模式：{{ overview.test_data_mode ? '开启' : '关闭' }}；生产可用：{{ overview.production_usable ? '是' : '否' }}。</p>
      <section class="metrics" aria-label="真实统计">
        <article v-for="metric in metrics" :key="metric[0]" class="metric">
          {{ metric[0] }}
          <strong>{{ metric[1] }}</strong>
        </article>
      </section>
      <section class="card overview-details">
        <h2>待处理事项</h2>
        <dl>
          <div><dt>待处理冲突</dt><dd>{{ overview.counts.conflicts }}</dd></div>
          <div><dt>已提交建议</dt><dd>{{ overview.counts.suggestions.submitted }}</dd></div>
          <div><dt>审核中建议</dt><dd>{{ overview.counts.suggestions.reviewing }}</dd></div>
          <div><dt>最近导入</dt><dd>{{ overview.recent_imported_at || '暂无' }}</dd></div>
        </dl>
      </section>
    </template>

    <section class="card service-status">
      <h2>服务状态</h2>
      <p><span class="badge">C 平台</span> {{ platformStatus === 'ok' ? '可用' : platformStatus === 'loading' ? '检测中' : '不可用' }}</p>
      <p><span class="badge">A AI 能力中心</span> {{ aiStatus === 'ok' ? '可用' : aiStatus === 'loading' ? '检测中' : '不可用或接口尚未合并' }}</p>
    </section>
  </main>
</template>

<style scoped>
.warning { color: #75570a; background: #fff8df; }
.overview-details, .service-status { margin-top: 20px; }
dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
dt { color: #617087; }
dd { margin: 5px 0 0; font-size: 22px; font-weight: 700; }
</style>
