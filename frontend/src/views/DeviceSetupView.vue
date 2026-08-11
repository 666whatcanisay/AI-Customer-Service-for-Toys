<template>
  <main class="setup-page">
    <section class="setup-card" data-testid="device-setup-wizard">
      <header>
        <span class="brand">AI</span>
        <div><small>首次使用设置</small><h1>把这台电脑连接到客服账号</h1></div>
        <span class="safe">不会读取或保存您的密码</span>
      </header>

      <ol class="progress" aria-label="设置进度">
        <li class="done"><i>✓</i><span>登录账号</span></li>
        <li :class="{ active: stage === 'DEVICE', done: stage === 'STORE' || stage === 'READY' }"><i>2</i><span>绑定电脑</span></li>
        <li :class="{ active: stage === 'STORE', done: stage === 'READY' }"><i>3</i><span>确认店铺</span></li>
        <li :class="{ active: stage === 'READY' }"><i>4</i><span>进入助手</span></li>
      </ol>

      <div v-if="loading" class="state-box">正在检查这台电脑，请稍候…</div>

      <section v-else-if="!stores.length" class="problem-box">
        <h2>账号还没有店铺权限</h2>
        <p>请联系管理员，在“运营中心 → 用户管理 → 修改分配”中为当前账号选择至少一个店铺。</p>
        <button type="button" class="secondary" @click="refresh">管理员处理好了，重新检查</button>
      </section>

      <section v-else-if="stage === 'DEVICE' && bootstrap?.binding.secure_control_ready === false" class="task-box host-pairing">
        <div class="task-heading"><span>现在只需完成这一步</span><b>首次连接主机</b></div>
        <h2>先把这台电脑连接到可信主机</h2>
        <p>这不是账号、密码或PDD问题。管理员会在主机上看到一个12位一次性连接码，请先搜索并核对主机，再人工输入连接码。完成后才能申请32位账号绑定许可。</p>
        <div class="button-row">
          <button type="button" class="secondary" :disabled="busy" @click="discoverTrustedHosts">{{ discoveringHosts ? '正在搜索…' : '搜索客服主机' }}</button>
        </div>
        <div v-if="trustedHosts.length" class="pairing-hosts">
          <label v-for="host in trustedHosts" :key="String(host.hostId)" :class="{ selected: selectedHostId === host.hostId }">
            <input v-model="selectedHostId" type="radio" :value="String(host.hostId)" />
            <span><strong>{{ host.hostName }}</strong><small>{{ host.serverAddress }} · {{ host.environment }}</small></span>
          </label>
          <label class="pairing-code"><strong>这里只输入12位主机连接码</strong>
            <input v-model.trim="hostPairingCode" maxlength="39" autocomplete="off" spellcheck="false" placeholder="例如 7K3M-9Q2X-4T8R" data-testid="host-pairing-code" />
            <small>不是运营端刚生成的32位账号绑定码。12位码由主机启动器生成，并显示或复制给主机管理员。</small>
            <span v-if="hostPairingCodeHint" :class="['code-hint', { invalid: hostPairingCodeKind !== 'READY' }]" data-testid="host-pairing-code-hint">{{ hostPairingCodeHint }}</span>
          </label>
          <label class="confirmation"><input v-model="hostPairingConfirmed" type="checkbox" />我已核对主机名称和地址，并确认连接这台电脑</label>
          <button type="button" class="primary" :disabled="busy || !selectedHostId || hostPairingCodeKind !== 'READY' || !hostPairingConfirmed" @click="pairTrustedHost">连接可信主机</button>
        </div>
        <p v-else-if="hostDiscoveryAttempted" class="pairing-help">没有发现主机。请让主机管理员启动18443设备服务和18421发现服务，并生成新的12位连接码，然后再次搜索。</p>
      </section>

      <section v-else-if="stage === 'DEVICE'" class="task-box">
        <div class="task-heading"><span>现在只需完成这一步</span><b>约1分钟</b></div>
        <h2>绑定这台客服电脑</h2>
        <p>这是首次使用，不是密码错误。程序会自动申请一次性许可并绑定当前账号，无需复制编号或使用命令行。</p>
        <dl>
          <div><dt>当前客服</dt><dd>{{ auth.user.value?.display_name }}</dd></div>
          <div><dt>当前电脑</dt><dd>{{ bootstrap?.binding.device_id || '正在识别' }}</dd></div>
          <div><dt>服务店铺</dt><dd>
            <select v-model.number="selectedStoreId" aria-label="绑定服务店铺">
              <option v-for="store in stores" :key="store.store_id" :value="store.store_id">{{ store.store_name }}</option>
            </select>
          </dd></div>
        </dl>
        <label class="confirmation"><input v-model="confirmed" type="checkbox" />我确认这是本人正在使用的客服电脑</label>
        <button type="button" class="primary" :disabled="busy || !confirmed || !selectedStoreId" @click="bindDevice">
          {{ busy ? actionText : bootstrap?.binding.identity_status === 'BOUND' ? '继续完成启用' : '绑定这台电脑' }}
        </button>
        <details class="admin-code-entry">
          <summary>已有管理员生成的一次性绑定码</summary>
          <p>只有主机管理员在“设备管理”中生成过绑定许可时才需要这里。绑定码不会保存，使用一次后立即失效。</p>
          <label>一次性绑定码<input v-model="adminBindingCode" maxlength="39" autocomplete="off" spellcheck="false" placeholder="输入或粘贴32位绑定码" /></label>
          <button type="button" class="secondary" :disabled="busy || !confirmed || !selectedStoreId || normalizedAdminBindingCode.length !== 32" @click="bindWithAdminCode">使用绑定码连接这台电脑</button>
        </details>
      </section>

      <section v-else-if="stage === 'STORE'" class="task-box">
        <div class="task-heading"><span>电脑已绑定</span><b>下一步</b></div>
        <h2>登录PDD并确认工作店铺</h2>
        <p v-if="!bootstrap?.binding.observed_store_id">请在Agent专用Edge中人工登录PDD。登录完成并进入客服工作台后，点击“重新检查”。程序不会自动登录。</p>
        <p v-else>程序识别到PDD店铺号“{{ bootstrap.binding.observed_store_id }}”，请选择与该平台账号绑定的授权店铺进行确认。</p>
        <label class="store-select">当前工作店铺
          <select v-model="selectedStoreCode" aria-label="当前工作店铺">
            <option v-for="store in authorizedStores" :key="store.store_code" :value="store.store_code">{{ storeOptionLabel(store) }}</option>
          </select>
        </label>
        <div class="button-row">
          <button type="button" class="secondary" :disabled="busy" @click="recheckStore">{{ busy ? '正在检查…' : '重新检查' }}</button>
          <button type="button" class="primary" :disabled="busy || !bootstrap?.binding.observed_store_id || !selectedStoreCode" @click="confirmStore">确认当前店铺</button>
        </div>
        <p v-if="storeCheckMessage" class="check-result" aria-live="polite">{{ storeCheckMessage }}</p>
      </section>

      <section v-else class="success-box">
        <h2>设置完成</h2><p>设备、客服身份和当前店铺均已确认，正在进入客服助手。</p>
      </section>

      <section v-if="error" class="error-guide" role="alert" data-testid="binding-error-guide">
        <div class="error-heading">
          <div><small>这一步没有完成</small><h2>{{ error.title }}</h2></div>
          <span>{{ error.owner }}</span>
        </div>
        <p>{{ error.message }}</p>
        <div v-if="error.avoid.length" class="not-required"><strong>您现在不用做：</strong>{{ error.avoid.join('、') }}</div>
        <div class="guide-steps">
          <strong>请按下面步骤处理</strong>
          <ol><li v-for="step in error.steps" :key="step">{{ step }}</li></ol>
        </div>
        <div class="error-actions">
          <button type="button" class="primary" :disabled="busy" @click="error.retry">{{ error.action }}</button>
          <button type="button" class="secondary" @click="copyDiagnostic(error)">{{ copied ? '诊断信息已复制' : '复制诊断信息' }}</button>
        </div>
        <details v-if="error.adminSteps.length" class="admin-guide">
          <summary>管理员处理方法</summary>
          <ol><li v-for="step in error.adminSteps" :key="step">{{ step }}</li></ol>
        </details>
        <details class="technical-guide">
          <summary>查看脱敏技术信息</summary>
          <dl><div v-for="(value, key) in error.technical" :key="key"><dt>{{ key }}</dt><dd>{{ value || '未提供' }}</dd></div></dl>
        </details>
      </section>
      <footer>安全保护：必须人工确认发送 · 禁止自动回复 · 不保存PDD密码或Cookie</footer>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthSession } from '@/auth/authSession'
