const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const { chromium } = require('playwright')

const TARGET = {
  storeName: process.env.R003_STORE_NAME || '玩具乐园积木店',
  storeCode: process.env.R003_STORE_CODE || 'c-store-6639df2982014226',
  productId:
    process.env.R003_PRODUCT_ID || 'C-PRODUCT-747f463efb104440a6bdda416cd072eb',
  productName:
    process.env.R003_PRODUCT_NAME || '50盒【随机款式】科教机构优选',
}

function argument(name, fallback) {
  const prefix = `--${name}=`
  const value = process.argv.find((item) => item.startsWith(prefix))
  return value ? value.slice(prefix.length) : fallback
}

function normalizedOrigin(name, raw, expectedPort) {
  const url = new URL(raw)
  assert.equal(url.protocol, 'http:', `${name} 必须使用当前内网 HTTP 入口`)
  assert.equal(url.port, expectedPort, `${name} 必须指向标准端口 ${expectedPort}`)
  return url.origin
}

function resolveBrowserExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    chromium.executablePath(),
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ].filter(Boolean)
  const executable = candidates.find((candidate) => fs.existsSync(candidate))
  assert.ok(
    executable,
    '未找到可用 Chromium/Chrome。请设置 PLAYWRIGHT_CHROMIUM_EXECUTABLE。',
  )
  return executable
}

function writeJson(target, value) {
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
}

async function json(response, label) {
  assert.ok(response.ok(), `${label} HTTP ${response.status()}`)
  return response.json()
}

async function openElementPlusOptions(page, testId) {
  const select = page.getByTestId(testId)
  await select.click()
  const dropdown = page.locator('.el-select-dropdown:visible').last()
  await dropdown.waitFor({ state: 'visible', timeout: 10_000 })
  const options = dropdown.locator('.el-select-dropdown__item:not(.is-disabled)')
  await options.first().waitFor({ state: 'visible', timeout: 10_000 })
  return { select, dropdown, options }
}

async function optionTexts(page, testId) {
  const { dropdown, options } = await openElementPlusOptions(page, testId)
  const texts = (await options.allTextContents()).map((item) => item.trim()).filter(Boolean)
  await page.keyboard.press('Escape')
  await dropdown.waitFor({ state: 'hidden', timeout: 5_000 }).catch(() => {})
  return texts
}

async function selectElementPlusOption(page, testId, text) {
  const { dropdown, options } = await openElementPlusOptions(page, testId)
  const option = options.filter({ hasText: text })
  assert.equal(await option.count(), 1, `选项必须唯一：${text}`)
  await option.click()
  await dropdown.waitFor({ state: 'hidden', timeout: 10_000 }).catch(() => {})
}

async function waitForTargetOption(page, timeoutMs = 65_000) {
  const deadline = Date.now() + timeoutMs
  let latest = []
  while (Date.now() < deadline) {
    latest = await optionTexts(page, 'product-select')
    if (latest.some((text) => text.includes(TARGET.productName))) return latest
    await page.waitForTimeout(2_000)
  }
  assert.fail(`B 在 ${timeoutMs}ms 内未出现目标商品；当前选项：${latest.join(' | ')}`)
}

async function requestContext(request) {
  const payload = request.postDataJSON()
  return {
    url: request.url(),
    method: request.method(),
    payload,
  }
}

async function closeFirstRunDialogs(page) {
  const identityDialog = page.getByTestId('identity-dialog')
  if (await identityDialog.isVisible().catch(() => false)) {
    await page.getByTestId('identity-name').fill('R003受控验收')
    await page.getByTestId('identity-save').click()
  }
  const pilotGuide = page.getByTestId('pilot-guide-dialog')
  if (await pilotGuide.isVisible().catch(() => false)) {
    await page.getByTestId('pilot-guide-start').click()
  }
}

