<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getTrialActor,
  getTrialAuditReason,
  getTrialGovernance,
  listTrialAuditEvents,
  setTrialActor,
  setTrialAuditReason,
  type TrialActorId,
  type TrialAuditReason,
  type TrialAuditEvent,
  type TrialGovernanceStatus,
} from '../api/client'
import { displayAuditAction, displayAuditReason, displayAuditResource, displayCapability, displayStatus } from '../presentation'

const actor = ref<TrialActorId>(getTrialActor())
const reason = ref<TrialAuditReason>(getTrialAuditReason())
const governance = ref<TrialGovernanceStatus | null>(null)
const auditEvents = ref<TrialAuditEvent[]>([])
const loading = ref(true)
const error = ref('')
const auditError = ref('')

const roleLabel = computed(() => ({ ADMIN: '管理员', OPERATOR: '运营', SUPPORT: '客服' })[governance.value?.role || 'OPERATOR'])
const canReadAudit = computed(() => governance.value?.role === 'ADMIN')

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  auditError.value = ''
  auditEvents.value = []
  try {
    governance.value = await getTrialGovernance()
    if (governance.value.role === 'ADMIN') {
      try { auditEvents.value = (await listTrialAuditEvents()).items } catch (reasonValue: unknown) { auditError.value = apiErrorMessage(reasonValue) }
    }
  } catch (reasonValue: unknown) {
    governance.value = null
    error.value = apiErrorMessage(reasonValue)
  } finally { loading.value = false }
}

