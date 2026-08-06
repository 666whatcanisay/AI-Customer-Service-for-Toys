<template>
  <div class="home-page" data-testid="workspace-home">
    <section class="welcome-panel">
      <div>
        <p class="eyebrow">AI客服平台 · 客服工作台</p>
        <h1>{{ identity.reporterName ? `${identity.reporterName}，从一条咨询开始` : '从一条咨询开始' }}</h1>
        <p>选择商品和 SKU，获取 AI 建议，再由你核对、编辑和复制。系统不会自动向客户发送消息。</p>
        <div class="hero-actions">
          <RouterLink to="/workspace" class="primary-link" data-testid="enter-ai-chat">进入 AI 客服副驾驶</RouterLink>
          <RouterLink to="/experience-cases" class="secondary-link">查看我的案例</RouterLink>
        </div>
      </div>
      <div class="today-card">
        <strong>今天的工作边界</strong>
        <p>请仅处理已获授权的业务信息。涉及商品、回复和引用时，请在复制前人工核对。</p>
      </div>
    </section>

    <section class="start-section" aria-labelledby="start-checklist-title" data-testid="start-checklist">
      <div class="section-heading">
        <div>
          <p class="eyebrow">首次使用</p>
          <h2 id="start-checklist-title">完成一条咨询，只需三步</h2>
        </div>
        <RouterLink to="/workspace" class="text-link">去处理咨询</RouterLink>
      </div>
      <ol class="start-grid">
        <li>
          <span>1</span>
          <div><strong>确认商品上下文</strong><p>选择当前店铺和商品；不确定 SKU 时可以留空。</p></div>
        </li>
        <li>
          <span>2</span>
          <div><strong>生成并核对建议</strong><p>先看 AI 的处理等级和来源依据，再决定是否编辑。</p></div>
        </li>
        <li>
          <span>3</span>
          <div><strong>复制并沉淀结果</strong><p>人工确认后复制；优秀回复收藏，未采用则反馈原因。</p></div>
        </li>
      </ol>
    </section>

    <section class="work-rhythm-section" aria-labelledby="work-rhythm-title" data-testid="work-rhythm-guide">
      <div class="section-heading">
        <div>
          <p class="eyebrow">日常使用</p>
          <h2 id="work-rhythm-title">不同节奏，同一安全流程</h2>
        </div>
        <RouterLink to="/ai-chat" class="text-link">开始一条咨询</RouterLink>
      </div>
      <div class="work-rhythm-grid">
        <article><strong>第一次使用</strong><p>按上方三步走，不确定 SKU 时留空，不要猜款式。</p></article>
        <article><strong>熟练使用</strong><p>先看 AI 处理等级和来源，再决定直接采用、修改或未采用。</p></article>
        <article><strong>高频使用</strong><p>同一商品连续咨询时，使用“处理下一条咨询”保留商品上下文并清空旧回答。</p></article>
      </div>
    </section>

    <section class="summary-section" aria-labelledby="today-summary-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">今日概览</p>
          <h2 id="today-summary-title">先看当前可用情况</h2>
        </div>
        <span>数据不足时不显示虚构趋势</span>
      </div>
      <div class="overview-grid">
        <article>
          <small>今日 AI 辅助</small>
          <strong class="metric-value" data-testid="today-ai-assist-count">{{ activity.aiAssists.value }}</strong>
          <span>本次会话成功生成的建议；日统计待服务端聚合。</span>
        </article>
        <article>
          <small>优秀案例</small>
          <strong class="metric-value" data-testid="experience-case-count">{{ submissions.length }}</strong>
          <span>本次会话已确认沉淀的案例；仍需运营审核。</span>
          <RouterLink to="/experience-cases">打开案例</RouterLink>
        </article>
        <article>
          <small>反馈数量</small>
          <strong class="metric-value" data-testid="feedback-count">{{ activity.feedbackSubmissions.value }}</strong>
          <span>本次会话提交成功的 AI 问题反馈。</span>
          <RouterLink to="/feedback">了解反馈流程</RouterLink>
        </article>
      </div>
    </section>

    <section class="quick-section" aria-labelledby="quick-entry-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">快捷入口</p>
          <h2 id="quick-entry-title">常用工作</h2>
        </div>
      </div>
      <div class="quick-grid">
        <RouterLink to="/workspace" class="quick-card available"><span>AI</span><div><h3>AI 客服副驾驶</h3><p>查看客户消息、生成建议、核对依据并人工确认。</p></div><b>可使用</b></RouterLink>
        <RouterLink to="/experience-cases" class="quick-card available"><span>☆</span><div><h3>我的案例</h3><p>查看已提交的优秀回复案例与审核状态。</p></div><b>可使用</b></RouterLink>
        <RouterLink to="/feedback" class="quick-card available"><span>!</span><div><h3>问题反馈</h3><p>记录未采用 AI 建议的原因，帮助后续改进。</p></div><b>可使用</b></RouterLink>
        <article class="quick-card planned" data-testid="planned-module-card"><span>⌁</span><div><h3>常用回复</h3><p>规划中；不会在当前版本伪造模板或自动发送。</p></div><b>规划中</b></article>
        <article class="quick-card planned" data-testid="planned-module-card"><span>↗</span><div><h3>售后助手</h3><p>规划中；未来只提供建议流程，不自动补发或退款。</p></div><b>规划中</b></article>
        <article class="quick-card planned" data-testid="planned-module-card"><span>□</span><div><h3>订单助手</h3><p>规划中；未来只读取受控镜像摘要，不写入 ERP。</p></div><b>规划中</b></article>
      </div>
    </section>

    <section v-if="!systemStatus.aiReady.value && !systemStatus.dataReady.value" class="empty-section">
      <ProductEmptyState
        title="服务尚未准备好"
        description="AI 或平台服务当前未连接。请先刷新状态；如仍不可用，请按现有本机启动与排查流程处理。"
        action-label="进入 AI 客服查看状态"
        to="/ai-chat"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import ProductEmptyState from '@/components/ProductEmptyState.vue'
