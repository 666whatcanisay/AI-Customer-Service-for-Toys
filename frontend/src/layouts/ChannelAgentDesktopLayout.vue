<template>
  <div class="agent-desktop-shell" data-testid="agent-desktop-shell">
    <header class="agent-desktop-bar">
      <div class="brand">
        <span class="brand-mark">AI</span>
        <div><strong>AI 客服助手</strong><small>客服工作台</small></div>
      </div>

      <div class="runtime-summary" aria-label="客服工作台摘要">
        <div class="auto-control-cluster">
          <button
            type="button"
            class="auto-reply-toggle"
            :class="autoReplyRunning ? 'running' : 'paused'"
            :disabled="autoToggleBusy || autoRepairBusy || !autoControlAvailable"
            :title="autoControlTitle"
            data-testid="controlled-auto-toggle"
            @click="toggleControlledAuto"
          >
            <i />{{ autoToggleBusy ? '切换中…' : autoControlLabel }}
          </button>
          <button
            v-if="autoRepairNeeded || !autoReplyRunning"
            type="button"
            class="auto-repair-button"
            :disabled="autoRepairBusy"
            title="重新核对当前店铺与工作台，恢复为暂停可开启状态"
            data-testid="controlled-auto-repair"
            @click="repairControlledAuto"
          >{{ autoRepairBusy ? '修复中…' : '一键修复' }}</button>
        </div>
        <span class="overall-status" :class="overallStatus.tone" data-testid="overall-runtime-status">
          <i />{{ overallStatus.label }}
        </span>
        <select
          v-if="storeOptions.length > 1"
          v-model="selectedStore"
          :disabled="loading || switchingStore"
          aria-label="当前工作店铺"
          @change="confirmStoreSelection"
        >
          <option value="" disabled>选择当前工作店铺</option>
          <option
            v-for="store in storeOptions"
            :key="store.storeCode"
            :value="store.storeCode"
            :disabled="!store.pddBinding"
          >{{ store.label }}</option>
        </select>
        <span v-else class="store-summary" :class="activeStore ? 'healthy' : 'attention'" data-testid="active-store-status">
          {{ activeStore?.label ?? '店铺待绑定' }}
        </span>
        <span class="pending-summary" data-testid="pending-conversation-count">
          待处理 <strong>{{ pendingConversationCount }}</strong>
        </span>
      </div>

      <div class="operator">
        <button type="button" class="detail-button" data-testid="open-runtime-details" @click="openRuntimeDetails">
          运行详情
        </button>
        <div class="more-wrap">
          <button
            type="button"
            class="more-button"
            aria-label="更多操作"
            :aria-expanded="moreMenuOpen"
            data-testid="desktop-more-menu"
            @click="moreMenuOpen = !moreMenuOpen"
          >•••</button>
          <div v-if="moreMenuOpen" class="more-menu" role="menu">
            <div class="operator-identity"><small>当前客服</small><strong>{{ auth.user.value?.display_name ?? '未登录' }}</strong></div>
            <button type="button" role="menuitem" :disabled="loading" @click="refreshFromMenu">刷新状态</button>
            <button type="button" role="menuitem" class="danger" @click="requestStopFromMenu">安全退出</button>
          </div>
        </div>
      </div>
    </header>

    <div v-if="actionAlert" class="action-alert" :class="actionAlert.tone" role="status" data-testid="runtime-action-alert">
      <div>
        <strong>{{ actionAlert.title }}</strong>
        <span>{{ actionAlert.impact }}</span>
      </div>
      <button
        v-if="actionAlert.action"
        type="button"
        :disabled="runtimeActionBusy"
        :data-testid="actionAlert.testId"
        @click="runAlertAction"
      >{{ runtimeActionBusy ? '处理中…' : actionAlert.actionLabel }}</button>
      <button v-if="actionAlert.showCopyUrl" type="button" @click="copyPddUrl">复制工作台地址</button>
      <button type="button" class="subtle" @click="openRuntimeDetails">查看详情</button>
    </div>

    <main class="agent-desktop-content">
      <RouterView />
    </main>

    <div v-if="runtimeDetailsOpen" class="runtime-drawer-backdrop" data-testid="runtime-details-drawer" @click.self="runtimeDetailsOpen = false">
      <aside class="runtime-drawer" aria-label="运行详情">
        <header>
          <div><small>运行诊断</small><h2>运行详情</h2></div>
          <button type="button" aria-label="关闭运行详情" data-testid="close-runtime-details" @click="runtimeDetailsOpen = false">×</button>
        </header>

        <section class="detail-section">
          <div class="section-heading"><strong>当前运行</strong><button type="button" :disabled="loading || runtimeDetailsLoading" @click="refreshRuntimeDetails">刷新</button></div>
          <dl class="detail-grid">
            <div><dt>总体状态</dt><dd :class="overallStatus.tone">{{ overallStatus.label }}</dd></div>
            <div><dt>Agent</dt><dd>{{ statusLabel(agentStatus) }}</dd></div>
            <div><dt>PDD</dt><dd>{{ pddLabel }}</dd></div>
            <div data-testid="message-source-status"><dt>消息读取</dt><dd>{{ messageSourceLabel }}</dd></div>
            <div><dt>当前客服</dt><dd>{{ auth.user.value?.display_name ?? '未登录' }}</dd></div>
            <div><dt>当前店铺</dt><dd>{{ activeStore?.label ?? '未绑定' }}</dd></div>
          </dl>
        </section>

        <section class="detail-section">
          <strong>客服连接程序</strong>
          <dl class="detail-grid">
            <div><dt>关联状态</dt><dd>{{ desktopAssociationLabel }}</dd></div>
            <div><dt>当前设备</dt><dd>{{ desktopAgentStatus?.agent?.deviceName || desktopAgentStatus?.agent?.deviceId || '未关联' }}</dd></div>
            <div><dt>程序版本</dt><dd>{{ desktopAgentStatus?.agent?.agentVersion || bootstrap?.agent.version || '—' }}</dd></div>
            <div><dt>最后心跳</dt><dd>{{ desktopHeartbeatLabel }}</dd></div>
            <div><dt>Agent编号</dt><dd>{{ desktopAgentStatus?.agent?.agentId || bootstrap?.binding.agent_id || '—' }}</dd></div>
            <div><dt>设备编号</dt><dd>{{ desktopAgentStatus?.agent?.deviceId || bootstrap?.binding.device_id || '—' }}</dd></div>
          </dl>
          <p v-if="runtimeDetailsError" class="detail-error">{{ runtimeDetailsError }}</p>
        </section>

        <section class="detail-section">
          <strong>回复与发送安全</strong>
          <div v-if="controlledAuto?.state_revision" class="controlled-policy-fact" data-testid="controlled-auto-policy">
            <span>生产自动回复策略</span>
            <strong>{{ controlledAuto.policy_mode }}</strong>
            <small>每条客户消息仍会独立生成单次 Grant；本开关不会给 Sender 长期通配权限。</small>
          </div>
          <label v-else class="policy-control">
            <span>回复策略</span>
            <select
              :value="replyPolicy?.mode ?? 'MANUAL_CONFIRM'"
              :disabled="replyPolicyBusy || !activeStoreNumericId || !canManageReplyPolicy"
              data-testid="reply-policy-mode"
              @change="changeReplyPolicy"
            >
              <option value="MANUAL_CONFIRM">MANUAL_CONFIRM（人工确认）</option>
              <option value="AUTO_LOW_RISK">AUTO_LOW_RISK（仅低风险自动准备）</option>
            </select>
          </label>
          <div class="controlled-policy-fact" data-testid="controlled-auto-scope">
            <span>自动回复范围</span>
            <strong>仅当前人工打开的 PDD 会话</strong>
            <small>不会自动点击、滚动或切换买家列表；切换会话后只观察新打开的当前会话。</small>
          </div>
          <div class="safety-facts">
            <span>{{ autoReplyRunning ? '逐消息自动授权已启用' : '新消息自动授权已暂停' }}</span>
            <strong>REAL_SEND = {{ realSendEnabled ? 'ON' : 'OFF' }}</strong>
          </div>
          <p v-if="controlledAuto?.control_error_code" class="detail-error">{{ controlledAuto.control_error_code }}</p>
          <p v-if="replyPolicyError" class="detail-error">{{ replyPolicyError }}</p>
          <small>顶部开关控制生产 AUTO 是否为新消息签发单次授权；双店铺、目标、去重、UNKNOWN 不重试及 Kill Switch 始终有效。</small>
        </section>

        <section class="detail-section">
          <strong>PDD 工作台</strong>
          <div class="workspace-url"><code>{{ PDD_CUSTOMER_SERVICE_URL }}</code><button type="button" @click="copyPddUrl">复制地址</button></div>
          <div class="drawer-actions">
            <button v-if="canOpenPddWindow" type="button" :disabled="openingPdd" @click="openPddWindow">启动专属窗口</button>
            <button v-if="canRefreshPddWorkspace" type="button" :disabled="refreshingPdd" @click="refreshPddWorkspace">重新识别工作台</button>
            <button v-if="canRestartPddObserver" type="button" :disabled="restartingObserver || !realMessageObservationEnabled" data-testid="restart-pdd-observer" @click="restartPddObserver">{{ observerRestartLabel }}</button>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref } from 'vue'
