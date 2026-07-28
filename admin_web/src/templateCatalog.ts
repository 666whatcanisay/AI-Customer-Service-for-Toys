import { productSkuTemplateUrl } from './api/client'

export interface DownloadTemplate {
  key: string
  title: string
  filename: string
  href: string
  applicable: string
  required: string
  excluded: string
}

function downloadableText(text: string, mimeType: string): string {
  return `data:${mimeType};charset=utf-8,${encodeURIComponent(`\uFEFF${text}`)}`
}

function csv(headers: string[], sample: string[]): string {
  return downloadableText(`${headers.join(',')}\n${sample.join(',')}\n`, 'text/csv')
}

/**
 * The product/SKU workbook is the controlled backend template.  The three
 * smaller CSV templates are intentionally minimal guidance files: they are
 * not import endpoints and cannot publish, train, or change knowledge by
 * themselves.
 */
export const testDataTemplates: DownloadTemplate[] = [
  {
    key: 'product-sku',
    title: '商品与 SKU 模板',
    filename: '商品与SKU资料模板.xlsx',
    href: productSkuTemplateUrl(),
    applicable: '用于准备商品、SKU、适用年龄、材质和来源信息。',
    required: '店铺编码、商品名称、商品编码或平台商品 ID、SKU 名称、SKU 编码或平台 SKU ID、来源名称。',
    excluded: '下载或填写模板不会自动发布知识、修改订单或发送客户消息。',
  },
  {
    key: 'faq',
    title: 'FAQ 模板',
    filename: 'FAQ填写模板.csv',
    href: csv(['店铺编码', '商品编码', '标准问题', '建议回复', '风险等级', '来源编号'], ['STORE-001', 'PRODUCT-001', '适用年龄是多少？', '请以商品说明为准。', '低', 'SRC-001']),
    applicable: '用于整理运营希望补充的常见问答。',
    required: '店铺编码、标准问题、建议回复、来源编号。',
    excluded: '该模板仅供填写和预检准备，不会自动导入或自动回复。',
  },
  {
    key: 'safety-rule',
    title: '安全规则模板',
    filename: '安全规则填写模板.csv',
    href: csv(['店铺编码', '适用场景', '风险等级', '允许动作', '禁止表述', '来源编号'], ['STORE-001', '小零件咨询', '高', '建议人工核对', '不得承诺绝对安全', 'SRC-001']),
    applicable: '用于梳理客服回答必须遵守的安全边界。',
    required: '店铺编码、适用场景、风险等级、允许动作、禁止表述、来源编号。',
    excluded: '填写安全规则不会自动发布到线上，也不会更改提示词。',
  },
  {
    key: 'source-evidence',
    title: '来源证据模板',
    filename: '来源证据填写模板.csv',
    href: csv(['来源编号', '文件名称', '关联商品编码', '关联SKU编码', '证据说明', '校验值'], ['SRC-001', '产品说明书.pdf', 'PRODUCT-001', 'SKU-001', '适用年龄依据', '待填写']),
    applicable: '用于登记资料来源及其与商品、SKU 的关联。',
    required: '来源编号、文件名称、证据说明；关联商品或 SKU 按实际情况填写。',
    excluded: '模板不上传原始文件，不会把资料自动提供给外部系统。',
  },
]

export const testDataGuide = {
  filename: '测试数据包使用说明.md',
  href: downloadableText(
    '# 测试数据包使用说明\n\n1. 下载与目标一致的模板。\n2. 按示例填写，保留字段名称。\n3. 在运营中心上传并完成预检。\n4. 预检通过后再正式导入。\n\n限制：仅用于测试/试运行；不会自动发布知识、自动训练、修改提示词、发送客户消息或写入 ERP。\n',
    'text/markdown',
  ),
}
