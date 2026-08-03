<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import OperationalStatePanel from '../components/OperationalStatePanel.vue'
import { apiErrorMessage, listOperationStores, type StoreOperationItem } from '../api/client'

const templates = [
  { title: '商品知识采集模板', description: '商品简介、卖点、年龄、材质、包装和使用说明。', status: '导入已支持', statusNote: '可在资料上传与审核页面完成 Excel 导入。', supported: true, href: '/templates/商品知识采集模板V1.xlsx' },
  { title: 'SKU差异知识采集模板', description: '只记录颜色、规格、包装、数量、尺寸和玩法差异。', status: '模板可下载', statusNote: '批量导入功能开发中。', supported: false, href: '/templates/SKU差异知识采集模板V1.xlsx' },
  { title: '客服FAQ知识采集模板', description: '把真实高频问题整理为有事实依据的标准回答。', status: '模板可下载', statusNote: '批量导入功能开发中。', supported: false, href: '/templates/客服FAQ知识采集模板V1.xlsx' },
  { title: '商品安全规则采集模板', description: '维护安全提醒、禁止承诺和必须转人工情况。', status: '模板可下载', statusNote: '批量导入功能开发中。', supported: false, href: '/templates/商品安全规则采集模板V1.xlsx' },
  { title: '客服AI问题反馈模板', description: '记录去除敏感信息后的AI回答问题和客服处理结果。', status: '模板可下载', statusNote: '批量导入功能开发中。', supported: false, href: '/templates/客服AI问题反馈模板V1.xlsx' },
  { title: 'AI知识缺口管理模板', description: '整理缺失主题、出现次数、影响程度和处理优先级。', status: '模板可下载', statusNote: '批量导入功能开发中。', supported: false, href: '/templates/AI知识缺口管理模板V1.xlsx' },
]