import { useCustomerSessionActivity } from '@/workspace/customerSessionActivity'
import { useExperienceCaseSubmissions } from '@/workspace/experienceCaseSession'
import { useTesterIdentity } from '@/workspace/testerIdentity'
import { useSystemStatus } from '@/workspace/systemStatus'

const { identity } = useTesterIdentity()
const systemStatus = useSystemStatus()
const activity = useCustomerSessionActivity()
const { submissions } = useExperienceCaseSubmissions(identity.value.reporterId)
</script>

<style scoped>
.home-page { width: min(1320px, 100%); margin: 0 auto; color: #172033; }
.welcome-panel { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(260px, .8fr); gap: 18px; padding: 26px; border: 1px solid #d4e1f0; border-radius: 20px; background: radial-gradient(circle at 0 0, rgb(100 157 255 / 20%), transparent 26rem), #fff; box-shadow: 0 12px 34px rgb(24 58 118 / 8%); }
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .1em; }
h1 { margin: 0 0 8px; font-size: clamp(26px, 3vw, 38px); }
h2, h3, p { margin-top: 0; }
.welcome-panel > div > p:not(.eyebrow) { margin-bottom: 0; color: #68758a; line-height: 1.6; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
.primary-link, .secondary-link { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 8px 14px; border: 1px solid #c8d7eb; border-radius: 10px; color: #31537f; text-decoration: none; font-weight: 700; }
.primary-link { border-color: #2e63d5; background: #2e63d5; color: #fff; }
.today-card { align-self: stretch; padding: 18px; border-radius: 16px; background: #fff7df; color: #74500d; }
.today-card strong { font-size: 15px; }
.today-card p { margin: 8px 0 0; font-size: 13px; line-height: 1.65; }
.summary-section, .quick-section, .start-section, .work-rhythm-section { margin-top: 26px; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.section-heading h2 { margin-bottom: 0; font-size: 21px; }
.section-heading > span { color: #718096; font-size: 12px; }
.text-link { color: #285fc8; font-size: 13px; font-weight: 800; text-decoration: none; }
.start-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 0; padding: 0; list-style: none; }
.start-grid li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 11px; padding: 16px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fafdff; }
.start-grid > li > span { display: grid; width: 28px; height: 28px; place-items: center; border-radius: 50%; background: #e8f1ff; color: #285fc8; font-size: 13px; font-weight: 900; }
.start-grid strong { font-size: 14px; }
.start-grid p { margin: 5px 0 0; color: #68758a; font-size: 12px; line-height: 1.55; }
.work-rhythm-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }.work-rhythm-grid article { padding: 15px; border-left: 3px solid #94b8ef; border-radius: 0 12px 12px 0; background: #f8fbff; }.work-rhythm-grid strong { color: #284a73; font-size: 14px; }.work-rhythm-grid p { margin: 6px 0 0; color: #68758a; font-size: 12px; line-height: 1.55; }
.overview-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.overview-grid article { display: grid; gap: 6px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }
.overview-grid small, .overview-grid span { color: #718096; font-size: 12px; line-height: 1.55; }
.overview-grid strong { color: #203b65; font-size: 17px; }
.overview-grid .metric-value { color: #214f9a; font-size: 28px; line-height: 1.1; }
.overview-grid a { margin-top: 4px; color: #285fc8; font-size: 13px; font-weight: 800; text-decoration: none; }
.quick-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.quick-card { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px; align-items: start; min-height: 142px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 16px; background: #fff; color: inherit; text-decoration: none; box-shadow: 0 8px 20px rgb(31 61 109 / 5%); }
.quick-card > span { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 10px; background: #edf4ff; color: #2b5fcc; font-size: 15px; font-weight: 900; }
.quick-card h3 { margin: 1px 0 7px; font-size: 16px; }
.quick-card p { margin: 0; color: #68758a; font-size: 13px; line-height: 1.55; }
.quick-card b { grid-column: 2; align-self: end; color: #237151; font-size: 11px; }
.quick-card.available:hover { border-color: #94b8ef; box-shadow: 0 10px 25px rgb(31 82 165 / 12%); }
.quick-card.planned { background: #fbfcfe; }
.quick-card.planned > span { background: #eef1f6; color: #718096; }
.quick-card.planned b { color: #718096; }
.empty-section { margin-top: 22px; }
@media (max-width: 1020px) { .quick-grid, .start-grid, .work-rhythm-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .welcome-panel, .overview-grid, .quick-grid, .start-grid, .work-rhythm-grid { grid-template-columns: 1fr; } .welcome-panel { padding: 18px; } .section-heading { align-items: flex-start; flex-direction: column; } }
</style>
