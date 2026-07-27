<template>
  <main class="ai-control-center" data-testid="ai-control-center">
    <section class="hero">
      <div>
        <p class="eyebrow">AI CONTROL CENTER · V2</p>
        <h1>AI 控制中心</h1>
        <p>面向技术负责人的只读工作台：集中查看 RAG、qwen、本地评测、质量归因与反馈分析的真实快照。这里没有 Prompt、知识、模型或业务数据的修改入口。</p>
      </div>
      <div class="hero-actions">
        <span class="readonly-badge">只读模式</span>
        <button type="button" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新真实数据' }}
        </button>
      </div>
    </section>

    <section class="workspace-meta" aria-label="workbench status">
      <span>控制中心：{{ snapshot ? `已更新 ${displayDate(snapshot.generatedAt)}` : '暂无数据' }}</span>
      <span>运营快照：{{ operations ? `已更新 ${displayDate(operations.generatedAt)}` : operationsError || '暂无数据' }}</span>
      <span>质量基线：{{ quality?.status === 'AVAILABLE' ? '已读取真实评测' : qualityError || '暂无数据' }}</span>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">OVERVIEW</p>
        <h2>AI 概览</h2>
      </div>
      <span>模型状态、知识状态与质量状态来自独立只读接口</span>
    </section>
    <p v-if="operationsError" class="section-error" data-testid="operations-error">{{ operationsError }}</p>
    <section class="metric-grid" data-testid="ai-overview">
      <article class="metric-card">
        <small>模型状态</small>
        <strong :class="{ positive: operations?.modelStatus.serviceReady, negative: operations?.modelStatus.status === 'NOT_CONFIGURED' }">
          {{ modelStatusLabel }}
        </strong>
        <span>{{ modelDescriptor }}</span>
        <p>{{ operations?.modelStatus.explanation || '暂无数据' }}</p>
      </article>
      <article class="metric-card">
        <small>知识状态</small>
        <strong>{{ displayNumber(operations?.knowledgeCoverage.indexedChunkCount) }}</strong>
        <span>已索引知识块</span>
        <p>{{ operations?.knowledgeCoverage.explanation || '暂无数据' }}</p>
      </article>
      <article class="metric-card">
        <small>回答质量</small>
        <strong :class="{ positive: operations?.answerQuality.status === 'AVAILABLE' }">{{ displayRate(operations?.answerQuality.passRatePercent) }}</strong>
        <span>{{ displayNumber(operations?.answerQuality.passedCaseCount) }} / {{ displayNumber(operations?.answerQuality.evaluatedCaseCount) }} 通过</span>
        <p>{{ operations?.answerQuality.explanation || '暂无数据' }}</p>
      </article>
      <article class="metric-card">
        <small>AI 回答量</small>
        <strong>{{ displayNumber(operations?.answerVolume.processedRequestCount) }}</strong>
        <span>{{ metricScopeLabel(operations?.answerVolume.metricsScope) }}</span>
        <p>{{ operations?.answerVolume.explanation || '暂无数据' }}</p>
      </article>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">CAPABILITY INVENTORY</p>
        <h2>AI 能力盘点</h2>
      </div>
      <span>状态、数据可用性与人工边界分开呈现</span>
    </section>
    <p v-if="controlError" class="section-error" data-testid="control-center-error">{{ controlError }}</p>
    <section class="capability-grid" data-testid="ai-capability-inventory">
      <article v-for="item in snapshot?.capabilities ?? []" :key="item.capabilityId" class="capability-card">
        <div class="card-title"><h3>{{ item.name }}</h3><span :class="['status-pill', `status-${item.status}`]">{{ controlStatusLabel(item.status) }}</span></div>
        <p>{{ item.summary }}</p>
        <div class="capability-meta"><span>数据：{{ dataStatusLabel(item.dataStatus) }}</span><span>操作：{{ operatorModeLabel(item.operatorMode) }}</span></div>
      </article>
      <div v-if="!snapshot && !controlError" class="empty-state">暂无数据</div>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">EVALUATION</p>
        <h2>评测中心</h2>
      </div>
      <span>只显示已保存的真实评测、版本和安全证据</span>
    </section>
    <p v-if="qualityError" class="section-error" data-testid="quality-error">{{ qualityError }}</p>
    <section class="panel" data-testid="ai-evaluation-center">
      <template v-if="quality?.summary">
        <div class="summary-grid">
          <div><small>评测结果</small><strong>{{ displayRate(quality.summary.passRatePercent) }}</strong><span>{{ quality.summary.passedCaseCount }} / {{ quality.summary.totalCaseCount }} 通过</span></div>
          <div><small>评测版本</small><strong>{{ quality.summary.evaluationId }}</strong><span>{{ displayDate(quality.summary.executedAt) }}</span></div>
          <div><small>数据集版本</small><strong>{{ quality.summary.datasetVersion }}</strong><span>{{ quality.summary.failedCaseCount }} 个未通过 CASE</span></div>
          <div><small>运行版本</small><strong>{{ displayText(snapshot?.evaluation.currentModelVersion) }}</strong><span>Prompt {{ displayText(snapshot?.evaluation.currentPromptVersion) }}</span></div>
        </div>
        <div class="check-grid">
          <div v-for="check in quality.summary.checks" :key="check.check"><small>{{ checkLabel(check.check) }}</small><strong>{{ displayNumber(check.passedCaseCount) }}</strong></div>
        </div>
        <details class="technical-details">
          <summary>评测证据（安全摘要）</summary>
          <ul class="case-list">
            <li v-for="item in quality.failedCases" :key="item.caseId"><code>{{ item.caseId }}</code> · {{ item.categories.map(diagnosisLabel).join('、') }} · {{ item.evaluatorFailureClasses.join('、') || '无直接失败类' }}</li>
          </ul>
          <p v-if="!quality.failedCases.length">暂无未通过 CASE 摘要。</p>
          <p>原始题目、回答、来源正文、事实文本和 Prompt 均未展示。</p>
        </details>
      </template>
      <div v-else class="empty-state" data-testid="evaluation-empty">暂无数据</div>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">QUALITY ANALYSIS</p>
        <h2>问题分析与优化建议</h2>
      </div>
      <span>结论来自评测器信号；仅给出人工下一步</span>
    </section>
    <section class="analysis-grid" data-testid="quality-analysis-center">
      <article class="panel">
        <h3>问题归因</h3>
        <template v-if="quality?.causeFindings.length">
          <div v-for="finding in quality.causeFindings" :key="finding.category" class="finding-row">
            <div><span class="category-label">{{ diagnosisLabel(finding.category) }}</span><strong>{{ displayNumber(finding.affectedCaseCount) }} 个 CASE</strong></div>
            <p>{{ finding.conclusion }}</p>
            <small>人工验证：{{ finding.recommendedVerification }}</small>
          </div>
        </template>
        <div v-else class="empty-state">暂无数据</div>
      </article>
      <article class="panel">
        <h3>优化建议</h3>
        <template v-if="quality?.recommendations.length">
          <div v-for="item in quality.recommendations" :key="`${item.priority}-${item.category}`" class="recommendation-row">
            <div><span :class="['priority', `priority-${item.priority}`]">{{ item.priority }}</span><strong>{{ diagnosisLabel(item.category) }}</strong></div>
            <p>{{ item.recommendation }}</p>
            <small>{{ item.rationale }}</small>
          </div>
        </template>
        <div v-else class="empty-state">暂无数据</div>
      </article>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">BADCASE</p>
        <h2>Badcase 中心</h2>
      </div>
      <span>只显示问题分类；不回显客服原始内容</span>
    </section>
    <section class="panel" data-testid="badcase-center">
      <p class="panel-intro">{{ operations?.badcase.explanation || '暂无数据' }}</p>
      <div class="badcase-grid">
        <article v-for="category in badcaseCategories" :key="category"><small>{{ category }}</small><strong>{{ displayNumber(badcaseCount(category)) }}</strong><span>{{ badcaseLabel(category) }}</span></article>
      </div>
      <details v-if="operations" class="technical-details"><summary>技术信息</summary><p>状态：{{ controlStatusLabel(operations.badcase.status) }}；原始客户内容：未暴露。</p></details>
    </section>

    <section class="section-heading">
      <div>
        <p class="eyebrow">EXCEPTIONS</p>
        <h2>AI 异常状态与下一步</h2>
      </div>
      <span>仅说明原因和建议操作，不执行自动动作</span>
    </section>
    <section class="analysis-grid" data-testid="ai-exception-center">
      <article class="panel">
        <h3>当前提示</h3>
        <template v-if="operations?.notices.length">
          <div v-for="notice in operations.notices" :key="notice.code" class="notice-row">
            <span :class="['severity', `severity-${notice.severity}`]">{{ severityLabel(notice.severity) }}</span>
            <div><strong>{{ notice.code }}</strong><p>{{ notice.message }}</p><small>下一步：{{ notice.operatorAction }}</small></div>
          </div>
        </template>
        <div v-else class="empty-state">暂无数据</div>
      </article>
      <article class="panel">
        <h3>外部数据依赖</h3>
        <template v-if="operations?.externalData.length">
          <div v-for="source in operations.externalData" :key="source.sourceId" class="notice-row">
            <span class="source-status">{{ externalStatusLabel(source.status) }}</span>
            <div><strong>{{ source.sourceId === 'feedback' ? '反馈数据' : '效率摘要' }}</strong><p>{{ source.explanation }}</p><small>下一步：{{ source.operatorAction }}</small></div>
          </div>
        </template>
        <div v-else class="empty-state">暂无数据</div>
      </article>
    </section>

    <section class="section-heading"><div><p class="eyebrow">PROMPT</p><h2>Prompt 管理</h2></div><span>第一阶段只读</span></section>
    <section class="panel" data-testid="prompt-readonly-center">
      <div class="summary-grid">
        <div><small>当前版本</small><strong>{{ displayText(snapshot?.prompt.promptVersion) }}</strong></div>
        <div><small>更新时间</small><strong>{{ displayDate(snapshot?.prompt.updatedAt) }}</strong></div>
        <div><small>来源</small><strong>{{ displayText(snapshot?.prompt.sourceType) }}</strong></div>
        <div><small>效果说明</small><strong>{{ displayText(snapshot?.prompt.safePreview) }}</strong></div>
      </div>
      <ul v-if="snapshot?.prompt.answerStyleRules.length" class="prompt-rules"><li v-for="rule in snapshot.prompt.answerStyleRules" :key="rule">{{ rule }}</li></ul>
      <div v-else class="empty-state">暂无数据</div>
      <el-alert title="Prompt 仅可查看" description="本页面没有编辑、发布或自动修改 Prompt 的能力；同样不会发布知识、更新模型或训练模型。" type="info" :closable="false" show-icon />
    </section>

    <details class="data-source-details">
      <summary>数据来源与展示边界</summary>
      <ul>
        <li><code>GET /api/admin/ai/control-center</code>：能力盘点、只读 Prompt 与反馈分析状态。</li>
        <li><code>GET /api/admin/ai/operations/overview</code>：模型、知识、回答量、Badcase 空态、提示和外部数据状态。</li>
        <li><code>GET /api/admin/ai/quality-baseline/latest</code>：保存的 <code>live_c_api</code> 评测及安全归因摘要。</li>
      </ul>
      <p>页面不调用 qwen、不读取客户原文、不写回 C，也不使用本地替代数据。</p>
    </details>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { aiControlCenterClient } from '@/api/aiControlCenterClient'
