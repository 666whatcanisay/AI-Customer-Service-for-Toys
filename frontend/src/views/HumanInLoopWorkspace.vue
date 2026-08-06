<template>
  <div class="human-loop-workspace" data-testid="human-loop-workspace">
    <ConversationCenter
      :conversations="conversations"
      :active-conversation-id="activeConversationId"
      @select="selectConversation"
      @mock-message="receiveMockMessage"
    />
    <ReplyAssistantPanel
      :conversation="activeConversation"
      :draft="activeDraft"
      :stores="stores"
      :products="products"
      :skus="skus"
      :selected-store-code="selectedStoreCode"
      :selected-product-id="selectedProductId"
      :selected-sku-id="selectedSkuId"
      :context-loading="contextLoading"
      :context-error="contextMessage"
      :busy="generationBusy"
      :action-busy="actionBusy"
      :action-error="actionError"
      @select-store="selectStore"
      @select-product="selectProduct"
      @select-sku="selectSku"
      @generate="generateDraft"
      @regenerate="regenerateDraft"
      @edit="editDraft"
      @accept="acceptDraft"
      @reject="rejectDraft"
      @copy="copyApprovedReply"
    />
    <DecisionCenter :draft="activeDraft" :receipt-id="interactionReceiptId" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'

import { aiInteractionEventClient, createAiInteractionEventIdempotencyKey } from '@/api/aiInteractionEventClient'
import { platformClient } from '@/api/platformClient'
import type { CatalogProduct, CatalogSku, CatalogStore } from '@/api/platformTypes'
import { ragClient } from '@/api/ragClient'
import type { AdoptionType } from '@/api/ragTypes'
import ConversationCenter from '@/components/humanLoop/ConversationCenter.vue'
import DecisionCenter from '@/components/humanLoop/DecisionCenter.vue'
import ReplyAssistantPanel from '@/components/humanLoop/ReplyAssistantPanel.vue'
import { useHumanLoopWorkspaceStore } from '@/stores/humanLoopWorkspace'
import { MockChannelMessageAdapter } from '@/workspace/channelMessageAdapter'
import { useTesterIdentity } from '@/workspace/testerIdentity'

const workspace = useHumanLoopWorkspaceStore()
const {
  conversations,
  activeConversationId,
  activeConversation,
  activeDraft,
  latestInboundMessage
} = storeToRefs(workspace)
const identity = useTesterIdentity().identity
const channelAdapter = new MockChannelMessageAdapter()

const stores = ref<CatalogStore[]>([])
const products = ref<CatalogProduct[]>([])
const skus = ref<CatalogSku[]>([])
const selectedStoreCode = ref('')
const selectedProductId = ref('')
const selectedSkuId = ref('')
const contextLoading = ref(false)
const contextError = ref('')
const contextWarning = ref('')
const generationBusy = ref(false)
const actionBusy = ref(false)
const actionError = ref('')
const interactionReceiptId = ref('')

const selectedStore = computed(() => stores.value.find((item) => item.storeCode === selectedStoreCode.value) ?? null)
const selectedProduct = computed(() => products.value.find((item) => item.productId === selectedProductId.value) ?? null)
const selectedSku = computed(() => skus.value.find((item) => item.skuId === selectedSkuId.value) ?? null)
const contextMessage = computed(() => contextError.value || contextWarning.value)

const warningSummary = (warnings: { message: string }[]): string => warnings.length
  ? `目录返回部分异常：${warnings.map((item) => item.message).join('；')}`
  : ''

const loadCatalog = async (): Promise<void> => {
  contextLoading.value = true
  contextError.value = ''
  contextWarning.value = ''
  try {
    const envelope = await platformClient.listStores()
    stores.value = envelope.items
    contextWarning.value = warningSummary(envelope.warnings)
    if (!stores.value.length) {
      contextError.value = envelope.resultStatus === 'PARTIAL'
        ? '商品目录暂时异常，请联系运营处理。'
        : '当前没有已启用的客服店铺。'
      return
    }
    const initialStore = stores.value.find(
      (item) => item.storeCode === identity.value.defaultStoreCode
    ) ?? stores.value[0]
    selectedStoreCode.value = initialStore.storeCode
    await loadProducts()
  } catch (error) {
    contextError.value = error instanceof Error ? error.message : '客服商品目录暂时不可用。'
  } finally {
    contextLoading.value = false
  }
}

const loadProducts = async (): Promise<void> => {
  products.value = []
  skus.value = []
  selectedProductId.value = ''
  selectedSkuId.value = ''
  if (!selectedStore.value) return
  const envelope = await platformClient.listProducts(selectedStore.value)
  products.value = envelope.items
  contextWarning.value = warningSummary(envelope.warnings)
  if (!products.value.length) {
    contextError.value = envelope.resultStatus === 'PARTIAL'
      ? '该店铺商品目录暂时异常，请联系运营处理。'
      : '该店铺当前没有客服可用商品。'
    return
  }
  selectedProductId.value = products.value[0].productId
  await loadSkus()
}

const loadSkus = async (): Promise<void> => {
  skus.value = []
  selectedSkuId.value = ''
  if (!selectedStore.value || !selectedProduct.value) return
  const envelope = await platformClient.listSkus(selectedStore.value, selectedProduct.value)
  skus.value = envelope.items
  const warning = warningSummary(envelope.warnings)
  if (warning) contextWarning.value = warning
}

const selectStore = async (storeCode: string): Promise<void> => {
  selectedStoreCode.value = storeCode
  contextLoading.value = true
  contextError.value = ''
  contextWarning.value = ''
  invalidateDraftForContextChange()
  try {
    await loadProducts()
  } catch (error) {
    contextError.value = error instanceof Error ? error.message : '商品目录读取失败。'
  } finally {
    contextLoading.value = false
  }
}