import type { AuthStorePlatformBinding } from '@/auth/authSession'
import {
  discoverChannelAgentHosts,
  enrollChannelAgentDevice,
  fetchChannelAgentBootstrap,
  pairChannelAgentHost,
  syncChannelAgentIdentity,
  type ChannelAgentBootstrap
} from '@/api/channelAgentDesktopClient'
import { desktopAgentClient } from '@/api/desktopAgentClient'

const auth = useAuthSession()
const router = useRouter()
const bootstrap = ref<ChannelAgentBootstrap | null>(null)
const loading = ref(true)
const busy = ref(false)
const confirmed = ref(false)
const selectedStoreId = ref<number | null>(auth.defaultStore.value?.store_id ?? auth.user.value?.stores[0]?.store_id ?? null)
const selectedStoreCode = ref('')
const actionText = ref('正在申请安全许可…')
const copied = ref(false)
const automaticRechecks = ref(0)
const adminBindingCode = ref('')
const trustedHosts = ref<Array<Record<string, unknown>>>([])
const selectedHostId = ref('')
const hostPairingCode = ref('')
const hostPairingConfirmed = ref(false)
const discoveringHosts = ref(false)
const hostDiscoveryAttempted = ref(false)
const storeCheckMessage = ref('')
let automaticRecheckTimer: number | null = null

type BindingIssue = {
  title: string
  message: string
  owner: string
  action: string
  retry: () => void
  steps: string[]
  avoid: string[]
  adminSteps: string[]
  technical: Record<string, string | number | null>
}

const error = ref<BindingIssue | null>(null)

type StoreForSetup = {
  store_code: string
  store_name: string
  platform_bindings?: readonly AuthStorePlatformBinding[]
}

