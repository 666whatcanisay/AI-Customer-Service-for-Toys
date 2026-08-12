<template>
  <aside class="conversation-center" aria-label="会话中心" data-testid="conversation-center">
    <header>
      <div>
        <p>客户消息</p>
        <h2>会话列表</h2>
      </div>
      <span class="agent-status" :class="`status-${agentStatus.toLowerCase()}`" data-testid="agent-status">
        {{ AGENT_STATUS_LABELS[agentStatus] }}
      </span>
    </header>

    <section class="presence-controls" aria-label="客服状态">
      <button
        type="button"
        :class="{ active: agentStatus !== 'OFFLINE' }"
        data-testid="agent-online"
        @click="$emit('availability', true)"
      >上线</button>
      <button
        type="button"
        :class="{ active: agentStatus === 'OFFLINE' }"
        data-testid="agent-offline"
        @click="$emit('availability', false)"
      >离线</button>
      <small>处理中状态由当前会话自动计算。</small>
    </section>

    <div class="source-notice">
      <strong>受控人工会话</strong>
      <span>当前未连接电商平台消息通道；请使用客户代号，消息只保留在当前页面内存。</span>
    </div>

    <section class="queue-toolbar">
      <label for="conversation-status-filter">队列</label>
      <select id="conversation-status-filter" v-model="statusFilter" data-testid="conversation-status-filter">
        <option value="ALL">全部（{{ conversations.length }}）</option>
        <option v-for="status in CONVERSATION_STATUSES" :key="status" :value="status">
          {{ CONVERSATION_STATUS_LABELS[status] }}（{{ conversationCounts[status] }}）
        </option>
      </select>
    </section>

    <div class="conversation-list">
      <button
        v-for="conversation in filteredConversations"
        :key="conversation.conversationId"
        type="button"
        class="conversation-item"
        :class="{ active: conversation.conversationId === activeConversationId }"
        :data-testid="`conversation-${conversation.conversationId}`"
        @click="$emit('select', conversation.conversationId)"
      >
        <span class="avatar">{{ conversation.customerLabel.slice(-2) }}</span>
        <span class="conversation-copy">
          <span class="conversation-title">
            <strong>{{ conversation.customerLabel }}</strong>
            <time>{{ timeLabel(conversation.messages.at(-1)?.receivedAt) }}</time>
          </span>
          <span class="message-preview">{{ conversation.messages.at(-1)?.content }}</span>
          <span class="conversation-meta">
            <em>{{ sourceLabel(conversation.source) }}</em>
            <span v-if="conversation.processingStage" class="processing-stage">
              {{ processingStageLabel(conversation.processingStage) }}
            </span>
            <b :class="`conversation-${conversation.status.toLowerCase()}`">
              {{ CONVERSATION_STATUS_LABELS[conversation.status] }}
            </b>
            <i v-if="conversation.unreadCount > 0">{{ conversation.unreadCount }}</i>
          </span>
        </span>
      </button>
      <div v-if="filteredConversations.length === 0" class="conversation-empty" data-testid="conversation-empty">
        当前队列没有会话。可在下方人工录入一条去标识化消息。
      </div>
    </div>

    <form class="manual-message-form" data-testid="manual-message-form" @submit.prevent="submitManualMessage">
      <div class="intake-mode">
        <button type="button" :class="{ active: intakeMode === 'APPEND' }" :disabled="!activeConversationId" @click="intakeMode = 'APPEND'">追加当前</button>
        <button type="button" :class="{ active: intakeMode === 'NEW' }" @click="intakeMode = 'NEW'">新建会话</button>
      </div>
      <label v-if="intakeMode === 'NEW'" for="manual-customer-label">客户代号</label>
      <input
        v-if="intakeMode === 'NEW'"
        id="manual-customer-label"
        v-model="customerLabel"
        maxlength="32"
        placeholder="例如：客户 A01（不要填写姓名）"
      />
      <label for="manual-message">人工录入客户消息</label>
      <textarea
        id="manual-message"
        v-model="manualMessage"
        rows="3"
        maxlength="300"
        placeholder="新消息会让当前回复草稿自动失效"
      />
      <button
        type="submit"
        :disabled="agentStatus === 'OFFLINE' || !manualMessage.trim() || (intakeMode === 'APPEND' ? !activeConversationId : !customerLabel.trim())"
      >
        {{ intakeMode === 'NEW' ? '创建并接收' : '接收新消息' }}
      </button>
    </form>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { WorkspaceConversation } from '@/stores/humanLoopWorkspace'
