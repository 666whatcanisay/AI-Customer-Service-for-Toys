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
import OperationsOverviewView from '../views/OperationsOverviewView.vue'
import ProductDetailView from '../views/ProductDetailView.vue'
import ReadonlyListView from '../views/ReadonlyListView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', name: 'overview', component: OperationsOverviewView },
    { path: '/ai-capabilities', name: 'ai-capabilities', component: AiCapabilityCenterView },
    {
      path: '/stores', name: 'stores', component: ReadonlyListView,
      props: { resource: 'stores', title: 'Stores', description: 'Platform, store code, test status, and product count.', columns: [
        { key: 'platform', label: 'Platform' }, { key: 'store_code', label: 'Store code' },
        { key: 'store_name', label: 'Store' }, { key: 'test_data_mode', label: 'Test data' }, { key: 'product_count', label: 'Products' },
      ] },
    },
    {
      path: '/products', name: 'products', component: ReadonlyListView,
      props: { resource: 'products', title: 'Products and SKUs', description: 'Search products and open read-only SKU details.', columns: [
        { key: 'product_id', label: 'Product ID' }, { key: 'product_name_display', label: 'Product' },
        { key: 'store_code', label: 'Store' }, { key: 'sales_status', label: 'Status' }, { key: 'review_status', label: 'Review' },
      ] },
    },
    { path: '/products/:productId', name: 'product-detail', component: ProductDetailView, props: true },
    {
      path: '/faqs', name: 'faqs', component: ReadonlyListView,
      props: { resource: 'faqs', title: 'FAQs', description: 'Question, answer action, risk, scope, and sources.', columns: [
        { key: 'question', label: 'Question' }, { key: 'answer_action', label: 'Answer action' },
        { key: 'risk_level', label: 'Risk' }, { key: 'product_id', label: 'Product' }, { key: 'source_ids', label: 'Sources' },
      ] },
    },
    {
      path: '/safety-rules', name: 'safety-rules', component: ReadonlyListView,
      props: { resource: 'safety-rules', title: 'Safety rules', description: 'Scenario, risk, allowed action, prohibited claim, and sources.', columns: [
        { key: 'scenario', label: 'Scenario' }, { key: 'risk_level', label: 'Risk' },
        { key: 'action', label: 'Action' }, { key: 'forbidden_claim', label: 'Prohibited claim' }, { key: 'source_ids', label: 'Sources' },
      ] },
    },
    {
      path: '/sources', name: 'sources', component: ReadonlyListView,
      props: { resource: 'sources', title: 'Source evidence', description: 'Metadata and safe relative locators only; no preview or download.', columns: [
        { key: 'source_type', label: 'Type' }, { key: 'file_name', label: 'File' },
        { key: 'file_sha256', label: 'SHA' }, { key: 'product_id', label: 'Product' }, { key: 'sku_id', label: 'SKU' },
      ] },
    },
    {
      path: '/conflicts', name: 'conflicts', component: ReadonlyListView,
      props: { resource: 'conflicts', title: 'Conflicts and confirmation', description: 'Field values A/B, source, and current handling status.', columns: [
        { key: 'entity_id', label: 'Entity' }, { key: 'field_name', label: 'Field' },
        { key: 'value_a', label: 'Value A' }, { key: 'value_b', label: 'Value B' }, { key: 'status', label: 'Status' },
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
