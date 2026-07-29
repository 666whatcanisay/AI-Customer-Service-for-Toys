<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  createKnowledgeOptimizationTask,
  listAiProblems,
  updateAiProblemStatus,
  updateKnowledgeOptimizationTaskStatus,
  verifyKnowledgeOptimizationTask,
  type AiProblem,
  type AiProblemType,
  type KnowledgeOptimizationTaskStatus,
  type KnowledgeVerificationResult,
} from '../api/client'
import { displayStatus } from '../presentation'

const problems = ref<AiProblem[]>([])
const total = ref<number | null>(null)
const selected = ref<AiProblem | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const operator = ref('运营测试员')
const selectedType = ref<AiProblemType>('UNCLASSIFIED')
const statusNote = ref('')
const missingTopic = ref('')
const verificationNote = ref('')

const issueTypes: AiProblemType[] = [
  'KNOWLEDGE_MISSING',
  'PRODUCT_INFO_ERROR',
  'SKU_ERROR',
  'INCOMPLETE_ANSWER',
  'RISK_ISSUE',
  'EXPRESSION_ISSUE',
]

const knowledgeTaskStatusLabels: Record<KnowledgeOptimizationTaskStatus, string> = {
  PENDING: '待补充',
  IN_PROGRESS: '处理中',
  COMPLETED: '已补充',
  VERIFIED: '已验证',
}

function displayKnowledgeTaskStatus(status: KnowledgeOptimizationTaskStatus): string {
  return knowledgeTaskStatusLabels[status]
}

