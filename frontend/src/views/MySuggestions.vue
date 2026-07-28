<template>
  <div class="mine-page" data-testid="my-suggestions-page">
    <header>
      <div><p class="eyebrow">意见与建议</p><h1>我的建议</h1><p>这里只显示当前本机测试客服提交的建议摘要。</p></div>
      <RouterLink to="/suggestions" class="primary-link">提交新建议</RouterLink>
    </header>

    <section v-if="loading" class="state-card" data-testid="suggestions-loading">正在查询建议记录……</section>
    <section v-else-if="errorMessage" class="state-card error" data-testid="suggestions-error">
      <strong>数据服务不可用</strong><p>{{ errorMessage }}</p><el-button @click="load">重新查询</el-button>
    </section>
    <section v-else-if="!items.length" class="state-card" data-testid="suggestions-empty">
      <strong>还没有提交过建议</strong><p>测试中发现问题时，可以提交一条不包含客户隐私的说明。</p>
    </section>
    <section v-else class="suggestion-list" data-testid="suggestion-list">
      <div class="list-summary">共 {{ total }} 条</div>
      <article v-for="item in items" :key="item.suggestionId">
        <div class="title-row"><h2>{{ item.title }}</h2><span>{{ suggestionStatusLabel(item.status) }}</span></div>
        <dl>
          <div><dt>建议编号</dt><dd>{{ item.suggestionId }}</dd></div>
          <div><dt>相关模块</dt><dd>{{ moduleName(item.moduleKey) }}</dd></div>
          <div><dt>分类</dt><dd>{{ CATEGORY_LABELS[item.category] }}</dd></div>
          <div><dt>频率</dt><dd>{{ FREQUENCY_LABELS[item.frequency] }}</dd></div>
          <div><dt>紧急程度</dt><dd>{{ URGENCY_LABELS[item.urgency] }}</dd></div>
          <div><dt>店铺</dt><dd>{{ item.storeCode || '未关联店铺' }}</dd></div>
        </dl>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { suggestionClient } from '@/api/suggestionClient'
import type { SuggestionSummary } from '@/api/suggestionTypes'
import { findWorkbenchModule } from '@/workspace/modules'
import { CATEGORY_LABELS, FREQUENCY_LABELS, URGENCY_LABELS, suggestionStatusLabel } from '@/workspace/suggestionPresentation'
import { useCustomerIdentity } from '@/workspace/customerIdentity'

const { identity } = useCustomerIdentity()
const loading = ref(false)
const errorMessage = ref('')
const items = ref<SuggestionSummary[]>([])
const total = ref(0)
const moduleName = (key: string) => findWorkbenchModule(key)?.name ?? '未知模块'

const load = async () => {
  if (loading.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    if (!identity.value) {
      errorMessage.value = '请先选择客服身份。'
      return
    }
    const request = suggestionClient.listMine(identity.value.userId)
    const outcome = await request.then(
      (result) => ({ result, error: null }),
      (error: unknown) => ({ result: null, error })
    )
    if (outcome.error) {
      errorMessage.value = outcome.error instanceof Error
        ? outcome.error.message
        : '请检查数据服务后重试。'
      return
    }
    if (!outcome.result) {
      errorMessage.value = '数据服务未返回建议列表，请重试。'
      return
    }
    const result = outcome.result
    items.value = result.items
    total.value = result.total
  } catch (error) {
    items.value = []
    total.value = 0
    errorMessage.value = error instanceof Error ? error.message : '请检查数据服务后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<style scoped>
.mine-page { width: min(1000px, 100%); margin: 0 auto; color: #172033; }
header { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin-bottom: 16px; }
.eyebrow { margin: 0 0 6px; color: #315fbd; font-size: 12px; font-weight: 800; letter-spacing: .1em; }
h1 { margin: 0 0 7px; font-size: 30px; } header p:last-child { margin: 0; color: #68758a; }
.primary-link { display: inline-flex; flex: 0 0 auto; padding: 9px 14px; border-radius: 10px; background: #2e63d5; color: #fff; text-decoration: none; font-weight: 700; }
.state-card { padding: 24px; border: 1px solid #d9e3ef; border-radius: 16px; background: #fff; color: #627086; }
.state-card strong { display: block; color: #263b5a; } .state-card p { margin: 7px 0 12px; } .state-card.error { border-color: #edb4ae; background: #fff7f6; }
.suggestion-list { display: grid; gap: 12px; } .list-summary { color: #748198; font-size: 12px; }
article { padding: 18px; border: 1px solid #dbe4ef; border-radius: 15px; background: #fff; }
.title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; } h2 { margin: 0; font-size: 17px; }
.title-row span { padding: 4px 8px; border-radius: 999px; background: #eef4fd; color: #315fbd; font-size: 11px; font-weight: 800; }
dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 18px; margin: 14px 0 0; }
dl div { min-width: 0; } dt { color: #7a8799; font-size: 11px; } dd { margin: 4px 0 0; overflow-wrap: anywhere; font-size: 13px; }
@media (max-width: 680px) { header { align-items: flex-start; flex-direction: column; } dl { grid-template-columns: 1fr 1fr; } }
</style>
