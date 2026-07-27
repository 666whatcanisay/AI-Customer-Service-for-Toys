<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { apiErrorMessage, getAdminCustomerEfficiencySummary, type CustomerEfficiencySummary } from '../api/client'

const summary = ref<CustomerEfficiencySummary | null>(null)
const error = ref('')

const hasSamples = computed(() => (summary.value?.ai_request_count || 0) > 0)
const metrics = computed(() => summary.value ? [
  ['AI 请求次数', summary.value.ai_request_count],
  ['直接采用', summary.value.direct_adoption_count],
  ['编辑采用', summary.value.edited_adoption_count],
  ['未采用', summary.value.not_adopted_count],
  ['采用率', hasSamples.value ? `${(summary.value.adoption_rate * 100).toFixed(1)}%` : '样本不足'],
] : [])

async function load(): Promise<void> {
  error.value = ''
  try {
    summary.value = await getAdminCustomerEfficiencySummary()
  } catch (reason: unknown) {
    summary.value = null
    error.value = apiErrorMessage(reason)
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>客服效率分析</h1>
        <p>展示当前统计窗口内的系统汇总，帮助观察 AI 在客服回复中的使用情况；不展示员工身份、排名或绩效评价。</p>
      </div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>

    <p v-if="error" class="notice error" role="alert">暂时无法读取效率摘要。{{ error }}</p>
    <p v-else-if="!summary" class="notice" role="status">正在读取效率摘要…</p>
    <template v-else>
      <p v-if="!hasSamples" class="notice warning">样本不足：当前统计窗口没有 AI 请求，不展示推断性采用率。</p>
      <p v-else class="notice warning">当前为测试/试运行汇总数据，不含客服内容、员工身份、排名或绩效结论。</p>
      <section class="metrics" aria-label="客服效率系统指标">
        <article v-for="metric in metrics" :key="metric[0]" class="metric">
          {{ metric[0] }}
          <strong>{{ metric[1] }}</strong>
        </article>
      </section>
      <section class="card summary-meta">
        <h2>统计口径</h2>
        <dl>
          <div><dt>统计窗口</dt><dd>{{ summary.window_start }} 至 {{ summary.window_end }}</dd></div>
          <div><dt>采用率</dt><dd>（直接采用 + 编辑采用）/ AI 请求次数</dd></div>
          <div><dt>摘要版本</dt><dd>{{ summary.summary_version }}</dd></div>
          <div><dt>生成时间</dt><dd>{{ summary.generated_at }}</dd></div>
        </dl>
      </section>
    </template>
  </main>
</template>

<style scoped>
.warning { color: #75570a; background: #fff8df; }.summary-meta { margin-top: 20px; }.summary-meta h2 { margin: 0 0 17px; color: #172554; font-size: 18px; }dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }dt { color: #64748b; font-size: 13px; }dd { margin: 5px 0 0; color: #334155; overflow-wrap: anywhere; }@media (max-width: 650px) { dl { grid-template-columns: 1fr; } }
</style>