async function applyContext(): Promise<void> {
  setTrialActor(actor.value)
  setTrialAuditReason(reason.value)
  await load()
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>试运行治理</h1><p>用于验证最小内部角色边界、审计基础和数据处理边界；不是正式登录、身份认证或生产权限体系。</p></div><button class="button secondary" type="button" @click="load">刷新状态</button></div>

    <p class="notice warning">当前仅允许测试数据。审计不记录客户问题、AI 回答、客服回复、表格单元格、文件路径或自由文本原因。</p>

    <section class="card context-card"><div><h2>试运行上下文</h2><p>服务端将固定身份映射为角色；浏览器选择用于验证边界，不能作为正式身份凭据。</p></div><form @submit.prevent="applyContext"><label>身份<select v-model="actor"><option value="trial-admin">管理员</option><option value="trial-operator">运营</option><option value="trial-support">客服（只读）</option></select></label><label>操作目的<select v-model="reason"><option value="DAILY_OPERATIONS">日常运营</option><option value="CASE_REVIEW">案例审核</option><option value="KNOWLEDGE_MAINTENANCE">知识维护</option><option value="GOVERNANCE_REVIEW">治理检查</option></select></label><button class="button" type="submit">应用试运行上下文</button></form></section>

    <p v-if="loading" class="notice" role="status">正在读取试运行治理状态…</p><p v-else-if="error" class="notice error" role="alert"><strong>数据加载失败</strong><br />原因：{{ error }}<br />建议下一步：检查服务状态后重试。</p>
    <template v-else-if="governance">
      <section class="summary-grid"><article><span>当前角色</span><strong>{{ roleLabel }}</strong><small>{{ governance.actor_id }}</small></article><article><span>审计基础</span><strong>{{ governance.audit_foundation_enabled ? '已启用' : '待启用' }}</strong><small>仅记录受控元数据</small></article><article><span>自动脱敏</span><strong>{{ governance.automatic_redaction_enabled ? '已启用' : '未启用' }}</strong><small>当前仅有提交前提醒</small></article><article><span>留存策略</span><strong>{{ governance.retention_policy_configured ? '已配置' : '未配置' }}</strong><small>正式策略待实施</small></article></section>

      <section class="card capability-card"><h2>当前可用范围</h2><p>能力由服务端固定角色矩阵返回。客服身份只能读取安全运营概览，无法查看案例或 AI 分析原文，也不能发起导入、审核或确认。</p><ul><li v-for="capability in governance.capabilities" :key="capability">{{ displayCapability(capability) }}</li></ul></section>

      <section class="card redaction-card"><h2>脱敏与留存边界</h2><div class="boundary-grid"><div><h3>当前能力</h3><ul><li>案例与反馈保留原始提交内容；页面与接口不宣称自动脱敏。</li><li>当前仅有提交前提醒，不替代脱敏处理。</li><li>审计事件不写入原文、身份之外的自由文本或来源文件内容。</li></ul></div><div><h3>正式上线前</h3><ul><li>接入经过验证的身份认证、服务端授权和敏感查看理由。</li><li>验证自动脱敏、密钥管理、留存/删除与访问审计闭环。</li><li>完成生产数据与安全评估后再作能力声明。</li></ul></div></div></section>

      <section class="card audit-card"><div class="section-heading"><div><h2>审计基础</h2><p>仅管理员可读取审计元数据；运营和客服角色不会看到该列表。</p></div></div><p v-if="!canReadAudit" class="notice">只读边界：当前角色没有读取审计记录的权限。</p><p v-else-if="auditError" class="notice error" role="alert">暂时无法读取审计记录。{{ auditError }}</p><p v-else-if="auditEvents.length === 0" class="notice">样本不足：尚无已记录的试运行操作。</p><div v-else class="table-wrap"><table class="data-table"><thead><tr><th>时间</th><th>身份</th><th>动作</th><th>资源</th><th>结果</th><th>目的</th></tr></thead><tbody><tr v-for="event in auditEvents" :key="event.id"><td>{{ formatTime(event.occurred_at) }}</td><td>{{ displayStatus(event.actor_role) }}<br /><small>{{ event.actor_id }}</small></td><td>{{ displayAuditAction(event.action) }}</td><td>{{ displayAuditResource(event.resource_type) }} / {{ event.resource_id }}</td><td><span class="badge">{{ displayStatus(event.outcome) }}</span></td><td>{{ displayAuditReason(event.reason_code) }}</td></tr></tbody></table></div></section>
    </template>
  </main>
</template>

<style scoped>
.warning { margin-bottom: 18px; color: #76580e; background: #fff8df; }.context-card { display: grid; grid-template-columns: 1fr auto; gap: 22px; margin-bottom: 18px; }.context-card h2, .capability-card h2, .redaction-card h2, .audit-card h2 { margin: 0 0 5px; color: #172554; font-size: 18px; }.context-card p, .capability-card p, .audit-card p { margin: 0; color: #64748b; line-height: 1.5; }.context-card form { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; }.context-card label { display: grid; gap: 5px; color: #526279; font-size: 12px; }.context-card select { min-height: 38px; min-width: 150px; border: 1px solid #cbd7e6; border-radius: 7px; padding: 7px; }.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }.summary-grid article { padding: 16px; border: 1px solid #dfe7f2; border-radius: 12px; background: #fff; }.summary-grid span, .summary-grid small { display: block; color: #64748b; font-size: 12px; }.summary-grid strong { display: block; margin: 6px 0; color: #172554; font-size: 20px; }.capability-card, .redaction-card, .audit-card { margin-bottom: 18px; }.capability-card ul { display: flex; flex-wrap: wrap; gap: 8px; padding: 0; list-style: none; }.capability-card li { padding: 5px 8px; border-radius: 999px; color: #365b8d; background: #edf4ff; font-size: 13px; }.boundary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }.boundary-grid div { padding: 14px; border-radius: 9px; background: #f6f8fc; }.boundary-grid h3 { margin: 0; color: #334155; font-size: 15px; }.boundary-grid ul { margin: 9px 0 0; padding-left: 19px; color: #526279; line-height: 1.6; }.section-heading { display: flex; justify-content: space-between; gap: 15px; }@media (max-width: 850px) { .context-card { grid-template-columns: 1fr; }.summary-grid { grid-template-columns: repeat(2, 1fr); } }@media (max-width: 560px) { .summary-grid, .boundary-grid { grid-template-columns: 1fr; } }
</style>
