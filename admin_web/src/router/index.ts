import { createRouter, createWebHistory } from 'vue-router'

import SystemStatusView from '../views/SystemStatusView.vue'
import ImportBatchDetailView from '../views/ImportBatchDetailView.vue'
import ImportBatchListView from '../views/ImportBatchListView.vue'
import NewImportView from '../views/NewImportView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/system-status' },
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
  ],
})
