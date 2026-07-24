import { inject, ref, type InjectionKey, type Ref } from 'vue'
import { platformClient } from '@/api/platformClient'
import { ragClient } from '@/api/ragClient'
import { toPlatformClientError, toRagClientError } from '@/api/errorMapper'

export interface SystemStatusStore {
  aiReady: Ref<boolean>
  dataReady: Ref<boolean>
  loading: Ref<boolean>
  aiError: Ref<string>
  dataError: Ref<string>
  refresh: () => Promise<void>
}

export const SystemStatusKey: InjectionKey<SystemStatusStore> = Symbol('SystemStatus')

export const createSystemStatusStore = (): SystemStatusStore => {
  const aiReady = ref(false)
  const dataReady = ref(false)
  const loading = ref(false)
  const aiError = ref('')
  const dataError = ref('')

  const refresh = async () => {
    if (loading.value) return
    loading.value = true
    aiError.value = ''
    dataError.value = ''

    await Promise.all([
      ragClient.getHealth()
        .then((health) => {
          aiReady.value = health.ready
          if (!health.ready) aiError.value = 'AI 服务仍在准备中'
        })
        .catch((error) => {
          aiReady.value = false
          aiError.value = toRagClientError(error).message
        }),
      platformClient.getHealth()
        .then((health) => {
          dataReady.value = health.status === 'ok'
          if (!dataReady.value) dataError.value = '数据服务状态异常'
        })
        .catch((error) => {
          dataReady.value = false
          dataError.value = toPlatformClientError(error).message
        })
    ])

    loading.value = false
  }

  return { aiReady, dataReady, loading, aiError, dataError, refresh }
}

export const useSystemStatus = () => {
  const store = inject(SystemStatusKey)
  if (!store) throw new Error('SystemStatusStore is not provided')
  return store
}