const stores = computed(() => auth.user.value?.stores ?? [])
const authorizedStores = computed(() => stores.value.filter((store) => bootstrap.value?.binding.authorized_store_ids.includes(store.store_code)))
const observedPlatform = 'pinduoduo'
const matchingObservedStore = computed(() => {
  const observed = bootstrap.value?.binding.observed_store_id
  if (!observed) return null
  return authorizedStores.value.find((store) => activePlatformBinding(store, observedPlatform, observed)) ?? null
})
const normalizedAdminBindingCode = computed(() => adminBindingCode.value.replace(/[^A-Fa-f0-9]/g, '').toUpperCase())
const normalizedHostPairingCode = computed(() => hostPairingCode.value.replace(/[^0-9A-HJ-NP-TV-Z]/gi, '').toUpperCase())
const rawHostPairingCode = computed(() => hostPairingCode.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase())
const hostPairingCodeKind = computed<'EMPTY' | 'ADMIN_BINDING_CODE' | 'INCOMPLETE' | 'READY' | 'INVALID'>(() => {
  if (!rawHostPairingCode.value) return 'EMPTY'
  if (/^[A-F0-9]{32}$/.test(rawHostPairingCode.value)) return 'ADMIN_BINDING_CODE'
  if (normalizedHostPairingCode.value.length < 12) return 'INCOMPLETE'
  if (normalizedHostPairingCode.value.length === 12 && rawHostPairingCode.value.length === 12) return 'READY'
  return 'INVALID'
})
const hostPairingCodeHint = computed(() => {
  if (hostPairingCodeKind.value === 'EMPTY') return ''
  if (hostPairingCodeKind.value === 'ADMIN_BINDING_CODE') return '您粘贴的是32位账号绑定码，这是下一步使用的码。请先向主机管理员索取本步骤的12位主机连接码。'
  if (hostPairingCodeKind.value === 'INCOMPLETE') return `当前是 ${normalizedHostPairingCode.value.length} 位，还需要 ${12 - normalizedHostPairingCode.value.length} 位。`
  if (hostPairingCodeKind.value === 'READY') return '12位主机连接码格式正确，请核对主机后继续。'
  return '这不是有效的12位主机连接码。请勿在这里输入32位账号绑定码。'
})
const stage = computed<'DEVICE' | 'STORE' | 'READY'>(() => {
  const binding = bootstrap.value?.binding
  if (!binding || binding.identity_status !== 'ACTIVE') return 'DEVICE'
  if (!binding.active_store_id) return 'STORE'
  return 'READY'
})

function activePlatformBinding(store: StoreForSetup, platform: string, platformStoreId: string) {
  return (store.platform_bindings ?? []).find((binding) =>
    binding.status === 'ACTIVE'
      && binding.platform.toLowerCase() === platform.toLowerCase()
      && String(binding.platform_store_id) === String(platformStoreId)
  )
}

function storeOptionLabel(store: StoreForSetup): string {
  const pddBindings = (store.platform_bindings ?? []).filter((binding) =>
    binding.status === 'ACTIVE' && binding.platform.toLowerCase() === observedPlatform
  )
  if (!pddBindings.length) return `${store.store_name} · PDD未绑定`
  return `${store.store_name} · PDD ${pddBindings.map((binding) => binding.platform_store_id).join('、')}`
}

function errorContext(caught: unknown) {
  const value = caught as {
    kind?: string
    code?: string | null
    requestId?: string | null
    status?: number | null
    body?: { request_id?: string; error?: { code?: string; message?: string } }
  }
  return {
    kind: value.kind ?? 'unknown',
    code: value.code || value.body?.error?.code || 'UNKNOWN_BINDING_ERROR',
    requestId: value.requestId || value.body?.request_id || null,
    status: value.status ?? null
  }
}

function issue(caught: unknown, definition: Omit<BindingIssue, 'technical'>): BindingIssue {
  const context = errorContext(caught)
  return {
    ...definition,
    technical: {
      error_code: context.code,
      request_id: context.requestId,
      http_status: context.status,
      agent_version: bootstrap.value?.agent.version ?? null,
      agent_process: bootstrap.value?.agent.process_status ?? null,
      runtime_status: bootstrap.value?.agent.runtime_status ?? null,
      identity_status: bootstrap.value?.binding.identity_status ?? null
    }
  }
}

