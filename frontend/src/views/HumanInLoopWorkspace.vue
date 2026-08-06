<template>
  <div class="desktop-workspace-shell" data-testid="human-loop-workspace">
    <DesktopAgentStatusPanel
      :user-name="auth.user.value?.display_name ?? ''"
      :store-name="selectedStore?.storeName ?? ''"
      :status="desktopAgentStatus"
      :error="desktopAgentError"
      :error-kind="desktopAgentErrorKind"
      :loading="desktopAgentLoading"
      :binding-busy="desktopBindingBusy"
      :binding-grant="desktopBindingGrant"
      :can-bind="auth.user.value?.roles.includes('CUSTOMER_SERVICE') === true"
      @refresh="loadDesktopAgentStatus"
      @bind="requestDesktopBinding"
      @clear-grant="clearDesktopBindingGrant"
    />
    <div class="human-loop-workspace-grid">
    <ConversationCenter
      :conversations="conversations"
      :active-conversation-id="activeConversationId"
      :agent-status="agentStatus"
      :conversation-counts="conversationCounts"
      @select="selectConversation"
      @availability="setAgentAvailability"
      @manual-message="receiveManualMessage"
    />
    <ReplyAssistantPanel
      :conversation="activeConversation"
      :draft="activeDraft"
      :stores="stores"
      :products="products"
      :skus="skus"
      :selected-store-id="selectedStoreId"
      :selected-product-id="selectedProductId"
      :selected-sku-id="selectedSkuId"
      :context-loading="contextLoading"
      :context-error="contextMessage"
      :context-status="contextStatus"
      :busy="generationBusy"
      :action-busy="actionBusy"
      :action-error="actionError"
      :agent-status="agentStatus"
      :can-generate-reply="canGenerateReply"
      :can-submit-feedback="canSubmitFeedback"
      :feedback-busy="feedbackBusy"
      :feedback-receipt-id="feedbackReceiptId"
      @select-store="selectStore"
      @select-product="selectProduct"
      @select-sku="selectSku"
      @generate="generateDraft"
      @regenerate="regenerateDraft"
      @start-edit="beginEditing"
      @edit="editDraft"
      @accept="acceptDraft"
      @feedback="submitFeedback"
      @copy="copyApprovedReply"
    />
    <DecisionCenter
      :draft="activeDraft"
      :conversation="activeConversation"
      :receipt-id="interactionReceiptId"
      :feedback-receipt-id="feedbackReceiptId"
      @complete="completeConversation"
      @reopen="reopenConversation"
    />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'

import { aiInteractionEventClient, createAiInteractionEventIdempotencyKey } from '@/api/aiInteractionEventClient'
import { aiResponseFeedbackClient, createAiResponseFeedbackIdempotencyKey } from '@/api/aiResponseFeedbackClient'
import type { AiResponseFeedbackType } from '@/api/aiResponseFeedbackTypes'
import { ragClient } from '@/api/ragClient'
import type { AdoptionType } from '@/api/ragTypes'
import { storeContextClient } from '@/api/storeContextClient'
import { desktopAgentClient } from '@/api/desktopAgentClient'
import { DesktopAgentClientError, type DesktopAgentStatus, type DesktopBindingGrant } from '@/api/desktopAgentTypes'
import type {
  ContextResolution, ProductContextCandidate, SkuContextCandidate, WorkspaceStoreContext
} from '@/api/storeContextTypes'
import { useAuthSession } from '@/auth/authSession'
import ConversationCenter from '@/components/humanLoop/ConversationCenter.vue'
import DesktopAgentStatusPanel from '@/components/humanLoop/DesktopAgentStatusPanel.vue'
import DecisionCenter from '@/components/humanLoop/DecisionCenter.vue'
import ReplyAssistantPanel from '@/components/humanLoop/ReplyAssistantPanel.vue'
import { useHumanLoopWorkspaceStore } from '@/stores/humanLoopWorkspace'
import { createWorkspaceMessageAdapter } from '@/workspace/channelMessageAdapter'
import { recordAiAssist, recordAiFeedbackSubmission } from '@/workspace/customerSessionActivity'

