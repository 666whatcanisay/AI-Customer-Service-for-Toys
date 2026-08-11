import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'
import AiChat from '@/views/AiChat.vue'
import CustomerWorkbenchLayout from '@/layouts/CustomerWorkbenchLayout.vue'
import ChannelAgentDesktopLayout from '@/layouts/ChannelAgentDesktopLayout.vue'
import ExperienceCases from '@/views/ExperienceCases.vue'
import FeedbackGuide from '@/views/FeedbackGuide.vue'
import HumanInLoopWorkspace from '@/views/HumanInLoopWorkspace.vue'
import ModuleInfo from '@/views/ModuleInfo.vue'
import MySuggestions from '@/views/MySuggestions.vue'
import SuggestionForm from '@/views/SuggestionForm.vue'
import WorkspaceHome from '@/views/WorkspaceHome.vue'
import LoginView from '@/views/LoginView.vue'
import ForbiddenView from '@/views/ForbiddenView.vue'
import ChangePasswordView from '@/views/ChangePasswordView.vue'
import StoreSelectionView from '@/views/StoreSelectionView.vue'
import DeviceSetupView from '@/views/DeviceSetupView.vue'
import { useAuthSession } from '@/auth/authSession'
import { fetchChannelAgentBootstrap } from '@/api/channelAgentDesktopClient'

const channelAgentDesktop = import.meta.env.VITE_CHANNEL_AGENT_DESKTOP === 'true'

export const createCustomerRouter = (
  history: RouterHistory = createWebHistory(),
  installAuthGuard = true
) => {
  const router = createRouter({
    history,
    routes: [
      { path: '/login', name: 'Login', component: LoginView, meta: { public: true, title: '客服登录' } },
      { path: '/forbidden', name: 'Forbidden', component: ForbiddenView, meta: { public: true, title: '没有权限' } },
      { path: '/change-password', name: 'ChangePassword', component: ChangePasswordView, meta: { authFlow: true, title: '修改初始密码' } },
      { path: '/store-selection', name: 'StoreSelection', component: StoreSelectionView, meta: { authFlow: true, title: '选择客服店铺' } },
      { path: '/device-setup', name: 'DeviceSetup', component: DeviceSetupView, meta: { authFlow: true, title: '首次使用设置' } },
      {
        path: '/',
        component: channelAgentDesktop ? ChannelAgentDesktopLayout : CustomerWorkbenchLayout,
        meta: { requiredPermission: 'workspace.access' },
        children: channelAgentDesktop ? [
          { path: '', redirect: '/workspace' },
          { path: 'workspace', name: 'HumanInLoopWorkspace', component: HumanInLoopWorkspace, meta: { title: '客服会话工作台' } }
        ] : [
          { path: '', name: 'WorkspaceHome', component: WorkspaceHome, meta: { title: '工作台首页' } },
          { path: 'workspace', name: 'HumanInLoopWorkspace', component: HumanInLoopWorkspace, meta: { title: '客服会话工作台' } },
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
  if (installAuthGuard) {
    router.beforeEach(async (to) => {
      if (to.meta.public === true) return true
      const auth = useAuthSession()
      const authenticated = await auth.restore()
      if (!authenticated) return { path: '/login', query: { redirect: to.fullPath } }
      const current = auth.user.value
      if (current?.must_change_password === true && to.path !== '/change-password') {
        return '/change-password'
      }
      if (to.path === '/change-password') return true
      if (channelAgentDesktop && current?.roles.includes('CUSTOMER_SERVICE') === true) {
        if (to.path === '/device-setup') return true
        try {
          const bootstrap = await fetchChannelAgentBootstrap()
          const identityIncomplete = !['BOUND', 'ACTIVE'].includes(bootstrap.binding.identity_status)
          const storeIncomplete = !bootstrap.binding.active_store_id
          if (identityIncomplete || storeIncomplete) return '/device-setup'
        } catch {
          // 本地诊断中心负责展示连接故障；路由守卫不制造循环跳转。
        }
      }
      const needsStores = current?.roles.includes('CUSTOMER_SERVICE') === true
        && !current.stores.some((store) => store.is_default)
      if (needsStores && to.path !== '/store-selection') return '/store-selection'
      if (to.path === '/store-selection') {
        return current?.roles.includes('CUSTOMER_SERVICE') === true ? true : '/forbidden'
      }
      if (to.path === '/device-setup') return '/forbidden'
      const required = typeof to.meta.requiredPermission === 'string'
        ? to.meta.requiredPermission
        : 'workspace.access'
      if (!auth.hasPermission(required)) return '/forbidden'
      return true
    })
  }
  return router
}

const router = createCustomerRouter()

export default router
