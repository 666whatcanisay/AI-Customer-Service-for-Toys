import {
  RAG_ACTIONS,
  RISK_LEVELS,
  type RagAction,
  type RagChatResult,
  type RagChatContext,
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
  if (!isRecord(payload) || !isRecord(payload.data)) {
    throw new RagAdapterError('B-T03 只接受包含 data 的 A API 响应')
  }
  return payload.data
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

const requiredStringList = (value: unknown, field: string): string[] => {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new RagAdapterError(`API 响应字段 ${field} 必须为 string[]`)
  }
  return value
}

const normalizeAction = (value: unknown): RagAction => {
  if (typeof value !== 'string' || !RAG_ACTIONS.includes(value as RagAction)) {
    throw new RagAdapterError('API 响应 action 不是已冻结的六种动作')
  }
  return value as RagAction
}

const normalizeRisk = (value: unknown): RiskLevel => {
  if (typeof value !== 'string' || !RISK_LEVELS.includes(value as RiskLevel)) {
    throw new RagAdapterError('API 响应 risk_level 无效')
  }
  return value as RiskLevel
}

const normalizeCitation = (value: unknown): RagCitation => {
  if (!isRecord(value)) throw new RagAdapterError('API sources 包含无效记录')
  const file = firstString(value, ['source_name'])
  const summary = firstString(value, ['excerpt'])
  const knowledgeVersion = firstString(value, ['knowledge_version'])
  if (
    !Object.prototype.hasOwnProperty.call(value, 'product_id') ||
    !Object.prototype.hasOwnProperty.call(value, 'sku_id')
  ) {
    throw new RagAdapterError('API source 缺少 product_id/sku_id')
  }
  if (!file || !summary || !knowledgeVersion) {
    throw new RagAdapterError('API source 缺少 source_name/excerpt/knowledge_version')
  }

  return {
    file,
    page: firstNumber(value, ['page']),
    chunkId: firstString(value, ['chunk_id']),
    summary,
    distance: firstNumber(value, ['distance']),
    knowledgeVersion,
    sourceIds: requiredStringList(value.source_ids, 'sources[].source_ids'),
    productId: firstString(value, ['product_id']),
    skuId: firstString(value, ['sku_id'])
  }
}

const normalizeContext = (value: unknown): RagChatContext => {
  if (!isRecord(value)) throw new RagAdapterError('API 响应缺少 context')
  if (!Object.prototype.hasOwnProperty.call(value, 'sku_id')) {
    throw new RagAdapterError('API 响应 context 缺少 sku_id')
  }
  const tenantId = firstString(value, ['tenant_id'])
  const platform = firstString(value, ['platform'])
  const storeCode = firstString(value, ['store_code'])
  const productId = firstString(value, ['product_id'])
  const skuValue = value.sku_id
  if (!tenantId || !platform || !storeCode || !productId) {
    throw new RagAdapterError('API 响应 context 缺少范围字段')
  }
  if (skuValue !== null && skuValue !== undefined && typeof skuValue !== 'string') {
    throw new RagAdapterError('API 响应 context.sku_id 类型无效')
  }
  return {
    tenant_id: tenantId,
    platform,
    store_code: storeCode,
    product_id: productId,
    sku_id: typeof skuValue === 'string' && skuValue.trim() ? skuValue.trim() : null
  }
}

export const adaptHealthResponse = (payload: unknown): RagHealth => {
  if (!isRecord(payload)) throw new RagAdapterError('API 返回了无法识别的数据格式')
  const data = isRecord(payload.data) ? payload.data : payload
  return {
    status: firstString(data, ['status']) ?? 'unknown',
    ready: data.ready === true
  }
}

export const adaptChatResponse = (payload: unknown): RagChatResult => {
  const data = unwrapData(payload)
  const answer = firstString(data, ['answer'])
  if (!answer) throw new RagAdapterError('API 响应缺少 answer 字段')

  const requestId = firstString(data, ['request_id'])
  const model = firstString(data, ['model'])
  const latencyMs = firstNumber(data, ['latency_ms'])
  if (!requestId || !model || latencyMs === null) {
    throw new RagAdapterError('API 响应缺少 request_id/model/latency_ms')
  }

  if (!Array.isArray(data.sources)) throw new RagAdapterError('API 响应缺少 sources')

  return {
    requestId,
    model,
    answer,
    action: normalizeAction(data.action),
    riskLevel: normalizeRisk(data.risk_level),
    citations: data.sources.map(normalizeCitation),
    warnings: requiredStringList(data.warnings, 'warnings'),
    requiredFields: requiredStringList(data.required_fields, 'required_fields'),
    latencyMs,
    context: normalizeContext(data.context)
  }
}
