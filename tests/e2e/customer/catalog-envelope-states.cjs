const { chromium } = require('playwright')
const { assert } = require('../utils.cjs')

const schemaVersion = 'pilot-business-catalog.v1.1'
const catalogWarning = {
  code: 'CUSTOMER_SERVICE_SOURCE_INVALID',
  entity_type: 'PRODUCT',
  count: 1,
  message: 'One source row was isolated.'
}
const store = {
  entity_type: 'STORE',
  tenant_id: 'TENANT-R006-E2E',
  platform: 'demo',
  store_code: 'R006-E2E-STORE',
  store_name: 'R006 Envelope Test Store',
  data_source: 'PILOT',
  customer_service_status: 'ENABLED',
  allow_auto_send: false
}
const product = {
  entity_type: 'PRODUCT',
  product_id: 'R006-E2E-PRODUCT',
  platform: 'demo',
  store_code: 'R006-E2E-STORE',
  product_name_official: 'R006 Envelope Test Product',
  product_name_display: 'R006 Envelope Test Product',
  sales_status: 'ON_SALE',
  age_min: null,
  age_max: null,
  safety_summary: null,
  knowledge_status: 'APPROVED',
  data_source: 'PILOT',
  customer_service_status: 'ENABLED'
}

function envelope(items, resultStatus = 'COMPLETE', warnings = []) {
  return {
    schema_version: schemaVersion,
    result_status: resultStatus,
    items,
    total: items.length,
    warnings
  }
}

function safeCustomerUrl() {
  const url = new URL(process.env.R006_B_URL || 'http://127.0.0.1:15183')
  assert.equal(url.hostname, '127.0.0.1', 'R006 Envelope E2E 只允许本机隔离环境')
  assert.notEqual(url.port, '5173', 'R006 Envelope E2E 禁止使用正式B端口5173')
  return url.origin
}

async function fulfillJson(route, body) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body)
  })
}

async function runScenario(browser, name, productsEnvelope, verify) {
  const context = await browser.newContext()
  await context.addInitScript(() => {
    localStorage.setItem('mumu-customer-workspace:pilot-guide-seen', 'true')
    localStorage.setItem('mumu-customer-workspace:tester-identity', JSON.stringify({
      reporterId: 'TESTER-R006-ENVELOPE',
      reporterName: 'R006 E2E',
      defaultStoreCode: ''
    }))
  })
  const page = await context.newPage()
  try {
    await page.route('**/rag-api/api/health', (route) => fulfillJson(route, {
      status: 'ok',
      ready: true,
      model_configured: true,
      vector_store: 'ready',
      document_count: 1
    }))
    await page.route('**/platform-api/health', (route) => fulfillJson(route, {
      status: 'ok',
      service: 'platform'
    }))
    await page.route('**/platform-api/api/v1/customer-service/catalog/stores', (route) =>
      fulfillJson(route, envelope([store])))
    await page.route('**/platform-api/api/v1/customer-service/catalog/products?*', (route) =>
      fulfillJson(route, productsEnvelope))
    await page.route('**/platform-api/api/v1/customer-service/catalog/products/*/skus', (route) =>
      fulfillJson(route, envelope([])))

    await page.goto(`${safeCustomerUrl()}/ai-chat`, { waitUntil: 'networkidle' })
    await page.getByTestId('store-select').click()
    const productResponse = page.waitForResponse((response) =>
      response.url().includes('/customer-service/catalog/products?'))
    await page.locator('.el-select-dropdown__item').filter({
      hasText: 'R006 Envelope Test Store'
    }).last().click()
    await productResponse
    await verify(page)
    return { name, status: 'PASS' }
  } finally {
    await context.close()
  }
}

async function visibleProductEmptyState(page) {
  await page.getByTestId('product-select').click()
  return page.locator('.el-select-dropdown__empty:visible').last()
}

async function runCatalogEnvelopeStates(browser) {
  const results = []
  results.push(await runScenario(browser, 'COMPLETE_ZERO', envelope([]), async (page) => {
    const guidance = page.getByTestId('catalog-guidance')
    assert.match(await guidance.innerText(), /该店铺暂无可用于 AI 建议的商品/)
    const emptyState = await visibleProductEmptyState(page)
    assert.doesNotMatch(await emptyState.innerText(), /No data/)
  }))
  results.push(await runScenario(
    browser,
    'PARTIAL_ZERO',
    envelope([], 'PARTIAL', [catalogWarning]),
    async (page) => {
      const guidanceText = await page.getByTestId('catalog-guidance').innerText()
      assert.match(guidanceText, /商品目录暂时异常，请联系运营处理。/)
      assert.doesNotMatch(guidanceText, /暂无可用于/)
      const emptyState = await visibleProductEmptyState(page)
      const emptyStateText = await emptyState.innerText()
      assert.match(emptyStateText, /商品目录暂时异常，请联系运营处理。/)
      assert.doesNotMatch(emptyStateText, /No data/)
    }
  ))
  results.push(await runScenario(
    browser,
    'PARTIAL_WITH_ITEMS',
    envelope([product], 'PARTIAL', [catalogWarning]),
    async (page) => {
      const guidanceText = await page.getByTestId('catalog-guidance').innerText()
      assert.match(guidanceText, /商品目录部分异常/)
      assert.match(guidanceText, /已显示有效商品/)
      await page.getByTestId('product-select').click()
      await page.locator('.el-select-dropdown__item:visible').filter({
        hasText: 'R006 Envelope Test Product'
      }).last().waitFor()
    }
  ))
  return results
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || chromium.executablePath()
  })
  try {
    console.log(JSON.stringify(await runCatalogEnvelopeStates(browser), null, 2))
  } finally {
    await browser.close()
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.stack || String(error))
    process.exitCode = 1
  })
}

module.exports = { runCatalogEnvelopeStates }
