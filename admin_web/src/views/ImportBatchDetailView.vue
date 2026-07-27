<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  errorReportUrl,
  getImportBatch,
  listImportRows,
  type ImportBatch,
  type ImportRow,
  type RowStatus,
} from '../api/client'
import { displayStatus } from '../presentation'

const props = defineProps<{ batchId: string }>()
const loading = ref(true)
const error = ref('')
const batch = ref<ImportBatch | null>(null)
const rows = ref<ImportRow[]>([])
const status = ref<RowStatus | ''>('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [batchResult, rowResult] = await Promise.all([
      getImportBatch(props.batchId),
      listImportRows(props.batchId, status.value || undefined),
    ])
    batch.value = batchResult
    rows.value = rowResult.items
  } catch (reason: unknown) {
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
        <h1>导入批次详情</h1>
        <p>{{ batchId }}</p>
      </div>
      <RouterLink class="button secondary" to="/imports">返回数据同步</RouterLink>
    </div>

    <p v-if="loading" class="notice" role="status">正在加载批次详情…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取同步详情。{{ error }}</p>
    <template v-else-if="batch">
      <section class="card">
        <div class="summary-row">
          <div>
            <strong>{{ batch.original_filename }}</strong>
            <p><span class="badge">{{ displayStatus(batch.status) }}</span></p>
          </div>
          <a class="button secondary" :href="errorReportUrl(batchId)" download>下载错误报告</a>
        </div>
        <div class="metrics">
          <span class="metric">总行数<strong>{{ batch.total_rows }}</strong></span>
          <span class="metric">待审核行<strong>{{ batch.staged_rows ?? batch.valid_rows }}</strong></span>
          <span class="metric">错误行<strong>{{ batch.invalid_rows }}</strong></span>
          <span class="metric">重复行<strong>{{ batch.duplicate_rows }}</strong></span>
        </div>
      </section>

      <section class="card rows-card">
        <div class="filter-row">
          <label>
            行状态
            <select v-model="status" @change="load">
              <option value="">全部</option>
              <option value="VALID">校验通过</option>
              <option value="INVALID">格式错误</option>
              <option value="DUPLICATE">重复记录</option>
              <option value="CONFLICT">存在冲突</option>
            </select>
          </label>
        </div>
        <p v-if="rows.length === 0" class="notice">当前筛选条件下没有数据行。</p>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>行号</th>
                <th>状态</th>
                <th>商品 / SKU</th>
                <th>错误码</th>
                <th>字段</th>
                <th>原始值</th>
                <th>修改建议</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.id">
                <td>{{ row.source_row_number }}</td>
                <td><span class="badge">{{ displayStatus(row.validation_status) }}</span></td>
                <td>{{ row.normalized_data.product_name }} / {{ row.normalized_data.sku_name }}</td>
                <td>{{ row.errors.map((issue) => issue.error_code).join(', ') || '—' }}</td>
                <td>{{ row.errors.map((issue) => issue.field).filter(Boolean).join(', ') || '—' }}</td>
                <td>{{ row.errors.map((issue) => String(issue.raw_value ?? '')).join(', ') || '—' }}</td>
                <td>{{ row.errors.map((issue) => issue.suggestion).join('；') || '已通过校验' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.summary-row,
.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.rows-card {
  margin-top: 20px;
}

select {
  margin-left: 8px;
  padding: 8px;
}
</style>
