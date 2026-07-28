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
const canImport = computed(
  () => selectedFile.value !== null && preflight.value?.can_import === true,
)

async function loadPackages(): Promise<void> {
  loading.value = true
  listError.value = ''
  try {
    packages.value = (await listTestDataPackages()).items
  } catch (reason: unknown) {
    listError.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  selectedFile.value = null
  fileError.value = ''
  preflightError.value = ''
  preflight.value = null
  importError.value = ''
  imported.value = null
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.zip')) {
    fileError.value = '仅支持 V0.3.1 测试数据包 ZIP。'
    input.value = ''
    return
  }
  if (file.size > MAX_PACKAGE_BYTES) {
    fileError.value = '测试数据包不能超过 32 MB。'
    input.value = ''
    return
  }
  selectedFile.value = file
}

async function runPreflight(): Promise<void> {
  if (!selectedFile.value || preflighting.value || importing.value) return
  preflighting.value = true
  preflightError.value = ''
  preflight.value = null
  imported.value = null
  try {
    preflight.value = await preflightTestDataPackage(selectedFile.value)
  } catch (reason: unknown) {
    preflightError.value = apiErrorMessage(reason)
  } finally {
    preflighting.value = false
  }
}

async function runImport(): Promise<void> {
  if (!selectedFile.value || !canImport.value || importing.value) return
  importing.value = true
  importError.value = ''
  imported.value = null
  try {
    imported.value = await importTestDataPackage(selectedFile.value)
    await loadPackages()
  } catch (reason: unknown) {
    importError.value = apiErrorMessage(reason)
  } finally {
    importing.value = false
  }
}

