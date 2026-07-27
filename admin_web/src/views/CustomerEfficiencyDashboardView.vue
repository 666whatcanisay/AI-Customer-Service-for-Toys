<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAdminCustomerEfficiencySummary,
  type CustomerEfficiencySummary,
} from '../api/client'

const summary = ref<CustomerEfficiencySummary | null>(null)
const error = ref('')

const metrics = computed(() => summary.value ? [
  ['AI requests', summary.value.ai_request_count],
  ['Direct adoption', summary.value.direct_adoption_count],
  ['Edited adoption', summary.value.edited_adoption_count],
  ['Not adopted', summary.value.not_adopted_count],
  ['Adoption rate', `${(summary.value.adoption_rate * 100).toFixed(1)}%`],
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
        <h1>Customer efficiency dashboard</h1>
        <p>Aggregate system metrics for the current UTC-day window. This is not an employee ranking or performance-evaluation report.</p>
      </div>
      <button class="button secondary" type="button" @click="load">Refresh</button>
    </div>

    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-else-if="!summary" class="notice" role="status">Loading customer-efficiency summary…</p>
    <template v-else>
      <p class="notice warning">Trial/test operational data only. No customer-service content, employee identity, ranking, or performance assessment is displayed.</p>
      <section class="metrics" aria-label="Customer efficiency system metrics">
        <article v-for="metric in metrics" :key="metric[0]" class="metric">
          {{ metric[0] }}
          <strong>{{ metric[1] }}</strong>
        </article>
      </section>
      <section class="card summary-meta">
        <h2>Summary definition</h2>
        <dl>
          <div><dt>Version</dt><dd>{{ summary.summary_version }}</dd></div>
          <div><dt>Generated at</dt><dd>{{ summary.generated_at }}</dd></div>
          <div><dt>Window</dt><dd>{{ summary.window_start }} to {{ summary.window_end }}</dd></div>
          <div><dt>Adoption formula</dt><dd>(direct adoption + edited adoption) / AI requests</dd></div>
        </dl>
      </section>
    </template>
  </main>
</template>

<style scoped>
.warning { color: #75570a; background: #fff8df; }
.summary-meta { margin-top: 20px; }
dl { display: grid; gap: 14px; }
dt { color: #617087; }
dd { margin: 5px 0 0; overflow-wrap: anywhere; }
</style>
