import { describe, expect, it } from 'vitest'
import { PlatformAdapterError } from './platformAdapter'
import {
  adaptSuggestionList,
  adaptSuggestionReceipt,
  toSuggestionPayload
} from './suggestionAdapter'
import type { SuggestionDraft } from './suggestionTypes'

const draft: SuggestionDraft = {
  reporterId: ' agent-001 ',
  reporterName: ' 木木 ',
  storeCode: ' PDD-SM ',
  moduleKey: 'AI_CHAT',
  category: 'IMPROVEMENT',
  title: ' 建议增加快捷入口 ',
  description: ' 希望减少重复点击。 ',
  frequency: 'DAILY',
  urgency: 'MEDIUM'
}

const listItem = {
  suggestion_id: 'SUG-001',
  reporter_id: 'agent-001',
  reporter_name: '不应保留',
  store_code: 'PDD-SM',
  module_key: 'AI_CHAT',
  category: 'BUG',
  title: '页面卡顿',
  description: '不应保留的完整正文',
  frequency: 'FREQUENT',
  urgency: 'HIGH',
  status: 'IN_REVIEW'
}

describe('suggestionAdapter', () => {
  it('maps the camelCase draft to the frozen snake_case request', () => {
    expect(toSuggestionPayload(draft)).toEqual({
      reporter_id: 'agent-001',
      reporter_name: '木木',
      store_code: 'PDD-SM',
      module_key: 'AI_CHAT',
      category: 'IMPROVEMENT',
      title: '建议增加快捷入口',
      description: '希望减少重复点击。',
      frequency: 'DAILY',
      urgency: 'MEDIUM'
    })
  })

  it('sends an empty store as null', () => {
    expect(toSuggestionPayload({ ...draft, storeCode: '   ' }).store_code).toBeNull()
    expect(toSuggestionPayload({ ...draft, storeCode: null }).store_code).toBeNull()
  })

  it('rejects values outside the frozen enums', () => {
    expect(() => toSuggestionPayload({ ...draft, category: 'QUESTION' as never })).toThrow(
      PlatformAdapterError
    )
    expect(() => toSuggestionPayload({ ...draft, frequency: 'WEEKLY' as never })).toThrow(
      PlatformAdapterError
    )
    expect(() => toSuggestionPayload({ ...draft, urgency: 'CRITICAL' as never })).toThrow(
      PlatformAdapterError
    )
  })

  it('accepts submission results at the top level or inside data', () => {
    const expected = { suggestionId: 'SUG-001', status: 'SUBMITTED' }
    expect(adaptSuggestionReceipt({ suggestion_id: 'SUG-001', status: 'SUBMITTED' })).toEqual(
      expected
    )
    expect(
      adaptSuggestionReceipt({
        data: { suggestion_id: 'SUG-001', status: 'SUBMITTED', description: '不保留' }
      })
    ).toEqual(expected)
  })

  it('requires an opaque non-empty submission status', () => {
    expect(() => adaptSuggestionReceipt({ suggestion_id: 'SUG-001', status: '' })).toThrow(
      PlatformAdapterError
    )
  })

  it('strictly adapts {items,total} without retaining private list fields', () => {
    const result = adaptSuggestionList({ items: [listItem], total: 1 }, 'agent-001')

    expect(result).toEqual({
      items: [
        {
          suggestionId: 'SUG-001',
          reporterId: 'agent-001',
          storeCode: 'PDD-SM',
          moduleKey: 'AI_CHAT',
          category: 'BUG',
          title: '页面卡顿',
          frequency: 'FREQUENT',
          urgency: 'HIGH',
          status: 'IN_REVIEW'
        }
      ],
      total: 1
    })
    expect(result.items[0]).not.toHaveProperty('description')
    expect(result.items[0]).not.toHaveProperty('reporterName')
  })

  it('rejects malformed envelopes and enum values', () => {
    expect(() => adaptSuggestionList({ items: [] }, 'agent-001')).toThrow(PlatformAdapterError)
    expect(() =>
      adaptSuggestionList(
        { items: [{ ...listItem, category: 'QUESTION' }], total: 1 },
        'agent-001'
      )
    ).toThrow(PlatformAdapterError)
  })

  it('rejects records belonging to another reporter', () => {
    expect(() =>
      adaptSuggestionList(
        { items: [{ ...listItem, reporter_id: 'agent-002' }], total: 1 },
        'agent-001'
      )
    ).toThrow('建议列表包含其他客服的数据')
  })
})
