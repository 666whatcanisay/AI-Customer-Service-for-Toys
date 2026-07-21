<template>
  <main class="ai-chat-page">
    <div class="page-header">
      <div>
        <h1>AI 知识问答助手</h1>
        <p>基于本地 PDF 知识库的 RAG 客服原型</p>
      </div>
      <div class="header-info" v-if="aiStatus">
        <el-tag :type="statusTagType" class="status-tag" @click="openModelConfig">
          {{ statusText }}
        </el-tag>
        <el-button type="primary" link @click="openModelConfig">
          <el-icon><Setting /></el-icon>
          配置大模型
        </el-button>
      </div>
    </div>

    <el-dialog
      v-model="configDialogVisible"
      title="大模型配置"
      width="min(480px, calc(100vw - 32px))"
      destroy-on-close
    >
      <el-alert
        title="API Key 仅保存到本机 backend/.env，页面和接口都不会回显明文。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form class="model-config-form" label-position="top">
        <el-form-item label="服务商">
          <el-select v-model="modelConfig.provider" style="width: 100%">
            <el-option label="阿里云百炼（DashScope）" value="bailian" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input
            v-model="modelConfig.model"
            maxlength="100"
            placeholder="例如 qwen-turbo"
          />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="modelConfig.apiKey"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="modelConfig.configured ? '留空则保留当前 Key' : '请输入 DashScope API Key'"
          />
          <div class="key-hint" v-if="modelConfig.configured">
            当前已配置。为安全起见，已有 Key 不会显示。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button
            v-if="modelConfig.configured"
            type="danger"
            plain
            :loading="configSaving"
            @click="clearModelApiKey"
          >
            清除 Key
          </el-button>
          <span class="dialog-footer-actions">
            <el-button @click="configDialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="configSaving" @click="saveModelConfig">
              保存并生效
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>

    <section class="chat-container">
      <div class="chat-messages" ref="chatContainerRef">
        <div v-if="messages.length === 0" class="empty-state">
          <el-icon :size="60"><ChatDotRound /></el-icon>
          <p>您好！我是 AI 知识问答助手</p>
          <p class="hint">您可以向我咨询当前知识库中的问题，例如：</p>
          <ul class="suggestions">
            <li
              v-for="question in recommendedQuestions"
              :key="question"
              @click="sendSuggestion(question)"
            >
              {{ question }}
            </li>
          </ul>
        </div>

        <div
          v-for="(msg, index) in messages"
          :key="index"
          :class="['message', msg.role]"
        >
          <div class="message-avatar">
            <el-icon v-if="msg.role === 'user'" :size="24"><UserFilled /></el-icon>
            <el-icon v-else :size="24"><ChatDotRound /></el-icon>
          </div>
          <div class="message-content">
            <div class="message-text">{{ msg.content }}</div>
            <div class="message-sources" v-if="msg.sources?.length">
              <div class="sources-title">参考来源：</div>
              <div
                v-for="(source, sourceIndex) in msg.sources"
                :key="`${source.file}-${source.page}-${sourceIndex}`"
                class="source-item"
              >
                <div class="source-heading">
                  <span class="source-file">{{ source.file }}</span>
                  <span class="source-page">第 {{ source.page }} 页</span>
                  <span class="source-distance">距离 {{ formatDistance(source.distance) }}</span>
                </div>
                <div v-if="source.content_preview" class="source-preview">
                  {{ source.content_preview }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="loading" class="message assistant">
          <div class="message-avatar">
            <el-icon :size="24"><ChatDotRound /></el-icon>
          </div>
          <div class="message-content">
            <div class="message-text typing" aria-label="AI 正在回答">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </div>
          </div>
        </div>
      </div>

      <div class="service-message" v-if="aiStatus && !aiStatus.ready">
        {{ aiStatus.message }}
      </div>

      <div class="chat-input">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="2"
          maxlength="4000"
          show-word-limit
          placeholder="请输入您的问题，按 Enter 发送，Shift+Enter 换行"
          :disabled="loading || !aiStatus?.ready"
          @keydown.enter.exact.prevent="handleSend"
        />
        <el-button
          type="primary"
          @click="handleSend"
          :loading="loading"
          :disabled="!inputMessage.trim() || !aiStatus?.ready"
        >
          <el-icon><Promotion /></el-icon>
          发送
        </el-button>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ChatDotRound, Promotion, Setting, UserFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api/client'

interface Source {
  file: string
  page: number
  distance: number
  content_preview?: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

interface AiStatus {
  ready: boolean
  message: string
  model_configured: boolean
  initialization_error?: string | null
}

interface ModelConfigResponse {
  provider: string
  model: string
  configured: boolean
  storage: string
  restart_required: boolean
}

const fallbackQuestions = [
  '党员有哪些义务？',
  '党章的内容有哪些？',
  '如何申请入党？',
  '党费如何缴纳？'
]

const messages = ref<Message[]>([])
const inputMessage = ref('')
const loading = ref(false)
const aiStatus = ref<AiStatus | null>(null)
const recommendedQuestions = ref<string[]>(fallbackQuestions)
const chatContainerRef = ref<HTMLElement | null>(null)
const configDialogVisible = ref(false)
const configSaving = ref(false)
const modelConfig = ref({
  provider: 'bailian',
  model: 'qwen-turbo',
  apiKey: '',
  configured: false
})
let statusTimer: number | undefined

const statusTagType = computed(() => {
  if (!aiStatus.value?.ready) return aiStatus.value?.initialization_error ? 'danger' : 'warning'
  return aiStatus.value.model_configured ? 'success' : 'warning'
})

const statusText = computed(() => {
  if (!aiStatus.value?.ready) return aiStatus.value?.message || 'AI 服务初始化中...'
  return aiStatus.value.model_configured
    ? 'AI 服务已就绪'
    : '本地检索已就绪 · 大模型未配置'
})

const responseData = <T,>(payload: any): T => (payload?.data ?? payload) as T

const fetchAiStatus = async () => {
  try {
    const response = await api.get('/status')
    aiStatus.value = responseData<AiStatus>(response.data)
    if (aiStatus.value.ready || aiStatus.value.initialization_error) {
      if (statusTimer) window.clearInterval(statusTimer)
      statusTimer = undefined
    }
  } catch {
    aiStatus.value = {
      ready: false,
      message: 'AI 服务未启动，请先运行 scripts/start.ps1',
      model_configured: false,
      initialization_error: 'connection_failed'
    }
  }
}

const fetchRecommendedQuestions = async () => {
  try {
    const response = await api.get('/questions/recommended')
    const data = responseData<{ questions?: string[] }>(response.data)
    if (Array.isArray(data.questions) && data.questions.length) {
      recommendedQuestions.value = data.questions
    }
  } catch {
    recommendedQuestions.value = fallbackQuestions
  }
}

const errorMessage = (error: any): string => {
  const payload = error?.response?.data
  return payload?.message || payload?.detail || error?.message || '网络错误，请稍后重试'
}

const applyModelConfigResponse = (data: ModelConfigResponse) => {
  modelConfig.value = {
    provider: data.provider,
    model: data.model,
    apiKey: '',
    configured: data.configured
  }
  if (aiStatus.value) aiStatus.value.model_configured = data.configured
}

const openModelConfig = async () => {
  try {
    const response = await api.get('/config/model')
    applyModelConfigResponse(responseData<ModelConfigResponse>(response.data))
    configDialogVisible.value = true
  } catch (error: any) {
    ElMessage.error(errorMessage(error))
  }
}

const saveModelConfig = async () => {
  const model = modelConfig.value.model.trim()
  const apiKey = modelConfig.value.apiKey.trim()
  if (!model) {
    ElMessage.warning('请填写模型名称')
    return
  }
  if (!modelConfig.value.configured && !apiKey) {
    ElMessage.warning('首次配置必须填写 API Key')
    return
  }

  configSaving.value = true
  try {
    const payload: Record<string, string> = {
      provider: modelConfig.value.provider,
      model
    }
    if (apiKey) payload.api_key = apiKey
    const response = await api.put('/config/model', payload)
    applyModelConfigResponse(responseData<ModelConfigResponse>(response.data))
    configDialogVisible.value = false
    ElMessage.success('大模型配置已保存并即时生效')
  } catch (error: any) {
    ElMessage.error(errorMessage(error))
  } finally {
    configSaving.value = false
  }
}

const clearModelApiKey = async () => {
  try {
    await ElMessageBox.confirm(
      '清除后将恢复为仅本地检索模式，确定继续吗？',
      '清除 API Key',
      { type: 'warning', confirmButtonText: '确定清除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  configSaving.value = true
  try {
    const response = await api.put('/config/model', {
      provider: modelConfig.value.provider,
      model: modelConfig.value.model.trim() || 'qwen-turbo',
      clear_api_key: true
    })
    applyModelConfigResponse(responseData<ModelConfigResponse>(response.data))
    configDialogVisible.value = false
    ElMessage.success('API Key 已从本机配置中清除')
  } catch (error: any) {
    ElMessage.error(errorMessage(error))
  } finally {
    configSaving.value = false
  }
}

const handleSend = async () => {
  const text = inputMessage.value.trim()
  if (!text || loading.value) return
  if (!aiStatus.value?.ready) {
    ElMessage.warning(aiStatus.value?.message || 'AI 服务正在初始化，请稍后')
    return
  }

  messages.value.push({ role: 'user', content: text })
  inputMessage.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const response = await api.post('/chat', { message: text })
    const data = responseData<{
      answer?: string
      sources?: Source[]
      model_configured?: boolean
    }>(response.data)
    messages.value.push({
      role: 'assistant',
      content: data.answer || '抱歉，服务没有返回有效回答。',
      sources: Array.isArray(data.sources) ? data.sources : []
    })
  } catch (error: any) {
    messages.value.push({ role: 'assistant', content: errorMessage(error) })
    if (error?.response?.status === 503) await fetchAiStatus()
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

const sendSuggestion = (text: string) => {
  inputMessage.value = text
  void handleSend()
}

const formatDistance = (distance: number) =>
  typeof distance === 'number' ? distance.toFixed(4) : '-'

const scrollToBottom = async () => {
  await nextTick()
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
  }
}

onMounted(async () => {
  await Promise.all([fetchAiStatus(), fetchRecommendedQuestions()])
  if (!aiStatus.value?.ready && !aiStatus.value?.initialization_error) {
    statusTimer = window.setInterval(fetchAiStatus, 2000)
  }
})

onBeforeUnmount(() => {
  if (statusTimer) window.clearInterval(statusTimer)
})
</script>

<style scoped>
.ai-chat-page {
  display: flex;
  flex-direction: column;
  width: min(1120px, calc(100% - 32px));
  height: 100vh;
  min-height: 620px;
  margin: 0 auto;
  padding: 24px 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.page-header h1 {
  margin: 0;
  color: #1f2937;
  font-size: 22px;
  font-weight: 600;
}

.page-header p {
  margin: 6px 0 0;
  color: #909399;
  font-size: 13px;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-tag {
  cursor: pointer;
}

.model-config-form {
  margin-top: 20px;
}

.key-hint {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.dialog-footer-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.chat-container {
  flex: 1;
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 12px rgb(0 0 0 / 8%);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: #f5f7fa;
}

.empty-state {
  display: flex;
  height: 100%;
  min-height: 300px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  text-align: center;
}

.empty-state p {
  margin: 10px 0 5px;
  font-size: 16px;
}

.empty-state .hint {
  color: #c0c4cc;
  font-size: 14px;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 10px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.suggestions li {
  padding: 10px 18px;
  border: 1px solid #409eff;
  border-radius: 20px;
  background: #fff;
  color: #409eff;
  cursor: pointer;
  transition: 0.2s ease;
}

.suggestions li:hover {
  background: #409eff;
  color: #fff;
}

.message {
  display: flex;
  align-items: flex-start;
  margin-bottom: 20px;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  display: flex;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.message.user .message-avatar {
  background: #409eff;
  color: #fff;
}

.message.assistant .message-avatar {
  background: #67c23a;
  color: #fff;
}

.message-content {
  max-width: min(76%, 760px);
  padding: 12px 16px;
  border-radius: 12px;
  box-shadow: 0 2px 4px rgb(0 0 0 / 5%);
}

.message.user .message-content {
  margin-right: 10px;
  background: #409eff;
  color: #fff;
}

.message.assistant .message-content {
  margin-left: 10px;
  background: #fff;
}

.message-text {
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-sources {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #eee;
  font-size: 12px;
}

.sources-title {
  margin-bottom: 7px;
  color: #909399;
}

.source-item {
  margin: 6px 0;
  padding: 8px;
  border-radius: 6px;
  background: #f8fafc;
}

.source-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.source-file {
  color: #409eff;
  font-weight: 500;
}

.source-page,
.source-distance,
.source-preview {
  color: #909399;
}

.source-preview {
  margin-top: 5px;
  line-height: 1.5;
}

.typing {
  display: flex;
  gap: 4px;
  align-items: center;
  min-height: 24px;
}

.typing .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
  animation: typing 1.4s infinite;
}

.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.typing .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { opacity: 0.4; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-4px); }
}

.service-message {
  padding: 8px 20px;
  border-top: 1px solid #fde68a;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
}

.chat-input {
  display: flex;
  gap: 10px;
  padding: 15px 20px;
  border-top: 1px solid #eee;
  background: #fff;
}

.chat-input .el-textarea {
  flex: 1;
}

.chat-input .el-button {
  height: auto;
  padding: 8px 20px;
}

@media (max-width: 640px) {
  .ai-chat-page {
    width: 100%;
    min-height: 100vh;
    padding: 12px;
  }

  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-info {
    flex-wrap: wrap;
  }

  .suggestions {
    grid-template-columns: 1fr;
  }

  .message-content {
    max-width: calc(100% - 50px);
  }

  .chat-messages {
    padding: 14px;
  }
}
</style>
