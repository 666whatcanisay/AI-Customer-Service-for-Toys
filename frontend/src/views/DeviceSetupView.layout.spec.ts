import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(process.cwd(), 'src/views/DeviceSetupView.vue'), 'utf8')
const style = source.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1] ?? ''

describe('DeviceSetupView desktop layout', () => {
  it('owns a bounded vertical scroll container inside the non-scrolling app shell', () => {
    expect(style).toMatch(/\.setup-page\s*\{[\s\S]*?height:100%;/)
    expect(style).toMatch(/\.setup-page\s*\{[\s\S]*?min-height:0;/)
    expect(style).toMatch(/\.setup-page\s*\{[\s\S]*?overflow-y:auto;/)
    expect(style).toMatch(/\.setup-page\s*\{[\s\S]*?overflow-x:hidden;/)
  })

  it('keeps a short card centered and lets a tall card start at the top of the scroll area', () => {
    expect(style).toMatch(/\.setup-card\s*\{[\s\S]*?flex:none;/)
    expect(style).toMatch(/\.setup-card\s*\{[\s\S]*?margin:auto 0;/)
  })

  it('reduces spacing for short desktop windows without hiding diagnostic actions', () => {
    expect(style).toContain('@media(max-height:900px)')
    expect(style).toContain('@media(max-height:720px)')
    expect(style).toMatch(/@media\(max-height:720px\)[\s\S]*?\.error-guide\{padding:14px\}/)
  })
})
