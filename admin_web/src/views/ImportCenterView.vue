<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { apiErrorMessage, listOperationStores, type StoreOperationItem } from '../api/client'

const templates = [
  { title: '商品知识采集模板', description: '商品简介、卖点、年龄、材质、包装和使用说明。', href: '/templates/商品知识采集模板V1.xlsx' },
  { title: 'SKU差异知识采集模板', description: '只记录颜色、规格、包装、数量、尺寸和玩法差异。', href: '/templates/SKU差异知识采集模板V1.xlsx' },
  { title: '客服FAQ知识采集模板', description: '把真实高频问题整理为有事实依据的标准回答。', href: '/templates/客服FAQ知识采集模板V1.xlsx' },
  { title: '商品安全规则采集模板', description: '维护安全提醒、禁止承诺和必须转人工情况。', href: '/templates/商品安全规则采集模板V1.xlsx' },
  { title: '客服AI问题反馈模板', description: '记录去除敏感信息后的AI回答问题和客服处理结果。', href: '/templates/客服AI问题反馈模板V1.xlsx' },
  { title: 'AI知识缺口管理模板', description: '整理缺失主题、出现次数、影响程度和处理优先级。', href: '/templates/AI知识缺口管理模板V1.xlsx' },
]

const stores = ref<StoreOperationItem[]>([])
const selectedStoreRef = ref('')
const storeLoading = ref(true)
const storeError = ref('')
const selectedStore = computed(() => stores.value.find((item) => String(item.store_ref) === selectedStoreRef.value))

async function loadStores(): Promise<void> {
  storeLoading.value = true
  storeError.value = ''
  try {
    stores.value = (await listOperationStores()).items.filter((item) => item.status === 'ACTIVE')
    const remembered = sessionStorage.getItem('c-operation-import-store-ref') || ''
    selectedStoreRef.value = stores.value.some((item) => String(item.store_ref) === remembered)
      ? remembered
      : ''
  } catch (reason: unknown) {
    stores.value = []
    storeError.value = apiErrorMessage(reason)
  } finally {
    storeLoading.value = false
  }
}

watch(selectedStoreRef, (value) => {
  if (value) sessionStorage.setItem('c-operation-import-store-ref', value)
  else sessionStorage.removeItem('c-operation-import-store-ref')
})

