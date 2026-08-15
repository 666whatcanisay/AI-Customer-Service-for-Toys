<template>
  <section class="desktop-agent-panel" :class="`mode-${mode}`" data-testid="desktop-agent-panel">
    <div class="desktop-heading">
      <div>
        <small>客服电脑接入</small>
        <strong>客服连接程序</strong>
      </div>
      <span class="status-pill" :class="statusClass" data-testid="desktop-agent-online-status">
        {{ statusLabel }}
      </span>
      <button type="button" :disabled="loading" data-testid="desktop-agent-refresh" @click="$emit('refresh')">
        {{ loading ? '检查中' : '刷新状态' }}
      </button>
    </div>

    <div v-if="mode !== 'alert'" class="desktop-association" data-testid="desktop-agent-association">
      <div><small>当前客服</small><strong>{{ userName || '身份未加载' }}</strong></div>
      <div><small>当前设备</small><strong>{{ deviceLabel }}</strong></div>
      <div><small>当前店铺</small><strong>{{ storeName || '店铺未加载' }}</strong></div>
      <div><small>程序版本</small><strong>{{ status?.agent?.agentVersion || '—' }}</strong></div>
      <div><small>最后心跳</small><strong>{{ heartbeatLabel }}</strong></div>
    </div>

    <p v-if="notice" class="desktop-notice" :class="noticeTone" data-testid="desktop-agent-notice">
      {{ notice }}
    </p>

    <form
      v-if="canBind && status?.associationState === 'BINDING_REQUIRED'"
      class="binding-form"
      data-testid="desktop-binding-form"
      @submit.prevent="submitBinding"
    >
      <label>连接程序编号<input v-model.trim="agentId" maxlength="128" autocomplete="off" /></label>
      <label>设备编号<input v-model.trim="deviceId" maxlength="128" autocomplete="off" /></label>
      <button type="submit" :disabled="bindingBusy || !agentId || !deviceId">
        {{ bindingBusy ? '申请中' : '生成一次性绑定码' }}
      </button>
      <p>请从本机客服连接程序的状态页核对两个编号。授权只覆盖当前账号负责的店铺。</p>
    </form>

    <div v-if="bindingGrant" class="binding-grant" data-testid="desktop-binding-grant">
      <strong>一次性绑定码</strong>
      <code>{{ bindingGrant.bindingCode }}</code>
      <p>请在本机客服连接程序的“设备绑定”页面输入。绑定码不会保存在此页面；有效至 {{ formatTime(bindingGrant.expiresAt) }}。如看不到设备绑定页面，请联系管理员。</p>
      <button type="button" @click="$emit('clear-grant')">我已完成本机录入</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import type { DesktopAgentStatus, DesktopBindingGrant } from '@/api/desktopAgentTypes'

const props = defineProps<{
  userName: string
  storeName: string
  status: DesktopAgentStatus | null
  error: string
  errorKind: string
  loading: boolean
  bindingBusy: boolean
  bindingGrant: DesktopBindingGrant | null
  canBind: boolean
  mode?: 'full' | 'alert'
}>()

const emit = defineEmits<{
  refresh: []
  bind: [payload: { agentId: string; deviceId: string }]
  'clear-grant': []
}>()

const agentId = ref('')
const deviceId = ref('')
const mode = computed(() => props.mode ?? 'full')

const statusLabel = computed(() => {
  if (props.errorKind === 'server_unreachable' || props.errorKind === 'timeout') return '服务器不可达'
  if (props.errorKind === 'permission_invalid' || props.errorKind === 'authorization_denied') return '权限失效'
  if (props.error) return '状态异常'
  if (!props.status) return props.loading ? '检查中' : '未检查'
  if (props.status.associationState !== 'READY') return {
    BINDING_REQUIRED: '待绑定', ACTIVATION_REQUIRED: '待激活', STORE_MISMATCH: '店铺不匹配',
    MULTIPLE_MATCHES: '多设备冲突', DISABLED: '已停用'
  }[props.status.associationState] ?? '状态异常'
  return { ONLINE: '设备在线', DEGRADED: '连接降级', OFFLINE: '设备离线' }[props.status.agent?.onlineStatus ?? 'OFFLINE']
})

const statusClass = computed(() => {
  if (props.status?.associationState === 'READY' && props.status.agent?.onlineStatus === 'ONLINE' && !props.error) return 'healthy'
  if (props.status?.associationState === 'READY' && props.status.agent?.onlineStatus === 'DEGRADED') return 'warning'
  return props.loading && !props.error ? 'pending' : 'danger'
})

const deviceLabel = computed(() => {
  const agent = props.status?.agent
  if (!agent) return '未关联'
  return agent.deviceName || '已关联设备'
})

const formatTime = (value: string): string => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '时间无效' : parsed.toLocaleString('zh-CN', { hour12: false })
}

const heartbeatLabel = computed(() => {
  const value = props.status?.agent?.lastHeartbeat
  return value ? formatTime(value) : '尚无心跳'
})

