const path = require('node:path')
const { assert, screenshot, selectFirstRealOption } = require('../utils.cjs')

async function uploadThroughPage(page, filePath) {
  await page.locator('input[type="file"]').setInputFiles(filePath)
  const responsePromise = page.waitForResponse((response) =>
    response.url().includes('/api/v1/admin/product-knowledge-imports')
      && response.request().method() === 'POST'
  )
  await page.getByRole('button', { name: /上传 Excel 并生成待审核结果/ }).click()
  const response = await responsePromise
  let body = {}
  try { body = await response.json() } catch {}
  await page.waitForLoadState('networkidle')
  return { status: response.status(), body }
}

async function runR009ProductImport(browser) {
  const baseUrl = process.env.AI_CS_ADMIN_URL || 'http://127.0.0.1:5179'
  const filePath = process.env.R009_XLSX_PATH
  const emptyFilePath = process.env.R009_EMPTY_XLSX_PATH
  const resumeBatchId = process.env.R009_RESUME_BATCH_ID || ''
  assert.ok(filePath, '必须提供 R009_XLSX_PATH')
  assert.ok(!/:(5174)(?:\/|$)/.test(baseUrl), 'R009 写入验收禁止指向正式 5174')

  const page = await browser.newPage()
  const evidence = { baseUrl, fileName: path.basename(filePath) }
  try {
    if (resumeBatchId) {
      await page.addInitScript((batchId) => {
        sessionStorage.setItem('r009-product-knowledge-import-batch-id', batchId)
      }, resumeBatchId)
    }
    await page.goto(`${baseUrl}/knowledge-materials`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '资料上传与审核' }).waitFor()
    const selects = page.getByRole('combobox')
    evidence.store = await selectFirstRealOption(selects.nth(0))
    await selects.nth(1).selectOption('PRODUCT_KNOWLEDGE')
    await page.getByRole('textbox', { name: /操作人/ }).fill('product-stability-v1')

    if (resumeBatchId) {
      evidence.batchId = resumeBatchId
      evidence.resumedFromBrowserUpload = true
    } else {
      const firstUpload = await uploadThroughPage(page, filePath)
      assert.ok([201, 202].includes(firstUpload.status), '真实 Excel 上传未被受理')
      evidence.batchId = firstUpload.body.batch_id
    }
    evidence.beforeReviewScreenshot = await screenshot(page, 'r009-merge-preview')

    const pageText = await page.getByRole('main').last().innerText()
    for (const sheet of ['填写说明', '数据填写', '示例数据', '字段说明']) {
      assert.ok(pageText.includes(sheet), `预检结果缺少工作表：${sheet}`)
    }
    evidence.changeTypes = {}
    for (const label of ['新增', '更新', '保留原值', '无变化']) {
      evidence.changeTypes[label] = await page.getByText(label, { exact: true }).count()
    }
    assert.ok(evidence.changeTypes['新增'] > 0, 'Merge 预览没有 ADD')
    assert.ok(
      Object.values(evidence.changeTypes).reduce((sum, count) => sum + count, 0) > 0,
      'Merge 预览没有字段变化',
    )

    let approved = 0
    while (await page.getByRole('button', { name: '通过并 Merge' }).count()) {
      await page.getByRole('button', { name: '通过并 Merge' }).first().click()
      await page.waitForLoadState('networkidle')
      approved += 1
      assert.ok(approved <= 200, '审核循环超过安全上限')
    }
    evidence.approved = approved
    if (approved === 0) {
      const reviewedText = await page.getByRole('main').last().innerText()
      assert.ok(/已通过并写入|审核完成/.test(reviewedText), '没有可验证的人工审核结果')
      evidence.resumedAfterApproval = true
    }
    evidence.afterReviewScreenshot = await screenshot(page, 'r009-review-applied')

    const duplicate = await uploadThroughPage(page, filePath)
    assert.ok([201, 202].includes(duplicate.status), '重复文件上传请求失败')
    await page.getByText(/没有需要审核的变化/).waitFor()
    evidence.duplicateStatus = duplicate.body.status

    const optionValues = await selects.nth(0).locator('option').evaluateAll((options) =>
      options.filter((option) => option.value).map((option) => option.value)
    )
    assert.ok(optionValues.length >= 2, '错误店铺测试需要至少两个店铺')
    const currentStore = await selects.nth(0).inputValue()
    await selects.nth(0).selectOption(optionValues.find((value) => value !== currentStore))
    const wrongStore = await uploadThroughPage(page, filePath)
    assert.ok(wrongStore.status >= 400 || wrongStore.body.status === 'PREFLIGHT_FAILED', '店铺不一致应整批阻断')
    evidence.wrongStoreStatus = wrongStore.status

    let unsupportedAlert = ''
    page.once('dialog', async (dialog) => {
      unsupportedAlert = dialog.message()
      await dialog.accept()
    })
    await selects.nth(1).selectOption('SKU_DIFFERENCE')
    await page.waitForTimeout(100)
    assert.equal(unsupportedAlert, '该模板导入功能暂未开放')
    evidence.unsupportedTemplateAlert = unsupportedAlert

    if (emptyFilePath) {
      await selects.nth(1).selectOption('PRODUCT_KNOWLEDGE')
      await selects.nth(0).selectOption(currentStore)
      const emptyUpload = await uploadThroughPage(page, emptyFilePath)
      assert.ok([201, 202, 422].includes(emptyUpload.status))
      const emptyText = await page.getByRole('main').last().innerText()
      assert.ok(/阻塞|没有.*商品|为空|预检/.test(emptyText), '空模板未显示阻断结果')
      evidence.emptyUploadStatus = emptyUpload.status
    }
    return evidence
  } finally {
    await page.close()
  }
}

module.exports = { runR009ProductImport }
