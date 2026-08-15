<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  getAdminOverview,
  getHealth,
  type HealthResponse
} from './api/client'
import { useAdminSession } from './auth/session'
import {
  aiControlCenterError,
  aiControlCenterLoading,
  aiControlCenterOverview,
  loadAiControlCenterOverview,
} from './stores/aiControlCenter'

type ServiceState = 'loading' | 'available' | 'unavailable' | 'not-probed'
type EnvironmentState = 'loading' | 'internal-production' | 'unknown'
type NavigationMode = 'simple' | 'advanced'
type NavigationItem = { label: string; to: string; requiredPermission?: string }
type NavigationGroup = { label: string; items: NavigationItem[] }

const NAVIGATION_MODE_STORAGE_KEY = 'ai-cs-admin-navigation-mode-v1'
const route = useRoute()
const router = useRouter()
const auth = useAdminSession()

const simpleNavigationItems: NavigationItem[] = [
  { label: '运营工作台', to: '/overview' },
  { label: '店铺与商品', to: '/store-management' },
  { label: '知识', to: '/knowledge-center' },
  { label: '商品回答风险池', to: '/reply-readiness', requiredPermission: 'knowledge.manage' },
  { label: '知识编辑器', to: '/knowledge-editor', requiredPermission: 'knowledge.manage' },
  { label: '导入', to: '/import-center' },
  { label: '客服运营', to: '/customer-operations' },
  { label: 'AI状态', to: '/ai-capabilities' },
]

const advancedNavigationGroups: NavigationGroup[] = [
  {
    label: '知识治理',
    items: [
      { label: '知识审核队列', to: '/knowledge-review' },
      { label: '知识缺口', to: '/knowledge-gaps' },
      { label: '资料上传与审核', to: '/knowledge-materials' },
      { label: 'FAQ管理', to: '/faqs' },
      { label: '安全规则', to: '/safety-rules' },
    ],
  },
  {
    label: '运营复盘',
    items: [
      { label: 'AI问题中心', to: '/ai-issues' },
      { label: '反馈分析', to: '/ai-feedback-optimization-pool' },
      { label: '回复质量', to: '/experience-cases' },
    ],
  },
  {
    label: '系统诊断',
    items: [
      { label: '服务状态', to: '/system-status' },
    ],
  },
]

function initialNavigationMode(): NavigationMode {
  try {
    return globalThis.localStorage?.getItem(NAVIGATION_MODE_STORAGE_KEY) === 'advanced'
      ? 'advanced'
      : 'simple'
  } catch {
    return 'simple'
  }
}

const platformState = ref<ServiceState>('loading')
const aiState = computed<ServiceState>(() => {
  if (aiControlCenterLoading.value && !aiControlCenterOverview.value) return 'loading'
  const value = aiControlCenterOverview.value
  if (aiControlCenterError.value || !value) return 'unavailable'
  return value.service.status === 'RUNNING'
    && value.service.ready === true
    && value.service.modelConfigured === true
    ? 'available'
    : 'unavailable'
})
const customerState = ref<ServiceState>('not-probed')
const environmentState = ref<EnvironmentState>('loading')
const health = ref<HealthResponse | null>(null)
const checkedAt = ref('')
const showTechnicalDetails = ref(false)
const refreshing = ref(false)
const navigationMode = ref<NavigationMode>(initialNavigationMode())
const mobileNavigationOpen = ref(false)
const visibleSimpleNavigationItems = computed(() => simpleNavigationItems.filter((item) => (
  !item.requiredPermission || auth.hasPermission(item.requiredPermission)
)))

const navigationModeDescription = computed(() => navigationMode.value === 'simple'
  ? '显示当前账号可用的常用入口。'
  : '展开知识治理、运营复盘和系统诊断入口。')

function setNavigationMode(mode: NavigationMode): void {
  navigationMode.value = mode
  try {
    globalThis.localStorage?.setItem(NAVIGATION_MODE_STORAGE_KEY, mode)
  } catch {
    // Restricted browsers still keep the selected mode for the current page.
  }
}

