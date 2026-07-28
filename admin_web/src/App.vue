<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import {
  getAdminOverview,
  getHealth,
  getAiRuntimeStatus,
} from './api/client'

type ServiceState = 'loading' | 'available' | 'unavailable' | 'not-probed'
type EnvironmentState = 'loading' | 'test' | 'production-preparation' | 'unknown'

const platformState = ref<ServiceState>('loading')
const aiState = ref<ServiceState>('loading')
const customerState = ref<ServiceState>('not-probed')
const environmentState = ref<EnvironmentState>('loading')
const checkedAt = ref('')
const showTechnicalDetails = ref(false)
const refreshing = ref(false)

const navGroups: Array<{ label: string; items: Array<{ label: string; to: string }> }> = [
  { label: '总览', items: [{ label: '运营概览', to: '/overview' }] },
  {
    label: '客服运营',
    items: [
      { label: '客服经验库', to: '/experience-cases' },
      { label: '客服用户', to: '/customer-users' },
      { label: 'AI 问题与分析', to: '/ai-feedback-optimization-pool' },
      { label: '客服建议审核', to: '/suggestions' },
    ],
  },
  {
    label: '商品资料',
    items: [
      { label: '店铺资料', to: '/stores' },
      { label: '商品与 SKU', to: '/products' },
      { label: 'FAQ', to: '/faqs' },
      { label: '安全规则', to: '/safety-rules' },
      { label: '资料来源', to: '/sources' },
      { label: '资料冲突', to: '/conflicts' },
    ],
  },
  {
    label: 'AI 控制中心',
    items: [
      { label: 'AI 运行状态', to: '/ai-capabilities' },
      { label: '历史评测记录', to: '/ai-optimization-pool' },
    ],
  },
  {
    label: '数据与系统',
    items: [
      { label: '商品资料导入', to: '/imports' },
      { label: '测试数据包', to: '/test-data-packages' },
      { label: '服务状态', to: '/system-status' },
    ],
  },
]

const environmentLabel = computed(() => {
  if (environmentState.value === 'test') return '测试环境'
  if (environmentState.value === 'production-preparation') return '生产准备'
  if (environmentState.value === 'loading') return '正在确认环境'
  return '环境未确认'
})

function stateLabel(state: ServiceState): string {
  if (state === 'available') return '可用'
  if (state === 'unavailable') return '不可用'
  if (state === 'loading') return '检测中'
  return '未接入检测'
}

async function refreshStatus(): Promise<void> {
  if (refreshing.value) return
  refreshing.value = true
  const [overviewResult, platformResult, aiResult] = await Promise.allSettled([
    getAdminOverview(),
    getHealth(),
    getAiRuntimeStatus(),
  ])

  environmentState.value = overviewResult.status === 'fulfilled'
    ? (overviewResult.value.test_data_mode ? 'test' : 'production-preparation')
    : 'unknown'
  platformState.value = platformResult.status === 'fulfilled' ? 'available' : 'unavailable'
  aiState.value = aiResult.status === 'fulfilled' && aiResult.value.ready && aiResult.value.modelConfigured
    ? 'available'
    : 'unavailable'
  checkedAt.value = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date())
  refreshing.value = false
}

const runtimeDetails = {
  version: import.meta.env.VITE_ADMIN_VERSION ?? 'unavailable',
  gitCommit: import.meta.env.VITE_GIT_SHORT_SHA ?? 'unavailable',
  buildMode: import.meta.env.VITE_BUILD_MODE ?? 'development',
}

onMounted(() => { void refreshStatus() })
</script>

