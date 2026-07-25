<template>
  <main class="workspace-shell">
    <header class="workspace-header">
      <div>
        <p class="eyebrow">木木小栈 · AI 客服工作台</p>
        <h1>跟着步骤，生成一条客服建议</h1>
        <p class="subtitle">先选客户咨询的商品，再输入问题。AI 只生成建议，由你确认、修改和复制。</p>
      </div>
      <div class="system-summary" data-testid="system-summary">
        <span class="status-dot" :class="{ ready: systemReady }" />
        <div>
          <strong>{{ systemReady ? '系统已就绪' : '系统正在连接' }}</strong>
          <p>{{ systemReady ? '可以开始处理测试问题' : '请稍候或刷新连接状态' }}</p>
        </div>
        <el-button link @click="showConnectionDetails = !showConnectionDetails">
          {{ showConnectionDetails ? '收起' : '技术详情' }}
        </el-button>
      </div>
    </header>

    <el-alert
      data-testid="safety-notice"
      class="safety-alert"
      title="当前为测试数据，仅供内部验证，禁止直接用于真实客户。"
      description="仅供建议，禁止自动发送。发送前必须人工核对商品、回复内容和引用。"
      type="error"
      :closable="false"
      show-icon
    />

    <section class="customer-friendly-notice" data-testid="customer-friendly-notice">
      <strong>测试环境提示</strong>
      <ul>
        <li>AI 辅助客服</li>
        <li>需要人工确认</li>
        <li>不自动发送</li>
        <li>不自动退款</li>
        <li>不修改订单</li>
      </ul>
    </section>

    <section v-if="showConnectionDetails" class="connection-card" data-testid="connection-details">
      <div data-testid="rag-health-status">
        <span>A 问答服务</span>
        <el-tag :type="ragHealthTagType" effect="light">{{ ragHealthStatusText }}</el-tag>
        <el-button link :loading="ragHealthLoading" @click="refreshRagHealth">刷新</el-button>
      </div>
      <div data-testid="platform-health-status">
        <span>C 商品目录</span>
        <el-tag :type="platformHealthTagType" effect="light">{{ platformHealthStatusText }}</el-tag>
        <el-button link :loading="platformHealthLoading" @click="refreshPlatform">刷新</el-button>
      </div>
      <div class="runtime-details" data-testid="runtime-details">
        <span>前端版本</span><code>{{ runtimeDetails.frontendVersion }}</code>
        <span>Git Commit</span><code>{{ runtimeDetails.gitCommit }}</code>
        <span>启动模式</span><code>{{ runtimeDetails.startMode }}</code>
        <span>API 模式</span><code>{{ runtimeDetails.apiMode }}</code>
        <span>当前客服入口</span><code>{{ runtimeDetails.customerEntry }}</code>
      </div>
    </section>

    <el-alert
      v-if="ragHealthError"
      class="status-alert"
      title="AI 服务不可用，请稍后重试或按原客服流程处理。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="platformError"
      data-testid="platform-error"
      class="status-alert"
      title="数据服务不可用，请联系技术人员检查中台。"
      type="error"
      :closable="false"
      show-icon
    />

    <nav class="workflow-progress" aria-label="操作步骤">
      <div :class="{ active: workflowStep === 1, done: workflowStep > 1 }">
        <span>1</span><strong>选择商品</strong>
      </div>
      <i />
      <div :class="{ active: workflowStep === 2, done: workflowStep > 2 }">
        <span>2</span><strong>输入问题</strong>
      </div>
      <i />
      <div :class="{ active: workflowStep === 3 }">
        <span>3</span><strong>核对并复制</strong>
      </div>
    </nav>

    <section class="workbench-grid" aria-label="客服建议工作区">
      <div class="composer-pane">
    <section class="step-card context-card">
      <div class="section-heading">
        <div>
          <p class="section-label">第 1 步</p>
          <h2>客户问的是哪件商品？</h2>
          <p>按顺序选择店铺和商品；知道具体款式时再选 SKU。</p>
        </div>
        <el-tag type="warning" effect="dark">仅测试数据</el-tag>
      </div>

      <div class="context-grid">
        <label>
          <span><b>1</b> 平台与店铺 <em>必选</em></span>
          <el-select
            v-model="selectedStoreKey"
            data-testid="store-select"
            placeholder="例如：拼多多 → 汕明"
            :loading="storesLoading"
            :disabled="loading"
            filterable
            @change="handleStoreChange"
          >
            <el-option
              v-for="store in stores"
              :key="storeKey(store)"
              :label="storeOptionLabel(store)"
              :value="storeKey(store)"
            />
          </el-select>
          <small>先确认客户来自哪个店铺</small>
        </label>

        <label>
          <span><b>2</b> 商品 <em>必选</em></span>
          <el-select
            v-model="selectedProductId"
            data-testid="product-select"
            placeholder="选择店铺后可选商品"
            :loading="productsLoading"
            :disabled="!selectedStore || loading"
            filterable
            @change="handleProductChange"
          >
            <el-option
              v-for="product in products"
              :key="product.productId"
              :label="productOptionLabel(product)"
              :value="product.productId"
              :disabled="!product.publishable"
            />
          </el-select>
          <small>{{ selectedStore ? '请选择客户正在咨询的商品' : '请先选择上方店铺' }}</small>
        </label>

        <label>
          <span><b>3</b> 具体款式 / SKU <em class="optional">可选</em></span>
          <el-select
            v-model="selectedSkuId"
            data-testid="sku-select"
            placeholder="不确定就留空"
            :loading="skusLoading"
            :disabled="!selectedProduct || loading"
            clearable
            filterable
            @change="clearAnswer"
          >
            <el-option
              v-for="sku in skus"
              :key="sku.skuId"
              :label="skuOptionLabel(sku)"
              :value="sku.skuId"
              :disabled="!sku.publishable"
            />
          </el-select>
          <small>不知道款式时不要猜，AI 会提示追问</small>
        </label>
      </div>

      <div v-if="selectedStore && selectedProduct" class="selection-confirmed" data-testid="context-summary">
        <span class="check-mark">✓</span>
        <div>
          <strong>已选择：{{ platformName(selectedStore.platform) }} · {{ selectedStore.name }}</strong>
          <p>{{ selectedProduct.displayName }}<template v-if="selectedSku"> · {{ selectedSku.displayName }}</template></p>
        </div>
        <el-button link @click="showTechnicalDetails = !showTechnicalDetails">
          {{ showTechnicalDetails ? '隐藏技术信息' : '查看技术信息' }}
        </el-button>
      </div>
      <div v-if="showTechnicalDetails && selectedStore && selectedProduct" class="technical-box" data-testid="context-technical-details">
        <code>tenant_id={{ selectedStore.tenantId }}</code>
        <code>platform={{ selectedStore.platform }}</code>
        <code>store_code={{ selectedStore.storeCode }}</code>
        <code>product_id={{ selectedProduct.productId }}</code>
        <code>sku_id={{ selectedSku?.skuId ?? '未选择' }}</code>
      </div>
    </section>

    <section class="step-card question-card">
      <div class="section-heading">
        <div>
          <p class="section-label">第 2 步</p>
          <h2>客户具体问了什么？</h2>
          <p>尽量保留客户原话，不要自行补充价格、库存或承诺。</p>
        </div>
      </div>
      <label class="question-label" for="customer-question">客户问题</label>
      <el-input
        id="customer-question"
        v-model="customerQuestion"
        data-testid="question-input"
        type="textarea"
        :rows="6"
        maxlength="4000"
        show-word-limit
        placeholder="例如：这个款式适合几岁的小朋友？"
        :disabled="loading"
        @keydown.enter.exact.prevent="submitQuestion"
      />
      <div class="example-row">
        <span>不会写？试试：</span>
        <button type="button" @click="useExample('这个款式适合几岁的小朋友？')">适用年龄</button>
        <button type="button" @click="useExample('这个商品现在有库存吗？')">查询库存</button>
        <button type="button" @click="useExample('客户说少了零件，应该怎么处理？')">缺件处理</button>
      </div>
      <div class="question-actions">
        <span class="input-hint">店铺和商品选好后才可生成；Shift+Enter 换行</span>
        <el-button
          v-if="loading"
          data-testid="cancel-button"
          type="danger"
          link
          @click="cancelRequest"
        >
          取消请求
        </el-button>
        <el-button
          data-testid="submit-button"
          type="primary"
          size="large"
          :loading="loading"
          :disabled="!canSubmit"
          @click="submitQuestion"
        >
          生成建议回复
        </el-button>
      </div>
    </section>

    <el-alert
      v-if="requestError"
      data-testid="request-error"
      class="status-alert"
      :title="requestError"
      type="error"
      :closable="false"
      show-icon
    />

    <section v-if="loading" class="loading-card" data-testid="loading-state">
      <div class="loading-dot" />
      <div>
        <strong>正在查询商品资料并生成建议</strong>
        <p>请稍候，不要重复提交；系统不会自动发送回复。</p>
      </div>
    </section>

      </div>
      <div class="review-pane">
    <section v-if="result" class="step-card answer-card" data-testid="answer-card">
      <div class="section-heading answer-heading">
        <div>
          <p class="section-label">第 3 步</p>
          <h2>核对、修改，再人工复制</h2>
          <div class="result-tags">
            <el-tag :type="actionTagType" data-testid="action-tag">{{ actionText }}</el-tag>
            <el-tag :type="riskTagType" data-testid="risk-tag">{{ riskText }}</el-tag>
          </div>
        </div>
      </div>

      <div class="action-guide" :class="actionGuide.tone" data-testid="action-guidance">
        <div class="guide-icon">{{ actionGuide.icon }}</div>
        <div>
          <strong>{{ actionGuide.title }}</strong>
          <p>{{ actionGuide.description }}</p>
          <ul>
            <li v-for="item in actionGuide.steps" :key="item">{{ item }}</li>
          </ul>
        </div>
      </div>

      <el-alert
        class="result-alert"
        title="仅供建议，禁止自动发送。请先阅读并修改，再复制到客服工具。"
        type="warning"
        :closable="false"
        show-icon
      />

      <label class="reply-label" for="reply-draft">建议回复 <span>可以直接修改</span></label>
      <el-input
        id="reply-draft"
        v-model="replyDraft"
        data-testid="reply-draft"
        class="reply-editor"
        type="textarea"
        :rows="7"
        maxlength="8000"
        show-word-limit
        @input="copyStatus = 'idle'"
      />
      <div class="copy-row">
        <span>复制的是上方当前内容，包括你的修改。</span>
        <el-button data-testid="copy-button" type="primary" size="large" @click="copyReply">
          {{ copyStatus === 'copied' ? '✓ 已复制修改后的回复' : '复制修改后的回复' }}
        </el-button>
      </div>

      <el-alert
        v-if="result.warnings.length"
        class="result-alert"
        :title="result.warnings.join('；')"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="result.requiredFields.length"
        data-testid="required-fields"
        class="result-alert"
        :title="`还需要向客户确认：${requiredFieldText}`"
        type="info"
        :closable="false"
        show-icon
      />

      <details class="evidence-section" data-testid="sources-details">
        <summary>查看回答依据（{{ result.citations.length }} 条）</summary>
        <div class="evidence-heading">
          <div>
            <h2>回答依据</h2>
            <p>发送前至少核对一条依据是否与所选商品一致。</p>
          </div>
          <span>{{ result.citations.length }} 条</span>
        </div>
        <div v-if="result.citations.length" class="evidence-list">
          <article
            v-for="(citation, index) in result.citations"
            :key="`${citation.file}-${citation.page}-${index}`"
            class="evidence-item"
            data-testid="citation-item"
          >
            <div class="evidence-title">
              <strong>依据 {{ index + 1 }}</strong>
              <span>{{ citation.file }}{{ citation.page === null ? '' : ` · 第 ${citation.page} 页` }}</span>
            </div>
            <p>{{ citation.summary || 'API 未返回可读摘要，请勿仅凭此条发送。' }}</p>
            <div v-if="showTechnicalDetails" class="evidence-meta" data-testid="citation-technical-details">
              <span v-if="citation.chunkId">片段 {{ citation.chunkId }}</span>
              <span v-if="citation.knowledgeVersion">版本 {{ citation.knowledgeVersion }}</span>
              <span v-if="citation.productId">商品 {{ citation.productId }}</span>
              <span v-if="citation.skuId">SKU {{ citation.skuId }}</span>
              <span v-if="citation.sourceIds.length">来源 ID {{ citation.sourceIds.join('、') }}</span>
            </div>
          </article>
        </div>
        <el-empty v-else description="本次没有返回依据，请不要直接采用" :image-size="64" />
      </details>

      <div class="technical-toggle-row">
        <el-button data-testid="technical-toggle" plain @click="showTechnicalDetails = !showTechnicalDetails">
          {{ showTechnicalDetails ? '隐藏技术详情' : '需要排查问题？展开技术详情' }}
        </el-button>
      </div>
      <div v-if="showTechnicalDetails" class="technical-box" data-testid="answer-technical-details">
        <code>request_id={{ result.requestId ?? '未提供' }}</code>
        <code>model={{ result.model ?? '未提供' }}</code>
        <code>latency={{ result.latencyMs === null ? '未提供' : `${Math.round(result.latencyMs)} ms` }}</code>
        <code>action={{ result.action ?? '未分类' }}</code>
        <code>risk_level={{ result.riskLevel ?? '未分类' }}</code>
      </div>

      <details class="feedback-section" data-testid="feedback-section">
        <summary>记录这条建议有没有用（可选）</summary>
        <div class="feedback-body">
          <p>当前采用反馈只记录在本页。保存经验案例时必须在表单中明确选择冻结的经验类型。</p>
          <div class="feedback-actions">
            <el-button data-testid="direct-accept" text @click="recordAdoption('DIRECT_ACCEPT')">
              直接采用
            </el-button>
            <el-button data-testid="edited-accept" text @click="recordAdoption('EDITED_ACCEPT')">
              修改后采用
            </el-button>
            <el-button data-testid="reject" text @click="recordAdoption('REJECTED')">
              未采用
            </el-button>
            <el-button
              v-if="adoption?.type === 'REJECTED'"
              data-testid="open-ai-feedback"
              text
              :disabled="aiFeedbackSubmitting"
              @click="openAiFeedbackCapture"
            >
              ⚑ AI 问题反馈
            </el-button>
            <el-button
              data-testid="save-experience-case"
              text
              :disabled="!adoption || adoption.type === 'REJECTED' || experienceCaseSubmitting"
              @click="openExperienceCaseCapture"
            >
              ⭐ 收藏为优秀案例
            </el-button>
          </div>
          <p class="experience-case-entry-hint">优秀回复用于经验沉淀，帮助系统持续优化。</p>
          <p v-if="adoption?.type === 'REJECTED'" class="ai-feedback-entry-hint">
            未采用请通过“AI 问题反馈”单独记录原因，不会进入优秀案例。
          </p>
          <p v-if="adoptionMessage" class="feedback-result" data-testid="adoption-result">
            {{ adoptionMessage }}
          </p>
        </div>
      </details>

      <section
        v-if="experienceCaseDialogOpen"
        class="experience-case-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="experience-case-dialog-title"
        data-testid="experience-case-dialog"
      >
        <header class="experience-case-dialog-header">
          <h3 id="experience-case-dialog-title">沉淀客服经验案例</h3>
          <el-button text aria-label="关闭案例表单" @click="experienceCaseDialogOpen = false">关闭</el-button>
        </header>
        <el-alert
          title="隐私提醒"
          description="仅沉淀测试案例。请确认问题和回复中没有客户姓名、电话、地址、完整订单号或隐私截图。"
          type="warning"
          :closable="false"
          show-icon
        />
        <dl class="experience-case-meta">
          <div><dt>店铺</dt><dd>{{ result.context.store_code }}</dd></div>
          <div><dt>商品</dt><dd>{{ result.context.product_id }}</dd></div>
          <div><dt>SKU</dt><dd>{{ result.context.sku_id || '未选择' }}</dd></div>
          <div><dt>本页反馈</dt><dd>{{ adoption ? adoptionLabels[adoption.type] : '未选择' }}</dd></div>
        </dl>
        <p class="experience-case-type-hint">本页反馈不会自动映射为经验类型，请按实际案例明确选择。</p>
        <label class="experience-case-field">
          <span>经验类型 <em>必选</em></span>
          <el-select
            v-model="experienceCaseFeedbackType"
            data-testid="experience-case-feedback-type"
            placeholder="请选择经验类型"
          >
            <el-option
              v-for="option in experienceCaseFeedbackOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>
        <label class="experience-case-field">
          <span>最终回复</span>
          <el-input
            v-model="experienceCaseFinalAnswer"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            data-testid="experience-case-final-answer"
          />
        </label>
        <p v-if="experienceCaseError" class="experience-case-error" data-testid="experience-case-error">
          {{ experienceCaseError }} 未保存本地成功记录，请检查中台服务后重试。
        </p>
        <p v-if="experienceCaseStatus" class="experience-case-success" data-testid="experience-case-success">
          {{ experienceCaseStatus }}
        </p>
        <footer class="experience-case-dialog-footer">
          <el-button @click="experienceCaseDialogOpen = false">取消</el-button>
          <el-button
            type="primary"
            :loading="experienceCaseSubmitting"
            :disabled="experienceCaseSubmitting"
            data-testid="experience-case-submit"
            @click="submitExperienceCase"
          >
            {{ experienceCaseSubmitting ? '正在保存' : '保存优秀案例' }}
          </el-button>
        </footer>
      </section>

      <el-dialog
        v-model="aiFeedbackDialogOpen"
        class="ai-feedback-dialog"
        title="为什么未采用？"
        width="min(600px, calc(100vw - 32px))"
        :teleported="false"
        data-testid="ai-feedback-dialog"
      >
        <el-alert
          title="仅提交去标识化测试反馈"
          description="请勿填写客户姓名、电话、地址、完整订单号、账号信息或聊天截图。"
          type="warning"
          :closable="false"
          show-icon
        />
        <label class="ai-feedback-field">
          <span>未采用原因 <em>必选</em></span>
          <el-select
            v-model="aiFeedbackType"
            data-testid="ai-feedback-type"
            placeholder="请选择原因"
          >
            <el-option
              v-for="option in notAdoptedReasonOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>
        <label v-if="aiFeedbackType === 'OTHER'" class="ai-feedback-field">
          <span>其他说明 <em>必填</em></span>
          <el-input
            v-model="aiFeedbackNote"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            data-testid="ai-feedback-note"
            placeholder="请填写去标识化、可复现的最小说明"
          />
        </label>
        <label class="ai-feedback-field">
          <span>最终人工回复 <small>可选；未发送时请留空</small></span>
          <el-input
            v-model="aiFeedbackFinalAnswer"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            data-testid="ai-feedback-final-answer"
            placeholder="只填写实际使用的去标识化人工回复"
          />
        </label>
        <p v-if="aiFeedbackError" class="ai-feedback-error" data-testid="ai-feedback-error">
          {{ aiFeedbackError }} 未生成本地成功反馈，请检查中台服务后重试。
        </p>
        <p v-if="aiFeedbackStatus" class="ai-feedback-success" data-testid="ai-feedback-success">
          {{ aiFeedbackStatus }}
        </p>
        <template #footer>
          <div class="ai-feedback-dialog-footer">
            <el-button @click="aiFeedbackDialogOpen = false">取消</el-button>
            <el-button
              type="primary"
              :loading="aiFeedbackSubmitting"
              :disabled="aiFeedbackSubmitting"
              data-testid="ai-feedback-submit"
              @click="submitAiFeedback"
            >
              {{ aiFeedbackSubmitting ? '正在提交' : '提交反馈' }}
            </el-button>
          </div>
        </template>
      </el-dialog>

    </section>

    <section v-else-if="!loading" class="empty-card">
      <div class="empty-number">3</div>
      <div>
        <h2>建议回复会显示在这里</h2>
        <p>完成前两步后点击“生成建议回复”。SKU 不确定时请留空，不要猜款式。</p>
      </div>
    </section>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ragClient } from '@/api/ragClient'
