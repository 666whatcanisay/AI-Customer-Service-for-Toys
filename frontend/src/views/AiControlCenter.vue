<template>
  <div class="ai-control-center" data-testid="ai-control-center">
    <section class="hero">
      <div>
        <p class="eyebrow">AI CONTROL CENTER · V1</p>
        <h1>AI 控制中心</h1>
        <p>
          技术负责人可在一个只读快照中查看 RAG、qwen、评测、Badcase 与反馈分析的状态。
          本页不执行 Prompt、知识、模型或业务数据修改。
        </p>
      </div>
      <div class="hero-actions">
        <span class="readonly-badge">只读模式</span>
        <button type="button" :disabled="loading" @click="load">
          {{ loading ? '加载中…' : '刷新真实数据' }}
        </button>
      </div>
    </section>

    <el-alert
      v-if="loadError"
      :title="loadError"
      description="未使用任何本地替代数据；对应区域将显示“暂无数据”，可在 A 服务恢复后刷新。"
      type="warning"
      :closable="false"
      show-icon
      data-testid="ai-control-center-error"
    />

    <section class="section-heading">
      <div>
        <p class="eyebrow">OVERVIEW</p>
        <h2>AI 概览</h2>
      </div>
      <span>{{ overviewScope }}</span>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">CAPABILITY INVENTORY</p>
        <h2>AI 能力盘点</h2>
      </div>
      <span>运行、数据可用性和人工边界分开显示</span>
    </section>

    <section class="capability-grid" data-testid="ai-capability-inventory">
      <article v-for="item in snapshot?.capabilities ?? []" :key="item.capabilityId" class="capability-card">
        <div class="module-title">
          <h3>{{ item.name }}</h3>
          <span :class="['status-pill', `status-${item.status}`]">{{ controlStatusLabel(item.status) }}</span>
        </div>
        <p>{{ item.summary }}</p>
        <div class="capability-meta">
          <span>数据：{{ dataStatusLabel(item.dataStatus) }}</span>
          <span>操作：{{ operatorModeLabel(item.operatorMode) }}</span>
        </div>
      </article>
      <div v-if="!snapshot" class="empty-state">暂无数据</div>
    </section>

    <section class="overview-grid" data-testid="ai-overview">
      <article class="metric-card">
        <small>模型状态</small>
        <strong :class="{ positive: capability?.ready === true, negative: capability?.status === 'ERROR' }">
          {{ modelStatus }}
        </strong>
        <span>{{ modelDescriptor }}</span>
      </article>
      <article class="metric-card">
        <small>知识规模</small>
        <strong>{{ displayNumber(capability?.knowledgeCount) }}</strong>
        <span>已索引知识块</span>
      </article>
      <article class="metric-card">
        <small>AI 调用</small>
        <strong>{{ displayNumber(capability?.callCount) }}</strong>
        <span>{{ callScope }}</span>
      </article>
      <article class="metric-card">
        <small>质量指标</small>
        <strong :class="{ positive: evaluation?.passRate !== null && evaluation?.passRate !== undefined }">
          {{ displayRate(evaluation?.passRate) }}
        </strong>
        <span>{{ evaluation ? '最近一次可读评测通过率' : '暂无可读评测结果' }}</span>
      </article>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">MODULES</p>
        <h2>AI 模块</h2>
      </div>
      <span>运行能力与产品规划分开呈现</span>
    </section>

    <section class="module-grid">
      <article class="module-card active-module" data-testid="ai-customer-service-module">
        <div class="module-title">
          <div>
            <small>已接入</small>
            <h3>AI 客服</h3>
          </div>
          <span :class="['status-pill', `status-${capability?.status ?? 'UNKNOWN'}`]">
            {{ statusLabel(capability?.status) }}
          </span>
        </div>
        <p>{{ capability?.description || '暂无数据' }}</p>
        <dl>
          <div><dt>模型</dt><dd>{{ displayText(capability?.modelName) }}</dd></div>
          <div><dt>知识块</dt><dd>{{ displayNumber(capability?.knowledgeCount) }}</dd></div>
          <div><dt>平均耗时</dt><dd>{{ displayLatency(capability?.averageLatencyMs) }}</dd></div>
        </dl>
      </article>

      <article v-for="plan in productPlans" :key="plan.name" class="module-card planned-module">
        <div class="module-title">
          <div>
            <small>产品规划 · 未接入</small>
            <h3>{{ plan.name }}</h3>
          </div>
          <span class="status-pill status-PLANNED">规划中</span>
        </div>
        <p>{{ plan.description }}</p>
        <span class="plan-note">仅展示方向，不读取或执行任何业务数据。</span>
      </article>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">EVALUATION</p>
        <h2>AI 评测中心</h2>
      </div>
      <span>只读取最新已保存的真实评测摘要</span>
    </section>

    <section class="evaluation-panel" data-testid="ai-evaluation-center">
      <template v-if="evaluation">
        <div class="evaluation-summary">
          <div>
            <small>评测</small>
            <strong>{{ displayText(evaluation.evaluationId) }}</strong>
            <span>执行于 {{ displayDate(evaluation.executedAt) }}</span>
          </div>
          <div>
            <small>评测结果</small>
            <strong>{{ displayRate(evaluation.passRate) }}</strong>
            <span>{{ displayNumber(evaluation.passedCases) }} / {{ displayNumber(evaluation.totalCases) }} 通过</span>
          </div>
          <div>
            <small>评测数据版本</small>
            <strong>{{ displayText(evaluation.datasetVersion) }}</strong>
            <span>仅展示 A 侧保存摘要</span>
          </div>
        </div>
        <div class="evaluation-version-row">
          <div><small>当前模块模型版本</small><strong>{{ displayText(snapshot?.evaluation.currentModelVersion) }}</strong></div>
          <div><small>当前评测 Prompt 版本</small><strong>{{ displayText(snapshot?.evaluation.currentPromptVersion) }}</strong></div>
          <div><small>未通过案例</small><strong>{{ failedCases }}</strong></div>
        </div>
        <p class="evaluation-caveat">
          {{ snapshot?.evaluation.versionNote || '暂无数据' }}
        </p>
        <div class="check-grid">
          <div v-for="check in evaluationChecks" :key="check.key">
            <small>{{ check.label }}</small>
            <strong>{{ displayNumber(evaluation.checks[check.key]) }}</strong>
          </div>
        </div>
      </template>
      <div v-else class="empty-state" data-testid="evaluation-empty">暂无数据</div>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">BADCASE</p>
        <h2>Badcase 中心</h2>
      </div>
      <span>仅展示问题分类，不回显客服原始内容</span>
    </section>

    <section class="badcase-panel" data-testid="badcase-center">
      <div class="badcase-intro">
        <strong>{{ snapshot ? '暂无数据' : '加载失败' }}</strong>
        <span>{{ snapshot?.badcase.reason || '未读取到控制中心快照。' }}</span>
      </div>
      <div class="badcase-grid">
        <article v-for="category in snapshot?.badcase.categories ?? badcaseCategories" :key="category.category">
          <small>{{ category.category }}</small>
          <strong>{{ displayNumber(category.count) }}</strong>
          <span>{{ badcaseCategoryLabel(category.category) }}</span>
        </article>
      </div>
      <details v-if="snapshot" class="technical-details">
        <summary>技术信息</summary>
        <p>原始客户内容：{{ snapshot.badcase.rawContentExposed ? '已暴露' : '未暴露' }}</p>
        <p>状态：{{ controlStatusLabel(snapshot.badcase.status) }}</p>
      </details>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">FEEDBACK ANALYSIS</p>
        <h2>反馈分析</h2>
      </div>
      <span>仅记录成功写回后的进程内聚合回执</span>
    </section>

    <section class="feedback-panel" data-testid="feedback-analysis-center">
      <template v-if="snapshot">
        <div class="feedback-summary">
          <div><small>执行方式</small><strong>{{ feedbackModeLabel(snapshot.feedbackAnalysis.status) }}</strong><span>不自动轮询或运行</span></div>
          <div><small>C 集成</small><strong>{{ configurationLabel(snapshot.feedbackAnalysis.platformIntegrationStatus) }}</strong><span>只由显式本机任务使用</span></div>
          <div><small>最近分析</small><strong>{{ snapshot.feedbackAnalysis.latestRun ? displayDate(snapshot.feedbackAnalysis.latestRun.completedAt) : '暂无数据' }}</strong><span>{{ snapshot.feedbackAnalysis.latestRun ? `${displayNumber(snapshot.feedbackAnalysis.latestRun.completedAnalysisCount)} 条安全回执` : '没有进程内回执' }}</span></div>
        </div>
        <div v-if="snapshot.feedbackAnalysis.latestRun" class="feedback-run-grid">
          <div><small>输入反馈</small><strong>{{ displayNumber(snapshot.feedbackAnalysis.latestRun.inputFeedbackCount) }}</strong></div>
          <div><small>成功写回</small><strong>{{ displayNumber(snapshot.feedbackAnalysis.latestRun.analyzedWritebackCount) }}</strong></div>
          <div><small>幂等验证</small><strong>{{ displayNumber(snapshot.feedbackAnalysis.latestRun.idempotencyVerifiedCount) }}</strong></div>
        </div>
        <details class="technical-details">
          <summary>技术信息</summary>
          <p>配置模型：{{ displayText(snapshot.feedbackAnalysis.configuredModelVersion) }}</p>
          <p>Prompt 版本：{{ displayText(snapshot.feedbackAnalysis.promptVersion) }}</p>
          <p>结果留存：{{ snapshot.feedbackAnalysis.resultRetention === 'PROCESS_MEMORY_ONLY' ? '仅当前 A 进程内聚合' : snapshot.feedbackAnalysis.resultRetention }}</p>
          <p>原始客户内容：{{ snapshot.feedbackAnalysis.rawContentExposed ? '已暴露' : '未暴露' }}</p>
        </details>
      </template>
      <div v-else class="empty-state">暂无数据</div>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">PROMPT</p>
        <h2>Prompt 管理</h2>
      </div>
      <span>第一阶段只读</span>
    </section>

    <section class="prompt-panel" data-testid="prompt-readonly-center">
      <div class="prompt-meta-grid">
        <div><small>当前版本</small><strong>{{ displayText(prompt?.promptVersion) }}</strong></div>
        <div><small>更新时间</small><strong>{{ displayText(prompt?.updatedAt) }}</strong></div>
        <div><small>管理方式</small><strong>{{ displayText(prompt?.sourceType) }}</strong></div>
        <div><small>效果</small><strong>{{ displayText(prompt?.safePreview) }}</strong></div>
      </div>
      <ul v-if="prompt?.answerStyleRules.length" class="prompt-rules">
        <li v-for="rule in prompt.answerStyleRules" :key="rule">{{ rule }}</li>
      </ul>
      <div v-else class="empty-inline">暂无数据</div>
      <details v-if="prompt" class="technical-details">
        <summary>技术信息</summary>
        <p>模块：{{ prompt.moduleId }}</p>
        <p>Prompt 指纹：{{ prompt.promptHash }}</p>
      </details>
      <el-alert
        title="Prompt 管理为只读展示"
        description="本页没有编辑、发布或自动修改 Prompt 的能力，也不会更新知识或模型。"
        type="info"
        :closable="false"
        show-icon
      />
    </section>

    <details class="data-source-details">
      <summary>数据来源与展示边界</summary>
      <ul v-if="snapshot">
        <li v-for="source in snapshot.dataSources" :key="source.sourceId">
          <code>{{ source.readPath }}</code>：{{ source.purpose }}
        </li>
        <li>控制中心快照由 <code>GET /api/admin/ai/control-center</code> 提供；未发布的 Badcase 聚合显示“暂无数据”。</li>
      </ul>
      <p v-else>暂无数据</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { aiControlCenterClient } from '@/api/aiControlCenterClient'
