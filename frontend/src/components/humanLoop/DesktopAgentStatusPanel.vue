<template>
  <section class="desktop-agent-panel" data-testid="desktop-agent-panel">
    <div class="desktop-heading">
      <div>
        <small>客服电脑接入</small>
        <strong>Channel Agent</strong>
      </div>
      <span class="status-pill" :class="statusClass" data-testid="desktop-agent-online-status">
        {{ statusLabel }}
      </span>
      <button type="button" :disabled="loading" data-testid="desktop-agent-refresh" @click="$emit('refresh')">
        {{ loading ? '检查中' : '刷新状态' }}
      </button>
    </div>

    <div class="desktop-association" data-testid="desktop-agent-association">
      <div><small>当前客服</small><strong>{{ userName || '身份未加载' }}</strong></div>
      <div><small>当前设备</small><strong>{{ deviceLabel }}</strong></div>
      <div><small>当前店铺</small><strong>{{ storeName || '店铺未加载' }}</strong></div>
      <div><small>Agent 版本</small><strong>{{ status?.agent?.agentVersion || '—' }}</strong></div>
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
      <label>Agent ID<input v-model.trim="agentId" maxlength="128" autocomplete="off" /></label>
      <label>Device ID<input v-model.trim="deviceId" maxlength="128" autocomplete="off" /></label>
      <button type="submit" :disabled="bindingBusy || !agentId || !deviceId">
        {{ bindingBusy ? '申请中' : '生成一次性绑定码' }}
      </button>
      <p>请从本机 Channel Agent 状态页核对两个标识。授权只覆盖当前账号的已授权店铺。</p>
    </form>

    <div v-if="bindingGrant" class="binding-grant" data-testid="desktop-binding-grant">
      <strong>一次性绑定码</strong>
      <code>{{ bindingGrant.bindingCode }}</code>
      <p>在本机运行 <code>ChannelAgent.exe enroll --binding-code-stdin</code> 并通过隐藏输入粘贴。绑定码不会保存在 AI-CS 页面；有效至 {{ formatTime(bindingGrant.expiresAt) }}，完成后仍需管理员独立激活。</p>
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
}>()

const emit = defineEmits<{
  refresh: []
  bind: [payload: { agentId: string; deviceId: string }]
  'clear-grant': []
}>()

const agentId = ref('')
const deviceId = ref('')

const statusLabel = computed(() => {
  if (props.errorKind === 'server_unreachable' || props.errorKind === 'timeout') return '服务器不可达'
  if (props.errorKind === 'permission_invalid' || props.errorKind === 'authorization_denied') return '权限失效'
  if (props.error) return '状态异常'
  if (!props.status) return props.loading ? '检查中' : '未检查'
  if (props.status.associationState !== 'READY') return {
    BINDING_REQUIRED: '待绑定', ACTIVATION_REQUIRED: '待激活', STORE_MISMATCH: '店铺不匹配',
    MULTIPLE_MATCHES: '多设备冲突', DISABLED: '已停用'
  }[props.status.associationState] ?? '状态异常'
  return { ONLINE: '设备在线', DEGRADED: '连接降级', OFFLINE: 'Agent 离线' }[props.status.agent?.onlineStatus ?? 'OFFLINE']
})

const statusClass = computed(() => {
  if (props.status?.associationState === 'READY' && props.status.agent?.onlineStatus === 'ONLINE' && !props.error) return 'healthy'
  if (props.status?.associationState === 'READY' && props.status.agent?.onlineStatus === 'DEGRADED') return 'warning'
  return props.loading && !props.error ? 'pending' : 'danger'
})