import type { ChannelMessageSource } from '@/workspace/channelMessageAdapter'
import {
  AGENT_STATUS_LABELS,
  CONVERSATION_STATUSES,
  CONVERSATION_STATUS_LABELS,
  type AgentStatus,
  type ConversationStatus
} from '@/workspace/customerSession'

const props = defineProps<{
  conversations: WorkspaceConversation[]
  activeConversationId: string
  agentStatus: AgentStatus
  conversationCounts: Record<ConversationStatus, number>
}>()

const emit = defineEmits<{
  select: [conversationId: string]
  availability: [online: boolean]
  manualMessage: [payload: { conversationId: string | null; customerLabel: string; content: string }]
}>()

const statusFilter = ref<'ALL' | ConversationStatus>('ALL')
const intakeMode = ref<'APPEND' | 'NEW'>(props.activeConversationId ? 'APPEND' : 'NEW')
const customerLabel = ref('')
const manualMessage = ref('')

const filteredConversations = computed(() => statusFilter.value === 'ALL'
  ? props.conversations
  : props.conversations.filter((item) => item.status === statusFilter.value))

watch(() => props.activeConversationId, (value) => {
  intakeMode.value = value ? 'APPEND' : 'NEW'
})

const submitManualMessage = () => {
  const content = manualMessage.value.trim()
  const label = customerLabel.value.trim()
  if (!content || props.agentStatus === 'OFFLINE') return
  if (intakeMode.value === 'NEW' && !label) return
  emit('manualMessage', {
    conversationId: intakeMode.value === 'APPEND' ? props.activeConversationId : null,
    customerLabel: label,
    content
  })
  manualMessage.value = ''
  if (intakeMode.value === 'NEW') customerLabel.value = ''
}

const sourceLabel = (source: ChannelMessageSource): string => {
  if (source === 'MANUAL') return '人工录入'
  if (source === 'VALIDATION_FIXTURE') return '验收数据'
  return '客服连接程序'
}

const processingStageLabel = (stage: string): string => ({
  READ: '已读取',
  BUFFERED: '消息合并',
  AI_GENERATING: 'AI 生成',
  QUALITY_GATE: '质量检查',
  WAITING_APPROVAL: '等待确认',
  EXECUTION_PREPARED: '执行已准备',
  FAILED: '处理异常'
}[stage] ?? stage)

const timeLabel = (value?: string): string => {
  if (!value) return '--:--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--:--'
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(date)
}
</script>