function bindingFailure(caught: unknown): BindingIssue {
  const { kind, code } = errorContext(caught)
  if (code === 'DEVICE_PAIRING_REQUIRED') {
    return issue(caught, {
      title: '这台电脑还没有连接可信主机',
      message: '账号和密码没有问题。请先完成12位主机连接码配对，再继续使用32位账号绑定许可。',
      owner: '需要您和主机管理员共同确认', action: '搜索客服主机', retry: () => void discoverTrustedHosts(),
      avoid: ['修改客服密码', '重新扫码PDD', '重复申请账号绑定许可'],
      steps: ['请管理员在主机上生成新的12位一次性连接码。', '点击“搜索客服主机”并核对主机名称和地址。', '输入12位连接码并勾选人工确认。', '连接成功后程序会自动重载，再继续绑定客服账号。'],
      adminSteps: ['启动18443 V2 Host Control和18421局域网发现服务。', '向当前客服提供本次屏幕显示的12位连接码；连接码5分钟失效且只能使用一次。']
    })
  }
  if (kind === 'contract' || code === 'CHANNEL_AGENT_RESPONSE_INVALID' || code === 'BINDING_RESPONSE_INVALID') {
    return issue(caught, {
      title: '程序组件版本不一致',
      message: '这不是账号、密码或PDD登录问题，也不是您的操作错误。客服程序和主机服务的版本没有完全匹配。',
      owner: '需要主机管理员处理', action: '重新检测', retry: () => void recheckBindingServices(),
      avoid: ['重新扫码', '修改密码', '重复绑定电脑'],
      steps: ['先点击“重新检测”，确认主机服务是否已经恢复。', '如果仍然显示此问题，点击“复制诊断信息”。', '把复制的内容发给负责AI-CS主机的管理员。', '管理员处理完成后，再点击“重新检测”继续绑定。'],
      adminSteps: ['把AI-CS更新到与ChannelAgent 1.6.0兼容的版本。', '运行 stop_ai_customer_service.ps1 安全停止AI-CS服务。', '运行 start_ai_customer_service.ps1 启动AI-CS服务。', '确认AI-CS和Channel Engine健康检查均通过，再通知客服重新检测。']
    })
  }
  if (kind === 'not_configured' || code === 'CHANNEL_AGENT_INTEGRATION_NOT_CONFIGURED' || code === 'AGENT_CONFIGURATION_INVALID') {
    return issue(caught, {
      title: '客服设备服务还没有配置好', message: '主机地址或Agent运行配置不完整，这不是密码错误。',
      owner: '需要主机管理员处理', action: '重新检测', retry: () => void recheckBindingServices(), avoid: ['重复登录', '重新扫码'],
      steps: ['请把诊断信息发给管理员。', '管理员完成运行配置后，点击“重新检测”。'],
      adminSteps: ['打开ChannelAgent运行配置，检查AI-CS与Channel Engine地址。', '验证服务端口和健康状态后重新启动AI-CS服务。']
    })
  }
  if (kind === 'server_unreachable' || code === 'CHANNEL_ENGINE_UNAVAILABLE' || code === 'CHANNEL_AGENT_SERVER_UNREACHABLE') {
    return issue(caught, {
      title: '设备服务暂时没有连接', message: '当前电脑正常，但暂时联系不上主机服务。',
      owner: '可先自行重试', action: '重新检测', retry: () => void recheckBindingServices(), avoid: ['修改密码', '重新绑定店铺'],
      steps: ['确认电脑网络正常。', '点击“重新检测”。', '仍未恢复时复制诊断信息并联系管理员。'],
      adminSteps: ['检查AI-CS与Channel Engine进程和端口。', '确认局域网、防火墙和服务健康状态。']
    })
  }
  if (kind === 'permission_invalid' || code === 'CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID') {
    return issue(caught, {
      title: '主机接入授权已失效', message: '客服账号没有问题，是AI-CS连接Channel Engine所用的服务授权失效。',
      owner: '需要主机管理员处理', action: '重新检测', retry: () => void recheckBindingServices(), avoid: ['修改客服密码', '重新扫码', '重复绑定电脑'],
      steps: ['复制诊断信息并发给主机管理员。', '管理员更新服务授权后，点击“重新检测”。'],
      adminSteps: ['重新对齐AI-CS与Channel Engine的服务身份引用。', '安全重启相关服务并验证健康状态。']
    })
  }
  if (kind === 'authorization_denied' || code === 'AUTHORIZATION_DENIED' || code === 'CHANNEL_AGENT_BINDING_INVALID') {
    return issue(caught, {
      title: '当前账号不能绑定这台电脑', message: '设备可能已绑定到其他账号，或当前账号没有所选店铺权限。程序不会覆盖原绑定。',
      owner: '需要运营管理员处理', action: '管理员处理后重新检查', retry: () => void recheckBindingServices(), avoid: ['重复申请绑定', '手工修改设备编号'],
      steps: ['请管理员在“运营中心 → 用户管理 → 修改分配”核对客服店铺权限。', '如果设备属于其他账号，请管理员先完成安全解绑。', '处理完成后点击“重新检查”。'], adminSteps: []
    })
  }
  if (code.includes('EXPIRED') || code.includes('USED') || code.includes('BINDING_CODE')) {
    return issue(caught, {
      title: '一次性绑定许可已失效', message: '刚才的安全许可已过期或已经使用，重新申请即可，不需要修改其他设置。',
      owner: '您可以自行处理', action: '重新申请绑定许可', retry: () => void bindDevice(), avoid: ['修改密码', '重新扫码'],
      steps: ['确认仍在使用当前电脑和所选店铺。', '点击“重新申请绑定许可”。'], adminSteps: []
    })
  }
  if (code.includes('DEVICE')) {
    return issue(caught, {
      title: '设备信息不匹配', message: '许可中的电脑与当前电脑不一致，程序已安全停止绑定。',
      owner: '请先重新检测', action: '重新读取本机信息', retry: () => void refresh(), avoid: ['手工填写Agent ID或Device ID'],
      steps: ['点击“重新读取本机信息”。', '仍不一致时复制诊断信息并联系管理员。'], adminSteps: []
    })
  }
  if (code === 'CHANNEL_AGENT_NOT_REGISTERED') {
    return issue(caught, {
      title: '本机Agent还没有注册', message: '客户端已经打开，但主机暂时没有识别到这台电脑。',
      owner: '可先自行重试', action: '重新检测', retry: () => void recheckBindingServices(), avoid: ['重新扫码'],
      steps: ['等待几秒后点击“重新检测”。', '仍未识别时复制诊断信息并联系管理员检查Agent连接。'], adminSteps: []
    })
  }
  if (code.startsWith('IDENTITY_SYNC')) {
    return issue(caught, {
      title: '绑定已完成，状态同步暂时失败', message: '程序会保留已经完成的绑定，不会再次绑定或覆盖身份。',
      owner: '可先自行重试', action: '重新同步状态', retry: () => void bindDevice(), avoid: ['重复绑定电脑'],
      steps: ['点击“重新同步状态”。', '仍失败时复制诊断信息并联系管理员。'], adminSteps: []
    })
  }
  return issue(caught, {
    title: '设备绑定没有完成', message: '程序已安全停止，没有修改店铺或PDD状态。请先重新检测，不要重复绑定。',
    owner: '请先重新检测', action: '重新检测', retry: () => void recheckBindingServices(), avoid: ['重复扫码', '连续点击绑定'],
    steps: ['点击“重新检测”。', '仍有问题时复制诊断信息并联系管理员。'], adminSteps: []
  })
}

