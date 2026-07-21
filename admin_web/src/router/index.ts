import { createRouter, createWebHistory } from 'vue-router'

import SystemStatusView from '../views/SystemStatusView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/system-status' },
    {
      path: '/system-status',
      name: 'system-status',
      component: SystemStatusView,
    },
  ],
})
