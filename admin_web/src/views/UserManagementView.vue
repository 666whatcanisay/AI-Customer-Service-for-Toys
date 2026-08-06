<template>
  <section class="user-management" data-testid="user-management-page">
    <header><div><p>系统 · 身份与权限</p><h1>用户管理</h1></div><button type="button" @click="load">刷新</button></header>
    <p class="boundary">账号权限由服务端校验。初始化密码首次登录必须修改；客服可绑定多个店铺，运营和管理员默认拥有全部店铺范围。</p>

    <form class="card create-form" data-testid="create-user-form" @submit.prevent="submitCreate">
      <h2>创建用户</h2>
      <label>账号<input v-model.trim="draft.username" required minlength="1" maxlength="64" /><small>支持中文、大小写字母、数字及 . _ -</small></label>
      <label>显示姓名<input v-model.trim="draft.displayName" required maxlength="80" /></label>
      <label>临时初始密码<input v-model="draft.password" type="password" required minlength="8" maxlength="128" autocomplete="new-password" /><small>至少8位；首次登录强制修改为12位以上。</small></label>
      <fieldset><legend>角色</legend><label v-for="role in roles" :key="role"><input v-model="draft.roles" type="checkbox" :value="role" />{{ roleLabel(role) }}</label></fieldset>
      <fieldset><legend>客服店铺（可多选，并指定默认店铺）</legend><label v-for="store in stores" :key="store.store_ref"><input v-model="draft.storeIds" type="checkbox" :value="store.store_ref" />{{ store.store_name }}<input v-if="draft.storeIds.includes(store.store_ref)" v-model="draft.defaultStoreId" type="radio" name="create-default-store" :value="store.store_ref" />默认</label></fieldset>
      <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      <button type="submit" :disabled="saving">{{ saving ? '创建中…' : '创建用户' }}</button>
    </form>

    <div class="card">
      <h2>用户列表</h2><p v-if="loading">正在加载…</p><p v-else-if="loadError" class="error" role="alert">{{ loadError }}</p>
      <table v-else><thead><tr><th>用户</th><th>角色</th><th>店铺范围</th><th>密码状态</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="item in users" :key="item.id">
          <td><strong>{{ item.display_name }}</strong><small>{{ item.username }}</small></td>
          <td>{{ item.roles.map(roleLabel).join('、') }}</td>
          <td>{{ item.all_store_access ? '全部店铺' : (item.stores.map((store) => `${store.store_name}${store.is_default ? '（默认）' : ''}`).join('、') || '待选择') }}</td>
          <td>{{ item.must_change_password ? '首次登录需修改' : '已更新' }}</td>
          <td>{{ item.status === 'ACTIVE' ? '启用' : '停用' }}</td>
          <td><button type="button" @click="startEdit(item)">分配</button><button v-if="item.status === 'ACTIVE'" type="button" class="danger" @click="disable(item)">停用</button></td>
        </tr></tbody>
      </table>
    </div>

    <form v-if="editing" class="card assignment" data-testid="user-assignment-form" @submit.prevent="saveAssignment">
      <h2>分配角色与店铺：{{ editing.display_name }}</h2>
      <fieldset><legend>角色</legend><label v-for="role in roles" :key="role"><input v-model="editRoles" type="checkbox" :value="role" />{{ roleLabel(role) }}</label></fieldset>
      <fieldset><legend>客服店铺（可多选，并指定默认店铺）</legend><label v-for="store in stores" :key="store.store_ref"><input v-model="editStoreIds" type="checkbox" :value="store.store_ref" />{{ store.store_name }}<input v-if="editStoreIds.includes(store.store_ref)" v-model="editDefaultStoreId" type="radio" name="edit-default-store" :value="store.store_ref" />默认</label></fieldset>
      <p v-if="editError" class="error" role="alert">{{ editError }}</p>
      <div><button type="submit" :disabled="saving">保存分配</button><button type="button" @click="editing = null">取消</button></div>
    </form>

    <div class="card" data-testid="store-context-audit">
      <h2>商品识别记录</h2>
      <p v-if="!resolutions.length">暂无识别记录。</p>
      <table v-else><thead><tr><th>时间</th><th>客服</th><th>店铺</th><th>商品 / SKU</th><th>结果</th></tr></thead>
        <tbody><tr v-for="item in resolutions" :key="item.resolution_id">
          <td>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</td>
          <td>{{ userName(item.user_id) }}</td><td>{{ storeName(item.store_id) }}</td>
          <td>{{ item.product_id ?? '未识别' }} / {{ item.sku_id ?? '无或待确认' }}</td>
          <td>{{ item.status }} · {{ item.reason_code }}</td>
        </tr></tbody>
      </table>
      <small>仅展示实体标识和解析结果；系统不保存或展示客户消息原文。</small>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { AuthUser, RoleName } from '../auth/session'
import {
  apiErrorMessage, assignUserRoles, assignUserStores, createUser, deactivateUser,
  listOperationStores, listStoreContextResolutions, listUsers,
  type StoreContextResolutionAudit, type StoreOperationItem,
} from '../api/client'

