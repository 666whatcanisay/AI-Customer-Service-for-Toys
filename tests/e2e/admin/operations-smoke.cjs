const { assert, screenshot } = require('../utils.cjs')

async function runAdminOperationsSmoke(browser) {
  const baseUrl = process.env.AI_CS_ADMIN_URL || 'http://127.0.0.1:5174'
  const page = await browser.newPage()
  const evidence = { baseUrl, pages: {} }
  try {
    await page.goto(`${baseUrl}/store-management`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '店铺管理' }).waitFor()
    const storeRows = page.locator('.list-card tbody tr')
    assert.ok(await storeRows.count(), '店铺管理必须展示正式店铺')
    evidence.storeCount = await storeRows.count()
    await storeRows.first().getByRole('button', { name: '查看', exact: true }).click()
    await page.locator('.detail-card').first().waitFor()
    await storeRows.first().getByRole('button', { name: '编辑', exact: true }).click()
    await page.getByRole('heading', { name: '编辑店铺' }).waitFor()
    evidence.editCustomerServiceStatus = await page
      .getByTestId('store-edit-customer-service-status')
      .inputValue()
    assert.match(evidence.editCustomerServiceStatus, /^(ENABLED|DISABLED)$/)
    await page.locator('.store-form').getByRole('button', { name: '取消' }).click()
    evidence.pages['/store-management'] = true

    await page.goto(`${baseUrl}/knowledge-center`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '商品知识中心' }).waitFor()
    const productCards = page.locator('.product-card')
    assert.ok(await productCards.count(), '商品知识中心必须展示商品卡片')
    evidence.productCardCount = await productCards.count()
    evidence.pendingEnableText = await page.getByTestId('pending-enable-count').innerText()
    const knowledgeText = await productCards.first().innerText()
    assert.match(knowledgeText, /资料：/)
    assert.match(knowledgeText, /客服：/)
    assert.match(knowledgeText, /AI知识：/)
    evidence.pages['/knowledge-center'] = true

    await page.goto(`${baseUrl}/import-center`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '中文资料模板' }).waitFor()
    const templateLinks = page.locator('a[download]')
    assert.equal(await templateLinks.count(), 6, '导入中心必须保留六类模板')
    evidence.templateCount = 6
    evidence.pages['/import-center'] = true
    evidence.screenshot = await screenshot(page, 'c-import-center-six-templates')

    await page.goto(`${baseUrl}/ai-issues`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: 'AI 问题中心' }).waitFor()
    assert.equal(await page.locator('[role="alert"]').count(), 0, 'AI问题中心不应出现接口错误')
    evidence.aiIssueRows = await page.locator('.issue-layout tbody tr').count()
    evidence.pages['/ai-issues'] = true
    return evidence
  } finally {
    await page.close()
  }
}

module.exports = { runAdminOperationsSmoke }
