/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_RAG_API_BASE_URL?: string
  readonly VITE_PLATFORM_API_BASE_URL?: string
  readonly VITE_START_MODE?: 'LOCAL' | 'LAN'
  readonly VITE_API_MODE?: 'SAME_ORIGIN_PROXY' | 'DIRECT'
  readonly VITE_CUSTOMER_ENTRY_URL?: string
  readonly VITE_FRONTEND_VERSION?: string
  readonly VITE_GIT_SHORT_SHA?: string
  readonly VITE_RUNTIME_RUN_MODE?: string
  readonly VITE_RUNTIME_API_MODE?: 'SAME_ORIGIN_PROXY' | 'DIRECT' | 'HYBRID' | 'UNAVAILABLE'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
