<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  importTestDataPackage,
  listTestDataPackages,
  preflightTestDataPackage,
  type TestPackagePreflight,
  type TestPackageSummary,
} from '../api/client'
import { displayStatus } from '../presentation'
import { testDataGuide, testDataTemplates } from '../templateCatalog'

const MAX_PACKAGE_BYTES = 32 * 1024 * 1024
const packages = ref<TestPackageSummary[]>([])
const loading = ref(true)
const listError = ref('')
const selectedFile = ref<File | null>(null)
const fileError = ref('')
const preflighting = ref(false)
const preflightError = ref('')
const preflight = ref<TestPackagePreflight | null>(null)
const importing = ref(false)
const importError = ref('')
const imported = ref<TestPackageSummary | null>(null)
const targetStoreCode = new URLSearchParams(window.location.search).get('store_code')?.trim() || ''
const visiblePackages = computed(() => targetStoreCode ? packages.value.filter((item) => item.store_code === targetStoreCode) : packages.value)
const canImport = computed(() => selectedFile.value !== null && preflight.value?.can_import === true && (!targetStoreCode || preflight.value.store_code === targetStoreCode))

function warningText(code: string): string {
  return {
    TEST_ONLY_PACKAGE: '该数据包仅可用于测试 / 试运行环境。',
    TEST_DATA_MODE_REQUIRED: '数据包必须明确标记为测试数据。',
    PRODUCTION_PACKAGE_REJECTED: '生产数据包不能在这里导入。',
    AUTO_SEND_REJECTED: '数据包不能启用自动发送。',
  }[code] || '请查看数据包填写说明并核对压缩包内容。'
}

async function loadPackages(): Promise<void> {
  loading.value = true
  listError.value = ''
  try { packages.value = (await listTestDataPackages()).items } catch (reason: unknown) { listError.value = apiErrorMessage(reason) } finally { loading.value = false }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  selectedFile.value = null; fileError.value = ''; preflightError.value = ''; preflight.value = null; importError.value = ''; imported.value = null
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.zip')) { fileError.value = '仅支持测试数据包 ZIP 文件。请先下载填写说明并按要求打包。'; input.value = ''; return }
  if (file.size > MAX_PACKAGE_BYTES) { fileError.value = '测试数据包不能超过 32 MB。请拆分或清理无关文件后重试。'; input.value = ''; return }
  selectedFile.value = file
}

async function runPreflight(): Promise<void> {
  if (!selectedFile.value || preflighting.value || importing.value) return
  preflighting.value = true; preflightError.value = ''; preflight.value = null; imported.value = null
  try {
    preflight.value = await preflightTestDataPackage(selectedFile.value)
    if (targetStoreCode && preflight.value.store_code !== targetStoreCode) preflightError.value = `数据包店铺编码 ${preflight.value.store_code} 与目标店铺 ${targetStoreCode} 不一致，不能导入。`
  } catch (reason: unknown) { preflightError.value = apiErrorMessage(reason) } finally { preflighting.value = false }
}

async function runImport(): Promise<void> {
  if (!selectedFile.value || !canImport.value || importing.value) return
  importing.value = true; importError.value = ''; imported.value = null
  try { imported.value = await importTestDataPackage(selectedFile.value); await loadPackages() } catch (reason: unknown) { importError.value = apiErrorMessage(reason) } finally { importing.value = false }
}