const notice = computed(() => {
  if (props.error) return props.error
  if (!props.status) return '正在核对当前账号、设备与店铺关联。'
  const state = props.status.associationState
  if (state === 'BINDING_REQUIRED') return '当前账号尚未关联客服电脑。请启动本机客服连接程序，核对编号后申请一次性绑定码。'
  if (state === 'ACTIVATION_REQUIRED') return '设备已绑定，等待管理员核验并激活。'
  if (state === 'STORE_MISMATCH') return '该账号已有设备，但没有覆盖当前店铺；请联系管理员调整设备的店铺范围。'
  if (state === 'MULTIPLE_MATCHES') return '发现多个设备同时匹配当前账号与店铺，已停止自动选择。'
  if (state === 'DISABLED') return '该设备绑定已停用，不能继续作为当前客服电脑。'
  if (props.status.agent?.onlineStatus === 'OFFLINE') return '客服连接程序已离线。AI 建议仍只供人工参考，当前无法使用渠道连接能力。'
  if (props.status.agent?.onlineStatus === 'DEGRADED') return '客服连接程序与服务器连接不稳定，请检查网络后刷新。'
  return '设备、客服身份与当前店铺关联正常。AI 只生成建议，系统不会自动发送。'
})

const noticeTone = computed(() => statusClass.value)

const submitBinding = (): void => {
  if (!agentId.value || !deviceId.value || props.bindingBusy) return
  emit('bind', { agentId: agentId.value, deviceId: deviceId.value })
}
</script>

<style scoped>
.desktop-agent-panel { display: grid; grid-template-columns: minmax(160px, .8fr) minmax(540px, 2.4fr) minmax(240px, 1fr); gap: 14px; align-items: center; padding: 12px 15px; border: 1px solid var(--workspace-border-strong); border-radius: 14px; color: var(--workspace-text); background: linear-gradient(110deg, #f8fcf8, #e5f3e8); box-shadow: 0 10px 28px rgb(48 95 61 / 10%); }
.desktop-agent-panel.mode-alert { grid-template-columns: minmax(240px, auto) minmax(0, 1fr); gap: 10px; padding: 7px 10px; border-color: #dfbd71; border-radius: 10px; background: var(--workspace-warning-soft); box-shadow: none; }
.mode-alert .desktop-heading > div { display: none; }.mode-alert .desktop-heading { justify-content: flex-start; }.mode-alert .desktop-heading button { order: -1; }.mode-alert .desktop-notice { padding: 5px 7px; background: transparent; }.mode-alert .desktop-notice.danger { color: var(--workspace-danger); }.mode-alert .desktop-notice.warning { color: var(--workspace-warning); }
.desktop-heading { display: flex; align-items: center; gap: 8px; }.desktop-heading > div { margin-right: auto; }.desktop-heading small,.desktop-association small { display:block;color:var(--workspace-muted);font-size:9px;font-weight:800; }.desktop-heading strong { font-size:13px; }.desktop-heading button,.binding-form button,.binding-grant button { padding:6px 9px;border:1px solid var(--workspace-border-strong);border-radius:8px;color:var(--workspace-accent-strong);background:#fff;font-size:9px;cursor:pointer; }.desktop-heading button:disabled,.binding-form button:disabled { opacity:.45;cursor:not-allowed; }
.status-pill { flex:0 0 auto;padding:5px 7px;border-radius:999px;background:#eef1ef;color:#6f7f74;font-size:9px;font-weight:900; }.status-pill.healthy{background:#dcefe1;color:var(--workspace-accent-strong)}.status-pill.warning{background:var(--workspace-warning-soft);color:var(--workspace-warning)}.status-pill.danger{background:var(--workspace-danger-soft);color:var(--workspace-danger)}
.desktop-association { display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px; }.desktop-association div{min-width:0}.desktop-association strong{display:block;margin-top:3px;overflow:hidden;color:var(--workspace-text);font-size:9px;text-overflow:ellipsis;white-space:nowrap}
.desktop-notice { margin:0;padding:9px 10px;border-radius:9px;background:#edf5ef;color:var(--workspace-text-soft);font-size:9px;line-height:1.45; }.desktop-notice.healthy{background:#dcefe1;color:var(--workspace-accent-strong)}.desktop-notice.warning{background:var(--workspace-warning-soft);color:var(--workspace-warning)}.desktop-notice.danger{background:var(--workspace-danger-soft);color:var(--workspace-danger)}
.binding-form,.binding-grant{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr auto;gap:8px;align-items:end;padding-top:10px;border-top:1px solid var(--workspace-border)}.binding-form label{display:grid;gap:4px;color:var(--workspace-text-soft);font-size:9px;font-weight:800}.binding-form input{padding:7px;border:1px solid var(--workspace-border);border-radius:7px;outline:none;color:var(--workspace-text);background:#fff}.binding-form p,.binding-grant p{grid-column:1/-1;margin:0;color:var(--workspace-muted);font-size:9px;line-height:1.5}.binding-grant{grid-template-columns:auto minmax(260px,1fr) auto}.binding-grant code{padding:7px 9px;border-radius:7px;color:#6e5119;background:#fff2c9;font-size:11px;letter-spacing:.08em}
@media(max-width:1200px){.desktop-agent-panel{grid-template-columns:1fr}.desktop-association{grid-template-columns:repeat(3,minmax(0,1fr))}.desktop-notice{grid-column:1/-1}}
</style>
