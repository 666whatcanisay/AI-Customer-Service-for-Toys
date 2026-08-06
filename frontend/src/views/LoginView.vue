<template>
  <main class="login-page">
    <form class="login-card" data-testid="customer-login" @submit.prevent="submit">
      <div class="brand">AI</div>
      <p>AI客服平台</p>
      <h1>客服登录</h1>
      <label>账号<input v-model.trim="username" autocomplete="username" maxlength="64" required /></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" maxlength="128" required /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="busy">{{ busy ? '登录中…' : '登录' }}</button>
      <small>初始化账号需先修改密码；客服可在登录后选择一个或多个负责店铺。</small>
    </form>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthSession } from '@/auth/authSession'

const route = useRoute()
const router = useRouter()
const auth = useAuthSession()
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

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
    if (user.roles.includes('CUSTOMER_SERVICE') && !user.stores.some((store) => store.is_default)) {
      await router.replace('/store-selection')
      return
    }
    const target = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : '/workspace'
    await router.replace(target)
  } catch (caught) {
    const code = (caught as { response?: { data?: { error?: { code?: string } } } })
      ?.response?.data?.error?.code
    error.value = code === 'AUTHENTICATION_RATE_LIMITED'
      ? '登录失败次数过多，请在冷却时间结束后重试。'
      : '账号或密码不正确，或账号已停用。'
  } finally {
    password.value = ''
    busy.value = false
  }
}
</script>

<style scoped>
.login-page { display: grid; min-height: 100vh; place-items: center; padding: 24px; background: linear-gradient(145deg, #0d1e3b, #1d4274); }
.login-card { display: grid; width: min(400px, 100%); gap: 16px; padding: 34px; border-radius: 18px; background: white; box-shadow: 0 28px 70px rgb(0 0 0 / 24%); }
.brand { display: grid; width: 46px; height: 46px; place-items: center; border-radius: 14px; background: #58c9ad; color: #10264a; font-weight: 900; }
.login-card p, .login-card h1 { margin: 0; }
.login-card > p { color: #58708e; }
.login-card label { display: grid; gap: 7px; color: #263c5c; font-weight: 700; }
.login-card input { padding: 11px 12px; border: 1px solid #c7d4e5; border-radius: 9px; }
.login-card button { padding: 11px; border: 0; border-radius: 9px; background: #225ea8; color: white; font-weight: 700; cursor: pointer; }
.login-card button:disabled { opacity: .6; }
.login-card small { color: #6c7d92; line-height: 1.5; }
.error { color: #b42318 !important; }
</style>
