const { assert, screenshot } = require('../utils.cjs')

async function runAdminOperationsSmoke(browser) {
  const baseUrl = process.env.AI_CS_ADMIN_URL || 'http://127.0.0.1:5174'
  const page = await browser.newPage()
  const evidence = { baseUrl, pages: {} }
  try {
    const checks = [
      ['/store-management', '店铺管理'],
      ['/knowledge-center', '商品知识中心'],
      ['/import-center', '中文资料模板'],
      ['/ai-issues', 'AI 问题中心'],
    ]
    for (const [route, heading] of checks) {
      await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: heading }).waitFor()
      evidence.pages[route] = true
    }
    await page.goto(`${baseUrl}/import-center`, { waitUntil: 'networkidle' })
    const templateLinks = page.locator('a[download]')
    assert.equal(await templateLinks.count(), 6, '导入中心必须保留六类模板')
    evidence.templateCount = 6
    evidence.screenshot = await screenshot(page, 'c-import-center-six-templates')
    return evidence
  } finally {
    await page.close()
  }
}

module.exports = { runAdminOperationsSmoke }