<template>
  <div class="product-shell">
    <aside class="product-sidebar" aria-label="AI 运营中心导航">
      <RouterLink class="brand" to="/overview">
        <span class="brand-mark" aria-hidden="true">AI</span>
        <span><strong>AI 客服平台</strong><small>AI 运营中心</small></span>
      </RouterLink>

      <nav class="product-nav" aria-label="主要功能">
        <section v-for="group in navGroups" :key="group.label" class="nav-group">
          <h2>{{ group.label }}</h2>
          <RouterLink v-for="item in group.items" :key="item.label" :to="item.to" class="nav-link">
            {{ item.label }}
          </RouterLink>
        </section>
      </nav>

      <div class="sidebar-boundary">
        <strong>业务扩展 · 规划中</strong>
        <p>ERP 数据镜像、售后助手、退款风险辅助尚未启用，不代表已接入或可执行。</p>
        <p class="boundary-rule">系统仅提供人工确认的辅助信息；不自动发送消息、不修改订单、不处理退款。</p>
      </div>
    </aside>

    <section class="product-stage">
      <header class="product-topbar">
        <div class="topbar-title">
          <p>AI 客服平台 / AI 运营中心</p>
          <strong>{{ environmentLabel }}</strong>
        </div>
        <div class="service-statuses" data-testid="admin-service-statuses" aria-label="服务连接状态">
          <span :class="platformState"><i />平台 {{ stateLabel(platformState) }}</span>
          <span :class="aiState"><i />AI {{ stateLabel(aiState) }}</span>
          <span :class="customerState"><i />客服 {{ stateLabel(customerState) }}</span>
          <button type="button" :disabled="refreshing" @click="refreshStatus">{{ refreshing ? '检查中' : '刷新' }}</button>
        </div>
        <button
          class="technical-toggle"
          type="button"
          :aria-expanded="showTechnicalDetails"
          data-testid="admin-technical-toggle"
          @click="showTechnicalDetails = !showTechnicalDetails"
        >
          {{ showTechnicalDetails ? '收起技术信息' : '技术信息' }}
        </button>
      </header>

      <p class="environment-banner">
        {{ environmentState === 'test'
          ? '测试环境：只使用测试或已去标识化数据。所有业务动作均需人工确认。'
          : '当前环境状态尚未确认：请勿据此执行客户消息、订单或数据写入操作。' }}
      </p>

      <section v-if="showTechnicalDetails" class="technical-panel" data-testid="admin-technical-details">
        <div><span>管理端版本</span><code>{{ runtimeDetails.version }}</code></div>
        <div><span>Git Commit</span><code>{{ runtimeDetails.gitCommit }}</code></div>
        <div><span>构建模式</span><code>{{ runtimeDetails.buildMode }}</code></div>
        <div><span>最近检查</span><code>{{ checkedAt || '未检查' }}</code></div>
        <p>客服服务当前没有冻结的健康检查接口，因此“未接入检测”不是客服不可用的结论。</p>
      </section>

      <main class="product-content"><RouterView /></main>
    </section>
  </div>
</template>

<style>
* { box-sizing: border-box; }

