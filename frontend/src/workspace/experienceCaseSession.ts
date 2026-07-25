import { computed, readonly, ref } from 'vue'
import type { ExperienceCaseSubmission } from '@/api/experienceCaseTypes'

// This is deliberately in-memory. Customer-facing text is never persisted in browser storage.
const submissions = ref<ExperienceCaseSubmission[]>([])

export const recordExperienceCaseSubmission = (submission: ExperienceCaseSubmission) => {
  submissions.value = [submission, ...submissions.value]
}

export const clearExperienceCaseSubmissions = () => {
  submissions.value = []
}

export const useExperienceCaseSubmissions = (createdBy: string) => ({
  submissions: computed(() => submissions.value.filter((item) => item.createdBy === createdBy)),
  allSubmissions: readonly(submissions)
})
