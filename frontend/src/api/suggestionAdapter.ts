import { PlatformAdapterError } from './platformAdapter'
import {
  SUGGESTION_CATEGORIES,
  SUGGESTION_FREQUENCIES,
  SUGGESTION_URGENCIES
} from './suggestionTypes'
import type {
  SuggestionCategory,
  SuggestionDraft,
  SuggestionFrequency,
  SuggestionList,
  SuggestionReceipt,
  SuggestionSummary,
  SuggestionUrgency
} from './suggestionTypes'

type UnknownRecord = Record<string, unknown>

export interface SuggestionRequestPayload {
  reporter_id: string
  reporter_name: string
  store_code: string | null
  module_key: string
  category: SuggestionCategory
  title: string
  description: string
  frequency: SuggestionFrequency
  urgency: SuggestionUrgency
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredString = (record: UnknownRecord, key: string, entity: string): string => {
  const value = record[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new PlatformAdapterError(`${entity} 缺少非空字段 ${key}`)
  }
  return value.trim()
}

const nullableString = (record: UnknownRecord, key: string, entity: string): string | null => {
  if (!(key in record)) throw new PlatformAdapterError(`${entity} 缺少字段 ${key}`)
  const value = record[key]
  if (value === null || value === '') return null
  if (typeof value !== 'string' || !value.trim()) {
    throw new PlatformAdapterError(`${entity} 字段 ${key} 类型无效`)
  }
  return value.trim()
}

const requiredInput = (value: string, key: string): string => {
  if (typeof value !== 'string' || !value.trim()) {
    throw new PlatformAdapterError(`建议请求缺少非空字段 ${key}`)
  }
  return value.trim()
}

const strictEnum = <T extends string>(
  value: unknown,
  allowed: readonly T[],
  key: string,
  entity: string
): T => {
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    throw new PlatformAdapterError(`${entity} 字段 ${key} 不在冻结枚举内`)
  }
  return value as T
}

const adaptListItem = (record: UnknownRecord, expectedReporterId: string): SuggestionSummary => {
  const reporterId = requiredString(record, 'reporter_id', '建议记录')
  if (reporterId !== expectedReporterId) {
    throw new PlatformAdapterError('建议列表包含其他客服的数据')
  }

  return {
    suggestionId: requiredString(record, 'suggestion_id', '建议记录'),
    reporterId,
    storeCode: nullableString(record, 'store_code', '建议记录'),
    moduleKey: requiredString(record, 'module_key', '建议记录'),
    category: strictEnum(record.category, SUGGESTION_CATEGORIES, 'category', '建议记录'),
    title: requiredString(record, 'title', '建议记录'),
    frequency: strictEnum(record.frequency, SUGGESTION_FREQUENCIES, 'frequency', '建议记录'),
    urgency: strictEnum(record.urgency, SUGGESTION_URGENCIES, 'urgency', '建议记录'),
    status: requiredString(record, 'status', '建议记录')
  }
}

export const toSuggestionPayload = (draft: SuggestionDraft): SuggestionRequestPayload => ({
  reporter_id: requiredInput(draft.reporterId, 'reporter_id'),
  reporter_name: requiredInput(draft.reporterName, 'reporter_name'),
  store_code: draft.storeCode?.trim() || null,
  module_key: requiredInput(draft.moduleKey, 'module_key'),
  category: strictEnum(draft.category, SUGGESTION_CATEGORIES, 'category', '建议请求'),
  title: requiredInput(draft.title, 'title'),
  description: requiredInput(draft.description, 'description'),
  frequency: strictEnum(draft.frequency, SUGGESTION_FREQUENCIES, 'frequency', '建议请求'),
  urgency: strictEnum(draft.urgency, SUGGESTION_URGENCIES, 'urgency', '建议请求')
})

export const adaptSuggestionReceipt = (payload: unknown): SuggestionReceipt => {
  if (!isRecord(payload)) throw new PlatformAdapterError('建议提交接口返回格式无效')
  const record = 'data' in payload ? payload.data : payload
  if (!isRecord(record)) throw new PlatformAdapterError('建议提交接口 data 格式无效')

  return {
    suggestionId: requiredString(record, 'suggestion_id', '建议提交结果'),
    status: requiredString(record, 'status', '建议提交结果')
  }
}

export const adaptSuggestionList = (payload: unknown, reporterId: string): SuggestionList => {
  const expectedReporterId = requiredInput(reporterId, 'reporter_id')
  if (
    !isRecord(payload) ||
    !Array.isArray(payload.items) ||
    typeof payload.total !== 'number' ||
    !Number.isInteger(payload.total) ||
    payload.total < 0
  ) {
    throw new PlatformAdapterError('建议列表接口必须返回 {items,total}')
  }

  return {
    items: payload.items.map((item) => {
      if (!isRecord(item)) throw new PlatformAdapterError('建议列表包含无效记录')
      return adaptListItem(item, expectedReporterId)
    }),
    total: payload.total
  }
}
