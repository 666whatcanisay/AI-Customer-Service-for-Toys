import { describe, expect, it } from 'vitest'
import {
  MODULE_STATUSES,
  MODULE_STATUS_LABELS,
  WORKBENCH_MODULES,
  findWorkbenchModule,
  groupWorkbenchModules
} from './modules'

const EXPECTED_MODULES = [
  ['ai-chat', 'AI 客服', 'AVAILABLE'],
  ['suggestions', '意见与建议', 'AVAILABLE'],
  ['after-sales', '售后中心', 'DEVELOPING'],
  ['product-query', '商品查询', 'PLANNED'],
  ['drawing-manual-assistant', '图纸/说明书助手', 'PLANNED'],
  ['work-orders', '工单中心', 'PLANNED'],
  ['refund-interception', '退款拦截', 'PLANNED'],
  ['in-transit-refunds', '在途退款处理', 'PLANNED'],
  ['instant-refund-interception', '极速退款拦截', 'PLANNED'],
  ['courier-note-assistant', '快递备注助手', 'PLANNED'],
  ['replacement-management', '补发管理', 'PLANNED'],
  ['order-appeals', '订单申诉', 'PLANNED']
] as const

describe('workspace module registry', () => {
  it('registers the twelve requested modules with complete card metadata', () => {
    expect(WORKBENCH_MODULES).toHaveLength(EXPECTED_MODULES.length)
    expect(WORKBENCH_MODULES.map(({ key, name, status }) => [key, name, status]))
      .toEqual(EXPECTED_MODULES)
    expect(new Set(WORKBENCH_MODULES.map((module) => module.key)).size).toBe(12)

    for (const module of WORKBENCH_MODULES) {
      expect(module.description).not.toBe('')
      expect(module.stage).not.toBe('')
      expect(module.expectedInput).not.toBe('')
      expect(module.expectedOutput).not.toBe('')
      expect(module.requiresHuman).toBe(true)
      expect(module.automationLevel).not.toBe('')
      expect(module.route).toMatch(/^\//)
    }
  })

  it('maps every supported status to its Chinese label', () => {
    expect(MODULE_STATUSES).toEqual([
      'AVAILABLE',
      'TESTING',
      'DEVELOPING',
      'PLANNED',
      'PAUSED'
    ])
    expect(MODULE_STATUS_LABELS).toEqual({
      AVAILABLE: '可用',
      TESTING: '验证中',
      DEVELOPING: '开发中',
      PLANNED: '规划中',
      PAUSED: '已暂停'
    })
  })

  it('finds modules by key and returns undefined for unknown keys', () => {
    expect(findWorkbenchModule('after-sales')?.name).toBe('售后中心')
    expect(findWorkbenchModule('missing-module')).toBeUndefined()
  })

  it('groups all modules without dropping empty statuses', () => {
    const groups = groupWorkbenchModules()

    expect(groups.AVAILABLE.map((module) => module.key)).toEqual(['ai-chat', 'suggestions'])
    expect(groups.TESTING).toEqual([])
    expect(groups.DEVELOPING.map((module) => module.key)).toEqual(['after-sales'])
    expect(groups.PLANNED).toHaveLength(9)
    expect(groups.PAUSED).toEqual([])
    expect(Object.values(groups).flat()).toHaveLength(12)
  })

  it('uses live routes only for available modules and explanation routes otherwise', () => {
    expect(
      WORKBENCH_MODULES
        .filter((module) => module.status === 'AVAILABLE')
        .map(({ key, route }) => [key, route])
    ).toEqual([
      ['ai-chat', '/ai-chat'],
      ['suggestions', '/suggestions']
    ])

    for (const module of WORKBENCH_MODULES.filter(({ status }) => status !== 'AVAILABLE')) {
      expect(module.route).toBe(`/modules/${module.key}`)
    }
  })
})
