<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  apiErrorMessage,
  preflightProductSku,
  productSkuTemplateUrl,
  uploadProductSku,
  type ImportBatch,
  type ProductSkuPreflight,
} from '../api/client'

const MAX_FILE_BYTES = 5 * 1024 * 1024
const selectedFile = ref<File | null>(null)
const fileError = ref('')
const preflighting = ref(false)
const preflightError = ref('')
const preflightResult = ref<ProductSkuPreflight | null>(null)
const uploading = ref(false)
const progress = ref(0)
const uploadError = ref('')
const result = ref<ImportBatch | null>(null)
const canUpload = computed(
  () => selectedFile.value !== null && preflightResult.value?.can_import === true,
)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  selectedFile.value = null
  fileError.value = ''
  preflightError.value = ''
  preflightResult.value = null
  uploadError.value = ''
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

async function runPreflight(): Promise<void> {
  if (!selectedFile.value || preflighting.value || uploading.value) return
  preflighting.value = true
  preflightError.value = ''
  preflightResult.value = null
  uploadError.value = ''
  result.value = null
  try {
    preflightResult.value = await preflightProductSku(selectedFile.value)
  } catch (reason: unknown) {
    preflightError.value = apiErrorMessage(reason)
  } finally {
    preflighting.value = false
  }
}

async function submit(): Promise<void> {
  if (!selectedFile.value || !canUpload.value || uploading.value) return
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
        <input
          type="file"
          accept=".xlsx"
          :disabled="preflighting || uploading"
          @change="onFileChange"
        />
        <small>仅支持 .xlsx，最大 5 MB；公式和宏不会被信任或执行。</small>
      </label>
      <p v-if="fileError" class="notice error" role="alert">{{ fileError }}</p>
      <p v-if="selectedFile">已选择：{{ selectedFile.name }}</p>

      <div class="action-row">
        <button
          class="button secondary"
          data-testid="preflight-button"
          type="button"
          :disabled="!selectedFile || preflighting || uploading"
          @click="runPreflight"
        >
          {{ preflighting ? '预检中…' : '先预检' }}
        </button>
        <button
          class="button"
          data-testid="upload-button"
          type="button"
          :disabled="!canUpload || preflighting || uploading"
          @click="submit"
        >
          {{ uploading ? `上传中 ${progress}%` : '正式上传并导入' }}
        </button>
      </div>
      <small v-if="selectedFile && !canUpload">正式上传将在预检通过后开放。</small>
      <p v-if="preflightError" class="notice error" role="alert">{{ preflightError }}</p>

      <section
        v-if="preflightResult"
        class="preflight-summary"
        :class="preflightResult.can_import ? 'passed' : 'blocked'"
        role="status"
      >
        <h2>{{ preflightResult.can_import ? '预检通过' : '预检未通过' }}</h2>
        <p>
          {{ preflightResult.original_filename }} · {{ preflightResult.file_size_bytes }} bytes ·
          SHA-256 {{ preflightResult.file_sha256 }}
        </p>
        <div class="metrics">
          <span class="metric">数据行<strong>{{ preflightResult.data_row_count }}</strong></span>
          <span class="metric">有效行<strong>{{ preflightResult.valid_rows }}</strong></span>
          <span class="metric">错误行<strong>{{ preflightResult.invalid_rows }}</strong></span>
          <span class="metric">重复行<strong>{{ preflightResult.duplicate_rows }}</strong></span>
          <span class="metric">冲突行<strong>{{ preflightResult.conflict_rows }}</strong></span>
          <span class="metric">公式单元格<strong>{{ preflightResult.formula_cell_count }}</strong></span>
          <span class="metric">空白行<strong>{{ preflightResult.blank_row_count }}</strong></span>
        </div>
        <dl class="preflight-details">
          <div><dt>工作表</dt><dd>{{ preflightResult.worksheets.join('、') || '无' }}</dd></div>
          <div><dt>缺失列</dt><dd>{{ preflightResult.missing_columns.join('、') || '无' }}</dd></div>
          <div><dt>未知列</dt><dd>{{ preflightResult.unknown_columns.join('、') || '无' }}</dd></div>
          <div>
            <dt>隐藏工作表</dt>
            <dd>{{ preflightResult.hidden_sheet_warnings.join('；') || '无' }}</dd>
          </div>
        </dl>
        <div v-if="preflightResult.error_summary.length" class="issue-list errors">
          <h3>错误</h3>
          <ul>
            <li v-for="issue in preflightResult.error_summary" :key="issue.code">
              <strong>{{ issue.code }} × {{ issue.count }}</strong>：{{ issue.message }}
            </li>
          </ul>
        </div>
        <div v-if="preflightResult.warning_summary.length" class="issue-list warnings">
          <h3>警告</h3>
          <ul>
            <li v-for="issue in preflightResult.warning_summary" :key="issue.code">
              <strong>{{ issue.code }} × {{ issue.count }}</strong>：{{ issue.message }}
            </li>
          </ul>
        </div>
      </section>

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

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.preflight-summary {
  padding: 20px;
  border: 1px solid #c9d5e5;
  border-radius: 12px;
  background: #f8fafc;
}

.preflight-summary.passed {
  border-color: #77b99a;
}

.preflight-summary.blocked {
  border-color: #d99a9a;
}

.preflight-summary h2,
.preflight-summary h3 {
  margin-top: 0;
}

.preflight-details {
  display: grid;
  gap: 8px;
}

.preflight-details div {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 12px;
}

.preflight-details dt {
  font-weight: 700;
}

.preflight-details dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.issue-list ul {
  margin-bottom: 0;
}

.issue-list.errors {
  color: #8c2929;
}

.issue-list.warnings {
  color: #76551b;
}
</style>