const workspace = useHumanLoopWorkspaceStore()
const auth = useAuthSession()
const {
  conversations, activeConversationId, activeConversation, activeDraft, latestInboundMessage,
  agentStatus, conversationCounts
} = storeToRefs(workspace)
const channelAdapter = createWorkspaceMessageAdapter()

const stores = ref<WorkspaceStoreContext[]>([])
const products = ref<ProductContextCandidate[]>([])
const skus = ref<SkuContextCandidate[]>([])
const selectedStoreId = ref<number | null>(null)
const selectedProductId = ref('')
const selectedSkuId = ref('')
const resolution = ref<ContextResolution | null>(null)
const contextLoading = ref(false)
const contextError = ref('')
const contextWarning = ref('')
const generationBusy = ref(false)
const actionBusy = ref(false)
const actionError = ref('')
const interactionReceiptId = ref('')
const feedbackBusy = ref(false)
const feedbackReceiptId = ref('')
const interactionKeys = new Map<string, string>()
const feedbackKeys = new Map<string, string>()
const desktopAgentStatus = ref<DesktopAgentStatus | null>(null)
const desktopAgentError = ref('')
const desktopAgentErrorKind = ref('')
const desktopAgentLoading = ref(false)
const desktopBindingBusy = ref(false)
const desktopBindingGrant = ref<DesktopBindingGrant | null>(null)
let desktopStatusTimer: ReturnType<typeof setInterval> | null = null
let desktopBindingGrantTimer: ReturnType<typeof setTimeout> | null = null
let desktopStatusRequestSequence = 0

const selectedStore = computed(() => stores.value.find((item) => item.storeId === selectedStoreId.value) ?? null)
const selectedProduct = computed(() => products.value.find((item) => item.productId === selectedProductId.value) ?? null)
const selectedSku = computed(() => skus.value.find((item) => item.skuId === selectedSkuId.value) ?? null)
const contextMessage = computed(() => contextError.value || contextWarning.value)
const contextStatus = computed(() => {
  if (resolution.value?.status === 'RESOLVED') return '上下文已自动识别'
  if (resolution.value?.status === 'PRODUCT_CONFIRMATION_REQUIRED') return '等待商品确认'
  if (resolution.value?.status === 'SKU_CONFIRMATION_REQUIRED') return '等待 SKU 确认'
  return selectedStore.value ? '店铺已自动加载' : '等待店铺'
})
const canGenerateReply = computed(() => auth.hasPermission('ai.reply'))
const canSubmitFeedback = computed(() => auth.hasPermission('feedback.submit'))

const resetResolution = (): void => {
  resolution.value = null
  products.value = []
  skus.value = []
  selectedProductId.value = ''
  selectedSkuId.value = ''
  contextError.value = ''
  contextWarning.value = ''
}

const loadWorkspaceContext = async (): Promise<void> => {
  contextLoading.value = true
  contextError.value = ''
  try {
    const result = await storeContextClient.getContext()
    stores.value = result.stores
    selectedStoreId.value = result.effectiveStore?.storeId ?? null
    if (!selectedStoreId.value) contextError.value = '请先完成默认客服店铺选择。'
    if (selectedStoreId.value) await loadDesktopAgentStatus()
  } catch (error) {
    contextError.value = error instanceof Error ? error.message : '店铺上下文暂时不可用。'
  } finally {
    contextLoading.value = false
  }
}

async function loadDesktopAgentStatus(): Promise<void> {
  if (!selectedStoreId.value) return
  const requestSequence = ++desktopStatusRequestSequence
  const storeId = selectedStoreId.value
  desktopAgentLoading.value = true
  desktopAgentError.value = ''
  desktopAgentErrorKind.value = ''
  try {
    const result = await desktopAgentClient.getStatus(storeId)
    if (requestSequence === desktopStatusRequestSequence) desktopAgentStatus.value = result
  } catch (error) {
    if (requestSequence !== desktopStatusRequestSequence) return
    desktopAgentStatus.value = null
    desktopAgentError.value = error instanceof Error ? error.message : '客服设备状态检查失败。'
    desktopAgentErrorKind.value = error instanceof DesktopAgentClientError ? error.kind : 'unknown'
  } finally {
    if (requestSequence === desktopStatusRequestSequence) desktopAgentLoading.value = false
  }
}

