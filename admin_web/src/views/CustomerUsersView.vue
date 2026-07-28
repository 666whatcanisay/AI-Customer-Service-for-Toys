<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  createCustomerUser,
  listCatalogStores,
  listCustomerUsers,
  updateCustomerUser,
  updateCustomerUserStatus,
  type CatalogStore,
  type CustomerUser,
  type CustomerUserRole,
  type CustomerUserStatus,
} from '../api/client'
import { displayStatus } from '../presentation'

const users = ref<CustomerUser[]>([])
const stores = ref<CatalogStore[]>([])
const selected = ref<CustomerUser | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const actionError = ref('')
const notice = ref('')
const filterStatus = ref<CustomerUserStatus | ''>('')
const isCreating = ref(false)
const roles: CustomerUserRole[] = ['CUSTOMER_SERVICE', 'OPERATIONS', 'ADMIN']
const form = reactive({
  display_name: '',
  role: 'CUSTOMER_SERVICE' as CustomerUserRole,
  store_codes: [] as string[],
  default_store_code: '',
})

const canSave = computed(() => (
  !saving.value
  && form.display_name.trim().length > 0
  && form.store_codes.length > 0
  && form.store_codes.includes(form.default_store_code)
))

function resetForm(user?: CustomerUser): void {
  actionError.value = ''
  notice.value = ''
  if (!user) {
    form.display_name = ''
    form.role = 'CUSTOMER_SERVICE'
    form.store_codes = []
    form.default_store_code = ''
    return
  }
  form.display_name = user.display_name
  form.role = user.role
  form.store_codes = user.store_bindings.map((binding) => binding.store_code)
  form.default_store_code = user.default_store_code
}

function choose(user: CustomerUser): void {
  isCreating.value = false
  selected.value = user
  resetForm(user)
}

function beginCreate(): void {
  selected.value = null
  isCreating.value = true
  resetForm()
}

