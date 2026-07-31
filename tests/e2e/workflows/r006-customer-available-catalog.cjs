const { chromium } = require('playwright')
const { assert, screenshot } = require('../utils.cjs')

function safeUrl(name, raw, forbiddenPort) {
  const url = new URL(raw)
  assert.equal(url.hostname, '127.0.0.1', `${name} 只允许本机隔离环境`)
  assert.notEqual(url.port, forbiddenPort, `${name} 禁止使用正式端口 ${forbiddenPort}`)
  return url.origin
}

async function json(response, label) {
  assert.ok(response.ok(), `${label} HTTP ${response.status()}`)
  return response.json()
}

async function selectElementPlusOption(page, comboIndex, text) {
  const combo = page.getByRole('combobox').nth(comboIndex)
  await combo.click()
  const option = page.locator('.el-select-dropdown__item').filter({ hasText: text }).last()
  await option.waitFor()
  await option.click()
}

async function availableOptionTexts(page, comboIndex) {
  await page.getByRole('combobox').nth(comboIndex).click()
  await page.locator('.el-select-dropdown__item').first().waitFor()
  return page.locator('.el-select-dropdown__item').allTextContents()
}

async function navigateSpa(page, baseUrl, route) {
  if (new URL(page.url()).origin !== baseUrl) {
    await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' })
  }
  await page.evaluate((path) => {
    history.pushState({}, '', path)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, route)
}

async function closeFirstRunDialogs(page) {
  const identityDialog = page.getByTestId('identity-dialog')
  if (await identityDialog.isVisible().catch(() => false)) {
    await page.getByTestId('identity-name').fill('R006 Test Agent')
    await page.getByTestId('identity-save').click()
  }
  const pilotGuide = page.getByTestId('pilot-guide-dialog')
  if (await pilotGuide.isVisible().catch(() => false)) {
    await page.getByTestId('pilot-guide-start').click()
  }
}

async function runR006CustomerAvailableCatalog(browser) {
  const platformUrl = safeUrl(
    'R006_PLATFORM_URL',
    process.env.R006_PLATFORM_URL || 'http://127.0.0.1:19021',
    '8011'
  )
  const bUrl = safeUrl(
    'R006_B_URL',
    process.env.R006_B_URL || 'http://127.0.0.1:15183',
    '5173'
  )
  const adminUrl = safeUrl(
    'R006_ADMIN_URL',
    process.env.R006_ADMIN_URL || 'http://127.0.0.1:15184',
    '5174'
  )
  const context = await browser.newContext()
  const page = await context.newPage()
  const evidence = { platformUrl, bUrl, adminUrl }
  try {
    const operationStores = await json(
      await context.request.get(`${platformUrl}/api/v1/admin/operations/stores`),
      'operation stores'
    )
    const pilotStore = operationStores.items.find(
      (item) => item.store_name === 'Pilot Store Pending'
    )
    assert.ok(pilotStore, '未找到隔离验收 PILOT 店铺')
    const resetHeaders = { 'Idempotency-Key': `r006-reset-${Date.now()}` }
    await json(
      await context.request.put(
        `${platformUrl}/api/v1/admin/operations/products/PILOT-PRODUCT/customer-service-status`,
        {
          headers: resetHeaders,
          data: {
            customer_service_status: 'DISABLED',
            confirmed_by: 'R006_E2E_RESET',
            confirmation_note: 'Reset isolated acceptance fixture before browser run'
          }
        }
      ),
      'reset Product status'
    )
    await json(
      await context.request.put(
        `${platformUrl}/api/v1/admin/operations/stores/${pilotStore.store_ref}/customer-service-status`,
        {
          headers: { 'Idempotency-Key': `r006-reset-store-${Date.now()}` },
          data: {
            customer_service_status: 'DISABLED',
            confirmed_by: 'R006_E2E_RESET',
            confirmation_note: 'Reset isolated acceptance fixture before browser run'
          }
        }
      ),
      'reset Store status'
    )
    const storesBefore = await json(
      await context.request.get(`${platformUrl}/api/v1/customer-service/catalog/stores`),
      'initial stores'
    )
    assert.equal(storesBefore.schema_version, 'pilot-business-catalog.v1.1')
    assert.equal(storesBefore.result_status, 'PARTIAL')
    assert.deepEqual(storesBefore.items.map((item) => item.store_code), ['TEST-STORE'])
    assert.equal(storesBefore.warnings[0].code, 'CUSTOMER_SERVICE_SOURCE_UNKNOWN')
    evidence.initialProjection = storesBefore

    const testProducts = await json(
      await context.request.get(
        `${platformUrl}/api/v1/customer-service/catalog/products?store_code=TEST-STORE`
      ),
      'TEST products'
    )
    assert.equal(testProducts.result_status, 'PARTIAL')
    assert.deepEqual(testProducts.items.map((item) => item.product_id), ['TEST-PRODUCT'])
    assert.ok(!('publishable' in testProducts.items[0]), 'B projection must not expose publishable')

    const testSkus = await json(
      await context.request.get(
        `${platformUrl}/api/v1/customer-service/catalog/products/TEST-PRODUCT/skus`
      ),
      'TEST skus'
    )
    assert.equal(testSkus.result_status, 'PARTIAL')
    assert.deepEqual(testSkus.items.map((item) => item.sku_id), ['TEST-SKU'])

    await navigateSpa(page, bUrl, '/ai-chat')
    await page.getByRole('heading', { name: '跟着步骤，生成一条客服建议' }).waitFor()
    await closeFirstRunDialogs(page)
    const initialStoreOptions = await availableOptionTexts(page, 0)
    assert.ok(initialStoreOptions.some((text) => text.includes('Legacy Test Store')))
    assert.ok(!initialStoreOptions.some((text) => text.includes('Pilot Store Pending')))
    assert.ok(!initialStoreOptions.some((text) => text.includes('Quarantined Store')))
    await page.keyboard.press('Escape')
    await selectElementPlusOption(page, 0, 'Legacy Test Store')
    const testProductOptions = await availableOptionTexts(page, 1)
    assert.ok(testProductOptions.some((text) => text.includes('Available Blocks')))
    assert.ok(!testProductOptions.some((text) => text.includes('Broken Product')))
    await page.keyboard.press('Escape')
    evidence.initialB = await screenshot(page, 'r006-b-initial-test-catalog')

    await navigateSpa(page, adminUrl, '/store-management')
    await page.getByRole('heading', { name: '店铺管理' }).waitFor()
    await page.locator('.operator-field input').fill('R006验收运营')
    const pilotRow = page.locator('tbody tr').filter({ hasText: 'Pilot Store Pending' })
    await pilotRow.getByRole('button', { name: '启用客服使用' }).click()
    await pilotRow.getByRole('button', { name: '关闭客服使用' }).waitFor()
    await page.getByText(/ACT-/).first().waitFor()
    evidence.storeActivation = await screenshot(page, 'r006-admin-store-activation')

    await navigateSpa(page, adminUrl, '/knowledge-center/products/PILOT-PRODUCT')
    await page.getByRole('heading', { name: 'Pending Product', level: 1 }).waitFor()
    await page.locator('.activation-panel input').fill('R006验收运营')
    await page.locator('.activation-panel').getByRole('button', {
      name: '启用客服使用'
    }).click()
    await page.locator('.activation-panel').getByRole('button', {
      name: '关闭客服使用'
    }).waitFor()
    await page.getByText(/ACT-/).first().waitFor()
    evidence.productActivation = await screenshot(page, 'r006-admin-product-activation')

    const pilotProducts = await json(
      await context.request.get(
        `${platformUrl}/api/v1/customer-service/catalog/products?store_code=PILOT-STORE`
      ),
      'activated PILOT products'
    )
    assert.deepEqual(pilotProducts.items.map((item) => item.product_id), ['PILOT-PRODUCT'])

    await navigateSpa(page, bUrl, '/ai-chat')
    const activatedStoreOptions = await availableOptionTexts(page, 0)
    assert.ok(activatedStoreOptions.some((text) => text.includes('Pilot Store Pending')))
    await page.keyboard.press('Escape')
    await selectElementPlusOption(page, 0, 'Pilot Store Pending')
    const activatedProductOptions = await availableOptionTexts(page, 1)
    assert.ok(activatedProductOptions.some((text) => text.includes('Pending Product')))
    await page.keyboard.press('Escape')
    evidence.activatedB = await screenshot(page, 'r006-b-activated-pilot-catalog')

    await navigateSpa(page, adminUrl, '/store-management')
    await page.locator('.operator-field input').fill('R006验收运营')
    const enabledPilotRow = page.locator('tbody tr').filter({ hasText: 'Pilot Store Pending' })
    await enabledPilotRow.getByRole('button', { name: '关闭客服使用' }).click()
    await enabledPilotRow.getByRole('button', { name: '启用客服使用' }).waitFor()
    const hiddenProducts = await json(
      await context.request.get(
        `${platformUrl}/api/v1/customer-service/catalog/products?store_code=PILOT-STORE`
      ),
      'disabled Store products'
    )
    assert.equal(hiddenProducts.total, 0)
    const productDetail = await json(
      await context.request.get(
        `${platformUrl}/api/v1/admin/product-knowledge/products/PILOT-PRODUCT`
      ),
      'Product state after Store disable'
    )
    assert.equal(productDetail.product.customer_service_status, 'ENABLED')

    await page.locator('.operator-field input').fill('R006验收运营')
    await enabledPilotRow.getByRole('button', { name: '启用客服使用' }).click()
    await enabledPilotRow.getByRole('button', { name: '关闭客服使用' }).waitFor()
    const receiptHistory = await json(
      await context.request.get(
        `${platformUrl}/api/v1/admin/operations/activation-receipts` +
        `?entity_type=STORE&entity_ref=${pilotStore.store_ref}&page=1&size=20`
      ),
      'Store receipt history'
    )
    assert.ok(receiptHistory.total >= 3)
    evidence.receiptCount = receiptHistory.total
    return evidence
  } finally {
    await context.close()
  }
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || chromium.executablePath()
  })
  try {
    const evidence = await runR006CustomerAvailableCatalog(browser)
    console.log(JSON.stringify({ status: 'PASS', evidence }, null, 2))
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

module.exports = { runR006CustomerAvailableCatalog }
