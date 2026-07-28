<script setup lang="ts">
import { computed, ref } from 'vue'

import { apiErrorMessage, preflightProductSku, productSkuTemplateUrl, uploadProductSku, type ImportBatch, type ProductSkuPreflight } from '../api/client'
import { displayStatus } from '../presentation'

const MAX_FILE_BYTES = 5 * 1024 * 1024
const fieldLabels: Record<string, string> = {
  tenant_id: '租户标识', platform: '平台', store_code: '店铺编码', product_code: '商品编码', platform_product_id: '平台商品 ID', product_name: '商品名称', sku_code: 'SKU 编码', platform_sku_id: '平台 SKU ID', sku_name: 'SKU 名称', specifications: '规格', applicable_age_min: '适用年龄下限', applicable_age_max: '适用年龄上限', material: '材质', package_contents: '包装内容', source_name: '来源名称', effective_from: '生效开始日期', effective_to: '生效结束日期', notes: '备注',
}
const issueLabels: Record<string, string> = {
  INVALID_TEMPLATE: '模板格式需要调整', REQUIRED_FIELD_MISSING: '必填项缺失', INVALID_PLATFORM: '平台名称不正确', INVALID_INTEGER: '数字格式不正确', AGE_RANGE_INVALID: '适用年龄范围不正确', PRODUCT_IDENTIFIER_MISSING: '缺少商品编码', SKU_IDENTIFIER_MISSING: '缺少 SKU 编码', DUPLICATE_ROW: '存在重复记录', CONFLICT_REQUIRES_REVIEW: '存在需要人工确认的冲突', FORMULA_NOT_ALLOWED: '不支持公式单元格', BLANK_ROWS_IGNORED: '空白行已忽略',
}
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
const missingFields = computed(() => Object.entries(preflightResult.value?.missing_field_counts || {})
  .map(([field, count]) => `${fieldLabels[field] || field}（${count} 行）`))

