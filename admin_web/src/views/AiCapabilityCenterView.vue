<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listAiModules, type AiModule } from '../api/client'
import { displayStatus } from '../presentation'

const modules = ref<AiModule[]>([])
const state = ref<'loading' | 'available' | 'unavailable'>('loading')

async function load(): Promise<void> {
  state.value = 'loading'
  try { modules.value = await listAiModules(); state.value = 'available' } catch { modules.value = []; state.value = 'unavailable' }
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>AI 效果</h1><p>只读观察已声明的 AI 能力服务状态，不提供提示词编辑、发布、回滚或在线试运行操作。</p></div><button class="button secondary" type="button" @click="load">重新检查</button></div>
    <p v-if="state === 'loading'" class="notice" role="status">正在连接 AI 服务…</p>
    <section v-else-if="state === 'unavailable'" class="card unavailable" role="alert"><h2>待启用</h2><p>当前未连接到 AI 服务目录。页面没有本地 Mock 回退，不会伪造服务可用状态。</p></section>
    <template v-else><p v-if="modules.length === 0" class="notice">待启用：AI 服务已响应，但尚未返回可观察模块。请稍后重新检查。</p><section v-else class="module-grid"><article v-for="module in modules" :key="module.id" class="card"><h2>{{ module.name }}</h2><p><span class="badge">{{ displayStatus(module.status) }}</span></p><p>{{ module.description || '未提供业务说明。' }}</p><details><summary>技术信息</summary><p>模块标识：{{ module.id }}</p><pre v-if="module.promptMetadata">{{ JSON.stringify(module.promptMetadata, null, 2) }}</pre><pre v-if="module.recentEvaluations.length">{{ JSON.stringify(module.recentEvaluations, null, 2) }}</pre><p v-if="!module.promptMetadata && !module.recentEvaluations.length">未提供可展示的技术元数据。</p></details></article></section></template>
  </main>
</template>

<style scoped>
.unavailable { border-left: 5px solid #c77a16; }.unavailable h2 { margin-top: 0; color: #172554; }.module-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 20px; }.module-grid h2 { margin: 0; color: #172554; font-size: 18px; }.module-grid details { margin-top: 14px; border-top: 1px solid #e7edf4; padding-top: 11px; color: #526279; font-size: 13px; }.module-grid summary { cursor: pointer; }pre { overflow: auto; padding: 10px; background: #f4f6f9; font-size: 12px; }
</style>