import { platformClient } from '@/api/platformClient'
import { experienceCaseClient } from '@/api/experienceCaseClient'
import { aiResponseFeedbackClient } from '@/api/aiResponseFeedbackClient'
import {
  PlatformClientError,
  toPlatformClientError,
  toRagClientError
} from '@/api/errorMapper'
import type {
  CatalogProduct,
  CatalogSku,
  CatalogStore,
  PlatformHealth
} from '@/api/platformTypes'
import type {
  AdoptionRecord,
  AdoptionType,
  RagAction,
  RagChatContext,
  RagChatResult,
  RagHealth,
  RiskLevel
} from '@/api/ragTypes'
import {
  EXPERIENCE_CASE_FEEDBACK_TYPES,
  type ExperienceCaseFeedbackType
} from '@/api/experienceCaseTypes'
import {
  NOT_ADOPTED_REASONS,
  NOT_ADOPTED_REASON_LABELS,
  type NotAdoptedReason
} from '@/workspace/adoptionFeedback'
import { recordExperienceCaseSubmission } from '@/workspace/experienceCaseSession'
import { EXPERIENCE_CASE_STATUS_LABELS } from '@/workspace/experienceCasePresentation'
import { useTesterIdentity } from '@/workspace/testerIdentity'

const LAST_STORE_KEY = 'mumu-customer-workbench:last-store'

