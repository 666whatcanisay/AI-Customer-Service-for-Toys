(() => {
  'use strict'

  const CONTRACT_VERSION = 'synthetic-pdd-contract.v1'
  const STORE = Object.freeze({ platform: 'PDD', storeId: 'SIM-STORE-001', storeName: '仿真积木店客服账号' })
  const PRODUCT = Object.freeze({
    productId: 'SIM-PRODUCT-001',
    productName: '【仿真商品】香槟玫瑰积木花束礼盒',
    attributes: Object.freeze({ applicable_age: '8岁以上', category: '颗粒拼搭积木玩具' })
  })
  const SKU = Object.freeze({
    skuId: 'SIM-SKU-AGE8-CHAMPAGNE',
    skuName: '香槟玫瑰花束礼盒',
    attributes: Object.freeze({ color: '香槟玫瑰', package: '礼盒装', applicable_age: '8岁以上' })
  })
  const ORDER = Object.freeze({
    orderId: 'SIM-ORDER-20260807-001',
    orderStatus: '待付款',
    logisticsStatus: '尚未发货',
    aftersalesStatus: '无售后申请',
    paymentDataIncluded: false,
    addressDataIncluded: false
  })

  const seedConversations = () => ([
    {
      id: 'SIM-CONV-A01', uid: 'sim-customer-a01', customer: '测试买家 A01', unread: 1,
      messages: [
        { id: 'SIM-MSG-A01-001', role: 'customer', content: '你好，请问这款积木适合几岁？', at: '16:32', stamp: 1786091520000, sequence: 1 },
        { id: 'SIM-MSG-A01-002', role: 'operator', content: '您好，这款商品建议 8 岁以上使用。', at: '16:34', stamp: 1786091640000, sequence: 2 },
        { id: 'SIM-MSG-A01-003', role: 'customer', content: '需要家长陪同吗？', at: '16:35', stamp: 1786091700000, sequence: 3 }
      ]
    },
    {
      id: 'SIM-CONV-B02', uid: 'sim-customer-b02', customer: '测试买家 B02', unread: 0,
      messages: [{ id: 'SIM-MSG-B02-001', role: 'customer', content: '少了一个零件应该怎么处理？', at: '15:18', stamp: 1786087080000, sequence: 1 }]
    },
    {
      id: 'SIM-CONV-C03', uid: 'sim-customer-c03', customer: '测试买家 C03', unread: 0,
      messages: [{ id: 'SIM-MSG-C03-001', role: 'customer', content: '这个订单预计什么时候发货？', at: '14:06', stamp: 1786082760000, sequence: 1 }]
    }
  ])

  const scenarios = Object.freeze({
    age: ['请问这款积木适合几岁？'],
    sequence: ['你好', '我买的是花束积木', '孩子 8 岁，可以独立玩吗？'],
    missing: ['刚打开包装', '发现少了一个小零件', '应该怎么处理？'],
    logistics: ['订单已经下单了', '请问预计什么时候发货？']
  })

  let conversations = seedConversations()
  let activeId = conversations[0].id
  let sequence = 100

  const $ = (selector) => document.querySelector(selector)
  const messageList = $('#msgListContainer')
  const conversationList = $('#conversationList')
  const input = $('#replyTextarea')
  const send = $('.reply-footer .send-btn')
  const confirmLayer = $('#confirmLayer')
  const current = () => conversations.find((item) => item.id === activeId)
  const timeLabel = (date = new Date()) => date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  const nextMessageId = (conversation, role) => `SIM-MSG-${conversation.id.replace('SIM-CONV-', '')}-${role === 'customer' ? 'C' : 'O'}-${String(sequence++).padStart(4, '0')}`
  const event = (label) => {
    const li = document.createElement('li')
    li.textContent = `${timeLabel()} · ${label}`
    $('#eventLog').prepend(li)
    while ($('#eventLog').children.length > 8) $('#eventLog').lastElementChild.remove()
  }

  const renderMessages = () => {
    const active = current()
    messageList.replaceChildren(...active.messages.map((message) => {
      const li = document.createElement('li')
      li.className = 'onemsg'
      li.id = message.id
      li.dataset.synthetic = 'true'
      li.dataset.messageId = message.id
      li.dataset.senderRole = message.role
      li.dataset.timestamp = new Date(message.stamp).toISOString()
      li.dataset.sequence = String(message.sequence)
      const item = document.createElement('div')
      item.className = message.role === 'customer' ? 'buyer-item' : 'cs-item'
      const meta = document.createElement('p')
      meta.className = 'message-meta'
      meta.textContent = `${message.role === 'customer' ? active.customer : '仿真客服'} · ${message.at}`
      const content = document.createElement('div')
      content.className = 'msg-content-box'
      content.textContent = message.content
      item.append(meta, content)
      li.append(item)
      return li
    }))
    messageList.scrollTop = messageList.scrollHeight
  }

  const renderConversationList = () => {
    const query = $('#conversationSearch').value.trim().toLowerCase()
    const visible = conversations.filter((conversation) => !query || conversation.customer.toLowerCase().includes(query))
    conversationList.replaceChildren(...visible.map((conversation) => {
      const button = document.createElement('button')
      button.type = 'button'
      button.className = `conversation-item${conversation.id === activeId ? ' active' : ''}`
      button.dataset.conversationId = conversation.id
      button.innerHTML = `<span class="conversation-avatar">${conversation.customer.slice(-3)}</span><span><strong></strong><small></small></span><span><time>${conversation.messages.at(-1)?.at ?? ''}</time><b>${conversation.unread ? `${conversation.unread} 条新消息` : ''}</b></span>`
      button.querySelector('strong').textContent = conversation.customer
      button.querySelector('small').textContent = conversation.messages.at(-1)?.content ?? ''
      button.addEventListener('click', () => switchConversation(conversation.id))
      return button
    }))
    $('#unreadTotal').textContent = String(conversations.reduce((total, item) => total + item.unread, 0))
    $('#waitingCount').textContent = String(conversations.filter((item) => item.unread).length)
  }

  const renderActive = () => {
    const active = current()
    $('.chat-panel').setAttribute('currentuid', active.uid)
    $('.chat-panel').dataset.conversationId = active.id
    $('#activeCustomer').textContent = active.customer
    $('#activeConversation').textContent = active.id
    $('#confirmConversation').textContent = active.id
    $('#confirmCustomer').textContent = active.customer
    active.unread = 0
    renderMessages()
    renderConversationList()
  }

  const switchConversation = (conversationId) => {
    if (!conversations.some((item) => item.id === conversationId)) return false
    if (input.value.trim() && conversationId !== activeId) {
      input.value = ''
      $('#replyStatus').textContent = '会话变化，未发送内容已清空'
    }
    activeId = conversationId
    renderActive()
    event(`切换到 ${conversationId}`)
    document.dispatchEvent(new CustomEvent('pdd-simulator:conversation-changed', { detail: contract() }))
    return true
  }

  const appendMessage = (role, content, options = {}) => {
    const normalized = String(content || '').trim()
    if (!normalized) return null
    const target = options.conversationId ? conversations.find((item) => item.id === options.conversationId) : current()
    if (!target) return null
    const now = Date.now()
    const message = {
      id: nextMessageId(target, role), role, content: normalized,
      at: timeLabel(new Date(now)), stamp: now, sequence: target.messages.length + 1
    }
    target.messages.push(message)
    if (role === 'customer' && target.id !== activeId) target.unread += 1
    renderConversationList()
    if (target.id === activeId) renderMessages()
    const detail = { conversationId: target.id, customer: target.customer, message: { ...message }, synthetic: true }
    document.dispatchEvent(new CustomEvent('pdd-simulator:message', { detail }))
    event(`${role === 'customer' ? '客户消息' : '客服回复'} · ${target.id}`)
    return structuredClone(detail)
  }

  const pushCustomerSequence = async (messages, intervalMs = 650) => {
    const accepted = []
    for (const content of messages) {
      accepted.push(appendMessage('customer', content))
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
    return accepted
  }

  const contract = () => {
    const active = current()
    return structuredClone({
      schemaVersion: CONTRACT_VERSION,
      environment: 'SIMULATOR',
      syntheticOnly: true,
      realPlatformConnected: false,
      externalSendEnabled: false,
      pageState: 'CUSTOMER_SERVICE_READY',
      generatedAt: new Date().toISOString(),
      store: STORE,
      conversation: {
        conversationId: active.id,
        customerReference: active.uid,
        customerLabel: active.customer
      },
      product: PRODUCT,
      sku: SKU,
      order: ORDER,
      messages: active.messages.map((message) => ({
        externalMessageId: message.id,
        sender: message.role,
        content: message.content,
        timestamp: new Date(message.stamp).toISOString(),
        sequence: message.sequence
      }))
    })
  }

  const snapshot = () => ({ ...contract(), simulatorVersion: '1.1', replyInputLength: input.value.length })
  const openConfirmation = () => {
    const reply = input.value.trim()
    if (!reply) { $('#replyStatus').textContent = '回复不能为空'; input.focus(); return }
    $('#confirmReply').textContent = reply
    $('#confirmConversation').textContent = current().id
    $('#confirmCustomer').textContent = current().customer
    confirmLayer.hidden = false
    $('#confirmSend').focus()
  }
  const closeConfirmation = () => { confirmLayer.hidden = true; input.focus() }
  const confirmSyntheticSend = () => {
    const expectedConversation = $('#confirmConversation').textContent
    const expectedCustomer = $('#confirmCustomer').textContent
    if (current().id !== expectedConversation || current().customer !== expectedCustomer) {
      closeConfirmation(); input.value = ''
      $('#replyStatus').textContent = '会话发生变化，已拒绝仿真发送'
      event('发送被拒绝：会话变化')
      return
    }
    const content = input.value.trim()
    appendMessage('operator', content)
    input.value = ''
    closeConfirmation()
    $('#replyStatus').textContent = '仿真发送成功（无外部副作用）'
    event('生成仿真 Receipt：SUCCESS')
  }

  document.querySelectorAll('[data-scenario]').forEach((button) => button.addEventListener('click', () => void pushCustomerSequence(scenarios[button.dataset.scenario])))
  $('#conversationSearch').addEventListener('input', renderConversationList)
  send.addEventListener('click', openConfirmation)
  $('#cancelSend').addEventListener('click', closeConfirmation)
  $('#confirmSend').addEventListener('click', confirmSyntheticSend)
  $('#resetSimulator').addEventListener('click', () => {
    conversations = seedConversations(); activeId = conversations[0].id; sequence = 100
    input.value = ''; $('#eventLog').replaceChildren(); renderActive(); event('仿真环境已重置')
  })

  window.__PDD_SIMULATOR__ = Object.freeze({
    version: '1.1', contractVersion: CONTRACT_VERSION, syntheticOnly: true,
    pushCustomerMessage: (content, conversationId) => appendMessage('customer', content, { conversationId }),
    pushCustomerSequence, switchConversation, contract, snapshot,
    reset: () => $('#resetSimulator').click()
  })
  renderActive()
  event('本地仿真工作台启动')
})()
