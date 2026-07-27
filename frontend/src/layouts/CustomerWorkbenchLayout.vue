<template>
  <div class="workbench-layout" data-testid="workbench-layout">
    <aside class="workbench-sidebar" :class="{ open: mobileMenuOpen }" data-testid="workbench-sidebar">
      <div class="brand-block">
        <span class="brand-mark" aria-hidden="true">AI</span>
        <div>
          <strong>AI客服平台</strong>
          <small>客服工作台</small>
        </div>
      </div>

      <nav class="primary-nav" aria-label="工作台导航">
        <RouterLink to="/" class="nav-link" exact-active-class="active" @click="closeMobileMenu">
          <span>⌂</span><span>首页</span>
        </RouterLink>
        <RouterLink to="/ai-chat" class="nav-link" active-class="active" @click="closeMobileMenu">
          <span>AI</span><span>AI 客服</span>
        </RouterLink>
        <RouterLink to="/experience-cases" class="nav-link" active-class="active" @click="closeMobileMenu">
          <span>☆</span><span>我的案例</span>
        </RouterLink>
        <RouterLink to="/feedback" class="nav-link" active-class="active" @click="closeMobileMenu">
          <span>!</span><span>问题反馈</span>
        </RouterLink>
      </nav>

      <div class="secondary-nav" aria-label="帮助与改进">
        <small>帮助与改进</small>
        <RouterLink to="/suggestions" @click="closeMobileMenu">提交意见建议</RouterLink>
        <RouterLink to="/suggestions/mine" @click="closeMobileMenu">我的建议</RouterLink>
      </div>

      <div class="sidebar-boundary">
        <strong>测试工作台</strong>
        <p>不是正式登录系统，不执行退款、补发或自动发送。</p>
        <dl class="runtime-identity" data-testid="customer-runtime-identity">
          <div><dt>产品</dt><dd>{{ runtimeIdentity.productName }}</dd></div>
          <div><dt>版本</dt><dd>{{ runtimeIdentity.version }}</dd></div>
          <div><dt>Git</dt><dd>{{ runtimeIdentity.gitShortSha }}</dd></div>
          <div><dt>运行</dt><dd>{{ runtimeIdentity.runMode }}</dd></div>
          <div><dt>API</dt><dd>{{ runtimeIdentity.apiMode }}</dd></div>
        </dl>
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
          <small>AI客服平台 · 当前位置</small>
          <strong>{{ currentTitle }}</strong>
        </div>

        <div class="global-status" data-testid="global-system-status">
          <span :class="{ ready: systemStatus.aiReady.value }">
            <i />AI {{ systemStatus.aiReady.value ? '可用' : '待连接' }}
          </span>
          <span :class="{ ready: systemStatus.dataReady.value }">
            <i />平台 {{ systemStatus.dataReady.value ? '可用' : '待连接' }}
          </span>
          <span class="local-status"><i />客服 当前页面</span>
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
        <button
          class="technical-toggle"
          type="button"
          :aria-expanded="showProductDetails"
          data-testid="product-technical-toggle"
          @click="showProductDetails = !showProductDetails"
        >
          {{ showProductDetails ? '收起技术信息' : '技术信息' }}
        </button>
      </header>

      <div class="test-banner" data-testid="global-test-banner">
        <strong>测试环境</strong>
        <span>仅供内部验证，禁止填写真实客户隐私；所有业务动作都需要人工确认。</span>
      </div>

      <section v-if="showProductDetails" class="product-technical-panel" data-testid="product-technical-details">
        <div><span>产品版本</span><code>{{ runtimeDetails.frontendVersion }}</code></div>
        <div><span>Git Commit</span><code>{{ runtimeDetails.gitCommit }}</code></div>
        <div><span>启动模式</span><code>{{ runtimeDetails.startMode }}</code></div>
        <div><span>API 模式</span><code>{{ runtimeDetails.apiMode }}</code></div>
        <div><span>客服入口</span><code>{{ runtimeDetails.customerEntry }}</code></div>
        <p>AI 与平台状态来自现有健康检查；“客服当前页面”仅表示本页面已打开，不代表新增客服服务健康接口。</p>
      </section>

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

    <el-dialog
      v-model="pilotGuideOpen"
      title="AI客服助手（测试版）"
      width="min(560px, calc(100vw - 32px))"
      data-testid="pilot-guide-dialog"
      @close="dismissPilotGuide"
    >
      <p class="pilot-guide-intro">这是辅助客服工具，请按以下流程完成一条建议回复。</p>
      <ol class="pilot-guide-steps">
        <li>选择商品 / SKU</li>
        <li>输入客户问题</li>
        <li>查看 AI 建议</li>
        <li>人工确认后复制发送</li>
        <li>好回复可以收藏为优秀案例</li>
      </ol>
      <el-alert
        title="AI 建议需要人工确认"
        description="系统不会自动发送消息、自动退款或修改订单。"
        type="warning"
        :closable="false"
        show-icon
      />
      <template #footer>
        <el-button type="primary" data-testid="pilot-guide-start" @click="dismissPilotGuide">
          我知道了，开始使用
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
const pilotGuideOpen = ref(false)
const showProductDetails = ref(false)
const identityStore = createTesterIdentityStore()
const identity = identityStore.identity
const systemStatus = createSystemStatusStore()