const actionLabels: Record<RagAction, string> = {
  DIRECT_ANSWER: '🟢 可以参考',
  CONTROLLED_ANSWER: '🟡 建议确认',
  ASK_CLARIFY: '需要补充信息',
  REQUIRE_LOOKUP: '需要查询系统',
  TRANSFER_HUMAN: '🔴 建议人工处理',
  REFUSE: '不能作出该承诺'
}

const riskLabels: Record<RiskLevel, string> = {
  LOW: '低风险',
  MEDIUM: '中风险',
  HIGH: '高风险'
}

const adoptionLabels: Record<AdoptionType, string> = {
  DIRECT_ACCEPT: '直接采用',
  EDITED_ACCEPT: '修改后采用',
  REJECTED: '未采用'
}

const experienceCaseFeedbackLabels: Record<ExperienceCaseFeedbackType, string> = {
  ADOPTED: '采用 AI 建议',
  EDITED_ADOPTED: '修改后采用',
  CORRECTION: '人工纠正 AI 建议',
  ESCALATED: '需升级人工处理'
}

const experienceCaseFeedbackOptions = EXPERIENCE_CASE_FEEDBACK_TYPES.map((value) => ({
  value,
  label: experienceCaseFeedbackLabels[value]
}))

const notAdoptedReasonOptions = NOT_ADOPTED_REASONS.map((value) => ({
  value,
  label: NOT_ADOPTED_REASON_LABELS[value]
}))

const platformLabels: Record<string, string> = {
  pdd: '拼多多',
  taobao: '淘宝',
  douyin: '抖音',
  jd: '京东',
  offline: '线下',
  other: '其他'
}

const requiredFieldLabels: Record<string, string> = {
  tenant_id: '店铺归属',
  platform: '平台',
  store_code: '店铺',
  product_id: '商品',
  sku_id: '具体款式（SKU）'
}

