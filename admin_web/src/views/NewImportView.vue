<script setup lang="ts">
import { computed, ref } from 'vue'

import { apiErrorMessage, preflightProductSku, productSkuTemplateUrl, uploadProductSku, type ImportBatch, type ProductSkuPreflight } from '../api/client'
import { displayStatus } from '../presentation'

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
const targetStoreCode = ref(new URLSearchParams(window.location.search).get('store_code')?.trim() || '')
const canUpload = computed(() => selectedFile.value !== null && preflightResult.value?.can_import === true)

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
    preflightResult.value = await preflightProductSku(selectedFile.value, targetStoreCode.value || undefined)
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
    result.value = await uploadProductSku(selectedFile.value, (value) => { progress.value = value }, targetStoreCode.value || undefined)
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
        <h1>导入商品与 SKU</h1>
        <p>商品数据先进入待审核暂存区，不会自动发布给 AI。选择目标店铺后，Excel 行内店铺编码必须完全一致。</p>
      </div>
      <RouterLink class="button secondary" to="/imports">返回数据同步</RouterLink>
    </div>

    <p v-if="targetStoreCode" class="notice target-store">目标试运行店铺：<strong>{{ targetStoreCode }}</strong>。此绑定会在预检和正式导入时校验。</p>
    <section class="card import-form">
      <a class="button secondary" :href="productSkuTemplateUrl()" download>下载标准 Excel 模板</a>
      <label><strong>选择 Excel 文件</strong><input type="file" accept=".xlsx" :disabled="preflighting || uploading" @change="onFileChange" /><small>仅支持 .xlsx，最大 5 MB；公式和宏不会被信任或执行。</small></label>
      <p v-if="fileError" class="notice error" role="alert">{{ fileError }}</p>
      <p v-if="selectedFile">已选择：{{ selectedFile.name }}</p>
      <div class="action-row"><button class="button secondary" data-testid="preflight-button" type="button" :disabled="!selectedFile || preflighting || uploading" @click="runPreflight">{{ preflighting ? '预检中…' : '先预检' }}</button><button class="button" data-testid="upload-button" type="button" :disabled="!canUpload || preflighting || uploading" @click="submit">{{ uploading ? `上传中 ${progress}%` : '正式上传并导入' }}</button></div>
      <small v-if="selectedFile && !canUpload">正式上传将在预检通过后开放。</small>
      <p v-if="preflightError" class="notice error" role="alert">{{ preflightError }}</p>

      <section v-if="preflightResult" class="preflight-summary" :class="preflightResult.can_import ? 'passed' : 'blocked'" role="status">
        <h2>{{ preflightResult.can_import ? '预检通过' : '预检未通过' }}</h2><p>{{ preflightResult.original_filename }} · {{ preflightResult.file_size_bytes }} 字节 · 校验值 {{ preflightResult.file_sha256 }}</p>
        <div class="metrics"><span class="metric">数据行<strong>{{ preflightResult.data_row_count }}</strong></span><span class="metric">有效行<strong>{{ preflightResult.valid_rows }}</strong></span><span class="metric">错误行<strong>{{ preflightResult.invalid_rows }}</strong></span><span class="metric">重复行<strong>{{ preflightResult.duplicate_rows }}</strong></span><span class="metric">冲突行<strong>{{ preflightResult.conflict_rows }}</strong></span></div>
        <dl class="preflight-details"><div><dt>工作表</dt><dd>{{ preflightResult.worksheets.join('、') || '无' }}</dd></div><div><dt>缺失列</dt><dd>{{ preflightResult.missing_columns.join('、') || '无' }}</dd></div><div><dt>未知列</dt><dd>{{ preflightResult.unknown_columns.join('、') || '无' }}</dd></div><div><dt>隐藏工作表</dt><dd>{{ preflightResult.hidden_sheet_warnings.join('；') || '无' }}</dd></div></dl>
        <div v-if="preflightResult.error_summary.length" class="issue-list errors"><h3>错误</h3><ul><li v-for="issue in preflightResult.error_summary" :key="issue.code"><strong>{{ issue.code }} × {{ issue.count }}</strong>：{{ issue.message }}</li></ul></div>
        <div v-if="preflightResult.warning_summary.length" class="issue-list warnings"><h3>警告</h3><ul><li v-for="issue in preflightResult.warning_summary" :key="issue.code"><strong>{{ issue.code }} × {{ issue.count }}</strong>：{{ issue.message }}</li></ul></div>
      </section>
      <p v-if="uploadError" class="notice error" role="alert">{{ uploadError }}</p>
      <div v-if="result" class="notice success" role="status"><strong>同步完成：{{ displayStatus(result.status) }}</strong><div class="metrics"><span class="metric">目标店铺<strong>{{ result.target_store_code || '未绑定' }}</strong></span><span class="metric">待审核有效行<strong>{{ result.valid_rows }}</strong></span><span class="metric">错误行<strong>{{ result.invalid_rows }}</strong></span><span class="metric">重复行<strong>{{ result.duplicate_rows }}</strong></span></div><RouterLink class="button secondary" :to="`/imports/${result.id}`">查看同步详情</RouterLink></div>
    </section>
  </main>
</template>

<style scoped>
.import-form { display: grid; gap: 16px; }.target-store { margin-bottom: 18px; color: #365b8d; background: #edf4ff; }label { display: grid; gap: 8px; }label small, small { color: #64748b; }.action-row { display: flex; flex-wrap: wrap; gap: 12px; }.preflight-summary { padding: 18px; border: 1px solid #d7e2ef; border-radius: 10px; }.preflight-summary.passed { border-color: #77b99a; background: #f5fbf8; }.preflight-summary.blocked { border-color: #d99a9a; background: #fff7f7; }.preflight-summary h2, .issue-list h3 { margin-top: 0; }.preflight-details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.preflight-details dt { color: #64748b; font-size: 12px; }.preflight-details dd { margin: 3px 0 0; overflow-wrap: anywhere; }.issue-list { padding: 12px; border-radius: 8px; }.errors { background: #fff0f0; }.warnings { background: #fff8df; }.issue-list ul { margin: 0; padding-left: 20px; }.success { display: grid; gap: 14px; }@media (max-width: 640px) { .preflight-details { grid-template-columns: 1fr; } }
</style>
