import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const frontendPackage = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf8')) as {
  version: string
}

function getGitShortSha() {
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

export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  define: {
    'import.meta.env.VITE_FRONTEND_VERSION': JSON.stringify(frontendPackage.version),
    'import.meta.env.VITE_GIT_SHORT_SHA': JSON.stringify(getGitShortSha()),
    'import.meta.env.VITE_BUILD_MODE': JSON.stringify(mode)
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
      '/platform-api': {
        target: 'http://127.0.0.1:8011',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/platform-api/, '')
      }
    }
  }
}))
