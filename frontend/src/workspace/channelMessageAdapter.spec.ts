import { describe, expect, it } from 'vitest'

import { MockChannelMessageAdapter } from './channelMessageAdapter'

describe('MockChannelMessageAdapter', () => {
  it('provides de-identified in-memory conversations without a real channel', async () => {
    const adapter = new MockChannelMessageAdapter()
    const conversations = await adapter.listConversations()

    expect(conversations).toHaveLength(2)
    expect(conversations.every((item) => item.source === 'MOCK')).toBe(true)
    expect(JSON.stringify(conversations)).not.toContain('PDD')
  })

  it('accepts a simulated new message for the selected conversation', async () => {
    const adapter = new MockChannelMessageAdapter()
    const message = await adapter.receiveMockMessage('mock-conversation-age', '还有其他注意事项吗？')

    expect(message).toMatchObject({
      conversationId: 'mock-conversation-age',
      content: '还有其他注意事项吗？',
      source: 'MOCK'
    })
  })
})

