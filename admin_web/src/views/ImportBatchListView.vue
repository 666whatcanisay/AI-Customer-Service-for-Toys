<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { apiErrorMessage, listImportBatches, type ImportBatch } from '../api/client'
import { displayStatus } from '../presentation'

const loading = ref(true)
const error = ref('')
const batches = ref<ImportBatch[]>([])

function formatDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    batches.value = (await listImportBatches()).items
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
        <h1>数据同步</h1>
        <p>所有有效数据只进入待审核区，不会自动发布给 AI。</p>
      </div>
      <RouterLink class="button" to="/imports/new">同步商品数据</RouterLink>
    </div>

    <section class="card">
      <p v-if="loading" class="notice" role="status">正在加载批次…</p>
      <p v-else-if="error" class="notice error" role="alert"><strong>数据加载失败</strong><br />原因：{{ error }}<br />建议下一步：检查服务状态后重试。</p>
      <p v-else-if="batches.length === 0" class="notice">待启用：尚无数据同步记录。请先同步商品数据。</p>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>批次号</th>
              <th>文件名</th>
              <th>状态</th>
              <th>总行数</th>
              <th>有效</th>
              <th>错误</th>
              <th>重复</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="batch in batches" :key="batch.id">
              <td><RouterLink :to="`/imports/${batch.id}`">{{ batch.id }}</RouterLink></td>
              <td>{{ batch.original_filename }}</td>
              <td><span class="badge">{{ displayStatus(batch.status) }}</span></td>
              <td>{{ batch.total_rows }}</td>
              <td>{{ batch.valid_rows }}</td>
              <td>{{ batch.invalid_rows }}</td>
              <td>{{ batch.duplicate_rows }}</td>
              <td>{{ formatDate(batch.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
