const path = require('node:path')
const { assert, screenshot, selectFirstRealOption } = require('../utils.cjs')

async function uploadThroughPage(page, filePath) {
  await page.locator('input[type="file"]').setInputFiles(filePath)
  const responsePromise = page.waitForResponse((response) =>
    response.url().includes('/api/v1/admin/product-knowledge-imports')
      && response.request().method() === 'POST'
  )
  const preflightPromise = page.waitForResponse((response) =>
    response.url().includes('/preflight') && response.request().method() === 'GET'
  )
  const previewPromise = page.waitForResponse((response) =>
    response.url().includes('/merge-preview') && response.request().method() === 'GET'
  )
  await page.getByRole('button', { name: /上传 Excel 并生成待审核结果/ }).click()
  const response = await responsePromise
  let body = {}
  try { body = await response.json() } catch {}
  const [preflightResponse, previewResponse] = await Promise.all([
    preflightPromise,
    previewPromise,
  ])
  assert.equal(preflightResponse.status(), 200, '预检结果读取失败')
  assert.equal(previewResponse.status(), 200, 'Merge预览读取失败')
  return { status: response.status(), body }
}

async function runR009ProductImport(browser) {
  const baseUrl = process.env.AI_CS_ADMIN_URL || 'http://127.0.0.1:5179'
  const filePath = process.env.R009_XLSX_PATH
  const emptyFilePath = process.env.R009_EMPTY_XLSX_PATH
  const missingProductFilePath = process.env.R009_MISSING_PRODUCT_XLSX_PATH
  const updateFilePath = process.env.R009_UPDATE_XLSX_PATH
  const resumeBatchId = process.env.R009_RESUME_BATCH_ID || ''
  const expectedStoreName = process.env.R009_STORE_NAME || ''
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
    if (expectedStoreName) {
      const matchingOption = selects.nth(0).locator('option').filter({ hasText: expectedStoreName }).first()
      const value = await matchingOption.getAttribute('value')
      assert.ok(value, `未找到与Excel匹配的店铺：${expectedStoreName}`)
      await selects.nth(0).selectOption(value)
      evidence.store = { value, text: (await matchingOption.innerText()).trim() }
    } else {
      evidence.store = await selectFirstRealOption(selects.nth(0))
    }
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
    evidence.sheetCount = await page.locator('.sheet-chip').count()
    assert.equal(evidence.sheetCount, 4, '预检必须识别四个固定工作表')
    evidence.dataRowCount = Number(await page.locator('.summary-grid strong').first().innerText())
    assert.ok(evidence.dataRowCount > 0, '真实Excel必须识别至少一条商品数据')
    evidence.changeTypes = {
      新增: await page.locator('.change-badge.add').count(),
      更新: await page.locator('.change-badge.update').count(),
      保留原值: await page.locator('.change-badge.keep').count(),
      无变化: await page.locator('.change-badge.no_change').count(),
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

    if (updateFilePath) {
      const updateUpload = await uploadThroughPage(page, updateFilePath)
      assert.ok([201, 202].includes(updateUpload.status), 'Merge更新文件上传未被受理')
      evidence.updateChangeTypes = {
        更新: await page.locator('.change-badge.update').count(),
        保留原值: await page.locator('.change-badge.keep').count(),
        无变化: await page.locator('.change-badge.no_change').count(),
      }
      for (const [label, count] of Object.entries(evidence.updateChangeTypes)) {
        assert.ok(count > 0, `Merge更新预览缺少${label}`)
      }
      let updateApproved = 0
      while (await page.getByRole('button', { name: '通过并 Merge' }).count()) {
        await page.getByRole('button', { name: '通过并 Merge' }).first().click()
        await page.waitForLoadState('networkidle')
        updateApproved += 1
        assert.ok(updateApproved <= 200, '更新审核循环超过安全上限')
      }
      evidence.updateApproved = updateApproved
    }

    const duplicate = await uploadThroughPage(page, updateFilePath || filePath)
    assert.ok([201, 202].includes(duplicate.status), '重复文件上传请求失败')
    await page.getByText(/没有需要审核的变化/).waitFor()
    evidence.duplicateStatus = duplicate.body.status || 'NO_CHANGE_UI_CONFIRMED'

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
    if (missingProductFilePath) {
      await selects.nth(1).selectOption('PRODUCT_KNOWLEDGE')
      await selects.nth(0).selectOption(currentStore)
      const missingProductUpload = await uploadThroughPage(page, missingProductFilePath)
      assert.ok([201, 202, 422].includes(missingProductUpload.status))
      const missingProductText = await page.getByRole('main').last().innerText()
      assert.ok(
        missingProductText.includes('商品名称') && /必填|不能为空|缺少/.test(missingProductText),
        '缺少商品名称未显示字段错误',
      )
      assert.ok(
        missingProductUpload.body.status === 'PREFLIGHT_FAILED' || missingProductUpload.status === 422,
        '缺少商品名称必须阻断正式写入',
      )
      evidence.missingProductStatus = missingProductUpload.body.status || missingProductUpload.status
    }
    return evidence
  } finally {
    await page.close()
  }
}

module.exports = { runR009ProductImport }
