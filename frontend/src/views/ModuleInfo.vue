<template>
  <div class="module-info-page" data-testid="module-info-page">
    <template v-if="module">
      <nav class="breadcrumb"><RouterLink to="/">工作台首页</RouterLink><span>/</span><span>{{ module.name }}</span></nav>
      <section class="module-hero">
        <div>
          <p class="eyebrow">未上线模块说明</p>
          <h1>{{ module.name }}</h1>
          <p>{{ module.description }}</p>
        </div>
        <span class="status">{{ MODULE_STATUS_LABELS[module.status] }}</span>
      </section>

      <el-alert
        title="该模块当前尚不可用，只能查看规划说明。"
        description="页面不会执行真实业务，也不会把任何内容发送到电商平台。"
        type="warning"
        :closable="false"
        show-icon
      />

      <section class="detail-grid">
        <article><small>功能目标</small><strong>{{ module.description }}</strong></article>
        <article><small>当前状态</small><strong>{{ MODULE_STATUS_LABELS[module.status] }} · {{ module.stage }}</strong></article>
        <article><small>未来可能输入</small><strong>{{ module.expectedInput }}</strong></article>
        <article><small>未来可能输出</small><strong>{{ module.expectedOutput }}</strong></article>
        <article><small>自动化等级</small><strong>{{ module.automationLevel }}</strong></article>
        <article><small>人工确认</small><strong>{{ module.requiresHuman ? '必须人工确认' : '按上线规则确认' }}</strong></article>
      </section>

      <section v-if="executionSensitive" class="hard-boundary" data-testid="execution-boundary">
        <h2>当前执行边界</h2>
        <ul>
          <li>当前不可执行任何订单操作。</li>
          <li>不会修改订单，不会自动退款或补发。</li>
          <li>不会自动发送消息，也不会绕过人工审批。</li>
        </ul>
      </section>

      <div class="page-actions">
        <RouterLink :to="{ path: '/suggestions', query: { module: module.key } }" class="primary-action">
          提交相关建议
        </RouterLink>
        <RouterLink to="/" class="secondary-action">返回工作台</RouterLink>
      </div>
    </template>

    <section v-else class="not-found">
      <h1>没有找到这个模块</h1>
      <p>模块名称可能已调整，请返回工作台查看当前规划。</p>
      <RouterLink to="/">返回工作台</RouterLink>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { MODULE_STATUS_LABELS, findWorkbenchModule } from '@/workspace/modules'

const route = useRoute()
const module = computed(() => findWorkbenchModule(String(route.params.moduleKey ?? '')))

const sensitiveModuleKeys = new Set([
  'after-sales',
  'refund-interception',
  'in-transit-refunds',
  'instant-refund-interception',
  'replacement-management',
  'order-appeals'
])

const executionSensitive = computed(() =>
  module.value ? sensitiveModuleKeys.has(module.value.key) : false
)
</script>

<style scoped>
.module-info-page { width: min(1000px, 100%); margin: 0 auto; color: #172033; }
.breadcrumb { display: flex; gap: 8px; margin-bottom: 14px; color: #718096; font-size: 12px; }
.breadcrumb a { color: #315fbd; text-decoration: none; }
.module-hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 16px; padding: 24px; border: 1px solid #d9e3ef; border-radius: 18px; background: #fff; }
.eyebrow { margin: 0 0 6px; color: #315fbd; font-size: 12px; font-weight: 800; letter-spacing: .1em; }
h1 { margin: 0 0 8px; font-size: 30px; }
.module-hero p:not(.eyebrow) { margin: 0; color: #68758a; }
.status { padding: 5px 10px; border-radius: 999px; background: #fff2ce; color: #805b0e; font-size: 12px; font-weight: 800; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.detail-grid article { display: grid; gap: 7px; padding: 17px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }
.detail-grid small { color: #77849a; }
.detail-grid strong { font-size: 14px; line-height: 1.55; }
.hard-boundary { margin-top: 16px; padding: 18px; border: 1px solid #efb3ae; border-radius: 14px; background: #fff4f3; color: #832f2a; }
.hard-boundary h2 { margin: 0 0 8px; font-size: 17px; }
.hard-boundary ul { margin: 0; padding-left: 20px; line-height: 1.75; }
.page-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
.primary-action, .secondary-action { display: inline-flex; padding: 9px 14px; border: 1px solid #c7d6ea; border-radius: 10px; color: #31537f; text-decoration: none; font-weight: 700; }
.primary-action { border-color: #2e63d5; background: #2e63d5; color: #fff; }
.not-found { padding: 28px; border-radius: 18px; background: #fff; }
@media (max-width: 680px) { .module-hero { flex-direction: column; } .detail-grid { grid-template-columns: 1fr; } }
</style>
