<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listAiModules, type AiModule } from '../api/client'

const modules = ref<AiModule[]>([])
const state = ref<'loading' | 'available' | 'unavailable'>('loading')

async function load(): Promise<void> {
  state.value = 'loading'
  try {
    modules.value = await listAiModules()
    state.value = 'available'
  } catch {
    modules.value = []
    state.value = 'unavailable'
  }
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>AI 能力中心</h1><p>只读探测 A 线已声明接口；不提供 Prompt 编辑、发布或回滚。</p></div><button class="button secondary" @click="load">重试</button></div>
    <p v-if="state === 'loading'" class="notice" role="status">正在连接 AI 服务…</p>
    <section v-else-if="state === 'unavailable'" class="card unavailable" role="alert"><h2>AI 服务不可用或接口尚未合并</h2><p>当前 C 线页面没有本地 Mock 回退；其余运营页面仍可正常使用。</p><p>待 A 线提供并合并版本化的模块详情与在线测试契约后，再启用真实调用。</p></section>
    <template v-else><p v-if="modules.length === 0" class="notice">AI 服务已响应，但未返回模块。</p><section v-else class="module-grid"><article v-for="module in modules" :key="module.id" class="card"><h2>{{ module.name }}</h2><p><span class="badge">{{ module.status }}</span></p><p>{{ module.description || '未提供描述。' }}</p><details v-if="module.promptMetadata"><summary>Prompt 元数据</summary><pre>{{ JSON.stringify(module.promptMetadata, null, 2) }}</pre></details><details><summary>最近评测（{{ module.recentEvaluations.length }}）</summary><pre>{{ JSON.stringify(module.recentEvaluations, null, 2) }}</pre></details></article></section>
      <section class="card online-test"><h2>在线测试</h2><p>当前基线尚未提供 A 线的版本化在线测试请求/响应契约，测试不会发送请求或展示 Mock 结果。</p><label>问题<textarea disabled placeholder="等待 A 线测试契约" /></label><label>上下文<textarea disabled /></label><div class="result-grid"><span>answer：—</span><span>action：—</span><span>risk：—</span><span>sources：—</span><span>latency：—</span></div><button class="button" disabled>运行在线测试</button><details><summary>技术详情</summary><p>等待受版本控制的 A 线接口定义。</p></details></section>
    </template>
  </main>
</template>

<style scoped>
.unavailable { border-left: 5px solid #c77a16; }
.module-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 20px; }
pre { overflow: auto; padding: 10px; background: #f4f6f9; font-size: 12px; }
.online-test { display: grid; gap: 12px; margin-top: 20px; }
label { display: grid; gap: 5px; }
textarea { min-height: 70px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; }
.result-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; color: #526279; }
</style>