function clearAutomaticRecheck() {
  if (automaticRecheckTimer !== null) window.clearTimeout(automaticRecheckTimer)
  automaticRecheckTimer = null
}

function showBindingFailure(caught: unknown) {
  error.value = bindingFailure(caught)
  const { kind, code } = errorContext(caught)
  if (
    (kind === 'contract' || code === 'CHANNEL_AGENT_RESPONSE_INVALID')
    && automaticRechecks.value < 3
  ) {
    automaticRechecks.value += 1
    clearAutomaticRecheck()
    automaticRecheckTimer = window.setTimeout(() => void recheckBindingServices(true), 5000)
  }
}

async function recheckBindingServices(automatic = false) {
  const storeId = selectedStoreId.value
  if (!storeId || busy.value) return
  busy.value = true
  if (!automatic) clearAutomaticRecheck()
  try {
    await desktopAgentClient.getStatus(storeId)
    automaticRechecks.value = 0
    clearAutomaticRecheck()
    await refresh()
  } catch (caught) {
    showBindingFailure(caught)
  } finally {
    busy.value = false
  }
}

async function copyDiagnostic(current: BindingIssue) {
  const text = JSON.stringify({
    schema_version: 'channel-agent-binding-diagnostic.v1', checked_at: new Date().toISOString(),
    issue: current.title, ...current.technical
  }, null, 2)
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    area.remove()
  }
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 1800)
}

async function refresh() {
  loading.value = true
  error.value = null
  copied.value = false
  try {
    bootstrap.value = await fetchChannelAgentBootstrap()
    const observed = bootstrap.value.binding.observed_store_id
    selectedStoreCode.value = bootstrap.value.binding.active_store_id
      || (observed ? matchingObservedStore.value?.store_code ?? '' : '')
      || authorizedStores.value[0]?.store_code
      || ''
    if (stage.value === 'READY') {
      setTimeout(() => void router.replace('/workspace'), 500)
    }
  } catch (caught) {
    error.value = issue(caught, {
      title: '暂时无法读取客户端状态', message: '客服助手暂时读不到本机Agent状态，请先重新检查。',
      owner: '可先自行重试', action: '重新检查', retry: () => void refresh(), avoid: ['重新扫码'],
      steps: ['点击“重新检查”。', '仍未恢复时复制诊断信息并联系管理员。'], adminSteps: []
    })
  } finally {
    loading.value = false
  }
}

function applyBootstrap(next: ChannelAgentBootstrap) {
  bootstrap.value = next
  const observed = next.binding.observed_store_id
  selectedStoreCode.value = next.binding.active_store_id
    || (observed ? matchingObservedStore.value?.store_code ?? '' : '')
    || authorizedStores.value[0]?.store_code
    || ''
}

async function recheckStore() {
  if (busy.value) return
  busy.value = true
  error.value = null
  storeCheckMessage.value = '正在检查专用Edge和PDD客服工作台，请稍候…'
  try {
    let observed = ''
    for (let attempt = 0; attempt < 6; attempt += 1) {
      applyBootstrap(await fetchChannelAgentBootstrap())
      observed = bootstrap.value?.binding.observed_store_id ?? ''
      if (observed) break
      if (attempt < 5) await new Promise((resolve) => window.setTimeout(resolve, 700))
    }
    if (observed) {
      const matched = matchingObservedStore.value
      storeCheckMessage.value = matched
        ? `已识别PDD店铺 ${observed}，请核对后确认“${matched.store_name}”。`
        : `已识别PDD店铺 ${observed}，但没有找到对应的有效授权绑定。`
    } else {
      storeCheckMessage.value = '尚未读取到PDD店铺。请保持专用Edge中的客服工作台打开，然后再次检查。'
    }
  } catch (caught) {
    storeCheckMessage.value = ''
    error.value = issue(caught, {
      title: '重新检查没有完成', message: '客户端暂时无法读取专用Edge或PDD工作台状态。',
      owner: '可以重新尝试', action: '重新检查', retry: () => void recheckStore(), avoid: ['重新扫码', '修改店铺资料'],
      steps: ['确认Agent专用Edge仍然打开。', '确认PDD客服工作台标签页仍在。', '再次点击“重新检查”。'], adminSteps: []
    })
  } finally {
    busy.value = false
  }
}