async function run() {
  const mode = argument('mode', 'smoke')
  assert.match(mode, /^(smoke|acceptance)$/, '--mode 只允许 smoke 或 acceptance')

  const urls = {
    admin: normalizedOrigin(
      'R003_ADMIN_URL',
      process.env.R003_ADMIN_URL || 'http://127.0.0.1:5174',
      '5174',
    ),
    customer: normalizedOrigin(
      'R003_B_URL',
      process.env.R003_B_URL || 'http://192.168.1.11:5173',
      '5173',
    ),
    platform: normalizedOrigin(
      'R003_PLATFORM_URL',
      process.env.R003_PLATFORM_URL || 'http://127.0.0.1:8011',
      '8011',
    ),
    ai: normalizedOrigin(
      'R003_A_URL',
      process.env.R003_A_URL || 'http://127.0.0.1:8000',
      '8000',
    ),
  }

  if (mode === 'acceptance') {
    assert.equal(
      process.env.R003_ENABLE_CONFIRMATION,
      TARGET.productId,
      `生产启用必须显式设置 R003_ENABLE_CONFIRMATION=${TARGET.productId}`,
    )
  }

  const evidenceRoot = path.resolve(
    process.env.R003_EVIDENCE_DIR ||
      path.join(__dirname, '..', '..', '..', '.runtime', 'phase-4-1', 'evidence', 'P41-R003-browser'),
  )
  fs.mkdirSync(evidenceRoot, { recursive: true })
  const executablePath = resolveBrowserExecutable()
  const browser = await chromium.launch({ headless: true, executablePath })
  const context = await browser.newContext({
    locale: 'zh-CN',
    viewport: { width: 1440, height: 1000 },
  })
  await context.addInitScript(() => {
    localStorage.setItem('mumu-customer-workspace:pilot-guide-seen', 'true')
    localStorage.setItem(
      'mumu-customer-workspace:tester-identity',
      JSON.stringify({
        reporterId: 'TESTER-R003-BROWSER-ACCEPTANCE',
        reporterName: 'R003受控验收',
        defaultStoreCode: '',
      }),
    )
  })

  const evidence = {
    status: 'RUNNING',
    mode,
    startedAt: new Date().toISOString(),
    browser: { executablePath, playwright: require('playwright/package.json').version },
    urls,
    target: TARGET,
    preflight: {},
    admin: {},
    customer: {},
    ai: {},
  }

  const adminPage = await context.newPage()
  const customerPage = await context.newPage()
  const unexpectedWrites = []
  const observeWrites = (request) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      unexpectedWrites.push({ method: request.method(), url: request.url() })
    }
  }

  try {
    const [platformHealth, aiHealth, aiStatus, catalogBefore, detailBefore, receiptsBefore] =
      await Promise.all([
        json(await context.request.get(`${urls.platform}/health`), 'C health'),
        json(await context.request.get(`${urls.ai}/api/health`), 'A health'),
        json(await context.request.get(`${urls.ai}/api/status`), 'A status'),
        json(
          await context.request.get(
            `${urls.platform}/api/v1/customer-service/catalog/products?store_code=${encodeURIComponent(TARGET.storeCode)}`,
          ),
          'Catalog before',
        ),
        json(
          await context.request.get(
            `${urls.platform}/api/v1/admin/product-knowledge/products/${encodeURIComponent(TARGET.productId)}`,
          ),
          'Product detail before',
        ),
        json(
          await context.request.get(
            `${urls.platform}/api/v1/admin/operations/activation-receipts` +
              `?entity_type=PRODUCT&entity_ref=${encodeURIComponent(TARGET.productId)}&page=1&size=20`,
          ),
          'Activation receipts before',
        ),
      ])
    evidence.preflight = {
      platformHealth,
      aiHealth,
      aiStatus,
      catalogBefore,
      productStatus: detailBefore.product?.customer_service_status,
      dataStatus: detailBefore.data_status,
      aiKnowledgeStatus: detailBefore.ai_knowledge?.status,
      receiptCount: receiptsBefore.total,
    }
    assert.equal(catalogBefore.result_status, 'COMPLETE', '启用前 Catalog 必须完整')
    assert.ok(
      !catalogBefore.items.some((item) => item.product_id === TARGET.productId),
      '启用前 Catalog 不应包含目标商品',
    )
    assert.equal(detailBefore.product?.customer_service_status, 'DISABLED')
    assert.equal(detailBefore.data_status, 'APPROVED')
    assert.equal(detailBefore.ai_knowledge?.status, 'PUBLISHED')

    await customerPage.goto(`${urls.customer}/ai-chat`, {
      waitUntil: 'domcontentloaded',
      timeout: 20_000,
    })
    await closeFirstRunDialogs(customerPage)
    await customerPage.getByTestId('store-select').waitFor({ timeout: 15_000 })
    const storeOptions = await optionTexts(customerPage, 'store-select')
    assert.ok(
      storeOptions.some((text) => text.includes(TARGET.storeName)),
      'B 启用前必须可选目标店铺',
    )
    await selectElementPlusOption(customerPage, 'store-select', TARGET.storeName)
    const productsBefore = await optionTexts(customerPage, 'product-select')
    assert.ok(
      !productsBefore.some((text) => text.includes(TARGET.productName)),
      'B 启用前不应显示目标商品',
    )
    evidence.customer.before = { storeOptions, productsBefore }
    await customerPage.screenshot({
      path: path.join(evidenceRoot, 'R003-AUTO-B-Before.png'),
      fullPage: true,
    })

    await adminPage.goto(`${urls.admin}/knowledge-center`, {
      waitUntil: 'domcontentloaded',
      timeout: 20_000,
    })
    await adminPage.getByTestId('pending-enable-count').waitFor({ timeout: 15_000 })
    const targetStore = adminPage.locator('.store-tab').filter({ hasText: TARGET.storeName })
    assert.equal(await targetStore.count(), 1, '目标店铺按钮必须唯一')
    await targetStore.click()
    const targetCheckbox = adminPage.getByTestId(`select-product-${TARGET.productId}`)
    const batchButton = adminPage.getByTestId('batch-enable-products')
    const nextStep = adminPage.getByTestId(`next-step-${TARGET.productId}`)
    await targetCheckbox.waitFor({ timeout: 15_000 })
    assert.equal(await targetCheckbox.count(), 1, '目标商品复选框必须唯一')
    assert.equal(await batchButton.isDisabled(), true, '未勾选时批量启用必须禁用')
    adminPage.on('request', observeWrites)
    await targetCheckbox.check()
    assert.equal(await batchButton.isEnabled(), true, '勾选目标后批量启用应可用')
    evidence.admin = {
      targetLocated: true,
      buttonEnabledAfterSelection: true,
      pendingText: await adminPage.getByTestId('pending-enable-count').innerText(),
      nextStep: await nextStep.innerText(),
    }
    await adminPage.screenshot({
      path: path.join(evidenceRoot, 'R003-AUTO-Admin-Target-Selected.png'),
      fullPage: true,
    })

    if (mode === 'smoke') {
      await targetCheckbox.uncheck()
      assert.equal(await batchButton.isDisabled(), true)
      assert.deepEqual(unexpectedWrites, [], '只读 Smoke 禁止产生任何写请求')
      const existingProduct = catalogBefore.items[0]
      assert.ok(existingProduct, '只读 AI Smoke 需要一个已在 Catalog 中的现有商品')
      await selectElementPlusOption(
        customerPage,
        'product-select',
        existingProduct.product_name_display,
      )
      const smokeQuestion = '这个商品适合多大年龄？'
      const smokeQuestionBox = customerPage.getByRole('textbox', { name: '客户问题' })
      const smokeSubmit = customerPage.getByRole('button', { name: '生成建议回复' })
      await smokeQuestionBox.fill(smokeQuestion)
      const smokeRequestPromise = customerPage.waitForRequest(
        (request) =>
          request.method() === 'POST' && request.url().includes('/rag-api/api/chat'),
        { timeout: 20_000 },
      )
      const smokeResponsePromise = customerPage.waitForResponse(
        (response) =>
          response.request().method() === 'POST' && response.url().includes('/rag-api/api/chat'),
        { timeout: 120_000 },
      )
      await smokeSubmit.click()
      const [smokeRequest, smokeResponse] = await Promise.all([
        smokeRequestPromise,
        smokeResponsePromise,
      ])
      assert.equal(smokeResponse.status(), 200, '只读 AI Smoke 回答失败')
      const smokeRequestEvidence = await requestContext(smokeRequest)
      assert.equal(
        smokeRequestEvidence.payload?.context?.product_id,
        existingProduct.product_id,
      )
      assert.equal(smokeRequestEvidence.payload?.context?.sku_id ?? null, null)
      await customerPage.getByTestId('answer-card').waitFor({ timeout: 15_000 })
      const smokeReply = await customerPage.getByTestId('reply-draft').inputValue()
      assert.ok(smokeReply.trim(), '只读 AI Smoke 建议不能为空')
      const smokeCitationCount = await customerPage.getByTestId('citation-item').count()
      assert.ok(smokeCitationCount > 0, '只读 AI Smoke 必须返回知识引用')
      const smokePageText = await customerPage.locator('body').innerText()
      assert.match(smokePageText, /人工确认/)
      assert.match(smokePageText, /不自动发送/)
      assert.match(smokePageText, /不自动退款/)
      assert.match(smokePageText, /不修改订单/)
      evidence.ai.readOnlySmoke = {
        question: smokeQuestion,
        request: smokeRequestEvidence,
        responseStatus: smokeResponse.status(),
        citationCount: smokeCitationCount,
        action: await customerPage.getByTestId('action-tag').innerText(),
        risk: await customerPage.getByTestId('risk-tag').innerText(),
        safetyBoundary: true,
      }
      await customerPage.screenshot({
        path: path.join(evidenceRoot, 'R003-AUTO-B-AI-ReadOnly-Smoke.png'),
        fullPage: true,
      })
      const [detailAfterSmoke, catalogAfterSmoke, receiptsAfterSmoke] = await Promise.all([
        json(
          await context.request.get(
            `${urls.platform}/api/v1/admin/product-knowledge/products/${encodeURIComponent(TARGET.productId)}`,
          ),
          'Product detail after smoke',
        ),
        json(
          await context.request.get(
            `${urls.platform}/api/v1/customer-service/catalog/products?store_code=${encodeURIComponent(TARGET.storeCode)}`,
          ),
          'Catalog after smoke',
        ),
        json(
          await context.request.get(
            `${urls.platform}/api/v1/admin/operations/activation-receipts` +
              `?entity_type=PRODUCT&entity_ref=${encodeURIComponent(TARGET.productId)}&page=1&size=20`,
          ),
          'Activation receipts after smoke',
        ),
      ])
      assert.equal(detailAfterSmoke.product?.customer_service_status, 'DISABLED')
      assert.equal(catalogAfterSmoke.total, catalogBefore.total)
      assert.equal(receiptsAfterSmoke.total, receiptsBefore.total)
      evidence.admin.writeRequests = unexpectedWrites
      evidence.postflight = {
        productStatus: detailAfterSmoke.product?.customer_service_status,
        catalogTotal: catalogAfterSmoke.total,
        receiptCount: receiptsAfterSmoke.total,
      }
      evidence.status = 'PASS_READ_ONLY'
      evidence.finishedAt = new Date().toISOString()
      writeJson(path.join(evidenceRoot, 'R003-Browser-Automation-Smoke.json'), evidence)
      console.log(JSON.stringify(evidence, null, 2))
      return
    }

    await adminPage.getByTestId('knowledge-activation-operator').fill(
      'AI-CS-R003-BROWSER-ACCEPTANCE',
    )
    let dialogSeen = false
    adminPage.once('dialog', async (dialog) => {
      dialogSeen = true
      assert.equal(dialog.type(), 'confirm')
      assert.match(dialog.message(), /确认启用当前选择的 1 个商品/)
      await dialog.accept()
    })
    const activationResponsePromise = adminPage.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes('/api/v1/admin/operations/products/customer-service-status:batch'),
      { timeout: 20_000 },
    )
    await batchButton.click()
    const activationResponse = await activationResponsePromise
    assert.equal(activationResponse.status(), 200, '批量启用请求失败')
    const activationBody = await activationResponse.json()
    assert.equal(dialogSeen, true, '必须经过人工确认对话框')
    assert.equal(activationBody.changed_count, 1, '必须仅启用一个目标商品')
    assert.equal(activationBody.failed_count, 0)
    await adminPage.getByText('商品上线操作已完成').waitFor({ timeout: 15_000 })
    evidence.admin.activation = {
      status: activationResponse.status(),
      response: activationBody,
      dialogSeen,
    }
    await adminPage.screenshot({
      path: path.join(evidenceRoot, 'R003-AUTO-Admin-Activation-Success.png'),
      fullPage: true,
    })

    await customerPage.bringToFront()
    const productsAfter = await waitForTargetOption(customerPage)
    evidence.customer.after = { productsAfter, appearedWithoutReload: true }
    await selectElementPlusOption(customerPage, 'product-select', TARGET.productName)
    await customerPage.screenshot({
      path: path.join(evidenceRoot, 'R003-AUTO-B-Target-Visible.png'),
      fullPage: true,
    })

    const questions = [
      '这个商品适合多大年龄？',
      '材质是什么？',
      '怎么玩？',
    ]
    const answers = []
    const questionBox = customerPage.getByRole('textbox', { name: '客户问题' })
    const submit = customerPage.getByRole('button', { name: '生成建议回复' })
    for (const [index, question] of questions.entries()) {
      await questionBox.fill(question)
      const requestPromise = customerPage.waitForRequest(
        (request) =>
          request.method() === 'POST' && request.url().includes('/rag-api/api/chat'),
        { timeout: 20_000 },
      )
      const responsePromise = customerPage.waitForResponse(
        (response) =>
          response.request().method() === 'POST' && response.url().includes('/rag-api/api/chat'),
        { timeout: 120_000 },
      )
      await submit.click()
      const [request, response] = await Promise.all([requestPromise, responsePromise])
      assert.equal(response.status(), 200, `AI 回答失败：${question}`)
      const contextEvidence = await requestContext(request)
      assert.equal(contextEvidence.payload?.context?.product_id, TARGET.productId)
      assert.equal(contextEvidence.payload?.context?.sku_id ?? null, null)
      await customerPage.getByTestId('answer-card').waitFor({ timeout: 15_000 })
      const citations = await customerPage.getByTestId('citation-item').allTextContents()
      const responseBody = await response.json()
      const foreignCitation = (responseBody.citations || []).find(
        (citation) => citation?.product_id && citation.product_id !== TARGET.productId,
      )
      assert.equal(foreignCitation, undefined, `AI 引用混入其他商品：${question}`)
      const reply = await customerPage.getByTestId('reply-draft').inputValue()
      assert.ok(reply.trim(), `AI 建议为空：${question}`)
      answers.push({
        question,
        request: contextEvidence,
        citationCount: citations.length,
        citations,
        action: await customerPage.getByTestId('action-tag').innerText(),
        risk: await customerPage.getByTestId('risk-tag').innerText(),
      })
      await customerPage.screenshot({
        path: path.join(evidenceRoot, `R003-AUTO-AI-Answer-${index + 1}.png`),
        fullPage: true,
      })
    }
    const pageText = await customerPage.locator('body').innerText()
    assert.match(pageText, /人工确认/)
    assert.match(pageText, /不自动发送/)
    assert.match(pageText, /不自动退款/)
    assert.match(pageText, /不修改订单/)
    evidence.ai = { answers, safetyBoundary: true }

    const [catalogAfter, detailAfter, receiptsAfter] = await Promise.all([
      json(
        await context.request.get(
          `${urls.platform}/api/v1/customer-service/catalog/products?store_code=${encodeURIComponent(TARGET.storeCode)}`,
        ),
        'Catalog after',
      ),
      json(
        await context.request.get(
          `${urls.platform}/api/v1/admin/product-knowledge/products/${encodeURIComponent(TARGET.productId)}`,
        ),
        'Product detail after',
      ),
      json(
        await context.request.get(
          `${urls.platform}/api/v1/admin/operations/activation-receipts` +
            `?entity_type=PRODUCT&entity_ref=${encodeURIComponent(TARGET.productId)}&page=1&size=20`,
        ),
        'Activation receipts after',
      ),
    ])
    assert.equal(catalogAfter.result_status, 'COMPLETE')
    assert.ok(catalogAfter.items.some((item) => item.product_id === TARGET.productId))
    assert.equal(detailAfter.product?.customer_service_status, 'ENABLED')
    assert.equal(receiptsAfter.total, evidence.preflight.receiptCount + 1)
    evidence.postflight = { catalogAfter, detailAfter, receiptsAfter }
    evidence.status = 'PASS_ACCEPTANCE'
    evidence.finishedAt = new Date().toISOString()
    writeJson(path.join(evidenceRoot, 'R003-Browser-Acceptance.json'), evidence)
    console.log(JSON.stringify(evidence, null, 2))
  } catch (error) {
    evidence.status = 'FAILED'
    evidence.finishedAt = new Date().toISOString()
    evidence.error = error.stack || String(error)
    writeJson(
      path.join(
        evidenceRoot,
        mode === 'smoke'
          ? 'R003-Browser-Automation-Smoke.json'
          : 'R003-Browser-Acceptance.json',
      ),
      evidence,
    )
    throw error
  } finally {
    await context.close()
    await browser.close()
  }
}

if (require.main === module) {
  run().catch((error) => {
    console.error(error.stack || String(error))
    process.exitCode = 1
  })
}

module.exports = { run, TARGET, resolveBrowserExecutable }
