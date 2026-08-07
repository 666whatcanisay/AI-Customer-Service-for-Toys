<template>
  <section class="user-management" data-testid="user-management-page">
    <header class="page-heading">
      <div>
        <p>系统 · 身份与权限</p>
        <h1>用户管理</h1>
        <span>快速查看人员岗位和负责店铺。</span>
      </div>
      <div class="page-actions">
        <button type="button" class="secondary" @click="load">刷新</button>
        <button type="button" data-testid="open-create-user" @click="openCreate">创建用户</button>
      </div>
    </header>

    <p class="boundary">权限由服务端校验。客服可以负责多个店铺，并且需要指定一个默认店铺；运营和管理员默认拥有全部店铺范围。</p>

    <section class="card user-list-card">
      <div class="section-heading">
        <div><h2>用户列表</h2><p>共 {{ users.length }} 人</p></div>
      </div>
      <p v-if="loading" class="empty-state">正在加载…</p>
      <p v-else-if="loadError" class="error" role="alert">{{ loadError }}</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>用户</th><th>岗位</th><th>负责店铺</th><th>密码</th><th>状态</th><th class="action-column">操作</th></tr></thead>
          <tbody><tr v-for="item in users" :key="item.id">
            <td><strong>{{ item.display_name }}</strong><small>{{ item.username }}</small></td>
            <td><div class="chips"><span v-for="role in item.roles" :key="role" class="chip">{{ roleLabel(role) }}</span></div></td>
            <td class="store-scope">{{ storeScope(item) }}</td>
            <td>{{ item.must_change_password ? '首次登录需修改' : '已更新' }}</td>
            <td><span class="status-pill" :class="item.status === 'ACTIVE' ? 'active' : 'disabled'">{{ item.status === 'ACTIVE' ? '启用' : '停用' }}</span></td>
            <td class="row-actions">
              <button type="button" class="small secondary" :data-testid="`edit-user-${item.id}`" @click="startProfileEdit(item)">编辑资料</button>
              <button type="button" class="small" :data-testid="`assign-user-${item.id}`" @click="startEdit(item)">修改分配</button>
              <button v-if="item.status === 'ACTIVE'" type="button" class="small danger" @click="disable(item)">停用</button>
            </td>
          </tr></tbody>
        </table>
      </div>
    </section>

    <details class="card audit" data-testid="store-context-audit">
      <summary><span>商品识别记录</span><small>{{ resolutions.length }} 条</small></summary>
      <div class="audit-content">
        <p v-if="!resolutions.length" class="empty-state">暂无识别记录。</p>
        <div v-else class="table-wrap"><table><thead><tr><th>时间</th><th>客服</th><th>店铺</th><th>商品 / SKU</th><th>结果</th></tr></thead>
          <tbody><tr v-for="item in resolutions" :key="item.resolution_id">
            <td>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</td>
            <td>{{ userName(item.user_id) }}</td><td>{{ storeName(item.store_id) }}</td>
            <td>{{ item.product_id ?? '未识别' }} / {{ item.sku_id ?? '无或待确认' }}</td>
            <td>{{ item.status }} · {{ item.reason_code }}</td>
          </tr></tbody>
        </table></div>
        <small>仅展示实体标识和解析结果；系统不保存或展示客户消息原文。</small>
      </div>
    </details>

    <div v-if="createOpen" class="modal-backdrop" data-testid="create-user-modal" @click.self="closeCreate" @keydown.esc="closeCreate">
      <form class="modal" data-testid="create-user-form" role="dialog" aria-modal="true" aria-labelledby="create-user-title" @submit.prevent="submitCreate">
        <header class="modal-heading"><div><p>新增公司人员</p><h2 id="create-user-title">创建用户</h2></div><button type="button" class="icon-button" aria-label="关闭创建用户弹窗" @click="closeCreate">×</button></header>
        <div class="modal-body">
          <div class="form-grid">
            <label>账号<input v-model.trim="draft.username" type="text" required minlength="1" maxlength="64" /><small>支持中文、大小写字母、数字及 . _ -</small></label>
            <label>显示姓名<input v-model.trim="draft.displayName" type="text" required maxlength="80" /></label>
            <label class="wide">临时初始密码<input v-model="draft.password" type="password" required minlength="8" maxlength="128" autocomplete="new-password" /><small>至少8位；员工首次登录后必须修改。</small></label>
          </div>
          <fieldset><legend>岗位</legend><div class="option-grid"><label v-for="role in roles" :key="role" class="choice"><input v-model="draft.roles" type="checkbox" :value="role" />{{ roleLabel(role) }}</label></div></fieldset>
          <UserStoreBindingFields
            v-if="draft.roles.includes('CUSTOMER_SERVICE')"
            mode="create"
            :stores="stores"
            :selected-store-ids="draft.storeIds"
            :default-store-id="draft.defaultStoreId"
            @toggle="toggleDraftStore"
            @default="draft.defaultStoreId = $event"
          />
          <p v-else class="scope-note">管理员或运营按岗位自动拥有全部店铺权限，无需逐个绑定。</p>
          <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        </div>
        <footer class="modal-actions"><button type="button" class="secondary" @click="closeCreate">取消</button><button type="submit" :disabled="saving">{{ saving ? '创建中…' : '创建用户' }}</button></footer>
      </form>
    </div>

    <div v-if="profileEditing" class="modal-backdrop" data-testid="user-profile-modal" @click.self="closeProfileEdit" @keydown.esc="closeProfileEdit">
      <form class="modal compact-modal" data-testid="user-profile-form" role="dialog" aria-modal="true" aria-labelledby="profile-title" @submit.prevent="saveProfile">
        <header class="modal-heading"><div><p>修改用户信息</p><h2 id="profile-title">编辑资料 · {{ profileEditing.display_name }}</h2></div><button type="button" class="icon-button" aria-label="关闭编辑资料弹窗" @click="closeProfileEdit">×</button></header>
        <div class="modal-body">
          <div class="form-grid single-column">
            <label>登录账号<span class="readonly-value">{{ profileEditing.username }}</span><small>登录账号用于身份和审计关联，创建后不可修改。</small></label>
            <label>显示姓名<input v-model.trim="profileDraft.displayName" type="text" required maxlength="80" /></label>
            <label>重置临时密码<input v-model="profileDraft.password" type="password" minlength="8" maxlength="128" autocomplete="new-password" placeholder="不修改密码请留空" /><small>填写后将撤销该用户所有登录状态，并要求下次登录重新设置密码。</small></label>
          </div>
          <p v-if="profileError" class="error" role="alert">{{ profileError }}</p>
        </div>
        <footer class="modal-actions"><button type="button" class="secondary" @click="closeProfileEdit">取消</button><button type="submit" :disabled="saving">{{ saving ? '保存中…' : (profileDraft.password ? '保存并重置密码' : '保存资料') }}</button></footer>
      </form>
    </div>

    <div v-if="editing" class="modal-backdrop" data-testid="user-assignment-modal" @click.self="closeAssignment" @keydown.esc="closeAssignment">
      <form class="modal" data-testid="user-assignment-form" role="dialog" aria-modal="true" aria-labelledby="assignment-title" @submit.prevent="saveAssignment">
        <header class="modal-heading"><div><p>修改人员权限</p><h2 id="assignment-title">角色与店铺 · {{ editing.display_name }}</h2></div><button type="button" class="icon-button" aria-label="关闭分配弹窗" @click="closeAssignment">×</button></header>
        <div class="modal-body">
          <fieldset><legend>岗位</legend><div class="option-grid"><label v-for="role in roles" :key="role" class="choice"><input v-model="editRoles" type="checkbox" :value="role" />{{ roleLabel(role) }}</label></div></fieldset>
          <UserStoreBindingFields
            v-if="editRoles.includes('CUSTOMER_SERVICE')"
            mode="edit"
            :stores="stores"
            :selected-store-ids="editStoreIds"
            :default-store-id="editDefaultStoreId"
            @toggle="toggleEditStore"
            @default="editDefaultStoreId = $event"
          />
          <p v-else class="scope-note">当前岗位自动拥有全部店铺权限，不需要逐个绑定客服店铺。</p>
          <p v-if="editError" class="error" role="alert">{{ editError }}</p>
        </div>
        <footer class="modal-actions"><button type="button" class="secondary" @click="closeAssignment">取消</button><button type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存分配' }}</button></footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { AuthUser, RoleName } from '../auth/session'
