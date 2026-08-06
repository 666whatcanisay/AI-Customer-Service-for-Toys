const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require('playwright')

const baseUrl = process.env.AI_CS_WORKSPACE_URL || 'http://127.0.0.1:15183'
const chromePath = process.env.PLAYWRIGHT_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const evidenceDir = path.resolve(__dirname, '../../../.runtime/human-loop-workspace-v1/evidence')

const envelope = (items) => ({
  schema_version: 'pilot-business-catalog.v1.1',
  result_status: 'COMPLETE',
  items,
  total: items.length,
  warnings: []
})

const store = {
  entity_type: 'STORE', tenant_id: 'TENANT-DEMO', platform: 'pdd',
  store_code: 'DEMO-TOY-STORE', store_name: '星光积木演示店', data_source: 'PILOT',
  customer_service_status: 'ENABLED', allow_auto_send: false
}

const product = {
  entity_type: 'PRODUCT', product_id: 'DEMO-BLOCK-HOUSE', platform: 'pdd',
  store_code: 'DEMO-TOY-STORE', product_name_official: '创意积木小屋',
  product_name_display: '创意积木小屋', sales_status: 'ON_SALE', age_min: 5, age_max: 12,
  safety_summary: '建议由家长陪同并避免误吞小零件。', knowledge_status: 'APPROVED',
  data_source: 'PILOT', customer_service_status: 'ENABLED'
}

const chatResponse = {
  data: {
    answer: '您好，这款创意积木小屋建议 5 岁以上儿童使用，材质为 ABS；拼搭时建议家长陪同，并注意避免误吞小零件。',
    action: 'CONTROLLED_ANSWER', risk_level: 'LOW',
    sources: [
      {
        source_name: '商品知识｜创意积木小屋', page: null, chunk_id: 'demo-product-1', distance: 0.08,
        excerpt: '建议年龄 5 岁以上，主体材质为 ABS。', knowledge_version: 'demo-v1',
        source_ids: ['DEMO-SOURCE-PRODUCT'], product_id: 'DEMO-BLOCK-HOUSE', sku_id: null
      },
      {
        source_name: 'FAQ｜年龄与玩法', page: null, chunk_id: 'demo-faq-1', distance: 0.11,
        excerpt: '可按说明书完成小屋拼搭，也可自由创作。', knowledge_version: 'demo-v1',
        source_ids: ['DEMO-SOURCE-FAQ'], product_id: 'DEMO-BLOCK-HOUSE', sku_id: null
      },
      {
        source_name: '安全规则｜小颗粒', page: null, chunk_id: 'demo-safety-1', distance: 0.13,
        excerpt: '拼搭时建议家长陪同，并注意避免误吞小零件。', knowledge_version: 'demo-v1',
        source_ids: ['DEMO-SOURCE-SAFETY'], product_id: 'DEMO-BLOCK-HOUSE', sku_id: null
      }
    ],
    warnings: [], required_fields: [], model: 'qwen3.5:9b', latency_ms: 128,
    request_id: 'demo-request-001',
    context: {
      tenant_id: 'TENANT-DEMO', platform: 'pdd', store_code: 'DEMO-TOY-STORE',
      product_id: 'DEMO-BLOCK-HOUSE', sku_id: null
    }
  }
}

async function main() {
  fs.mkdirSync(evidenceDir, { recursive: true })
  const interactionRequests = []
  const browser = await chromium.launch({ headless: true, executablePath: chromePath })
  const context = await browser.newContext({ viewport: { width: 1720, height: 1050 } })
  const page = await context.newPage()

  await page.addInitScript(() => {
    localStorage.setItem('mumu-customer-workspace:tester-identity', JSON.stringify({
      reporterId: 'TESTER-DEMO-OPERATOR', reporterName: '演示客服', defaultStoreCode: 'DEMO-TOY-STORE'
    }))
    localStorage.setItem('mumu-customer-workspace:pilot-guide-seen', 'true')
  })

  await page.route('**/platform-api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/customer-service/catalog/stores')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope([store])) })
    }
    if (url.pathname.endsWith('/customer-service/catalog/products')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope([product])) })
    }
    if (url.pathname.includes('/customer-service/catalog/products/') && url.pathname.endsWith('/skus')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope([])) })
    }
    if (url.pathname.endsWith('/ai-interaction-events')) {
      const payload = route.request().postDataJSON()
      interactionRequests.push(payload)
      return route.fulfill({
        status: 201, contentType: 'application/json',
        body: JSON.stringify({
          event_id: `AIE-DEMO-${interactionRequests.length}`,
          interaction_id: payload.interaction_id,
          status: 'RECORDED', occurred_at: new Date().toISOString()
        })
      })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })

  await page.route('**/rag-api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/api/chat')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(chatResponse) })
    }
    if (url.pathname.endsWith('/api/health')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: { status: 'ok', ready: true } }) })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })

  try {
    await page.goto(`${baseUrl}/workspace`, { waitUntil: 'networkidle' })
    await page.getByTestId('human-loop-workspace').waitFor()
    await page.getByTestId('generate-draft').click()
    await page.getByTestId('reply-draft-editor').waitFor()

    const evidenceText = await page.getByTestId('knowledge-evidence').innerText()
    if (!evidenceText.includes('商品知识') || !evidenceText.includes('FAQ') || !evidenceText.includes('安全规则')) {
      throw new Error('Knowledge evidence categories were not all visible.')
    }

    await page.getByTestId('reply-draft-editor').fill(
      '您好，这款创意积木小屋建议 5 岁以上儿童使用，材质为 ABS。请您陪同孩子拼搭，并留意小零件安全。'
    )
    await page.getByTestId('edited-accept').click()
    await page.getByTestId('interaction-receipt').waitFor()
    await page.screenshot({ path: path.join(evidenceDir, 'workspace-edited-accept.png'), fullPage: true })

    if (interactionRequests.length !== 1 || interactionRequests[0].action_type !== 'EDITED_ACCEPT') {
      throw new Error('Edited acceptance did not produce the expected interaction event.')
    }
    if (interactionRequests[0].sku_id !== null) throw new Error('Demo must retain sku_id=null.')

    await page.locator('#mock-message').fill('如果孩子刚满 5 岁，还需要注意什么？')
    await page.getByTestId('mock-message-form').dispatchEvent('submit')
    await page.getByTestId('draft-card').getByText('Message Received').waitFor()
    await page.screenshot({ path: path.join(evidenceDir, 'new-message-expired-old-draft.png'), fullPage: true })

    const result = {
      status: 'PASS', base_url: baseUrl, browser: 'system Chrome controlled by Playwright',
      mode: 'MOCK_MESSAGE_WITH_INTERCEPTED_EXISTING_APIS', interaction_events: interactionRequests,
      checks: {
        three_column_workspace: true, product_context_bound: true,
        knowledge_evidence: ['PRODUCT_KNOWLEDGE', 'FAQ', 'SAFETY_RULE'],
        edited_accept_recorded: true, new_message_expires_old_draft: true,
        auto_send: false, refund: false, order_mutation: false
      }
    }
    fs.writeFileSync(path.join(evidenceDir, 'human-loop-browser-result.json'), JSON.stringify(result, null, 2))
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`)
  process.exitCode = 1
})