const requestDesktopBinding = async (payload: { agentId: string; deviceId: string }): Promise<void> => {
  if (!selectedStoreId.value || desktopBindingBusy.value) return
  desktopBindingBusy.value = true
  desktopAgentError.value = ''
  desktopAgentErrorKind.value = ''
  if (desktopBindingGrantTimer) clearTimeout(desktopBindingGrantTimer)
  desktopBindingGrantTimer = null
  desktopBindingGrant.value = null
  try {
    desktopBindingGrant.value = await desktopAgentClient.requestBindingGrant({
      ...payload, storeId: selectedStoreId.value
    })
    const expiresIn = Math.max(
      new Date(desktopBindingGrant.value.expiresAt).getTime() - Date.now(), 0
    )
    desktopBindingGrantTimer = setTimeout(() => {
      desktopBindingGrant.value = null
      desktopBindingGrantTimer = null
    }, Math.min(expiresIn, 10 * 60 * 1000))
  } catch (error) {
    desktopAgentError.value = error instanceof Error ? error.message : '客服设备绑定申请失败。'
    desktopAgentErrorKind.value = error instanceof DesktopAgentClientError ? error.kind : 'unknown'
  } finally {
    desktopBindingBusy.value = false
  }
}

const clearDesktopBindingGrant = (): void => {
  if (desktopBindingGrantTimer) clearTimeout(desktopBindingGrantTimer)
  desktopBindingGrantTimer = null
  desktopBindingGrant.value = null
  void loadDesktopAgentStatus()
}

const invalidateDraftForContextChange = (): void => {
  if (activeDraft.value && activeDraft.value.state !== 'MESSAGE_RECEIVED') {
    workspace.restartDraft()
    interactionReceiptId.value = ''
    actionError.value = ''
  }
}

const selectStore = async (storeId: number): Promise<void> => {
  if (!storeId || storeId === selectedStoreId.value) return
  contextLoading.value = true
  contextError.value = ''
  invalidateDraftForContextChange()
  try {
    if (auth.user.value?.roles.includes('CUSTOMER_SERVICE')) {
      await auth.setDefaultStore(storeId)
      stores.value = stores.value.map((item) => ({ ...item, isDefault: item.storeId === storeId }))
    }
    selectedStoreId.value = storeId
    resetResolution()
    desktopBindingGrant.value = null
    await loadDesktopAgentStatus()
  } catch {
    contextError.value = '店铺切换失败，请稍后重试；如持续失败，请联系管理员。'
  } finally {
    contextLoading.value = false
  }
}

const selectProduct = (productId: string): void => {
  selectedProductId.value = productId
  selectedSkuId.value = ''
  skus.value = []
  actionError.value = productId ? '商品已确认，请再次点击生成以继续 SKU 识别。' : ''
}

const selectSku = (skuId: string): void => {
  selectedSkuId.value = skuId
  actionError.value = skuId ? 'SKU 已确认，请再次点击生成回复建议。' : ''
}

const selectConversation = (conversationId: string): void => {
  workspace.selectConversation(conversationId)
  interactionReceiptId.value = ''
  feedbackReceiptId.value = ''
  actionError.value = ''
  resetResolution()
}

const setAgentAvailability = (online: boolean): void => {
  workspace.setAgentAvailability(online)
  actionError.value = online ? '' : '当前客服已离线；可查看会话，但不能接收或生成新回复。'
}