const environmentLabel = computed(() => {
  if (environmentState.value === 'internal-production') return '内部生产就绪'
  if (environmentState.value === 'loading') return '正在确认环境'
  return '环境未确认'
})

const stateLabel = (state: ServiceState) => {
  if (state === 'available') return '可用'
  if (state === 'unavailable') return '待连接'
  if (state === 'loading') return '检测中'
  return '未检测'
}

async function refreshStatus(): Promise<void> {
  if (refreshing.value) return
  refreshing.value = true
  const [overviewResult, platformResult, aiResult] = await Promise.allSettled([
    getAdminOverview(),
    getHealth(),
    loadAiControlCenterOverview(true),
  ])

  if (overviewResult.status === 'fulfilled') {
    environmentState.value = 'internal-production'
  } else {
    environmentState.value = 'unknown'
  }

  if (platformResult.status === 'fulfilled') {
    health.value = platformResult.value
    platformState.value = 'available'
  } else {
    health.value = null
    platformState.value = 'unavailable'
  }

  // The header and AI status page consume the same shared runtime fact.
  void aiResult
  checkedAt.value = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  }).format(new Date())
  refreshing.value = false
}

const runtimeDetails = {
  version: import.meta.env.VITE_ADMIN_VERSION ?? 'unavailable',
  releaseStatus: 'INTERNAL_PRODUCTION_READY',
  gitCommit: import.meta.env.VITE_GIT_SHORT_SHA ?? 'unavailable',
  buildMode: import.meta.env.VITE_BUILD_MODE ?? 'development'
}

const signOut = async () => { await auth.logout(); await router.replace('/login') }

watch(() => route.fullPath, () => { mobileNavigationOpen.value = false })
onMounted(() => { if (route.meta.public !== true) void refreshStatus() })
</script>