async function load(preferredProblemId?: string): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await listAiProblems()
    problems.value = response.items
    total.value = response.total
    const problemId = preferredProblemId ?? selected.value?.problem_id
    selected.value = problemId
      ? response.items.find((item) => item.problem_id === problemId) ?? null
      : null
    if (selected.value) selectedType.value = selected.value.issue_type
  } catch (reason: unknown) {
    problems.value = []
    total.value = null
    selected.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function choose(problem: AiProblem): void {
  selected.value = problem
  selectedType.value = problem.issue_type
  statusNote.value = ''
  missingTopic.value = ''
  verificationNote.value = ''
  error.value = ''
  success.value = ''
}

async function perform(
  action: () => Promise<unknown>,
  message: string,
): Promise<void> {
  if (!selected.value || saving.value) return
  const problemId = selected.value.problem_id
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    await action()
    await load(problemId)
    success.value = message
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function confirmProblem(): Promise<void> {
  if (!selected.value) return
  if (selectedType.value === 'UNCLASSIFIED') {
    error.value = '确认前请选择问题类型。'
    return
  }
  await perform(
    () => updateAiProblemStatus(selected.value!.problem_id, {
      status: 'CONFIRMED',
      issue_type: selectedType.value,
      operator: operator.value.trim(),
      note: statusNote.value.trim() || null,
    }),
    '问题已确认，可以创建知识优化任务。',
  )
}

async function createTask(): Promise<void> {
  if (!selected.value) return
  if (!missingTopic.value.trim()) {
    error.value = '请填写需要补充的知识主题。'
    return
  }
  await perform(
    () => createKnowledgeOptimizationTask(selected.value!.problem_id, {
      missing_topic: missingTopic.value.trim(),
      operator: operator.value.trim(),
      note: statusNote.value.trim() || null,
    }),
    '知识优化任务已创建，未自动生成或发布知识。',
  )
}

async function moveTask(status: KnowledgeOptimizationTaskStatus): Promise<void> {
  const task = selected.value?.knowledge_task
  if (!task) return
  await perform(
    () => updateKnowledgeOptimizationTaskStatus(task.task_id, {
      status,
      operator: operator.value.trim(),
      note: statusNote.value.trim() || null,
    }),
    status === 'COMPLETED' ? '已记录知识补充完成，等待重新验证。' : '知识补充已开始。',
  )
}

async function verify(result: KnowledgeVerificationResult): Promise<void> {
  const task = selected.value?.knowledge_task
  if (!task) return
  if (!verificationNote.value.trim()) {
    error.value = '请填写重新提问后的验证结果。'
    return
  }
  await perform(
    () => verifyKnowledgeOptimizationTask(task.task_id, {
      result,
      operator: operator.value.trim(),
      note: verificationNote.value.trim(),
    }),
    result === 'IMPROVED'
      ? '已记录 AI 改善，问题闭环完成。'
      : '已记录仍未改善，任务返回处理中。',
  )
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">客服发现 → 运营补充 → 人工复验</p>
        <h1>AI 问题中心</h1>
        <p>客服“未采用”会立即形成问题。运营只确认、补知识和记录复验，不自动生成知识、不自动发布、不修改 Prompt。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load()">刷新数据</button>
    </div>

    <p class="notice boundary">
      当前保存去标识化摘要；客服身份是试点报告人标识，不是正式登录或 RBAC。知识补充仍须走既有人工审核流程。
    </p>
    <p v-if="loading" class="notice" role="status">正在读取 AI 问题…</p>
    <p v-else-if="error && !selected" class="notice error" role="alert">暂时无法读取 AI 问题。{{ error }}</p>
    <p v-else-if="problems.length === 0" class="notice">
      {{ total === 0 ? '尚无 AI 问题。客服点击“未采用”并保存成功后会出现在这里。' : '当前没有可展示的问题。' }}
    </p>

    <section v-else class="issue-layout">
      <div class="card table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>商品 / SKU</th>
              <th>问题摘要</th>
              <th>AI 回答摘要</th>
              <th>问题类型</th>
              <th>次数</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="problem in problems" :key="problem.problem_id">
              <td>
                <button class="link-button" type="button" @click="choose(problem)">
                  {{ problem.product_name }}
                </button>
                <small>{{ problem.sku_name || '全部 SKU' }}</small>
              </td>
              <td>{{ problem.question_summary }}</td>
              <td>{{ problem.ai_answer_summary }}</td>
              <td><span class="badge">{{ displayStatus(problem.issue_type) }}</span></td>
              <td>{{ problem.occurrence_count }}</td>
              <td><span class="badge">{{ displayStatus(problem.status) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <aside v-if="selected" class="card detail" data-testid="ai-issue-detail">
        <header>
          <div>
            <small>{{ selected.store_name }}</small>
            <h2>{{ selected.product_name }} · {{ selected.sku_name || '全部 SKU' }}</h2>
          </div>
          <span class="badge">{{ displayStatus(selected.status) }}</span>
        </header>
        <dl class="summary">
          <div><dt>问题摘要</dt><dd>{{ selected.question_summary }}</dd></div>
          <div><dt>AI 回答摘要</dt><dd>{{ selected.ai_answer_summary }}</dd></div>
          <div><dt>出现次数</dt><dd>{{ selected.occurrence_count }} 次</dd></div>
        </dl>

        <label>
          <span>当前操作人</span>
          <input v-model="operator" maxlength="128">
        </label>
        <label>
          <span>处理说明（可选）</span>
          <textarea v-model="statusNote" maxlength="1000" rows="2" />
        </label>

        <section v-if="selected.status === 'NEW'" class="workflow-card">
          <h3>1. 确认问题</h3>
          <label>
            <span>问题类型</span>
            <select v-model="selectedType" data-testid="ai-issue-type">
              <option value="UNCLASSIFIED" disabled>请选择</option>
              <option v-for="type in issueTypes" :key="type" :value="type">
                {{ displayStatus(type) }}
              </option>
            </select>
          </label>
          <button class="button" type="button" :disabled="saving" data-testid="confirm-ai-issue" @click="confirmProblem">
            确认问题
          </button>
        </section>

        <section v-else-if="selected.status === 'CONFIRMED' && !selected.knowledge_task" class="workflow-card">
          <h3>2. 生成知识优化任务</h3>
          <label>
            <span>缺失主题</span>
            <input v-model="missingTopic" maxlength="256" data-testid="missing-topic">
          </label>
          <button class="button" type="button" :disabled="saving" data-testid="create-knowledge-task" @click="createTask">
            生成任务
          </button>
          <p>只生成待办，不生成知识内容，也不发布到 RAG。</p>
        </section>

        <section v-if="selected.knowledge_task" class="workflow-card task-card">
          <h3>知识优化任务</h3>
          <dl>
            <div><dt>缺失主题</dt><dd>{{ selected.knowledge_task.missing_topic }}</dd></div>
            <div><dt>任务状态</dt><dd>{{ displayKnowledgeTaskStatus(selected.knowledge_task.status) }}</dd></div>
            <div v-if="selected.knowledge_task.verification_result">
              <dt>最近复验</dt>
              <dd>{{ displayStatus(selected.knowledge_task.verification_result) }} · {{ selected.knowledge_task.verification_note }}</dd>
            </div>
          </dl>
          <button
            v-if="selected.knowledge_task.status === 'PENDING'"
            class="button"
            type="button"
            :disabled="saving"
            data-testid="start-knowledge-task"
            @click="moveTask('IN_PROGRESS')"
          >
            开始补充
          </button>
          <button
            v-if="selected.knowledge_task.status === 'IN_PROGRESS'"
            class="button"
            type="button"
            :disabled="saving"
            data-testid="complete-knowledge-task"
            @click="moveTask('COMPLETED')"
          >
            标记已补充
          </button>
          <div v-if="selected.knowledge_task.status === 'COMPLETED'" class="verification">
            <label>
              <span>重新提问后的验证记录</span>
              <textarea v-model="verificationNote" maxlength="1000" rows="3" data-testid="verification-note" />
            </label>
            <div>
              <button class="button secondary" type="button" :disabled="saving" @click="verify('NOT_IMPROVED')">仍未改善</button>
              <button class="button" type="button" :disabled="saving" data-testid="verify-improved" @click="verify('IMPROVED')">确认 AI 已改善</button>
            </div>
          </div>
          <p v-if="selected.knowledge_task.status === 'VERIFIED'" class="closed-loop">
            已完成：客服问题 → AI 问题 → 知识补充 → AI 改善。
          </p>
        </section>

        <p v-if="error" class="notice error" role="alert">{{ error }}</p>
        <p v-if="success" class="notice success" role="status">{{ success }}</p>
      </aside>
      <aside v-else class="card detail"><h2>处理 AI 问题</h2><p>从列表选择一条问题，查看摘要并推进人工闭环。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.boundary { margin-bottom: 20px; color: #75570a; background: #fff8df; }
.issue-layout { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(340px, .9fr); gap: 20px; }
.table-wrap { overflow-x: auto; }
.data-table td { max-width: 260px; line-height: 1.5; overflow-wrap: anywhere; }
.data-table td:first-child small { display: block; margin-top: 4px; color: #64748b; }
.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; font-weight: 700; text-align: left; cursor: pointer; }
.detail { display: grid; align-content: start; gap: 14px; }
.detail header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.detail h2, .detail h3, .detail p { margin: 0; }
.detail header small { color: #64748b; }
.detail label { display: grid; gap: 6px; color: #475569; font-size: 13px; font-weight: 700; }
.detail input, .detail textarea, .detail select { width: 100%; padding: 9px 10px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; color: #172033; font: inherit; }
.summary, .task-card dl { display: grid; gap: 10px; margin: 0; }
.summary div, .task-card dl div { display: grid; gap: 3px; }
.summary dt, .task-card dt { color: #64748b; font-size: 12px; }
.summary dd, .task-card dd { margin: 0; overflow-wrap: anywhere; line-height: 1.55; }
.workflow-card { display: grid; gap: 12px; padding: 14px; border: 1px solid #dce5f1; border-radius: 10px; background: #f9fbfe; }
.workflow-card > p { color: #64748b; font-size: 12px; line-height: 1.5; }
.verification { display: grid; gap: 10px; }
.verification > div { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.closed-loop { padding: 10px; border-radius: 8px; color: #176744 !important; background: #edf9f3; font-weight: 700; }
@media (max-width: 980px) { .issue-layout { grid-template-columns: 1fr; } }
</style>