body { margin: 0; color: #172033; background: #f4f7fb; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
a { color: #285493; }

.product-shell { --sidebar-width: 244px; display: grid; grid-template-columns: var(--sidebar-width) minmax(0, 1fr); width: 100%; min-height: 100vh; }
.product-sidebar { display: flex; min-height: 100vh; flex-direction: column; padding: 18px 12px; background: linear-gradient(180deg, #12294d, #0d1e3b); color: #eaf1ff; box-shadow: 8px 0 28px rgb(18 40 77 / 12%); }
.brand { display: flex; gap: 11px; align-items: center; padding: 2px 8px 17px; color: #fff; text-decoration: none; }
.brand-mark { display: grid; width: 40px; height: 40px; place-items: center; border-radius: 12px; background: linear-gradient(135deg, #75a5ff, #59d3b3); color: #102342; font-size: 13px; font-weight: 900; }
.brand strong, .brand small { display: block; }
.brand strong { font-size: 16px; letter-spacing: .01em; }
.brand small { margin-top: 3px; color: #9fb2d1; font-size: 12px; }
.product-nav { display: grid; gap: 11px; overflow-y: auto; padding-right: 2px; }
.nav-group { display: grid; gap: 2px; }
.nav-group h2 { margin: 0; padding: 0 9px 3px; color: #91a7ca; font-size: 10px; font-weight: 800; letter-spacing: .08em; }
.nav-link { display: block; min-height: 31px; overflow: hidden; padding: 7px 10px; border-radius: 8px; color: #c1d0e7; font-size: 13px; line-height: 17px; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }
.nav-link:hover, .nav-link.router-link-active { color: #fff; background: rgb(103 153 245 / 22%); }
.sidebar-boundary { margin-top: 15px; padding: 12px; border: 1px solid rgb(160 183 220 / 22%); border-radius: 11px; background: rgb(255 255 255 / 6%); }
.sidebar-boundary strong { font-size: 12px; }
.sidebar-boundary p { margin: 5px 0 0; color: #a7b8d3; font-size: 11px; line-height: 1.5; }
.sidebar-boundary .boundary-rule { color: #d4dfef; }
.product-stage { min-width: 0; }
.product-topbar { display: flex; min-width: 0; align-items: center; gap: 14px; min-height: 66px; padding: 10px 22px; border-bottom: 1px solid #d8e1ee; background: rgb(255 255 255 / 95%); }
.topbar-title p { margin: 0 0 3px; color: #718096; font-size: 11px; }
.topbar-title strong { font-size: 16px; }
.service-statuses { display: flex; align-items: center; gap: 9px; margin-left: auto; }
.service-statuses span { display: flex; align-items: center; gap: 5px; color: #526981; font-size: 12px; white-space: nowrap; }
.service-statuses i { width: 8px; height: 8px; border-radius: 50%; background: #7c8ca3; }
.service-statuses .available { color: #20704d; }.service-statuses .available i { background: #2da875; }
.service-statuses .unavailable { color: #9a511b; }.service-statuses .unavailable i { background: #d47b26; }
.service-statuses .not-probed { color: #65758b; }.service-statuses .not-probed i { background: #8b9bb0; }
.service-statuses button, .technical-toggle { padding: 5px 8px; border: 1px solid #ccd8e8; border-radius: 8px; background: #fff; color: #365174; font: inherit; font-size: 12px; cursor: pointer; }
.service-statuses button:disabled { cursor: wait; opacity: .6; }
.environment-banner { margin: 0; padding: 8px 22px; border-bottom: 1px solid #f2d596; background: #fff8e7; color: #77510a; font-size: 12px; line-height: 1.5; }
.technical-panel { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px 14px; padding: 12px 22px; border-bottom: 1px solid #dce6f2; background: #f7faff; }
.technical-panel div { display: grid; gap: 3px; min-width: 0; }.technical-panel span, .technical-panel p { color: #6b7b91; font-size: 11px; }.technical-panel code { overflow: hidden; color: #2d4364; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.technical-panel p { grid-column: 1 / -1; margin: 0; line-height: 1.5; }
.product-content { min-width: 0; padding: 0 22px 34px; }.page { width: min(1180px, 100%); margin: 0 auto; padding: 30px 0 48px; }.page-header { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 24px; }.page-header h1 { margin: 0 0 6px; }.page-header p { margin: 0; color: #617087; }.card { padding: 22px; border: 1px solid #dbe3ef; border-radius: 14px; background: #fff; box-shadow: 0 12px 30px rgb(30 52 86 / 7%); }.button { display: inline-flex; align-items: center; justify-content: center; min-height: 39px; padding: 9px 15px; border: 0; border-radius: 8px; color: #fff; background: #284f8f; font: inherit; text-decoration: none; cursor: pointer; }.button.secondary { border: 1px solid #9fb2cc; color: #25466f; background: #fff; }.button:disabled { cursor: not-allowed; opacity: .55; }.notice { padding: 15px; border-radius: 9px; background: #edf3fb; }.notice.error { color: #8c2929; background: #fff0f0; }.notice.success { color: #176744; background: #edf9f3; }.data-table { width: 100%; border-collapse: collapse; }.data-table th, .data-table td { padding: 12px 10px; border-bottom: 1px solid #e4e9f1; text-align: left; vertical-align: top; }.data-table th { color: #526279; font-size: 13px; }.badge { display: inline-block; padding: 4px 8px; border-radius: 999px; color: #33445c; background: #edf1f6; font-size: 12px; font-weight: 700; }.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin: 20px 0; }.metric { padding: 14px; border-radius: 10px; background: #f5f7fb; }.metric strong { display: block; margin-top: 5px; font-size: 22px; }
@media (max-width: 1080px) { .product-shell { grid-template-columns: 208px minmax(0, 1fr); }.technical-panel { grid-template-columns: repeat(3, minmax(0, 1fr)); }.service-statuses span:nth-child(3) { display: none; } }
@media (max-width: 820px) { .product-shell { grid-template-columns: 1fr; }.product-sidebar { min-height: auto; padding: 13px; }.product-nav { grid-template-columns: repeat(3, minmax(150px, 1fr)); }.sidebar-boundary { display: none; }.product-topbar { flex-wrap: wrap; padding: 10px 14px; }.service-statuses { margin-left: 0; }.product-content { padding: 0 14px 28px; }.environment-banner, .technical-panel { padding-right: 14px; padding-left: 14px; } }
@media (max-width: 560px) { .product-nav { grid-template-columns: repeat(2, minmax(0, 1fr)); }.service-statuses span { font-size: 11px; }.technical-toggle { display: none; }.technical-panel { grid-template-columns: repeat(2, minmax(0, 1fr)); }.page-header { align-items: flex-start; flex-direction: column; }.table-wrap { overflow-x: auto; } }
</style>
