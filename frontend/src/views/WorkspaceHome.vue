<template>
  <div class="home-page" data-testid="workspace-home">
    <section class="welcome-panel">
      <div>
        <p class="eyebrow">客服智能工作台</p>
        <h1>{{ identity.reporterName ? `${identity.reporterName}，欢迎回来` : '欢迎进入测试工作台' }}</h1>
        <p>从一个入口处理 AI 客服和意见建议；其他模块会按计划逐步开放。</p>
        <div class="hero-actions">
          <RouterLink to="/ai-chat" class="primary-link" data-testid="enter-ai-chat">
            进入 AI 客服
          </RouterLink>
          <RouterLink to="/suggestions" class="secondary-link">提交意见建议</RouterLink>
        </div>
      </div>
      <div class="today-card">
        <strong>今日测试提示</strong>
        <p>只使用测试商品和虚构问题，不粘贴客户电话、地址、完整订单号或隐私截图。</p>
      </div>
    </section>

    <section class="overview-grid">
      <article>
        <small>当前负责店铺</small>
        <strong>{{ identity.defaultStoreCode || '尚未设置' }}</strong>
        <span>可在右上角“修改”中更新</span>
      </article>
      <article>
        <small>AI 服务</small>
        <strong :class="{ ready: systemStatus.aiReady.value }">
          {{ systemStatus.aiReady.value ? '可用' : '待连接' }}
        </strong>
        <span>{{ systemStatus.aiError.value || '用于生成客服建议回复' }}</span>
      </article>
      <article>
        <small>数据服务</small>
        <strong :class="{ ready: systemStatus.dataReady.value }">
          {{ systemStatus.dataReady.value ? '可用' : '待连接' }}
        </strong>
        <span>{{ systemStatus.dataError.value || '提供店铺、商品与建议服务' }}</span>
      </article>
    </section>

    <section v-for="group in moduleGroups" :key="group.status" class="module-group">
      <div class="group-heading">
        <div>
          <p class="eyebrow">{{ group.label }}</p>
          <h2>{{ group.title }}</h2>
        </div>
        <span>{{ group.items.length }} 个模块</span>
      </div>

      <div v-if="group.items.length" class="module-grid">
        <article
          v-for="module in group.items"
          :key="module.key"
          class="module-card"
          :data-status="module.status"
          data-testid="module-card"
        >
          <div class="module-title-row">
            <h3>{{ module.name }}</h3>
            <span class="status-pill">{{ MODULE_STATUS_LABELS[module.status] }}</span>
          </div>
          <p class="module-description">{{ module.description }}</p>
          <dl>
            <div><dt>当前阶段</dt><dd>{{ module.stage }}</dd></div>
            <div><dt>预计输入</dt><dd>{{ module.expectedInput }}</dd></div>
            <div><dt>预计输出</dt><dd>{{ module.expectedOutput }}</dd></div>
            <div><dt>人工确认</dt><dd>{{ module.requiresHuman ? '需要' : '不需要' }}</dd></div>
          </dl>
          <RouterLink
            v-if="module.status === 'AVAILABLE' && module.route"
            :to="module.route"
            class="card-action primary"
          >
            打开模块
          </RouterLink>
          <RouterLink v-else :to="`/modules/${module.key}`" class="card-action">
            查看未上线说明
          </RouterLink>
        </article>
      </div>
      <div v-else class="empty-group">当前没有处于“{{ group.label }}”状态的模块。</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  MODULE_STATUS_LABELS,
  WORKBENCH_MODULES,
  type ModuleStatus
} from '@/workspace/modules'
import { useTesterIdentity } from '@/workspace/testerIdentity'
import { useSystemStatus } from '@/workspace/systemStatus'

const { identity } = useTesterIdentity()
const systemStatus = useSystemStatus()

