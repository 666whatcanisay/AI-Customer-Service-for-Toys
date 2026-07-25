<template>
  <div class="workbench-layout" data-testid="workbench-layout">
    <aside class="workbench-sidebar" :class="{ open: mobileMenuOpen }" data-testid="workbench-sidebar">
      <div class="brand-block">
        <span class="brand-mark">木</span>
        <div>
          <strong>木木小栈</strong>
          <small>客服智能工作台</small>
        </div>
      </div>

      <nav class="primary-nav" aria-label="工作台导航">
        <RouterLink to="/" class="nav-link" exact-active-class="active" @click="closeMobileMenu">
          <span>⌂</span><span>工作台首页</span>
        </RouterLink>
        <RouterLink to="/ai-chat" class="nav-link" active-class="active" @click="closeMobileMenu">
          <span>AI</span><span>AI 客服</span>
        </RouterLink>
        <RouterLink to="/suggestions" class="nav-link" active-class="active" @click="closeMobileMenu">
          <span>✎</span><span>提交意见建议</span>
        </RouterLink>
        <RouterLink to="/suggestions/mine" class="nav-link" active-class="active" @click="closeMobileMenu">
          <span>☷</span><span>我的建议</span>
        </RouterLink>
      </nav>

      <div class="sidebar-boundary">
        <strong>测试工作台</strong>
        <p>不是正式登录系统，不执行退款、补发或自动发送。</p>
      </div>
    </aside>

    <button
      v-if="mobileMenuOpen"
      class="mobile-mask"
      type="button"
      aria-label="关闭菜单"
      @click="closeMobileMenu"
    />

    <section class="workbench-stage">
      <header class="workbench-topbar">
        <button
          class="menu-button"
          type="button"
          :aria-expanded="mobileMenuOpen"
          aria-label="打开工作台菜单"
          data-testid="mobile-menu-button"
          @click="mobileMenuOpen = !mobileMenuOpen"
        >
          ☰
        </button>

        <div class="current-module">
          <small>当前位置</small>
          <strong>{{ currentTitle }}</strong>
        </div>

        <div class="global-status" data-testid="global-system-status">
          <span :class="{ ready: systemStatus.aiReady.value }">
            <i />AI {{ systemStatus.aiReady.value ? '可用' : '待连接' }}
          </span>
          <span :class="{ ready: systemStatus.dataReady.value }">
            <i />数据 {{ systemStatus.dataReady.value ? '可用' : '待连接' }}
          </span>
          <button type="button" :disabled="systemStatus.loading.value" @click="systemStatus.refresh">
            {{ systemStatus.loading.value ? '检查中' : '刷新' }}
          </button>
        </div>

        <div class="tester-summary" data-testid="tester-summary">
          <div>
            <small>当前测试客服</small>
            <strong>{{ identity.reporterName || '尚未填写姓名' }}</strong>
          </div>
          <div>
            <small>负责店铺</small>
            <strong>{{ identity.defaultStoreCode || '未设置' }}</strong>
          </div>
          <button type="button" @click="openIdentityEditor">修改</button>
        </div>
      </header>

      <div class="test-banner" data-testid="global-test-banner">
        <strong>测试环境</strong>
        <span>仅供内部验证，禁止填写真实客户隐私；所有业务动作都需要人工确认。</span>
      </div>

      <main class="workbench-content">
        <RouterView />
      </main>
    </section>

    <el-dialog
      v-model="identityDialogOpen"
      title="设置测试客服身份"
      width="min(520px, calc(100vw - 32px))"
      :close-on-click-modal="Boolean(identity.reporterName)"
      :close-on-press-escape="Boolean(identity.reporterName)"
      :show-close="Boolean(identity.reporterName)"
      data-testid="identity-dialog"
    >
      <div class="identity-notice">
        这只是本机测试标识，不是登录或权限认证。请勿填写密码、电话、客户姓名或订单信息。
      </div>
      <label class="identity-field">
        <span>显示姓名 <em>必填</em></span>
        <el-input
          v-model="identityDraft.reporterName"
          data-testid="identity-name"
          maxlength="40"
          placeholder="例如：测试客服小木"
        />
      </label>
      <label class="identity-field">
        <span>默认店铺 <small>可选</small></span>
        <el-input
          v-model="identityDraft.defaultStoreCode"
          data-testid="identity-store"
          maxlength="64"
          placeholder="例如：PDD-SM"
        />
      </label>
      <p v-if="identityError" class="identity-error" data-testid="identity-error">
        {{ identityError }}
      </p>
      <template #footer>
        <el-button v-if="identity.reporterName" @click="identityDialogOpen = false">取消</el-button>
        <el-button type="primary" data-testid="identity-save" @click="saveIdentity">
          保存测试身份
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, reactive, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  TesterIdentityKey,
  createTesterIdentityStore
} from '@/workspace/testerIdentity'
import { SystemStatusKey, createSystemStatusStore } from '@/workspace/systemStatus'

