import { ref } from 'vue'

import {
  apiErrorMessage,
  getAiControlCenterOverview,
  type AiControlCenterOverview,
} from '../api/client'

export const aiControlCenterOverview = ref<AiControlCenterOverview | null>(null)
export const aiControlCenterLoading = ref(false)
export const aiControlCenterError = ref('')

let inFlight: Promise<AiControlCenterOverview> | null = null

export function loadAiControlCenterOverview(force = false): Promise<AiControlCenterOverview> {
  if (!force && aiControlCenterOverview.value) {
    return Promise.resolve(aiControlCenterOverview.value)
  }
  if (inFlight) return inFlight
  aiControlCenterLoading.value = true
  aiControlCenterError.value = ''
  inFlight = getAiControlCenterOverview()
    .then((value) => {
      aiControlCenterOverview.value = value
      return value
    })
    .catch((reason: unknown) => {
      aiControlCenterError.value = apiErrorMessage(reason)
      throw reason
    })
    .finally(() => {
      aiControlCenterLoading.value = false
      inFlight = null
    })
  return inFlight
}