provide(TesterIdentityKey, identityStore)
provide(SystemStatusKey, systemStatus)

const identityDraft = reactive({
  reporterName: identity.value.reporterName,
  defaultStoreCode: identity.value.defaultStoreCode
})

const PILOT_GUIDE_STORAGE_KEY = 'mumu-customer-workspace:pilot-guide-seen'

const runtimeIdentity = {
  productName: '木木小树 AI 客服工作台',
  version: import.meta.env.VITE_FRONTEND_VERSION ?? 'unavailable',
  gitShortSha: import.meta.env.VITE_GIT_SHORT_SHA ?? 'unavailable',
  runMode: import.meta.env.VITE_RUNTIME_RUN_MODE ?? 'unavailable',
  apiMode: import.meta.env.VITE_RUNTIME_API_MODE ?? 'unavailable'
}

const runtimeDetails = {
  frontendVersion: import.meta.env.VITE_FRONTEND_VERSION ?? 'unavailable',
  gitCommit: import.meta.env.VITE_GIT_SHORT_SHA ?? 'unavailable',
  startMode: import.meta.env.VITE_RUNTIME_RUN_MODE ?? 'unavailable',
  apiMode: import.meta.env.VITE_RUNTIME_API_MODE ?? 'unavailable',
  customerEntry: import.meta.env.VITE_CUSTOMER_ENTRY_URL ?? `${window.location.origin}/`
}

const shouldShowPilotGuide = () => {
  try {
    return globalThis.localStorage?.getItem(PILOT_GUIDE_STORAGE_KEY) !== 'true'
  } catch {
    return true
  }
}

const dismissPilotGuide = () => {
  pilotGuideOpen.value = false
  try {
    globalThis.localStorage?.setItem(PILOT_GUIDE_STORAGE_KEY, 'true')
  } catch {
    // A restricted browser can show the safety guide again next time.
  }
}

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
  pilotGuideOpen.value = shouldShowPilotGuide()
}

watch(() => route.fullPath, closeMobileMenu)

onMounted(() => {
  identityStore.reload()
  identityDraft.reporterName = identity.value.reporterName
  identityDraft.defaultStoreCode = identity.value.defaultStoreCode
  identityDialogOpen.value = !identity.value.reporterName
  pilotGuideOpen.value = Boolean(identity.value.reporterName) && shouldShowPilotGuide()
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
  font-size: 13px;
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

.secondary-nav {
  display: grid;
  gap: 8px;
  margin-top: 22px;
  padding: 0 10px;
}

.secondary-nav small {
  color: #91a7ca;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .06em;
}

.secondary-nav a {
  color: #b9c9e0;
  font-size: 12px;
  text-decoration: none;
}

.secondary-nav a:hover,
.secondary-nav a.router-link-active { color: #fff; }

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
.runtime-identity { display: grid; gap: 5px; margin: 13px 0 0; padding-top: 11px; border-top: 1px solid rgb(160 183 220 / 22%); }
.runtime-identity div { display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 6px; }
.runtime-identity dt { color: #91a7ca; font-size: 10px; }
.runtime-identity dd { min-width: 0; margin: 0; overflow: hidden; color: #d8e5fa; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

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
.global-status .local-status { color: #536981; }
.global-status .local-status i { background: #7c8ca3; }
.global-status button,
.tester-summary button,
.technical-toggle {
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

.technical-toggle { flex: 0 0 auto; }

.product-technical-panel {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px 14px;
  padding: 12px 22px;
  border-bottom: 1px solid #dce6f2;
  background: #f7faff;
}

.product-technical-panel div { display: grid; gap: 3px; min-width: 0; }
.product-technical-panel span,
.product-technical-panel p { color: #6b7b91; font-size: 11px; }
.product-technical-panel code { overflow: hidden; color: #2d4364; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.product-technical-panel p { grid-column: 1 / -1; margin: 0; line-height: 1.5; }

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
.pilot-guide-intro { margin: 0 0 12px; color: #52627a; }
.pilot-guide-steps { display: grid; gap: 9px; margin: 0 0 18px; padding-left: 24px; color: #203555; line-height: 1.5; }
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
  .product-technical-panel { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 720px) {
  .workbench-layout { min-height: 520px; }
  .workbench-topbar { gap: 10px; padding: 9px 12px; }
  .current-module { display: none; }
  .global-status span { font-size: 0; }
  .global-status span::after { font-size: 11px; content: '状态'; }
  .tester-summary { gap: 8px; padding-left: 8px; }
  .tester-summary > div:nth-child(2) { display: none; }
  .technical-toggle { display: none; }
  .test-banner { align-items: flex-start; padding: 7px 12px; line-height: 1.4; }
  .workbench-content { padding: 12px; }
  .product-technical-panel { grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 12px; }
}
</style>