const route = useRoute()
const mobileMenuOpen = ref(false)
const identityDialogOpen = ref(false)
const identityError = ref('')
const identityStore = createTesterIdentityStore()
const identity = identityStore.identity
const systemStatus = createSystemStatusStore()

provide(TesterIdentityKey, identityStore)
provide(SystemStatusKey, systemStatus)

const identityDraft = reactive({
  reporterName: identity.value.reporterName,
  defaultStoreCode: identity.value.defaultStoreCode
})

const currentTitle = computed(() => String(route.meta.title ?? '客服智能工作台'))

const closeMobileMenu = () => {
  mobileMenuOpen.value = false
}

const openIdentityEditor = () => {
  identityDraft.reporterName = identity.value.reporterName
  identityDraft.defaultStoreCode = identity.value.defaultStoreCode
  identityError.value = ''
  identityDialogOpen.value = true
}

const saveIdentity = () => {
  if (!identityDraft.reporterName.trim()) {
    identityError.value = '请填写一个用于内部测试的显示姓名。'
    return
  }
  identityStore.save(identityDraft.reporterName, identityDraft.defaultStoreCode)
  identityError.value = ''
  identityDialogOpen.value = false
}

watch(() => route.fullPath, closeMobileMenu)

onMounted(() => {
  identityStore.reload()
  identityDraft.reporterName = identity.value.reporterName
  identityDraft.defaultStoreCode = identity.value.defaultStoreCode
  identityDialogOpen.value = !identity.value.reporterName
  void systemStatus.refresh()
})
</script>

<style scoped>
.workbench-layout {
  --sidebar-width: 236px;
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  width: 100%;
  height: 100vh;
  min-height: 600px;
  overflow: hidden;
  color: #172033;
  background: #edf2f8;
}