import UserStoreBindingFields from '../components/UserStoreBindingFields.vue'
import {
  apiErrorMessage, assignUserRoles, assignUserStores, createUser, deactivateUser,
  listOperationStores, listStoreContextResolutions, listUsers, updateUser,
  type StoreContextResolutionAudit, type StoreOperationItem,
} from '../api/client'

const roles: RoleName[] = ['ADMIN', 'OPERATOR', 'CUSTOMER_SERVICE']
const users = ref<AuthUser[]>([])
const stores = ref<StoreOperationItem[]>([])
const resolutions = ref<StoreContextResolutionAudit[]>([])
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const formError = ref('')
const editError = ref('')
const profileError = ref('')
const createOpen = ref(false)
const profileEditing = ref<AuthUser | null>(null)
const editing = ref<AuthUser | null>(null)
const editRoles = ref<RoleName[]>([])
const editStoreIds = ref<number[]>([])
const editDefaultStoreId = ref<number | null>(null)
const draft = reactive({ username: '', displayName: '', password: '', roles: ['CUSTOMER_SERVICE'] as RoleName[], storeIds: [] as number[], defaultStoreId: null as number | null })
const profileDraft = reactive({ displayName: '', password: '' })

const roleLabel = (role: RoleName) => ({ ADMIN: '管理员', OPERATOR: '运营', CUSTOMER_SERVICE: '客服' })[role]
const storeScope = (item: AuthUser) => item.all_store_access
  ? '全部店铺'
  : (item.stores.map((store) => `${store.store_name}${store.is_default ? '（默认）' : ''}`).join('、') || '待选择')
