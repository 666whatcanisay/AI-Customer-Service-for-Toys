import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'
import AiChat from '@/views/AiChat.vue'
import CustomerWorkbenchLayout from '@/layouts/CustomerWorkbenchLayout.vue'
import ExperienceCases from '@/views/ExperienceCases.vue'
import FeedbackGuide from '@/views/FeedbackGuide.vue'
import ModuleInfo from '@/views/ModuleInfo.vue'
import MySuggestions from '@/views/MySuggestions.vue'
import SuggestionForm from '@/views/SuggestionForm.vue'
import WorkspaceHome from '@/views/WorkspaceHome.vue'

export const createCustomerRouter = (history: RouterHistory = createWebHistory()) =>
  createRouter({
    history,
    routes: [
      {
        path: '/',
        component: CustomerWorkbenchLayout,
        children: [
          { path: '', name: 'WorkspaceHome', component: WorkspaceHome, meta: { title: '工作台首页' } },
          { path: 'ai-chat', name: 'AiChat', component: AiChat, meta: { title: 'AI 客服' } },
          { path: 'suggestions', name: 'SuggestionForm', component: SuggestionForm, meta: { title: '提交意见建议' } },
          { path: 'suggestions/mine', name: 'MySuggestions', component: MySuggestions, meta: { title: '我的建议' } },
          { path: 'experience-cases', name: 'ExperienceCases', component: ExperienceCases, meta: { title: '我的案例' } },
          { path: 'feedback', name: 'FeedbackGuide', component: FeedbackGuide, meta: { title: '问题反馈' } },
          { path: 'modules/:moduleKey', name: 'ModuleInfo', component: ModuleInfo, meta: { title: '模块说明' } }
        ]
      },
      { path: '/chat', redirect: '/ai-chat' },
      { path: '/app', redirect: '/' },
      { path: '/:pathMatch(.*)*', redirect: '/' }
    ]
  })

const router = createCustomerRouter()

export default router
