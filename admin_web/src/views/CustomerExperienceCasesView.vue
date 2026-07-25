<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  listAdminExperienceCases,
  updateAdminExperienceCaseReview,
  type AdminExperienceCase,
  type ExperienceCaseReviewStatus,
} from '../api/client'

const cases = ref<AdminExperienceCase[]>([])
const selected = ref<AdminExperienceCase | null>(null)
const loading = ref(false)
const error = ref('')
const actionError = ref('')
const reviewNote = ref('')
const reviewedBy = ref('operations-test-operator')
const filters = reactive({
  store_code: '',
  product_id: '',
  sku_id: '',
  review_status: '',
  created_by: '',
  page: 1,
  size: 20,
})
const statuses: ExperienceCaseReviewStatus[] = ['NEW', 'REVIEWING', 'APPROVED', 'REJECTED']
const canReview = computed(() => selected.value !== null && reviewedBy.value.trim().length > 0 && !loading.value)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await listAdminExperienceCases(filters)
    cases.value = result.items
    if (selected.value) {
      selected.value = result.items.find((item) => item.case_id === selected.value?.case_id) || selected.value
    }
  } catch (reason: unknown) {
    cases.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function choose(item: AdminExperienceCase): void {
  selected.value = item
  reviewNote.value = item.review_note || ''
  reviewedBy.value = item.reviewed_by || 'operations-test-operator'
  actionError.value = ''
}

async function transition(reviewStatus: ExperienceCaseReviewStatus): Promise<void> {
  if (!selected.value || !reviewedBy.value.trim()) return
  actionError.value = ''
  try {
    const result = await updateAdminExperienceCaseReview(selected.value.case_id, {
      review_status: reviewStatus,
      review_note: reviewNote.value || null,
      reviewed_by: reviewedBy.value.trim(),
    })
    selected.value = result
    await load()
  } catch (reason: unknown) {
    actionError.value = apiErrorMessage(reason)
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>Customer experience case center</h1>
        <p>Human review only. Approval creates a controlled evaluation snapshot; it never publishes knowledge or changes a prompt.</p>
      </div>
    </div>

    <form class="filters card" @submit.prevent="filters.page = 1; load()">
      <label>Store<input v-model.trim="filters.store_code" /></label>
      <label>Product<input v-model.trim="filters.product_id" /></label>
      <label>SKU<input v-model.trim="filters.sku_id" /></label>
      <label>Submitter<input v-model.trim="filters.created_by" /></label>
      <label>Status<select v-model="filters.review_status"><option value="">All</option><option v-for="status in statuses" :key="status" :value="status">{{ status }}</option></select></label>
      <button class="button" type="submit">Filter cases</button>
    </form>

    <p v-if="loading" class="notice">Loading cases…</p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-else-if="cases.length === 0" class="notice">No cases match the current filters.</p>

    <section v-else class="case-grid">
      <div class="card table-wrap">
        <table class="data-table">
          <thead><tr><th>Case</th><th>Store</th><th>Product / SKU</th><th>Submitter</th><th>Status</th></tr></thead>
          <tbody>
            <tr v-for="item in cases" :key="`${item.case_id}-${item.revision}`">
              <td><button class="link-button" type="button" @click="choose(item)">{{ item.case_id }}</button><small>Revision {{ item.revision }}</small></td>
              <td>{{ item.store_code }}</td>
              <td>{{ item.product_id || '—' }} / {{ item.sku_id || '—' }}</td>
              <td>{{ item.created_by }}</td>
              <td><span class="badge">{{ item.review_status }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <aside v-if="selected" class="card detail">
        <h2>Case detail</h2>
        <dl>
          <div><dt>Customer question</dt><dd>{{ selected.question }}</dd></div>
          <div><dt>AI answer</dt><dd>{{ selected.ai_answer }}</dd></div>
          <div><dt>Final service reply</dt><dd>{{ selected.final_answer }}</dd></div>
          <div><dt>Feedback type</dt><dd>{{ selected.feedback_type }}</dd></div>
          <div><dt>Review record</dt><dd>{{ selected.review_status }} · {{ selected.reviewed_by || 'Not yet reviewed' }}<br>{{ selected.reviewed_at || '—' }}</dd></div>
        </dl>
        <template v-if="selected.review_status === 'NEW' || selected.review_status === 'REVIEWING'">
          <label>Test operator ID<input v-model.trim="reviewedBy" aria-label="Test operator ID" /></label>
          <label>Review note<textarea v-model="reviewNote" maxlength="4000" /></label>
          <p class="subtle">This environment records an unverified test operator ID; formal authorization is not enabled.</p>
          <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>
          <div class="actions">
            <button v-if="selected.review_status === 'NEW'" class="button secondary" :disabled="!canReview" @click="transition('REVIEWING')">Start review</button>
            <template v-else>
              <button class="button" :disabled="!canReview" @click="transition('APPROVED')">Approve snapshot</button>
              <button class="button danger" :disabled="!canReview" @click="transition('REJECTED')">Reject case</button>
            </template>
          </div>
        </template>
        <p v-else class="notice">This terminal revision is immutable. {{ selected.review_status === 'APPROVED' ? 'Its evaluation snapshot is available to A through the controlled export API.' : '' }}</p>
      </aside>
      <aside v-else class="card detail"><h2>Case detail</h2><p>Select a case to view its submitted content and audit record.</p></aside>
    </section>
  </main>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }
label { display: grid; gap: 5px; color: #526279; font-size: 13px; }
input, select, textarea { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }
textarea { min-height: 96px; resize: vertical; }
.case-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }
.detail { display: grid; align-content: start; gap: 14px; }
.detail h2 { margin: 0; }
dl { display: grid; gap: 12px; margin: 0; }
dt { color: #526279; font-size: 12px; font-weight: 700; text-transform: uppercase; }
dd { margin: 4px 0 0; line-height: 1.5; white-space: pre-wrap; }
.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }
small, .subtle { color: #617087; font-size: 12px; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; }
.danger { background: #9c3434; }
@media (max-width: 900px) { .case-grid { grid-template-columns: 1fr; } }
</style>