.workbench-sidebar {
  position: relative;
  z-index: 30;
  display: flex;
  min-height: 0;
  flex-direction: column;
  padding: 22px 16px;
  color: #eaf1ff;
  background: linear-gradient(180deg, #14284d 0%, #0d1e3b 100%);
  box-shadow: 8px 0 28px rgb(18 40 77 / 12%);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 8px 22px;
}

.brand-mark {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 13px;
  background: linear-gradient(135deg, #6fa1ff, #53d1b1);
  color: #0e2344;
  font-size: 22px;
  font-weight: 900;
}

.brand-block strong,
.brand-block small {
  display: block;
}

.brand-block strong { font-size: 18px; }
.brand-block small { margin-top: 3px; color: #9fb2d1; font-size: 12px; }

.primary-nav {
  display: grid;
  gap: 7px;
}

.nav-link {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: center;
  min-height: 44px;
  padding: 7px 11px;
  border-radius: 11px;
  color: #bdcce3;
  text-decoration: none;
  transition: background 150ms ease, color 150ms ease;
}

.nav-link > span:first-child {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 8px;
  background: rgb(255 255 255 / 8%);
  font-size: 12px;
  font-weight: 800;
}

.nav-link:hover,
.nav-link.active {
  color: #fff;
  background: rgb(103 153 245 / 20%);
}

.nav-link.active > span:first-child { background: #6f9ff4; color: #10264b; }

.sidebar-boundary {
  margin-top: auto;
  padding: 14px;
  border: 1px solid rgb(160 183 220 / 22%);
  border-radius: 12px;
  background: rgb(255 255 255 / 6%);
}

.sidebar-boundary strong { font-size: 13px; }
.sidebar-boundary p { margin: 6px 0 0; color: #9fb2d1; font-size: 11px; line-height: 1.55; }

.workbench-stage {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}

.workbench-topbar {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 18px;
  min-height: 68px;
  padding: 10px 22px;
  border-bottom: 1px solid #d8e1ee;
  background: rgb(255 255 255 / 94%);
}

.menu-button {
  display: none;
  border: 0;
  background: transparent;
  color: #243d68;
  font-size: 24px;
  cursor: pointer;
}

.current-module small,
.tester-summary small {
  display: block;
  margin-bottom: 3px;
  color: #728099;
  font-size: 11px;
}

.current-module strong { white-space: nowrap; font-size: 16px; }

.global-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.global-status span {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #8a5a00;
  font-size: 12px;
}

.global-status i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e8a321;
}

.global-status span.ready { color: #20704d; }
.global-status span.ready i { background: #2da875; }
.global-status button,
.tester-summary button {
  padding: 5px 8px;
  border: 1px solid #ccd8e8;
  border-radius: 8px;
  background: #fff;
  color: #365174;
  cursor: pointer;
}

.tester-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-left: 16px;
  border-left: 1px solid #dce4ef;
}

.tester-summary strong { display: block; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }

.test-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 36px;
  padding: 7px 22px;
  border-bottom: 1px solid #f2d596;
  background: #fff8e7;
  color: #77510a;
  font-size: 12px;
}

.test-banner strong {
  padding: 2px 7px;
  border-radius: 999px;
  background: #e89a17;
  color: #fff;
}

.workbench-content {
  min-width: 0;
  min-height: 0;
  padding: 18px 22px 28px;
  overflow: auto;
}

.identity-notice {
  margin-bottom: 18px;
  padding: 12px;
  border-radius: 10px;
  background: #fff6e2;
  color: #77510a;
  font-size: 13px;
  line-height: 1.55;
}

.identity-field {
  display: grid;
  gap: 7px;
  margin-top: 14px;
  font-weight: 700;
}

.identity-field em { color: #c33d35; font-style: normal; font-size: 12px; }
.identity-field small { color: #748198; font-weight: 400; }
.identity-error { margin: 12px 0 0; color: #c33d35; font-size: 13px; }
.mobile-mask { display: none; }

@media (max-width: 980px) {
  .workbench-layout { grid-template-columns: 1fr; }
  .workbench-sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: min(280px, calc(100vw - 52px));
    transform: translateX(-105%);
    transition: transform 180ms ease;
  }
  .workbench-sidebar.open { transform: translateX(0); }
  .mobile-mask {
    position: fixed;
    z-index: 20;
    inset: 0;
    display: block;
    border: 0;
    background: rgb(6 18 39 / 48%);
  }
  .menu-button { display: block; }
  .global-status { margin-left: auto; }
}

@media (max-width: 720px) {
  .workbench-layout { min-height: 520px; }
  .workbench-topbar { gap: 10px; padding: 9px 12px; }
  .current-module { display: none; }
  .global-status span { font-size: 0; }
  .global-status span::after { font-size: 11px; content: '状态'; }
  .tester-summary { gap: 8px; padding-left: 8px; }
  .tester-summary > div:nth-child(2) { display: none; }
  .test-banner { align-items: flex-start; padding: 7px 12px; line-height: 1.4; }
  .workbench-content { padding: 12px; }
}
</style>
