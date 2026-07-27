import { readonly, ref } from 'vue'

// Session-only counters make the home page useful without presenting browser state as server analytics.
const aiAssists = ref(0)
const feedbackSubmissions = ref(0)

export const recordAiAssist = () => {
  aiAssists.value += 1
}

export const recordAiFeedbackSubmission = () => {
  feedbackSubmissions.value += 1
}

export const clearCustomerSessionActivity = () => {
  aiAssists.value = 0
  feedbackSubmissions.value = 0
}

export const useCustomerSessionActivity = () => ({
  aiAssists: readonly(aiAssists),
  feedbackSubmissions: readonly(feedbackSubmissions)
})
