import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'
import AiChat from '@/views/AiChat.vue'
import AiControlCenter from '@/views/AiControlCenter.vue'
import CustomerWorkbenchLayout from '@/layouts/CustomerWorkbenchLayout.vue'
import ExperienceCases from '@/views/ExperienceCases.vue'
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
          { path: 'ai-control-center', name: 'AiControlCenter', component: AiControlCenter, meta: { title: 'AI 控制中心' } },
          { path: 'suggestions', name: 'SuggestionForm', component: SuggestionForm, meta: { title: '提交意见建议' } },
          { path: 'suggestions/mine', name: 'MySuggestions', component: MySuggestions, meta: { title: '我的建议' } },
          { path: 'experience-cases', name: 'ExperienceCases', component: ExperienceCases, meta: { title: '我的案例' } },
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
