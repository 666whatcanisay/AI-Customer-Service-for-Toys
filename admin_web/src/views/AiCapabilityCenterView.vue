<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAiKnowledgeStatistics,
  getAiModuleDetail,
  getAiModuleLatestEvaluation,
  getAiModulePrompt,
  getAiRuntimeStatus,
  listAiModules,
  type AiKnowledgeStatistics,
  type AiLatestEvaluation,
  type AiModule,
  type AiModuleDetail,
  type AiPromptMetadata,
  type AiRuntimeStatus,
} from '../api/client'
import ProductEmptyState from '../components/ProductEmptyState.vue'
import { displayStatus } from '../presentation'

const modules = ref<AiModule[]>([])
const runtime = ref<AiRuntimeStatus | null>(null)
const knowledge = ref<AiKnowledgeStatistics | null>(null)
const selectedModuleId = ref('')
const detail = ref<AiModuleDetail | null>(null)
const prompt = ref<AiPromptMetadata | null>(null)
const evaluation = ref<AiLatestEvaluation | null>(null)
const loading = ref(false)
const selectionLoading = ref(false)
const error = ref('')
const selectionError = ref('')

const selectedModule = computed(() => modules.value.find((item) => item.id === selectedModuleId.value) ?? null)

const runtimeLabel = computed(() => {
  if (!runtime.value) return '未取得运行状态'
  if (runtime.value.initializationError) return `初始化异常：${runtime.value.initializationError}`
  if (!runtime.value.ready) return '服务未就绪'
  if (!runtime.value.modelConfigured) return '模型未配置'
  return '服务已就绪，模型已配置'
})

const evaluationSummary = computed(() => {
  const item = evaluation.value?.evaluation
  if (!item) return '没有可展示的历史评测记录。'
  if (item.totalCases === null || item.passedCases === null) return '历史评测记录缺少通过数量，不能判断是否全量通过。'
  if (item.passedCases < item.totalCases) return `历史评测记录：${item.passedCases}/${item.totalCases}，尚未达到全量通过。`
  return `历史评测记录：${item.passedCases}/${item.totalCases}，记录显示全部通过。`
})

function readableAction(action: string): string {
  const labels: Record<string, string> = {
    answer_customer_question: '生成客服建议',
    search_knowledge: '检索已导入知识',
    run_online_test: '运行受控在线测试',
  }
  return labels[action] ?? action
}

function formatJson(value: unknown): string { return JSON.stringify(value, null, 2) }

