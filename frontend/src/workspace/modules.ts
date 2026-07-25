export const MODULE_STATUSES = [
  'AVAILABLE',
  'TESTING',
  'DEVELOPING',
  'PLANNED',
  'PAUSED'
] as const

export type ModuleStatus = (typeof MODULE_STATUSES)[number]

export const MODULE_STATUS_LABELS: Readonly<Record<ModuleStatus, string>> = {
  AVAILABLE: '可用',
  TESTING: '测试中',
  DEVELOPING: '开发中',
  PLANNED: '规划中',
  PAUSED: '已暂停'
}

export interface WorkbenchModule {
  key: string
  name: string
  description: string
  status: ModuleStatus
  stage: string
  expectedInput: string
  expectedOutput: string
  requiresHuman: boolean
  automationLevel: string
  route: string
}

export const WORKBENCH_MODULES = [
  {
    key: 'ai-chat',
    name: 'AI 客服',
    description: '根据已审核的商品资料生成客服建议回复和引用。',
    status: 'AVAILABLE',
    stage: '已上线，可进行内部测试',
    expectedInput: '店铺、商品、可选 SKU 和客户问题',
    expectedOutput: '可编辑的建议回复、动作提示和引用来源',
    requiresHuman: true,
    automationLevel: 'AI 辅助，人工确认',
    route: '/ai-chat'
  },
  {
    key: 'suggestions',
    name: '意见与建议',
    description: '提交工作台问题、改进意见和新功能建议。',
    status: 'AVAILABLE',
    stage: '已上线，可提交和查询建议',
    expectedInput: '测试客服身份、模块、分类和建议内容',
    expectedOutput: '建议编号、处理状态和历史记录',
    requiresHuman: true,
    automationLevel: '人工提交，人工处理',
    route: '/suggestions'
  },
  {
    key: 'after-sales',
    name: '售后中心',
    description: '统一查看售后事项并辅助客服判断下一步。',
    status: 'DEVELOPING',
    stage: '开发中，暂不可执行售后业务',
    expectedInput: '售后问题、订单摘要和商品信息',
    expectedOutput: '处理建议、风险提示和人工操作清单',
    requiresHuman: true,
    automationLevel: '仅规划辅助，不执行业务',
    route: '/modules/after-sales'
  },
  {
    key: 'product-query',
    name: '商品查询',
    description: '帮助客服快速定位商品、规格和已审核资料。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '店铺、商品关键词或规格线索',
    expectedOutput: '匹配商品、SKU 和资料摘要',
    requiresHuman: true,
    automationLevel: '规划中，不执行业务',
    route: '/modules/product-query'
  },
  {
    key: 'drawing-manual-assistant',
    name: '图纸/说明书助手',
    description: '辅助查找商品图纸、说明书和安装资料。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '商品、SKU 和资料需求',
    expectedOutput: '候选图纸、说明书和使用提示',
    requiresHuman: true,
    automationLevel: '规划中，不自动发送资料',
    route: '/modules/drawing-manual-assistant'
  },
  {
    key: 'work-orders',
    name: '工单中心',
    description: '集中整理需要跟进的客服事项和处理进度。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '问题摘要、关联订单和跟进要求',
    expectedOutput: '工单草稿、负责人和待办状态',
    requiresHuman: true,
    automationLevel: '规划中，不自动创建工单',
    route: '/modules/work-orders'
  },
  {
    key: 'refund-interception',
    name: '退款拦截',
    description: '辅助识别可沟通的退款场景并给出处理建议。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '退款原因、订单摘要和沟通上下文',
    expectedOutput: '沟通建议、风险和人工处理步骤',
    requiresHuman: true,
    automationLevel: '规划中，不修改订单或退款',
    route: '/modules/refund-interception'
  },
  {
    key: 'in-transit-refunds',
    name: '在途退款处理',
    description: '辅助梳理运输途中退款的处理条件和步骤。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '物流状态、退款原因和订单摘要',
    expectedOutput: '核对清单、沟通建议和风险提示',
    requiresHuman: true,
    automationLevel: '规划中，不修改订单或退款',
    route: '/modules/in-transit-refunds'
  },
  {
    key: 'instant-refund-interception',
    name: '极速退款拦截',
    description: '辅助识别极速退款场景中的人工核查事项。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '退款状态、订单摘要和异常线索',
    expectedOutput: '人工核查清单和风险提示',
    requiresHuman: true,
    automationLevel: '规划中，不修改订单或退款',
    route: '/modules/instant-refund-interception'
  },
  {
    key: 'courier-note-assistant',
    name: '快递备注助手',
    description: '辅助整理需要人工提交给快递方的备注内容。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '物流信息和备注需求',
    expectedOutput: '可核对的快递备注草稿',
    requiresHuman: true,
    automationLevel: '规划中，不自动提交备注',
    route: '/modules/courier-note-assistant'
  },
  {
    key: 'replacement-management',
    name: '补发管理',
    description: '辅助记录补发需求并整理人工处理步骤。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '补发原因、商品和订单摘要',
    expectedOutput: '补发核对清单和处理建议',
    requiresHuman: true,
    automationLevel: '规划中，不创建或执行补发',
    route: '/modules/replacement-management'
  },
  {
    key: 'order-appeals',
    name: '订单申诉',
    description: '辅助整理订单申诉所需事实和材料清单。',
    status: 'PLANNED',
    stage: '规划中',
    expectedInput: '申诉原因、订单摘要和可用证据',
    expectedOutput: '申诉草稿、证据清单和风险提示',
    requiresHuman: true,
    automationLevel: '规划中，不自动提交申诉',
    route: '/modules/order-appeals'
  }
] as const satisfies readonly WorkbenchModule[]

export function findWorkbenchModule(moduleKey: string): WorkbenchModule | undefined {
  return WORKBENCH_MODULES.find((module) => module.key === moduleKey)
}

export function groupWorkbenchModules(
  modules: readonly WorkbenchModule[] = WORKBENCH_MODULES
): Record<ModuleStatus, WorkbenchModule[]> {
  const groups: Record<ModuleStatus, WorkbenchModule[]> = {
    AVAILABLE: [],
    TESTING: [],
    DEVELOPING: [],
    PLANNED: [],
    PAUSED: []
  }

  for (const module of modules) {
    groups[module.status].push(module)
  }

  return groups
}