const actionGuides: Record<RagAction, { icon: string; title: string; description: string; steps: string[]; tone: string }> = {
  DIRECT_ANSWER: {
    icon: '✓',
    title: '资料足够，可以核对后回复',
    description: 'AI 找到了当前商品范围内的明确依据。',
    steps: ['核对商品与款式', '阅读至少一条回答依据', '必要时修改措辞后人工复制'],
    tone: 'safe'
  },
  CONTROLLED_ANSWER: {
    icon: '!',
    title: '可以回复，但必须保留限制条件',
    description: '不要删掉建议中的条件、范围或不确定性说明。',
    steps: ['核对限制条件', '避免改成绝对承诺', '确认依据后人工复制'],
    tone: 'caution'
  },
  ASK_CLARIFY: {
    icon: '?',
    title: '信息不够，先向客户追问',
    description: '不要猜商品款式或缺失信息，先把下方建议作为追问发给客户。',
    steps: ['查看“还需要确认”的字段', '用客户听得懂的话追问', '拿到信息后重新生成建议'],
    tone: 'caution'
  },
  REQUIRE_LOOKUP: {
    icon: '⌕',
    title: '需要先查询订单或业务系统',
    description: '价格、库存、物流等实时信息不能只靠知识库判断。',
    steps: ['不要承诺查询结果', '在业务系统核对实时状态', '把查询结果补充后再回复'],
    tone: 'caution'
  },
  TRANSFER_HUMAN: {
    icon: '↗',
    title: '停止直接处理，请转人工专员',
    description: '这是高风险或需要授权的情况，AI 建议不能代替人工决策。',
    steps: ['不要作赔付、补发或时效承诺', '收集必要订单和问题信息', '按团队流程转给人工专员'],
    tone: 'danger'
  },
  REFUSE: {
    icon: '×',
    title: '不能按客户要求直接回答或承诺',
    description: '保持礼貌拒绝，不要绕过安全限制。',
    steps: ['保留拒绝边界', '可说明下一步可行方式', '不确定时转人工'],
    tone: 'danger'
  }
}

const fallbackGuide = {
  icon: '!',
  title: '动作未分类，请先停止发送',
  description: '服务没有返回可识别的处理动作。',
  steps: ['不要直接采用', '展开技术详情记录信息', '联系技术人员排查'],
  tone: 'danger'
}

const customerQuestion = ref('')
const selectedStoreKey = ref('')
const selectedProductId = ref('')
const selectedSkuId = ref('')
const stores = ref<CatalogStore[]>([])
const products = ref<CatalogProduct[]>([])
const skus = ref<CatalogSku[]>([])
const loading = ref(false)
const storesLoading = ref(false)
const productsLoading = ref(false)
const skusLoading = ref(false)
const ragHealthLoading = ref(false)
const platformHealthLoading = ref(false)
const ragHealth = ref<RagHealth | null>(null)
const platformHealth = ref<PlatformHealth | null>(null)
const ragHealthError = ref('')
const platformError = ref('')
const requestError = ref('')
const result = ref<RagChatResult | null>(null)
const replyDraft = ref('')
const copyStatus = ref<'idle' | 'copied'>('idle')
const adoption = ref<AdoptionRecord | null>(null)
const experienceCaseDialogOpen = ref(false)
const experienceCaseSubmitting = ref(false)
const experienceCaseError = ref('')
const experienceCaseStatus = ref('')
const experienceCaseFinalAnswer = ref('')
const experienceCaseFeedbackType = ref<ExperienceCaseFeedbackType | ''>('')
const aiFeedbackDialogOpen = ref(false)
const aiFeedbackSubmitting = ref(false)
const aiFeedbackError = ref('')
const aiFeedbackStatus = ref('')
const aiFeedbackType = ref<NotAdoptedReason | ''>('')
const aiFeedbackNote = ref('')
const aiFeedbackFinalAnswer = ref('')
const showTechnicalDetails = ref(false)
const showConnectionDetails = ref(false)
let activeRagController: AbortController | null = null
let activeCatalogController: AbortController | null = null
const { identity } = useTesterIdentity()

const runtimeDetails = {
  frontendVersion: import.meta.env.VITE_FRONTEND_VERSION ?? 'development',
  gitCommit: import.meta.env.VITE_GIT_SHORT_SHA ?? 'unavailable',
  startMode: import.meta.env.VITE_START_MODE ?? 'LOCAL',
  apiMode: import.meta.env.VITE_API_MODE ?? 'SAME_ORIGIN_PROXY',
  customerEntry: import.meta.env.VITE_CUSTOMER_ENTRY_URL ?? `${window.location.origin}/`
}

const storeKey = (store: CatalogStore) =>
  `${store.tenantId}::${store.platform}::${store.storeCode}`

const selectedStore = computed(() =>
  stores.value.find((store) => storeKey(store) === selectedStoreKey.value) ?? null
)
const selectedProduct = computed(() =>
  products.value.find((product) => product.productId === selectedProductId.value) ?? null
)
const selectedSku = computed(() =>
  skus.value.find((sku) => sku.skuId === selectedSkuId.value) ?? null
)

const canSubmit = computed(() => Boolean(customerQuestion.value.trim() && !loading.value))

const systemReady = computed(() =>
  ragHealth.value?.ready === true &&
  platformHealth.value?.status === 'ok' &&
  stores.value.length > 0 &&
  !ragHealthError.value &&
  !platformError.value
)

const workflowStep = computed(() => {
  if (result.value) return 3
  if (selectedStore.value && selectedProduct.value) return 2
  return 1
})

const platformName = (platform: string) => platformLabels[platform] ?? platform
const storeOptionLabel = (store: CatalogStore) =>
  `${platformName(store.platform)} → ${store.name}${store.testDataMode ? '（测试数据）' : ''}`
const productOptionLabel = (product: CatalogProduct) =>
  `${product.displayName}${product.publishable ? '' : '（待发布）'}`
const skuOptionLabel = (sku: CatalogSku) =>
  `${sku.displayName}${sku.publishable ? '' : '（待发布）'}`

const ragHealthStatusText = computed(() => {
  if (ragHealthLoading.value) return '正在检查'
  if (ragHealthError.value) return '不可用'
  if (ragHealth.value?.ready) return '已就绪'
  if (ragHealth.value) return '初始化中'
  return '状态未知'
})

const platformHealthStatusText = computed(() => {
  if (platformHealthLoading.value || storesLoading.value) return '正在检查'
  if (platformError.value) return '不可用'
  if (platformHealth.value?.status === 'ok' && stores.value.length) return '已就绪'
  if (platformHealth.value?.status === 'ok') return '在线，目录待发布'
  return '状态未知'
})

const ragHealthTagType = computed(() => {
  if (ragHealthError.value) return 'danger'
  if (ragHealth.value?.ready) return 'success'
  return 'warning'
})

const platformHealthTagType = computed(() => {
  if (platformError.value) return 'danger'
  if (platformHealth.value?.status === 'ok' && stores.value.length) return 'success'
  return 'warning'
})

const actionText = computed(() =>
  result.value?.action ? actionLabels[result.value.action] : '动作未分类'
)

const riskText = computed(() =>
  result.value?.riskLevel ? riskLabels[result.value.riskLevel] : '风险未分类'
)

const requiredFieldText = computed(() =>
  result.value?.requiredFields
    .map((field) => requiredFieldLabels[field] ?? '其他必要信息')
    .join('、') ?? ''
)

const actionGuide = computed(() =>
  result.value?.action ? actionGuides[result.value.action] : fallbackGuide
)

const actionTagType = computed(() =>
  result.value?.action === 'TRANSFER_HUMAN' || result.value?.action === 'REFUSE'
    ? 'danger'
    : result.value?.action === 'ASK_CLARIFY' || result.value?.action === 'REQUIRE_LOOKUP'
      ? 'warning'
      : result.value?.action === 'DIRECT_ANSWER'
        ? 'success'
        : result.value?.action
          ? 'primary'
          : 'info'
)

const riskTagType = computed(() => {
  if (result.value?.riskLevel === 'HIGH') return 'danger'
  if (result.value?.riskLevel === 'MEDIUM') return 'warning'
  if (result.value?.riskLevel === 'LOW') return 'success'
  return 'info'
})

const adoptionMessage = computed(() =>
  !adoption.value
    ? ''
    : adoption.value.type === 'REJECTED'
      ? aiFeedbackStatus.value
        ? '已在本页记录：未采用。AI 问题反馈已独立提交。'
        : '已在本页记录：未采用。可通过“AI 问题反馈”单独提交原因。'
      : `已在本页记录：${adoptionLabels[adoption.value.type]}。未发送到远端反馈服务。`
)