import { RouterView } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useAuthSession } from '@/auth/authSession'
import { desktopAgentClient } from '@/api/desktopAgentClient'
import type { DesktopAgentStatus } from '@/api/desktopAgentTypes'
import {
  offlineReplyControlClient,
  type ReplyPolicy,
  type ReplyPolicyMode
} from '@/api/offlineReplyControlClient'
import {
  fetchChannelAgentBootstrap,
  requestChannelAgentControlledAutoRepair,
  requestChannelAgentControlledAutoToggle,
  requestChannelAgentPddObserverRestart,
  requestChannelAgentPddWorkspaceRefresh,
  requestChannelAgentPddWindowOpen,
  requestChannelAgentSafeStop,
  selectChannelAgentActiveStore,
  type ChannelAgentBootstrap
} from '@/api/channelAgentDesktopClient'
import { useHumanLoopWorkspaceStore } from '@/stores/humanLoopWorkspace'

const auth = useAuthSession()
const workspace = useHumanLoopWorkspaceStore()
const { conversationCounts } = storeToRefs(workspace)
const bootstrap = ref<ChannelAgentBootstrap | null>(null)
const loading = ref(false)
const error = ref(false)
const switchingStore = ref(false)
const openingPdd = ref(false)
const refreshingPdd = ref(false)
const restartingObserver = ref(false)
const autoToggleBusy = ref(false)
const autoRepairBusy = ref(false)
const selectedStore = ref('')
const moreMenuOpen = ref(false)
const runtimeDetailsOpen = ref(false)
const runtimeDetailsLoading = ref(false)
const runtimeDetailsError = ref('')
const desktopAgentStatus = ref<DesktopAgentStatus | null>(null)
const replyPolicy = ref<ReplyPolicy | null>(null)
const replyPolicyBusy = ref(false)
const replyPolicyError = ref('')
const PDD_CUSTOMER_SERVICE_URL = 'https://mms.pinduoduo.com/chat-merchant/index.html#'
let refreshTimer: ReturnType<typeof setInterval> | undefined

