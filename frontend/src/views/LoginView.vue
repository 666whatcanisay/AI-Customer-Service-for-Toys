<template>
  <main class="login-page" :class="{ desktop: desktopMode, blocked: agentBlocked }">
    <div class="client-window">
      <header v-if="desktopMode" class="client-header">
        <div class="header-brand"><span>AI</span><div><strong>AI客服助手</strong><small>ChannelAgent 客服工作台</small></div></div>
        <div class="header-safety"><i></i>人工确认后发送</div>
      </header>
      <div class="login-shell">
        <form class="login-card" data-testid="customer-login" @submit.prevent="submit">
          <div class="brand">AI</div>
          <span class="welcome-label">客服工作台</span>
          <h1>欢迎登录AI客服助手</h1>
          <div v-if="desktopMode" class="login-health" :class="agentHealth.overall.toLowerCase()">
            <i></i>{{ agentBlocked ? `需要先处理 ${agentHealth.issues} 项运行问题` : agentHealth.overall === 'BLOCKED' ? '首次使用，请先登录完成设置' : agentHealth.issues ? `有 ${agentHealth.issues} 项提醒` : '系统运行正常' }}
          </div>
          <label>账号<input ref="usernameInput" v-model.trim="username" autocomplete="username" maxlength="64" placeholder="请输入客服账号" required /></label>
          <label>密码<input v-model="password" type="password" autocomplete="current-password" maxlength="128" placeholder="请输入登录密码" required /></label>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <button type="submit" :disabled="busy || (desktopMode && agentBlocked)">{{ busy ? '正在登录…' : agentBlocked ? '请先处理右侧问题' : '登录' }}</button>
          <small>首次使用需要完成设备绑定和店铺授权，完成后即可进入客服助手。</small>
        </form>
        <AgentRecoveryCenter
          v-if="desktopMode"
          ref="recoveryCenter"
          @blocked="agentBlocked = $event"
          @status="agentHealth = $event"
          @onboarding="focusLogin"
        />
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthSession } from '@/auth/authSession'
import AgentRecoveryCenter from '@/components/agent/AgentRecoveryCenter.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthSession()
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const desktopMode = import.meta.env.VITE_CHANNEL_AGENT_DESKTOP === 'true'
const agentBlocked = ref(false)
const agentHealth = ref<{ overall: 'PASS' | 'WARNING' | 'BLOCKED'; issues: number }>({ overall: 'PASS', issues: 0 })
const recoveryCenter = ref<InstanceType<typeof AgentRecoveryCenter> | null>(null)
const usernameInput = ref<HTMLInputElement | null>(null)

const focusLogin = () => {
  usernameInput.value?.focus()
}

const submit = async () => {
  busy.value = true
  error.value = ''
  try {
    const user = await auth.login(username.value, password.value)
    if (user.must_change_password === true) {
      await router.replace('/change-password')
      return
    }
    if (!user.permissions.includes('workspace.access')) {
      await auth.logout()
      error.value = '当前账号没有客服工作台权限。'
      return
    }
    if (!desktopMode && user.roles.includes('CUSTOMER_SERVICE') && !user.stores.some((store) => store.is_default)) {
      await router.replace('/store-selection')
      return
    }
    const target = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : '/workspace'
    await router.replace(target)
  } catch (caught) {
    const response = (caught as { response?: { status?: number; data?: { detail?: string; error?: { code?: string } } }; code?: string })?.response
    const localError = caught instanceof Error ? caught.message : ''
    const status = response?.status
    const code = response?.data?.error?.code
    const detail = response?.data?.detail ?? ''
    if (status === 401) {
      error.value = '账号或密码错误，或账号已停用。'
    } else if (status === 429 || code === 'AUTHENTICATION_RATE_LIMITED') {
      error.value = '登录失败次数过多，请在冷却时间结束后重试。'
    } else if (status === 503 && detail.includes('not configured')) {
      error.value = 'AI-CS身份服务地址未配置，登录请求已被本地安全代理阻止。'
      recoveryCenter.value?.openDiagnostics(error.value)
    } else if (code === 'LOCAL_SESSION_OR_CSRF_INVALID' || localError.startsWith('CHANNEL_AGENT_BOOTSTRAP_')) {
      error.value = '客服助手本地安全会话已失效，请从任务栏托盘重新打开客服助手。这不是账号或密码错误。'
      recoveryCenter.value?.openDiagnostics(error.value)
    } else if ([502, 503, 504].includes(status ?? 0)) {
      error.value = `AI-CS服务暂时不可用（HTTP ${status}），请检查主机服务、地址和端口。`
      recoveryCenter.value?.openDiagnostics(error.value)
    } else if (code?.includes('AGENT') || code?.includes('DEVICE') || code?.includes('BIND')) {
      error.value = `Channel Engine拒绝连接：设备未注册、未绑定或凭证已失效（${code}）。`
      recoveryCenter.value?.openDiagnostics(error.value)
    } else {
      const faultId = `LOGIN-${Date.now().toString(36).toUpperCase()}`
      error.value = `登录请求未完成，故障编号：${faultId}。`
      recoveryCenter.value?.openDiagnostics(error.value)
    }
  } finally {
    password.value = ''
    busy.value = false
  }
}
</script>

