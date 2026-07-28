<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  listAdminSuggestions,
  updateAdminSuggestion,
  type AdminSuggestion,
  type SuggestionStatus,
} from '../api/client'
import { displayStatus } from '../presentation'

const suggestions = ref<AdminSuggestion[]>([])
const selected = ref<AdminSuggestion | null>(null)
const loading = ref(false)
const error = ref('')
const actionError = ref('')
const filters = reactive({ status: '', module_key: '', store_code: '', urgency: '', page: 1, size: 20 })
const internalNote = ref('')
const targetStatus = ref<SuggestionStatus>('REVIEWING')
const statuses: SuggestionStatus[] = ['SUBMITTED', 'REVIEWING', 'PLANNED', 'DONE', 'REJECTED']
const canUpdate = computed(() => selected.value !== null && !loading.value)

function anonymizedReporter(): string { return '已匿名报告人' }

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await listAdminSuggestions(filters)
    suggestions.value = result.items
    if (selected.value) selected.value = result.items.find((item) => item.id === selected.value?.id) || null
  } catch (reason: unknown) {
    suggestions.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function choose(item: AdminSuggestion): void {
  selected.value = item
  targetStatus.value = item.status
  internalNote.value = item.internal_note || ''
  actionError.value = ''
}

async function update(): Promise<void> {
  if (!selected.value) return
  actionError.value = ''
  try {
    const result = await updateAdminSuggestion(selected.value.id, { status: targetStatus.value, internal_note: internalNote.value || null })
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
    <div class="page-header"><div><h1>客服建议审核</h1><p>建议仅支持状态和内部备注处理，不会自动创建开发任务或知识。</p></div></div>
    <form class="filters card" @submit.prevent="filters.page = 1; load()">
      <label>状态<select v-model="filters.status"><option value="">全部</option><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label>
      <label>模块<input v-model.trim="filters.module_key" /></label>
      <label>店铺<input v-model.trim="filters.store_code" /></label>
      <label>紧急程度<input v-model.trim="filters.urgency" /></label>
      <button class="button" type="submit">筛选</button>
    </form>
    <p v-if="loading" class="notice">正在加载…</p><p v-else-if="error" class="notice error" role="alert">{{ error }}</p><p v-else-if="suggestions.length === 0" class="notice">暂无建议。</p>
    <section v-else class="suggestion-grid"><div class="card"><table class="data-table"><thead><tr><th>建议</th><th>状态</th><th>紧急程度</th></tr></thead><tbody><tr v-for="item in suggestions" :key="item.id"><td><button class="link-button" type="button" @click="choose(item)">{{ item.title }}</button><small>{{ anonymizedReporter() }} · {{ item.module_key || '未分类模块' }}</small></td><td><span class="badge">{{ item.status }}</span></td><td>{{ item.urgency || '—' }}</td></tr></tbody></table></div>
      <aside v-if="selected" class="card detail"><h2>建议详情</h2><p>{{ selected.description }}</p><p><small>报告人信息已在界面中匿名化。</small></p><label>状态<select v-model="targetStatus"><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label><label>内部备注<textarea v-model="internalNote" maxlength="2000" /></label><p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p><button class="button" :disabled="!canUpdate" @click="update">保存处理状态</button></aside>
      <aside v-else class="card detail"><h2>建议详情</h2><p>选择一条建议后查看并处理。</p></aside></section>
  </main>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }
label { display: grid; gap: 5px; color: #526279; font-size: 13px; }
input, select, textarea { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }
textarea { min-height: 110px; resize: vertical; }
.suggestion-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, .9fr); gap: 20px; }
.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }
small { display: block; color: #617087; margin-top: 4px; }
.detail { display: grid; align-content: start; gap: 12px; }
@media (max-width: 800px) { .suggestion-grid { grid-template-columns: 1fr; } }
</style>