import { toRagClientError } from '@/api/errorMapper'
import type {
  AiBadcaseCategory,
  AiControlCenterSnapshot,
  AiControlCenterStatus,
  AiOperationsOverviewSnapshot,
  AiQualityBaselineSnapshot,
  AiQualityDiagnosisCategory
} from '@/api/aiControlCenterTypes'

const snapshot = ref<AiControlCenterSnapshot | null>(null)
const operations = ref<AiOperationsOverviewSnapshot | null>(null)
const quality = ref<AiQualityBaselineSnapshot | null>(null)
const loading = ref(false)
const controlError = ref('')
const operationsError = ref('')
const qualityError = ref('')
let activeController: AbortController | null = null

const badcaseCategories: AiBadcaseCategory[] = ['FACT_ERROR', 'MISSING_INFO', 'STYLE_ISSUE', 'RISK_ISSUE']

const modelStatusLabel = computed(() => {
  if (!operations.value) return '暂无数据'
  if (operations.value.modelStatus.status === 'NOT_CONFIGURED') return '未配置'
  return operations.value.modelStatus.serviceReady ? '已配置' : '待就绪'
})
const modelDescriptor = computed(() => {
  const model = operations.value?.modelStatus
  if (!model) return '暂无数据'
  return [model.provider, model.modelVersion].filter(Boolean).join(' · ') || '暂无数据'
})

