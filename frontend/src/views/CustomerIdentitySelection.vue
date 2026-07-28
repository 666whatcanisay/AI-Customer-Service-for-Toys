<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { CustomerIdentity } from '@/api/customerIdentityTypes'
import { useCustomerIdentity } from '@/workspace/customerIdentity'

const store = useCustomerIdentity()
const choices = ref<CustomerIdentity[]>([])
const loadingChoices = ref(false)
const selectedUserId = ref('')

const selected = computed(() => choices.value.find((item) => item.userId === selectedUserId.value) ?? null)

async function load(): Promise<void> {
  loadingChoices.value = true
  choices.value = await store.loadSelectable()
  if (choices.value.length === 1) selectedUserId.value = choices.value[0].userId
  loadingChoices.value = false
}

function continueToWorkbench(): void {
  if (!selected.value) return
  store.select(selected.value)
}

onMounted(() => { void load() })
</script>

<template>
  <main class="identity-page" data-testid="customer-identity-selection">
    <section class="identity-card">
      <div class="brand"><span>AI</span><div><strong>AI 客服平台</strong><small>客服工作台</small></div></div>
      <p class="eyebrow">内部试运行 · 身份选择</p>
      <h1>先选择你的客服身份</h1>
      <p class="intro">选择运营后台已配置的客服身份后，才能进入工作台。系统会记录案例、问题反馈和效率事件的来源；不会保存密码，也不是正式登录或权限认证。</p>

      <p v-if="store.error.value" class="notice error" role="alert">{{ store.error.value }}</p>
      <p v-else-if="loadingChoices || store.loading.value" class="notice" role="status">正在读取可用客服身份…</p>
      <p v-else-if="choices.length === 0" class="notice warning">暂无可用客服身份。请让运营人员先在 5174 的“客服用户”中创建并启用客服、绑定店铺后再刷新。</p>

      <div v-else class="identity-list" aria-label="可选客服身份">
        <button
          v-for="choice in choices"
          :key="choice.userId"
          class="identity-option"
          :class="{ selected: selectedUserId === choice.userId }"
          type="button"
          @click="selectedUserId = choice.userId"
        >
          <span class="radio" aria-hidden="true" />
          <span><strong>{{ choice.displayName }}</strong><small>{{ choice.defaultStoreCode }} · {{ choice.storeBindings.length }} 家已绑定店铺</small></span>
        </button>
      </div>

      <div class="actions">
        <button class="secondary" type="button" :disabled="loadingChoices || store.loading.value" @click="load">刷新身份列表</button>
        <button class="primary" type="button" :disabled="!selected" @click="continueToWorkbench">进入客服工作台</button>
      </div>
      <p class="boundary">AI 只提供建议，回复仍需人工确认、修改和复制；系统不会自动发送客户消息、退款或修改订单。</p>
    </section>
  </main>
</template>

<style scoped>
.identity-page { display: grid; min-height: 100vh; place-items: center; padding: 24px; color: #172033; background: radial-gradient(circle at 12% 8%, rgb(91 145 238 / 20%), transparent 28rem), #edf2f8; }.identity-card { width: min(620px, 100%); padding: clamp(24px, 5vw, 44px); border: 1px solid #d5e1ef; border-radius: 22px; background: #fff; box-shadow: 0 24px 60px rgb(29 56 101 / 14%); }.brand { display: flex; align-items: center; gap: 10px; }.brand > span { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 11px; color: #10264b; background: linear-gradient(135deg, #6fa1ff, #53d1b1); font-size: 12px; font-weight: 900; }.brand strong, .brand small { display: block; }.brand strong { font-size: 15px; }.brand small { margin-top: 2px; color: #73819a; font-size: 11px; }.eyebrow { margin: 28px 0 7px; color: #2d64cc; font-size: 12px; font-weight: 800; letter-spacing: .08em; } h1 { margin: 0 0 10px; font-size: clamp(26px, 4vw, 34px); }.intro { margin: 0; color: #64738b; line-height: 1.65; }.notice { margin: 20px 0; padding: 12px; border-radius: 10px; color: #3e5a7c; background: #eef5ff; line-height: 1.55; }.notice.error { color: #943a36; background: #fff1f0; }.notice.warning { color: #805d13; background: #fff8e6; }.identity-list { display: grid; gap: 10px; margin-top: 22px; }.identity-option { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 11px; width: 100%; padding: 15px; border: 1px solid #d8e3f0; border-radius: 12px; color: #263c5e; background: #fff; text-align: left; cursor: pointer; }.identity-option:hover, .identity-option.selected { border-color: #75a2eb; background: #f2f7ff; }.radio { width: 16px; height: 16px; border: 2px solid #9bb1ce; border-radius: 50%; }.selected .radio { border: 5px solid #316ed2; }.identity-option strong, .identity-option small { display: block; }.identity-option small { margin-top: 4px; color: #708097; font-size: 12px; }.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; margin-top: 22px; }.actions button { min-height: 40px; padding: 8px 14px; border: 1px solid #c4d3e6; border-radius: 9px; font: inherit; font-weight: 800; cursor: pointer; }.actions .primary { border-color: #2e63d5; color: #fff; background: #2e63d5; }.actions .secondary { color: #34547c; background: #fff; }.actions button:disabled { cursor: not-allowed; opacity: .55; }.boundary { margin: 20px 0 0; padding-top: 16px; border-top: 1px solid #e2e9f2; color: #718096; font-size: 12px; line-height: 1.6; }
</style>