const agentStatus = computed(() => bootstrap.value?.agent.runtime_status ?? 'CONNECTING')
const controlledAuto = computed(() => bootstrap.value?.safety.controlled_auto ?? null)
const autoReplyRunning = computed(() => controlledAuto.value?.auto_reply_running === true)
const autoReplyDesired = computed(() => controlledAuto.value?.desired_auto_reply_enabled === true)
const realSendEnabled = computed(() => (
  bootstrap.value?.safety.real_send_enabled === true
  || (
    autoReplyRunning.value
    && controlledAuto.value?.runtime_mode === 'PRODUCTION_AUTO'
    && controlledAuto.value?.production_real_send_enabled === true
    && controlledAuto.value?.controlled_store_auto_enabled === true
    && controlledAuto.value?.kill_switch_enabled === false
  )
))
provide('channelAgentRealSendEnabled', realSendEnabled)
const autoControlAvailable = computed(() => controlledAuto.value?.control_available === true)
const autoRepairNeeded = computed(() => {
  const runtime = controlledAuto.value
  return !runtime?.control_available
    || Boolean(runtime.control_error_code)
    || !runtime.ai_cs_store_id
    || !runtime.platform_store_id
    || !['AUTO_LOW_RISK', 'AUTO_ALL_MESSAGES_V1'].includes(runtime.policy_mode)
})
const autoControlLabel = computed(() => {
  if (autoReplyRunning.value) return '当前会话自动回复中'
  if (autoControlAvailable.value) return '当前会话自动回复已暂停'
  if (controlledAuto.value?.supervisor_active) {
    if (controlledAuto.value.supervisor_state === 'WAITING_FOR_CURRENT_PDD_CONVERSATION') return '等待当前会话'
    if (controlledAuto.value.supervisor_state === 'RECOVERING_AUTO_COMPONENTS') return '当前会话AUTO恢复中'
    if (controlledAuto.value.supervisor_state === 'STARTING') return '自动回复启动中'
  }
  return autoReplyDesired.value ? '当前会话AUTO待修复' : '自动回复待启动'
})
const autoControlTitle = computed(() => {
  if (!autoControlAvailable.value) return '当前页AUTO尚未就绪；不会自动切换其他买家会话'
  return autoReplyRunning.value
    ? '点击暂停当前人工打开会话的新消息自动回复与真实发送'
    : '点击核对当前店铺和当前会话后恢复自动回复；不会跳转其他会话'
})
const browserStatus = computed(() => bootstrap.value?.browser.status ?? 'STOPPED')
const realMessageObservationEnabled = computed(() => (
  bootstrap.value?.browser.real_pdd_message_observation_enabled === true
))
const messageSourceLabel = computed(() => {
  const source = bootstrap.value?.browser.message_source
  if (source === 'REAL_PDD') return '真实消息读取 已启用'
  if (source === 'OFFLINE_REPLAY') return '消息源 离线回放'
  return '真实消息读取 未启用'
})
const observerRestartLabel = computed(() => {
  if (restartingObserver.value) return '正在恢复…'
  return realMessageObservationEnabled.value
    ? '重新开始30分钟观察'
    : '当前为离线回放'
})
const pddLabel = computed(() => {
  const login = bootstrap.value?.browser.pdd_login_state
  if (login === 'CUSTOMER_SERVICE_READY') return '客服工作台已就绪'
  if (login === 'PDD_LOGIN_SUCCESS' || login === 'LOGIN_SUCCESS' || login === 'OPENING_CUSTOMER_SERVICE') return '已登录'
  if (login === 'WAITING_QR_SCAN' || login === 'PDD_LOGIN_PAGE') return '等待扫码'
  return statusLabel(browserStatus.value)
})
const canOpenPddWindow = computed(() => Boolean(
  bootstrap.value?.browser.pdd_workspace_launch_available
  && ['STOPPED', 'FAILED', 'DEGRADED'].includes(browserStatus.value)
))
const canRefreshPddWorkspace = computed(() => Boolean(
  bootstrap.value?.browser.pdd_workspace_refresh_available
  && !['STOPPED', 'FAILED'].includes(browserStatus.value)
))
const canRestartPddObserver = computed(() => Boolean(
  bootstrap.value?.browser.observer_restart_available
  && bootstrap.value?.browser.observer_status === 'SESSION_LIMIT_REACHED'
  && bootstrap.value?.browser.pdd_login_state === 'CUSTOMER_SERVICE_READY'
))
const authorizedStores = computed(() => bootstrap.value?.binding.authorized_store_ids ?? [])
const storeOptions = computed(() => authorizedStores.value.map((storeCode) => {
  const store = auth.user.value?.stores.find((item) => item.store_code === storeCode)
  const pddBinding = store?.platform_bindings?.find((item) =>
    item.status === 'ACTIVE' && ['pinduoduo', 'pdd'].includes(item.platform.toLowerCase())
  )
  return {
    storeCode,
    pddBinding,
    label: store
      ? `${store.store_name}${pddBinding ? ` · PDD ${pddBinding.platform_store_id}` : '（未绑定PDD）'}`
      : storeCode
  }
}))
const activeStore = computed(() => storeOptions.value.find((item) =>
  item.storeCode === bootstrap.value?.binding.active_store_id
) ?? null)
const activeStoreRecord = computed(() => auth.user.value?.stores.find(
  (store) => store.store_code === bootstrap.value?.binding.active_store_id
) ?? null)
const activeStoreNumericId = computed(() => activeStoreRecord.value?.store_id ?? activeStoreRecord.value?.id ?? null)
const canManageReplyPolicy = computed(() => auth.hasPermission('customer_service.manage'))
const pendingConversationCount = computed(() => (
  conversationCounts.value.NEW
  + conversationCounts.value.PROCESSING
  + conversationCounts.value.WAITING_REPLY
))
const observedStoreOption = computed(() => {
  const observedPlatformStoreId = bootstrap.value?.binding.observed_store_id
  if (!observedPlatformStoreId) return null
  const matches = storeOptions.value.filter((item) =>
    item.pddBinding?.platform_store_id === observedPlatformStoreId
  )
  return matches.length === 1 ? matches[0] : null
})
const storeMismatch = computed(() => {
  const observedPlatformStoreId = bootstrap.value?.binding.observed_store_id
  if (!activeStore.value || !observedPlatformStoreId) return false
  return activeStore.value.pddBinding?.platform_store_id !== observedPlatformStoreId
})

