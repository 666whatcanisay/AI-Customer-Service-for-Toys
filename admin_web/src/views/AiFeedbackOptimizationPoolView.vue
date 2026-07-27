<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  listAiFeedbackAnalysisResults,
  type AiFeedbackAnalysisResult,
} from '../api/client'

const results = ref<AiFeedbackAnalysisResult[]>([])
const selected = ref<AiFeedbackAnalysisResult | null>(null)
const loading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await listAiFeedbackAnalysisResults()
    results.value = response.items
    if (selected.value) {
      selected.value = response.items.find((item) => item.feedback_id === selected.value?.feedback_id) || null
    }
  } catch (reason: unknown) {
    results.value = []
    selected.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function choose(item: AiFeedbackAnalysisResult): void {
  selected.value = item
}

function formatted(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>AI optimization pool</h1>
        <p>Read-only completed AI feedback analysis evidence. No prompt, knowledge, or business-action controls are available.</p>
      </div>
    </div>

    <p v-if="loading" class="notice">Loading analyzed feedback…</p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-else-if="results.length === 0" class="notice">No completed AI feedback analyses are available.</p>

    <section v-else class="pool-grid">
      <div class="card table-wrap">
        <table class="data-table">
          <thead><tr><th>Question</th><th>Type</th><th>AI analysis</th><th>Status</th><th>Model</th><th>Prompt</th></tr></thead>
          <tbody>
            <tr v-for="item in results" :key="`${item.feedback_id}-${item.revision}`">
              <td><button class="link-button" type="button" @click="choose(item)">{{ item.question }}</button><small>{{ item.feedback_id }}</small></td>
              <td><span class="badge">{{ item.feedback_type }}</span></td>
              <td>{{ formatted(item.analysis) }}</td>
              <td><span class="badge">{{ item.analysis_status }}</span></td>
              <td>{{ item.model_version }}</td>
              <td>{{ item.prompt_version }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <aside v-if="selected" class="card detail">
        <h2>Analysis detail</h2>
        <p><strong>Customer question</strong><br>{{ selected.question }}</p>
        <p><strong>AI answer</strong><br>{{ selected.ai_answer }}</p>
        <p><strong>Final service reply</strong><br>{{ selected.final_answer || 'No final reply supplied' }}</p>
        <p><strong>AI analysis</strong></p><pre>{{ formatted(selected.analysis) }}</pre>
        <p><strong>Suggestions</strong></p><pre>{{ formatted(selected.suggestions) }}</pre>
        <p><strong>Evidence version</strong><br>Revision {{ selected.revision }} · {{ selected.content_hash }}<br>{{ selected.analysis_run_id }} · {{ selected.created_at }}</p>
      </aside>
      <aside v-else class="card detail"><h2>Analysis detail</h2><p>Select a completed feedback analysis to inspect its evidence.</p></aside>
    </section>
  </main>
</template>

<style scoped>
.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }
.detail { display: grid; align-content: start; gap: 12px; }
.detail h2, .detail p { margin: 0; }
.detail p { line-height: 1.5; overflow-wrap: anywhere; white-space: pre-wrap; }
.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }
small { display: block; margin-top: 4px; color: #617087; }
pre { max-width: 100%; margin: 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }
td:nth-child(3) { min-width: 180px; white-space: pre-wrap; }
@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
