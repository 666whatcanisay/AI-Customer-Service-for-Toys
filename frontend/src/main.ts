import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { fetchChannelAgentBootstrap } from './api/channelAgentDesktopClient'

async function startApplication(): Promise<void> {
  if (import.meta.env.VITE_CHANNEL_AGENT_DESKTOP === 'true') {
    try {
      // The launcher URL has already exchanged its one-time nonce for an
      // HttpOnly local-session cookie. Fetching bootstrap completes the second
      // half of that exchange and installs the matching in-memory CSRF token.
      await fetchChannelAgentBootstrap()
    } catch {
      // The UI still starts so the novice diagnostics page can explain how to
      // reopen the assistant through the tray and obtain a fresh handoff.
    }
  }
  createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
}

void startApplication()
