<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  createOperationProduct,
  createOperationStore,
  getOperationStore,
  listOperationStores,
  updateOperationStore,
  type ProductOperationInput,
  type ProductOperationItem,
  type StoreOperationInput,
  type StoreOperationItem,
  type StoreOperationStatus,
} from '../api/client'

const stores = ref<StoreOperationItem[]>([])
const selected = ref<StoreOperationItem | null>(null)
const editingRef = ref<number | null>(null)
const loading = ref(true)
const saving = ref(false)
const productSaving = ref(false)
const error = ref('')
const receipt = ref('')
const formVisible = ref(false)
const productFormVisible = ref(false)
const createdProduct = ref<ProductOperationItem | null>(null)
const form = reactive<StoreOperationInput & { status: StoreOperationStatus }>({
  store_name: '',
  platform: 'pinduoduo',
  remarks: '',
  status: 'ACTIVE',
})

const formTitle = computed(() => editingRef.value === null ? '新增店铺' : '编辑店铺')
const activeStores = computed(() => stores.value.filter((item) => item.status === 'ACTIVE'))
const productForm = reactive<ProductOperationInput & { store_ref: number | null }>({
  store_ref: null,
  product_name: '',
  product_summary: '',
})
const platforms: Array<{ value: StoreOperationInput['platform']; label: string }> = [
  { value: 'pinduoduo', label: '拼多多' },
  { value: 'taobao', label: '淘宝' },
  { value: 'tmall', label: '天猫' },
  { value: 'jd', label: '京东' },
  { value: 'douyin', label: '抖音' },
  { value: 'offline', label: '线下' },
  { value: 'other', label: '其他平台' },
]

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value))
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    stores.value = (await listOperationStores()).items
  } catch (reason: unknown) {
    stores.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function beginCreate(): void {
  editingRef.value = null
  Object.assign(form, { store_name: '', platform: 'pinduoduo', remarks: '', status: 'ACTIVE' })
  receipt.value = ''
  createdProduct.value = null
  error.value = ''
  productFormVisible.value = false
  formVisible.value = true
}

function beginCreateProduct(item?: StoreOperationItem): void {
  const preferred = item?.status === 'ACTIVE' ? item : activeStores.value[0]
  if (!preferred) {
    error.value = '请先创建并启用一家店铺，再新增商品。'
    return
  }
  Object.assign(productForm, {
    store_ref: preferred.store_ref,
    product_name: '',
    product_summary: '',
  })
  receipt.value = ''
  createdProduct.value = null
  error.value = ''
  formVisible.value = false
  productFormVisible.value = true
}

function beginEdit(item: StoreOperationItem): void {
  editingRef.value = item.store_ref
  const platform = platforms.find((candidate) => candidate.label === item.platform_name)?.value || 'offline'
  Object.assign(form, {
    store_name: item.store_name,
    platform,
    remarks: item.remarks,
    status: item.status,
  })
  receipt.value = ''
  createdProduct.value = null
  error.value = ''
  productFormVisible.value = false
  formVisible.value = true
}

async function viewStore(item: StoreOperationItem): Promise<void> {
  error.value = ''
  try {
    selected.value = await getOperationStore(item.store_ref)
  } catch (reason: unknown) {
    selected.value = null
    error.value = apiErrorMessage(reason)
  }
}

async function submit(): Promise<void> {
  if (saving.value) return
  saving.value = true
  error.value = ''
  receipt.value = ''
  try {
    const payload: StoreOperationInput = {
      store_name: form.store_name,
      platform: form.platform,
      remarks: form.remarks,
    }
    const result = editingRef.value === null
      ? await createOperationStore(payload)
      : await updateOperationStore(editingRef.value, { ...payload, status: form.status })
    receipt.value = editingRef.value === null ? '店铺已创建，可在导入中心选择。' : '店铺信息已更新。'
    selected.value = result
    formVisible.value = false
    await load()
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function submitProduct(): Promise<void> {
  if (productSaving.value || productForm.store_ref === null) return
  productSaving.value = true
  error.value = ''
  receipt.value = ''
  createdProduct.value = null
  try {
    const result = await createOperationProduct(productForm.store_ref, {
      product_name: productForm.product_name,
      product_summary: productForm.product_summary,
    })
    createdProduct.value = result
    receipt.value = '商品已新增并进入待审核状态。请继续补充 SKU 与商品知识。'
    productFormVisible.value = false
    await load()
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    productSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">店铺业务范围</p>
        <h1>店铺管理</h1>
        <p>使用中文业务名称维护商品知识所属店铺；内部标识由系统生成，不需要运营填写。</p>
      </div>
      <div class="page-actions">
        <button class="button" type="button" @click="beginCreate">新增店铺</button>
        <button class="button secondary" type="button" :disabled="activeStores.length === 0" @click="beginCreateProduct()">新增商品</button>
      </div>
    </div>

    <p v-if="receipt" class="notice success" role="status">
      {{ receipt }}
      <a v-if="createdProduct" :href="`/knowledge-center/products/${encodeURIComponent(createdProduct.product_ref)}`">查看并维护商品知识</a>
    </p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>

    <form v-if="formVisible" class="card store-form" @submit.prevent="submit">
      <div class="section-heading">
        <div><h2>{{ formTitle }}</h2><p>只填写运营能够确认的业务信息。</p></div>
        <button class="text-button" type="button" @click="formVisible = false">取消</button>
      </div>
      <div class="form-grid">
        <label>店铺名称<input v-model.trim="form.store_name" required minlength="2" maxlength="255" placeholder="例如：木木小栈拼多多旗舰店"></label>
        <label>平台<select v-model="form.platform"><option v-for="item in platforms" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        <label v-if="editingRef !== null">状态<select v-model="form.status"><option value="ACTIVE">正常</option><option value="INACTIVE">停用</option></select></label>
        <label class="wide">备注<textarea v-model.trim="form.remarks" maxlength="1000" placeholder="可填写店铺知识运营范围或注意事项"></textarea></label>
      </div>
      <p class="notice boundary">创建店铺不会自动创建商品、发布知识或触发任何客户与业务动作。</p>
      <button class="button" type="submit" :disabled="saving">{{ saving ? '正在保存…' : '保存店铺' }}</button>
    </form>

    <form v-if="productFormVisible" class="card product-form" @submit.prevent="submitProduct">
      <div class="section-heading">
        <div><h2>新增商品</h2><p>先建立商品档案，再按需补充 SKU 和知识资料。</p></div>
        <button class="text-button" type="button" @click="productFormVisible = false">取消</button>
      </div>
      <div class="form-grid">
        <label>所属店铺<select v-model.number="productForm.store_ref" required><option v-for="item in activeStores" :key="item.store_ref" :value="item.store_ref">{{ item.store_name }}（{{ item.platform_name }}）</option></select></label>
        <label class="wide-two">商品名称<input v-model.trim="productForm.product_name" required minlength="2" maxlength="255" placeholder="例如：城市消防局机械积木玩具套装"></label>
        <label class="wide">商品简介<textarea v-model.trim="productForm.product_summary" maxlength="4000" placeholder="填写已经确认的商品用途、特点或基础说明；不确定可暂不填写"></textarea></label>
      </div>
      <p class="notice boundary">商品由系统生成内部身份，初始为待审核且不可发布；不会自动创建 SKU、生成知识或发布到 RAG。</p>
      <button class="button" type="submit" :disabled="productSaving">{{ productSaving ? '正在保存…' : '保存商品' }}</button>
    </form>

    <section class="card list-card">
      <div class="section-heading"><div><h2>店铺列表</h2><p>共 {{ stores.length }} 家店铺</p></div><button class="button secondary" type="button" @click="load">刷新</button></div>
      <p v-if="loading" class="notice" role="status">正在读取店铺…</p>
      <p v-else-if="stores.length === 0" class="notice">当前暂无店铺。请先创建店铺，再进入导入中心。</p>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead><tr><th>店铺名称</th><th>平台</th><th>状态</th><th>商品数量</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody><tr v-for="item in stores" :key="item.store_ref"><td><strong>{{ item.store_name }}</strong></td><td>{{ item.platform_name }}</td><td><span class="badge">{{ item.status_name }}</span></td><td>{{ item.product_count }}</td><td>{{ formatDate(item.created_at) }}</td><td><div class="row-actions"><button class="text-button" type="button" @click="viewStore(item)">查看</button><button class="text-button" type="button" @click="beginEdit(item)">编辑</button><button class="text-button" type="button" :disabled="item.status !== 'ACTIVE'" @click="beginCreateProduct(item)">新增商品</button></div></td></tr></tbody>
        </table>
      </div>
    </section>

    <section v-if="selected" class="card detail-card">
      <div class="section-heading"><div><p class="eyebrow">店铺详情</p><h2>{{ selected.store_name }}</h2></div><button class="button secondary" type="button" @click="beginEdit(selected)">编辑</button></div>
      <dl><div><dt>平台</dt><dd>{{ selected.platform_name }}</dd></div><div><dt>状态</dt><dd>{{ selected.status_name }}</dd></div><div><dt>商品数量</dt><dd>{{ selected.product_count }}</dd></div><div><dt>创建时间</dt><dd>{{ formatDate(selected.created_at) }}</dd></div><div class="wide"><dt>备注</dt><dd>{{ selected.remarks || '暂无备注' }}</dd></div></dl>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.page-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.store-form, .product-form { display: grid; gap: 18px; margin-bottom: 20px; }
.section-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
.section-heading h2 { margin: 0; color: #172554; }.section-heading p { margin: 5px 0 0; color: #617087; }
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }.form-grid label { display: grid; gap: 6px; color: #526279; font-size: 13px; }.form-grid input, .form-grid select, .form-grid textarea { min-height: 41px; padding: 9px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }.form-grid textarea { min-height: 90px; resize: vertical; }.form-grid .wide { grid-column: span 3; }.form-grid .wide-two { grid-column: span 2; }
.text-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; cursor: pointer; }.text-button:disabled { color: #94a3b8; cursor: not-allowed; }.row-actions { display: flex; gap: 12px; flex-wrap: wrap; }.boundary { color: #75570a; background: #fff8df; }.success a { margin-left: 10px; color: #1e5aa8; font-weight: 700; }.list-card { margin-top: 20px; }.list-card .table-wrap { margin-top: 14px; }.detail-card { margin-top: 20px; }.detail-card dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.detail-card dl div { padding: 13px; border-radius: 9px; background: #f7f9fc; }.detail-card dt { color: #617087; font-size: 12px; }.detail-card dd { margin: 5px 0 0; color: #2f4259; }.detail-card .wide { grid-column: 1 / -1; }
@media (max-width: 760px) { .form-grid, .detail-card dl { grid-template-columns: 1fr; }.form-grid .wide, .form-grid .wide-two { grid-column: span 1; } }
</style>