function toggleStore(storeCode: string, checked: boolean): void {
  form.store_codes = checked
    ? [...form.store_codes, storeCode]
    : form.store_codes.filter((item) => item !== storeCode)
  if (!form.store_codes.includes(form.default_store_code)) {
    form.default_store_code = form.store_codes[0] || ''
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [userResult, storeResult] = await Promise.all([listCustomerUsers(filterStatus.value || undefined), listCatalogStores()])
    users.value = userResult.items
    stores.value = storeResult
    if (selected.value) {
      selected.value = userResult.items.find((item) => item.user_id === selected.value?.user_id) || null
      if (selected.value) resetForm(selected.value)
    }
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!canSave.value) return
  saving.value = true
  actionError.value = ''
  notice.value = ''
  const payload = {
    display_name: form.display_name.trim(),
    role: form.role,
    store_codes: form.store_codes,
    default_store_code: form.default_store_code,
  }
  const wasEditing = selected.value !== null
  try {
    const user = selected.value
      ? await updateCustomerUser(selected.value.user_id, payload)
      : await createCustomerUser(payload)
    selected.value = user
    isCreating.value = false
    resetForm(user)
    notice.value = wasEditing ? '客服用户信息已保存。' : '客服用户已创建。'
    await load()
  } catch (reason: unknown) {
    actionError.value = apiErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function toggleStatus(user: CustomerUser): Promise<void> {
  saving.value = true
  actionError.value = ''
  notice.value = ''
  try {
    const nextStatus: CustomerUserStatus = user.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'
    const updated = await updateCustomerUserStatus(user.user_id, nextStatus)
    selected.value = updated
    resetForm(updated)
    notice.value = nextStatus === 'ACTIVE' ? '客服用户已启用。' : '客服用户已停用，客服工作台将不再允许其进入。'
    await load()
  } catch (reason: unknown) {
    actionError.value = apiErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">客服运营 / 团队身份</p>
        <h1>客服用户</h1>
        <p>为内部试运行配置客服、运营和管理员身份，并绑定可处理的店铺。这里是最小身份选择，不是密码登录或正式权限系统。</p>
      </div>
      <button class="button" type="button" @click="beginCreate">新增客服用户</button>
    </div>

    <p class="notice boundary"><strong>试运行边界：</strong>客服工作台只使用已启用且已绑定店铺的身份。停用后不能再提交案例、AI 问题反馈或效率事件；不会删除历史记录。</p>

    <div class="toolbar card">
      <label>状态
        <select v-model="filterStatus" @change="load">
          <option value="">全部</option>
          <option value="ACTIVE">启用中</option>
          <option value="DISABLED">已停用</option>
        </select>
      </label>
      <button class="button secondary" type="button" :disabled="loading" @click="load">刷新列表</button>
    </div>

    <p v-if="loading" class="notice" role="status">正在读取客服用户和店铺资料…</p>
    <p v-else-if="error" class="notice error" role="alert">客服用户资料暂时无法读取。{{ error }}</p>

    <section v-else class="user-grid">
      <div class="card table-wrap">
        <template v-if="users.length">
          <table class="data-table">
            <thead><tr><th>姓名</th><th>角色</th><th>默认店铺</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="user in users" :key="user.user_id" :class="{ selected: selected?.user_id === user.user_id }">
                <td><button class="link-button" type="button" @click="choose(user)">{{ user.display_name }}</button><small>{{ user.user_id }}</small></td>
                <td>{{ displayStatus(user.role) }}</td>
                <td>{{ user.default_store_code }}<small>{{ user.store_bindings.length }} 家已绑定店铺</small></td>
                <td><span class="badge" :class="user.status === 'ACTIVE' ? 'success' : 'muted'">{{ displayStatus(user.status) }}</span></td>
                <td><button class="text-button" type="button" @click="choose(user)">编辑</button></td>
              </tr>
            </tbody>
          </table>
        </template>
        <p v-else class="notice">还没有客服用户。请先新增一位客服并绑定店铺，客服工作台才可进入。</p>
      </div>

      <aside v-if="isCreating || selected" class="card detail">
        <h2>{{ isCreating ? '新增客服用户' : '编辑客服用户' }}</h2>
        <label>姓名<input v-model="form.display_name" maxlength="80" placeholder="例如：小林" /></label>
        <label>角色
          <select v-model="form.role"><option v-for="role in roles" :key="role" :value="role">{{ displayStatus(role) }}</option></select>
        </label>
        <fieldset>
          <legend>可处理店铺</legend>
          <p v-if="stores.length === 0" class="notice error">当前没有可绑定的店铺资料。请先导入测试数据包或商品资料，不能创建无法使用的客服身份。</p>
          <label v-for="store in stores" :key="store.store_code" class="check-row">
            <input :checked="form.store_codes.includes(store.store_code)" type="checkbox" @change="toggleStore(store.store_code, ($event.target as HTMLInputElement).checked)" />
            <span>{{ store.store_name }}<small>{{ store.store_code }}</small></span>
          </label>
        </fieldset>
        <label>默认店铺
          <select v-model="form.default_store_code" :disabled="form.store_codes.length === 0">
            <option value="">请选择默认店铺</option>
            <option v-for="storeCode in form.store_codes" :key="storeCode" :value="storeCode">{{ storeCode }}</option>
          </select>
        </label>
        <p class="subtle">客服进入工作台后默认使用此店铺；多店切换已保留绑定信息，但不会擅自切换店铺。</p>
        <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>
        <p v-if="notice" class="notice success">{{ notice }}</p>
        <div class="actions">
          <button class="button" data-testid="customer-user-save" type="button" :disabled="!canSave" @click="save">{{ saving ? '保存中…' : '保存用户' }}</button>
          <button v-if="selected" class="button secondary" type="button" :disabled="saving" @click="toggleStatus(selected)">{{ selected.status === 'ACTIVE' ? '停用用户' : '启用用户' }}</button>
          <button class="button secondary" type="button" :disabled="saving" @click="selected = null; isCreating = false; resetForm()">取消</button>
        </div>
      </aside>

      <aside v-else class="card detail">
        <h2>用户说明</h2>
        <p>选择一位客服可编辑姓名、角色、可处理店铺和默认店铺；也可以新增用户。</p>
        <p class="subtle">此页不展示密码，也不提供 SSO 或复杂角色授权。历史案例和反馈只保存客服用户 ID，用于追溯来源。</p>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.toolbar { display: flex; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }
label { display: grid; gap: 5px; color: #526279; font-size: 13px; }
input, select { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }
.boundary { margin-bottom: 18px; background: #fff8e7; color: #77510a; }.user-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(300px, .85fr); gap: 20px; }
.detail { display: grid; align-content: start; gap: 13px; }.detail h2 { margin: 0; color: #172554; } fieldset { display: grid; gap: 8px; margin: 0; padding: 12px; border: 1px solid #d7e2ee; border-radius: 9px; } legend { padding: 0 5px; color: #526279; font-size: 13px; font-weight: 700; }.check-row { display: flex; grid-template-columns: none; align-items: start; gap: 8px; }.check-row input { min-height: 0; margin-top: 3px; }.check-row small, td small { display: block; margin-top: 3px; color: #617087; font-size: 11px; }.link-button, .text-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.text-button { font-size: 13px; }.selected { background: #f0f6ff; }.badge.success { color: #176744; background: #edf9f3; }.badge.muted { color: #667085; background: #edf1f6; }.subtle { margin: 0; color: #617087; font-size: 12px; line-height: 1.5; }.actions { display: flex; flex-wrap: wrap; gap: 10px; }
@media (max-width: 900px) { .user-grid { grid-template-columns: 1fr; } }
</style>
