<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { apiErrorMessage, listAdminResource, type AdminResource } from '../api/client'
import { displayStatus } from '../presentation'

interface Column {
  key: string
  label: string
}

const props = defineProps<{
  resource: AdminResource
  title: string
  description: string
  columns: Column[]
}>()

const rows = ref<Record<string, unknown>[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const filters = reactive({ keyword: '', store_code: '', product_id: '', status: '', page: 1, size: 20 })

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / filters.size)))

function value(row: Record<string, unknown>, key: string): string {
  const raw = row[key]
  if (Array.isArray(raw)) return raw.join(', ')
  if (raw === null || raw === undefined || raw === '') return '—'
  if (typeof raw === 'boolean') return raw ? '是' : '否'
  if (typeof raw === 'string' && [
    'sales_status', 'review_status', 'risk_level', 'answer_action', 'status', 'relation_type', 'source_type',
  ].includes(key)) return displayStatus(raw)
  return String(raw)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await listAdminResource<Record<string, unknown>>(props.resource, filters)
    rows.value = result.items
    total.value = result.total
  } catch (reason: unknown) {
    rows.value = []
    total.value = 0
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function search(): void {
  filters.page = 1
  void load()
}

function changePage(next: number): void {
  filters.page = Math.min(Math.max(1, next), pageCount.value)
  void load()
}

watch(() => props.resource, () => { filters.page = 1; void load() })
onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div><h1>{{ title }}</h1><p>{{ description }} 只读，不提供发布或编辑操作。</p></div>
    </div>
    <form class="filters card" @submit.prevent="search">
      <label>关键词<input v-model.trim="filters.keyword" type="search" placeholder="搜索" /></label>
      <label>状态 / 风险<input v-model.trim="filters.status" type="search" placeholder="可选" /></label>
      <button class="button" type="submit">筛选</button>
    </form>
    <p v-if="loading" class="notice" role="status">正在加载…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取{{ title }}。{{ error }}</p>
    <p v-else-if="rows.length === 0" class="notice">暂无符合当前筛选条件的{{ title }}。请调整筛选条件，或先完成数据导入与审核。</p>
    <div v-else class="card table-wrap readonly-table-wrap">
      <table class="data-table readonly-list-table" :class="{ 'source-table': resource === 'sources' }">
        <thead><tr><th v-for="column in columns" :key="column.key">{{ column.label }}</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="value(row, columns[0]?.key || 'id')">
            <td
              v-for="column in columns"
              :key="column.key"
              :class="{
                'source-type-cell': resource === 'sources' && column.key === 'source_type',
                'source-file-cell': resource === 'sources' && column.key === 'file_name',
                'source-hash-cell': resource === 'sources' && column.key === 'file_sha256',
              }"
            >
              <RouterLink v-if="resource === 'products' && column.key === 'product_id'" :to="`/products/${encodeURIComponent(value(row, column.key))}`">{{ value(row, column.key) }}</RouterLink>
              <span v-else>{{ value(row, column.key) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pager" aria-label="分页">
      <button class="button secondary" :disabled="filters.page <= 1 || loading" @click="changePage(filters.page - 1)">上一页</button>
      <span>第 {{ filters.page }} / {{ pageCount }} 页，共 {{ total }} 条</span>
      <button class="button secondary" :disabled="filters.page >= pageCount || loading" @click="changePage(filters.page + 1)">下一页</button>
    </div>
  </main>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }
label { display: grid; gap: 5px; color: #526279; font-size: 13px; }
input { min-height: 38px; min-width: 130px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }
.readonly-table-wrap { max-width: 100%; overflow-x: auto; }
.source-table { table-layout: fixed; }
.source-table th:nth-child(1) { width: 18%; }
.source-table th:nth-child(2) { width: 21%; }
.source-table th:nth-child(3) { width: 34%; }
.source-table th:nth-child(4) { width: 17%; }
.source-table th:nth-child(5) { width: 10%; }
.source-type-cell, .source-file-cell, .source-hash-cell { overflow-wrap: anywhere; word-break: break-word; }
.source-hash-cell { color: #33445c; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
.pager { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 20px; }
</style>