onMounted(loadPackages)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">数据与系统 / 测试数据包</p>
        <h1>测试数据包</h1>
        <p>仅导入经验证的 V0.3.1 原始 ZIP 到测试租户；不可用于生产，禁止自动发送。</p>
      </div>
    </div>

    <section class="card package-import">
      <h2>导入汕明 V0.3.1 测试基线包</h2>
      <p class="notice warning">
        测试专用：test_data_mode=true、production_usable=false、SUGGESTION_ONLY、allow_auto_send=false。
      </p>
      <section class="package-steps" aria-label="测试数据包导入三步">
        <article><span>1</span><div><strong>选择原始 ZIP</strong><p>使用已通过 Manifest 验证的原始 V0.3.1 ZIP。</p></div></article>
        <article><span>2</span><div><strong>先预检</strong><p>确认租户、数量和安全限制被正确识别。</p></div></article>
        <article><span>3</span><div><strong>确认后导入</strong><p>只在预检通过后导入测试租户。</p></div></article>
      </section>
      <p class="template-note"><strong>没有测试包模板下载：</strong>此入口不接受自行拼装的模板或解压目录，只接受原始测试 ZIP。</p>
      <input
        type="file"
        accept=".zip,application/zip"
        :disabled="preflighting || importing"
        @change="onFileChange"
      />
      <p v-if="fileError" class="notice error" role="alert">{{ fileError }}</p>
      <p v-if="selectedFile">已选择：{{ selectedFile.name }}</p>
      <div class="actions">
        <button
          class="button secondary"
          data-testid="package-preflight"
          :disabled="!selectedFile || preflighting || importing"
          @click="runPreflight"
        >
          {{ preflighting ? '预检中…' : '先预检 ZIP' }}
        </button>
        <button
          class="button"
          data-testid="package-import"
          :disabled="!canImport || preflighting || importing"
          @click="runImport"
        >
          {{ importing ? '导入中…' : '导入测试租户' }}
        </button>
      </div>
      <p v-if="preflightError" class="notice error" role="alert">{{ preflightError }}</p>
      <p v-if="importError" class="notice error" role="alert">{{ importError }}</p>

      <div v-if="preflight" class="preflight" role="status">
        <h3>{{ preflight.can_import ? '识别结果：ZIP 预检通过' : '识别结果：ZIP 预检未通过' }}</h3>
        <p>包：{{ preflight.package_id }} · 版本：{{ preflight.version }} · Schema：{{ preflight.schema_version }}</p>
        <p>租户：{{ preflight.tenant_id }} · 店铺：{{ preflight.store_code }} · 自动发送：{{ preflight.allow_auto_send ? '允许（异常）' : '禁止' }}</p>
        <div class="metrics">
          <span class="metric">商品<strong>{{ preflight.counts.products }}</strong></span>
          <span class="metric">SKU/组合<strong>{{ preflight.counts.skus_and_bundles }}</strong></span>
          <span class="metric">图片证据<strong>{{ preflight.counts.image_evidence }}</strong></span>
          <span class="metric">FAQ<strong>{{ preflight.counts.faqs }}</strong></span>
          <span class="metric">安全规则<strong>{{ preflight.counts.safety_rules }}</strong></span>
          <span class="metric">评测案例<strong>{{ preflight.counts.evaluation_cases }}</strong></span>
        </div>
        <ul v-if="preflight.warnings.length">
          <li v-for="warning in preflight.warnings" :key="warning.code">
            {{ warning.code }}：{{ warning.message }}
          </li>
        </ul>
        <section v-if="preflight.errors.length" class="issue-list errors"><h4>失败原因</h4><ul><li v-for="issue in preflight.errors" :key="issue.code">{{ issue.code }}：{{ issue.message }}</li></ul></section>
      </div>

      <p v-if="imported" class="notice success" role="status">
        已导入 {{ imported.package_id }}；状态 {{ displayStatus(imported.import_status) }}。
      </p>
    </section>

    <section class="card package-list">
      <h2>已导入测试包</h2>
      <p v-if="loading" class="notice" role="status">正在加载…</p>
      <p v-else-if="listError" class="notice error" role="alert">{{ listError }}</p>
      <p v-else-if="packages.length === 0" class="notice">暂无测试数据包。</p>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead><tr><th>数据包</th><th>状态</th><th>商品</th><th>SKU</th><th>FAQ</th><th>规则</th><th>评测</th><th>限制</th></tr></thead>
          <tbody>
            <tr v-for="item in packages" :key="item.package_id">
              <td>{{ item.package_id }}<br /><small>{{ item.version }}</small></td>
              <td><span class="badge">{{ displayStatus(item.import_status) }}</span></td>
              <td>{{ item.counts.products }}</td>
              <td>{{ item.counts.skus_and_bundles }}</td>
              <td>{{ item.counts.faqs }}</td>
              <td>{{ item.counts.safety_rules }}</td>
              <td>{{ item.counts.evaluation_cases }}</td>
              <td>测试专用 / 不可生产 / 禁止自动发送</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>

<style scoped>
.package-import,
.package-list {
  display: grid;
  gap: 18px;
  margin-bottom: 24px;
}

.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.package-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 14px; border-radius: 12px; background: #eef4fb; }.package-steps article { display: flex; gap: 9px; min-width: 0; }.package-steps span { display: grid; width: 24px; height: 24px; flex: 0 0 auto; place-items: center; border-radius: 50%; background: #284f8f; color: #fff; font-size: 12px; font-weight: 800; }.package-steps strong { font-size: 13px; }.package-steps p { margin: 3px 0 0; color: #617087; font-size: 12px; line-height: 1.45; }.template-note { padding: 11px 13px; border-left: 3px solid #cf8c24; border-radius: 7px; background: #fff8e7; color: #6d531a; font-size: 13px; line-height: 1.55; }

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.warning {
  color: #76551b;
  background: #fff8e6;
}

.preflight {
  padding: 18px;
  border: 1px solid #77b99a;
  border-radius: 10px;
  background: #f5fbf8;
}

.preflight h3,
.package-import h2,
.package-list h2 {
  margin: 0;
}

.issue-list.errors { color: #8c2929; }.issue-list h4 { margin-bottom: 6px; }

small {
  color: #617087;
}

@media (max-width: 760px) { .package-steps { grid-template-columns: 1fr; } }
</style>
