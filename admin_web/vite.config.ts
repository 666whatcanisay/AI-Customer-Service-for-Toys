import { resolve } from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import {
  createRuntimeIdentity,
  createRuntimeIdentityPlugin
} from '../scripts/vite-runtime-identity'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const platformProxyTarget = env.VITE_PLATFORM_PROXY_TARGET?.trim() || 'http://127.0.0.1:8011'
  const aiProxyTarget = env.VITE_AI_PROXY_TARGET?.trim() || 'http://127.0.0.1:8000'
  const identity = createRuntimeIdentity({
    rootDirectory: __dirname,
    packageJsonPath: resolve(__dirname, 'package.json'),
    productName: 'AI 客服平台运营管理中心',
    viteMode: mode,
    startupMode: env.VITE_START_MODE,
    apiTargets: [env.VITE_PLATFORM_API_BASE_URL ?? '/platform-api', env.VITE_AI_API_BASE_URL ?? '/ai-api']
  })

  return {
    plugins: [vue(), createRuntimeIdentityPlugin(identity)],
    define: {
      'import.meta.env.VITE_ADMIN_VERSION': JSON.stringify(identity.version),
      'import.meta.env.VITE_GIT_SHORT_SHA': JSON.stringify(identity.gitShortSha),
      'import.meta.env.VITE_GIT_SOURCE_STATE': JSON.stringify(identity.sourceState),
      'import.meta.env.VITE_RUNTIME_RUN_MODE': JSON.stringify(identity.runMode),
      'import.meta.env.VITE_RUNTIME_API_MODE': JSON.stringify(identity.apiMode)
    },
    server: {
      proxy: {
        '/platform-api': {
          target: platformProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/platform-api/, ''),
        },
        '/ai-api': {
          target: aiProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/ai-api/, ''),
        },
      },
    },
    test: {
      environment: 'jsdom',
    },
  }
})