<style scoped>
.login-page{display:grid;min-height:100vh;place-items:center;padding:24px;background:radial-gradient(circle at 72% 15%,#2d5d91 0,transparent 34%),linear-gradient(145deg,#102a4e,#183e6c);font-family:"Segoe UI","Microsoft YaHei",sans-serif}.client-window{width:min(1180px,100%)}.client-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;padding:0 6px;color:white}.header-brand{display:flex;align-items:center;gap:12px}.header-brand>span{display:grid;width:40px;height:40px;place-items:center;border-radius:12px;background:#58c9ad;color:#10264a;font-weight:900}.header-brand div{display:grid;gap:2px}.header-brand strong{font-size:18px}.header-brand small{color:#c9d8e9}.header-safety{display:flex;align-items:center;gap:8px;padding:8px 13px;border:1px solid #ffffff32;border-radius:999px;background:#ffffff12;font-size:13px}.header-safety i,.login-health i{width:8px;height:8px;border-radius:50%;background:#42c78a}.login-shell{display:flex;align-items:stretch;justify-content:center;gap:18px;width:100%}.login-card{display:grid;align-content:center;width:min(410px,100%);min-height:520px;box-sizing:border-box;gap:15px;padding:38px;border-radius:20px;background:white;box-shadow:0 25px 65px rgb(4 20 45 / 25%)}.brand{display:grid;width:46px;height:46px;place-items:center;border-radius:14px;background:#58c9ad;color:#10264a;font-weight:900}.welcome-label{color:#52708f;font-size:14px}.login-card p,.login-card h1{margin:0}.login-card h1{font-size:28px;line-height:1.25;color:#122d4e}.login-health{display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:10px;background:#ecf8f1;color:#16704a;font-size:13px;font-weight:700}.login-health.warning{background:#fff7df;color:#8a5b00}.login-health.blocked{background:#fff0ef;color:#b42318}.login-health.warning i{background:#e9a323}.login-health.blocked i{background:#d92d20}.login-card label{display:grid;gap:8px;color:#263c5c;font-weight:700}.login-card input{height:48px;box-sizing:border-box;padding:0 14px;border:1px solid #c3d2e3;border-radius:11px;font-size:15px;outline:none;transition:.2s}.login-card input:focus{border-color:#2f6fba;box-shadow:0 0 0 3px #2f6fba18}.login-card button{height:48px;border:0;border-radius:11px;background:#2869b5;color:white;font-size:15px;font-weight:800;cursor:pointer}.login-card button:disabled{background:#9fb2c7;cursor:not-allowed}.login-card small{color:#6c7d92;line-height:1.6}.error{padding:10px 12px;border-radius:9px;background:#fff0ef;color:#b42318!important;font-size:13px}.login-page:not(.desktop) .client-window{max-width:410px}.desktop.blocked .login-shell{align-items:stretch}@media(max-width:900px){.login-page{align-items:start;padding:16px}.client-header{margin:4px 0 14px}.header-safety{display:none}.login-shell{flex-direction:column}.login-card{width:100%;min-height:auto}.client-window{max-width:680px}}
</style>
