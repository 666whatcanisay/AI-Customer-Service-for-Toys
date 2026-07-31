/**
 * Chinese labels for stable API enum values.
 *
 * Transport values remain unchanged. This module only prevents the operations
 * UI from making a nontechnical pilot operator interpret implementation codes.
 */
const STATUS_LABELS: Record<string, string> = {
  NEW: '新建',
  REVIEWING: '审核中',
  APPROVED: '已通过',
  DRAFT: '草稿',
  PENDING_REVIEW: '待审核',
  EFFECTIVE: '已生效',
  PARTIALLY_AVAILABLE: '部分可用',
  MISSING_KNOWLEDGE: '缺少知识',
  UNCONFIRMED: '无法确认',
  PENDING: '待处理',
  IN_PROGRESS: '补充中',
  PENDING_VERIFICATION: '待验证',
  REJECTED: '已拒绝',
  SUBMITTED: '已提交',
  PLANNED: '已规划',
  DONE: '已完成',
  NOT_EXPORTED: '未导出',
  EXPORTED: '已导出',
  EVALUATED: '已评测',
  WRITEBACK_REJECTED: '回写未通过',
  ANALYZING: '分析中',
  ANALYZED: '已完成分析',
  CONFIRMED: '已确认',
  PROCESSING: '处理中',
  SOLVED: '已解决',
  VERIFIED: '已验证',
  COMPLETED: '已补充',
  IMPROVED: 'AI 已改善',
  NOT_IMPROVED: '仍需优化',
  UNCLASSIFIED: '待分析',
  KNOWLEDGE_MISSING: '知识缺失',
  PRODUCT_INFO_ERROR: '商品信息错误',
  SKU_ERROR: 'SKU 信息错误',
  INCOMPLETE_ANSWER: '回答不完整',
  EXPRESSION_ISSUE: '表达问题',
  APPROVED_FOR_ANALYSIS: '已审核，待分析',
  ANALYSIS_FAILED: '分析未完成',
  RECOGNIZED: '已识别，待审核',
  OPEN: '待补充',
  ACKNOWLEDGED: '已知悉',
  RESOLVED: '已修复',
  DISMISSED: '不适用',
  PRODUCT_SPEC: '商品规格',
  PRODUCT_DETAIL_SCREENSHOT: '商品详情截图',
  PRODUCT_MAIN_IMAGE: '商品主图',
  SKU_SCREENSHOT: 'SKU截图',
  SIZE_IMAGE: '尺寸图片',
  PACKAGING_IMAGE: '包装图片',
  ACCESSORY_IMAGE: '配件图片',
  TEST_VERIFIED: '已核验',
  SAFETY_INSTRUCTION: '安全说明',
  ASSEMBLY_GUIDE: '拼装说明',
  FAQ_SOURCE: '问答资料',
  FACT_ERROR: '事实错误',
  MISSING_INFO: '信息缺失',
  STYLE_ISSUE: '表达问题',
  RISK_ISSUE: '风险问题',
  OTHER: '其他问题',
  PRODUCT_KNOWLEDGE: '商品知识',
  SKU_DIFFERENCE: 'SKU差异知识',
  FAQ: '客服FAQ',
  SAFETY_RULE: '商品安全规则',
  AI_FEEDBACK: '客服AI问题反馈',
  KNOWLEDGE_GAP: 'AI知识缺口',
  ADOPTED: '直接采用',
  EDITED_ADOPTED: '编辑后采用',
  CORRECTION: '人工纠正',
  ESCALATED: '升级处理',
  RECEIVED: '已接收',
  PARSING: '解析中',
  VALIDATED: '已校验',
  READY_FOR_REVIEW: '待审核',
  FAILED: '处理失败',
  VALID: '校验通过',
  INVALID: '格式错误',
  DUPLICATE: '重复记录',
  CONFLICT: '存在冲突',
  IMPORTED_TEST_ONLY: '已导入（初始化资料）',
  INITIAL_IMPORT: '初始化导入',
  ON_SALE: '在售',
  OFF_SALE: '停售',
  HIGH: '高风险',
  MEDIUM: '中风险',
  LOW: '低风险',
  CONTROLLED_ANSWER: '受控回答',
  REFERENCE: '引用关联',
  CANONICAL: '标准规格',
  COMPONENT: '组合组件',
  RUNNING: '运行中',
  PAUSED: '已暂停',
  ERROR: '异常',
  UNKNOWN: '状态未知',
}

export function displayStatus(value: string | null | undefined, empty = '未设置'): string {
  if (!value) return empty
  return STATUS_LABELS[value] || value
}

/**
 * A providers may serialize a pass rate as a fraction (0..1) or as an
 * already-percent value. Keep the transport value unchanged and normalize
 * only its operator-facing label.
 */
export function displayPassRate(value: number): string {
  const percentage = value >= 0 && value <= 1 ? value * 100 : value
  return `${Number(percentage.toFixed(2))}%`
}
