const { chromium } = require('playwright')
const { runCatalogEnvelopeStates } = require('../customer/catalog-envelope-states.cjs')

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || chromium.executablePath(),
  })
  try {
    console.log(JSON.stringify(await runCatalogEnvelopeStates(browser), null, 2))
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error.stack || String(error))
  process.exitCode = 1
})
