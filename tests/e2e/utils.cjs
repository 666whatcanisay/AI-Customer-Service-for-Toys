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

async function createCustomerContext(browser, identity = {}) {
  const context = await browser.newContext()
  const storedIdentity = {
    reporterId: identity.reporterId || 'TESTER-RELIABILITY-E2E',
    reporterName: identity.reporterName || '稳定性验收',
    defaultStoreCode: identity.defaultStoreCode || '',
  }
  await context.addInitScript(({ storedIdentity }) => {
    localStorage.setItem('mumu-customer-workspace:pilot-guide-seen', 'true')
    localStorage.setItem(
      'mumu-customer-workspace:tester-identity',
      JSON.stringify(storedIdentity),
    )
  }, { storedIdentity })
  return context
}

async function selectElementPlusOption(page, testId, options = {}) {
  const select = page.getByTestId(testId)
  await select.click()
  const dropdown = page.locator('.el-select-dropdown:visible').last()
  await dropdown.waitFor({ state: 'visible', timeout: 10_000 })
  const visibleOptions = dropdown.locator(
    '.el-select-dropdown__item:not(.is-disabled)',
  )
  await visibleOptions.first().waitFor({ state: 'visible', timeout: 10_000 })

  let option
  if (options.text) {
    option = visibleOptions.filter({ hasText: options.text }).first()
  } else {
    option = visibleOptions.nth(options.index || 0)
  }
  await option.waitFor({ state: 'visible', timeout: 10_000 })
  const text = (await option.innerText()).trim()
  await option.click()
  await dropdown.waitFor({ state: 'hidden', timeout: 10_000 }).catch(() => {})
  return { text }
}

module.exports = {
  assert,
  screenshot,
  selectFirstRealOption,
  createCustomerContext,
  selectElementPlusOption,
}