const clearAnswer = () => {
  result.value = null
  replyDraft.value = ''
  adoption.value = null
  aiFeedbackDialogOpen.value = false
  aiFeedbackType.value = ''
  aiFeedbackNote.value = ''
  aiFeedbackFinalAnswer.value = ''
  aiFeedbackError.value = ''
  aiFeedbackStatus.value = ''
  copyStatus.value = 'idle'
  requestError.value = ''
}

const readRememberedStore = () => {
  try {
    return window.localStorage.getItem(LAST_STORE_KEY) ?? ''
  } catch {
    return ''
  }
}

const rememberStore = (value: string) => {
  try {
    if (value) window.localStorage.setItem(LAST_STORE_KEY, value)
    else window.localStorage.removeItem(LAST_STORE_KEY)
  } catch {
    // Store memory is optional and must not block customer-service work.
  }
}

const useExample = (question: string) => {
  if (!loading.value) customerQuestion.value = question
}

const refreshRagHealth = async () => {
  ragHealthLoading.value = true
  ragHealthError.value = ''
  try {
    ragHealth.value = await ragClient.getHealth()
  } catch (error) {
    ragHealth.value = null
    ragHealthError.value = toRagClientError(error).message
  } finally {
    ragHealthLoading.value = false
  }
}

const loadStores = async () => {
  activeCatalogController?.abort()
  const controller = new AbortController()
  activeCatalogController = controller
  storesLoading.value = true
  platformError.value = ''
  let shouldRestoreStore = false
  try {
    const nextStores = await platformClient.listStores(controller.signal)
    const unsafeStore = nextStores.find((store) =>
      !store.trialEnabled ||
      !store.testDataMode ||
      store.productionUsable ||
      store.responseMode !== 'SUGGESTION_ONLY' ||
      store.allowAutoSend
    )
    if (unsafeStore) {
      throw new PlatformClientError(
        'contract',
        `店铺 ${unsafeStore.storeCode} 不符合测试数据、仅供建议、禁止自动发送的安全边界`
      )
    }
    stores.value = nextStores
    shouldRestoreStore = !selectedStoreKey.value && Boolean(readRememberedStore())
  } catch (error) {
    if (!controller.signal.aborted) {
      stores.value = []
      platformError.value = toPlatformClientError(error).message
    }
  } finally {
    if (activeCatalogController === controller) activeCatalogController = null
    storesLoading.value = false
  }

  if (shouldRestoreStore) {
    const rememberedKey = readRememberedStore()
    if (stores.value.some((store) => storeKey(store) === rememberedKey)) {
      selectedStoreKey.value = rememberedKey
      await handleStoreChange()
    } else {
      rememberStore('')
    }
  }
}

const refreshPlatform = async () => {
  platformHealthLoading.value = true
  platformError.value = ''
  try {
    platformHealth.value = await platformClient.getHealth()
  } catch (error) {
    platformHealth.value = null
    platformError.value = toPlatformClientError(error).message
  } finally {
    platformHealthLoading.value = false
  }
  await loadStores()
}

const handleStoreChange = async () => {
  activeCatalogController?.abort()
  products.value = []
  skus.value = []
  selectedProductId.value = ''
  selectedSkuId.value = ''
  clearAnswer()
  if (!selectedStore.value) {
    rememberStore('')
    return
  }

  rememberStore(selectedStoreKey.value)

  const controller = new AbortController()
  activeCatalogController = controller
  productsLoading.value = true
  platformError.value = ''
  try {
    const store = selectedStore.value
    const nextProducts = await platformClient.listProducts(store, controller.signal)
    if (nextProducts.some((product) =>
      product.platform !== store.platform || product.storeCode !== store.storeCode
    )) {
      throw new PlatformClientError('contract', '商品列表与所选店铺不一致，已停止加载')
    }
    products.value = nextProducts
  } catch (error) {
    if (!controller.signal.aborted) {
      platformError.value = toPlatformClientError(error).message
    }
  } finally {
    if (activeCatalogController === controller) activeCatalogController = null
    productsLoading.value = false
  }
}

const handleProductChange = async () => {
  activeCatalogController?.abort()
  skus.value = []
  selectedSkuId.value = ''
  clearAnswer()
  if (!selectedStore.value || !selectedProduct.value) return

  const controller = new AbortController()
  activeCatalogController = controller
  skusLoading.value = true
  platformError.value = ''
  try {
    const store = selectedStore.value
    const product = selectedProduct.value
    const nextSkus = await platformClient.listSkus(
      store,
      product,
      controller.signal
    )
    if (nextSkus.some((sku) => sku.productId !== product.productId)) {
      throw new PlatformClientError('contract', 'SKU 列表与所选商品不一致，已停止加载')
    }
    skus.value = nextSkus
  } catch (error) {
    if (!controller.signal.aborted) {
      platformError.value = toPlatformClientError(error).message
    }
  } finally {
    if (activeCatalogController === controller) activeCatalogController = null
    skusLoading.value = false
  }
}

const submitQuestion = async () => {
  if (loading.value) return

  const message = customerQuestion.value.trim()
  const store = selectedStore.value
  const product = selectedProduct.value
  if (!message) return
  if (!store || !product) {
    requestError.value = '尚未选择商品，请先完成第一步。'
    return
  }

  activeRagController?.abort()
  activeRagController = new AbortController()
  const controller = activeRagController
  loading.value = true
  requestError.value = ''
  clearAnswer()

  const expectedContext: RagChatContext = {
    tenant_id: store.tenantId,
    platform: store.platform,
    store_code: store.storeCode,
    product_id: product.productId,
    sku_id: selectedSku.value?.skuId ?? null
  }

  try {
    const response = await ragClient.chat(
      {
        question: message,
        context: expectedContext
      },
      controller.signal
    )
    const contextMatches = Object.entries(expectedContext).every(
      ([key, value]) => response.context[key as keyof RagChatContext] === value
    )
    if (!contextMatches) {
      requestError.value = '问答服务返回的店铺、商品或 SKU 与当前选择不一致，已停止展示答案'
      return
    }
    result.value = response
    replyDraft.value = response.answer
  } catch (error) {
    const clientError = toRagClientError(error)
    if (controller.signal.aborted || clientError.kind === 'canceled') {
      requestError.value = '问答请求已取消，可以重新提交'
    } else if (clientError.kind === 'timeout') {
      requestError.value = 'AI 服务请求超时，请稍后重试或按原客服流程处理。'
    } else {
      requestError.value = 'AI 服务不可用，请稍后重试或按原客服流程处理。'
    }
  } finally {
    if (activeRagController === controller) activeRagController = null
    loading.value = false
  }
}

const cancelRequest = () => {
  activeRagController?.abort()
}

const copyReply = async () => {
  const text = replyDraft.value.trim()
  if (!text) {
    ElMessage.warning('没有可复制的回复')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    copyStatus.value = 'copied'
    ElMessage.success('已复制当前回复，请核对后人工发送')
  } catch {
    copyStatus.value = 'idle'
    ElMessage.error('复制失败，请手动选择回复文本')
  }
}

const recordAdoption = (type: AdoptionType) => {
  if (!result.value) return
  const originalAnswer = result.value.answer
  const finalAnswer = type === 'REJECTED'
    ? ''
    : type === 'DIRECT_ACCEPT'
      ? originalAnswer
      : replyDraft.value.trim()

  if (type === 'EDITED_ACCEPT' && !finalAnswer) {
    ElMessage.warning('修改后的回复不能为空')
    return
  }

  adoption.value = {
    requestId: result.value.requestId,
    type,
    originalAnswer,
    finalAnswer
  }
  aiFeedbackDialogOpen.value = false
  aiFeedbackType.value = ''
  aiFeedbackNote.value = ''
  aiFeedbackFinalAnswer.value = ''
  aiFeedbackError.value = ''
  aiFeedbackStatus.value = ''
  ElMessage.success('已记录本页反馈')
}

const openExperienceCaseCapture = () => {
  if (!result.value || !adoption.value) {
    ElMessage.warning('请先选择本页反馈后再打开经验案例表单')
    return
  }
  experienceCaseError.value = ''
  experienceCaseStatus.value = ''
  experienceCaseFinalAnswer.value = adoption.value.finalAnswer
  experienceCaseFeedbackType.value = ''
  experienceCaseDialogOpen.value = true
}

