import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import SystemStatusView from '../views/SystemStatusView.vue'
import AiCapabilityCenterView from '../views/AiCapabilityCenterView.vue'
import CustomerSuggestionsView from '../views/CustomerSuggestionsView.vue'
import CustomerExperienceCasesView from '../views/CustomerExperienceCasesView.vue'
import AiOptimizationPoolView from '../views/AiOptimizationPoolView.vue'
import AiFeedbackOptimizationPoolView from '../views/AiFeedbackOptimizationPoolView.vue'
import OperationsOverviewView from '../views/OperationsOverviewView.vue'
import ProductDetailView from '../views/ProductDetailView.vue'
import ReadonlyListView from '../views/ReadonlyListView.vue'
import KnowledgeMaterialsView from '../views/KnowledgeMaterialsView.vue'
import KnowledgeQualityPoolView from '../views/KnowledgeQualityPoolView.vue'
import KnowledgeCenterView from '../views/KnowledgeCenterView.vue'
import ImportCenterView from '../views/ImportCenterView.vue'
import CustomerOperationsView from '../views/CustomerOperationsView.vue'
import KnowledgeEditorView from '../views/KnowledgeEditorView.vue'
import KnowledgeReviewView from '../views/KnowledgeReviewView.vue'
import KnowledgeGapCenterView from '../views/KnowledgeGapCenterView.vue'
import StoreManagementView from '../views/StoreManagementView.vue'
import AiIssueCenterView from '../views/AiIssueCenterView.vue'
import LoginView from '../views/LoginView.vue'
import ForbiddenView from '../views/ForbiddenView.vue'
import UserManagementView from '../views/UserManagementView.vue'
import ChangePasswordView from '../views/ChangePasswordView.vue'
import { useAdminSession } from '../auth/session'