const displayText = (value: string | null | undefined) => value || '暂无数据'
const displayNumber = (value: number | null | undefined) => value === null || value === undefined ? '暂无数据' : new Intl.NumberFormat('zh-CN').format(value)
const displayRate = (value: number | null | undefined) => value === null || value === undefined ? '暂无数据' : `${value.toFixed(1)}%`
const displayDate = (value: string | null | undefined) => {
  if (!value) return '暂无数据'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
const metricScopeLabel = (scope: string | undefined) => scope === 'since_start' ? '当前进程启动以来' : scope || '暂无数据'
const controlStatusLabel = (status: AiControlCenterStatus | 'NOT_AVAILABLE') => ({ RUNNING: '运行中', PAUSED: '已暂停', ERROR: '异常', PLANNED: '规划中', CONFIGURED: '已配置', NOT_CONFIGURED: '未配置', AVAILABLE: '可用', NOT_AVAILABLE: '暂无数据', MANUAL_ONLY: '人工显式运行' }[status])
const dataStatusLabel = (status: 'AVAILABLE' | 'NOT_AVAILABLE') => status === 'AVAILABLE' ? '可读' : '暂无数据'
const operatorModeLabel = (mode: 'READ_ONLY' | 'EXPLICIT_MANUAL') => mode === 'READ_ONLY' ? '只读' : '人工显式运行'
const severityLabel = (severity: 'INFO' | 'WARNING' | 'ERROR') => ({ INFO: '提示', WARNING: '注意', ERROR: '异常' }[severity])
const externalStatusLabel = (status: string) => ({ AVAILABLE: '可用', NOT_AVAILABLE: '暂无数据', NOT_CONFIGURED: '未配置', NOT_REGISTERED: '未登记' }[status] || status)
const badcaseLabel = (category: AiBadcaseCategory) => ({ FACT_ERROR: '事实问题', MISSING_INFO: '信息缺失', STYLE_ISSUE: '表达问题', RISK_ISSUE: '风险问题' }[category])
const diagnosisLabel = (category: AiQualityDiagnosisCategory) => ({ KNOWLEDGE_PROBLEM: '知识问题', RETRIEVAL_PROBLEM: '检索问题', PROMPT_OR_MODEL_PROBLEM: 'Prompt / 模型问题', DATA_PROBLEM: '数据问题', RULE_DECISION_PROBLEM: '规则决策问题' }[category])
const checkLabel = (check: string) => ({ action: '动作', source_ids: '来源标识', key_facts: '关键事实', forbidden_claims: '禁用声明', required_fields: '必填字段', risk_level: '风险等级', scope: '范围隔离' }[check] || check)
const badcaseCount = (category: AiBadcaseCategory) => operations.value?.badcase.categories.find((item) => item.category === category)?.count

const resolveResult = <T>(result: PromiseSettledResult<T>, setValue: (value: T) => void, setError: (value: string) => void) => {
  if (result.status === 'fulfilled') setValue(result.value)
  else setError(toRagClientError(result.reason).message)
}

const load = async () => {
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  snapshot.value = null
  operations.value = null
  quality.value = null
  controlError.value = ''
  operationsError.value = ''
  qualityError.value = ''
  try {
    const results = await Promise.allSettled([
      aiControlCenterClient.getControlCenter(controller.signal),
      aiControlCenterClient.getOperationsOverview(controller.signal),
      aiControlCenterClient.getQualityBaseline(controller.signal)
    ])
    if (!controller.signal.aborted) {
      resolveResult(results[0], (value) => { snapshot.value = value }, (value) => { controlError.value = value })
      resolveResult(results[1], (value) => { operations.value = value }, (value) => { operationsError.value = value })
      resolveResult(results[2], (value) => { quality.value = value }, (value) => { qualityError.value = value })
    }
  } finally {
    if (activeController === controller) loading.value = false
  }
}

onMounted(() => { void load() })
onBeforeUnmount(() => activeController?.abort())
</script>

<style scoped>
.ai-control-center { width: min(1320px, 100%); margin: 0 auto; color: #172033; }
.hero { display: flex; justify-content: space-between; gap: 24px; padding: 28px; border: 1px solid #ccddef; border-radius: 20px; background: radial-gradient(circle at 0 0, rgb(93 133 244 / 22%), transparent 29rem), #fff; box-shadow: 0 12px 30px rgb(24 58 118 / 7%); }
.hero h1, h2, h3, p { margin-top: 0; } .hero h1 { margin-bottom: 9px; font-size: clamp(26px, 3vw, 38px); } .hero p:not(.eyebrow) { max-width: 800px; margin-bottom: 0; color: #607089; line-height: 1.65; }
.eyebrow { margin: 0 0 6px; color: #3065cd; font-size: 11px; font-weight: 800; letter-spacing: .12em; }.hero-actions { display: flex; align-items: flex-start; gap: 9px; }.hero button { min-height: 38px; padding: 8px 13px; border: 1px solid #2f63cf; border-radius: 9px; background: #2f63cf; color: #fff; font-weight: 700; cursor: pointer; }.hero button:disabled { cursor: wait; opacity: .72; }.readonly-badge { padding: 5px 9px; border-radius: 999px; background: #e9f0ff; color: #2e5bb8; font-size: 12px; font-weight: 800; }
.workspace-meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 13px 0; color: #617088; font-size: 12px; }.workspace-meta span { padding: 6px 9px; border-radius: 999px; background: #f2f6fb; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 14px; margin-top: 29px; margin-bottom: 12px; }.section-heading h2 { margin-bottom: 0; font-size: 21px; }.section-heading > span { color: #748198; font-size: 12px; text-align: right; }.section-error { margin: -5px 0 12px; padding: 9px 12px; border: 1px solid #f0c9c5; border-radius: 9px; background: #fff7f5; color: #a03b34; font-size: 12px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 13px; }.metric-card, .panel, .capability-card { border: 1px solid #d9e4f0; border-radius: 15px; background: #fff; box-shadow: 0 7px 18px rgb(31 61 109 / 4%); }.metric-card { display: grid; min-height: 170px; gap: 6px; padding: 18px; }.metric-card small, .panel small { color: #728099; font-size: 12px; }.metric-card strong { color: #56677d; font-size: 22px; }.metric-card .positive { color: #19734d; }.metric-card .negative { color: #af3d36; }.metric-card span, .metric-card p { margin: 0; color: #728099; font-size: 12px; line-height: 1.45; }.metric-card p { align-self: end; }
.capability-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 13px; }.capability-card { display: grid; gap: 10px; min-height: 175px; padding: 17px; }.card-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }.card-title h3 { margin: 0; font-size: 15px; }.capability-card p { margin: 0; color: #66768c; font-size: 12px; line-height: 1.55; }.capability-meta { display: grid; gap: 5px; margin-top: auto; color: #718096; font-size: 11px; }.status-pill { flex: 0 0 auto; padding: 4px 8px; border-radius: 999px; background: #eef2f7; color: #57697f; font-size: 11px; font-weight: 800; }.status-RUNNING { background: #dff6e9; color: #16724b; }.status-ERROR { background: #ffe6e4; color: #a43a32; }.status-PAUSED, .status-PLANNED { background: #fff2ce; color: #805c11; }
.panel { padding: 20px; }.panel h3 { margin-bottom: 14px; font-size: 16px; }.panel-intro { margin-bottom: 15px; color: #64738a; font-size: 13px; line-height: 1.55; }.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }.summary-grid > div { display: grid; min-width: 0; gap: 5px; padding: 13px; border-radius: 11px; background: #f6f9fd; }.summary-grid strong { color: #263b59; font-size: 15px; overflow-wrap: anywhere; }.summary-grid span { color: #728099; font-size: 12px; line-height: 1.45; }.check-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 9px; margin-top: 12px; }.check-grid div { display: grid; gap: 5px; padding: 11px; border: 1px solid #e0e7f0; border-radius: 10px; }.check-grid strong { font-size: 15px; }
.technical-details, .data-source-details { margin-top: 14px; padding: 11px 13px; border: 1px solid #e0e7f0; border-radius: 10px; background: #fbfcfe; color: #617088; font-size: 12px; line-height: 1.55; }.technical-details summary, .data-source-details summary { color: #395985; font-weight: 800; cursor: pointer; }.technical-details p { margin: 8px 0 0; }.case-list { display: grid; gap: 5px; margin: 10px 0; padding-left: 17px; }.case-list code, .data-source-details code { color: #315fc0; font-family: Consolas, monospace; }
.analysis-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; }.finding-row, .recommendation-row, .notice-row { padding: 12px 0; border-top: 1px solid #e6edf5; }.finding-row:first-of-type, .recommendation-row:first-of-type, .notice-row:first-of-type { border-top: 0; padding-top: 0; }.finding-row > div, .recommendation-row > div { display: flex; align-items: center; gap: 9px; }.finding-row p, .recommendation-row p, .notice-row p { margin: 8px 0 5px; color: #607089; font-size: 13px; line-height: 1.5; }.finding-row small, .recommendation-row small, .notice-row small { display: block; line-height: 1.5; }.category-label { padding: 3px 7px; border-radius: 999px; background: #edf3ff; color: #355ea9; font-size: 11px; font-weight: 800; }.priority { padding: 3px 7px; border-radius: 999px; font-size: 11px; font-weight: 800; }.priority-P0 { background: #ffe5e2; color: #a33730; }.priority-P1 { background: #fff1cf; color: #805c11; }.priority-P2 { background: #e9f0ff; color: #315cae; }
.badcase-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 11px; }.badcase-grid article { display: grid; gap: 5px; padding: 14px; border: 1px solid #e1e7f0; border-radius: 11px; background: #fbfcfe; }.badcase-grid strong { color: #7c899b; font-size: 15px; }.badcase-grid span { color: #596a81; font-size: 12px; }.notice-row { display: flex; gap: 11px; }.notice-row > div { min-width: 0; }.severity, .source-status { flex: 0 0 auto; align-self: flex-start; padding: 4px 7px; border-radius: 999px; background: #eef2f7; color: #57697f; font-size: 11px; font-weight: 800; }.severity-WARNING { background: #fff1cf; color: #805c11; }.severity-ERROR { background: #ffe5e2; color: #a33730; }.prompt-rules { display: grid; gap: 6px; margin: 15px 0; padding: 13px 13px 13px 32px; border-radius: 11px; background: #fbfcfe; color: #5d6e84; font-size: 12px; line-height: 1.5; }.panel :deep(.el-alert) { margin-top: 15px; }.empty-state { padding: 20px; border: 1px dashed #cdd8e6; border-radius: 10px; color: #7c899b; text-align: center; }.data-source-details { margin-top: 22px; }.data-source-details ul { display: grid; gap: 5px; margin: 10px 0 0; padding-left: 19px; }
@media (max-width: 1120px) { .metric-grid, .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.capability-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }.check-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (max-width: 720px) { .hero, .section-heading { align-items: flex-start; flex-direction: column; }.hero-actions { width: 100%; justify-content: space-between; }.section-heading > span { text-align: left; }.metric-grid, .capability-grid, .summary-grid, .check-grid, .analysis-grid, .badcase-grid { grid-template-columns: 1fr; } }
</style>