type RuntimeAction = 'REFRESH' | 'OPEN_PDD' | 'REFRESH_WORKSPACE' | 'RESTART_OBSERVER' | 'CONFIRM_STORE'
type RuntimeAlert = {
  title: string
  impact: string
  tone: 'warning' | 'danger' | 'info'
  action: RuntimeAction | null
  actionLabel: string
  testId?: string
  showCopyUrl?: boolean
}

const actionAlert = computed<RuntimeAlert | null>(() => {
  if (error.value) return {
    title: 'Agent 连接失败', impact: '暂时无法确认实时运行状态；AI 不会自动发送。',
    tone: 'danger', action: 'REFRESH', actionLabel: '重新连接'
  }
  if (!activeStore.value) return {
    title: '店铺尚未确认', impact: '无法安全接收或处理店铺会话。',
    tone: 'danger', action: null, actionLabel: ''
  }
  if (storeMismatch.value) return {
    title: '页面店铺与当前店铺不一致', impact: '消息读取已暂停，请先核对当前 PDD 页面。',
    tone: 'danger', action: 'CONFIRM_STORE', actionLabel: '人工确认', testId: 'confirm-observed-store'
  }
  if (!['ONLINE', 'RUNNING', 'READY', 'OPENED'].includes(agentStatus.value)) return {
    title: 'Agent 运行状态异常', impact: '实时会话能力可能不可用，请刷新后检查。',
    tone: 'danger', action: 'REFRESH', actionLabel: '刷新状态'
  }
  if (canOpenPddWindow.value) return {
    title: 'PDD 专属窗口未启动', impact: '当前不会接收真实客户消息。',
    tone: 'warning', action: 'OPEN_PDD', actionLabel: '启动 PDD 窗口', testId: 'open-pdd-window'
  }
  if (['FAILED', 'STOPPED', 'DEGRADED'].includes(browserStatus.value)) return {
    title: 'PDD 专属窗口状态异常', impact: '当前不会可靠读取客户消息。',
    tone: 'danger', action: 'REFRESH', actionLabel: '刷新状态'
  }
  const login = bootstrap.value?.browser.pdd_login_state
  if (login === 'WAITING_QR_SCAN' || login === 'PDD_LOGIN_PAGE') return {
    title: '等待扫码登录', impact: '请在 PDD 专属 Edge 中完成扫码，系统不会代替登录。',
    tone: 'warning', action: null, actionLabel: ''
  }
  if (login !== 'CUSTOMER_SERVICE_READY' && canRefreshPddWorkspace.value) return {
    title: '尚未识别客服工作台', impact: '当前不会读取会话；请打开客服页面后重新识别。',
    tone: 'warning', action: 'REFRESH_WORKSPACE', actionLabel: '重新识别',
    testId: 'refresh-pdd-workspace', showCopyUrl: true
  }
  if (login !== 'CUSTOMER_SERVICE_READY') return {
    title: 'PDD 登录或页面状态异常', impact: '当前不会读取真实客户消息，请检查专属窗口。',
    tone: 'danger', action: 'REFRESH', actionLabel: '刷新状态'
  }
  if (canRestartPddObserver.value && realMessageObservationEnabled.value) return {
    title: '只读观察会话已结束', impact: '新客户消息暂时不会进入工作台。',
    tone: 'warning', action: 'RESTART_OBSERVER', actionLabel: '恢复只读观察', testId: 'restart-pdd-observer'
  }
  if (!realMessageObservationEnabled.value) return {
    title: '当前未读取真实消息',
    impact: bootstrap.value?.browser.message_source === 'OFFLINE_REPLAY'
      ? '当前为离线回放，不会接收真实客户消息。'
      : '请在运行详情中检查消息读取配置。',
    tone: 'info', action: null, actionLabel: ''
  }
  return null
})

