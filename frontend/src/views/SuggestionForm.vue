<template>
  <div class="suggestion-page" data-testid="suggestion-form-page">
    <header>
      <p class="eyebrow">意见与建议</p>
      <h1>告诉我们哪里需要改进</h1>
      <p>建议会关联当前客服工作台身份，提交后可在“我的建议”中查看。</p>
    </header>

    <el-alert
      title="隐私提醒"
      description="请勿填写客户姓名、电话、地址、完整订单号、密码或上传隐私截图。只描述测试现象和期望结果。"
      type="warning"
      :closable="false"
      show-icon
    />

    <section class="form-card">
      <div class="identity-row">
        <span>提交人：{{ identity.reporterName || '请先在右上角设置测试姓名' }}</span>
        <span>默认店铺：{{ identity.defaultStoreCode || '未设置' }}</span>
      </div>

      <div class="form-grid">
        <label><span>相关模块</span>
          <el-select v-model="form.moduleKey" data-testid="suggestion-module" placeholder="请选择模块">
            <el-option v-for="item in WORKBENCH_MODULES" :key="item.key" :label="item.name" :value="item.key" />
          </el-select>
        </label>
        <label><span>问题分类</span>
          <el-select v-model="form.category" data-testid="suggestion-category">
            <el-option v-for="item in SUGGESTION_CATEGORIES" :key="item" :label="CATEGORY_LABELS[item]" :value="item" />
          </el-select>
        </label>
        <label><span>出现频率</span>
          <el-select v-model="form.frequency" data-testid="suggestion-frequency">
            <el-option v-for="item in SUGGESTION_FREQUENCIES" :key="item" :label="FREQUENCY_LABELS[item]" :value="item" />
          </el-select>
        </label>
        <label><span>紧急程度</span>
          <el-select v-model="form.urgency" data-testid="suggestion-urgency">
            <el-option v-for="item in SUGGESTION_URGENCIES" :key="item" :label="URGENCY_LABELS[item]" :value="item" />
          </el-select>
        </label>
        <label class="wide"><span>标题</span>
          <el-input v-model="form.title" maxlength="100" show-word-limit data-testid="suggestion-title" placeholder="用一句话说明问题或建议" />
        </label>
        <label class="wide"><span>详细说明</span>
          <el-input v-model="form.description" type="textarea" :rows="7" maxlength="2000" show-word-limit resize="vertical" data-testid="suggestion-description" placeholder="请说明如何出现、影响什么，以及你希望如何改进。不要填写客户隐私。" />
        </label>
      </div>

      <p v-if="validationError" class="message error" data-testid="suggestion-validation">{{ validationError }}</p>
      <p v-if="requestError" class="message error" data-testid="suggestion-error">{{ requestError }} 请检查数据服务后重试。</p>
      <div v-if="receipt" class="success-box" data-testid="suggestion-success">
        <strong>建议已提交</strong>
        <span>编号：{{ receipt.suggestionId }}</span>
        <span>状态：{{ suggestionStatusLabel(receipt.status) }}</span>
        <RouterLink to="/suggestions/mine">查看我的建议</RouterLink>
      </div>

      <div class="actions">
        <el-button type="primary" :loading="submitting" :disabled="submitting" data-testid="suggestion-submit" @click="submit">
          {{ submitting ? '正在提交' : '提交建议' }}
        </el-button>
        <RouterLink to="/suggestions/mine">查看我的建议</RouterLink>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { suggestionClient } from '@/api/suggestionClient'
import {
  SUGGESTION_CATEGORIES,
  SUGGESTION_FREQUENCIES,
  SUGGESTION_URGENCIES,
  type SuggestionDraft,
  type SuggestionReceipt
} from '@/api/suggestionTypes'
import { WORKBENCH_MODULES, findWorkbenchModule } from '@/workspace/modules'
import {
  CATEGORY_LABELS,
  FREQUENCY_LABELS,
  URGENCY_LABELS,
  suggestionStatusLabel
} from '@/workspace/suggestionPresentation'
import { useTesterIdentity } from '@/workspace/testerIdentity'