const receiveManualMessage = async (payload: {
  conversationId: string | null
  customerLabel: string
  content: string
}): Promise<void> => {
  if (agentStatus.value === 'OFFLINE') {
    actionError.value = '客服离线时不能接收人工消息。'
    return
  }
  try {
    if (payload.conversationId) {
      const message = await channelAdapter.receiveManualMessage(payload.conversationId, payload.content)
      workspace.receiveMessage(message)
    } else {
      const conversation = await channelAdapter.createManualConversation(
        payload.customerLabel,
        payload.content
      )
      workspace.addConversation(conversation)
    }
    interactionReceiptId.value = ''
    feedbackReceiptId.value = ''
    actionError.value = ''
    resetResolution()
    ElMessage.info('已接收人工录入消息；旧草稿已失效，内容不会写入浏览器存储')
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '人工消息接收失败。'
  }
}

const resolveConversation = async (): Promise<ContextResolution | null> => {
  if (!activeConversation.value || !selectedStoreId.value) {
    actionError.value = '缺少默认店铺或会话，无法识别商品上下文。'
    return null
  }
  contextLoading.value = true
  try {
    const result = await storeContextClient.resolve({
      conversation: activeConversation.value.messages.map((message) => ({
        role: message.direction === 'INBOUND' ? 'CUSTOMER' as const : 'AGENT' as const,
        content: message.content
      })),
      storeId: selectedStoreId.value,
      confirmedProductId: selectedProductId.value || null,
      confirmedSkuId: selectedSkuId.value || null
    })
    resolution.value = result
    products.value = result.productCandidates
    skus.value = result.skuCandidates
    if (result.product) selectedProductId.value = result.product.productId
    if (result.sku) selectedSkuId.value = result.sku.skuId
    if (result.status === 'PRODUCT_CONFIRMATION_REQUIRED') {
      actionError.value = '识别到多个商品，请确认客户正在咨询的商品。'
      return null
    }
    if (result.status === 'SKU_CONFIRMATION_REQUIRED') {
      actionError.value = '识别到多个 SKU，请确认具体款式。'
      return null
    }
    if (result.status !== 'RESOLVED') {
      actionError.value = result.status === 'UNKNOWN'
        ? '暂时无法识别商品，请补充商品名称或编号。'
        : '请先完成默认店铺选择。'
      return null
    }
    actionError.value = ''
    return result
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '商品上下文识别失败。'
    return null
  } finally {
    contextLoading.value = false
  }
}

const generateDraft = async (): Promise<void> => {
  const draft = activeDraft.value
  const message = latestInboundMessage.value
  if (!draft || !message || !selectedStore.value) {
    actionError.value = '请先选择会话并完成默认店铺配置。'
    return
  }
  if (agentStatus.value === 'OFFLINE') {
    actionError.value = '客服离线时不能生成回复。'
    return
  }
  if (!canGenerateReply.value) {
    actionError.value = '当前账号没有 AI 回复权限。'
    return
  }
  if (draft.state !== 'MESSAGE_RECEIVED') return

  generationBusy.value = true
  actionError.value = ''
  interactionReceiptId.value = ''
  try {
    const resolved = await resolveConversation()
    if (!resolved) return
    workspace.beginUnderstanding()
    await nextTick()
    workspace.beginGenerating()
    const result = await ragClient.chat({
      question: message.content,
      resolution_id: resolved.resolutionId
    })
    if (result.warnings.includes('KNOWLEDGE_NOT_PUBLISHED')) {
      throw new Error('该商品的 AI 知识尚未发布，请联系运营完成知识发布后重试。')
    }
    if (result.warnings.includes('RAG_RUNTIME_ERROR')) {
      throw new Error('AI 服务暂时异常，请稍后重试；如持续失败，请联系管理员。')
    }
    if (result.warnings.includes('LLM_REQUEST_FAILED')) {
      throw new Error('AI 回复生成失败，请检查服务状态后重试。')
    }
    workspace.setDraftReady({
      answer: result.answer, requestId: result.requestId, action: result.action,
      riskLevel: result.riskLevel, citations: result.citations,
      warnings: result.warnings, requiredFields: result.requiredFields
    })
    recordAiAssist()
    workspace.beginHumanReview()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : 'AI 回复建议生成失败。'
    workspace.markDraftExpired()
  } finally {
    generationBusy.value = false
  }
}