const normalizedDefault = (storeIds: number[], current: number | null): number | null => (
  current !== null && storeIds.includes(current) ? current : storeIds[0] ?? null
)

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [userResult, storeResult, resolutionResult] = await Promise.all([listUsers(), listOperationStores(), listStoreContextResolutions()])
    users.value = userResult.items
    stores.value = storeResult.items
    resolutions.value = resolutionResult.items
  } catch (error) { loadError.value = apiErrorMessage(error) }
  finally { loading.value = false }
}
const validateAssignment = (selectedRoles: RoleName[]): string => selectedRoles.length ? '' : '至少分配一个岗位。'
const requireDefault = (selectedRoles: RoleName[], storeIds: number[], defaultId: number | null): string => {
  if (selectedRoles.includes('CUSTOMER_SERVICE') && storeIds.length && (defaultId === null || !storeIds.includes(defaultId))) return '请选择一个默认店铺。'
  return ''
}
const userName = (userId: string) => users.value.find((item) => item.id === userId)?.display_name ?? userId
const storeName = (storeId: number | null) => stores.value.find((item) => item.store_ref === storeId)?.store_name ?? (storeId ? String(storeId) : '未选择')
const resetDraft = () => Object.assign(draft, { username: '', displayName: '', password: '', roles: ['CUSTOMER_SERVICE'], storeIds: [], defaultStoreId: null })
const openCreate = () => { resetDraft(); formError.value = ''; createOpen.value = true }
const closeCreate = () => { if (!saving.value) { draft.password = ''; createOpen.value = false } }
const closeProfileEdit = () => { if (!saving.value) { profileDraft.password = ''; profileEditing.value = null } }
const closeAssignment = () => { if (!saving.value) editing.value = null }
const toggleStore = (storeIds: number[], storeId: number): number[] => storeIds.includes(storeId)
  ? storeIds.filter((item) => item !== storeId)
  : [...storeIds, storeId]
