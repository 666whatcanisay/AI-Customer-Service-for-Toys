<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { apiErrorMessage, listKnowledgeQualityAssessments, type KnowledgeQualityAssessment } from '../api/client'
import { displayStatus } from '../presentation'

const assessments = ref<KnowledgeQualityAssessment[]>([])
const selected = ref<KnowledgeQualityAssessment | null>(null)
const loading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await listKnowledgeQualityAssessments()
    assessments.value = result.items
    if (selected.value) selected.value = result.items.find((item) => item.assessment_id === selected.value?.assessment_id) ?? null
  } catch (reason: unknown) {
    assessments.value = []
    selected.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>资料质量与补充</h1><p>查看已审核资料的 AI 质量分析。这里是运营修正依据，不会自动修改知识、Prompt、模型或客服回复。</p></div><button class="button secondary" type="button" @click="load">刷新</button></div>
    <p class="notice boundary">如果发现待补充项，请回到“资料上传与审核”，使用原资料编号重新上传修正版本；旧版本和分析证据会保持可追溯。</p>
    <p v-if="loading" class="notice" role="status">正在读取资料质量分析…</p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-else-if="assessments.length === 0" class="notice">暂无完成的资料质量分析。请先上传资料、人工审核，再由 AI 发起真实分析并回写结果。</p>
    <section v-else class="pool-grid"><div class="card table-wrap"><table class="data-table"><thead><tr><th>资料版本</th><th>质量摘要</th><th>待补充项</th><th>状态</th></tr></thead><tbody><tr v-for="item in assessments" :key="item.assessment_id"><td><button class="link-button" type="button" @click="selected = item">{{ item.material_id }}</button><small>版本 {{ item.revision }}</small></td><td>{{ item.summary }}</td><td>{{ item.gaps.filter((gap) => gap.status === 'OPEN').length }} 项</td><td><span class="badge">{{ displayStatus(item.overall_status) }}</span></td></tr></tbody></table></div><aside v-if="selected" class="card detail"><h2>运营修正建议</h2><p>{{ selected.summary }}</p><div v-if="selected.gaps.length" class="gap-list"><article v-for="gap in selected.gaps" :key="gap.gap_id"><div><span class="badge">{{ displayStatus(gap.severity) }}</span> <span class="badge">{{ displayStatus(gap.status) }}</span></div><h3>{{ gap.title }}</h3><p>{{ gap.description }}</p><strong>建议操作</strong><p>{{ gap.recommended_action }}</p></article></div><p v-else class="notice">本次分析没有返回结构化待补充项。仍请按商品事实与人工审核流程核对。</p><details class="technical-details"><summary>技术详情</summary><dl><div><dt>分析任务</dt><dd>{{ selected.analysis_run_id }}</dd></div><div><dt>模型 / 提示词版本</dt><dd>{{ selected.model_version }} / {{ selected.prompt_version }}</dd></div><div><dt>内容校验</dt><dd>{{ selected.content_hash }}</dd></div></dl></details></aside><aside v-else class="card detail"><h2>查看修正建议</h2><p>选择一条资料分析，查看面向运营的缺口与下一步操作。</p></aside></section>
  </main>
</template>

<style scoped>
.boundary { margin-bottom: 20px; color: #75570a; background: #fff8df; line-height: 1.55; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(320px, .9fr); gap: 20px; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }small { display: block; margin-top: 4px; color: #64748b; }.detail { display: grid; align-content: start; gap: 13px; }.detail h2, .detail h3, .detail p { margin: 0; }.detail h2, .detail h3 { color: #172554; }.detail p { line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }.gap-list { display: grid; gap: 12px; }.gap-list article { padding: 13px; border: 1px solid #dce5f1; border-radius: 10px; background: #f9fbfe; }.gap-list h3 { margin: 9px 0 5px; font-size: 16px; }.technical-details { border-top: 1px solid #e6edf5; color: #526279; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details dl { display: grid; gap: 8px; }.technical-details dt { color: #64748b; }.technical-details dd { margin: 3px 0 0; overflow-wrap: anywhere; }@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