async function discoverTrustedHosts() {
  if (busy.value) return
  busy.value = true
  discoveringHosts.value = true
  hostDiscoveryAttempted.value = true
  error.value = null
  try {
    const result = await discoverChannelAgentHosts()
    trustedHosts.value = result.hosts
    selectedHostId.value = String(result.hosts[0]?.hostId ?? '')
    if (!result.hosts.length) throw new Error('HOST_DISCOVERY_EMPTY')
  } catch (caught) {
    trustedHosts.value = []
    error.value = issue(caught, {
      title: '暂时没有发现客服主机',
      message: '这台电脑没有搜索到可配对的18443主机。请主机管理员启动设备服务并生成新的连接码。',
      owner: '需要主机管理员处理', action: '重新搜索', retry: () => void discoverTrustedHosts(),
      avoid: ['修改密码', '重新登录PDD'],
      steps: ['请管理员确认18443设备服务和18421发现服务正在运行。', '请管理员生成新的12位一次性连接码。', '回到这里点击“重新搜索”。'],
      adminSteps: ['运行正式ChannelAgent主机启动器，确认Host Control与发现服务均为健康状态。']
    })
  } finally {
    busy.value = false
    discoveringHosts.value = false
  }
}

async function pairTrustedHost() {
  if (busy.value || !selectedHostId.value || hostPairingCodeKind.value !== 'READY' || !hostPairingConfirmed.value) return
  busy.value = true
  error.value = null
  try {
    await pairChannelAgentHost({
      host_id: selectedHostId.value,
      pairing_code: normalizedHostPairingCode.value,
      human_confirmed: true
    })
    hostPairingCode.value = ''
    window.setTimeout(() => window.location.reload(), 2500)
  } catch (caught) {
    error.value = issue(caught, {
      title: '主机连接没有完成',
      message: '连接码可能已过期、已使用，或与所选主机不匹配。程序没有保存该连接码。',
      owner: '可以重新申请连接码', action: '重新搜索', retry: () => void discoverTrustedHosts(),
      avoid: ['重复输入旧连接码', '修改客服密码'],
      steps: ['请管理员重新生成12位连接码。', '重新搜索并核对主机。', '输入新连接码后再次人工确认。'],
      adminSteps: []
    })
  } finally {
    busy.value = false
  }
}

async function bindDevice() {
  const agentId = bootstrap.value?.binding.agent_id
  const deviceId = bootstrap.value?.binding.device_id
  const storeId = selectedStoreId.value
  if (!agentId || !deviceId || !storeId || busy.value) return
  busy.value = true
  error.value = null
  automaticRechecks.value = 0
  clearAutomaticRecheck()
  try {
    if (['UNBOUND', 'REGISTERED'].includes(bootstrap.value?.binding.identity_status || '')) {
      actionText.value = '正在申请安全许可…'
      const grant = await desktopAgentClient.requestBindingGrant({ agentId, deviceId, storeId })
      actionText.value = '正在绑定这台电脑…'
      await enrollChannelAgentDevice(grant.bindingCode)
    }
    actionText.value = '正在启用客服设备…'
    await desktopAgentClient.activateBinding({ agentId, deviceId, storeId })
    actionText.value = '正在同步最新状态…'
    await syncChannelAgentIdentity()
    await refresh()
  } catch (caught) {
    showBindingFailure(caught)
  } finally {
    busy.value = false
  }
}

async function bindWithAdminCode() {
  const agentId = bootstrap.value?.binding.agent_id
  const deviceId = bootstrap.value?.binding.device_id
  const storeId = selectedStoreId.value
  const bindingCode = normalizedAdminBindingCode.value
  if (!agentId || !deviceId || !storeId || bindingCode.length !== 32 || busy.value) return
  busy.value = true
  error.value = null
  try {
    actionText.value = '正在验证一次性绑定码…'
    await enrollChannelAgentDevice(bindingCode)
    adminBindingCode.value = ''
    actionText.value = '正在启用客服设备…'
    await desktopAgentClient.activateBinding({ agentId, deviceId, storeId })
    actionText.value = '正在同步最新状态…'
    await syncChannelAgentIdentity()
    await refresh()
  } catch (caught) {
    adminBindingCode.value = ''
    showBindingFailure(caught)
  } finally {
    busy.value = false
  }
}

