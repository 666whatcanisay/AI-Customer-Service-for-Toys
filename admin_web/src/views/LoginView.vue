<template>
  <main class="login-page"><form class="login-card" data-testid="admin-login" @submit.prevent="submit">
    <div class="brand-mark">AI</div><p>AI客服平台</p><h1>运营管理登录</h1>
    <label>账号<input v-model.trim="username" autocomplete="username" maxlength="64" required /></label>
    <label>密码<input v-model="password" type="password" autocomplete="current-password" maxlength="128" required /></label>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="busy">{{ busy ? '登录中…' : '登录' }}</button>
  </form></main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminSession } from '../auth/session'
const auth = useAdminSession(); const route = useRoute(); const router = useRouter()
const username = ref(''); const password = ref(''); const busy = ref(false); const error = ref('')
const submit = async () => {
  busy.value = true; error.value = ''
  try {
    const current = await auth.login(username.value, password.value)
    if (current.must_change_password === true) { await router.replace('/change-password'); return }
    const allowed = current.permissions.some((item) => ['product.manage', 'sku.manage', 'knowledge.manage', 'faq.manage', 'ai_quality.view', 'store.view', 'feedback.view', 'user.manage'].includes(item))
    if (!allowed) { await auth.logout(); error.value = '当前账号没有运营管理权限。'; return }
    const target = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/overview'
    await router.replace(target)
  } catch { error.value = '账号或密码不正确，或账号已停用。' }
  finally { password.value = ''; busy.value = false }
}
</script>
<style scoped>
.login-page{display:grid;min-height:100vh;place-items:center;padding:24px;background:linear-gradient(145deg,#0d1e3b,#1d4274)}.login-card{display:grid;width:min(410px,100%);gap:16px;padding:34px;border-radius:18px;background:#fff;box-shadow:0 28px 70px rgb(0 0 0/24%)}.login-card p,.login-card h1{margin:0}.login-card>p{color:#58708e}.login-card label{display:grid;gap:7px;color:#263c5c;font-weight:700}.login-card input{padding:11px 12px;border:1px solid #c7d4e5;border-radius:9px}.login-card button{padding:11px;border:0;border-radius:9px;background:#225ea8;color:#fff;font-weight:700}.error{color:#b42318!important}
</style>