async function selectModule(moduleId: string): Promise<void> {
  if (!moduleId) return
  selectedModuleId.value = moduleId
  selectionLoading.value = true
  selectionError.value = ''
  detail.value = null
  prompt.value = null
  evaluation.value = null
  const [detailResult, promptResult, evaluationResult] = await Promise.allSettled([
    getAiModuleDetail(moduleId),
    getAiModulePrompt(moduleId),
    getAiModuleLatestEvaluation(moduleId),
  ])
  if (detailResult.status === 'fulfilled') detail.value = detailResult.value
  if (promptResult.status === 'fulfilled') prompt.value = promptResult.value
  if (evaluationResult.status === 'fulfilled') evaluation.value = evaluationResult.value
  const failures = [detailResult, promptResult, evaluationResult]
    .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    .map((result) => apiErrorMessage(result.reason))
  if (failures.length) selectionError.value = `部分 AI 只读信息暂时不可用：${failures[0]}`
  selectionLoading.value = false
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  modules.value = []
  runtime.value = null
  knowledge.value = null
  const [modulesResult, runtimeResult, knowledgeResult] = await Promise.allSettled([
    listAiModules(),
    getAiRuntimeStatus(),
    getAiKnowledgeStatistics(),
  ])
  if (modulesResult.status === 'fulfilled') modules.value = modulesResult.value
  if (runtimeResult.status === 'fulfilled') runtime.value = runtimeResult.value
  if (knowledgeResult.status === 'fulfilled') knowledge.value = knowledgeResult.value
  const failures = [modulesResult, runtimeResult, knowledgeResult]
    .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    .map((result) => apiErrorMessage(result.reason))
  if (failures.length) error.value = `部分 AI 运行信息无法读取：${failures[0]}`
  const preferred = modules.value.find((item) => item.implemented) ?? modules.value[0]
  if (preferred) await selectModule(preferred.id)
  loading.value = false
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI 客服平台 / AI 控制中心</p>
        <h1>AI 控制中心</h1>
        <p>此页面只读取 A 服务已经提供的运行、知识、模块、提示词元数据和历史评测信息；不支持修改 Prompt、切换模型或发布知识。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新状态' }}</button>
    </div>

    <p v-if="loading && !runtime && !knowledge" class="notice" role="status">正在读取 AI 服务的真实状态…</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>

    <template v-if="runtime || knowledge">
      <section class="status-grid" aria-label="AI 真实运行状态">
        <article class="card status-card">
          <p class="card-label">服务状态</p>
          <h2>{{ runtimeLabel }}</h2>
          <p v-if="runtime?.initializationError" class="state-note">错误代码：{{ runtime.initializationError }}</p>
          <p v-else class="state-note">ready={{ runtime?.ready ?? '未知' }}；model_configured={{ runtime?.modelConfigured ?? '未知' }}</p>
        </article>
        <article class="card status-card">
          <p class="card-label">知识统计（运行时）</p>
          <h2>{{ knowledge ? `${knowledge.chunkCount} 个知识块` : '未取得' }}</h2>
          <p class="state-note">集合：{{ knowledge?.collectionName ?? '未提供' }}；向量库：{{ knowledge?.vectorDatabase ?? '未提供' }}</p>
          <p class="muted">主知识库文档统计：{{ knowledge?.documentCount ?? '未取得' }}。这不是历史趋势或质量评分。</p>
        </article>
        <article class="card status-card">
          <p class="card-label">模块与模型</p>
          <h2>{{ detail?.modelName || '选择模块后读取' }}</h2>
          <p class="state-note">提供方：{{ detail?.modelProvider || '未提供' }}；已注册模块：{{ modules.length }}</p>
          <p class="muted">模型信息来自 A 模块详情，不从前端推断。</p>
        </article>
      </section>

      <section class="card module-selector" aria-label="AI 模块选择">
        <div><h2>可用模块</h2><p>模块状态来自 A 服务；“规划中”模块不会被当作已启用能力。</p></div>
        <div class="module-tabs">
          <button
            v-for="item in modules"
            :key="item.id"
            class="module-tab"
            :class="{ active: item.id === selectedModuleId }"
            type="button"
            @click="selectModule(item.id)"
          >
            {{ item.name }} <small>{{ displayStatus(item.status) }}</small>
          </button>
        </div>
      </section>

      <section v-if="selectedModule" class="detail-grid">
        <article class="card module-detail">
          <div class="section-title"><div><p class="card-label">当前模块</p><h2>{{ selectedModule.name }}</h2></div><span class="badge">{{ displayStatus(detail?.status ?? selectedModule.status) }}</span></div>
          <p>{{ detail?.description || selectedModule.description || 'A 服务未提供模块说明。' }}</p>
          <p v-if="selectionLoading" class="notice" role="status">正在读取模块详情…</p>
          <p v-else-if="selectionError" class="notice error" role="alert">{{ selectionError }}</p>
          <template v-else-if="detail">
            <dl class="fact-grid">
              <div><dt>模块就绪</dt><dd>{{ detail.ready === null ? '未提供' : detail.ready ? '是' : '否' }}</dd></div>
              <div><dt>模型已配置</dt><dd>{{ detail.modelConfigured === null ? '未提供' : detail.modelConfigured ? '是' : '否' }}</dd></div>
              <div><dt>可查询知识</dt><dd>{{ detail.knowledgeCount ?? '未提供' }}</dd></div>
              <div><dt>安全预览</dt><dd>{{ detail.safePreview || '未提供' }}</dd></div>
            </dl>
            <div class="action-list"><strong>支持的受控操作</strong><span v-for="action in detail.supportedActions" :key="action" class="badge">{{ readableAction(action) }}</span><span v-if="detail.supportedActions.length === 0" class="muted">当前未声明可用操作。</span></div>
          </template>
        </article>

        <article class="card prompt-detail">
          <p class="card-label">提示词元数据（只读）</p>
          <h2>{{ prompt?.promptVersion || detail?.promptVersion || '未提供' }}</h2>
          <p>{{ prompt?.safePreview || detail?.safePreview || '没有可展示的安全预览。' }}</p>
          <dl class="compact-facts">
            <div><dt>来源</dt><dd>{{ prompt?.sourceType || '未提供' }}</dd></div>
            <div><dt>更新方式</dt><dd>{{ prompt?.updatedAt || '未提供' }}</dd></div>
          </dl>
          <details class="technical-details"><summary>查看提示词技术元数据</summary><dl class="compact-facts"><div><dt>哈希</dt><dd>{{ prompt?.promptHash || detail?.promptHash || '未提供' }}</dd></div><div><dt>版本</dt><dd>{{ prompt?.promptVersion || detail?.promptVersion || '未提供' }}</dd></div></dl><pre>{{ formatJson(prompt?.raw ?? detail?.raw) }}</pre></details>
        </article>
      </section>

      <section class="card evaluation-card">
        <div class="section-title"><div><p class="card-label">历史评测</p><h2>{{ evaluationSummary }}</h2></div><span class="badge">{{ displayStatus(evaluation?.status) }}</span></div>
        <template v-if="evaluation?.evaluation">
          <dl class="fact-grid">
            <div><dt>执行时间</dt><dd>{{ evaluation.evaluation.executedAt || '未提供' }}</dd></div>
            <div><dt>数据集版本</dt><dd>{{ evaluation.evaluation.datasetVersion || '未提供' }}</dd></div>
            <div><dt>通过率</dt><dd>{{ evaluation.evaluation.passRate === null ? '未提供' : `${evaluation.evaluation.passRate}%` }}</dd></div>
            <div><dt>未通过案例</dt><dd>{{ evaluation.evaluation.failedCaseIds.length }}</dd></div>
          </dl>
          <details class="technical-details"><summary>查看评测检查项与原始记录</summary><pre>{{ formatJson(evaluation.raw) }}</pre></details>
        </template>
        <p v-else class="muted">评测接口没有返回可展示的历史记录；页面不会以空白或默认“通过”代替。</p>
      </section>
    </template>

    <ProductEmptyState
      v-if="!loading && !error && modules.length === 0 && !runtime && !knowledge"
      title="暂无可显示的 AI 运行信息"
      description="A 服务没有返回模块、运行状态或知识统计。请先检查 AI 服务连接；页面不会生成 Mock 信息。"
      action-label="返回运营概览"
      to="/overview"
    />
  </main>
</template>

<style scoped>
.eyebrow, .card-label { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.status-grid, .detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 18px; }.detail-grid { grid-template-columns: minmax(0, 1.35fr) minmax(280px, .85fr); }.status-card h2, .module-detail h2, .prompt-detail h2, .evaluation-card h2 { margin: 0 0 8px; color: #172554; font-size: 18px; }.state-note { margin: 0; color: #526981; }.muted { color: #6b7b91; font-size: 13px; line-height: 1.55; }.module-selector { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }.module-selector h2 { margin: 0 0 4px; font-size: 18px; }.module-selector p { margin: 0; color: #617087; font-size: 13px; }.module-tabs { display: flex; flex-wrap: wrap; gap: 8px; }.module-tab { padding: 8px 10px; border: 1px solid #cbd7e6; border-radius: 8px; background: #fff; color: #34516f; font: inherit; cursor: pointer; }.module-tab.active { border-color: #285493; background: #edf4ff; color: #173d73; }.module-tab small { margin-left: 4px; color: #65758b; }.section-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }.module-detail > p { line-height: 1.6; }.fact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 16px 0 0; }.fact-grid div, .compact-facts div { min-width: 0; }.fact-grid dt, .compact-facts dt { color: #6b7b91; font-size: 12px; }.fact-grid dd, .compact-facts dd { margin: 4px 0 0; overflow-wrap: anywhere; line-height: 1.5; }.action-list { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 18px; }.action-list strong { margin-right: 3px; font-size: 13px; }.compact-facts { display: grid; gap: 10px; margin: 14px 0; }.technical-details { margin-top: 16px; border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details pre { max-width: 100%; max-height: 260px; overflow: auto; padding: 10px; border-radius: 8px; background: #f4f7fb; color: #33445c; font-size: 12px; white-space: pre-wrap; }.evaluation-card { margin-bottom: 16px; }
@media (max-width: 920px) { .status-grid, .detail-grid { grid-template-columns: 1fr; }.module-selector { align-items: flex-start; flex-direction: column; } }
</style>
