import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import {
  createRuntimeIdentity,
  createRuntimeIdentityPlugin
} from '../scripts/vite-runtime-identity'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const ragProxyTarget = env.VITE_RAG_PROXY_TARGET?.trim() || 'http://127.0.0.1:8000'
  const platformProxyTarget = env.VITE_PLATFORM_PROXY_TARGET?.trim() || 'http://127.0.0.1:8011'
  const identity = createRuntimeIdentity({
    rootDirectory: __dirname,
    packageJsonPath: resolve(__dirname, 'package.json'),
    productName: '木木小树 AI 客服工作台',
    viteMode: mode,
    startupMode: env.VITE_START_MODE,
    apiTargets: [env.VITE_RAG_API_BASE_URL ?? '/rag-api', env.VITE_PLATFORM_API_BASE_URL ?? '/platform-api']
  })

  return {
    plugins: [vue(), createRuntimeIdentityPlugin(identity)],
    define: {
      'import.meta.env.VITE_FRONTEND_VERSION': JSON.stringify(identity.version),
      'import.meta.env.VITE_GIT_SHORT_SHA': JSON.stringify(identity.gitShortSha),
      'import.meta.env.VITE_GIT_SOURCE_STATE': JSON.stringify(identity.sourceState),
      'import.meta.env.VITE_RUNTIME_RUN_MODE': JSON.stringify(identity.runMode),
      'import.meta.env.VITE_RUNTIME_API_MODE': JSON.stringify(identity.apiMode)
    },
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      }
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        // Deliberately limited to the two approved service prefixes. The browser
        // never receives a route that can proxy to an arbitrary upstream.
        '/rag-api': {
          target: ragProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/rag-api/, '')
        },
        '/platform-api': {
          target: platformProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/platform-api/, '')
        }
      }
    }
  }
})
