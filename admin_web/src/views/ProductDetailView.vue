<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  apiErrorMessage,
  getProductKnowledgeProduct,
  type ProductKnowledgeDetail,
  type TopicCoverage,
} from '../api/client'
import { displayStatus } from '../presentation'

const props = defineProps<{ productId: string }>()
const detail = ref<ProductKnowledgeDetail | null>(null)
const error = ref('')
const loading = ref(true)

const aTopics = computed(() => detail.value?.topic_coverage.filter((item) => item.level === 'A') ?? [])
const bTopics = computed(() => detail.value?.topic_coverage.filter((item) => item.level === 'B') ?? [])

function topicStatusLabel(topic: TopicCoverage): string {
  return {
    SUPPORTED: '可回答',
    PARTIAL: '可基础回答',
    MISSING: '资料缺失',
  }[topic.status]
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    detail.value = await getProductKnowledgeProduct(props.productId)
  } catch (reason: unknown) {
    detail.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

watch(() => props.productId, load)
onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">商品知识详情</p>
        <h1>{{ detail?.product.product_name || '商品知识' }}</h1>
        <p v-if="detail">{{ detail.store.store_name }} → {{ detail.product.product_name }} → {{ detail.skus.map((sku) => sku.sku_name).join(' / ') || '暂无 SKU' }}</p>
      </div>
      <RouterLink class="button secondary" to="/knowledge-center">返回商品知识中心</RouterLink>
    </div>

    <p v-if="loading" class="notice" role="status">正在读取商品知识详情…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取商品知识详情。{{ error }}</p>

    <template v-else-if="detail">
      <section class="answer-grid" aria-label="AI 可回答能力摘要">
        <article class="answer-card supported">
          <span>1. AI 现在能回答什么？</span>
          <strong>{{ detail.answerable_topics.length }} 项</strong>
          <div class="topic-chips">
            <span v-for="topic in detail.answerable_topics" :key="topic">✓ {{ topic }}</span>
          </div>
        </article>
        <article class="answer-card missing">
          <span>2. AI 不能回答什么？</span>
          <strong>{{ detail.missing_topics.length }} 项</strong>
          <div class="topic-chips">
            <span v-for="topic in detail.missing_topics" :key="topic">⚠ {{ topic }}</span>
            <span v-if="detail.missing_topics.length === 0">暂无规则内缺失项</span>
          </div>
        </article>
        <article class="answer-card action">
          <span>3. 运营下一步补什么？</span>
          <strong>{{ detail.next_actions.length }} 项</strong>
          <ul>
            <li v-for="action in detail.next_actions.slice(0, 4)" :key="action">{{ action }}</li>
            <li v-if="detail.next_actions.length === 0">当前无需补充核心资料。</li>
          </ul>
        </article>
      </section>

      <section class="card overview-card">
        <div class="section-heading">
          <div>
            <p class="eyebrow">商品概览</p>
            <h2>{{ detail.product.product_name }}</h2>
            <div class="status-row">
              <span class="status-pill">资料：{{ displayStatus(detail.data_status) }}</span>
              <span class="status-pill ai">AI：{{ displayStatus(detail.ai_status) }}</span>
            </div>
          </div>
          <div class="coverage-score"><strong>{{ detail.coverage_percent }}%</strong><span>AI 核心知识覆盖度</span></div>
        </div>
        <p class="summary">{{ detail.product.product_summary || '当前资料未提供商品简介。' }}</p>
        <dl class="business-facts">
          <div><dt>核心卖点</dt><dd>{{ detail.product.core_selling_points.join('；') || '当前资料未提供' }}</dd></div>
          <div><dt>适用年龄</dt><dd>{{ detail.product.applicable_age || '当前资料未提供，回答时需提示人工确认' }}</dd></div>
          <div><dt>材质与安全</dt><dd>{{ detail.product.material || '当前资料未提供' }}</dd></div>
          <div><dt>包装内容</dt><dd>{{ detail.product.package_contents || '当前资料未提供' }}</dd></div>
          <div><dt>基础使用说明</dt><dd>{{ detail.product.usage_instructions || '当前资料未提供' }}</dd></div>
        </dl>
      </section>

      <section class="card section-card">
        <div class="section-heading"><div><p class="eyebrow">SKU 信息</p><h2>规格和款式差异</h2></div><span>{{ detail.skus.length }} 个 SKU</span></div>
        <p v-if="detail.skus.length === 0" class="notice">当前商品暂无 SKU 资料。</p>
        <div v-else class="sku-grid">
          <article v-for="sku in detail.skus" :key="sku.technical_details.sku_id || sku.sku_name" class="sku-card">
            <h3>{{ sku.sku_name }}</h3>
            <p><strong>差异结论：</strong>{{ sku.specification_difference || '当前资料未说明与其他 SKU 的差异。' }}</p>
            <p><strong>颜色款式：</strong>{{ sku.color_style || '当前资料未提供' }}</p>
            <p><strong>包装差异：</strong>{{ sku.package_difference || '当前资料未提供' }}</p>
            <p><strong>SKU专属FAQ：</strong>{{ sku.faq_count }} 条</p>
            <p v-if="sku.specification_difference === '已确认无差异'" class="confirmed">✓ 已确认无差异</p>
            <div class="topic-chips"><span v-for="attribute in sku.attributes" :key="attribute">{{ attribute }}</span></div>
          </article>
        </div>
      </section>

      <section class="coverage-layout">
        <article class="card section-card">
          <p class="eyebrow">A级 · AI 客服核心信息</p>
          <h2>核心覆盖情况</h2>
          <div class="coverage-list">
            <div v-for="topic in aTopics" :key="topic.key" :class="['coverage-item', topic.status.toLowerCase()]">
              <span>{{ topic.name }}</span><strong>{{ topicStatusLabel(topic) }}</strong>
            </div>
          </div>
        </article>
        <article class="card section-card">
          <p class="eyebrow">B级 · 回答效果增强</p>
          <h2>增强信息覆盖</h2>
          <div class="coverage-list">
            <div v-for="topic in bTopics" :key="topic.key" :class="['coverage-item', topic.status.toLowerCase()]">
              <span>{{ topic.name }}</span><strong>{{ topicStatusLabel(topic) }}</strong>
            </div>
          </div>
        </article>
      </section>

      <section class="card section-card">
        <div class="section-heading"><div><p class="eyebrow">AI 问题缺口</p><h2>缺失信息与安全回答</h2></div><RouterLink class="button" :to="{ path: '/knowledge-editor', query: { product: detail.product.technical_details.product_id || '', store: detail.store.technical_details.store_code || '' } }">补充知识</RouterLink></div>
        <p v-if="detail.gaps.length === 0" class="notice success">当前规则范围内未发现待补充缺口。</p>
        <div v-else class="gap-list">
          <article v-for="gap in detail.gaps" :key="`${gap.source}-${gap.key}`" class="gap-card">
            <div><strong>⚠ {{ gap.title }}</strong><span>{{ displayStatus(gap.severity) }}</span></div>
            <p>{{ gap.description }}</p>
            <p><b>运营建议：</b>{{ gap.recommended_action }}</p>
            <blockquote>{{ gap.safe_fallback }}</blockquote>
          </article>
        </div>
      </section>

      <section class="lower-grid">
        <article class="card section-card">
          <p class="eyebrow">常见问题 FAQ</p><h2>已核对问答</h2>
          <p v-if="detail.faqs.length === 0" class="notice">当前商品暂无结构化 FAQ。</p>
          <details v-for="faq in detail.faqs" v-else :key="faq.question" class="faq-item">
            <summary>{{ faq.question }}</summary>
            <p>{{ faq.recommended_reply }}</p>
            <small>{{ faq.sku_name ? `适用SKU：${faq.sku_name} · ` : '适用全部SKU · ' }}回答策略：{{ displayStatus(faq.answer_strategy) }} · 风险：{{ displayStatus(faq.risk_level) }}</small>
          </details>
        </article>
        <article class="card section-card">
          <p class="eyebrow">安全信息</p><h2>回答边界与提示</h2>
          <p v-if="detail.safety_information.length === 0" class="notice">当前商品暂无单独安全说明。</p>
          <div v-for="item in detail.safety_information" v-else :key="`${item.title}-${item.content}`" class="safety-item">
            <strong>{{ item.title }}</strong><p>{{ item.content }}</p><p v-if="item.forbidden_claim"><b>禁止承诺：</b>{{ item.forbidden_claim }}</p><p v-if="item.handoff_condition"><b>必须转人工：</b>{{ item.handoff_condition }}</p><small v-if="item.risk_level">风险：{{ displayStatus(item.risk_level) }}</small>
          </div>
        </article>
      </section>

      <section class="card section-card">
        <p class="eyebrow">资料来源</p><h2>可追溯依据</h2>
        <p v-if="detail.sources.length === 0" class="notice">当前商品尚未登记独立资料来源。</p>
        <div v-else class="source-grid">
          <article v-for="source in detail.sources" :key="source.technical_details.source_id || source.technical_details.material_id || source.source_name">
            <strong>{{ source.source_name }}</strong><span>{{ displayStatus(source.source_type) }} · {{ source.review_status ? displayStatus(source.review_status) : '未标注审核状态' }}</span>
          </article>
        </div>
      </section>

      <p class="notice boundary">{{ detail.boundary_note }}页面只显示有来源的现有事实；缺失字段不会自动补全或编造。</p>
    </template>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.answer-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 20px; }.answer-card { display: grid; align-content: start; gap: 10px; min-height: 180px; padding: 19px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }.answer-card > span { color: #526279; font-size: 13px; }.answer-card > strong { color: #172554; font-size: 26px; }.answer-card.supported { border-top: 4px solid #3d9b6b; }.answer-card.missing { border-top: 4px solid #d69735; }.answer-card.action { border-top: 4px solid #3973c4; }.answer-card ul { margin: 0; padding-left: 18px; color: #526279; line-height: 1.55; }
.topic-chips { display: flex; flex-wrap: wrap; gap: 6px; }.topic-chips span { padding: 5px 8px; border-radius: 7px; background: #f1f5fa; color: #425b78; font-size: 12px; }.section-heading { display: flex; justify-content: space-between; gap: 18px; align-items: start; }.section-heading h2, .section-card h2 { margin: 0; color: #172554; }.coverage-score { display: grid; justify-items: end; }.coverage-score strong { color: #2e6db0; font-size: 30px; }.coverage-score span { color: #617087; font-size: 12px; }.status-row { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }.status-pill { padding: 5px 9px; border-radius: 999px; color: #365174; background: #edf2f8; font-size: 12px; }.status-pill.ai { color: #285493; background: #eaf2ff; }.summary { color: #526279; line-height: 1.65; }.business-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.business-facts div { padding: 13px; border-radius: 9px; background: #f7f9fc; }.business-facts dt { color: #617087; font-size: 12px; }.business-facts dd { margin: 5px 0 0; color: #2f4259; line-height: 1.5; }
.section-card { margin-top: 20px; }.section-card > .eyebrow + h2 { margin-bottom: 16px; }.sku-grid, .source-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }.sku-card, .source-grid article { padding: 15px; border: 1px solid #e0e7f0; border-radius: 10px; }.sku-card h3 { margin: 0; color: #25466f; }.sku-card p { color: #526279; line-height: 1.55; }.sku-card .confirmed { color: #217447; font-weight: 700; }.coverage-layout, .lower-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }.coverage-list { display: grid; gap: 8px; margin-top: 16px; }.coverage-item { display: flex; justify-content: space-between; padding: 10px 12px; border-radius: 8px; background: #edf7f1; color: #276a49; }.coverage-item.partial { background: #eef4ff; color: #315f9d; }.coverage-item.missing { background: #fff5e7; color: #9a641c; }.coverage-item strong { font-size: 12px; }
.gap-list { display: grid; gap: 10px; margin-top: 16px; }.gap-card { padding: 15px; border-left: 4px solid #d69735; border-radius: 8px; background: #fffaf2; }.gap-card > div { display: flex; justify-content: space-between; gap: 12px; color: #704911; }.gap-card p { margin: 8px 0; color: #526279; line-height: 1.55; }.gap-card blockquote { margin: 10px 0 0; padding: 10px 12px; border-radius: 7px; background: #fff; color: #75570a; }.faq-item { padding: 11px 0; border-bottom: 1px solid #e5ebf2; }.faq-item summary { color: #25466f; cursor: pointer; }.faq-item p, .safety-item p { color: #526279; line-height: 1.55; }.faq-item small, .safety-item small { color: #617087; }.safety-item { padding: 12px 0; border-bottom: 1px solid #e5ebf2; }.source-grid article { display: grid; gap: 6px; }.source-grid article > span { color: #617087; font-size: 12px; }.boundary { margin-top: 20px; color: #75570a; background: #fff8df; line-height: 1.6; }
@media (max-width: 900px) { .answer-grid, .coverage-layout, .lower-grid { grid-template-columns: 1fr; }.business-facts, .sku-grid, .source-grid { grid-template-columns: 1fr; } }
</style>
