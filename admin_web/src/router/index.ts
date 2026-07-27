import { createRouter, createWebHistory } from 'vue-router'

import SystemStatusView from '../views/SystemStatusView.vue'
import ImportBatchDetailView from '../views/ImportBatchDetailView.vue'
import ImportBatchListView from '../views/ImportBatchListView.vue'
import NewImportView from '../views/NewImportView.vue'
import TestDataPackagesView from '../views/TestDataPackagesView.vue'
import AiCapabilityCenterView from '../views/AiCapabilityCenterView.vue'
import CustomerSuggestionsView from '../views/CustomerSuggestionsView.vue'
import CustomerExperienceCasesView from '../views/CustomerExperienceCasesView.vue'
import AiOptimizationPoolView from '../views/AiOptimizationPoolView.vue'
import AiFeedbackOptimizationPoolView from '../views/AiFeedbackOptimizationPoolView.vue'
import CustomerEfficiencyDashboardView from '../views/CustomerEfficiencyDashboardView.vue'
import PilotStoreCenterView from '../views/PilotStoreCenterView.vue'
import OperationsOverviewView from '../views/OperationsOverviewView.vue'
import ProductDetailView from '../views/ProductDetailView.vue'
import ReadonlyListView from '../views/ReadonlyListView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', name: 'overview', component: OperationsOverviewView },
    { path: '/ai-capabilities', name: 'ai-capabilities', component: AiCapabilityCenterView },
    { path: '/store-center', name: 'store-center', component: PilotStoreCenterView },
    {
      path: '/stores', name: 'stores', component: ReadonlyListView,
      props: { resource: 'stores', title: '店铺', description: '查看平台、店铺编码、试运行标记与商品数量。', columns: [
        { key: 'platform', label: '平台' }, { key: 'store_code', label: '店铺编码' },
        { key: 'store_name', label: '店铺' }, { key: 'test_data_mode', label: '测试数据' }, { key: 'product_count', label: '商品数' },
      ] },
    },
    {
      path: '/products', name: 'products', component: ReadonlyListView,
      props: { resource: 'products', title: '商品与 SKU', description: '查询商品，并打开只读 SKU 明细。', columns: [
        { key: 'product_id', label: '商品 ID' }, { key: 'product_name_display', label: '商品' },
        { key: 'store_code', label: '店铺' }, { key: 'sales_status', label: '销售状态' }, { key: 'review_status', label: '审核状态' },
      ] },
    },
    { path: '/products/:productId', name: 'product-detail', component: ProductDetailView, props: true },
    {
      path: '/faqs', name: 'faqs', component: ReadonlyListView,
      props: { resource: 'faqs', title: 'FAQ', description: '查看问题、回答动作、风险、适用范围与来源。', columns: [
        { key: 'question', label: '问题' }, { key: 'answer_action', label: '回答动作' },
        { key: 'risk_level', label: '风险' }, { key: 'product_id', label: '商品' }, { key: 'source_ids', label: '来源' },
      ] },
    },
    {
      path: '/safety-rules', name: 'safety-rules', component: ReadonlyListView,
      props: { resource: 'safety-rules', title: '安全规则', description: '查看场景、风险、允许动作、禁止表述与来源。', columns: [
        { key: 'scenario', label: '场景' }, { key: 'risk_level', label: '风险' },
        { key: 'action', label: '允许动作' }, { key: 'forbidden_claim', label: '禁止表述' }, { key: 'source_ids', label: '来源' },
      ] },
    },
    {
      path: '/sources', name: 'sources', component: ReadonlyListView,
      props: { resource: 'sources', title: '知识来源', description: '仅展示元数据和安全相对定位，不提供预览或下载。', columns: [
        { key: 'source_type', label: '类型' }, { key: 'file_name', label: '文件' },
        { key: 'file_sha256', label: '校验值' }, { key: 'product_id', label: '商品' }, { key: 'sku_id', label: 'SKU' },
      ] },
    },
    {
      path: '/conflicts', name: 'conflicts', component: ReadonlyListView,
      props: { resource: 'conflicts', title: '数据冲突', description: '查看字段值 A/B、来源与当前处理状态。', columns: [
        { key: 'entity_id', label: '实体' }, { key: 'field_name', label: '字段' },
        { key: 'value_a', label: '值 A' }, { key: 'value_b', label: '值 B' }, { key: 'status', label: '状态' },
      ] },
    },
    { path: '/suggestions', name: 'suggestions', component: CustomerSuggestionsView },
    { path: '/experience-cases', name: 'experience-cases', component: CustomerExperienceCasesView },
    { path: '/ai-optimization-pool', name: 'ai-optimization-pool', component: AiOptimizationPoolView },
    { path: '/ai-feedback-optimization-pool', name: 'ai-feedback-optimization-pool', component: AiFeedbackOptimizationPoolView },
    { path: '/customer-efficiency', name: 'customer-efficiency', component: CustomerEfficiencyDashboardView },
    {
      path: '/system-status',
      name: 'system-status',
      component: SystemStatusView,
    },
    {
      path: '/imports',
      name: 'import-batches',
      component: ImportBatchListView,
    },
    {
      path: '/imports/new',
      name: 'new-import',
      component: NewImportView,
    },
    {
      path: '/imports/:batchId',
      name: 'import-batch-detail',
      component: ImportBatchDetailView,
      props: true,
    },
    {
      path: '/test-data-packages',
      name: 'test-data-packages',
      component: TestDataPackagesView,
    },
  ],
})
