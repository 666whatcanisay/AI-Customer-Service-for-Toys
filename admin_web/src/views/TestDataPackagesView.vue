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
const visiblePackages = computed(() => (
  targetStoreCode
    ? packages.value.filter((item) => item.store_code === targetStoreCode)
    : packages.value
))
const canImport = computed(
  () => selectedFile.value !== null
    && preflight.value?.can_import === true
    && (!targetStoreCode || preflight.value.store_code === targetStoreCode),
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
    if (targetStoreCode && preflight.value.store_code !== targetStoreCode) {
      preflightError.value = `知识包店铺编码 ${preflight.value.store_code} 与目标店铺 ${targetStoreCode} 不一致，不能导入。`
    }
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
        <h1>测试数据包</h1>
        <p>仅导入 TENANT-PDD-SM-TEST；不可用于生产，禁止自动发送。</p>
      </div>
    </div>
    <p v-if="targetStoreCode" class="notice warning">目标试运行店铺：<strong>{{ targetStoreCode }}</strong>。只展示并允许导入店铺编码一致的受控测试知识包。</p>

    <section class="card package-import">
      <h2>导入汕明 V0.3.1 测试基线包</h2>
      <p class="notice warning">
        测试专用：test_data_mode=true、production_usable=false、SUGGESTION_ONLY、allow_auto_send=false。
      </p>
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
        <h3>{{ preflight.can_import ? 'ZIP 预检通过' : 'ZIP 预检未通过' }}</h3>
        <p>{{ preflight.package_id }} · {{ preflight.version }} · {{ preflight.schema_version }}</p>
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
      </div>

      <p v-if="imported" class="notice success" role="status">
        已导入 {{ imported.package_id }}；状态 {{ imported.import_status }}。
      </p>
    </section>

    <section class="card package-list">
      <h2>已导入测试包</h2>
      <p v-if="loading" class="notice" role="status">正在加载…</p>
      <p v-else-if="listError" class="notice error" role="alert">{{ listError }}</p>
      <p v-else-if="visiblePackages.length === 0" class="notice">{{ targetStoreCode ? '待维护知识：尚无该目标店铺的受控测试知识包。' : '暂无测试数据包。' }}</p>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead><tr><th>数据包</th><th>状态</th><th>商品</th><th>SKU</th><th>FAQ</th><th>规则</th><th>评测</th><th>限制</th></tr></thead>
          <tbody>
            <tr v-for="item in visiblePackages" :key="item.package_id">
              <td>{{ item.package_id }}<br /><small>{{ item.version }}</small></td>
              <td><span class="badge">{{ item.import_status }}</span></td>
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

small {
  color: #617087;
}
</style>