const toggleDraftStore = (storeId: number) => {
  draft.storeIds = toggleStore(draft.storeIds, storeId)
  draft.defaultStoreId = normalizedDefault(draft.storeIds, draft.defaultStoreId)
  formError.value = ''
}
const toggleEditStore = (storeId: number) => {
  editStoreIds.value = toggleStore(editStoreIds.value, storeId)
  editDefaultStoreId.value = normalizedDefault(editStoreIds.value, editDefaultStoreId.value)
  editError.value = ''
}
const submitCreate = async () => {
  formError.value = validateAssignment(draft.roles) || requireDefault(draft.roles, draft.storeIds, draft.defaultStoreId)
  if (formError.value) return
  saving.value = true
  try {
    await createUser({
      username: draft.username, password: draft.password, display_name: draft.displayName, roles: draft.roles,
      store_bindings: draft.roles.includes('CUSTOMER_SERVICE')
        ? draft.storeIds.map((store_id) => ({ store_id, is_default: store_id === draft.defaultStoreId })) : [],
    })
    createOpen.value = false
    resetDraft()
    await load()
  } catch (error) { formError.value = apiErrorMessage(error) }
  finally { saving.value = false }
}
const startProfileEdit = (item: AuthUser) => {
  profileEditing.value = item
  profileDraft.displayName = item.display_name
  profileDraft.password = ''
  profileError.value = ''
}
const saveProfile = async () => {
  if (!profileEditing.value) return
  const displayName = profileDraft.displayName.trim()
  if (!displayName) { profileError.value = '显示姓名不能为空。'; return }
  if (profileDraft.password && profileDraft.password.length < 8) { profileError.value = '临时密码至少需要8位。'; return }
  const input: { display_name?: string; password?: string } = {}
  if (displayName !== profileEditing.value.display_name) input.display_name = displayName
  if (profileDraft.password) input.password = profileDraft.password
  if (!Object.keys(input).length) { profileError.value = '没有需要保存的变更。'; return }
  saving.value = true
  try {
    await updateUser(profileEditing.value.id, input)
    profileEditing.value = null
    profileDraft.password = ''
    await load()
  } catch (error) { profileError.value = apiErrorMessage(error) }
  finally { saving.value = false }
}
const startEdit = (item: AuthUser) => {
  editing.value = item
  editRoles.value = [...item.roles]
  editStoreIds.value = item.stores.map((store) => store.store_id)
  editDefaultStoreId.value = normalizedDefault(editStoreIds.value, item.stores.find((store) => store.is_default)?.store_id ?? null)
  editError.value = ''
}
const saveAssignment = async () => {
  if (!editing.value) return
  editError.value = validateAssignment(editRoles.value) || requireDefault(editRoles.value, editStoreIds.value, editDefaultStoreId.value)
  if (editError.value) return
  saving.value = true
  try {
    const bindings = editRoles.value.includes('CUSTOMER_SERVICE')
      ? editStoreIds.value.map((store_id) => ({ store_id, is_default: store_id === editDefaultStoreId.value })) : []
    await assignUserRoles(editing.value.id, editRoles.value)
    await assignUserStores(editing.value.id, bindings)
    editing.value = null
    await load()
  } catch (error) { editError.value = apiErrorMessage(error) }
  finally { saving.value = false }
}
const disable = async (item: AuthUser) => { if (!confirm(`确认停用 ${item.display_name}？其会话将立即失效。`)) return; await deactivateUser(item.id); await load() }
onMounted(load)
</script>