const overallStatus = computed(() => {
  if (error.value || ['FAILED', 'STOPPED'].includes(agentStatus.value)) {
    return { label: '离线', tone: 'offline' }
  }
  if (actionAlert.value) return { label: '需处理', tone: 'attention' }
  return { label: '就绪', tone: 'healthy' }
})

const runtimeActionBusy = computed(() => (
  loading.value || openingPdd.value || refreshingPdd.value || restartingObserver.value
    || autoToggleBusy.value || autoRepairBusy.value
))

async function repairControlledAuto() {
  if (autoRepairBusy.value) return
  autoRepairBusy.value = true
  try {
    await requestChannelAgentControlledAutoRepair()
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 250))
      await refresh()
      if (!autoRepairNeeded.value && autoControlAvailable.value) break
    }
    if (autoRepairNeeded.value || !autoControlAvailable.value) {
      throw new Error(controlledAuto.value?.control_error_code || 'CONTROLLED_AUTO_REPAIR_TIMEOUT')
    }
    ElMessage.success('自动回复已修复并保持暂停，请确认后再点击开启。')
  } catch (repairError) {
    const code = repairError instanceof Error ? repairError.message : ''
    ElMessage.error(code.includes('SCOPE') || code.includes('READY')
      ? '修复失败：请确认已登录当前店铺、工作台和真实消息读取均正常。'
      : '一键修复失败，请查看运行详情后重试。')
  } finally {
    autoRepairBusy.value = false
  }
}

async function toggleControlledAuto() {
  if (autoToggleBusy.value || !autoControlAvailable.value) return
  const target = !autoReplyRunning.value
  autoToggleBusy.value = true
  try {
    await requestChannelAgentControlledAutoToggle(target)
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 250))
      await refresh()
      if (autoReplyRunning.value === target) break
      if (controlledAuto.value?.control_error_code) {
        throw new Error(controlledAuto.value.control_error_code)
      }
    }
    if (autoReplyRunning.value !== target) throw new Error('CONTROLLED_AUTO_TOGGLE_TIMEOUT')
    ElMessage.success(target ? '自动回复已恢复运行。' : '自动回复已暂停，不再为新消息真实发送。')
  } catch (toggleError) {
    const code = toggleError instanceof Error ? toggleError.message : ''
    ElMessage.error(code.includes('SCOPE') || code.includes('READY')
      ? '切换失败：当前店铺、登录页面或观察状态尚未通过核对。'
      : '自动回复模式切换失败，请查看运行详情。')
  } finally {
    autoToggleBusy.value = false
  }
}

const desktopAssociationLabel = computed(() => {
  if (runtimeDetailsLoading.value && !desktopAgentStatus.value) return '检查中'
  const state = desktopAgentStatus.value?.associationState
  if (!state) return runtimeDetailsError.value ? '检查失败' : '未检查'
  if (state !== 'READY') return {
    BINDING_REQUIRED: '待绑定', ACTIVATION_REQUIRED: '待激活', STORE_MISMATCH: '店铺不匹配',
    MULTIPLE_MATCHES: '多设备冲突', DISABLED: '已停用'
  }[state] ?? '状态异常'
  return { ONLINE: '设备在线', DEGRADED: '连接降级', OFFLINE: '设备离线' }[
    desktopAgentStatus.value?.agent?.onlineStatus ?? 'OFFLINE'
  ]
})

const desktopHeartbeatLabel = computed(() => {
  const value = desktopAgentStatus.value?.agent?.lastHeartbeat
  if (!value) return '尚无心跳'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? '时间无效'
    : parsed.toLocaleString('zh-CN', { hour12: false })
})

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    ONLINE: '在线', RUNNING: '运行中', READY: '就绪', OPENED: '已打开',
    STARTING: '启动中', CONNECTING: '连接中', DEGRADED: '需检查',
    FAILED: '异常', STOPPED: '已停止'
  }
  return labels[value] ?? '待连接'
}

