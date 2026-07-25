<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { apiErrorMessage, getPilotOperationDashboard, type PilotOperationDashboard } from '../api/client'

const dashboard = ref<PilotOperationDashboard | null>(null)
const loading = ref(false)
const error = ref('')

const todayMetrics = computed(() => dashboard.value ? [
  ['AI calls', dashboard.value.today.ai_call_count],
  ['Case submissions', dashboard.value.today.case_submission_count],
  ['Pending review', dashboard.value.today.pending_review_count],
  ['Approved cases', dashboard.value.today.approved_case_count],
  ['AI evaluated cases', dashboard.value.today.evaluated_case_count],
] : [])

const experienceMetrics = computed(() => dashboard.value ? [
  ['NEW', dashboard.value.experience_cases.new],
  ['REVIEWING', dashboard.value.experience_cases.reviewing],
  ['APPROVED', dashboard.value.experience_cases.approved],
  ['EVALUATED', dashboard.value.experience_cases.evaluated],
] : [])

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    dashboard.value = await getPilotOperationDashboard()
  } catch (reason: unknown) {
    dashboard.value = null
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
        <h1>Customer-service pilot operations</h1>
        <p>Simple observation of the existing experience-case workflow. This page does not create business records or trigger automation.</p>
      </div>
      <button class="button secondary" :disabled="loading" @click="load">Refresh</button>
    </div>

    <p class="notice warning"><strong>Test / pilot data only.</strong> This is not an official operations report. AI calls are case-linked AI-answer observations, not production telemetry.</p>
    <p v-if="loading" class="notice">Loading pilot observations…</p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>

    <template v-else-if="dashboard">
      <section aria-label="Today's pilot observations">
        <h2>Today</h2>
        <div class="metrics">
          <article v-for="metric in todayMetrics" :key="metric[0]" class="metric">
            {{ metric[0] }}
            <strong>{{ metric[1] }}</strong>
          </article>
        </div>
      </section>

      <section class="card status-card" aria-label="Experience case status counts">
        <h2>Experience cases</h2>
        <div class="metrics compact">
          <article v-for="metric in experienceMetrics" :key="metric[0]" class="metric">
            {{ metric[0] }}
            <strong>{{ metric[1] }}</strong>
          </article>
        </div>
      </section>

      <section class="card questions" aria-label="Frequent questions">
        <h2>Frequent questions</h2>
        <p>Exact question text grouped from existing experience cases. No semantic clustering or complex analysis is applied.</p>
        <div class="table-wrap">
          <table v-if="dashboard.frequent_questions.length" class="data-table">
            <thead><tr><th>Rank</th><th>Question</th><th>Cases</th></tr></thead>
            <tbody><tr v-for="(item, index) in dashboard.frequent_questions" :key="item.question"><td>{{ index + 1 }}</td><td>{{ item.question }}</td><td>{{ item.case_count }}</td></tr></tbody>
          </table>
          <p v-else class="notice">No experience cases have been submitted yet.</p>
        </div>
      </section>

      <p class="generated">Generated {{ dashboard.generated_at }} · {{ dashboard.data_mode }}</p>
    </template>
  </main>
</template>

<style scoped>
.warning { color: #75570a; background: #fff8df; }
h2 { margin: 28px 0 12px; font-size: 19px; }
.status-card, .questions { margin-top: 20px; }
.compact { margin-bottom: 0; }
.questions h2 { margin-top: 0; }
.questions > p { margin-top: 0; color: #617087; }
.generated { margin: 20px 0 0; color: #617087; font-size: 13px; }
</style>