const regenerateDraft = async (): Promise<void> => {
  workspace.restartDraft()
  resolution.value = null
  await generateDraft()
}

const editDraft = (value: string): void => {
  try { workspace.editDraft(value); actionError.value = '' }
  catch (error) { actionError.value = error instanceof Error ? error.message : '草稿当前不可编辑。' }
}

const beginEditing = (): void => {
  try { workspace.beginEditing(); actionError.value = '' }
  catch (error) { actionError.value = error instanceof Error ? error.message : '草稿当前不可修改。' }
}

const interactionKeyFor = (draftId: string, actionType: AdoptionType): string => {
  const fingerprint = `${draftId}:${actionType}`
  const existing = interactionKeys.get(fingerprint)
  if (existing) return existing
  const created = createAiInteractionEventIdempotencyKey()
  interactionKeys.set(fingerprint, created)
  return created
}

const feedbackKeyFor = (
  draftId: string,
  mode: 'REJECT' | 'ISSUE',
  feedbackType: AiResponseFeedbackType,
  note: string | null
): string => {
  const fingerprint = `${draftId}:${mode}:${feedbackType}:${note?.trim() ?? ''}`
  const existing = feedbackKeys.get(fingerprint)
  if (existing) return existing
  const created = createAiResponseFeedbackIdempotencyKey()
  feedbackKeys.set(fingerprint, created)
  return created
}

const recordInteraction = async (actionType: AdoptionType): Promise<string> => {
  const draft = activeDraft.value
  const message = activeConversation.value?.messages.find((item) => item.messageId === draft?.messageId)
  if (!draft || !message || !selectedStore.value || !selectedProduct.value) {
    throw new Error('缺少已解析的店铺或商品上下文，无法保存反馈。')
  }
  const actorId = auth.user.value?.id
  if (!actorId) throw new Error('登录身份已失效，无法保存反馈。')
  const finalAnswer = actionType === 'REJECTED'
    ? null
    : actionType === 'DIRECT_ACCEPT' ? draft.originalAnswer : draft.editedAnswer.trim()
  if (actionType === 'EDITED_ACCEPT' && !finalAnswer) throw new Error('修改后的回复不能为空。')

  const receipt = await aiInteractionEventClient.submit({
    interactionId: draft.requestId || draft.draftId,
    storeCode: selectedStore.value.storeCode,
    storeName: selectedStore.value.storeName,
    productId: selectedProduct.value.productId,
    productName: selectedProduct.value.displayName,
    skuId: selectedSku.value?.skuId ?? null,
    skuName: selectedSku.value?.displayName ?? null,
    actionType,
    questionSummary: message.content,
    aiAnswerSummary: draft.originalAnswer,
    finalAnswerSummary: finalAnswer,
    createdBy: actorId
  }, interactionKeyFor(draft.draftId, actionType))
  return receipt.eventId
}

const acceptDraft = async (type: 'DIRECT_ACCEPT' | 'EDITED_ACCEPT'): Promise<void> => {
  if (!canSubmitFeedback.value) {
    actionError.value = '当前账号没有反馈提交权限。'
    return
  }
  actionBusy.value = true; actionError.value = ''
  try {
    interactionReceiptId.value = await recordInteraction(type)
    workspace.acceptDraft()
    ElMessage.success('采用结果已记录；请人工复制并发送')
  } catch (error) { actionError.value = error instanceof Error ? error.message : '采用结果保存失败。' }
  finally { actionBusy.value = false }
}