import { toRagClientError } from '@/api/errorMapper'
import type { AiControlCenterSnapshot, AiControlCenterStatus } from '@/api/aiControlCenterTypes'

const snapshot = ref<AiControlCenterSnapshot | null>(null)
const loading = ref(false)
const loadError = ref('')
let activeController: AbortController | null = null

const productPlans = [
  { name: '售后 AI', description: '规划中：协助识别售后意图，保留人工确认与现有业务边界。' },
  { name: '工单 AI', description: '规划中：辅助归纳工单信息，不自动创建、分派或关闭工单。' },
  { name: '退款风险 AI', description: '规划中：提供风险提示，不自动退款、拦截订单或执行资金操作。' }
]

const badcaseCategories = [
  { category: 'FACT_ERROR' as const, count: null },
  { category: 'MISSING_INFO' as const, count: null },
  { category: 'STYLE_ISSUE' as const, count: null },
  { category: 'RISK_ISSUE' as const, count: null }
]

const evaluationChecks = [
  { key: 'action', label: '动作' },
  { key: 'source_ids', label: '来源标识' },
  { key: 'key_facts', label: '关键事实' },
  { key: 'required_fields', label: '必填字段' },
  { key: 'risk_level', label: '风险等级' },
  { key: 'scope', label: '范围隔离' }
]