function issueLabel(code: string): string { return issueLabels[code] || '需要人工查看' }
function issueMessage(code: string): string {
  return {
    INVALID_TEMPLATE: '请使用下载的模板，保留工作表、字段名称和字段顺序。',
    REQUIRED_FIELD_MISSING: '请补齐对应的必填资料，并确认来源可靠。',
    INVALID_PLATFORM: '请使用系统支持的平台名称。',
    INVALID_INTEGER: '适用年龄需要填写为非负整数。',
    AGE_RANGE_INVALID: '适用年龄下限不能大于上限。',
    PRODUCT_IDENTIFIER_MISSING: '商品编码或平台商品 ID 至少需要填写一个。',
    SKU_IDENTIFIER_MISSING: 'SKU 编码或平台 SKU ID 至少需要填写一个。',
    DUPLICATE_ROW: '请删除重复行，只保留一条已核对资料。',
    CONFLICT_REQUIRES_REVIEW: '相同商品或 SKU 的资料不一致，请人工确认后再导入。',
    FORMULA_NOT_ALLOWED: '请把公式改为已核对的静态值。',
    BLANK_ROWS_IGNORED: '空白行不会导入，无需处理。',
  }[code] || '请核对资料并按模板要求修正后重新预检。'
}

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
    fileError.value = '仅支持 .xlsx 文件。请先下载并使用商品与 SKU 模板。'
    input.value = ''
    return
  }
  if (file.size > MAX_FILE_BYTES) {
    fileError.value = '文件不能超过 5 MB。请拆分数据后重新预检。'
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
    <div class="page-header"><div><h1>商品与 SKU 导入</h1><p>按向导准备商品资料。数据会先进入待审核暂存区，不会自动发布给 AI，也不会修改订单或 ERP。</p></div><RouterLink class="button secondary" to="/imports">查看导入记录</RouterLink></div>
    <p v-if="targetStoreCode" class="notice target-store">目标试运行店铺：<strong>{{ targetStoreCode }}</strong>。预检和导入都会核对模板中的店铺编码。</p>

    <section class="guide-grid">
      <article class="card"><h2>先准备这些数据</h2><ul><li>商品名称与商品编码</li><li>SKU 名称与 SKU 编码</li><li>适用年龄、核心卖点、材质和包装内容</li><li>风险提醒与可参考问答的来源信息</li></ul><p class="subtle">商品编码和 SKU 编码至少可使用对应的平台 ID 之一，但必须来自已核对的资料。</p></article>
      <article class="card"><h2>填写说明</h2><p>下载模板后保留表头和顺序。每一行代表一个商品与 SKU 的组合；相同资料请勿重复填写。</p><p class="subtle">示例：一个商品有三种款式时，填写三行，商品信息相同、SKU 信息不同。</p></article>
      <article class="card"><h2>文件要求</h2><p>仅支持 Excel .xlsx，文件不超过 5 MB。系统不会执行公式或宏，含公式的单元格需要改为已核对的静态值。</p><p class="subtle">先预检，再正式导入；预检不写入数据。</p></article>
    </section>

    <section class="card import-form">
      <div class="form-heading"><div><h2>第 1 步：下载并填写模板</h2><p>模板包含字段说明和示例。填写完成后回到这里选择文件。</p></div><a class="button secondary" :href="productSkuTemplateUrl()" download>下载商品与 SKU 模板</a></div>
      <ol class="steps"><li><strong>第一步：下载模板</strong><span>使用标准字段，不修改表头。</span></li><li><strong>第二步：按示例填写</strong><span>补齐商品、SKU、年龄、来源和风险信息。</span></li><li><strong>第三步：上传并预检</strong><span>先查看识别结果和缺失项。</span></li><li><strong>第四步：正式导入</strong><span>仅在预检通过后开放。</span></li></ol>
      <label><strong>第 2 步：选择 Excel 文件</strong><input type="file" accept=".xlsx" :disabled="preflighting || uploading" @change="onFileChange" /><small>支持 .xlsx，最大 5 MB；不会信任或执行公式、宏。</small></label>
      <p v-if="fileError" class="notice error" role="alert"><strong>文件无法使用</strong><br />原因：{{ fileError }}<br />建议下一步：下载标准模板后重新填写。</p>
      <p v-if="selectedFile" class="selected-file">已选择：{{ selectedFile.name }}</p>
      <div class="action-row"><button class="button secondary" data-testid="preflight-button" type="button" :disabled="!selectedFile || preflighting || uploading" @click="runPreflight">{{ preflighting ? '正在预检…' : '第 3 步：上传并预检' }}</button><button class="button" data-testid="upload-button" type="button" :disabled="!canUpload || preflighting || uploading" @click="submit">{{ uploading ? `正在导入 ${progress}%` : '第 4 步：正式导入' }}</button></div>
      <small v-if="selectedFile && !canUpload">正式导入会在预检通过后开放。</small>
      <p v-if="preflightError" class="notice error" role="alert"><strong>数据加载失败</strong><br />原因：{{ preflightError }}<br />建议下一步：检查文件格式和服务状态后重试。</p>

      <section v-if="preflightResult" class="preflight-summary" :class="preflightResult.can_import ? 'passed' : 'blocked'" role="status">
        <h2>{{ preflightResult.can_import ? '预检通过，可以正式导入' : '预检未通过，请先补齐资料' }}</h2><p>{{ preflightResult.original_filename }} · {{ preflightResult.file_size_bytes }} 字节</p>
        <h3>系统识别结果</h3>
        <div class="metrics"><span class="metric">识别到商品<strong>{{ preflightResult.recognized_product_count }}</strong></span><span class="metric">识别到 SKU<strong>{{ preflightResult.recognized_sku_count }}</strong></span><span class="metric">待人工补充<strong>{{ preflightResult.rows_needing_manual_completion }}</strong></span><span class="metric">有效行<strong>{{ preflightResult.valid_rows }}</strong></span><span class="metric">重复或冲突行<strong>{{ preflightResult.duplicate_rows + preflightResult.conflict_rows }}</strong></span></div>
        <dl class="preflight-details"><div><dt>缺少字段</dt><dd>{{ missingFields.join('、') || '无' }}</dd></div><div><dt>缺失模板列</dt><dd>{{ preflightResult.missing_columns.map((field) => fieldLabels[field] || field).join('、') || '无' }}</dd></div><div><dt>未知字段</dt><dd>{{ preflightResult.unknown_columns.map((field) => fieldLabels[field] || field).join('、') || '无' }}</dd></div><div><dt>工作表</dt><dd>{{ preflightResult.worksheets.join('、') || '无' }}</dd></div></dl>
        <div v-if="preflightResult.error_summary.length" class="issue-list errors"><h3>需要处理</h3><ul><li v-for="issue in preflightResult.error_summary" :key="issue.code"><strong>{{ issueLabel(issue.code) }} · {{ issue.count }} 项</strong><span>{{ issueMessage(issue.code) }}</span></li></ul></div>
        <div v-if="preflightResult.warning_summary.length" class="issue-list warnings"><h3>填写提醒</h3><ul><li v-for="issue in preflightResult.warning_summary" :key="issue.code"><strong>{{ issueLabel(issue.code) }} · {{ issue.count }} 项</strong><span>{{ issueMessage(issue.code) }}</span></li></ul></div>
      </section>
      <p v-if="uploadError" class="notice error" role="alert"><strong>导入失败</strong><br />原因：{{ uploadError }}<br />建议下一步：根据预检结果修正资料后重新导入。</p>
      <div v-if="result" class="notice success" role="status"><strong>导入完成：{{ displayStatus(result.status) }}</strong><p>已进入待审核暂存区，尚未自动发布给 AI。</p><div class="metrics"><span class="metric">目标店铺<strong>{{ result.target_store_code || '未绑定' }}</strong></span><span class="metric">待审核有效行<strong>{{ result.valid_rows }}</strong></span><span class="metric">待处理行<strong>{{ result.invalid_rows + result.duplicate_rows }}</strong></span></div><RouterLink class="button secondary" :to="`/imports/${result.id}`">查看导入详情</RouterLink></div>
    </section>
  </main>
</template>

<style scoped>
.target-store { margin-bottom: 18px; color: #365b8d; background: #edf4ff; }.guide-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }.guide-grid h2, .form-heading h2, .preflight-summary h2, .preflight-summary h3, .issue-list h3 { margin: 0; color: #172554; font-size: 18px; }.guide-grid p, .guide-grid li, .form-heading p, .subtle, label small, small { color: #64748b; line-height: 1.55; font-size: 13px; }.guide-grid ul { padding-left: 20px; margin: 12px 0; }.import-form { display: grid; gap: 16px; }.form-heading { display: flex; justify-content: space-between; gap: 20px; align-items: start; }.form-heading p { margin: 6px 0 0; }.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 0; margin: 0; list-style: none; counter-reset: step; }.steps li { display: grid; gap: 5px; padding: 13px; border-radius: 9px; background: #f6f8fc; color: #475569; font-size: 13px; }.steps strong { color: #172554; }.steps span { color: #64748b; line-height: 1.45; }label { display: grid; gap: 8px; }.action-row { display: flex; flex-wrap: wrap; gap: 12px; }.selected-file { margin: 0; color: #475569; }.preflight-summary { display: grid; gap: 15px; padding: 18px; border: 1px solid #d7e2ef; border-radius: 10px; }.preflight-summary > p { margin: -6px 0 0; color: #64748b; }.preflight-summary.passed { border-color: #77b99a; background: #f5fbf8; }.preflight-summary.blocked { border-color: #d99a9a; background: #fff7f7; }.preflight-details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 0; }.preflight-details dt { color: #64748b; font-size: 12px; }.preflight-details dd { margin: 3px 0 0; overflow-wrap: anywhere; }.issue-list { padding: 12px; border-radius: 8px; }.errors { background: #fff0f0; }.warnings { background: #fff8df; }.issue-list ul { display: grid; gap: 8px; margin: 0; padding-left: 20px; }.issue-list li { display: grid; gap: 2px; }.issue-list span { color: #64748b; font-size: 13px; }.success { display: grid; gap: 14px; }.success p { margin: 0; }@media (max-width: 900px) { .guide-grid { grid-template-columns: 1fr; }.steps { grid-template-columns: repeat(2, minmax(0, 1fr)); } }@media (max-width: 640px) { .form-heading { flex-direction: column; }.steps, .preflight-details { grid-template-columns: 1fr; } }
</style>