const submitFeedback = async (payload: {
  mode: 'REJECT' | 'ISSUE'
  feedbackType: AiResponseFeedbackType
  note: string | null
}): Promise<void> => {
  const draft = activeDraft.value
  const message = activeConversation.value?.messages.find((item) => item.messageId === draft?.messageId)
  if (!canSubmitFeedback.value) {
    actionError.value = '当前账号没有反馈提交权限。'
    return
  }
  if (!draft || !message || !selectedStore.value || !selectedProduct.value) {
    actionError.value = '缺少已解析的会话、店铺或商品，无法记录问题。'
    return
  }
  const actorId = auth.user.value?.id
  if (!actorId) {
    actionError.value = '登录身份已失效，无法记录问题。'
    return
  }
  feedbackBusy.value = true
  actionBusy.value = true
  actionError.value = ''
  try {
    if (payload.mode === 'REJECT') {
      interactionReceiptId.value = await recordInteraction('REJECTED')
    }
    const receipt = await aiResponseFeedbackClient.submit({
      storeCode: selectedStore.value.storeCode,
      productId: selectedProduct.value.productId,
      skuId: selectedSku.value?.skuId ?? null,
      question: message.content,
      aiAnswer: draft.originalAnswer,
      feedbackType: payload.feedbackType,
      feedbackNote: payload.note,
      finalAnswer: draft.state === 'EDITED' ? draft.editedAnswer.trim() || null : null,
      createdBy: actorId,
      interactionId: draft.requestId || draft.draftId
    }, feedbackKeyFor(draft.draftId, payload.mode, payload.feedbackType, payload.note))
    feedbackReceiptId.value = receipt.feedbackId
    recordAiFeedbackSubmission()
    if (payload.mode === 'REJECT') {
      workspace.rejectDraft()
      ElMessage.success('拒绝回复与原因已记录并进入Badcase分析')
    } else {
      ElMessage.success('问题标记已记录；仍需选择采用、修改或拒绝')
    }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '问题反馈保存失败。'
  } finally {
    feedbackBusy.value = false
    actionBusy.value = false
  }
}

const copyApprovedReply = async (): Promise<void> => {
  const text = activeDraft.value?.editedAnswer.trim()
  if (!text || activeDraft.value?.decisionState !== 'APPROVED') return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制，请在渠道窗口人工核对后发送')
  } catch { actionError.value = '浏览器无法自动复制，请手动选择草稿文本。' }
}

const completeConversation = (): void => {
  try {
    workspace.completeConversation()
    actionError.value = ''
    ElMessage.success('会话已由客服显式标记完成')
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '会话无法完成。'
  }
}

const reopenConversation = (): void => {
  try {
    workspace.reopenConversation()
    interactionReceiptId.value = ''
    feedbackReceiptId.value = ''
    actionError.value = ''
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '会话无法重新打开。'
  }
}

onMounted(async () => {
  workspace.installConversations(await channelAdapter.listConversations())
  await loadWorkspaceContext()
  desktopStatusTimer = setInterval(() => {
    if (document.visibilityState === 'visible') void loadDesktopAgentStatus()
  }, 30_000)
})

onBeforeUnmount(() => {
  desktopStatusRequestSequence += 1
  if (desktopStatusTimer) clearInterval(desktopStatusTimer)
  desktopStatusTimer = null
  if (desktopBindingGrantTimer) clearTimeout(desktopBindingGrantTimer)
  desktopBindingGrantTimer = null
  desktopBindingGrant.value = null
})
</script>

<style scoped>
.desktop-workspace-shell {
  display: grid;
  gap: 10px;
  min-width: 980px;
}

.human-loop-workspace-grid {
  display: grid;
  grid-template-columns: minmax(220px, 260px) minmax(580px, 1fr) minmax(210px, 250px);
  width: 100%;
  min-width: 980px;
  height: calc(100vh - 154px);
  min-height: 650px;
  overflow: hidden;
  border: 1px solid #283956;
  border-radius: 15px;
  background: #0c1422;
  box-shadow: 0 24px 60px rgb(13 27 52 / 18%);
}

@media (max-width: 1280px) {
  .human-loop-workspace-grid { grid-template-columns: 230px minmax(540px, 1fr) 220px; }
}
</style>
