/**
 * Business-facing rendering for analysis evidence.
 *
 * Analysis payloads are versioned evidence supplied by another line.  This
 * adapter deliberately reads only commonly used, human-readable fields and
 * falls back to a Chinese "not provided" state.  It never guesses an analysis
 * outcome from raw JSON or creates an operation that the evidence did not ask
 * for.
 */
type EvidenceRecord = Record<string, unknown>

export interface AnalysisSummary {
  overview: string
  difference: string
  risk: string
  action: string
}

function nonEmptyText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

/** Business pages must not present an untranslated technical payload as a
 * Chinese operating conclusion.  The original evidence remains available in
 * the explicitly expanded technical section. */
export function businessText(value: unknown, fallback = '未提供'): string {
  const text = nonEmptyText(value)
  return text && /[\u3400-\u9fff]/.test(text) ? text : fallback
}

function firstText(record: EvidenceRecord, keys: string[]): string | null {
  for (const key of keys) {
    const value = nonEmptyText(record[key])
    if (value) return value
  }
  return null
}

function suggestionText(suggestions: Array<EvidenceRecord>): string | null {
  for (const suggestion of suggestions) {
    const text = firstText(suggestion, [
      'action',
      'suggestion',
      'recommendation',
      'summary',
      'description',
      'title',
    ])
    if (text) return text
  }
  return null
}

export function summarizeAnalysis(
  analysis: EvidenceRecord | null | undefined,
  suggestions: Array<EvidenceRecord> | null | undefined,
): AnalysisSummary {
  const source = analysis || {}
  const recommendation = suggestionText(suggestions || [])
  return {
    overview: businessText(firstText(source, ['summary', 'conclusion', 'overview', 'finding', 'root_cause']), '已提供分析结论，请查看技术详情'),
    difference: businessText(firstText(source, ['ai_human_difference', 'difference', 'gap', 'comparison'])),
    risk: businessText(firstText(source, ['risk_judgement', 'risk_assessment', 'risk', 'risk_level'])),
    action: businessText(firstText(source, ['recommended_action', 'next_action', 'action']) || recommendation, '暂无可直接展示的建议动作'),
  }
}

export function formatEvidenceTime(value: string | null | undefined): string {
  if (!value) return '未提供'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    hour12: false,
  }).format(date)
}

export function technicalJson(value: unknown): string {
  return JSON.stringify(value, null, 2)
}
