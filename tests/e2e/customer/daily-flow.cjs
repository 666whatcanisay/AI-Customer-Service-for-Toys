const {
  assert,
  screenshot,
  createCustomerContext,
  selectElementPlusOption,
} = require('../utils.cjs')

async function runCustomerDailyFlow(browser) {
  const baseUrl = process.env.AI_CS_B_URL || 'http://127.0.0.1:5173'
  const context = await createCustomerContext(browser)
  const page = await context.newPage()
  const evidence = { baseUrl, questions: [] }
  try {
    await page.goto(`${baseUrl}/ai-chat`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '跟着步骤，生成一条客服建议' }).waitFor()
    evidence.initialScreenshot = await screenshot(page, 'b-customer-initial')

    assert.equal(await page.getByRole('combobox').count(), 3, '客服工作台应提供店铺、商品、SKU 三个选择器')
    const productResponse = page.waitForResponse((response) =>
      response.url().includes('/customer-service/catalog/products?'))
    evidence.store = await selectElementPlusOption(page, 'store-select', {
      index: Number(process.env.AI_CS_B_STORE_OPTION_INDEX || 0),
    })
    assert.equal((await productResponse).status(), 200, '商品目录请求失败')
    evidence.product = await selectElementPlusOption(page, 'product-select', {
      index: Number(process.env.AI_CS_B_PRODUCT_OPTION_INDEX || 0),
    })

    const questionBox = page.getByRole('textbox', { name: '客户问题' })
    const submit = page.getByRole('button', { name: '生成建议回复' })
    for (const question of ['商品适合年龄？', '材质是什么？', '怎么玩法？']) {
      await questionBox.fill(question)
      const chatResponse = page.waitForResponse((response) =>
        response.url().includes('/rag-api/api/chat'))
      await submit.click()
      assert.equal((await chatResponse).status(), 200, `AI请求失败：${question}`)
      await page.getByTestId('answer-card').waitFor()
      const body = await page.getByTestId('answer-card').innerText()
      assert.ok(!body.includes('大模型请求失败'), `客服答案暴露技术失败文案：${question}`)
      assert.ok(body.includes('仅供建议') || body.includes('人工确认'), '缺少人工确认安全提示')
      const reply = await page.getByTestId('reply-draft').inputValue()
      assert.ok(reply.trim(), `AI建议为空：${question}`)
      evidence.questions.push({
        question,
        passed: true,
        citationCount: await page.getByTestId('citation-item').count(),
        action: await page.getByTestId('action-tag').innerText(),
        risk: await page.getByTestId('risk-tag').innerText(),
      })
    }
    evidence.finalScreenshot = await screenshot(page, 'b-customer-final')
    return evidence
  } finally {
    await context.close()
  }
}

module.exports = { runCustomerDailyFlow }
