<script setup lang="ts">
import { ref } from 'vue'

import {
  apiErrorMessage,
  productSkuTemplateUrl,
  uploadProductSku,
  type ImportBatch,
} from '../api/client'

const MAX_FILE_BYTES = 5 * 1024 * 1024
const selectedFile = ref<File | null>(null)
const fileError = ref('')
const uploading = ref(false)
const progress = ref(0)
const uploadError = ref('')
const result = ref<ImportBatch | null>(null)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  selectedFile.value = null
  fileError.value = ''
  result.value = null
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    fileError.value = '仅支持 .xlsx 文件。'
    input.value = ''
    return
  }
  if (file.size > MAX_FILE_BYTES) {
    fileError.value = '文件不能超过 5 MB。'
    input.value = ''
    return
  }
  selectedFile.value = file
}

async function submit(): Promise<void> {
  if (!selectedFile.value || uploading.value) return
  uploading.value = true
  uploadError.value = ''
  result.value = null
  progress.value = 0
  try {
    result.value = await uploadProductSku(selectedFile.value, (value) => {
      progress.value = value
    })
  } catch (reason: unknown) {
    uploadError.value = apiErrorMessage(reason)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>新建商品与 SKU 导入</h1>
        <p>请使用固定模板；上传后只进入 PENDING_REVIEW。</p>
      </div>
      <RouterLink class="button secondary" to="/imports">返回批次</RouterLink>
    </div>

    <section class="card import-form">
      <a class="button secondary" :href="productSkuTemplateUrl()" download>下载标准 Excel 模板</a>
      <label>
        <strong>选择 Excel 文件</strong>
        <input type="file" accept=".xlsx" @change="onFileChange" />
        <small>仅支持 .xlsx，最大 5 MB；公式和宏不会被信任或执行。</small>
      </label>
      <p v-if="fileError" class="notice error" role="alert">{{ fileError }}</p>
      <p v-if="selectedFile">已选择：{{ selectedFile.name }}</p>
      <button class="button" type="button" :disabled="!selectedFile || uploading" @click="submit">
        {{ uploading ? `上传中 ${progress}%` : '上传并校验' }}
      </button>
      <p v-if="uploadError" class="notice error" role="alert">{{ uploadError }}</p>

      <div v-if="result" class="notice success" role="status">
        <strong>导入完成：{{ result.status }}</strong>
        <div class="metrics">
          <span class="metric">总行数<strong>{{ result.total_rows }}</strong></span>
          <span class="metric">待审核有效行<strong>{{ result.valid_rows }}</strong></span>
          <span class="metric">错误行<strong>{{ result.invalid_rows }}</strong></span>
          <span class="metric">重复行<strong>{{ result.duplicate_rows }}</strong></span>
        </div>
        <RouterLink :to="`/imports/${result.id}`">查看批次详情</RouterLink>
      </div>
    </section>
  </main>
</template>

<style scoped>
.import-form {
  display: grid;
  gap: 20px;
}

label {
  display: grid;
  gap: 8px;
}

input[type='file'] {
  padding: 14px;
  border: 1px dashed #9fb2cc;
  border-radius: 9px;
  background: #f8fafc;
}

small {
  color: #617087;
}
</style>