const roles: RoleName[] = ['ADMIN', 'OPERATOR', 'CUSTOMER_SERVICE']
const users = ref<AuthUser[]>([]); const stores = ref<StoreOperationItem[]>([])
const resolutions = ref<StoreContextResolutionAudit[]>([])
const loading = ref(true); const saving = ref(false); const loadError = ref(''); const formError = ref(''); const editError = ref('')
const editing = ref<AuthUser | null>(null); const editRoles = ref<RoleName[]>([]); const editStoreIds = ref<number[]>([]); const editDefaultStoreId = ref<number | null>(null)
const draft = reactive({ username: '', displayName: '', password: '', roles: ['CUSTOMER_SERVICE'] as RoleName[], storeIds: [] as number[], defaultStoreId: null as number | null })
const roleLabel = (role: RoleName) => ({ ADMIN: '管理员', OPERATOR: '运营', CUSTOMER_SERVICE: '客服' })[role]

const load = async () => {
  loading.value = true; loadError.value = ''
  try { const [userResult, storeResult, resolutionResult] = await Promise.all([listUsers(), listOperationStores(), listStoreContextResolutions()]); users.value = userResult.items; stores.value = storeResult.items; resolutions.value = resolutionResult.items }
  catch (error) { loadError.value = apiErrorMessage(error) }
  finally { loading.value = false }
}
const validateAssignment = (selectedRoles: RoleName[]): string => {
  if (!selectedRoles.length) return '至少分配一个角色。'
  return ''
}
const requireDefault = (selectedRoles: RoleName[], storeIds: number[], defaultId: number | null): string => {
  if (selectedRoles.includes('CUSTOMER_SERVICE') && storeIds.length && (!defaultId || !storeIds.includes(defaultId))) return '已绑定客服店铺时必须指定一个默认店铺。'
  return ''
}
const userName = (userId: string) => users.value.find((item) => item.id === userId)?.display_name ?? userId
const storeName = (storeId: number | null) => stores.value.find((item) => item.store_ref === storeId)?.store_name ?? (storeId ? String(storeId) : '未选择')
const submitCreate = async () => {
  formError.value = validateAssignment(draft.roles) || requireDefault(draft.roles, draft.storeIds, draft.defaultStoreId); if (formError.value) return
  saving.value = true
  try {
    await createUser({ username: draft.username, password: draft.password, display_name: draft.displayName, roles: draft.roles,
      store_bindings: draft.roles.includes('CUSTOMER_SERVICE')
        ? draft.storeIds.map((store_id) => ({ store_id, is_default: store_id === draft.defaultStoreId })) : [] })
    Object.assign(draft, { username: '', displayName: '', password: '', roles: ['CUSTOMER_SERVICE'], storeIds: [], defaultStoreId: null }); await load()
  } catch (error) { formError.value = apiErrorMessage(error) }
  finally { saving.value = false }
}
const startEdit = (item: AuthUser) => { editing.value = item; editRoles.value = [...item.roles]; editStoreIds.value = item.stores.map((store) => store.store_id); editDefaultStoreId.value = item.stores.find((store) => store.is_default)?.store_id ?? null; editError.value = '' }
const saveAssignment = async () => {
  if (!editing.value) return
  editError.value = validateAssignment(editRoles.value) || requireDefault(editRoles.value, editStoreIds.value, editDefaultStoreId.value); if (editError.value) return
  saving.value = true
  try {
    const bindings = editRoles.value.includes('CUSTOMER_SERVICE')
      ? editStoreIds.value.map((store_id) => ({ store_id, is_default: store_id === editDefaultStoreId.value })) : []
    await assignUserRoles(editing.value.id, editRoles.value)
    await assignUserStores(editing.value.id, bindings)
    editing.value = null; await load()
  } catch (error) { editError.value = apiErrorMessage(error) }
  finally { saving.value = false }
}
const disable = async (item: AuthUser) => { if (!confirm(`确认停用 ${item.display_name}？其会话将立即失效。`)) return; await deactivateUser(item.id); await load() }
onMounted(load)
</script>

<style scoped>
.user-management{display:grid;gap:18px}.user-management>header{display:flex;justify-content:space-between;align-items:end}.user-management h1,.user-management h2,.user-management p{margin:0}.user-management header p{color:#6c7d92}.boundary{padding:12px 14px;border-radius:10px;background:#fff5dc;color:#76520c}.card{padding:18px;border:1px solid #dde5f0;border-radius:14px;background:#fff}.create-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.create-form h2,.create-form fieldset,.create-form .error{grid-column:1/-1}.card label{display:grid;gap:6px}.card input,.card select{padding:9px;border:1px solid #cbd6e5;border-radius:8px}.card fieldset{display:flex;gap:18px;border:0;padding:0}.card fieldset label{display:flex;flex-direction:row;align-items:center}.card button{margin-right:7px;padding:8px 12px;border:0;border-radius:8px;background:#285b9e;color:#fff}.card button.danger{background:#a63a36}table{width:100%;border-collapse:collapse}th,td{padding:11px;border-bottom:1px solid #e5eaf1;text-align:left}td small{display:block;color:#718096}.assignment{display:grid;gap:14px}.error{color:#b42318}@media(max-width:800px){.create-form{grid-template-columns:1fr}}
</style>