const modelStatus = computed(() => {
  if (!snapshot.value) return '暂无数据'
  if (snapshot.value.customerService.ready === true) return '运行中'
  if (snapshot.value.customerService.status === 'ERROR') return '异常'
  if (snapshot.value.customerService.status === 'PAUSED') return '已暂停'
  return '未就绪'
})

const modelDescriptor = computed(() => {
  if (!snapshot.value) return '暂无数据'
  return [snapshot.value.customerService.modelProvider, snapshot.value.customerService.modelName].filter(Boolean).join(' · ') || '暂无数据'
})

const callScope = computed(() => {
  if (!snapshot.value?.customerService.metricsScope) return '暂无数据'
  return snapshot.value.customerService.metricsScope === 'since_start' ? '当前进程启动以来' : snapshot.value.customerService.metricsScope
})

const overviewScope = computed(() =>
  snapshot.value ? `统一快照 · ${displayDate(snapshot.value.generatedAt)}` : '暂无数据'
)

const capability = computed(() => snapshot.value?.customerService ?? null)
const prompt = computed(() => snapshot.value?.prompt ?? null)
const evaluation = computed(() => snapshot.value?.evaluation.evaluation ?? null)

const failedCases = computed(() => {
  if (!evaluation.value) return '暂无数据'
  return evaluation.value.failedCaseIds.length ? evaluation.value.failedCaseIds.join('、') : '无'
})

