<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getHealth, isOfflineError, type HealthResponse } from '../api/client'

type ViewState = 'loading' | 'ok' | 'offline' | 'error'

const state = ref<ViewState>('loading')
const health = ref<HealthResponse | null>(null)

async function loadStatus(): Promise<void> {
  state.value = 'loading'
  health.value = null

  try {
    health.value = await getHealth()
    state.value = 'ok'
  } catch (error: unknown) {
    state.value = isOfflineError(error) ? 'offline' : 'error'
  }
}

onMounted(loadStatus)
</script>

<template>
  <main class="status-page">
    <section class="status-card" aria-live="polite">
      <p class="eyebrow">木木小栈 · 管理平台</p>
      <h1>系统状态</h1>

      <div v-if="state === 'loading'" class="state state-loading" role="status">
        <strong>正在加载</strong>
        <span>正在连接平台服务，请稍候。</span>
      </div>

      <div v-else-if="state === 'ok'" class="state state-ok" role="status">
        <strong>正常</strong>
        <span>{{ health?.service }} · v{{ health?.version }}</span>
        <small>Request ID: {{ health?.request_id }}</small>
      </div>

      <div v-else-if="state === 'offline'" class="state state-offline" role="alert">
        <strong>断网</strong>
        <span>无法连接平台服务，请检查网络或服务是否已启动。</span>
      </div>

      <div v-else class="state state-error" role="alert">
        <strong>错误</strong>
        <span>平台服务返回错误，请稍后重试。</span>
      </div>

      <button v-if="state !== 'loading'" type="button" @click="loadStatus">重新检查</button>
    </section>
  </main>
</template>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  color: #172033;
  background: #f3f6fb;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
}

.status-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.status-card {
  width: min(100%, 560px);
  padding: 36px;
  border: 1px solid #dbe3ef;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 18px 50px rgb(30 52 86 / 9%);
}

.eyebrow {
  margin: 0 0 8px;
  color: #53627a;
  font-size: 14px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1 {
  margin: 0 0 28px;
  font-size: clamp(28px, 5vw, 40px);
}

.state {
  display: grid;
  gap: 8px;
  padding: 20px;
  border-left: 5px solid;
  border-radius: 10px;
  background: #f7f9fc;
}

.state strong {
  font-size: 20px;
}

.state small {
  overflow-wrap: anywhere;
  color: #53627a;
}

.state-loading {
  border-color: #4f6ea8;
}

.state-ok {
  border-color: #16845b;
  background: #effaf5;
}

.state-offline {
  border-color: #c77a16;
  background: #fff8ec;
}

.state-error {
  border-color: #c94444;
  background: #fff3f3;
}

button {
  margin-top: 20px;
  padding: 10px 16px;
  border: 0;
  border-radius: 8px;
  color: #fff;
  background: #284f8f;
  font: inherit;
  cursor: pointer;
}

button:hover {
  background: #1f3f74;
}

button:focus-visible {
  outline: 3px solid #8bb4ff;
  outline-offset: 3px;
}
</style>