const testToolsEnabled = import.meta.env.VITE_ENABLE_TEST_TOOLS === 'true'

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
      <div class="header-actions">
        <RouterLink class="button secondary" to="/overview">返回运营工作台</RouterLink>
        <RouterLink class="button" to="/knowledge-materials">进入资料上传与审核</RouterLink>
      </div>
    </div>

    <section class="steps card">
      <div><p class="eyebrow">新用户引导</p><h2>四步完成资料准备</h2></div>
      <ol>
        <li><strong>下载模板</strong><span>选择对应业务模板，先阅读“填写说明”和“字段说明”。</span></li>
        <li><strong>填写商品资料</strong><span>在“数据填写”中录入真实信息；示例数据不能直接作为正式知识。</span></li>
        <li><strong>上传审核</strong><span>进入“资料上传与审核”，选择店铺和模板，上传后人工核对。</span></li>
        <li><strong>查看结果</strong><span>审核完成后回到商品知识中心，确认资料、客服和 AI知识状态。</span></li>
      </ol>
    </section>

    <section class="template-grid">
      <article v-for="template in templates" :key="template.title" class="template-card">
        <div>
          <p class="eyebrow">中文运营模板 · XLSX</p>
          <h2>{{ template.title }}</h2>
          <p>{{ template.description }}</p>
          <div :class="['template-status', { supported: template.supported }]">
            <strong>{{ template.status }}</strong>
            <small>{{ template.statusNote }}</small>
          </div>
        </div>
        <a class="button secondary" :href="template.href" download>下载模板</a>
      </article>
    </section>

    <section class="card store-scope">
      <div class="store-heading">
        <div><p class="eyebrow">准备上传时</p><h2>确认目标店铺</h2><p>下载模板不需要选择店铺。准备上传时，请选择中文店铺名称，避免资料进入错误业务范围。</p></div>
        <RouterLink class="button secondary" to="/store-management">店铺管理</RouterLink>
      </div>
      <OperationalStatePanel
        v-if="storeLoading"
        state="loading"
        title="正在读取可用店铺"
        reason="系统正在读取状态正常、可用于资料归属的店铺。"
        next-step="请稍候；读取完成后选择本次 Excel 所属店铺。"
        compact
        data-testid="import-store-loading-state"
      />
      <OperationalStatePanel
        v-else-if="storeError"
        state="error"
        title="可用店铺暂时无法读取"
        :reason="storeError"
        next-step="重新读取；如果持续失败，返回运营工作台检查平台状态。"
        action-label="返回运营工作台"
        action-to="/overview"
        retry-label="重新读取店铺"
        compact
        data-testid="import-store-error-state"
        @retry="loadStores"
      />
      <OperationalStatePanel
        v-else-if="stores.length === 0"
        state="empty"
        title="当前还没有可用店铺"
        reason="店铺接口读取成功，但没有返回状态正常的店铺。"
        next-step="先创建或恢复一个正常店铺，再返回本页选择店铺并上传资料。"
        action-label="前往店铺管理"
        action-to="/store-management"
        compact
        data-testid="import-store-empty-state"
      />
      <div v-else class="store-selector">
        <label>店铺<select v-model="selectedStoreRef"><option value="">请选择店铺</option><option v-for="store in stores" :key="store.store_ref" :value="String(store.store_ref)">{{ store.store_name }} · {{ store.platform_name }}</option></select></label>
        <OperationalStatePanel
          v-if="selectedStore"
          state="success"
          title="目标店铺已确认"
          :reason="`已选择 ${selectedStore.store_name}；后续资料将以该店铺为业务范围。`"
          next-step="进入资料上传与审核，继续选择模板并上传 Excel。"
          action-label="进入资料上传与审核"
          :action-to="`/knowledge-materials?store_ref=${encodeURIComponent(String(selectedStore.store_ref))}`"
          compact
          data-testid="import-store-success-state"
        />
        <OperationalStatePanel
          v-else
          state="empty"
          title="还未选择目标店铺"
          reason="已有可用店铺，但尚未确定本次资料所属的业务范围。"
          next-step="从上方店铺列表选择与 Excel 内容一致的店铺。"
          compact
        />
      </div>
      <ol class="flow"><li :class="{ done: stores.length > 0 }">创建店铺</li><li :class="{ done: !!selectedStore }">选择店铺</li><li>进入上传审核</li></ol>
    </section>

    <section class="card template-note">
      <h2>统一填写边界</h2>
      <ul><li>A级知识优先核实年龄、安全、包装和FAQ。</li><li>资料不足允许保存，但AI不能编造，必须提示人工确认。</li><li>不收集价格、库存、财务、采购和平台技术标识。</li></ul>
    </section>

    <section class="entry-grid">
      <RouterLink class="entry-card primary" :class="{ disabled: !selectedStore }" :aria-disabled="!selectedStore" :to="selectedStore ? { path: '/knowledge-materials', query: { store_ref: selectedStore.store_ref } } : '/import-center'">
        <strong>资料上传与审核</strong>
        <span>日常商品知识补充的主入口。选择业务名称、核对识别结果并由运营人工审核。</span>
        <em>{{ selectedStore ? '继续上传审核 →' : '请先选择目标店铺' }}</em>
      </RouterLink>
      <RouterLink class="entry-card" to="/knowledge-editor"><strong>手工补充知识</strong><span>不使用Excel时，可按店铺、商品和SKU直接补充结构化知识。</span><em>立即前往 →</em></RouterLink>
      <RouterLink class="entry-card" to="/knowledge-center">
        <strong>查看商品知识缺口</strong>
        <span>按店铺、商品和 SKU 查看 AI 能回答什么、不能回答什么以及下一步补什么。</span>
        <em>查看处理建议 →</em>
      </RouterLink>
    </section>

    <details v-if="testToolsEnabled" class="card legacy-entry">
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
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.header-actions { display: flex; flex-wrap: wrap; gap: 10px; }.steps { margin-bottom: 20px; background: #f8fbff; }.steps h2, .template-card h2, .boundary h2, .template-note h2 { margin-top: 0; color: #172554; }.steps ol { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 16px 0 0; padding: 0; list-style: none; counter-reset: guide; }.steps li { display: grid; gap: 7px; padding: 13px; border: 1px solid #dbe4ef; border-radius: 10px; color: #526279; background: #fff; line-height: 1.55; }.steps li::before { counter-increment: guide; content: counter(guide); display: grid; width: 24px; height: 24px; place-items: center; border-radius: 50%; color: #fff; background: #3269b3; font-size: 12px; font-weight: 800; }.steps li strong { color: #172554; }.steps li span { font-size: 13px; }.template-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; }.template-card { display: grid; align-content: space-between; gap: 18px; min-height: 230px; padding: 20px; border: 1px solid #b9cde9; border-radius: 13px; background: linear-gradient(145deg, #f4f8ff, #fff); }.template-card h2 { margin-bottom: 8px; font-size: 18px; }.template-card p { color: #526279; line-height: 1.6; }.template-card > .button { justify-self: start; }.template-status { display: grid; gap: 3px; margin-top: 13px; padding: 9px 10px; border-radius: 8px; color: #8a5a14; background: #fff6e6; }.template-status.supported { color: #217447; background: #eaf7ef; }.template-status strong { font-size: 13px; }.template-status small { color: inherit; font-size: 12px; line-height: 1.45; }.template-note { margin-top: 16px; }.template-note ul { margin-bottom: 0; color: #526279; line-height: 1.7; }.entry-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }.entry-card { display: grid; gap: 9px; min-height: 118px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }.entry-card.primary { border-color: #92b5e8; }.entry-card span { color: #617087; font-size: 13px; line-height: 1.55; }.entry-card em { align-self: end; color: #285493; font-size: 12px; font-style: normal; font-weight: 800; }.entry-card.disabled em { color: #718096; }.legacy-entry { margin-top: 20px; color: #526279; }.legacy-entry summary { color: #334965; font-weight: 700; cursor: pointer; }.legacy-entry p { line-height: 1.6; }.legacy-links { display: flex; flex-wrap: wrap; gap: 10px; }.boundary { margin-top: 20px; border-left: 4px solid #d59b2c; }.boundary p { margin-bottom: 0; color: #526279; line-height: 1.65; }
.store-scope { margin-top: 20px; }.store-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }.store-heading h2 { margin: 0; color: #172554; }.store-heading p:last-child { color: #617087; }.store-selector { display: grid; gap: 12px; }.store-selector label { display: grid; gap: 6px; max-width: 520px; color: #526279; font-size: 13px; }.store-selector select { min-height: 42px; padding: 9px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }.flow { display: flex; gap: 28px; margin: 18px 0 0; padding: 0; list-style: none; counter-reset: flow; }.flow li { color: #7a8798; }.flow li::before { counter-increment: flow; content: counter(flow); display: inline-grid; width: 24px; height: 24px; margin-right: 7px; place-items: center; border-radius: 50%; background: #e7edf5; font-size: 12px; font-weight: 800; }.flow li.done { color: #217447; }.flow li.done::before { color: #fff; background: #369367; }.entry-card.disabled { opacity: .55; cursor: not-allowed; }
@media (max-width: 1050px) { .steps ol { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 900px) { .template-grid, .entry-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .template-grid, .entry-grid, .steps ol { grid-template-columns: 1fr; } }
</style>