const testToolsEnabled = import.meta.env.VITE_ENABLE_TEST_TOOLS === 'true'
const testToolRoutes: RouteRecordRaw[] = testToolsEnabled
  ? [
      {
        path: '/imports',
        name: 'import-batches',
        component: () => import('../views/ImportBatchListView.vue'),
      },
      {
        path: '/imports/new',
        name: 'new-import',
        component: () => import('../views/NewImportView.vue'),
      },
      {
        path: '/imports/:batchId',
        name: 'import-batch-detail',
        component: () => import('../views/ImportBatchDetailView.vue'),
        props: true,
      },
      {
        path: '/test-data-packages',
        name: 'test-data-packages',
        component: () => import('../views/TestDataPackagesView.vue'),
      },
    ]
  : []

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/forbidden', name: 'forbidden', component: ForbiddenView, meta: { public: true } },
    { path: '/change-password', name: 'change-password', component: ChangePasswordView, meta: { authFlow: true } },
    { path: '/', redirect: '/overview' },
    { path: '/overview', name: 'overview', component: OperationsOverviewView },
    { path: '/knowledge-center', name: 'knowledge-center', component: KnowledgeCenterView },
    { path: '/knowledge-editor', name: 'knowledge-editor', component: KnowledgeEditorView },
    { path: '/knowledge-review', name: 'knowledge-review', component: KnowledgeReviewView },
    { path: '/knowledge-gaps', name: 'knowledge-gaps', component: KnowledgeGapCenterView },
    { path: '/import-center', name: 'import-center', component: ImportCenterView },
    { path: '/store-management', name: 'store-management', component: StoreManagementView },
    { path: '/customer-operations', name: 'customer-operations', component: CustomerOperationsView },
    { path: '/ai-capabilities', name: 'ai-capabilities', component: AiCapabilityCenterView },
    {
      path: '/stores', name: 'stores', component: ReadonlyListView,
      props: { resource: 'stores', title: '店铺', description: '查看店铺业务名称、平台与已导入商品数量。', columns: [
        { key: 'platform', label: '平台' },
        { key: 'store_name', label: '店铺名称' }, { key: 'product_count', label: '商品数' },
      ] },
    },
    {
      path: '/products', name: 'products', component: ReadonlyListView,
      props: { resource: 'products', title: '商品与 SKU', description: '按商品业务名称查询已导入资料，并打开 SKU 明细核对事实。', columns: [
        { key: 'product_name_display', label: '商品名称' },
        { key: 'sales_status', label: '销售状态' }, { key: 'review_status', label: '审核状态' },
      ] },
    },
    { path: '/products/:productId', name: 'product-detail', component: ProductDetailView, props: true },
    { path: '/knowledge-center/products/:productId', name: 'product-knowledge-detail', component: ProductDetailView, props: true },
    {
      path: '/faqs', name: 'faqs', component: ReadonlyListView,
      props: { resource: 'faqs', title: '常见问题', description: '查看已导入问题、回答动作、风险、适用范围与来源。', columns: [
        { key: 'question', label: '问题' }, { key: 'answer_action', label: '回答动作' },
        { key: 'risk_level', label: '风险' },
      ] },
    },
    {
      path: '/safety-rules', name: 'safety-rules', component: ReadonlyListView,
      props: { resource: 'safety-rules', title: '安全规则', description: '查看风险场景、允许动作、禁止表述与来源。', columns: [
        { key: 'scenario', label: '场景' }, { key: 'risk_level', label: '风险' },
        { key: 'action', label: '允许动作' }, { key: 'forbidden_claim', label: '禁止表述' },
      ] },
    },
    {
      path: '/sources', name: 'sources', component: ReadonlyListView,
      props: { resource: 'sources', title: '知识来源', description: '仅展示来源类型和业务文件名称，不提供原文预览、下载或发布。', columns: [
        { key: 'source_type', label: '类型' }, { key: 'file_name', label: '文件' },
      ] },
    },
    {
      path: '/conflicts', name: 'conflicts', component: ReadonlyListView,
      props: { resource: 'conflicts', title: '数据冲突', description: '查看不同来源的字段值与当前处理状态；本页不自动确认。', columns: [
        { key: 'entity_id', label: '实体' }, { key: 'field_name', label: '字段' },
        { key: 'value_a', label: '值 A' }, { key: 'value_b', label: '值 B' }, { key: 'status', label: '状态' },
      ] },
    },
    { path: '/suggestions', name: 'suggestions', component: CustomerSuggestionsView },
    { path: '/experience-cases', name: 'experience-cases', component: CustomerExperienceCasesView },
    { path: '/ai-optimization-pool', name: 'ai-optimization-pool', component: AiOptimizationPoolView },
    { path: '/ai-feedback-optimization-pool', name: 'ai-feedback-optimization-pool', component: AiFeedbackOptimizationPoolView },
    { path: '/ai-issues', name: 'ai-issues', component: AiIssueCenterView },
    { path: '/knowledge-materials', name: 'knowledge-materials', component: KnowledgeMaterialsView },
    { path: '/knowledge-quality-pool', name: 'knowledge-quality-pool', component: KnowledgeQualityPoolView },
    {
      path: '/system-status',
      name: 'system-status',
      component: SystemStatusView,
    },
    { path: '/user-management', name: 'user-management', component: UserManagementView, meta: { requiredPermission: 'user.manage' } },
    ...testToolRoutes,
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public === true) return true
  const auth = useAdminSession()
  if (!await auth.restore()) return { path: '/login', query: { redirect: to.fullPath } }
  if (auth.user.value?.must_change_password === true && to.path !== '/change-password') return '/change-password'
  if (to.path === '/change-password') return true
  const permission = typeof to.meta.requiredPermission === 'string' ? to.meta.requiredPermission : null
  if (permission && !auth.hasPermission(permission)) return '/forbidden'
  if (!permission && !auth.hasAnyPermission(['product.manage', 'knowledge.manage', 'feedback.view', 'user.manage'])) return '/forbidden'
  return true
})
