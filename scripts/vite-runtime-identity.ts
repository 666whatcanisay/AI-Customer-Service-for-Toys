import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
export const runtimeIdentityPath = '/__runtime-identity.json'

type ApiTarget = string | undefined

export interface RuntimeIdentity {
  schemaVersion: 1
  productName: string
  version: string | null
  gitShortSha: string | null
  sourceState: 'CLEAN' | 'DIRTY' | 'UNAVAILABLE'
  runMode: string
  runModeSource: 'STARTUP_ENV' | 'VITE_MODE'
  apiMode: 'SAME_ORIGIN_PROXY' | 'DIRECT' | 'HYBRID' | 'UNAVAILABLE'
}

export interface RuntimeIdentityOptions {
  rootDirectory: string
  packageJsonPath: string
  productName: string
  viteMode: string
  startupMode?: string
  apiTargets: ApiTarget[]
}

function gitOutput(rootDirectory: string, args: string[]): string | null {
  try {
    return execFileSync('git', args, {
      cwd: rootDirectory,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore']
    })
  } catch {
    return null
  }
}

function gitValue(rootDirectory: string, args: string[]): string | null {
  const output = gitOutput(rootDirectory, args)
  const value = output?.trim()
  return value || null
}

function sourceState(rootDirectory: string): RuntimeIdentity['sourceState'] {
  const status = gitOutput(rootDirectory, ['status', '--porcelain', '--untracked-files=all'])
  if (status === null) return 'UNAVAILABLE'
  return status.trim() ? 'DIRTY' : 'CLEAN'
}

function apiMode(apiTargets: ApiTarget[]): RuntimeIdentity['apiMode'] {
  const configuredTargets = apiTargets.filter((value): value is string => Boolean(value?.trim()))
  if (configuredTargets.length === 0) return 'UNAVAILABLE'
  if (configuredTargets.every((value) => value.trim().startsWith('/'))) return 'SAME_ORIGIN_PROXY'
  if (configuredTargets.every((value) => /^https?:\/\//i.test(value.trim()))) return 'DIRECT'
  return 'HYBRID'
}

export function createRuntimeIdentity(options: RuntimeIdentityOptions): RuntimeIdentity {
  let version: string | null = null
  try {
    const packageJson = JSON.parse(readFileSync(resolve(options.packageJsonPath), 'utf8')) as { version?: unknown }
    version = typeof packageJson.version === 'string' && packageJson.version.trim() ? packageJson.version : null
  } catch {
    version = null
  }

  const startupMode = options.startupMode?.trim()
  return {
    schemaVersion: 1,
    productName: options.productName,
    version,
    gitShortSha: gitValue(options.rootDirectory, ['rev-parse', '--short=12', 'HEAD']),
    sourceState: sourceState(options.rootDirectory),
    runMode: startupMode || options.viteMode,
    runModeSource: startupMode ? 'STARTUP_ENV' : 'VITE_MODE',
    apiMode: apiMode(options.apiTargets)
  }
}

export function createRuntimeIdentityPlugin(identity: RuntimeIdentity) {
  const body = `${JSON.stringify(identity, null, 2)}\n`

  return {
    name: 'runtime-identity',
    configureServer(server: { middlewares: { use: (handler: (request: { url?: string }, response: { statusCode: number; setHeader: (name: string, value: string) => void; end: (body: string) => void }, next: () => void) => void) => void } }) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? '/', 'http://runtime.local').pathname
        if (pathname !== runtimeIdentityPath) {
          next()
          return
        }
        response.statusCode = 200
        response.setHeader('Content-Type', 'application/json; charset=utf-8')
        response.setHeader('Cache-Control', 'no-store, max-age=0')
        response.end(body)
      })
    },
    generateBundle(this: { emitFile: (asset: { type: 'asset'; fileName: string; source: string }) => unknown }) {
      this.emitFile({
        type: 'asset',
        fileName: runtimeIdentityPath.slice(1),
        source: body
      })
    }
  }
}