<template>
  <RouterView v-if="route.meta.public === true" />
  <div v-else class="product-shell">
    <aside :class="['product-sidebar', { 'mobile-open': mobileNavigationOpen }]" aria-label="运营管理中心导航">
      <div class="sidebar-header">
        <RouterLink class="brand" to="/overview">
          <span class="brand-mark" aria-hidden="true">AI</span>
          <span><strong>AI客服平台</strong><small>运营管理中心</small></span>
        </RouterLink>
        <button
          class="mobile-navigation-toggle"
          type="button"
          aria-controls="admin-navigation-content"
          :aria-expanded="mobileNavigationOpen"
          @click="mobileNavigationOpen = !mobileNavigationOpen"
        >{{ mobileNavigationOpen ? '收起' : '菜单' }}</button>
      </div>

      <div id="admin-navigation-content" class="mobile-navigation-content">
        <section class="navigation-mode" aria-label="导航显示模式">
        <div class="navigation-mode__heading">
          <strong>导航模式</strong>
          <span>{{ navigationMode === 'simple' ? '简洁' : '高级' }}</span>
        </div>
        <div class="navigation-mode__buttons" role="group" aria-label="切换导航模式">
          <button
            type="button"
            :class="{ active: navigationMode === 'simple' }"
            :aria-pressed="navigationMode === 'simple'"
            data-testid="navigation-mode-simple"
            @click="setNavigationMode('simple')"
          >简洁模式</button>
          <button
            type="button"
            :class="{ active: navigationMode === 'advanced' }"
            :aria-pressed="navigationMode === 'advanced'"
            data-testid="navigation-mode-advanced"
            @click="setNavigationMode('advanced')"
          >高级模式</button>
        </div>
        <small>{{ navigationModeDescription }}</small>
        <small>模式只改变导航显示，不改变页面权限。</small>
        </section>

        <nav class="product-nav" aria-label="运营管理中心导航">
        <section class="nav-group">
          <h2>常用工作</h2>
          <RouterLink
            v-for="item in visibleSimpleNavigationItems"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            data-testid="simple-navigation-item"
          >
            {{ item.label }}
          </RouterLink>
          <RouterLink
            v-if="auth.hasPermission('user.manage')"
            to="/user-management"
            class="nav-link"
            data-testid="user-management-navigation"
          >用户管理</RouterLink>
        </section>

        <template v-if="navigationMode === 'advanced'">
          <p class="advanced-navigation-label" data-testid="advanced-navigation-label">高级功能</p>
          <section v-for="group in advancedNavigationGroups" :key="group.label" class="nav-group" data-testid="advanced-navigation-group">
            <h2>{{ group.label }}</h2>
            <RouterLink
              v-for="item in group.items"
              :key="item.to"
              :to="item.to"
              class="nav-link"
              data-testid="advanced-navigation-item"
            >
              {{ item.label }}
            </RouterLink>
          </section>
        </template>
        </nav>

        <section v-if="navigationMode === 'advanced'" class="planned-capabilities" aria-label="规划中的业务能力">
          <strong>后续能力</strong>
          <p>ERP 镜像、售后助手和退款风险辅助仍在规划中，当前没有自动业务动作。</p>
        </section>

        <div class="sidebar-boundary">
          <strong>内部运营管理</strong>
          <p>页面权限由服务端校验；系统不自动发送、修改订单、退款或写入 ERP。</p>
        </div>
      </div>
    </aside>

    <section class="product-stage">
      <header class="product-topbar">
        <div>
          <p>AI客服平台 · 运营管理中心</p>
          <strong>{{ environmentLabel }}</strong>
        </div>
        <div class="service-statuses" data-testid="admin-service-statuses">
          <span :class="platformState"><i />平台 {{ stateLabel(platformState) }}</span>
          <span :class="aiState"><i />AI {{ stateLabel(aiState) }}</span>
          <span :class="customerState"><i />客服 {{ stateLabel(customerState) }}</span>
          <button type="button" :disabled="refreshing" @click="refreshStatus">{{ refreshing ? '检查中' : '刷新' }}</button>
        </div>
        <div class="admin-identity" data-testid="admin-identity">
          <strong>{{ auth.displayName.value }}</strong>
          <button type="button" data-testid="admin-logout" @click="signOut">退出</button>
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
        {{ environmentState === 'internal-production' ? 'AI-CS V1.0.0 已进入内部生产使用。所有业务动作均需人工确认；系统不会自动发送消息、自动退款或修改订单。' : '当前环境状态未确认：不要据此执行客户、订单或数据写入动作。' }}
      </p>

      <section v-if="showTechnicalDetails" class="technical-panel" data-testid="admin-technical-details">
        <div><span>管理端版本</span><code>{{ runtimeDetails.version }}</code></div>
        <div><span>运行状态</span><code>{{ runtimeDetails.releaseStatus }}</code></div>
        <div><span>Git Commit</span><code>{{ runtimeDetails.gitCommit }}</code></div>
        <div><span>构建模式</span><code>{{ runtimeDetails.buildMode }}</code></div>
        <div><span>平台版本</span><code>{{ health?.version ?? '未取得' }}</code></div>
        <div><span>检查时间</span><code>{{ checkedAt || '未检查' }}</code></div>
        <p>客服入口未检测，因为当前没有已冻结的客服健康接口；这不是“客服服务不可用”的判断。</p>
      </section>

      <main class="product-content"><RouterView /></main>
    </section>
  </div>
</template>

<style>
* { box-sizing: border-box; }

