const { chromium } = require('playwright')
const { runCustomerDailyFlow } = require('./customer/daily-flow.cjs')
const { runAdminOperationsSmoke } = require('./admin/operations-smoke.cjs')
const { runR009ProductImport } = require('./workflows/r009-product-import.cjs')

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || chromium.executablePath(),
  })
  const results = []
  const suites = [
    ['B 客服日常流程', runCustomerDailyFlow],
    ['C 运营页面', runAdminOperationsSmoke],
    ['R009 商品知识导入', runR009ProductImport],
  ]
  try {
    for (const [name, suite] of suites) {
      try {
        results.push({ name, status: 'PASS', evidence: await suite(browser) })
      } catch (error) {
        results.push({ name, status: 'FAIL', error: error.stack || String(error) })
      }
    }
  } finally {
    await browser.close()
  }
  console.log(JSON.stringify(results, null, 2))
  if (results.some((item) => item.status === 'FAIL')) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