onMounted(loadPackages)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>测试数据包</h1><p>准备、预检并导入受控测试数据。只用于测试 / 试运行，不可用于生产，且不会自动发送。</p></div></div>
    <p v-if="targetStoreCode" class="notice warning">目标试运行店铺：<strong>{{ targetStoreCode }}</strong>。只显示并允许导入店铺编码一致的测试数据包。</p>

    <section class="card template-section">
      <div class="section-heading"><div><h2>模板下载与填写说明</h2><p>先下载模板，按示例填写；模板本身不会导入原始资料、发布知识或触发业务动作。</p></div><a class="button secondary" :href="testDataGuide.href" :download="testDataGuide.filename">下载测试数据包使用说明</a></div>
      <div class="template-grid"><article v-for="template in testDataTemplates" :key="template.key" class="template-card"><h3>{{ template.title }}</h3><p><strong>适用于：</strong>{{ template.applicable }}</p><p><strong>必填项：</strong>{{ template.required }}</p><p><strong>不会导入：</strong>{{ template.excluded }}</p><a class="button secondary" :href="template.href" :download="template.filename">下载模板</a></article></div>
      <ol class="steps"><li><strong>第一步：下载模板</strong><span>选择需要准备的资料类型。</span></li><li><strong>第二步：按示例填写</strong><span>保留字段名称，使用已核对的信息。</span></li><li><strong>第三步：上传并预检</strong><span>系统只检查格式和测试边界。</span></li><li><strong>第四步：正式导入</strong><span>只有预检通过后才可导入。</span></li></ol>
    </section>

    <section class="card package-import">
      <h2>导入测试数据包</h2><p class="notice warning">测试专用：不用于生产，只提供建议，不会自动发送。</p>
      <label><strong>选择 ZIP 文件</strong><input type="file" accept=".zip,application/zip" :disabled="preflighting || importing" @change="onFileChange" /><small>支持 .zip，最大 32 MB。请先按使用说明完成打包。</small></label>
      <p v-if="fileError" class="notice error" role="alert"><strong>文件无法使用</strong><br />原因：{{ fileError }}<br />建议下一步：下载使用说明并重新打包。</p>
      <p v-if="selectedFile">已选择：{{ selectedFile.name }}</p>
      <div class="actions"><button class="button secondary" data-testid="package-preflight" :disabled="!selectedFile || preflighting || importing" @click="runPreflight">{{ preflighting ? '正在预检…' : '上传并预检' }}</button><button class="button" data-testid="package-import" :disabled="!canImport || preflighting || importing" @click="runImport">{{ importing ? '正在导入…' : '正式导入测试数据' }}</button></div>
      <div v-if="preflightError" class="notice error" role="alert"><strong>数据加载失败</strong><br />原因：{{ preflightError }}<br />建议下一步：核对店铺和数据包内容后重新预检。</div><div v-if="importError" class="notice error" role="alert"><strong>导入失败</strong><br />原因：{{ importError }}<br />建议下一步：按预检提示修正后重试。</div>
      <div v-if="preflight" class="preflight" role="status"><h3>{{ preflight.can_import ? '预检通过，可以导入' : '预检未通过，请先处理问题' }}</h3><p>{{ preflight.package_name || preflight.package_id }} · 版本 {{ preflight.version }}</p><div class="metrics"><span class="metric">商品数<strong>{{ preflight.counts.products }}</strong></span><span class="metric">SKU 数<strong>{{ preflight.counts.skus_and_bundles }}</strong></span><span class="metric">FAQ 数<strong>{{ preflight.counts.faqs }}</strong></span><span class="metric">规则数<strong>{{ preflight.counts.safety_rules }}</strong></span><span class="metric">来源证据<strong>{{ preflight.counts.source_records_total }}</strong></span></div><ul v-if="preflight.warnings.length"><li v-for="warning in preflight.warnings" :key="warning.code">{{ warningText(warning.code) }}</li></ul></div>
      <p v-if="imported" class="notice success" role="status">已导入 {{ imported.package_name || imported.package_id }}；状态：{{ displayStatus(imported.import_status) }}。数据仍受测试边界限制。</p>
    </section>

    <section class="card package-list"><h2>已导入测试数据包</h2><p v-if="loading" class="notice" role="status">正在加载…</p><div v-else-if="listError" class="notice error" role="alert"><strong>数据加载失败</strong><br />原因：{{ listError }}<br />建议下一步：检查服务状态后重试。</div><p v-else-if="visiblePackages.length === 0" class="notice">{{ targetStoreCode ? '待启用：尚无该目标店铺的受控测试数据包。' : '暂无测试数据包。请先下载模板和使用说明。' }}</p><div v-else class="table-wrap"><table class="data-table"><thead><tr><th>数据包名称</th><th>版本</th><th>状态</th><th>商品数</th><th>SKU数</th><th>FAQ数</th><th>规则数</th><th>限制说明</th></tr></thead><tbody><tr v-for="item in visiblePackages" :key="item.package_id"><td>{{ item.package_name || item.package_id }}</td><td>{{ item.version || '未提供' }}</td><td><span class="badge">{{ displayStatus(item.import_status) }}</span></td><td>{{ item.counts.products }}</td><td>{{ item.counts.skus_and_bundles }}</td><td>{{ item.counts.faqs }}</td><td>{{ item.counts.safety_rules }}</td><td>仅测试 / 试运行；不可用于生产；不会自动发送</td></tr></tbody></table></div></section>
  </main>
</template>

<style scoped>
.template-section, .package-import, .package-list { display: grid; gap: 18px; margin-bottom: 24px; }.section-heading { display: flex; justify-content: space-between; gap: 18px; align-items: start; }.section-heading h2, .package-import h2, .package-list h2, .preflight h3 { margin: 0; color: #172554; font-size: 19px; }.section-heading p { margin: 6px 0 0; color: #64748b; line-height: 1.55; }.template-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }.template-card { display: grid; align-content: start; gap: 9px; padding: 16px; border: 1px solid #e0e8f1; border-radius: 10px; background: #f9fbfe; }.template-card h3, .template-card p { margin: 0; }.template-card h3 { color: #172554; }.template-card p { color: #526279; font-size: 13px; line-height: 1.55; }.template-card .button { justify-self: start; margin-top: 4px; }.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 0; margin: 0; list-style: none; }.steps li { display: grid; gap: 5px; padding: 13px; border-radius: 9px; background: #f6f8fc; font-size: 13px; }.steps strong { color: #172554; }.steps span, label small { color: #64748b; line-height: 1.45; }.warning { color: #76551b; background: #fff8e6; }.package-import label { display: grid; gap: 8px; }.actions { display: flex; flex-wrap: wrap; gap: 12px; }.preflight { display: grid; gap: 13px; padding: 18px; border: 1px solid #77b99a; border-radius: 10px; background: #f5fbf8; }.preflight p { margin: -6px 0 0; color: #64748b; }.preflight ul { margin: 0; padding-left: 20px; color: #526279; }.success { margin: 0; }@media (max-width: 850px) { .template-grid { grid-template-columns: 1fr; }.steps { grid-template-columns: repeat(2, minmax(0, 1fr)); } }.section-heading { flex-wrap: wrap; }@media (max-width: 580px) { .steps { grid-template-columns: 1fr; } }
</style>