body { margin: 0; color: #172033; background: #f3f6fb; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
a { color: #285493; }

.product-shell { --sidebar-width: 248px; display: grid; grid-template-columns: var(--sidebar-width) minmax(0, 1fr); width: 100%; min-height: 100vh; }
.product-sidebar { display: flex; min-height: 100vh; flex-direction: column; padding: 20px 14px; background: linear-gradient(180deg, #14284d, #0d1e3b); color: #eaf1ff; box-shadow: 8px 0 28px rgb(18 40 77 / 12%); }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.brand { display: flex; gap: 11px; align-items: center; padding: 0 7px 20px; color: #fff; text-decoration: none; }
.brand-mark { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 13px; background: linear-gradient(135deg, #6fa1ff, #53d1b1); color: #0e2344; font-size: 13px; font-weight: 900; }
.brand strong, .brand small { display: block; }
.brand strong { font-size: 17px; }
.brand small { margin-top: 3px; color: #9fb2d1; font-size: 12px; }
.mobile-navigation-toggle { display: none; padding: 7px 10px; border: 1px solid rgb(160 183 220 / 35%); border-radius: 8px; color: #fff; background: rgb(255 255 255 / 8%); font: inherit; font-size: 12px; cursor: pointer; }
.mobile-navigation-content { display: flex; flex: 1; min-height: 0; flex-direction: column; }
.navigation-mode { display: grid; gap: 8px; margin-bottom: 14px; padding: 10px; border: 1px solid rgb(160 183 220 / 22%); border-radius: 11px; background: rgb(255 255 255 / 5%); }
.navigation-mode__heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.navigation-mode__heading strong { font-size: 12px; }
.navigation-mode__heading span { padding: 2px 7px; border-radius: 999px; color: #dbe8fb; background: rgb(111 159 244 / 22%); font-size: 10px; }
.navigation-mode__buttons { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px; }
.navigation-mode__buttons button { min-height: 30px; padding: 5px 7px; border: 1px solid rgb(160 183 220 / 25%); border-radius: 8px; color: #b9c8df; background: transparent; font: inherit; font-size: 11px; cursor: pointer; }
.navigation-mode__buttons button.active { border-color: #7aa5ef; color: #fff; background: rgb(103 153 245 / 24%); }
.navigation-mode > small { color: #91a7ca; font-size: 10px; line-height: 1.45; }
.product-nav { display: grid; gap: 12px; }
.nav-group { display: grid; gap: 4px; }
.nav-group h2 { margin: 0; padding: 0 9px 4px; color: #91a7ca; font-size: 11px; font-weight: 800; letter-spacing: .06em; }
.advanced-navigation-label { margin: 4px 9px -4px; color: #dbe8fb; font-size: 11px; font-weight: 800; letter-spacing: .06em; }
.nav-link { display: flex; min-height: 34px; align-items: center; justify-content: space-between; padding: 7px 10px; border-radius: 9px; color: #c1d0e7; font-size: 13px; text-decoration: none; }
.nav-link:hover, .nav-link.router-link-active { color: #fff; background: rgb(103 153 245 / 21%); }
.nav-link.planned { color: #8498b8; cursor: default; }
.nav-link.planned small { color: #8297b6; font-size: 10px; }
.planned-capabilities { margin-top: 16px; padding: 11px 12px; border-left: 2px solid rgb(160 183 220 / 35%); color: #9fb2d1; }
.planned-capabilities strong { color: #b9c8df; font-size: 12px; }
.planned-capabilities p { margin: 5px 0 0; font-size: 11px; line-height: 1.55; }
.sidebar-boundary { margin-top: auto; padding: 13px; border: 1px solid rgb(160 183 220 / 22%); border-radius: 12px; background: rgb(255 255 255 / 6%); }
.sidebar-boundary strong { font-size: 13px; }
.sidebar-boundary p { margin: 6px 0 0; color: #9fb2d1; font-size: 11px; line-height: 1.55; }
.product-stage { min-width: 0; }
.product-topbar { display: flex; min-width: 0; align-items: center; gap: 16px; min-height: 68px; padding: 10px 22px; border-bottom: 1px solid #d8e1ee; background: rgb(255 255 255 / 94%); }
.product-topbar p { margin: 0 0 3px; color: #718096; font-size: 11px; }
.product-topbar strong { font-size: 16px; }
.service-statuses { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.service-statuses span { display: flex; align-items: center; gap: 5px; color: #526981; font-size: 12px; white-space: nowrap; }
.service-statuses i { width: 8px; height: 8px; border-radius: 50%; background: #7c8ca3; }
.service-statuses .available { color: #20704d; }
.service-statuses .available i { background: #2da875; }
.service-statuses .unavailable { color: #8a5a00; }
.service-statuses .unavailable i { background: #e8a321; }
.service-statuses button, .technical-toggle { padding: 5px 8px; border: 1px solid #ccd8e8; border-radius: 8px; background: #fff; color: #365174; font: inherit; font-size: 12px; cursor: pointer; }
.service-statuses button:disabled { cursor: wait; opacity: .6; }
.admin-identity { display: flex; min-width: 0; align-items: center; gap: 7px; }
.admin-identity strong { overflow: hidden; max-width: 130px; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.admin-identity button { padding: 5px 8px; border: 1px solid #ccd8e8; border-radius: 8px; background: #fff; color: #365174; font: inherit; font-size: 12px; cursor: pointer; }
.environment-banner { margin: 0; padding: 8px 22px; border-bottom: 1px solid #f2d596; background: #fff8e7; color: #77510a; font-size: 12px; line-height: 1.5; }
.technical-panel { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px 14px; padding: 12px 22px; border-bottom: 1px solid #dce6f2; background: #f7faff; }
.technical-panel div { display: grid; gap: 3px; min-width: 0; }
.technical-panel span, .technical-panel p { color: #6b7b91; font-size: 11px; }
.technical-panel code { overflow: hidden; color: #2d4364; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.technical-panel p { grid-column: 1 / -1; margin: 0; line-height: 1.5; }
.product-content { min-width: 0; padding: 0 22px 34px; }
.page { width: min(1180px, 100%); margin: 0 auto; padding: 32px 0 48px; }
.page-header { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { margin: 0; color: #617087; }
.card { padding: 24px; border: 1px solid #dbe3ef; border-radius: 14px; background: #fff; box-shadow: 0 12px 30px rgb(30 52 86 / 7%); }
.button { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 9px 16px; border: 0; border-radius: 8px; color: #fff; background: #284f8f; font: inherit; text-decoration: none; cursor: pointer; }
.button.secondary { border: 1px solid #9fb2cc; color: #25466f; background: #fff; }
.button:disabled { cursor: not-allowed; opacity: .55; }
.notice { padding: 16px; border-radius: 9px; background: #edf3fb; }
.notice.error { color: #8c2929; background: #fff0f0; }
.notice.success { color: #176744; background: #edf9f3; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 12px 10px; border-bottom: 1px solid #e4e9f1; text-align: left; vertical-align: top; }
.data-table th { color: #526279; font-size: 13px; }
.badge { display: inline-block; padding: 4px 8px; border-radius: 999px; color: #33445c; background: #edf1f6; font-size: 12px; font-weight: 700; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin: 20px 0; }
.metric { padding: 14px; border-radius: 10px; background: #f5f7fb; }
.metric strong { display: block; margin-top: 5px; font-size: 22px; }
@media (max-width: 1080px) { .product-shell { grid-template-columns: 210px minmax(0, 1fr); } .technical-panel { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 820px) { .product-shell { grid-template-columns: 1fr; } .product-sidebar { min-height: auto; padding: 13px; } .product-sidebar .brand { padding-bottom: 0; } .mobile-navigation-toggle { display: inline-flex; } .product-sidebar:not(.mobile-open) .mobile-navigation-content { display: none; } .mobile-navigation-content { padding-top: 12px; } .product-nav { grid-template-columns: repeat(3, minmax(150px, 1fr)); } .sidebar-boundary { display: none; } .product-topbar { flex-wrap: wrap; gap: 8px 12px; padding: 10px 14px; } .product-topbar > :first-child { flex: 1 1 auto; } .service-statuses { order: 4; width: 100%; margin-left: 0; flex-wrap: wrap; } .admin-identity { margin-left: auto; } .product-content { padding: 0 14px 28px; } .environment-banner, .technical-panel { padding-right: 14px; padding-left: 14px; } }
@media (max-width: 560px) { .brand-mark { width: 38px; height: 38px; border-radius: 11px; } .product-nav { grid-template-columns: repeat(2, minmax(0, 1fr)); } .service-statuses { gap: 7px; } .service-statuses span { font-size: 11px; } .admin-identity strong { max-width: 90px; } .technical-toggle { display: none; } .technical-panel { grid-template-columns: repeat(2, minmax(0, 1fr)); } .page-header { align-items: flex-start; flex-direction: column; } .table-wrap { overflow-x: auto; } }
</style>