const route = useRoute()
const { identity } = useTesterIdentity()
const submitting = ref(false)
const validationError = ref('')
const requestError = ref('')
const receipt = ref<SuggestionReceipt | null>(null)

const form = reactive({
  moduleKey: 'ai-chat',
  category: 'IMPROVEMENT' as SuggestionDraft['category'],
  title: '',
  description: '',
  frequency: 'ONCE' as SuggestionDraft['frequency'],
  urgency: 'MEDIUM' as SuggestionDraft['urgency']
})

onMounted(() => {
  const requestedModule = typeof route.query.module === 'string' ? route.query.module : ''
  if (requestedModule && findWorkbenchModule(requestedModule)) form.moduleKey = requestedModule
})

const validate = (): string => {
  if (!identity.value.reporterName) return '请先在右上角设置客服工作台姓名。'
  if (!findWorkbenchModule(form.moduleKey)) return '请选择相关模块。'
  if (!form.title.trim()) return '请填写建议标题。'
  if (form.title.trim().length < 4) return '标题至少需要 4 个字。'
  if (!form.description.trim()) return '请填写详细说明。'
  if (form.description.trim().length < 10) return '详细说明至少需要 10 个字。'
  return ''
}

const submit = async () => {
  if (submitting.value) return
  validationError.value = validate()
  requestError.value = ''
  receipt.value = null
  if (validationError.value) return

  submitting.value = true
  try {
    const request = suggestionClient.submit({
        reporterId: identity.value.reporterId,
        reporterName: identity.value.reporterName,
        storeCode: identity.value.defaultStoreCode || null,
        moduleKey: form.moduleKey,
        category: form.category,
        title: form.title.trim(),
        description: form.description.trim(),
        frequency: form.frequency,
        urgency: form.urgency
      })
    const outcome = await request.then(
      (result) => ({ result, error: null }),
      (error: unknown) => ({ result: null, error })
    )
    if (outcome.error) {
      requestError.value = outcome.error instanceof Error
        ? outcome.error.message
        : '数据服务不可用。'
      return
    }
    if (!outcome.result) {
      requestError.value = '数据服务未返回建议编号。'
      return
    }
    receipt.value = outcome.result
    form.title = ''
    form.description = ''
  } catch (error) {
    requestError.value = error instanceof Error ? error.message : '数据服务不可用。'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.suggestion-page { width: min(920px, 100%); margin: 0 auto; color: #172033; }
header { margin-bottom: 16px; } .eyebrow { margin: 0 0 6px; color: #315fbd; font-size: 12px; font-weight: 800; letter-spacing: .1em; }
h1 { margin: 0 0 8px; font-size: 30px; } header > p:last-child { margin: 0; color: #68758a; }
.form-card { margin-top: 16px; padding: 22px; border: 1px solid #d9e3ef; border-radius: 18px; background: #fff; }
.identity-row { display: flex; flex-wrap: wrap; gap: 10px 28px; margin-bottom: 18px; padding: 10px 12px; border-radius: 10px; background: #eef4fd; color: #31537f; font-size: 13px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
label { display: grid; gap: 7px; font-size: 13px; font-weight: 700; } label.wide { grid-column: 1 / -1; }
.message { margin: 14px 0 0; font-size: 13px; } .error { color: #b83b32; }
.success-box { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; margin-top: 16px; padding: 14px; border: 1px solid #a9d9c5; border-radius: 12px; background: #effaf5; color: #1c6a49; }
.success-box a, .actions a { color: #2d5fb8; }
.actions { display: flex; align-items: center; gap: 16px; margin-top: 18px; }
@media (max-width: 680px) { .form-card { padding: 16px; } .form-grid { grid-template-columns: 1fr; } label.wide { grid-column: auto; } }
</style>
