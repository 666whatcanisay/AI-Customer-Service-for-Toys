<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { getAdminOverview, getHealth, listAiModules } from './api/client'

type ServiceState = 'loading' | 'ready' | 'unavailable'

const platformState = ref<ServiceState>('loading')
const aiState = ref<ServiceState>('loading')
const operationState = ref<ServiceState>('loading')
const technicalOpen = ref(false)
const checkedAt = ref('')
const platformVersion = ref('')

const platformLabel = computed(() => ({ loading: '正在检查', ready: '可用', unavailable: '待连接' })[platformState.value])
const aiLabel = computed(() => ({ loading: '正在检查', ready: '可用', unavailable: '待连接' })[aiState.value])
const operationLabel = computed(() => ({ loading: '正在读取', ready: '数据已连接', unavailable: '待启用' })[operationState.value])

async function loadSystemState(): Promise<void> {
  const [overviewResult, healthResult, aiResult] = await Promise.allSettled([getAdminOverview(), getHealth(), listAiModules()])
  operationState.value = overviewResult.status === 'fulfilled' ? 'ready' : 'unavailable'
  platformState.value = healthResult.status === 'fulfilled' ? 'ready' : 'unavailable'
  aiState.value = aiResult.status === 'fulfilled' ? 'ready' : 'unavailable'
  if (healthResult.status === 'fulfilled') platformVersion.value = healthResult.value.version || ''
  checkedAt.value = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', hour12: false }).format(new Date())
}

onMounted(loadSystemState)
</script>

<template>
  <div class="product-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/overview"><span class="brand-mark">AI</span><span><strong>AI 客服平台</strong><small>运营管理中心 · 试运行</small></span></RouterLink>
      <nav class="side-nav" aria-label="运营管理中心导航">
        <section class="nav-group"><p>首页</p><RouterLink to="/overview">运营总览</RouterLink></section>
        <section class="nav-group"><p>客服运营</p><RouterLink to="/experience-cases">客服经验库</RouterLink><RouterLink to="/ai-feedback-optimization-pool">AI 问题</RouterLink><RouterLink to="/ai-improvement-suggestions">改进建议</RouterLink><RouterLink to="/customer-efficiency">效率分析</RouterLink></section>
        <section class="nav-group"><p>商品知识</p><RouterLink to="/store-center">店铺</RouterLink><RouterLink to="/products">商品与 SKU</RouterLink><RouterLink to="/faqs">FAQ</RouterLink><RouterLink to="/safety-rules">安全规则</RouterLink><RouterLink to="/sources">来源证据</RouterLink><RouterLink to="/conflicts">冲突处理</RouterLink><RouterLink to="/imports">数据导入</RouterLink><RouterLink to="/test-data-packages">测试数据包</RouterLink></section>
        <section class="nav-group"><p>AI 管理</p><RouterLink to="/ai-control-center">AI 控制中心</RouterLink><RouterLink to="/ai-optimization-pool">评测中心</RouterLink><RouterLink to="/ai-capabilities">AI 能力中心</RouterLink><RouterLink to="/ai-improvement-suggestions">AI 优化池</RouterLink></section>
        <section class="nav-group"><p>系统</p><RouterLink to="/system-status">服务状态</RouterLink><RouterLink to="/trial-governance">治理与审计日志</RouterLink></section>
        <section class="nav-group planned-group"><p>规划功能</p><span class="nav-planned">ERP 同步 <em>规划中</em></span><span class="nav-planned">售后助手 <em>规划中</em></span><span class="nav-planned">退款风险 <em>规划中</em></span></section>
      </nav>
    </aside>

    <div class="stage">
      <header class="topbar"><div><p class="eyebrow">AI 客服平台 · 运营管理中心</p><p class="topbar-title">今天的运营状态与待处理事项</p></div><div class="service-chips" aria-label="系统状态"><span class="service-chip"><i :class="platformState"></i>平台服务：{{ platformLabel }}</span><span class="service-chip"><i :class="aiState"></i>AI 服务：{{ aiLabel }}</span><span class="service-chip"><i :class="operationState"></i>运营数据：{{ operationLabel }}</span></div></header>
      <p class="trial-banner">当前展示测试 / 试运行数据，不构成正式运营报表。正式身份认证、权限体系、留存策略和自动脱敏尚未启用；不会自动发布知识、训练模型或执行业务动作。</p>
      <main class="content"><RouterView /></main>
      <footer class="app-footer"><button class="technical-toggle" type="button" @click="technicalOpen = !technicalOpen">{{ technicalOpen ? '收起技术信息' : '展开技术信息' }}</button><div v-if="technicalOpen" class="technical-info"><span>平台版本：{{ platformVersion || '未提供' }}</span><span>状态检查：{{ checkedAt || '尚未完成' }}</span><button type="button" class="inline-button" @click="loadSystemState">重新检查</button></div></footer>
    </div>
  </div>
</template>