const displayText = (value: string | null | undefined) => value || '暂无数据'
const displayNumber = (value: number | null | undefined) =>
  value === null || value === undefined ? '暂无数据' : new Intl.NumberFormat('zh-CN').format(value)
const displayRate = (value: number | null | undefined) =>
  value === null || value === undefined ? '暂无数据' : `${Number(value).toFixed(1)}%`
const displayLatency = (value: number | null | undefined) =>
  value === null || value === undefined ? '暂无数据' : `${Number(value).toFixed(1)} ms`
const displayDate = (value: string | null | undefined) => {
  if (!value) return '暂无数据'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

const statusLabels: Record<'RUNNING' | 'PAUSED' | 'ERROR' | 'TESTING' | 'DEVELOPING' | 'PLANNED', string> = {
  RUNNING: '运行中',
  PAUSED: '已暂停',
  ERROR: '异常',
  TESTING: '测试中',
  DEVELOPING: '开发中',
  PLANNED: '规划中'
}

const statusLabel = (status: 'RUNNING' | 'PAUSED' | 'ERROR' | 'TESTING' | 'DEVELOPING' | 'PLANNED' | undefined) =>
  status ? statusLabels[status] : '暂无数据'

const controlStatusLabel = (status: AiControlCenterStatus) => ({
  RUNNING: '运行中', PAUSED: '已暂停', ERROR: '异常', PLANNED: '规划中',
  CONFIGURED: '已配置', NOT_CONFIGURED: '未配置', AVAILABLE: '可用',
  NOT_AVAILABLE: '暂无数据', MANUAL_ONLY: '人工显式运行'
}[status])

const dataStatusLabel = (status: 'AVAILABLE' | 'NOT_AVAILABLE') =>
  status === 'AVAILABLE' ? '可读' : '暂无数据'
const operatorModeLabel = (mode: 'READ_ONLY' | 'EXPLICIT_MANUAL') =>
  mode === 'READ_ONLY' ? '只读' : '人工显式运行'
const configurationLabel = (status: 'CONFIGURED' | 'NOT_CONFIGURED') =>
  status === 'CONFIGURED' ? '已配置' : '未配置'
const feedbackModeLabel = (status: 'MANUAL_ONLY' | 'NOT_CONFIGURED') =>
  status === 'MANUAL_ONLY' ? '人工显式运行' : '未配置'
const badcaseCategoryLabel = (category: string) => ({
  FACT_ERROR: '事实问题', MISSING_INFO: '信息缺失', STYLE_ISSUE: '表达问题', RISK_ISSUE: '风险问题'
}[category] ?? category)

const load = async () => {
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  loadError.value = ''
  snapshot.value = null
  try {
    snapshot.value = await aiControlCenterClient.getControlCenter(controller.signal)
  } catch (error) {
    if (!controller.signal.aborted) loadError.value = toRagClientError(error).message
  } finally {
    if (activeController === controller) loading.value = false
  }
}

onMounted(() => { void load() })
onBeforeUnmount(() => activeController?.abort())
</script>

<style scoped>
.ai-control-center { width: min(1320px, 100%); margin: 0 auto; color: #172033; }
.hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 28px; border: 1px solid #ccddef; border-radius: 20px; background: radial-gradient(circle at 0 0, rgb(93 133 244 / 22%), transparent 28rem), #fff; box-shadow: 0 12px 30px rgb(24 58 118 / 7%); }
.eyebrow { margin: 0 0 6px; color: #3065cd; font-size: 11px; font-weight: 800; letter-spacing: .12em; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 9px; font-size: clamp(26px, 3vw, 38px); }
.hero > div:first-child > p:not(.eyebrow) { max-width: 760px; margin-bottom: 0; color: #607089; line-height: 1.65; }
.hero-actions { display: flex; flex: 0 0 auto; align-items: center; gap: 9px; }
.hero-actions button { min-height: 38px; padding: 8px 13px; border: 1px solid #2f63cf; border-radius: 9px; background: #2f63cf; color: #fff; font-weight: 700; cursor: pointer; }
.hero-actions button:disabled { cursor: wait; opacity: .72; }
.readonly-badge { padding: 5px 9px; border-radius: 999px; background: #e9f0ff; color: #2e5bb8; font-size: 12px; font-weight: 800; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 14px; margin-top: 27px; margin-bottom: 12px; }
.section-heading h2 { margin-bottom: 0; font-size: 21px; }
.section-heading > span { color: #748198; font-size: 12px; text-align: right; }
.overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 13px; }
.metric-card, .module-card, .capability-card, .evaluation-panel, .badcase-panel, .feedback-panel, .prompt-panel { border: 1px solid #d9e4f0; border-radius: 15px; background: #fff; box-shadow: 0 7px 18px rgb(31 61 109 / 4%); }
.metric-card { display: grid; gap: 6px; min-height: 132px; padding: 18px; }
.metric-card small, .module-card small, .evaluation-panel small, .badcase-panel small, .prompt-panel small { color: #728099; font-size: 12px; }
.metric-card strong { color: #56677d; font-size: 22px; }
.metric-card strong.positive { color: #19734d; }
.metric-card strong.negative { color: #af3d36; }
.metric-card span { color: #728099; font-size: 12px; line-height: 1.45; overflow-wrap: anywhere; }
.module-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 13px; }
.capability-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 13px; }
.capability-card { display: grid; min-width: 0; gap: 11px; min-height: 185px; padding: 17px; }
.capability-card h3 { margin: 0; font-size: 15px; }
.capability-card p { margin: 0; color: #66768c; font-size: 12px; line-height: 1.55; }
.capability-meta { display: grid; gap: 5px; margin-top: auto; color: #718096; font-size: 11px; }
.module-card { display: flex; min-width: 0; min-height: 205px; flex-direction: column; padding: 18px; }
.active-module { border-color: #9bcdb5; background: linear-gradient(145deg, #fff, #f4fffa); }
.planned-module { background: #fbfcfe; }
.module-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 9px; }
.module-title h3 { margin: 4px 0 0; font-size: 17px; }
.status-pill { flex: 0 0 auto; padding: 4px 8px; border-radius: 999px; background: #eef2f7; color: #57697f; font-size: 11px; font-weight: 800; }
.status-RUNNING { background: #dff6e9; color: #16724b; }
.status-ERROR { background: #ffe6e4; color: #a43a32; }
.status-PAUSED, .status-PLANNED { background: #fff2ce; color: #805c11; }
.module-card p { margin: 13px 0; color: #66768c; font-size: 13px; line-height: 1.55; }
.module-card dl { display: grid; gap: 7px; margin: auto 0 0; }
.module-card dl div { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 7px; font-size: 12px; }
.module-card dt { color: #7b879a; }
.module-card dd { margin: 0; color: #31445f; overflow-wrap: anywhere; }
.plan-note { margin-top: auto; color: #8692a3; font-size: 11px; line-height: 1.5; }
.evaluation-panel, .badcase-panel, .feedback-panel, .prompt-panel { padding: 20px; }
.evaluation-summary, .evaluation-version-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.evaluation-summary > div, .evaluation-version-row > div { display: grid; gap: 5px; min-width: 0; padding: 13px; border-radius: 11px; background: #f6f9fd; }
.evaluation-summary strong, .evaluation-version-row strong { color: #263b59; font-size: 16px; overflow-wrap: anywhere; }
.evaluation-summary span { color: #728099; font-size: 12px; line-height: 1.45; }
.evaluation-version-row { margin-top: 12px; }
.evaluation-version-row strong { font-size: 13px; }
.evaluation-caveat { margin: 13px 0; color: #76849a; font-size: 12px; line-height: 1.55; }
.check-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 9px; }
.check-grid div { display: grid; gap: 5px; padding: 11px; border: 1px solid #e0e7f0; border-radius: 10px; }
.check-grid strong { font-size: 15px; }
.empty-state, .empty-inline { padding: 20px; border: 1px dashed #cdd8e6; border-radius: 10px; color: #7c899b; text-align: center; }
.badcase-intro { display: flex; align-items: baseline; gap: 12px; padding: 12px 0 17px; color: #6d7a8e; font-size: 13px; line-height: 1.55; }
.badcase-intro strong { color: #805b11; white-space: nowrap; }
.badcase-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 11px; }
.badcase-grid article { display: grid; gap: 5px; padding: 14px; border: 1px solid #e1e7f0; border-radius: 11px; background: #fbfcfe; }
.badcase-grid strong { color: #7c899b; font-size: 15px; }
.badcase-grid span { color: #596a81; font-size: 12px; }
.feedback-summary, .feedback-run-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.feedback-summary > div, .feedback-run-grid > div { display: grid; gap: 5px; min-width: 0; padding: 13px; border-radius: 11px; background: #f6f9fd; }
.feedback-summary strong, .feedback-run-grid strong { color: #263b59; font-size: 15px; overflow-wrap: anywhere; }
.feedback-summary span { color: #728099; font-size: 12px; line-height: 1.45; }
.feedback-run-grid { margin-top: 12px; }
.prompt-meta-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.prompt-meta-grid > div { display: grid; gap: 6px; min-width: 0; padding: 13px; border-radius: 11px; background: #f6f9fd; }
.prompt-meta-grid strong { color: #263b59; font-size: 13px; line-height: 1.5; overflow-wrap: anywhere; }
.prompt-rules { display: grid; gap: 6px; margin: 15px 0; padding: 13px 13px 13px 32px; border-radius: 11px; background: #fbfcfe; color: #5d6e84; font-size: 12px; line-height: 1.5; }
.prompt-panel :deep(.el-alert) { margin-top: 15px; }
.technical-details { margin-top: 14px; padding: 11px 13px; border: 1px solid #e0e7f0; border-radius: 10px; background: #fbfcfe; color: #617088; font-size: 12px; line-height: 1.55; }
.technical-details summary { color: #395985; font-weight: 800; cursor: pointer; }
.technical-details p { margin: 8px 0 0; overflow-wrap: anywhere; }
.data-source-details { margin-top: 22px; padding: 15px 18px; border: 1px solid #d9e4f0; border-radius: 13px; background: rgb(255 255 255 / 72%); color: #617088; font-size: 12px; line-height: 1.65; }
.data-source-details summary { color: #395985; font-weight: 800; cursor: pointer; }
.data-source-details ul { margin: 10px 0 0; padding-left: 19px; }
.data-source-details code { color: #315fc0; font-family: Consolas, monospace; }
@media (max-width: 1120px) { .overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .module-grid, .capability-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .check-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 720px) { .hero { flex-direction: column; padding: 20px; } .hero-actions { width: 100%; justify-content: space-between; } .section-heading { align-items: flex-start; flex-direction: column; } .section-heading > span { text-align: left; } .overview-grid, .module-grid, .capability-grid, .evaluation-summary, .evaluation-version-row, .badcase-grid, .feedback-summary, .feedback-run-grid, .prompt-meta-grid, .check-grid { grid-template-columns: 1fr; } .badcase-intro { align-items: flex-start; flex-direction: column; gap: 5px; } }
</style>
