const { assert, screenshot, selectFirstRealOption } = require('../utils.cjs')

async function runCustomerDailyFlow(browser) {
  const baseUrl = process.env.AI_CS_B_URL || 'http://127.0.0.1:5173'
  const page = await browser.newPage()
  const evidence = { baseUrl, questions: [] }
  try {
    await page.goto(`${baseUrl}/ai-chat`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '跟着步骤，生成一条客服建议' }).waitFor()
    evidence.initialScreenshot = await screenshot(page, 'b-customer-initial')

    const selects = page.getByRole('combobox')
    assert.equal(await selects.count(), 3, '客服工作台应提供店铺、商品、SKU 三个选择器')
    evidence.store = await selectFirstRealOption(selects.nth(0))
    await page.waitForFunction(() => {
      const controls = document.querySelectorAll('select')
      return controls.length >= 2 && controls[1].querySelectorAll('option').length > 1
    })
    evidence.product = await selectFirstRealOption(selects.nth(1))

    const questionBox = page.getByRole('textbox', { name: '客户问题' })
    const submit = page.getByRole('button', { name: '生成建议回复' })
    for (const question of ['商品适合年龄？', '材质是什么？', '怎么玩法？']) {
      await questionBox.fill(question)
      await submit.click()
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(300)
      const body = await page.locator('main').innerText()
      assert.ok(!body.includes('大模型请求失败'), `客服答案暴露技术失败文案：${question}`)
      assert.ok(body.includes('仅供建议') || body.includes('人工确认'), '缺少人工确认安全提示')
      evidence.questions.push({ question, passed: true })
    }
    evidence.finalScreenshot = await screenshot(page, 'b-customer-final')
    return evidence
  } finally {
    await page.close()
  }
}

module.exports = { runCustomerDailyFlow }
