<template>
  <div class="agent-desktop-shell" data-testid="agent-desktop-shell">
    <header class="agent-desktop-bar">
      <div class="brand">
        <span class="brand-mark">AI</span>
        <div><strong>AI 客服助手</strong><small>Channel Agent 桌面端</small></div>
      </div>

      <div class="runtime-summary" aria-label="客户端运行状态">
        <span :class="statusClass(agentStatus)"><i />Agent {{ statusLabel(agentStatus) }}</span>
        <span :class="statusClass(browserStatus)"><i />PDD {{ pddLabel }}</span>
        <span
          :class="realMessageObservationEnabled ? 'healthy' : 'attention'"
          data-testid="message-source-status"
        ><i />{{ messageSourceLabel }}</span>
        <button
          v-if="canOpenPddWindow"
          type="button"
          class="pdd-launch"
          :disabled="openingPdd"
          data-testid="open-pdd-window"
          @click="openPddWindow"
        >{{ openingPdd ? '正在启动…' : '启动 PDD 专属窗口' }}</button>
        <button
          v-if="canRefreshPddWorkspace"
          type="button"
          class="pdd-launch"
          :disabled="refreshingPdd"
          data-testid="refresh-pdd-workspace"
          @click="refreshPddWorkspace"
        >{{ refreshingPdd ? '正在识别…' : '我已进入客服工作台，重新识别' }}</button>
        <button
          v-if="canRestartPddObserver"
          type="button"
          class="pdd-launch"
          :disabled="restartingObserver || !realMessageObservationEnabled"
          data-testid="restart-pdd-observer"
          @click="restartPddObserver"
        >{{ observerRestartLabel }}</button>
        <span :class="activeStore ? 'healthy' : 'attention'" data-testid="active-store-status"><i />{{ storeLabel }}</span>
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
      </div>

      <div class="operator">
        <div><small>当前客服</small><strong>{{ auth.user.value?.display_name ?? '未登录' }}</strong></div>
        <button type="button" :disabled="loading" @click="refresh">刷新状态</button>
        <button type="button" class="danger" @click="requestStop">安全退出</button>
      </div>
    </header>

    <div v-if="canRefreshPddWorkspace" class="pdd-workspace-guide" data-testid="pdd-workspace-guide">
      <strong>客服工作台地址</strong>
      <span>扫码后若停在商家首页，请在当前 PDD 专属 Edge 中新建标签页并输入：</span>
      <code>{{ PDD_CUSTOMER_SERVICE_URL }}</code>
    </div>

    <div v-if="error" class="agent-warning" role="status">
      本地 Agent 暂时无法连接。AI 建议仍不会自动发送，请从 Windows 托盘检查 Agent 状态。
    </div>
    <div v-else class="safety-strip">
      <strong>人工确认模式</strong>
      <span>AI 只生成建议；只有客服明确确认后，Agent 才允许执行发送。</span>
    </div>

    <main class="agent-desktop-content">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterView } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthSession } from '@/auth/authSession'
import {
  fetchChannelAgentBootstrap,
  requestChannelAgentPddObserverRestart,
  requestChannelAgentPddWorkspaceRefresh,
  requestChannelAgentPddWindowOpen,
  requestChannelAgentSafeStop,
  selectChannelAgentActiveStore,
  type ChannelAgentBootstrap
} from '@/api/channelAgentDesktopClient'

const auth = useAuthSession()
const bootstrap = ref<ChannelAgentBootstrap | null>(null)
const loading = ref(false)
const error = ref(false)
const switchingStore = ref(false)
const openingPdd = ref(false)
const refreshingPdd = ref(false)
const restartingObserver = ref(false)
const selectedStore = ref('')
const PDD_CUSTOMER_SERVICE_URL = 'https://mms.pinduoduo.com/chat-merchant/index.html#'
let refreshTimer: ReturnType<typeof setInterval> | undefined