async function refresh() {
  loading.value = true
  try {
    bootstrap.value = await fetchChannelAgentBootstrap()
    selectedStore.value = bootstrap.value.binding.active_store_id ?? ''
    error.value = false
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function loadRuntimeSupplementals() {
  if (!activeStoreNumericId.value) return
  runtimeDetailsLoading.value = true
  runtimeDetailsError.value = ''
  replyPolicyError.value = ''
  const [desktopResult, policyResult] = await Promise.allSettled([
    desktopAgentClient.getStatus(activeStoreNumericId.value),
    offlineReplyControlClient.getPolicy(activeStoreNumericId.value)
  ])
  if (desktopResult.status === 'fulfilled') desktopAgentStatus.value = desktopResult.value
  else runtimeDetailsError.value = desktopResult.reason instanceof Error
    ? desktopResult.reason.message
    : '客服连接程序状态检查失败。'
  if (policyResult.status === 'fulfilled') replyPolicy.value = policyResult.value
  else replyPolicyError.value = policyResult.reason instanceof Error
    ? policyResult.reason.message
    : '回复策略暂时不可用。'
  runtimeDetailsLoading.value = false
}

function openRuntimeDetails() {
  moreMenuOpen.value = false
  runtimeDetailsOpen.value = true
  void loadRuntimeSupplementals()
}

async function refreshRuntimeDetails() {
  await refresh()
  await loadRuntimeSupplementals()
}

async function changeReplyPolicy(event: Event) {
  const select = event.target as HTMLSelectElement
  const mode = select.value as ReplyPolicyMode
  if (!activeStoreNumericId.value || mode === replyPolicy.value?.mode) return
  const confirmed = window.confirm(
    mode === 'AUTO_LOW_RISK'
      ? '确认启用 AUTO_LOW_RISK？仅通过质量门的低风险回复会自动进入执行准备，真实发送仍保持关闭。'
      : '确认切换回 MANUAL_CONFIRM？此后每条回复都必须人工确认后才能进入执行准备。'
  )
  if (!confirmed) {
    select.value = replyPolicy.value?.mode ?? 'MANUAL_CONFIRM'
    return
  }
  replyPolicyBusy.value = true
  replyPolicyError.value = ''
  try {
    replyPolicy.value = await offlineReplyControlClient.setPolicy({
      storeId: activeStoreNumericId.value,
      mode,
      expectedRevision: replyPolicy.value?.revision ?? null
    })
    ElMessage.success(`回复策略已切换为 ${mode}；真实发送状态未改变。`)
  } catch (policyError) {
    replyPolicyError.value = policyError instanceof Error ? policyError.message : '回复策略切换失败。'
    select.value = replyPolicy.value?.mode ?? 'MANUAL_CONFIRM'
  } finally {
    replyPolicyBusy.value = false
  }
}

async function copyPddUrl() {
  try {
    await navigator.clipboard.writeText(PDD_CUSTOMER_SERVICE_URL)
    ElMessage.success('客服工作台地址已复制')
  } catch {
    ElMessage.warning('无法自动复制，请在运行详情中手动选择地址。')
  }
}

async function runAlertAction() {
  if (actionAlert.value?.action === 'OPEN_PDD') return openPddWindow()
  if (actionAlert.value?.action === 'REFRESH_WORKSPACE') return refreshPddWorkspace()
  if (actionAlert.value?.action === 'RESTART_OBSERVER') return restartPddObserver()
  if (actionAlert.value?.action === 'CONFIRM_STORE') return confirmObservedStore()
  await refresh()
}

async function confirmObservedStore() {
  const target = observedStoreOption.value
  const observedPlatformStoreId = bootstrap.value?.binding.observed_store_id
  if (!target || !observedPlatformStoreId) {
    ElMessage.error('页面店铺号无法唯一对应到已授权店铺，不能人工放行。')
    return
  }
  try {
    await ElMessageBox.confirm(
      `页面识别到 PDD 店铺号 ${observedPlatformStoreId}，对应“${target.label}”。请确认当前客服页面确实属于该店铺。`,
      '人工确认页面店铺',
      { confirmButtonText: '确认正确', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  switchingStore.value = true
  try {
    await selectChannelAgentActiveStore(target.storeCode)
    await refresh()
    ElMessage.success('已按 PDD 店铺号与 AI-CS 店铺绑定完成确认。')
  } catch {
    ElMessage.error('人工确认被安全策略拒绝，请重新识别页面后再试。')
  } finally {
    switchingStore.value = false
  }
}

function refreshFromMenu() {
  moreMenuOpen.value = false
  void refresh()
}

function requestStopFromMenu() {
  moreMenuOpen.value = false
  void requestStop()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  if (runtimeDetailsOpen.value) runtimeDetailsOpen.value = false
  else moreMenuOpen.value = false
}

async function openPddWindow() {
  if (openingPdd.value) return
  openingPdd.value = true
  try {
    const result = await requestChannelAgentPddWindowOpen()
    if (bootstrap.value) {
      bootstrap.value.browser.status = result.browser_status
      bootstrap.value.browser.pdd_login_state = result.pdd_login_state
    }
    ElMessage.success('PDD 专属 Edge 已启动，请在新窗口中人工登录。')
  } catch {
    ElMessage.error('PDD 专属窗口启动失败，请确认 Microsoft Edge 可用后重试。')
  } finally {
    openingPdd.value = false
  }
}

async function refreshPddWorkspace() {
  if (refreshingPdd.value) return
  refreshingPdd.value = true
  try {
    const result = await requestChannelAgentPddWorkspaceRefresh()
    if (bootstrap.value) {
      bootstrap.value.browser.status = result.browser_status
      bootstrap.value.browser.pdd_login_state = result.pdd_login_state
    }
    if (result.pdd_login_state === 'CUSTOMER_SERVICE_READY') {
      ElMessage.success('已识别到拼多多客服工作台。')
    } else {
      ElMessage.warning('尚未识别到客服工作台，请确认当前标签页地址后重试。')
    }
  } catch {
    ElMessage.error('客服工作台识别失败；未启动读取或发送。')
  } finally {
    refreshingPdd.value = false
  }
}

async function restartPddObserver() {
  if (restartingObserver.value) return
  restartingObserver.value = true
  try {
    await requestChannelAgentPddObserverRestart()
    ElMessage.success('已申请重新开始一个30分钟只读观察会话。')
    await refresh()
  } catch {
    ElMessage.error('观察会话未恢复，请确认客服工作台与Agent身份状态。')
  } finally {
    restartingObserver.value = false
  }
}

async function confirmStoreSelection() {
  const target = selectedStore.value
  const previous = bootstrap.value?.binding.active_store_id ?? ''
  if (!target || target === previous) return
  const targetOption = storeOptions.value.find((item) => item.storeCode === target)
  if (!targetOption?.pddBinding) {
    selectedStore.value = previous
    ElMessage.error('该店铺尚未绑定有效的 PDD 店铺号，不能作为当前客服店铺。')
    return
  }
  try {
    await ElMessageBox.confirm(
      `请先确认 PDD 当前页面确实属于“${targetOption.label}”。切换时不能存在待审核、执行中或结果未知的任务。`,
      '确认当前工作店铺',
      { confirmButtonText: '确认选择', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    selectedStore.value = previous
    return
  }
  switchingStore.value = true
  try {
    await selectChannelAgentActiveStore(target)
    await refresh()
    desktopAgentStatus.value = null
    replyPolicy.value = null
    if (runtimeDetailsOpen.value) await loadRuntimeSupplementals()
    ElMessage.success('当前工作店铺已切换')
  } catch {
    selectedStore.value = previous
    ElMessage.error('切换被安全策略拒绝。请核对 PDD 当前店铺并处理未完成任务。')
  } finally {
    switchingStore.value = false
  }
}

async function requestStop() {
  try {
    await ElMessageBox.confirm(
      '安全退出会停止 Channel Agent；PDD 浏览器将按运行策略关闭。平时关闭本窗口只会隐藏到托盘。',
      '确认安全退出',
      { confirmButtonText: '确认退出', cancelButtonText: '继续运行', type: 'warning' }
    )
  } catch {
    return
  }
  await requestChannelAgentSafeStop()
  window.close()
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  void refresh()
  refreshTimer = setInterval(() => void refresh(), 5000)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.agent-desktop-shell{display:flex;flex-direction:column;height:100vh;min-height:560px;background:#edf4ef;color:#153529;overflow:hidden}
.agent-desktop-bar{z-index:20;display:flex;align-items:center;gap:18px;min-height:56px;padding:7px 14px;border-bottom:1px solid #cfe0d6;background:#fff}
.brand{display:flex;flex:0 0 auto;align-items:center;gap:9px}.brand-mark{display:grid;width:34px;height:34px;place-items:center;border-radius:10px;background:linear-gradient(135deg,#2f8b61,#72d7bd);color:#fff;font-size:13px;font-weight:900}.brand strong,.brand small{display:block}.brand strong{font-size:14px}.brand small{margin-top:1px;color:#72877c;font-size:9px}
.runtime-summary{display:flex;min-width:0;align-items:center;gap:9px;margin-left:auto}.runtime-summary span{display:flex;align-items:center;gap:6px;color:#587064;font-size:10px;white-space:nowrap}.runtime-summary i{width:8px;height:8px;border-radius:50%;background:#d99b2b}.runtime-summary .healthy i{background:#29a875}.runtime-summary .offline{color:#a13c30}.runtime-summary .offline i{background:#c8584b}.runtime-summary .attention{color:#936108}.overall-status{padding:6px 8px;border-radius:999px;background:#edf3ef;font-weight:900}.overall-status.healthy{color:#25704e;background:#dff2e5}.overall-status.attention{color:#8b5c00;background:#fff1ca}.overall-status.offline{color:#9b382f;background:#ffebe8}
.auto-control-cluster{display:flex;align-items:center;gap:5px}.auto-reply-toggle{display:flex;align-items:center;gap:6px;padding:7px 10px;border:1px solid transparent;border-radius:999px;font-size:10px;font-weight:900;white-space:nowrap;cursor:pointer}.auto-reply-toggle.running{border-color:#a8d6ba;color:#17653f;background:#dff3e6}.auto-reply-toggle.running i{background:#22a66f;box-shadow:0 0 0 3px rgb(34 166 111 / 13%)}.auto-reply-toggle.paused{border-color:#d4dcd7;color:#66766e;background:#f2f5f3}.auto-reply-toggle.paused i{background:#87958e}.auto-reply-toggle:disabled{cursor:not-allowed;opacity:.62}.auto-repair-button{padding:7px 10px;border:1px solid #e1b55a;border-radius:999px;background:#fff6dc;color:#8a5a00;font-size:10px;font-weight:900;white-space:nowrap;cursor:pointer}.auto-repair-button:hover{background:#ffedb8}.auto-repair-button:disabled{cursor:wait;opacity:.62}
.runtime-summary select{width:min(220px,24vw);padding:7px 28px 7px 9px;border:1px solid #bcd2c5;border-radius:8px;background:#fff;color:#245a43;font-size:10px}.store-summary{max-width:240px;overflow:hidden;text-overflow:ellipsis}.pending-summary{padding:6px 8px;border-radius:8px;background:#f1f7f3}.pending-summary strong{color:#206744;font-size:12px}
.operator{display:flex;flex:0 0 auto;align-items:center;gap:7px;padding-left:12px;border-left:1px solid #dce8e0}.operator button,.action-alert button,.section-heading button,.workspace-url button,.drawer-actions button{padding:7px 9px;border:1px solid #bcd2c5;border-radius:8px;background:#fff;color:#245a43;font-size:10px;cursor:pointer}.operator button:disabled,.action-alert button:disabled,.runtime-drawer button:disabled{cursor:wait;opacity:.55}.more-wrap{position:relative}.operator .more-button{width:34px;padding:7px 0;font-weight:900;letter-spacing:.08em}.more-menu{position:absolute;top:42px;right:0;z-index:50;display:grid;width:170px;padding:7px;border:1px solid #cadcd0;border-radius:11px;background:#fff;box-shadow:0 16px 45px rgb(28 62 41 / 18%)}.more-menu .operator-identity{display:grid;gap:2px;padding:7px 8px 9px;border-bottom:1px solid #e3ece6}.operator-identity small{color:#788b81;font-size:8px}.operator-identity strong{overflow:hidden;text-overflow:ellipsis;font-size:10px;white-space:nowrap}.more-menu button{margin-top:5px;text-align:left}.more-menu .danger{border-color:#e2b8b2;color:#a13c30;background:#fff7f6}
.action-alert{display:flex;align-items:center;gap:9px;min-height:38px;padding:5px 14px;border-bottom:1px solid #e3c57e;background:#fff7e3;color:#79520e}.action-alert>div{display:flex;min-width:0;align-items:center;gap:8px;margin-right:auto}.action-alert strong{font-size:11px;white-space:nowrap}.action-alert span{overflow:hidden;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.action-alert.danger{border-color:#e7b7b2;background:#fff0ee;color:#943a30}.action-alert.info{border-color:#b9d2df;background:#eef7fb;color:#356b87}.action-alert .subtle{border-color:transparent;background:transparent}
.agent-desktop-content{min-width:0;min-height:0;flex:1;padding:8px;overflow:hidden}
.runtime-drawer-backdrop{position:fixed;inset:0;z-index:2000;display:flex;justify-content:flex-end;background:rgb(23 45 31 / 38%);backdrop-filter:blur(2px)}.runtime-drawer{box-sizing:border-box;width:min(440px,94vw);height:100%;padding:16px;overflow:auto;background:#f8fcf9;box-shadow:-20px 0 60px rgb(20 55 35 / 24%)}.runtime-drawer>header{display:flex;align-items:flex-start;justify-content:space-between;padding:2px 2px 14px;border-bottom:1px solid #d4e2d8}.runtime-drawer>header small{color:#4c8065;font-size:9px;font-weight:900;letter-spacing:.12em}.runtime-drawer>header h2{margin:4px 0 0;font-size:20px}.runtime-drawer>header button{width:32px;height:32px;border:1px solid #cadcd0;border-radius:9px;background:#fff;color:#597065;font-size:20px;cursor:pointer}.detail-section{display:grid;gap:10px;margin-top:13px;padding:13px;border:1px solid #c9ddcd;border-radius:12px;background:#fff}.detail-section>strong,.section-heading strong{font-size:12px}.section-heading{display:flex;align-items:center;justify-content:space-between}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:0}.detail-grid div{min-width:0;padding:8px;border-radius:8px;background:#f1f7f3}.detail-grid dt{color:#73867a;font-size:8px}.detail-grid dd{margin:4px 0 0;overflow:hidden;color:#284b38;font-size:10px;font-weight:800;text-overflow:ellipsis;white-space:nowrap}.detail-grid dd.healthy{color:#25704e}.detail-grid dd.attention{color:#8b5c00}.detail-grid dd.offline{color:#a13c30}.policy-control{display:grid;gap:5px;color:#61766a;font-size:9px}.policy-control select{padding:8px;border:1px solid #bed3c4;border-radius:8px;background:#fff;color:#245a43;font-size:10px}.controlled-policy-fact{display:grid;gap:5px;padding:9px;border-radius:9px;background:#edf7f0}.controlled-policy-fact>span{color:#60766a;font-size:9px}.controlled-policy-fact>strong{color:#1f6946;font-size:11px}.controlled-policy-fact>small{color:#6d8175;font-size:8px;line-height:1.5}.safety-facts{display:flex;align-items:center;justify-content:space-between;gap:8px}.safety-facts span{color:#446151;font-size:9px}.safety-facts strong{padding:5px 8px;border-radius:999px;color:#963d46;background:#fff0f1;font-size:9px}.detail-section>small{color:#6d8175;font-size:8px;line-height:1.5}.detail-error{margin:0;color:#aa4650;font-size:9px}.workspace-url{display:flex;gap:7px;align-items:center}.workspace-url code{min-width:0;flex:1;padding:8px;overflow:hidden;border-radius:7px;background:#eff6f1;color:#256345;font-size:9px;text-overflow:ellipsis;white-space:nowrap;user-select:all}.drawer-actions{display:flex;flex-wrap:wrap;gap:7px}
@media(max-width:900px){.agent-desktop-bar{gap:8px;padding:7px 9px}.brand small{display:none}.runtime-summary{gap:6px}.runtime-summary select{width:170px}.pending-summary{display:none}.operator{padding-left:6px}.detail-button{font-size:0}.detail-button::after{content:'详情';font-size:10px}.action-alert span{display:none}}
</style>