<style scoped>
.conversation-center { display: grid; grid-template-rows: auto auto auto auto minmax(0, 1fr) auto; min-width: 0; min-height: 0; border-right: 1px solid var(--workspace-border); color: var(--workspace-text); background: var(--workspace-panel-soft); }
header { display: flex; align-items: center; justify-content: space-between; padding: 18px 16px 10px; }
header p { margin: 0 0 5px; color: var(--workspace-accent); font-size: 9px; font-weight: 800; letter-spacing: .14em; }
header h2 { margin: 0; color: var(--workspace-text); font-size: 18px; }
.agent-status { padding: 6px 9px; border: 1px solid var(--workspace-border-strong); border-radius: 999px; color: var(--workspace-accent-strong); background: var(--workspace-accent-soft); font-size: 9px; font-weight: 900; }
.agent-status.status-busy { border-color: #dfbd71; color: #8b6117; background: var(--workspace-warning-soft); }.agent-status.status-offline { border-color: #ccd4ce; color: #6e7a72; background: #f1f3f1; }
.presence-controls { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 0 12px 8px; }.presence-controls button, .intake-mode button { padding: 7px; border: 1px solid var(--workspace-border); border-radius: 7px; color: var(--workspace-text-soft); background: #fff; font-size: 9px; cursor: pointer; }.presence-controls button.active, .intake-mode button.active { border-color: var(--workspace-accent); color: var(--workspace-accent-strong); background: var(--workspace-accent-soft); }.presence-controls small { grid-column: 1 / -1; color: var(--workspace-muted); font-size: 8px; text-align: center; }
.source-notice { display: grid; gap: 3px; margin: 0 12px 8px; padding: 9px 10px; border: 1px solid #b7d3bd; border-radius: 10px; background: #e8f5eb; }.source-notice strong { color: var(--workspace-accent-strong); font-size: 10px; }.source-notice span { color: var(--workspace-text-soft); font-size: 9px; line-height: 1.45; }
.queue-toolbar { display: flex; align-items: center; gap: 8px; padding: 0 12px 8px; }.queue-toolbar label { color: var(--workspace-text-soft); font-size: 9px; font-weight: 800; }.queue-toolbar select { flex: 1; min-width: 0; padding: 6px 7px; border: 1px solid var(--workspace-border); border-radius: 7px; color: var(--workspace-text); background: #fff; font-size: 9px; }
.conversation-list { min-height: 0; padding: 0 8px; overflow: auto; }.conversation-item { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 10px; width: 100%; margin-bottom: 5px; padding: 10px; border: 1px solid transparent; border-radius: 11px; color: inherit; background: transparent; text-align: left; cursor: pointer; }.conversation-item:hover { background: #eaf5ec; }.conversation-item.active { border-color: var(--workspace-border-strong); background: linear-gradient(135deg, #dcefe1, #edf8ef); box-shadow: 0 5px 16px rgb(47 125 87 / 9%); }
.avatar { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 11px; background: #cde5d3; color: var(--workspace-accent-strong); font-size: 11px; font-weight: 900; }.conversation-copy { display: grid; min-width: 0; gap: 5px; }.conversation-title { display: flex; justify-content: space-between; gap: 8px; }.conversation-title strong { color: var(--workspace-text); font-size: 12px; }.conversation-title time { color: var(--workspace-muted); font-size: 9px; }.message-preview { overflow: hidden; color: var(--workspace-text-soft); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.conversation-meta { display: flex; align-items: center; gap: 5px; }.conversation-meta em { margin-right: auto; color: var(--workspace-muted); font-size: 8px; font-style: normal; }.processing-stage { padding: 2px 5px; border-radius: 999px; color: #315e45; background: #e4efe7; font-size: 8px; }.conversation-meta b { padding: 2px 5px; border-radius: 999px; color: #356b50; background: #dcefe1; font-size: 8px; }.conversation-meta b.conversation-waiting_reply { color: #8d6117; background: #fff0ca; }.conversation-meta b.conversation-completed { color: #2e7151; background: #d9eee0; }.conversation-meta i { display: grid; min-width: 17px; height: 17px; place-items: center; border-radius: 999px; color: #fff; background: var(--workspace-accent); font-size: 8px; font-style: normal; }.conversation-empty { margin: 8px; padding: 14px; border: 1px dashed var(--workspace-border-strong); border-radius: 10px; color: var(--workspace-muted); background: rgb(255 255 255 / 55%); font-size: 9px; line-height: 1.5; text-align: center; }
.manual-message-form { display: grid; gap: 7px; margin: 8px 12px 12px; padding: 10px; border: 1px solid var(--workspace-border); border-radius: 11px; background: #fff; }.intake-mode { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }.manual-message-form label { color: var(--workspace-text-soft); font-size: 9px; font-weight: 800; }.manual-message-form input, .manual-message-form textarea { resize: none; padding: 8px; border: 1px solid var(--workspace-border); border-radius: 8px; outline: none; color: var(--workspace-text); background: #fbfefb; font-size: 9px; line-height: 1.45; }.manual-message-form input:focus, .manual-message-form textarea:focus { border-color: var(--workspace-accent); box-shadow: 0 0 0 3px rgb(47 125 87 / 10%); }.manual-message-form > button { padding: 8px; border: 0; border-radius: 8px; color: #fff; background: var(--workspace-accent); font-size: 9px; font-weight: 800; cursor: pointer; }.manual-message-form button:disabled { opacity: .42; cursor: not-allowed; }
</style>