const selectProduct = async (productId: string): Promise<void> => {
  selectedProductId.value = productId
  contextLoading.value = true
  contextError.value = ''
  contextWarning.value = ''
  invalidateDraftForContextChange()
  try {
    await loadSkus()
  } catch (error) {
    contextError.value = error instanceof Error ? error.message : 'SKU 目录读取失败。'
  } finally {
    contextLoading.value = false
  }
}

const selectSku = (skuId: string): void => {
  selectedSkuId.value = skuId
  invalidateDraftForContextChange()
}

const invalidateDraftForContextChange = (): void => {
  if (activeDraft.value && activeDraft.value.state !== 'MESSAGE_RECEIVED') {
    workspace.restartDraft()
    interactionReceiptId.value = ''
    actionError.value = ''
  }
}

const selectConversation = (conversationId: string): void => {
  workspace.selectConversation(conversationId)
  interactionReceiptId.value = ''
  actionError.value = ''
}

const receiveMockMessage = async (content: string): Promise<void> => {
  try {
    const message = await channelAdapter.receiveMockMessage(activeConversationId.value, content)
    workspace.receiveMessage(message)
    interactionReceiptId.value = ''
    actionError.value = ''
    ElMessage.info('已接收模拟客户消息，旧草稿已失效')
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '模拟消息接收失败。'
  }
}

const generateDraft = async (): Promise<void> => {
  const draft = activeDraft.value
  const message = latestInboundMessage.value
  if (!draft || !message || !selectedStore.value || !selectedProduct.value) {
    actionError.value = '请先选择会话、店铺和商品。'
    return
  }
  if (draft.state !== 'MESSAGE_RECEIVED') return

  generationBusy.value = true
  actionError.value = ''
  interactionReceiptId.value = ''
  try {
    workspace.beginUnderstanding()
    await nextTick()
    workspace.beginGenerating()
    const result = await ragClient.chat({
      question: message.content,
      context: {
        tenant_id: selectedStore.value.tenantId,
        platform: selectedStore.value.platform,
        store_code: selectedStore.value.storeCode,
        product_id: selectedProduct.value.productId,
        sku_id: selectedSku.value?.skuId ?? null
      }
    })
    workspace.setDraftReady({
      answer: result.answer,
      requestId: result.requestId,
      action: result.action,
      riskLevel: result.riskLevel,
      citations: result.citations,
      warnings: result.warnings,
      requiredFields: result.requiredFields
    })
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
  await generateDraft()
}

const editDraft = (value: string): void => {
  try {
    workspace.editDraft(value)
    actionError.value = ''
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '草稿当前不可编辑。'
  }
}

const recordInteraction = async (actionType: AdoptionType): Promise<string> => {
  const draft = activeDraft.value
  const message = activeConversation.value?.messages.find((item) => item.messageId === draft?.messageId)
  if (!draft || !message || !selectedStore.value || !selectedProduct.value) {
    throw new Error('缺少会话、店铺或商品上下文，无法保存反馈。')
  }
  const finalAnswer = actionType === 'REJECTED'
    ? null
    : actionType === 'DIRECT_ACCEPT'
      ? draft.originalAnswer
      : draft.editedAnswer.trim()
  if (actionType === 'EDITED_ACCEPT' && !finalAnswer) throw new Error('修改后的回复不能为空。')

  const receipt = await aiInteractionEventClient.submit({
    interactionId: draft.requestId || draft.draftId,
    storeCode: selectedStore.value.storeCode,
    storeName: selectedStore.value.name,
    productId: selectedProduct.value.productId,
    productName: selectedProduct.value.displayName,
    skuId: selectedSku.value?.skuId ?? null,
    skuName: selectedSku.value?.displayName ?? null,
    actionType,
    questionSummary: message.content,
    aiAnswerSummary: draft.originalAnswer,
    finalAnswerSummary: finalAnswer,
    createdBy: identity.value.reporterId
  }, createAiInteractionEventIdempotencyKey())
  return receipt.eventId
}

const acceptDraft = async (type: 'DIRECT_ACCEPT' | 'EDITED_ACCEPT'): Promise<void> => {
  actionBusy.value = true
  actionError.value = ''
  try {
    interactionReceiptId.value = await recordInteraction(type)
    workspace.acceptDraft()
    ElMessage.success('采用结果已记录；请人工复制并发送')
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '采用结果保存失败。'
  } finally {
    actionBusy.value = false
  }
}

const rejectDraft = async (): Promise<void> => {
  actionBusy.value = true
  actionError.value = ''
  try {
    interactionReceiptId.value = await recordInteraction('REJECTED')
    workspace.rejectDraft()
    ElMessage.success('拒绝结果已记录并进入反馈闭环')
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '拒绝结果保存失败。'
  } finally {
    actionBusy.value = false
  }
}

const copyApprovedReply = async (): Promise<void> => {
  const text = activeDraft.value?.editedAnswer.trim()
  if (!text || activeDraft.value?.decisionState !== 'APPROVED') return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制，请在渠道窗口人工核对后发送')
  } catch {
    actionError.value = '浏览器无法自动复制，请手动选择草稿文本。'
  }
}

onMounted(async () => {
  workspace.installConversations(await channelAdapter.listConversations())
  await loadCatalog()
})
</script>

<style scoped>
.human-loop-workspace {
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
  .human-loop-workspace { grid-template-columns: 230px minmax(540px, 1fr) 220px; }
}
</style>
