<template>
  <main class="store-page">
    <section class="store-card" data-testid="customer-store-selection">
      <p>客服工作范围</p>
      <h1>选择负责的店铺</h1>
      <small>可选择一个或多个已启用客服店铺。保存后仍可回到本页调整。</small>
      <p v-if="loading">正在读取店铺…</p>
      <form v-else @submit.prevent="save">
        <div v-for="store in options" :key="store.store_id" class="store-option">
          <label class="store-main"><input v-model="selected" type="checkbox" :value="store.store_id" />
            <span><strong>{{ store.store_name }}</strong><small>{{ platformLabel(store.platform) }}</small></span>
          </label>
          <label v-if="selected.includes(store.store_id)" class="default-choice">
            <input v-model="defaultStoreId" type="radio" name="default-store" :value="store.store_id" /> 默认进入
          </label>
        </div>
        <p v-if="!options.length" class="error">当前没有已启用的客服店铺，请联系运营。</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" :disabled="saving || !selected.length">{{ saving ? '保存中…' : '保存并进入工作台' }}</button>
      </form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthSession, type AuthStoreOption } from '@/auth/authSession'

const auth = useAuthSession()
const router = useRouter()
const options = ref<AuthStoreOption[]>([])
const selected = ref<number[]>([])
const defaultStoreId = ref<number | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')

const platformLabel = (platform: string): string => ({
  pdd: '拼多多',
  pinduoduo: '拼多多',
  taobao: '淘宝',
  tmall: '天猫',
  jd: '京东',
  douyin: '抖音',
  offline: '线下',
}[platform.toLowerCase()] ?? '其他平台')

onMounted(async () => {
  try {
    options.value = await auth.listStoreOptions()
    selected.value = auth.user.value?.stores.map((item) => item.store_id) ?? []
    defaultStoreId.value = auth.defaultStore.value?.store_id ?? selected.value[0] ?? null
  } catch {
    error.value = '店铺列表读取失败，请稍后重试。'
  } finally {
    loading.value = false
  }
})

const save = async () => {
  if (!selected.value.length) return
  if (defaultStoreId.value === null || !selected.value.includes(defaultStoreId.value)) {
    defaultStoreId.value = selected.value[0]
  }
  saving.value = true
  error.value = ''
  try {
    await auth.replaceStoreBindings(selected.value, defaultStoreId.value)
    await router.replace('/workspace')
  } catch {
    error.value = '店铺绑定保存失败，请刷新后重试。'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.store-page{display:grid;min-height:100vh;place-items:center;padding:24px;background:#10284b}.store-card{width:min(560px,100%);padding:32px;border-radius:18px;background:#fff}.store-card>p,.store-card h1{margin:0 0 10px}.store-card>small{color:#5f7087}.store-card form{display:grid;gap:12px;margin-top:22px}.store-option,.store-main{display:flex;gap:12px;align-items:center}.store-option{padding:13px;border:1px solid #d4deeb;border-radius:10px}.store-main{flex:1}.store-option span,.store-option small{display:block}.store-option small{margin-top:3px;color:#6e7e92}.store-card button{padding:11px;border:0;border-radius:9px;background:#225ea8;color:#fff;font-weight:700}.store-card button:disabled{opacity:.55}.error{color:#b42318}
.default-choice{margin-left:auto;display:flex!important;gap:5px;align-items:center;color:#335f96;font-size:13px}
</style>