async function confirmStore() {
  const observed = bootstrap.value?.binding.observed_store_id
  if (!observed || !selectedStoreCode.value) return
  const selected = stores.value.find((store) => store.store_code === selectedStoreCode.value)
  const selectedBinding = selected
    ? activePlatformBinding(selected, observedPlatform, observed)
    : undefined
  if (!selectedBinding) {
    const matched = matchingObservedStore.value
    error.value = issue(new Error('PDD_STORE_MISMATCH'), {
      title: '店铺不一致，已安全停止',
      message: matched
        ? `PDD当前店铺号“${observed}”对应“${matched.store_name}”，您当前选择的是“${selected?.store_name ?? selectedStoreCode.value}”。`
        : `PDD当前店铺号“${observed}”没有对应的有效AI-CS授权店铺绑定。程序不会通过店铺名称猜测身份。`,
      owner: '需要您确认店铺', action: '重新检查', retry: () => void refresh(), avoid: ['继续进入助手'],
      steps: matched
        ? ['在下拉框选择程序已精确匹配的授权店铺。', '核对店铺名称和PDD店铺号。', '再次点击“确认当前店铺”。']
        : ['确认PDD当前登录店铺号。', '请管理员在店铺管理中登记该PDD平台账号绑定。', '管理员处理后点击“重新检查”。'],
      adminSteps: matched ? [] : ['在AI-CS店铺的平台绑定中新增 pinduoduo 外部店铺号，并由管理员人工确认。']
    })
    return
  }
  busy.value = true
  error.value = null
  try {
    const agentId = bootstrap.value?.binding.agent_id
    const deviceId = bootstrap.value?.binding.device_id
    if (!selected || !agentId || !deviceId) {
      throw new Error('CHANNEL_AGENT_IDENTITY_INCOMPLETE')
    }
    await desktopAgentClient.selectActiveStore({
      agentId,
      deviceId,
      storeId: selected.store_id,
      platform: observedPlatform,
      observedPlatformStoreId: observed
    })
    await syncChannelAgentIdentity()
    if (selected) await auth.setDefaultStore(selected.store_id)
    await refresh()
  } catch (caught) {
    error.value = issue(caught, {
      title: '当前店铺还不能确认', message: '程序没有更改当前店铺，请重新检查PDD登录状态和店铺选择。',
      owner: '需要您确认店铺', action: '重新检查', retry: () => void refresh(), avoid: ['强制进入助手'],
      steps: ['确认PDD已经人工登录。', '确认选择的店铺与PDD页面一致。', '点击“重新检查”。'], adminSteps: []
    })
  } finally {
    busy.value = false
  }
}

onMounted(() => void refresh())
onBeforeUnmount(() => clearAutomaticRecheck())
</script>

