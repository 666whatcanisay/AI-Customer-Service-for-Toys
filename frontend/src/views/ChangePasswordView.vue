<template>
  <main class="policy-page">
    <form class="policy-card" data-testid="customer-change-password" @submit.prevent="submit">
      <p>账号安全</p>
      <h1>首次登录请修改密码</h1>
      <small>新密码至少12个字符。修改成功后所有现有会话失效，请使用新密码重新登录。</small>
      <label>当前临时密码<input v-model="currentPassword" type="password" autocomplete="current-password" maxlength="128" required /></label>
      <label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required /></label>
      <label>确认新密码<input v-model="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="128" required /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="busy">{{ busy ? '修改中…' : '修改密码并重新登录' }}</button>
    </form>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthSession } from '@/auth/authSession'

const auth = useAuthSession()
const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const confirmation = ref('')
const busy = ref(false)
const error = ref('')

const submit = async () => {
  error.value = ''
  if (newPassword.value !== confirmation.value) {
    error.value = '两次输入的新密码不一致。'
    return
  }
  busy.value = true
  try {
    await auth.changePassword(currentPassword.value, newPassword.value)
    await router.replace('/login?passwordChanged=1')
  } catch {
    error.value = '密码修改失败，请检查当前密码和新密码长度。'
  } finally {
    currentPassword.value = ''
    newPassword.value = ''
    confirmation.value = ''
    busy.value = false
  }
}
</script>

<style scoped>
.policy-page{display:grid;min-height:100vh;place-items:center;padding:24px;background:#10284b}.policy-card{display:grid;width:min(440px,100%);gap:15px;padding:32px;border-radius:18px;background:#fff}.policy-card p,.policy-card h1{margin:0}.policy-card small{color:#5f7087;line-height:1.6}.policy-card label{display:grid;gap:7px;font-weight:700}.policy-card input{padding:11px;border:1px solid #c8d4e3;border-radius:9px}.policy-card button{padding:11px;border:0;border-radius:9px;background:#225ea8;color:#fff;font-weight:700}.error{color:#b42318}
</style>