onMounted(loadStores)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">商品知识资料准备</p>
        <h1>中文资料模板</h1>
        <p>六类中文模板分别覆盖商品、SKU、FAQ、安全、AI反馈和知识缺口。模板不要求填写内部标识，也不会在下载或上传后自动发布知识。</p>
      </div>
      <RouterLink class="button" to="/knowledge-materials">进入资料上传与审核</RouterLink>
    </div>

    <section class="steps card">
      <h2>使用顺序</h2>
      <ol>
        <li>下载 Excel，先阅读“填写说明”和“字段说明”。</li>
        <li>在“数据填写”中录入真实资料；“示例数据”仅用于理解格式，不能直接当作正式知识。</li>
        <li>进入“资料上传与审核”，用中文名称选择店铺、商品和 SKU，再上传并完成人工审核。</li>
      </ol>
    </section>

    <section class="card store-scope">
      <div class="store-heading">
        <div><p class="eyebrow">导入业务范围</p><h2>先选择店铺</h2><p>选择中文店铺名称后再下载或上传商品知识资料，不需要填写任何内部编号。</p></div>
        <RouterLink class="button secondary" to="/store-management">店铺管理</RouterLink>
      </div>
      <p v-if="storeLoading" class="notice" role="status">正在读取可用店铺…</p>
      <p v-else-if="storeError" class="notice error" role="alert">店铺读取失败：{{ storeError }}</p>
      <div v-else-if="stores.length === 0" class="empty-store">
        <p class="notice">当前还没有可用店铺。请先创建店铺，再返回选择店铺并导入商品知识。</p>
        <RouterLink class="button" to="/store-management">创建店铺</RouterLink>
      </div>
      <div v-else class="store-selector">
        <label>店铺<select v-model="selectedStoreRef"><option value="">请选择店铺</option><option v-for="store in stores" :key="store.store_ref" :value="String(store.store_ref)">{{ store.store_name }} · {{ store.platform_name }}</option></select></label>
        <p v-if="selectedStore" class="notice success">已选择：{{ selectedStore.store_name }}。后续资料准备以该店铺为业务范围。</p>
      </div>
      <ol class="flow"><li :class="{ done: stores.length > 0 }">创建店铺</li><li :class="{ done: !!selectedStore }">选择店铺</li><li>导入商品知识</li></ol>
    </section>

    <section class="template-grid">
      <article v-for="template in templates" :key="template.title" class="template-card">
        <div><p class="eyebrow">中文运营模板 · XLSX</p><h2>{{ template.title }}</h2><p>{{ template.description }}</p></div>
        <a class="button secondary" :href="template.href" download>下载模板</a>
      </article>
    </section>

    <section class="card template-note">
      <h2>统一填写边界</h2>
      <ul><li>A级知识优先核实年龄、安全、包装和FAQ。</li><li>资料不足允许保存，但AI不能编造，必须提示人工确认。</li><li>不收集价格、库存、财务、采购和平台技术标识。</li></ul>
    </section>

    <section class="entry-grid">
      <RouterLink class="entry-card primary" :class="{ disabled: !selectedStore }" :aria-disabled="!selectedStore" :to="selectedStore ? { path: '/knowledge-materials', query: { store_ref: selectedStore.store_ref } } : '/import-center'">
        <strong>资料上传与审核</strong>
        <span>日常商品知识补充的主入口。选择业务名称、核对识别结果并由运营人工审核。</span>
      </RouterLink>
      <RouterLink class="entry-card" to="/knowledge-editor"><strong>中文知识维护</strong><span>不使用Excel时，可按店铺、商品和SKU直接补充结构化知识。</span></RouterLink>
      <RouterLink class="entry-card" to="/knowledge-center">
        <strong>查看商品知识缺口</strong>
        <span>按店铺、商品和 SKU 查看 AI 能回答什么、不能回答什么以及下一步补什么。</span>
      </RouterLink>
    </section>

    <details class="card legacy-entry">
      <summary>旧版试点数据入口（兼容保留）</summary>
      <p>下列入口继续用于既有试点数据验证，不是日常商品知识维护流程，也不会自动迁移历史测试数据。</p>
      <div class="legacy-links">
        <RouterLink class="button secondary" to="/imports/new">旧版商品与 SKU 批量导入</RouterLink>
        <RouterLink class="button secondary" to="/test-data-packages">测试数据包</RouterLink>
      </div>
    </details>

    <section class="card boundary">
      <h2>处理边界</h2>
      <p>资料上传后只进行受控保存、识别和人工审核。系统不会自动补写缺失事实、发布到 RAG、训练模型、修改 Prompt 或触发任何客户与业务动作。</p>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.steps { margin-bottom: 20px; background: #f8fbff; }.steps h2, .template-card h2, .boundary h2, .template-note h2 { margin-top: 0; color: #172554; }.steps ol { display: grid; gap: 9px; margin-bottom: 0; padding-left: 22px; color: #526279; line-height: 1.65; }.template-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; }.template-card { display: grid; align-content: space-between; gap: 18px; min-height: 210px; padding: 20px; border: 1px solid #b9cde9; border-radius: 13px; background: linear-gradient(145deg, #f4f8ff, #fff); }.template-card h2 { margin-bottom: 8px; font-size: 18px; }.template-card p { color: #526279; line-height: 1.6; }.template-card > .button { justify-self: start; }.template-note { margin-top: 16px; }.template-note ul { margin-bottom: 0; color: #526279; line-height: 1.7; }.entry-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }.entry-card { display: grid; gap: 9px; min-height: 118px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }.entry-card.primary { border-color: #92b5e8; }.entry-card span { color: #617087; font-size: 13px; line-height: 1.55; }.legacy-entry { margin-top: 20px; color: #526279; }.legacy-entry summary { color: #334965; font-weight: 700; cursor: pointer; }.legacy-entry p { line-height: 1.6; }.legacy-links { display: flex; flex-wrap: wrap; gap: 10px; }.boundary { margin-top: 20px; border-left: 4px solid #d59b2c; }.boundary p { margin-bottom: 0; color: #526279; line-height: 1.65; }
.store-scope { margin-bottom: 20px; }.store-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }.store-heading h2 { margin: 0; color: #172554; }.store-heading p:last-child { color: #617087; }.empty-store { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }.store-selector label { display: grid; gap: 6px; max-width: 520px; color: #526279; font-size: 13px; }.store-selector select { min-height: 42px; padding: 9px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }.flow { display: flex; gap: 28px; margin: 18px 0 0; padding: 0; list-style: none; counter-reset: flow; }.flow li { color: #7a8798; }.flow li::before { counter-increment: flow; content: counter(flow); display: inline-grid; width: 24px; height: 24px; margin-right: 7px; place-items: center; border-radius: 50%; background: #e7edf5; font-size: 12px; font-weight: 800; }.flow li.done { color: #217447; }.flow li.done::before { color: #fff; background: #369367; }.entry-card.disabled { opacity: .55; cursor: not-allowed; }
@media (max-width: 900px) { .template-grid, .entry-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .template-grid, .entry-grid { grid-template-columns: 1fr; } }
</style>