const deviceLabel = computed(() => {
  const agent = props.status?.agent
  if (!agent) return '未关联'
  return agent.deviceName ? `${agent.deviceName} · ${agent.deviceId}` : agent.deviceId
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
  if (state === 'BINDING_REQUIRED') return '当前账号尚未关联客服电脑。请启动本机 Channel Agent，核对标识后申请一次性绑定码。'
  if (state === 'ACTIVATION_REQUIRED') return '设备已绑定，等待管理员在 Channel Agent 中独立核验并激活。'
  if (state === 'STORE_MISMATCH') return '该账号已有设备，但没有覆盖当前店铺；请联系管理员调整 Agent 店铺范围。'
  if (state === 'MULTIPLE_MATCHES') return '发现多个设备同时匹配当前账号与店铺，已停止自动选择。'
  if (state === 'DISABLED') return '该设备绑定已停用，不能继续作为当前客服电脑。'
  if (props.status.agent?.onlineStatus === 'OFFLINE') return 'Agent 已离线。AI 建议仍只供人工参考，渠道侧能力当前不可用。'
  if (props.status.agent?.onlineStatus === 'DEGRADED') return 'Agent 与服务器连接降级，请检查网络后刷新。'
  return '设备、客服身份与当前店铺关联正常。AI 只生成建议，系统不会自动发送。'
})

const noticeTone = computed(() => statusClass.value)

const submitBinding = (): void => {
  if (!agentId.value || !deviceId.value || props.bindingBusy) return
  emit('bind', { agentId: agentId.value, deviceId: deviceId.value })
}
</script>

<style scoped>
.desktop-agent-panel { display: grid; grid-template-columns: minmax(160px, .8fr) minmax(540px, 2.4fr) minmax(240px, 1fr); gap: 14px; align-items: center; padding: 12px 15px; border: 1px solid #293b59; border-radius: 14px; color: #e8effb; background: linear-gradient(110deg, #101b2e, #14233b); box-shadow: 0 14px 34px rgb(8 18 34 / 18%); }
.desktop-heading { display: flex; align-items: center; gap: 8px; }.desktop-heading > div { margin-right: auto; }.desktop-heading small,.desktop-association small { display:block;color:#8193ae;font-size:9px;font-weight:800; }.desktop-heading strong { font-size:13px; }.desktop-heading button,.binding-form button,.binding-grant button { padding:6px 9px;border:1px solid #3d5274;border-radius:8px;color:#dce8fb;background:#192944;font-size:9px;cursor:pointer; }.desktop-heading button:disabled,.binding-form button:disabled { opacity:.45;cursor:not-allowed; }
.status-pill { flex:0 0 auto;padding:5px 7px;border-radius:999px;background:#26344b;color:#a8b8ce;font-size:9px;font-weight:900; }.status-pill.healthy{background:#183a31;color:#79dab2}.status-pill.warning{background:#433719;color:#efd078}.status-pill.danger{background:#47252a;color:#f3a8b0}
.desktop-association { display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px; }.desktop-association div{min-width:0}.desktop-association strong{display:block;margin-top:3px;overflow:hidden;color:#dfe8f6;font-size:9px;text-overflow:ellipsis;white-space:nowrap}
.desktop-notice { margin:0;padding:9px 10px;border-radius:9px;background:#18283f;color:#aebdd1;font-size:9px;line-height:1.45; }.desktop-notice.healthy{background:#163229;color:#86d8b7}.desktop-notice.warning{background:#3d321b;color:#e8ca80}.desktop-notice.danger{background:#402229;color:#efabb2}
.binding-form,.binding-grant{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr auto;gap:8px;align-items:end;padding-top:10px;border-top:1px solid #2a3d5d}.binding-form label{display:grid;gap:4px;color:#aebed6;font-size:9px;font-weight:800}.binding-form input{padding:7px;border:1px solid #3a4e6e;border-radius:7px;outline:none;color:#edf3fc;background:#0d1728}.binding-form p,.binding-grant p{grid-column:1/-1;margin:0;color:#91a1b8;font-size:9px;line-height:1.5}.binding-grant{grid-template-columns:auto minmax(260px,1fr) auto}.binding-grant code{padding:7px 9px;border-radius:7px;color:#ffe197;background:#071221;font-size:11px;letter-spacing:.08em}
@media(max-width:1200px){.desktop-agent-panel{grid-template-columns:1fr}.desktop-association{grid-template-columns:repeat(3,minmax(0,1fr))}.desktop-notice{grid-column:1/-1}}
</style>
