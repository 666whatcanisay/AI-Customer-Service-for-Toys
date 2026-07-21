import { createRouter, createWebHistory } from 'vue-router'
import AiChat from '@/views/AiChat.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      alias: ['/chat', '/ai-chat', '/app'],
      name: 'AiChat',
      component: AiChat
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

export default router
