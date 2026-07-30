const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const resultRoot = path.join(__dirname, 'test-results')

async function screenshot(page, name) {
  fs.mkdirSync(resultRoot, { recursive: true })
  const target = path.join(resultRoot, `${name}.png`)
  await page.screenshot({ path: target, fullPage: true })
  return target
}

async function selectFirstRealOption(locator) {
  const values = await locator.locator('option').evaluateAll((options) =>
    options.map((option) => ({ value: option.value, text: option.textContent || '' }))
  )
  const selected = values.find((item) => item.value)
  assert.ok(selected, '没有可选择的业务选项')
  await locator.selectOption(selected.value)
  return selected
}

module.exports = { assert, screenshot, selectFirstRealOption }