<style>
:root { color: #1e293b; background: #f5f7fb; font-family: Inter, "Microsoft YaHei", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }* { box-sizing: border-box; }body { min-width: 320px; margin: 0; background: #f5f7fb; }a { color: inherit; }button, input, select { font: inherit; }
.product-shell { display: grid; min-height: 100vh; grid-template-columns: 256px minmax(0, 1fr); }.sidebar { position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 18px 13px 24px; color: #dbe7ff; background: linear-gradient(180deg, #102547 0%, #0d1e39 100%); }.brand { display: flex; gap: 11px; align-items: center; padding: 7px 10px 18px; color: #fff; text-decoration: none; }.brand-mark { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 9px; color: #102547; background: #7dd3fc; font-weight: 800; letter-spacing: -1px; }.brand strong, .brand small { display: block; }.brand strong { font-size: 17px; }.brand small { margin-top: 2px; color: #9db4da; font-size: 12px; }.side-nav { display: grid; gap: 13px; }.nav-group { display: grid; gap: 2px; }.nav-group p { margin: 0 0 4px; padding: 0 10px; color: #88a4d1; font-size: 11px; font-weight: 800; letter-spacing: .09em; }.nav-group a, .nav-planned { padding: 7px 10px; border-radius: 7px; color: #dbe7ff; font-size: 13px; line-height: 1.35; text-decoration: none; }.nav-group a:hover, .nav-group a.router-link-active { color: #fff; background: #244775; }.planned-group { padding-top: 2px; border-top: 1px solid rgb(157 180 218 / 16%); }.nav-planned { display: flex; justify-content: space-between; color: #7f95b9; cursor: default; }.nav-planned em { color: #6e84a6; font-size: 11px; font-style: normal; }.stage { display: grid; min-width: 0; grid-template-rows: auto auto 1fr auto; }.topbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 76px; padding: 14px clamp(20px, 4vw, 56px); border-bottom: 1px solid #e2e8f0; background: #fff; }.eyebrow { margin: 0 0 3px; color: #64748b; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.topbar-title { margin: 0; color: #0f172a; font-size: 17px; font-weight: 700; }.service-chips { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }.service-chip { display: inline-flex; gap: 6px; align-items: center; padding: 7px 9px; border: 1px solid #dbe4f0; border-radius: 999px; color: #475569; background: #f8fafc; font-size: 12px; }.service-chip i { width: 7px; height: 7px; border-radius: 50%; background: #f59e0b; }.service-chip i.ready { background: #22c55e; }.service-chip i.unavailable { background: #94a3b8; }.service-chip i.loading { background: #f59e0b; }.trial-banner { margin: 0; padding: 9px clamp(20px, 4vw, 56px); border-bottom: 1px solid #f3dd9d; color: #78570a; background: #fff8df; font-size: 13px; line-height: 1.5; }.content { min-width: 0; }.page { width: min(1280px, calc(100% - 40px)); margin: 0 auto; padding: 34px 0 56px; }.page-header { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 24px; }.page-header h1 { margin: 0 0 7px; color: #0f172a; font-size: clamp(24px, 3vw, 31px); }.page-header p { max-width: 760px; margin: 0; color: #64748b; line-height: 1.55; }.card { padding: 22px; border: 1px solid #dde6f0; border-radius: 13px; background: #fff; box-shadow: 0 9px 24px rgb(15 23 42 / 4%); }.button { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 9px 15px; border: 1px solid #214f91; border-radius: 8px; color: #fff; background: #214f91; cursor: pointer; text-decoration: none; }.button.secondary { border-color: #a9b9d0; color: #284568; background: #fff; }.button:disabled { cursor: not-allowed; opacity: .55; }.notice { padding: 15px; border-radius: 9px; color: #43546c; background: #edf3fb; }.notice.error { color: #8c2929; background: #fff0f0; }.notice.success { color: #176744; background: #edf9f3; }.data-table { width: 100%; border-collapse: collapse; }.data-table th, .data-table td { padding: 12px 10px; border-bottom: 1px solid #e7edf4; text-align: left; vertical-align: top; }.data-table th { color: #64748b; font-size: 12px; font-weight: 800; }.data-table td { color: #334155; }.badge { display: inline-block; padding: 4px 8px; border-radius: 999px; color: #334155; background: #edf2f7; font-size: 12px; font-weight: 700; }.table-wrap { overflow-x: auto; }.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 13px; margin: 0; }.metric { padding: 15px; border-radius: 10px; color: #64748b; background: #f6f8fc; }.metric strong { display: block; margin-top: 6px; color: #172554; font-size: 23px; }.app-footer { padding: 0 clamp(20px, 4vw, 56px) 18px; }.technical-toggle, .inline-button { padding: 0; border: 0; color: #526a8c; background: transparent; cursor: pointer; font-size: 12px; text-decoration: underline; }.technical-info { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-top: 9px; color: #64748b; font-size: 12px; }@media (max-width: 900px) { .product-shell { grid-template-columns: 1fr; }.sidebar { position: static; height: auto; padding: 12px; }.brand { padding: 6px 6px 12px; }.side-nav { display: flex; flex-wrap: wrap; gap: 12px; }.nav-group { min-width: 132px; }.topbar { align-items: flex-start; flex-direction: column; }.service-chips { justify-content: flex-start; }.page { width: min(100% - 28px, 1280px); padding-top: 26px; } }@media (max-width: 600px) { .page-header { align-items: flex-start; flex-direction: column; }.service-chips { display: grid; width: 100%; }.service-chip { justify-content: center; }.side-nav { display: grid; grid-template-columns: 1fr 1fr; }.nav-group { min-width: 0; } }
</style>