const openAiFeedbackCapture = () => {
  if (!result.value || adoption.value?.type !== 'REJECTED') {
    ElMessage.warning('请先选择“未采用”后再记录 AI 问题反馈')
    return
  }
  aiFeedbackError.value = ''
  aiFeedbackStatus.value = ''
  aiFeedbackType.value = ''
  aiFeedbackNote.value = ''
  aiFeedbackFinalAnswer.value = ''
  aiFeedbackDialogOpen.value = true
}

const submitAiFeedback = async () => {
  if (!result.value || adoption.value?.type !== 'REJECTED' || aiFeedbackSubmitting.value) return

  const question = customerQuestion.value.trim()
  const aiAnswer = result.value.answer.trim()
  if (!question || !aiAnswer) {
    aiFeedbackError.value = '缺少当前问题或 AI 回复，无法提交反馈。'
    return
  }
  if (!aiFeedbackType.value) {
    aiFeedbackError.value = '请选择未采用原因后再提交。'
    return
  }
  if (aiFeedbackType.value === 'OTHER' && !aiFeedbackNote.value.trim()) {
    aiFeedbackError.value = '选择“其他”时请填写去标识化说明。'
    return
  }

  aiFeedbackSubmitting.value = true
  aiFeedbackError.value = ''
  aiFeedbackStatus.value = ''
  try {
    await aiResponseFeedbackClient.submit({
      storeCode: result.value.context.store_code,
      productId: result.value.context.product_id,
      skuId: result.value.context.sku_id,
      question,
      aiAnswer,
      feedbackType: aiFeedbackType.value,
      feedbackNote: aiFeedbackType.value === 'OTHER' ? aiFeedbackNote.value.trim() : null,
      finalAnswer: aiFeedbackFinalAnswer.value.trim() || null,
      createdBy: identity.value.reporterId
    })
    aiFeedbackStatus.value = '反馈已记录。'
  } catch (error) {
    aiFeedbackError.value = error instanceof Error ? error.message : 'AI 问题反馈服务当前不可用。'
  } finally {
    aiFeedbackSubmitting.value = false
  }
}

const submitExperienceCase = async () => {
  if (!result.value || !adoption.value || experienceCaseSubmitting.value) return

  const question = customerQuestion.value.trim()
  const aiAnswer = result.value.answer.trim()
  if (!question || !aiAnswer) {
    experienceCaseError.value = '缺少当前问题或 AI 回复，无法沉淀案例。'
    return
  }
  if (!experienceCaseFeedbackType.value) {
    experienceCaseError.value = '请选择经验类型后再提交。'
    return
  }

  experienceCaseSubmitting.value = true
  experienceCaseError.value = ''
  experienceCaseStatus.value = ''
  try {
    const receipt = await experienceCaseClient.submit({
      storeCode: result.value.context.store_code,
      productId: result.value.context.product_id,
      skuId: result.value.context.sku_id,
      question,
      aiAnswer,
      finalAnswer: experienceCaseFinalAnswer.value.trim(),
      feedbackType: experienceCaseFeedbackType.value,
      createdBy: identity.value.reporterId
    })
    recordExperienceCaseSubmission({
      storeCode: result.value.context.store_code,
      productId: result.value.context.product_id,
      skuId: result.value.context.sku_id,
      caseId: receipt.caseId,
      feedbackType: experienceCaseFeedbackType.value,
      createdBy: identity.value.reporterId,
      reviewStatus: receipt.reviewStatus,
      submittedAt: new Date().toLocaleString('zh-CN', { hour12: false })
    })
    experienceCaseStatus.value = `案例已提交，当前状态：${EXPERIENCE_CASE_STATUS_LABELS[receipt.reviewStatus]}。`
  } catch (error) {
    experienceCaseError.value = error instanceof Error ? error.message : '案例服务当前不可用。'
  } finally {
    experienceCaseSubmitting.value = false
  }
}

onMounted(() => {
  void refreshRagHealth()
  void refreshPlatform()
})

onBeforeUnmount(() => {
  activeRagController?.abort()
  activeCatalogController?.abort()
})
</script>