<style scoped>
.setup-page{display:grid;min-height:100vh;place-items:center;padding:24px;background:radial-gradient(circle at 80% 10%,#2d5d91,transparent 35%),linear-gradient(145deg,#102a4e,#183e6c);font-family:"Segoe UI","Microsoft YaHei",sans-serif}.setup-card{width:min(760px,100%);box-sizing:border-box;padding:32px;border-radius:22px;background:#f8fbff;box-shadow:0 28px 70px #061a342e;color:#18314f}.setup-card header{display:flex;align-items:center;gap:14px}.brand{display:grid;width:46px;height:46px;place-items:center;border-radius:14px;background:#58c9ad;color:#10264a;font-weight:900}.setup-card h1,.setup-card h2,.setup-card p{margin:0}.setup-card h1{margin-top:3px;font-size:25px}.setup-card header small{color:#6d8097}.safe{margin-left:auto;padding:7px 10px;border-radius:999px;background:#e7f6ee;color:#16704a;font-size:12px;font-weight:800}.progress{display:grid;grid-template-columns:repeat(4,1fr);margin:27px 0;padding:0;list-style:none}.progress li{position:relative;display:grid;justify-items:center;gap:7px;color:#78899c;font-size:12px}.progress li:not(:last-child)::after{content:"";position:absolute;top:13px;left:calc(50% + 17px);width:calc(100% - 34px);height:2px;background:#dce6f1}.progress i{z-index:1;display:grid;width:27px;height:27px;place-items:center;border-radius:50%;background:#e9eff5;font-style:normal;font-weight:800}.progress .active{color:#2366ad;font-weight:800}.progress .active i{background:#286bb8;color:#fff;box-shadow:0 0 0 4px #dceafa}.progress .done{color:#178157}.progress .done i{background:#dff4e9;color:#16704a}.state-box,.problem-box,.task-box,.success-box{padding:24px;border:1px solid #d8e4f0;border-radius:15px;background:#fff}.task-heading{display:flex;justify-content:space-between;color:#2869b5;font-size:12px;font-weight:800}.task-box h2,.problem-box h2,.success-box h2{margin:8px 0;font-size:21px}.task-box>p,.problem-box>p,.success-box>p{color:#60738a;line-height:1.65}.task-box dl{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}.task-box dl div{padding:11px;border-radius:10px;background:#f2f6fa}.task-box dt{color:#75869a;font-size:11px}.task-box dd{margin:5px 0 0;font-weight:800}.task-box select,.store-select select{width:100%;box-sizing:border-box;padding:8px;border:1px solid #bfd0e2;border-radius:8px;background:#fff}.confirmation,.store-select{display:flex;align-items:center;gap:8px;margin:16px 0;color:#38516d;font-size:13px}.store-select{display:grid}.primary,.secondary,.error button{padding:11px 16px;border:0;border-radius:9px;font-weight:800;cursor:pointer}.primary{background:#286bb8;color:#fff}.primary:disabled{opacity:.5}.secondary,.error button{border:1px solid #bfd0e2;background:#fff;color:#285b91}.button-row{display:flex;gap:10px}.error{display:flex;align-items:center;gap:10px;margin:14px 0 0;padding:12px;border-radius:10px;background:#fff0ef;color:#b42318}.error span{flex:1}.error strong{flex:none}.setup-card footer{margin-top:17px;color:#6d8094;font-size:12px;text-align:center}@media(max-width:700px){.setup-card{padding:22px}.safe{display:none}.task-box dl{grid-template-columns:1fr}.progress li span{font-size:10px}.error{align-items:flex-start;flex-direction:column}}
.error-guide{margin-top:14px;padding:18px;border:1px solid #f1a7a0;border-radius:14px;background:#fff8f7;color:#5e2b28}.error-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.error-heading small{color:#b42318;font-weight:800}.error-heading h2{margin:3px 0 0;font-size:19px;color:#8f1f17}.error-heading>span{padding:6px 9px;border-radius:999px;background:#ffe2df;color:#a5241b;font-size:11px;font-weight:800}.error-guide>p{margin:10px 0;color:#67413e;line-height:1.6}.not-required{padding:10px 12px;border-radius:9px;background:#fff1d8;color:#7b4c09;font-size:13px}.guide-steps{margin:14px 0;padding:13px;border-radius:10px;background:#fff}.guide-steps ol,.admin-guide ol{margin:8px 0 0;padding-left:22px;line-height:1.8}.error-actions{display:flex;gap:10px;margin-top:13px}.admin-guide,.technical-guide{margin-top:12px;padding-top:10px;border-top:1px dashed #e7b8b3}.admin-guide summary,.technical-guide summary{cursor:pointer;color:#285b91;font-weight:800}.technical-guide dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:10px 0 0}.technical-guide dl div{padding:8px;border-radius:7px;background:#fff}.technical-guide dt{color:#77869a;font-size:10px}.technical-guide dd{margin:3px 0 0;overflow-wrap:anywhere;font-family:Consolas,monospace;font-size:11px}@media(max-width:700px){.error-heading,.error-actions{align-items:stretch;flex-direction:column}.technical-guide dl{grid-template-columns:1fr}}
.admin-code-entry{margin-top:16px;padding-top:14px;border-top:1px dashed #c7d6e5}.admin-code-entry summary{cursor:pointer;color:#285b91;font-weight:800}.admin-code-entry p{margin:10px 0;color:#60738a;font-size:12px;line-height:1.55}.admin-code-entry label{display:grid;gap:6px;color:#38516d;font-size:12px}.admin-code-entry input{box-sizing:border-box;width:100%;padding:10px;border:1px solid #bfd0e2;border-radius:8px;background:#fff;font:700 14px/1 Consolas,monospace;letter-spacing:.06em;text-transform:uppercase}.admin-code-entry button{margin-top:10px}
 .pairing-hosts{display:grid;gap:10px;margin-top:16px}.pairing-hosts>label:not(.confirmation){display:flex;align-items:center;gap:10px;padding:12px;border:1px solid #d8e4f0;border-radius:10px;background:#f7faff}.pairing-hosts>label.selected{border-color:#2a6cb8;background:#edf5ff}.pairing-hosts label span{display:grid}.pairing-hosts small{margin-top:3px;color:#6d8094}.pairing-hosts .pairing-code{display:grid!important;gap:7px;color:#38516d;font-size:12px}.pairing-code input{box-sizing:border-box;width:100%;padding:11px;border:1px solid #bfd0e2;border-radius:8px;background:#fff;font:700 14px/1 Consolas,monospace;letter-spacing:.06em;text-transform:uppercase}.pairing-code .code-hint{display:block;padding:9px 10px;border-radius:8px;background:#e7f6ee;color:#16704a;font-weight:700;line-height:1.5}.pairing-code .code-hint.invalid{background:#fff1d8;color:#8a5208}.pairing-help{margin-top:14px!important;padding:12px;border-radius:9px;background:#fff1d8;color:#7b4c09!important;font-size:13px}

/*
 * The desktop shell intentionally keeps the application root from scrolling.
 * Device setup is the exception: novice guidance and diagnostics can be taller
 * than the window, so this view owns its vertical scroll container.
 */
.setup-page{
  box-sizing:border-box;
  display:flex;
  width:100%;
  height:100%;
  min-height:0;
  align-items:center;
  flex-direction:column;
  overflow-x:hidden;
  overflow-y:auto;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
  padding:clamp(12px,3vh,24px) 24px max(24px,env(safe-area-inset-bottom));
}
.setup-card{
  flex:none;
  margin:auto 0;
}
.setup-page::-webkit-scrollbar{width:10px}
.setup-page::-webkit-scrollbar-track{background:#102a4e}
.setup-page::-webkit-scrollbar-thumb{border:3px solid transparent;border-radius:999px;background:#9fb4ca;background-clip:padding-box}
.check-result{margin-top:12px!important;padding:10px 12px;border-radius:9px;background:#edf5ff;color:#285b91!important;font-size:13px;font-weight:700;line-height:1.55!important}

@media(max-height:900px){
  .setup-card{padding:24px}
  .progress{margin:18px 0}
  .state-box,.problem-box,.task-box,.success-box{padding:20px}
  .error-guide{padding:16px}
}

@media(max-height:720px){
  .setup-page{padding:10px 14px 18px}
  .setup-card{padding:18px;border-radius:16px}
  .setup-card h1{font-size:21px}
  .progress{margin:14px 0}
  .state-box,.problem-box,.task-box,.success-box{padding:16px}
  .task-box dl{margin:14px 0}
  .error-guide{padding:14px}
  .setup-card footer{margin-top:12px}
}
</style>