<style scoped>
.user-management{display:grid;gap:16px}.page-heading{display:flex;justify-content:space-between;align-items:flex-end;gap:18px}.page-heading h1,.page-heading p,.page-heading span,.section-heading h2,.section-heading p{margin:0}.page-heading p,.page-heading span,.section-heading p{color:#6c7d92}.page-heading h1{margin:3px 0;font-size:30px}.page-actions{display:flex;gap:9px}.boundary{margin:0;padding:11px 14px;border:1px solid #f1d99c;border-radius:10px;background:#fff8e7;color:#76520c}.card{padding:18px;border:1px solid #dde5f0;border-radius:14px;background:#fff;box-shadow:0 8px 24px rgba(37,65,105,.04)}.section-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.section-heading>div{display:flex;align-items:baseline;gap:10px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:11px 10px;border-bottom:1px solid #e8edf4;text-align:left;vertical-align:middle}th{color:#56677b;font-size:13px;font-weight:650}tbody tr:hover{background:#f8faff}td small{display:block;margin-top:2px;color:#718096}.action-column{width:270px}.row-actions{white-space:nowrap}.store-scope{max-width:300px}.chips{display:flex;flex-wrap:wrap;gap:5px}.chip,.status-pill{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:13px}.chip{background:#edf4ff;color:#285b9e}.status-pill.active{background:#e8f7ee;color:#237a43}.status-pill.disabled{background:#f1f3f6;color:#6b7280}button{padding:9px 14px;border:0;border-radius:8px;background:#285b9e;color:#fff;font-weight:600;cursor:pointer}button:hover{filter:brightness(.96)}button:disabled{cursor:not-allowed;opacity:.6}button.secondary{border:1px solid #cbd6e5;background:#fff;color:#334a67}button.small{padding:7px 10px}button.danger{background:#a63a36}.empty-state{margin:18px 0;color:#718096}.error{margin:0;color:#b42318}.audit{padding:0}.audit summary{display:flex;justify-content:space-between;padding:16px 18px;cursor:pointer;font-weight:700;list-style:none}.audit summary::-webkit-details-marker{display:none}.audit summary small{color:#718096;font-weight:500}.audit-content{padding:0 18px 18px}.modal-backdrop{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:24px;background:rgba(15,35,63,.48);backdrop-filter:blur(2px)}.modal{width:min(680px,100%);max-height:calc(100vh - 48px);overflow:auto;border-radius:16px;background:#fff;box-shadow:0 24px 70px rgba(14,31,53,.28)}.compact-modal{width:min(560px,100%)}.modal-heading{display:flex;justify-content:space-between;align-items:flex-start;padding:20px 22px 15px;border-bottom:1px solid #e8edf4}.modal-heading p,.modal-heading h2{margin:0}.modal-heading p{margin-bottom:3px;color:#718096;font-size:13px}.icon-button{padding:2px 9px;background:transparent;color:#607087;font-size:26px;line-height:1}.modal-body{display:grid;gap:18px;padding:20px 22px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.form-grid.single-column{grid-template-columns:1fr}.form-grid .wide{grid-column:1/-1}.modal label{display:grid;gap:6px}.modal input{padding:9px;border:1px solid #cbd6e5;border-radius:8px}.readonly-value{padding:10px 11px;border:1px solid #e1e6ed;border-radius:8px;background:#f5f7fa;color:#556579}.modal fieldset{margin:0;padding:0;border:0}.modal legend{margin-bottom:9px;font-weight:700}.option-grid{display:flex;flex-wrap:wrap;gap:8px}.choice{display:flex!important;grid-template-columns:none!important;flex-direction:row;align-items:center;gap:7px!important;padding:9px 12px;border:1px solid #dbe4ef;border-radius:9px;background:#f9fbfd}.choice input{margin:0;padding:0}.scope-note{margin:0;padding:11px 13px;border-radius:9px;background:#f4f7fa;color:#506177}.modal-actions{display:flex;justify-content:flex-end;gap:9px;padding:15px 22px;border-top:1px solid #e8edf4}.modal-actions button{min-width:98px}@media(max-width:900px){.page-heading{align-items:stretch;flex-direction:column}.page-actions{justify-content:flex-end}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}.action-column{width:auto}th,td{min-width:110px}.row-actions{min-width:270px}}@media(max-width:560px){.modal-backdrop{padding:10px}.modal{max-height:calc(100vh - 20px)}.page-actions button{flex:1}}
</style>