const agentStatus = computed(() => bootstrap.value?.agent.runtime_status ?? 'CONNECTING')
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
const storeLabel = computed(() => activeStore.value
  ? `当前店铺 ${activeStore.value.label}`
  : authorizedStores.value.length ? '请选择当前工作店铺' : '店铺待绑定')

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    ONLINE: '在线', RUNNING: '运行中', READY: '就绪', OPENED: '已打开',
    STARTING: '启动中', CONNECTING: '连接中', DEGRADED: '需检查',
    FAILED: '异常', STOPPED: '已停止'
  }
  return labels[value] ?? '待连接'
}

function statusClass(value: string) {
  return ['ONLINE', 'RUNNING', 'READY', 'OPENED'].includes(value) ? 'healthy' : 'attention'
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
  void refresh()
  refreshTimer = setInterval(() => void refresh(), 5000)
})
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.agent-desktop-shell{display:grid;grid-template-rows:auto auto minmax(0,1fr);height:100vh;min-height:640px;background:#edf4ef;color:#153529;overflow:hidden}
.agent-desktop-bar{display:flex;align-items:center;gap:24px;min-height:70px;padding:10px 20px;border-bottom:1px solid #cfe0d6;background:#fff}
.brand{display:flex;align-items:center;gap:10px;min-width:230px}.brand-mark{display:grid;width:40px;height:40px;place-items:center;border-radius:12px;background:linear-gradient(135deg,#2f8b61,#72d7bd);color:#fff;font-weight:900}.brand strong,.brand small{display:block}.brand small{margin-top:2px;color:#72877c;font-size:11px}
.runtime-summary{display:flex;align-items:center;gap:14px;margin-left:auto}.runtime-summary span{display:flex;align-items:center;gap:6px;color:#667b70;font-size:12px}.runtime-summary i{width:8px;height:8px;border-radius:50%;background:#d99b2b}.runtime-summary .healthy i{background:#29a875}.runtime-summary .attention{color:#9a6300}
.runtime-summary select{max-width:190px;padding:7px 28px 7px 9px;border:1px solid #bcd2c5;border-radius:8px;background:#fff;color:#245a43;font-size:12px}
.runtime-summary .pdd-launch{padding:6px 10px;border:1px solid #d6a331;border-radius:8px;background:#fff8e7;color:#8b5c00;font-size:12px;cursor:pointer;white-space:nowrap}.runtime-summary .pdd-launch:disabled{cursor:wait;opacity:.65}
.operator{display:flex;align-items:center;gap:10px;padding-left:18px;border-left:1px solid #dce8e0}.operator small,.operator strong{display:block}.operator small{color:#788b81;font-size:10px}.operator strong{max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.operator button{padding:7px 10px;border:1px solid #bcd2c5;border-radius:8px;background:#fff;color:#245a43;cursor:pointer}.operator .danger{border-color:#e2b8b2;color:#a13c30}
.pdd-workspace-guide{display:flex;align-items:center;gap:8px;padding:6px 20px;border-bottom:1px solid #cfe0d6;background:#f4faf6;color:#48695a;font-size:12px}.pdd-workspace-guide strong{color:#245a43;white-space:nowrap}.pdd-workspace-guide code{padding:3px 7px;border:1px solid #c6d9ce;border-radius:6px;background:#fff;color:#175f43;user-select:all}
.safety-strip,.agent-warning{padding:8px 20px;border-bottom:1px solid #e6d5a7;background:#fff8e7;color:#77510a;font-size:12px}.safety-strip strong{margin-right:10px;padding:2px 7px;border-radius:999px;background:#e79c1b;color:#fff}.agent-warning{border-color:#efc5c0;background:#fff0ee;color:#943a30}
.agent-desktop-content{min-width:0;min-height:0;padding:12px;overflow:auto}
@media(max-width:900px){.agent-desktop-bar{gap:10px;padding:8px 12px}.brand{min-width:0}.runtime-summary span:last-child{display:none}.operator>div{display:none}}
</style>
