import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

const adminPackage = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf8')) as {
  version: string
}

function getGitShortSha(): string {
  try {
    return execFileSync('git', ['rev-parse', '--short', 'HEAD'], {
      cwd: __dirname,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore']
    }).trim()
  } catch {
    return 'unknown'
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  return {
    plugins: [vue()],
    define: {
      'import.meta.env.VITE_ADMIN_VERSION': JSON.stringify(adminPackage.version),
      'import.meta.env.VITE_GIT_SHORT_SHA': JSON.stringify(getGitShortSha()),
      'import.meta.env.VITE_BUILD_MODE': JSON.stringify(mode)
    },
    server: {
      proxy: {
        '/platform-api': {
          target: env.VITE_PLATFORM_API_TARGET || 'http://127.0.0.1:8011',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/platform-api/, ''),
        },
        '/ai-api': {
          target: env.VITE_AI_API_TARGET || 'http://127.0.0.1:8000',
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
