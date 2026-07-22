import {
  RAG_ACTIONS,
  RISK_LEVELS,
  type RagAction,
  type RagChatResult,
  type RagCitation,
  type RagHealth,
  type RiskLevel
} from './ragTypes'

type UnknownRecord = Record<string, unknown>

export class RagAdapterError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RagAdapterError'
  }
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const unwrapData = (payload: unknown): UnknownRecord => {
  if (!isRecord(payload)) throw new RagAdapterError('API 返回了无法识别的数据格式')
  return isRecord(payload.data) ? payload.data : payload
}

const firstString = (record: UnknownRecord, keys: string[]): string | null => {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

const firstNumber = (record: UnknownRecord, keys: string[]): number | null => {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

const stringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : []

const normalizeAction = (value: unknown): RagAction | null =>
  value === 'ANSWER'
    ? 'DIRECT_ANSWER'
    : typeof value === 'string' && RAG_ACTIONS.includes(value as RagAction)
      ? (value as RagAction)
      : null

const normalizeRisk = (value: unknown): RiskLevel | null =>
  typeof value === 'string' && RISK_LEVELS.includes(value as RiskLevel)
    ? (value as RiskLevel)
    : null

const normalizeCitation = (value: unknown): RagCitation | null => {
  if (!isRecord(value)) return null
  const file = firstString(value, ['file', 'source_name', 'source', 'filename', 'title'])
  const summary = firstString(value, ['summary', 'excerpt', 'content_preview', 'preview', 'snippet'])
  if (!file && !summary) return null

  return {
    file: file ?? '未命名来源',
    page: firstNumber(value, ['page', 'page_number']),
    chunkId: firstString(value, ['chunk_id', 'chunkId']),
    summary: summary ?? '',
    distance: firstNumber(value, ['distance', 'score']),
    knowledgeVersion: firstString(value, ['knowledge_version', 'version'])
  }
}

export const adaptHealthResponse = (payload: unknown): RagHealth => {
  const data = unwrapData(payload)
  return {
    status: firstString(data, ['status']) ?? 'unknown',
    ready: data.ready === true
  }
}

export const adaptChatResponse = (payload: unknown): RagChatResult => {
  const data = unwrapData(payload)
  const answer = firstString(data, ['answer'])
  if (!answer) throw new RagAdapterError('API 响应缺少 answer 字段')

  const rawCitations = Array.isArray(data.citations)
    ? data.citations
    : Array.isArray(data.sources)
      ? data.sources
      : []

  return {
    requestId: firstString(data, ['request_id', 'requestId']),
    model: firstString(data, ['model']),
    answer,
    action: normalizeAction(data.action),
    riskLevel: normalizeRisk(data.risk_level ?? data.riskLevel),
    citations: rawCitations
      .map(normalizeCitation)
      .filter((citation): citation is RagCitation => citation !== null),
    warnings: stringList(data.warnings),
    requiredFields: stringList(data.required_fields ?? data.requiredFields),
    latencyMs: firstNumber(data, ['latency_ms', 'elapsed_ms'])
  }
}
