<template>
  <aside class="conversation-center" aria-label="会话中心" data-testid="conversation-center">
    <header>
      <div>
        <p>CONVERSATION CENTER</p>
        <h2>客户会话</h2>
      </div>
      <span class="observe-badge">OBSERVE</span>
    </header>

    <div class="source-notice">
      <strong>模拟渠道</strong>
      <span>当前不连接真实 PDD，不读取真实客户消息。</span>
    </div>

    <div class="conversation-list">
      <button
        v-for="conversation in conversations"
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
            <em>{{ conversation.source === 'MOCK' ? 'Mock Message' : 'Channel Agent' }}</em>
            <i v-if="conversation.unreadCount > 0">{{ conversation.unreadCount }}</i>
          </span>
        </span>
      </button>
    </div>

    <form class="mock-message-form" data-testid="mock-message-form" @submit.prevent="submitMockMessage">
      <label for="mock-message">模拟一条新客户消息</label>
      <textarea
        id="mock-message"
        v-model="mockMessage"
        rows="3"
        maxlength="300"
        placeholder="新消息会让当前回复草稿自动失效"
      />
      <button type="submit" :disabled="!activeConversationId || !mockMessage.trim()">
        接收模拟消息
      </button>
    </form>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import type { WorkspaceConversation } from '@/stores/humanLoopWorkspace'

defineProps<{
  conversations: WorkspaceConversation[]
  activeConversationId: string
}>()

const emit = defineEmits<{
  select: [conversationId: string]
  mockMessage: [content: string]
}>()

const mockMessage = ref('')

const submitMockMessage = () => {
  const content = mockMessage.value.trim()
  if (!content) return
  emit('mockMessage', content)
  mockMessage.value = ''
}

const timeLabel = (value?: string): string => {
  if (!value) return '--:--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--:--'
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(date)
}
</script>

<style scoped>
.conversation-center {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  min-width: 0;
  min-height: 0;
  border-right: 1px solid #263653;
  background: #111a2c;
}

header { display: flex; align-items: center; justify-content: space-between; padding: 20px 18px 14px; }
header p { margin: 0 0 5px; color: #6f83a8; font-size: 9px; font-weight: 800; letter-spacing: .14em; }
header h2 { margin: 0; color: #f3f7ff; font-size: 18px; }
.observe-badge { padding: 5px 8px; border: 1px solid #3c557e; border-radius: 999px; color: #8db5ff; font-size: 9px; font-weight: 900; }
.source-notice { display: grid; gap: 3px; margin: 0 12px 12px; padding: 10px 11px; border: 1px solid #34527b; border-radius: 10px; background: #172640; }
.source-notice strong { color: #83b1ff; font-size: 11px; }
.source-notice span { color: #91a2bd; font-size: 10px; line-height: 1.45; }
.conversation-list { min-height: 0; padding: 0 8px; overflow: auto; }
.conversation-item { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 10px; width: 100%; margin-bottom: 5px; padding: 11px 10px; border: 1px solid transparent; border-radius: 11px; color: inherit; background: transparent; text-align: left; cursor: pointer; }
.conversation-item:hover { background: #18243a; }
.conversation-item.active { border-color: #365f9d; background: linear-gradient(135deg, #1c3152, #18253c); }
.avatar { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 11px; background: #263a5a; color: #a9c8ff; font-size: 11px; font-weight: 900; }
.conversation-copy { display: grid; min-width: 0; gap: 5px; }
.conversation-title { display: flex; justify-content: space-between; gap: 8px; }
.conversation-title strong { color: #eaf1ff; font-size: 12px; }
.conversation-title time { color: #657897; font-size: 9px; }
.message-preview { overflow: hidden; color: #8fa0bb; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.conversation-meta { display: flex; align-items: center; justify-content: space-between; }
.conversation-meta em { color: #657b9d; font-size: 9px; font-style: normal; }
.conversation-meta i { display: grid; min-width: 18px; height: 18px; place-items: center; border-radius: 999px; background: #4e8cff; color: #fff; font-size: 9px; font-style: normal; }
.mock-message-form { display: grid; gap: 8px; margin: 10px 12px 12px; padding: 12px; border: 1px solid #2a3b58; border-radius: 11px; background: #152036; }
.mock-message-form label { color: #b8c6dc; font-size: 10px; font-weight: 800; }
.mock-message-form textarea { resize: none; padding: 9px; border: 1px solid #344765; border-radius: 8px; outline: none; color: #e8effb; background: #0e1829; font-size: 10px; line-height: 1.5; }
.mock-message-form textarea:focus { border-color: #5a92e9; }
.mock-message-form button { padding: 8px; border: 0; border-radius: 8px; background: #315d9f; color: #fff; font-size: 10px; font-weight: 800; cursor: pointer; }
.mock-message-form button:disabled { opacity: .45; cursor: not-allowed; }
</style>

