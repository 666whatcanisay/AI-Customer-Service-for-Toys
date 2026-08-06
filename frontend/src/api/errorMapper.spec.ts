import { describe, expect, it } from 'vitest'

import { RagAdapterError } from './ragAdapter'
import { PlatformAdapterError } from './platformAdapter'
import { toPlatformClientError, toRagClientError } from './errorMapper'

const axiosError = (status: number, message: string) => ({
  isAxiosError: true,
  message: `Request failed with status code ${status}`,
  response: { status, data: { error: { message } } },
})

describe('employee-facing error messages', () => {
  it('does not expose raw server or transport errors', () => {
    const platform = toPlatformClientError(axiosError(500, 'Internal server error.'))
    const rag = toRagClientError(axiosError(503, 'RAG API unavailable.'))

    expect(platform.message).toBe('店铺与商品服务暂时不可用，请联系管理员')
    expect(rag.message).toBe('AI 服务暂时不可用，请稍后重试；如持续失败，请联系管理员')
    expect(`${platform.message}${rag.message}`).not.toMatch(/500|503|RAG|Internal|Request failed/)
  })

  it('hides adapter contract diagnostics from ordinary employees', () => {
    expect(toPlatformClientError(new PlatformAdapterError('C 目录字段 product_id 类型无效')).message)
      .toBe('店铺与商品数据无法识别，请联系管理员')
    expect(toRagClientError(new RagAdapterError('API response context_id invalid')).message)
      .toBe('AI 服务返回的数据无法识别，请联系管理员')
  })
})