<style scoped>
.workspace-shell {
  width: min(1120px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 64px;
  color: #172033;
}

.workspace-header,
.section-heading,
.question-actions,
.copy-row,
.evidence-heading,
.selection-confirmed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.workspace-header { margin-bottom: 22px; }

.eyebrow,
.section-label {
  margin: 0 0 6px;
  color: #3157c8;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

h1, h2, p { margin-top: 0; }
h1 { margin-bottom: 8px; font-size: clamp(28px, 4vw, 42px); }
h2 { margin-bottom: 7px; font-size: 21px; }
.subtitle, .section-heading p, .system-summary p, .input-hint, .copy-row span,
.feedback-section p, .empty-card p, .loading-card p, .evidence-heading p {
  color: #697386;
}
.subtitle, .section-heading p, .system-summary p, .feedback-section p,
.empty-card p, .loading-card p, .evidence-heading p { margin-bottom: 0; }

.system-summary {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 300px;
  padding: 13px 15px;
  border: 1px solid #dce3f0;
  border-radius: 14px;
  background: #fff;
}
.system-summary p { margin-top: 3px; font-size: 12px; }
.status-dot { width: 12px; height: 12px; border-radius: 50%; background: #f59e0b; }
.status-dot.ready { background: #22a06b; box-shadow: 0 0 0 5px rgb(34 160 107 / 12%); }

.safety-alert { border: 2px solid #d93025; }
.connection-card {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
  padding: 14px 18px;
  border: 1px dashed #b8c5da;
  border-radius: 12px;
  background: #f8fafc;
}
.connection-card > div { display: flex; align-items: center; gap: 10px; }

.workflow-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 24px auto 0;
}
.workflow-progress div { display: flex; align-items: center; gap: 8px; color: #8a94a6; }
.workflow-progress div > span {
  display: grid; place-items: center; width: 28px; height: 28px;
  border: 2px solid #cbd5e1; border-radius: 50%; font-weight: 800;
}
.workflow-progress div.active, .workflow-progress div.done { color: #3157c8; }
.workflow-progress div.active > span, .workflow-progress div.done > span {
  border-color: #3157c8; background: #3157c8; color: white;
}
.workflow-progress i { width: 70px; height: 2px; background: #dce3f0; }

.step-card, .empty-card, .loading-card {
  margin-top: 18px;
  border: 1px solid #dce3f0;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 12px 34px rgb(43 62 101 / 8%);
}
.step-card { padding: 26px; }
.status-alert { margin-top: 16px; }
.context-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 22px;
}
.context-grid label { display: grid; gap: 9px; }
.context-grid label > span { font-weight: 800; }
.context-grid label b {
  display: inline-grid; place-items: center; width: 23px; height: 23px;
  margin-right: 4px; border-radius: 50%; background: #e9efff; color: #3157c8;
}
.context-grid label em {
  margin-left: 5px; color: #c2413b; font-size: 11px; font-style: normal;
}
.context-grid label em.optional { color: #697386; }
.context-grid label small { color: #7b8496; }
.context-grid .el-select { width: 100%; }

.selection-confirmed {
  justify-content: flex-start;
  margin-top: 20px;
  padding: 15px;
  border-radius: 12px;
  background: #ecf8f2;
  color: #19633f;
}
.selection-confirmed p { margin: 3px 0 0; color: #356d53; }
.selection-confirmed .el-button { margin-left: auto; }
.check-mark {
  display: grid; place-items: center; width: 32px; height: 32px;
  border-radius: 50%; background: #22a06b; color: #fff; font-weight: 900;
}

.technical-box {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  padding: 13px;
  border-radius: 10px;
  background: #172033;
  color: #e6edf7;
}
.technical-box code { font-size: 12px; }
.runtime-details {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 6px 12px;
  width: 100%;
  padding-top: 10px;
  border-top: 1px solid #dce5f1;
  color: #52667f;
  font-size: 12px;
}
.runtime-details code { overflow-wrap: anywhere; color: #172033; }

.question-label, .reply-label { display: block; margin: 20px 0 8px; font-weight: 800; }
.reply-label span { margin-left: 8px; color: #3157c8; font-size: 13px; }
.example-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; color: #697386; font-size: 13px; }
.example-row button {
  padding: 5px 10px; border: 1px solid #cbd7ef; border-radius: 999px;
  background: #f6f8ff; color: #3157c8; cursor: pointer;
}
.question-actions, .copy-row { margin-top: 16px; }

.loading-card, .empty-card { display: flex; align-items: center; gap: 16px; padding: 28px; }
.loading-dot {
  width: 14px; height: 14px; border-radius: 50%; background: #3157c8;
  box-shadow: 0 0 0 8px rgb(49 87 200 / 12%); animation: pulse 1.2s infinite ease-in-out;
}
.empty-number {
  display: grid; place-items: center; flex: 0 0 auto; width: 44px; height: 44px;
  border-radius: 50%; background: #eef2f7; color: #94a3b8; font-size: 20px; font-weight: 900;
}

.answer-heading { align-items: flex-start; }
.result-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.action-guide {
  display: flex; gap: 16px; margin-top: 18px; padding: 18px;
  border: 1px solid; border-radius: 14px;
}
.action-guide.safe { border-color: #a7dac2; background: #effaf4; color: #165c3a; }
.action-guide.caution { border-color: #f0ce83; background: #fff8e8; color: #7a5200; }
.action-guide.danger { border-color: #efaaa6; background: #fff1f0; color: #8f2d28; }
.guide-icon {
  display: grid; place-items: center; flex: 0 0 auto; width: 36px; height: 36px;
  border: 2px solid currentColor; border-radius: 50%; font-size: 20px; font-weight: 900;
}
.action-guide p { margin: 5px 0 8px; }
.action-guide ul { margin: 0; padding-left: 20px; line-height: 1.75; }
.result-alert, .reply-editor { margin-top: 15px; }
.copy-row { justify-content: flex-end; }

.evidence-section, .feedback-section {
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid #e7ebf2;
}
.evidence-heading span { color: #697386; font-size: 13px; }
.evidence-list { display: grid; gap: 12px; margin-top: 14px; }
.evidence-item { padding: 16px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
.evidence-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.evidence-title span { color: #697386; font-size: 12px; }
.evidence-item > p { margin: 10px 0 0; color: #475569; line-height: 1.7; white-space: pre-wrap; }
.evidence-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; color: #697386; font-size: 12px; }
.technical-toggle-row { margin-top: 16px; text-align: right; }

.feedback-actions { display: flex; flex-wrap: wrap; margin: 16px 12px 14px 0; }
.feedback-section > .el-button { vertical-align: top; margin-top: 16px; }
.feedback-result { margin-top: 12px; color: #246b3f !important; font-weight: 700; }
.experience-case-entry-hint { margin-top: -2px !important; color: #47705d !important; }
.ai-feedback-entry-hint { margin-top: 8px !important; color: #315fbd !important; }
.customer-friendly-notice {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 9px 14px;
  padding: 10px 14px;
  border: 1px solid #c8d9f3;
  border-radius: 12px;
  background: #f4f8ff;
  color: #294d84;
  font-size: 12px;
}
.customer-friendly-notice ul { display: flex; flex-wrap: wrap; gap: 5px 14px; margin: 0; padding-left: 18px; }

@keyframes pulse {
  0%, 100% { opacity: 0.45; transform: scale(0.88); }
  50% { opacity: 1; transform: scale(1); }
}

@media (max-width: 820px) {
  .context-grid { grid-template-columns: 1fr; }
  .workflow-progress i { width: 28px; }
}

@media (max-width: 700px) {
  .workspace-shell { width: min(100% - 20px, 1120px); padding-top: 18px; }
  .workspace-header, .section-heading, .question-actions, .copy-row, .evidence-heading {
    align-items: flex-start; flex-direction: column;
  }
  .system-summary, .question-actions .el-button, .copy-row .el-button { width: 100%; }
  .connection-card { grid-template-columns: 1fr; }
  .workflow-progress strong { display: none; }
}

/* Desktop workbench refresh: keep the full three-step flow in one calm workspace. */
.workspace-shell {
  --ink: #14213d;
  --muted: #69758a;
  --line: #dbe5f2;
  --panel: #ffffff;
  --canvas: #f3f7fc;
  --primary: #245bda;
  --primary-soft: #eaf0ff;
  --success: #0f9d7a;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 0;
  color: var(--ink);
}

:global(body) {
  background:
    radial-gradient(circle at 10% 0%, rgb(128 183 255 / 19%), transparent 28rem),
    radial-gradient(circle at 100% 100%, rgb(47 174 146 / 12%), transparent 30rem),
    var(--canvas);
}

.workspace-header {
  margin-bottom: 0;
  padding: 18px 22px;
  border: 1px solid rgb(202 218 240 / 85%);
  border-radius: 20px;
  background: rgb(255 255 255 / 88%);
  box-shadow: 0 12px 32px rgb(24 58 118 / 8%);
}

.eyebrow,
.section-label {
  margin-bottom: 4px;
  color: var(--primary);
  font-size: 11px;
  letter-spacing: 0.12em;
}

h1 {
  margin-bottom: 4px;
  font-size: clamp(27px, 3vw, 38px);
  letter-spacing: -0.035em;
  line-height: 1.08;
}

h2 {
  margin-bottom: 4px;
  font-size: 18px;
  letter-spacing: -0.02em;
}

.subtitle,
.section-heading p,
.system-summary p,
.input-hint,
.copy-row span,
.feedback-section p,
.empty-card p,
.loading-card p,
.evidence-heading p {
  color: var(--muted);
}

.subtitle,
.section-heading p {
  font-size: 13px;
  line-height: 1.45;
}

.system-summary {
  min-width: 278px;
  padding: 10px 12px;
  border-color: #cfe0f7;
  border-radius: 14px;
  background: linear-gradient(135deg, #f9fcff, #edf7ff);
}

.system-summary p { font-size: 12px; }
.system-summary .el-button { padding-inline: 2px; color: #486177; }
.status-dot.ready { background: var(--success); box-shadow: 0 0 0 5px rgb(15 157 122 / 12%); }

.safety-alert {
  margin: 0;
  border: 1px solid #f3b9bd;
  border-radius: 12px;
  background: #fff7f7;
}

.safety-alert :deep(.el-alert__content) { min-width: 0; }
.safety-alert :deep(.el-alert__title) { font-size: 13px; font-weight: 800; }
.safety-alert :deep(.el-alert__description) { margin-top: 1px; font-size: 12px; line-height: 1.35; }

.connection-card,
.status-alert {
  margin-top: 0;
}

.connection-card {
  border-color: #cbd9ee;
  border-radius: 14px;
  background: rgb(255 255 255 / 88%);
}

.workflow-progress {
  justify-content: flex-start;
  gap: 10px;
  margin: 0;
  padding: 0 4px;
}

.workflow-progress div { font-size: 13px; }
.workflow-progress div > span { width: 24px; height: 24px; font-size: 12px; }
.workflow-progress i { width: min(7vw, 72px); }

.workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.96fr) minmax(0, 1.04fr);
  gap: 14px;
  min-width: 0;
}

.composer-pane,
.review-pane {
  min-width: 0;
  min-height: 0;
}

.composer-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.review-pane {
  display: flex;
}

.step-card,
.empty-card,
.loading-card {
  margin-top: 0;
  border-color: var(--line);
  border-radius: 18px;
  background: var(--panel);
  box-shadow: 0 10px 26px rgb(27 67 129 / 7%);
}

.step-card { padding: 18px; }
.context-card { flex: 0 0 auto; }
.question-card { flex: 1 1 auto; min-height: 0; }

.context-grid {
  gap: 10px;
  margin-top: 14px;
}

.context-grid label { gap: 6px; min-width: 0; }
.context-grid label > span { font-size: 13px; white-space: nowrap; }
.context-grid label b { width: 20px; height: 20px; font-size: 12px; }
.context-grid label small { min-height: 28px; font-size: 11px; line-height: 1.3; }
.context-grid :deep(.el-select__wrapper) { min-height: 34px; }

.selection-confirmed {
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid #c7eddf;
  border-radius: 12px;
  background: #effbf7;
}

.selection-confirmed strong { font-size: 13px; }
.selection-confirmed p { font-size: 12px; }
.check-mark { width: 26px; height: 26px; font-size: 13px; }

.technical-box {
  margin-top: 10px;
  padding: 10px;
  border-radius: 10px;
}

.question-label,
.reply-label { margin: 14px 0 6px; font-size: 13px; }

.question-card :deep(.el-textarea__inner) {
  min-height: 114px !important;
  padding: 10px 12px;
  line-height: 1.55;
  resize: none;
}

.example-row { gap: 6px; margin-top: 9px; font-size: 12px; }
.example-row button { padding: 4px 8px; font-size: 12px; }
.question-actions,
.copy-row { margin-top: 10px; }
.input-hint { font-size: 12px; }

.loading-card,
.empty-card {
  width: 100%;
  padding: 22px;
}

.empty-card {
  align-items: center;
  border-style: dashed;
  background:
    linear-gradient(135deg, rgb(234 240 255 / 82%), rgb(255 255 255 / 95%));
}

.empty-card h2 { margin-bottom: 5px; }
.empty-number { background: var(--primary-soft); color: var(--primary); }

.review-pane > .step-card,
.review-pane > .empty-card {
  width: 100%;
  min-width: 0;
}

.answer-card {
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: #c6d4e7 transparent;
}

.answer-heading { align-items: flex-start; }
.result-tags { gap: 6px; margin-top: 6px; }
.result-tags :deep(.el-tag) { font-size: 11px; }

.action-guide {
  gap: 12px;
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
}

.guide-icon { width: 30px; height: 30px; font-size: 16px; }
.action-guide p { margin: 4px 0 5px; font-size: 13px; }
.action-guide ul { padding-left: 17px; font-size: 12px; line-height: 1.5; }

.result-alert,
.reply-editor { margin-top: 10px; }
.result-alert :deep(.el-alert__title) { font-size: 12px; }

.reply-editor :deep(.el-textarea__inner) {
  min-height: 138px !important;
  line-height: 1.55;
  resize: vertical;
}

.copy-row { align-items: center; }
.copy-row .el-button,
.question-actions .el-button { min-height: 34px; }

.evidence-section,
.feedback-section {
  margin-top: 16px;
  padding-top: 14px;
}

.evidence-section summary {
  cursor: pointer;
  color: #365174;
  font-size: 13px;
  font-weight: 800;
}

.evidence-list { gap: 8px; margin-top: 10px; }
.evidence-item { padding: 10px; }
.evidence-item > p { margin-top: 6px; font-size: 13px; line-height: 1.5; }
.technical-toggle-row { margin-top: 10px; }
.feedback-actions { margin: 9px 0; }
.feedback-section > .el-button { margin-top: 8px; }

@media (min-width: 901px) {
  .workspace-shell {
    display: grid;
    grid-template-rows: auto auto auto minmax(0, 1fr);
    gap: 10px;
    height: auto;
    min-height: 650px;
    overflow: visible;
  }

  .workspace-header,
  .safety-alert,
  .connection-card,
  .status-alert,
  .workflow-progress,
  .workbench-grid {
    min-width: 0;
  }

  .workbench-grid {
    min-height: 500px;
    overflow: visible;
  }

  .composer-pane {
    overflow: visible;
    scrollbar-width: thin;
    scrollbar-color: #c6d4e7 transparent;
  }

  .review-pane,
  .review-pane > .answer-card,
  .review-pane > .empty-card {
    min-height: 500px;
    height: auto;
  }

  .empty-card { justify-content: center; }
}

@media (max-width: 1040px) {
  .workspace-shell { width: min(100% - 28px, 1440px); }
  .context-grid { grid-template-columns: 1fr; }
  .context-grid label small { min-height: auto; }
}

@media (max-width: 900px) {
  .workspace-shell { padding-bottom: 32px; }
  .workbench-grid { grid-template-columns: 1fr; }
  .review-pane { min-height: 300px; }
  .answer-card { overflow: visible; }
}

@media (min-width: 901px) and (max-height: 740px) {
  .workspace-shell {
    height: auto;
    min-height: 650px;
    overflow: visible;
  }

  .workbench-grid { min-height: auto; overflow: visible; }
  .composer-pane { overflow: visible; }
  .review-pane,
  .review-pane > .answer-card,
  .review-pane > .empty-card { height: auto; min-height: 300px; }
}

@media (max-width: 700px) {
  .workspace-shell { width: min(100% - 20px, 1440px); }
  .workspace-header { padding: 16px; }
  .context-grid { grid-template-columns: 1fr; }
  .system-summary { min-width: 0; }
  .workflow-progress { justify-content: center; }
  .workflow-progress i { width: 28px; }
}

/* Keep the review controls visible before optional evidence and feedback. */
.answer-card { padding: 14px; }
.answer-card .section-label { margin-bottom: 2px; }
.answer-card h2 { font-size: 17px; }

.action-guide {
  gap: 9px;
  margin-top: 9px;
  padding: 9px 10px;
}

.action-guide ul {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 0;
  list-style: none;
}

.action-guide li {
  padding: 2px 6px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.35;
}

.result-alert,
.reply-editor { margin-top: 7px; }
.result-alert :deep(.el-alert) { padding: 6px 8px; }
.result-alert :deep(.el-alert__title) { font-size: 11px; line-height: 1.35; }

.reply-label { margin: 9px 0 4px; }
.reply-editor :deep(.el-textarea__inner) {
  min-height: 118px !important;
  height: 118px !important;
}

.copy-row { margin-top: 7px; }
.copy-row span { font-size: 12px; }

.evidence-section { margin-top: 10px; padding-top: 10px; }
.feedback-section { margin-top: 10px; padding-top: 10px; }
.feedback-section summary {
  cursor: pointer;
  color: #365174;
  font-size: 12px;
  font-weight: 800;
}
.feedback-body { padding-top: 8px; }
.feedback-section p { margin-bottom: 0; font-size: 12px; }
.feedback-actions { margin: 6px 0; }

.experience-case-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 18px; margin: 18px 0; }
.experience-case-dialog { margin-top: 16px; padding: 20px; border: 1px solid #b9c7d8; border-radius: 12px; background: #fff; box-shadow: 0 8px 24px rgb(33 55 85 / 12%); }
.experience-case-dialog-header, .experience-case-dialog-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.experience-case-dialog-header h3 { margin: 0; font-size: 18px; }
.experience-case-dialog-footer { justify-content: flex-end; margin-top: 18px; }
.experience-case-meta dt { color: #7a8799; font-size: 12px; }
.experience-case-meta dd { margin: 4px 0 0; overflow-wrap: anywhere; font-size: 13px; font-weight: 700; }
.experience-case-field { display: grid; gap: 7px; font-size: 13px; font-weight: 700; }
.experience-case-error { margin-top: 14px; color: #b83b32 !important; }
.experience-case-success { margin-top: 14px; color: #1c6a49 !important; font-weight: 700; }
.ai-feedback-dialog { margin-top: 16px; padding: 20px; border: 1px solid #f0c57c; border-radius: 12px; background: #fffdf8; box-shadow: 0 8px 24px rgb(90 62 23 / 12%); }
.ai-feedback-dialog-header, .ai-feedback-dialog-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ai-feedback-dialog-header h3 { margin: 0; font-size: 18px; }
.ai-feedback-dialog-footer { justify-content: flex-end; margin-top: 18px; }
.ai-feedback-field { display: grid; gap: 7px; margin-top: 16px; font-size: 13px; font-weight: 700; }
.ai-feedback-field em { color: #c33d35; font-style: normal; }
.ai-feedback-field small { color: #748198; font-weight: 400; }
.ai-feedback-error { margin-top: 14px; color: #b83b32 !important; }
.ai-feedback-success { margin-top: 14px; color: #1c6a49 !important; font-weight: 700; }
</style>