const groupDefinitions: Array<{ status: ModuleStatus; label: string; title: string }> = [
  { status: 'AVAILABLE', label: '可用', title: '现在可以使用' },
  { status: 'TESTING', label: '测试中', title: '正在内部验证' },
  { status: 'DEVELOPING', label: '开发中', title: '正在建设' },
  { status: 'PLANNED', label: '规划中', title: '后续计划' }
]

const moduleGroups = computed(() => groupDefinitions.map((group) => ({
  ...group,
  items: WORKBENCH_MODULES.filter((module) => module.status === group.status)
})))
</script>

<style scoped>
.home-page {
  width: min(1320px, 100%);
  margin: 0 auto;
  color: #172033;
}

.welcome-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(260px, 0.8fr);
  gap: 18px;
  padding: 26px;
  border: 1px solid #d4e1f0;
  border-radius: 20px;
  background:
    radial-gradient(circle at 0 0, rgb(100 157 255 / 20%), transparent 26rem),
    #fff;
  box-shadow: 0 12px 34px rgb(24 58 118 / 8%);
}

.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .1em; }
h1 { margin: 0 0 8px; font-size: clamp(26px, 3vw, 38px); }
h2, h3, p { margin-top: 0; }
.welcome-panel > div > p:not(.eyebrow) { margin-bottom: 0; color: #68758a; }

.hero-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
.primary-link, .secondary-link, .card-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 8px 14px;
  border: 1px solid #c8d7eb;
  border-radius: 10px;
  color: #31537f;
  text-decoration: none;
  font-weight: 700;
}
.primary-link, .card-action.primary { border-color: #2e63d5; background: #2e63d5; color: #fff; }

.today-card { align-self: stretch; padding: 18px; border-radius: 16px; background: #fff7df; color: #74500d; }
.today-card strong { font-size: 15px; }
.today-card p { margin: 8px 0 0; font-size: 13px; line-height: 1.65; }

.overview-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }
.overview-grid article { display: grid; gap: 5px; padding: 16px 18px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }
.overview-grid small, .overview-grid span { color: #718096; font-size: 12px; }
.overview-grid strong { color: #a06400; font-size: 18px; }
.overview-grid strong.ready { color: #19704c; }

.module-group { margin-top: 24px; }
.group-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.group-heading h2 { margin-bottom: 0; font-size: 21px; }
.group-heading > span { color: #718096; font-size: 12px; }
.module-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.module-card { display: flex; min-width: 0; flex-direction: column; padding: 18px; border: 1px solid #dbe4ef; border-radius: 16px; background: #fff; box-shadow: 0 8px 20px rgb(31 61 109 / 5%); }
.module-card[data-status="AVAILABLE"] { border-color: #a9d9c5; }
.module-card[data-status="DEVELOPING"] { border-color: #edcc89; }
.module-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.module-title-row h3 { margin-bottom: 0; font-size: 17px; }
.status-pill { flex: 0 0 auto; padding: 3px 8px; border-radius: 999px; background: #eef2f8; color: #52657d; font-size: 11px; font-weight: 800; }
.module-description { min-height: 42px; margin: 10px 0; color: #68758a; font-size: 13px; line-height: 1.55; }
.module-card dl { display: grid; gap: 7px; margin: 0 0 16px; }
.module-card dl div { display: grid; grid-template-columns: 68px minmax(0, 1fr); gap: 8px; font-size: 12px; }
.module-card dt { color: #7b879a; }
.module-card dd { margin: 0; color: #33445d; overflow-wrap: anywhere; }
.card-action { align-self: flex-start; margin-top: auto; font-size: 12px; }
.empty-group { padding: 18px; border: 1px dashed #cfd9e7; border-radius: 14px; color: #7a8799; background: rgb(255 255 255 / 65%); }

@media (max-width: 1120px) { .module-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) {
  .welcome-panel, .overview-grid, .module-grid { grid-template-columns: 1fr; }
  .welcome-panel { padding: 18px; }
  .module-description { min-height: 0; }
}
</style>
