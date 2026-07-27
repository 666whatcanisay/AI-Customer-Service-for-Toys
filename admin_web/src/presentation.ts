/** Chinese business-facing labels for controlled platform states.
 *
 * API enum values remain stable in transport.  This mapping is only the
 * presentation layer and keeps operational pages from exposing implementation
 * codes as their primary language.
 */
const labels: Record<string, string> = {
  NEW: '新建',
  REVIEWING: '审核中',
  APPROVED: '已通过',
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
  FACT_ERROR: '事实错误',
  MISSING_INFO: '信息缺失',
  STYLE_ISSUE: '表达问题',
  RISK_ISSUE: '风险问题',
  OTHER: '其他问题',
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
  IMPORTED_TEST_ONLY: '已导入（测试）',
  NEEDS_PRODUCT_IMPORT: '待导入商品',
  NEEDS_KNOWLEDGE: '待维护知识',
  OBSERVABLE: '可观察',
  PENDING: '待处理',
  PENDING_REVIEW: '待审核',
  ON_SALE: '在售',
  OFF_SALE: '停售',
  REFERENCE: '引用关联',
  CANONICAL: '标准规格',
  COMPONENT: '组合组件',
  CONTROLLED_ANSWER: '受控回答',
  HIGH: '高风险',
  MEDIUM: '中风险',
  LOW: '低风险',
  ADMIN: '管理员',
  OPERATOR: '运营',
  SUPPORT: '客服',
  SUCCESS: '成功',
  REJECTED_OPERATION: '已拒绝',
  UNKNOWN: '状态未知',
}

export function displayStatus(value: string | null | undefined, empty = '未设置'): string {
  if (!value) return empty
  return labels[value] || value
}

export function displayAuditAction(value: string): string {
  return {
    PILOT_STORE_CREATE: '创建试运行店铺',
    PRODUCT_IMPORT_PREFLIGHT: '商品导入预检',
    PRODUCT_IMPORT_CREATE: '同步商品数据',
    KNOWLEDGE_PACKAGE_IMPORT: '同步知识包',
    EXPERIENCE_CASE_VIEW: '查看客服案例',
    EXPERIENCE_CASE_REVIEW: '审核客服案例',
    EXPERIENCE_CASE_EVALUATION_VIEW: '查看 AI 评测',
    AI_FEEDBACK_CONFIRM: '确认 AI 问题',
    AI_FEEDBACK_ANALYSIS_VIEW: '查看优化建议',
    AUDIT_LOG_VIEW: '查看审计记录',
  }[value] || '试运行操作'
}

export function displayAuditResource(value: string): string {
  return {
    PILOT_STORE: '试运行店铺',
    PRODUCT_IMPORT: '商品同步',
    KNOWLEDGE_PACKAGE: '知识包',
    EXPERIENCE_CASE: '客服案例',
    AI_FEEDBACK: 'AI 问题',
    AI_FEEDBACK_ANALYSIS: '优化建议',
    AUDIT_EVENT: '审计记录',
  }[value] || '运营资源'
}

export function displayAuditReason(value: string): string {
  return {
    DAILY_OPERATIONS: '日常运营',
    CASE_REVIEW: '案例审核',
    KNOWLEDGE_MAINTENANCE: '知识维护',
    GOVERNANCE_REVIEW: '治理检查',
    UNSPECIFIED: '未说明',
  }[value] || '未说明'
}

export function displayCapability(value: string): string {
  return {
    'operations.read': '查看运营总览',
    'sensitive-content.read': '查看受控内容',
    'store.write': '维护试运行店铺',
    'knowledge.import': '同步知识数据',
    'case.review': '审核客服案例',
    'feedback.confirm': '确认 AI 问题',
    'audit.read': '查看审计记录',
  }[value] || '试运行能力'
}
