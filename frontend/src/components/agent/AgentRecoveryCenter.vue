<template>
  <aside class="recovery" :class="{ expanded }" data-testid="agent-recovery-center">
    <header>
      <div>
        <span class="eyebrow">运行状态助手</span>
        <h2>{{ statusTitle }}</h2>
        <p>{{ statusDescription }}</p>
      </div>
      <span class="status" :class="doctor?.overall.toLowerCase()"><i></i>{{ doctor?.overall === 'PASS' ? '运行正常' : doctor?.overall === 'WARNING' ? '需要关注' : '需要处理' }}</span>
    </header>

    <div class="actions">
      <button type="button" class="primary" data-testid="doctor-repair" :disabled="busy || !hasRepairable" @click="repair">{{ busy ? '正在处理…' : '一键修复' }}</button>
      <button type="button" class="secondary" data-testid="doctor-recheck" :disabled="busy" @click="runDoctor(true)">{{ busy ? '检测中…' : '重新检测' }}</button>
      <button type="button" class="secondary" data-testid="config-toggle" @click="showConfig = !showConfig">{{ showConfig ? '收起配置' : '运行配置' }}</button>
      <button v-if="expanded" type="button" class="link" @click="copyDiagnostics">复制诊断信息</button>
    </div>

    <p v-if="notice" class="notice" role="status">{{ notice }}</p>

    <section v-if="expanded && firstUse" class="onboarding-guide" aria-label="首次使用步骤">
      <div class="guide-title"><strong>首次使用设置</strong><span>完成后即可进入客服助手</span></div>
      <ol>
        <li v-for="(step, index) in onboardingSteps" :key="step" :class="{ active: index + 1 === currentStep, done: index + 1 < currentStep }"><i>{{ index + 1 < currentStep ? '✓' : index + 1 }}</i><span>{{ step }}</span></li>
      </ol>
    </section>

    <section v-if="expanded" class="diagnostics" aria-label="运行检查">
      <div class="diagnostic-summary">
        <strong>{{ issueCount ? `现在需要完成 ${issueCount} 步` : '全部检查正常' }}</strong>
        <span>{{ pendingCount ? `随后完成 ${pendingCount} 步` : '有问题的项目已排在前面' }}</span>
      </div>
      <details v-for="group in diagnosticGroups" :key="group.key" class="diagnostic-group" :open="group.issueCount > 0">
        <summary>
          <span class="group-icon">{{ group.icon }}</span>
          <span class="group-title"><strong>{{ group.title }}</strong><small>{{ group.description }}</small></span>
          <span class="group-result" :class="group.issueCount ? 'has-issue' : group.pendingCount ? 'has-pending' : 'all-pass'">{{ group.issueCount ? `${group.issueCount} 项需处理` : group.pendingCount ? '等待上一步' : '全部正常' }}</span>
        </summary>
        <div class="group-items">
          <details
            v-for="item in group.items"
            :key="item.component"
            class="diagnostic-item"
            :class="[item.status.toLowerCase(), { dependent: isDependent(item) }]"
            :data-status="item.status"
          >
            <summary>
              <span class="component-name"><i aria-hidden="true">{{ statusIcon(item.status) }}</i>{{ friendlyName(item.component) }}</span>
              <span class="component-status">{{ isDependent(item) ? '等待上一步' : friendlyStatus(item.status) }}</span>
            </summary>
            <div class="diagnostic-detail">
              <p><strong>当前情况</strong>{{ item.reason }}</p>
              <p><strong>怎么处理</strong>{{ item.next_action }}</p>
              <ol v-if="resolutionSteps(item).length" class="resolution-steps">
                <li v-for="step in resolutionSteps(item)" :key="step">{{ step }}</li>
              </ol>
              <button
                v-if="!isDependent(item) && item.scope === 'ONBOARDING'"
                type="button"
                class="issue-action"
                @click="emit('onboarding', item.error_code.includes('STORE') ? 'STORE' : 'LOGIN')"
              >{{ item.error_code.includes('STORE') ? '登录后确认店铺' : '登录后开始绑定' }}</button>
              <details class="technical-detail">
                <summary>查看技术信息</summary>
                <code>{{ item.error_code }}</code>
                <pre v-if="Object.keys(item.technical).length">{{ JSON.stringify(item.technical, null, 2) }}</pre>
              </details>
            </div>
          </details>
        </div>
      </details>
    </section>

    <section v-if="showConfig" class="config-panel" data-testid="config-panel">
      <div class="section-title">
        <div><span class="eyebrow">手动配置</span><h3>连接与运行参数</h3></div>
        <button type="button" class="secondary" :disabled="busy" @click="discoverHosts">发现主机</button>
      </div>

      <div v-if="hosts.length" class="host-list">
        <label v-for="host in hosts" :key="String(host.hostId)" :class="{ selected: selectedHost === host.hostId }">
          <input v-model="selectedHost" type="radio" :value="host.hostId" />
          <span><strong>{{ host.hostName }}</strong><small>{{ host.serverAddress }} · {{ host.environment }}</small></span>
        </label>
        <input v-model.trim="pairingCode" placeholder="输入一次性连接码" autocomplete="off" />
        <label class="confirmation"><input v-model="pairingConfirmed" type="checkbox" />我已核对主机信息并确认绑定</label>
        <button type="button" class="primary" :disabled="busy || !selectedHost || !pairingCode || !pairingConfirmed" @click="pairHost">确认连接主机</button>
      </div>

      <div class="form-grid">
        <label>Channel Engine 地址<input v-model.trim="form.server_url" placeholder="https://主机:端口" /></label>
        <label>AI-CS 身份服务地址<input v-model.trim="form.ai_cs_platform_url" placeholder="https://主机:端口" /></label>
        <label>连接超时（秒）<input v-model.number="form.connect_timeout_seconds" type="number" min="0.1" max="30" step="0.1" /></label>
        <label>心跳间隔（秒）<input v-model.number="form.heartbeat_interval_seconds" type="number" min="0.05" max="300" step="1" /></label>
      </div>

      <details class="advanced">
        <summary>高级配置</summary>
        <p>高级配置会影响浏览器和客服助手 Runtime。请输入下方确认语句后才可保存。</p>
        <input v-model="advancedConfirmation" data-testid="advanced-confirmation" placeholder="请输入：继续高级配置" />
        <div class="form-grid">
          <label>运行模式<select v-model="form.runtime_mode"><option>MOCK</option><option>SIMULATOR</option><option>STAGING</option></select></label>
          <label class="check"><input v-model="form.browser_enabled" type="checkbox" />启用 Browser Runtime</label>
          <label class="check"><input v-model="form.pdd_login_observation_enabled" type="checkbox" />启用 PDD 登录观察</label>
          <label class="check"><input v-model="form.customer_assistant_enabled" type="checkbox" />启用客服助手</label>
          <label>PDD 官方登录页<input v-model.trim="form.pdd_login_url" /></label>
          <label>PDD 客服工作台<input v-model.trim="form.pdd_customer_service_url" /></label>
          <label>连续消息合并窗口（秒）<input v-model.number="form.conversation_buffer_window_seconds" type="number" min="1" max="30" /></label>
        </div>
      </details>

      <div class="readonly">
        <h4>设备与绑定（只读）</h4>
        <dl><template v-for="(value, key) in config?.read_only" :key="key"><dt>{{ readonlyLabel(key) }}</dt><dd>{{ display(value) }}</dd></template></dl>
      </div>

      <div class="safety-locks">
        <h4>永久安全锁</h4>
        <span>✓ 必须人工审批</span><span>✓ 禁止自动回复</span><span>✓ 禁止真实发送</span><span>✓ 禁止真实平台自动激活</span>
      </div>

      <div class="config-actions">
        <button type="button" class="secondary" :disabled="busy" @click="validateConfig">校验配置</button>
        <button type="button" class="primary" :disabled="busy" @click="saveConfig">校验并保存</button>
      </div>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  discoverChannelAgentHosts,
  fetchChannelAgentConfig,
  fetchChannelAgentDoctor,
  fetchChannelAgentRepair,
  pairChannelAgentHost,
  saveChannelAgentConfig,
  startChannelAgentRepair,
  validateChannelAgentConfig,
  type ChannelAgentConfigCenter,
  type ChannelAgentDoctor
} from '@/api/channelAgentDesktopClient'

const emit = defineEmits<{
  blocked: [value: boolean]
  status: [value: { overall: 'PASS' | 'WARNING' | 'BLOCKED'; issues: number }]
  onboarding: [value: 'LOGIN' | 'STORE']
}>()
const doctor = ref<ChannelAgentDoctor | null>(null)
const config = ref<ChannelAgentConfigCenter | null>(null)
const busy = ref(false)
const showConfig = ref(false)
const forceExpanded = ref(false)
const notice = ref('')
const advancedConfirmation = ref('')
const hosts = ref<Array<Record<string, unknown>>>([])
const selectedHost = ref<unknown>('')
const pairingCode = ref('')
const pairingConfirmed = ref(false)
const form = reactive<Record<string, any>>({})

const expanded = computed(() => forceExpanded.value || showConfig.value || doctor.value?.overall === 'BLOCKED')
const hasRepairable = computed(() => doctor.value?.components.some((item) => item.repairable) === true)
const sortedComponents = computed(() => [...(doctor.value?.components ?? [])].sort((left, right) => {
  const priority = { BLOCKED: 0, WARNING: 1, PASS: 2 }
  return Number(isDependent(left)) - Number(isDependent(right)) || priority[left.status] - priority[right.status]
}))
const issueCount = computed(() => sortedComponents.value.filter((item) => item.status !== 'PASS' && !isDependent(item)).length)
const pendingCount = computed(() => sortedComponents.value.filter((item) => item.status !== 'PASS' && isDependent(item)).length)
const onboardingSteps = ['连接服务器', '绑定设备', '选择店铺', '进入客服助手']
const currentStep = computed(() => {
  const codes = new Set(doctor.value?.components.filter((item) => item.status !== 'PASS').map((item) => item.error_code) ?? [])
  if ([...codes].some((code) => code.includes('SERVICE_') || code.includes('CONFIG_') || code.includes('AI_CS'))) return 1
  if ([...codes].some((code) => code.includes('IDENTITY') || code.includes('DEVICE'))) return 2
  if ([...codes].some((code) => code.includes('STORE'))) return 3
  return 4
})
const firstUse = computed(() => currentStep.value < 4)
const diagnosticGroups = computed(() => {
  const definitions = [
    { key: 'device', title: '设备与账号', icon: '▣', description: '本机配置、设备身份和工作店铺', match: ['本地配置文件', 'ChannelAgent进程', '设备注册与身份绑定', '当前店铺绑定'] },
    { key: 'service', title: '服务连接', icon: '◉', description: 'AI服务、Channel Engine和安全连接', match: ['AI-CS身份服务', 'Channel Engine', '客服助手本地代理', '人工审批和发送安全'] },
    { key: 'environment', title: '工作环境', icon: '▤', description: 'Edge浏览器和PDD登录环境', match: ['Edge运行环境', 'PDD Session状态'] }
  ]
  return definitions.map((definition) => {
    const items = sortedComponents.value.filter((item) => definition.match.includes(item.component))
    return {
      ...definition,
      items,
      issueCount: items.filter((item) => item.status !== 'PASS' && !isDependent(item)).length,
      pendingCount: items.filter((item) => item.status !== 'PASS' && isDependent(item)).length
    }
  }).filter((group) => group.items.length).sort((left, right) => {
    const rank = (group: { issueCount: number; pendingCount: number }) => group.issueCount ? 0 : group.pendingCount ? 1 : 2
    return rank(left) - rank(right)
  })
})
const statusTitle = computed(() => doctor.value?.overall === 'BLOCKED'
  ? doctor.value.login_allowed ? '首次使用，需要完成设置' : '需要先解决运行故障'
  : doctor.value?.overall === 'WARNING' ? '可以使用，部分项目需确认' : '运行环境已准备好')
const statusDescription = computed(() => doctor.value?.overall === 'BLOCKED'
  ? doctor.value.login_allowed
    ? '这不是密码错误。请先登录客服账号，程序会按顺序引导绑定电脑和确认店铺。'
    : '当前服务或配置异常，请按下方提示处理后再登录。'
  : doctor.value?.overall === 'WARNING' ? '当前不影响登录，建议在空闲时处理提醒项目。' : '各项服务运行正常，可以登录并开始工作。')

function applyConfig(value: ChannelAgentConfigCenter) {
  config.value = value
  Object.assign(form, value.basic ?? {}, value.advanced ?? {})
}

async function runDoctor(deep = false) {
  busy.value = true
  notice.value = deep ? '正在执行完整检测…' : '正在快速检测…'
  try {
    doctor.value = await fetchChannelAgentDoctor(deep)
    emit('blocked', doctor.value.login_allowed === false)
    emit('status', { overall: doctor.value.overall, issues: issueCount.value })
    notice.value = doctor.value.overall === 'PASS' ? '检测通过。' : doctor.value.overall === 'WARNING' ? '检测完成，有需要关注的项目。' : '检测完成，请按下方提示处理。'
  } catch {
    doctor.value = localDoctorUnavailable()
    forceExpanded.value = true
    emit('blocked', true)
    emit('status', { overall: 'BLOCKED', issues: 1 })
    notice.value = '客服端后台暂时没有连接。请按下方步骤恢复；这不是账号或密码错误。'
  } finally {
    busy.value = false
  }
}

async function loadConfig() {
  try { applyConfig(await fetchChannelAgentConfig()) } catch {
    if (doctor.value?.components[0]?.error_code !== 'CHANNEL_AGENT_LOCAL_API_UNAVAILABLE') {
      notice.value = '无法读取本地配置。'
    }
  }
}

function localDoctorUnavailable(): ChannelAgentDoctor {
  return {
    schema_version: 'channel-agent-doctor.v1',
    overall: 'BLOCKED',
    checked_at: new Date().toISOString(),
    mode: 'QUICK',
    auto_expand: true,
    safe_to_continue: false,
    login_allowed: false,
    sanitized: true,
    components: [{
      component: '客服助手本地代理',
      status: 'BLOCKED',
      status_label: '需要恢复',
      error_code: 'CHANNEL_AGENT_LOCAL_API_UNAVAILABLE',
      reason: '客服助手窗口没有连接到本机 ChannelAgent 后台。常见原因是窗口关闭后旧的一次性会话已经失效，或 Agent 尚未完成启动。',
      checked_at: new Date().toISOString(),
      repairable: false,
      next_action: '先关闭当前助手窗口，再从右下角托盘重新打开；如果仍未恢复，请使用托盘中的“检查并恢复连接”。',
      scope: 'LOGIN',
      technical: { faultId: 'LOCAL_ASSISTANT_SESSION_UNAVAILABLE' }
    }]
  }
}

function payload() {
  const original = { ...(config.value?.basic ?? {}), ...(config.value?.advanced ?? {}) }
  const changes: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(form)) if (original[key] !== value) changes[key] = value
  return { changes, advanced_confirmation: advancedConfirmation.value }
}

async function validateConfig() {
  busy.value = true
  try {
    const result = await validateChannelAgentConfig(payload())
    notice.value = result.valid ? '配置格式和服务连通性均通过。' : '配置未通过，请根据标记字段修正。'
  } catch (error) { notice.value = localErrorMessage(error) } finally { busy.value = false }
}

async function saveConfig() {
  busy.value = true
  try {
    const result = await saveChannelAgentConfig(payload())
    notice.value = result.reload_requested ? '配置已保存，Agent 正在安全重载；PDD 窗口和 Session 保持不变。' : '配置已保存并立即生效。'
    await loadConfig()
    setTimeout(() => void runDoctor(true), 800)
  } catch (error) { notice.value = localErrorMessage(error) } finally { busy.value = false }
}

async function repair() {
  busy.value = true
  try {
    const started = await startChannelAgentRepair()
    notice.value = '正在按安全顺序修复…'
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 350))
      const status = await fetchChannelAgentRepair(started.repair_id)
      if (status.status !== 'RUNNING') {
        notice.value = String(status.message ?? '修复任务已结束。')
        if (status.requires_human) forceExpanded.value = true
        else setTimeout(() => void runDoctor(true), 900)
        return
      }
    }
    notice.value = '修复仍在进行，请稍后重新检测。'
  } catch (error) { notice.value = localErrorMessage(error) } finally { busy.value = false }
}

async function discoverHosts() {
  busy.value = true
  try {
    hosts.value = (await discoverChannelAgentHosts()).hosts
    notice.value = hosts.value.length ? '请选择并核对主机，再输入连接码确认绑定。' : '未发现主机，请确认主机端已启动且处于同一局域网。'
  } catch (error) { notice.value = localErrorMessage(error) } finally { busy.value = false }
}

async function pairHost() {
  busy.value = true
  try {
    await pairChannelAgentHost({ host_id: String(selectedHost.value), pairing_code: pairingCode.value, human_confirmed: true })
    pairingCode.value = ''
    notice.value = '主机绑定完成，Agent 正在安全重载。'
  } catch (error) { notice.value = localErrorMessage(error) } finally { busy.value = false }
}

async function copyDiagnostics() {
  if (!doctor.value) return
  await navigator.clipboard?.writeText(JSON.stringify(doctor.value, null, 2))
  notice.value = '已复制脱敏诊断信息。'
}

function localErrorMessage(error: unknown): string {
  const value = error as { body?: { error?: { code?: string; message?: string } } }
  return value.body?.error?.message || `操作未完成（${value.body?.error?.code || 'LOCAL_OPERATION_FAILED'}）。`
}

function readonlyLabel(key: string): string {
  return ({ agent_id: 'Agent ID', device_id: '设备 ID', user_binding: '用户绑定', authorized_store_ids: '授权店铺', active_store_id: '当前店铺', credential_reference: '凭证引用', certificate_fingerprint: '证书指纹', browser_profile_reference: '浏览器 Profile 引用' } as Record<string, string>)[key] ?? key
}
function display(value: unknown): string { return Array.isArray(value) ? value.join('、') || '未设置' : value == null || value === '' ? '未设置' : String(value) }
function friendlyName(value: string): string {
  return ({ '本地配置文件': '本地配置', 'ChannelAgent进程': '客服端程序', 'AI-CS身份服务': 'AI服务连接', '设备注册与身份绑定': '设备与客服身份', '当前店铺绑定': '当前工作店铺', 'Edge运行环境': 'Edge浏览器', 'PDD Session状态': 'PDD登录状态', '客服助手本地代理': '客服助手连接', '人工审批和发送安全': '发送安全保护' } as Record<string, string>)[value] ?? value
}
function friendlyStatus(status: 'PASS' | 'WARNING' | 'BLOCKED'): string { return status === 'PASS' ? '正常' : status === 'WARNING' ? '需提醒' : '已阻塞' }
function statusIcon(status: 'PASS' | 'WARNING' | 'BLOCKED'): string { return status === 'PASS' ? '✓' : status === 'WARNING' ? '!' : '×' }
function isDependent(item: ChannelAgentDoctor['components'][number]): boolean {
  return typeof item.technical?.dependsOn === 'string'
}
function resolutionSteps(item: ChannelAgentDoctor['components'][number]): string[] {
  if (item.error_code === 'CHANNEL_AGENT_LOCAL_API_UNAVAILABLE') {
    return [
      '关闭当前“AI 知识客服”窗口；不要退出 PDD，也不要清理浏览器 Profile。',
      '点击 Windows 右下角“显示隐藏的图标”（向上的小箭头）。',
      '找到 ChannelAgent 图标，双击“打开 AI 客服助手”。',
      '如果仍未恢复，右键该图标，选择“检查并恢复连接”，等待约 5 秒后再打开。'
    ]
  }
  if (item.error_code.includes('IDENTITY') || item.error_code.includes('DEVICE')) {
    return ['先在左侧登录客服账号。', '从账号有权限的店铺中选择服务店铺。', '确认“绑定这台电脑”。', '等待程序自动完成绑定、启用和身份同步。']
  }
  if (item.error_code.includes('STORE')) {
    return isDependent(item)
      ? ['先完成上方的设备与客服身份绑定。', '随后人工登录 PDD。', '选择与 PDD 当前页面识别结果一致的授权店铺。']
      : ['人工登录 PDD 并进入客服工作台。', '选择当前正在服务的授权店铺。', '核对 PDD 识别店铺与所选店铺一致后确认。']
  }
  return []
}

function openDiagnostics(message?: string) {
  forceExpanded.value = true
  if (message) notice.value = message
  void runDoctor(true)
}
defineExpose({ openDiagnostics })

onMounted(async () => { await Promise.all([runDoctor(false), loadConfig()]) })
</script>

<style scoped>
.recovery{width:min(390px,100%);padding:24px;border:1px solid #d7e2ef;border-radius:18px;background:#f8fbff;box-shadow:0 20px 55px rgb(4 25 55 / 16%);color:#18314f}.recovery.expanded{width:min(680px,48vw);max-height:88vh;overflow:auto}header{display:flex;gap:18px;align-items:flex-start;justify-content:space-between}h2,h3,h4,p{margin:0}header p{margin-top:8px;color:#5e7188;line-height:1.55}.eyebrow{display:block;margin-bottom:6px;color:#2b68aa;font-size:12px;font-weight:800;letter-spacing:.08em}.status{flex:none;padding:7px 10px;border-radius:999px;background:#dff4e9;color:#16704a;font-size:12px;font-weight:800}.status.warning,.status.blocked{background:#fee4e2;color:#b42318}.actions,.config-actions{display:flex;flex-wrap:wrap;gap:9px;margin-top:18px}button{border:0;border-radius:9px;padding:10px 14px;font-weight:700;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.primary{background:#2468b4;color:white}.secondary{border:1px solid #b9cbe0;background:white;color:#24486f}.link{background:transparent;color:#2468b4}.notice{margin-top:14px;padding:10px 12px;border-radius:9px;background:#edf4fc;color:#315d88}.diagnostics{display:grid;grid-template-columns:1fr;gap:8px;margin-top:16px}.diagnostic-summary{display:flex;justify-content:space-between;gap:12px;padding:0 2px 5px;color:#61758e;font-size:12px}.diagnostic-summary strong{color:#18314f;font-size:14px}.diagnostic-item{overflow:hidden;border:1px solid #bfe2ce;border-radius:10px;background:#f2fbf6}.diagnostic-item.warning,.diagnostic-item.blocked{border-color:#f2b8b5;background:#fff4f3}.diagnostic-item>summary{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:13px 15px;list-style:none;cursor:pointer}.diagnostic-item>summary::-webkit-details-marker{display:none}.component-name{display:flex;align-items:center;gap:10px;font-weight:800}.component-name i{width:9px;height:9px;border-radius:50%;background:#2fa66d;box-shadow:0 0 0 4px #dff4e9}.warning .component-name i,.blocked .component-name i{background:#d92d20;box-shadow:0 0 0 4px #fee4e2}.component-status{flex:none;color:#16704a;font-size:13px;font-weight:800}.warning .component-status,.blocked .component-status{color:#b42318}.diagnostic-detail{padding:0 15px 14px 34px;border-top:1px solid #dcebe3}.warning .diagnostic-detail,.blocked .diagnostic-detail{border-top-color:#f4d2cf}.diagnostic-detail p,.diagnostic-detail small{display:block;margin-top:9px;line-height:1.5}.diagnostic-detail code{display:inline-block;margin-top:9px;color:#8d3440}.technical-detail{margin-top:9px}.technical-detail summary{cursor:pointer;color:#45627f}.diagnostic-item pre{max-width:100%;overflow:auto;font-size:11px}.config-panel{margin-top:18px;padding-top:18px;border-top:1px solid #d7e2ef}.section-title{display:flex;align-items:center;justify-content:space-between}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.form-grid label{display:grid;gap:6px;font-size:13px;font-weight:700}.form-grid input,.form-grid select,.advanced>input,.host-list>input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #b9cbe0;border-radius:8px;background:white}.form-grid .check{display:flex;align-items:center}.form-grid .check input{width:auto}.advanced{margin-top:16px;padding:13px;border:1px solid #d7e2ef;border-radius:10px;background:white}.advanced summary{font-weight:800;cursor:pointer}.advanced p{margin:9px 0;color:#6b7787}.readonly,.safety-locks{margin-top:14px;padding:13px;border-radius:10px;background:#edf4fc}.readonly dl{display:grid;grid-template-columns:140px 1fr;gap:7px;margin-bottom:0}.readonly dt{color:#627389}.readonly dd{margin:0;overflow-wrap:anywhere}.safety-locks{display:flex;flex-wrap:wrap;gap:8px 16px;background:#e7f6ee;color:#176d48}.safety-locks h4{width:100%}.host-list{display:grid;gap:9px;margin-top:12px;padding:12px;border:1px solid #d7e2ef;border-radius:10px}.host-list>label:not(.confirmation){display:flex;gap:10px;padding:10px;border:1px solid #d7e2ef;border-radius:8px}.host-list>label.selected{border-color:#2468b4;background:#edf4fc}.host-list small{display:block;color:#63758c}.confirmation{display:flex;gap:8px;align-items:center}@media(max-width:900px){.recovery.expanded{width:100%;max-height:none}.form-grid{grid-template-columns:1fr}}
/* Productized status assistant overrides. Keep diagnostic data and actions unchanged. */
.recovery{
  box-sizing:border-box;width:min(430px,100%);min-height:520px;padding:30px;
  border:1px solid rgba(210,224,239,.9);border-radius:20px;background:#f8fbff;
  box-shadow:0 25px 65px rgb(4 20 45 / 20%);font-family:"Segoe UI","Microsoft YaHei",sans-serif
}
.recovery.expanded{width:min(690px,58vw);max-height:78vh;padding:28px 30px}
.recovery header{padding-bottom:18px;border-bottom:1px solid #e2ebf5}
.recovery header h2{font-size:25px;line-height:1.25;color:#153354}
.recovery header p{max-width:440px;font-size:14px}
.recovery .status{display:flex;align-items:center;gap:7px;padding:8px 12px}
.recovery .status i{width:8px;height:8px;border-radius:50%;background:#2fa66d;box-shadow:0 0 0 4px #dff4e9}
.recovery .status.warning{background:#fff7df;color:#8a5b00}
.recovery .status.warning i{background:#e7a11a;box-shadow:0 0 0 4px #ffebba}
.recovery .status.blocked{background:#fff0ef;color:#b42318}
.recovery .status.blocked i{background:#d92d20;box-shadow:0 0 0 4px #fee4e2}
.recovery .actions{align-items:center;margin-top:18px}
.recovery .actions .primary{order:0;min-width:112px;background:#2569b6;box-shadow:0 6px 14px #2569b62e}
.recovery .actions .secondary{order:1}
.recovery .actions .link{order:2;margin-left:auto;padding-inline:6px}
.recovery .notice{margin-top:14px;background:#edf4fc;font-size:13px}
.onboarding-guide{margin-top:16px;padding:16px;border:1px solid #d9e5f2;border-radius:13px;background:#fff}
.guide-title{display:flex;align-items:baseline;justify-content:space-between;gap:12px;color:#18314f}
.guide-title span{color:#6b7c91;font-size:12px}
.onboarding-guide ol{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin:15px 0 0;padding:0;list-style:none}
.onboarding-guide li{position:relative;display:grid;justify-items:center;gap:7px;color:#7a899b;font-size:12px;text-align:center}
.onboarding-guide li:not(:last-child)::after{content:"";position:absolute;top:13px;left:calc(50% + 16px);width:calc(100% - 32px);height:2px;background:#dce6f1}
.onboarding-guide li i{z-index:1;display:grid;width:26px;height:26px;place-items:center;border-radius:50%;background:#edf2f7;color:#708197;font-style:normal;font-weight:800}
.onboarding-guide li.active{color:#2165ad;font-weight:800}
.onboarding-guide li.active i{background:#286bb8;color:#fff;box-shadow:0 0 0 4px #e1edfa}
.onboarding-guide li.done{color:#19825a}.onboarding-guide li.done i{background:#dff4e9;color:#16704a}
.diagnostics{gap:10px}.diagnostic-summary{align-items:center;padding:2px 1px 5px}.diagnostic-summary span{color:#78889a}
.diagnostic-group{overflow:hidden;border:1px solid #d8e4f0;border-radius:13px;background:#fff}
.diagnostic-group>summary{display:flex;align-items:center;gap:12px;padding:14px 15px;list-style:none;cursor:pointer;transition:background .15s}
.diagnostic-group>summary:hover{background:#f4f8fc}.diagnostic-group>summary::-webkit-details-marker{display:none}
.group-icon{display:grid;width:34px;height:34px;flex:none;place-items:center;border-radius:10px;background:#e9f2fc;color:#2869b5;font-size:16px;font-weight:900}
.group-title{display:grid;gap:2px}.group-title strong{font-size:15px;color:#18314f}.group-title small{color:#77879a;font-size:12px}
.group-result{margin-left:auto;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:800}
.group-result.all-pass{background:#e7f6ee;color:#16704a}.group-result.has-issue{background:#fff0ef;color:#b42318}
.group-result.has-pending{background:#eef2f6;color:#61758a}
.group-items{display:grid;gap:8px;padding:0 12px 12px;border-top:1px solid #edf2f7}
.diagnostic-item{margin-top:10px;border-radius:10px}.diagnostic-item>summary{padding:11px 13px}
.diagnostic-item .component-name i{display:grid;width:20px;height:20px;place-items:center;border-radius:50%;font-size:11px;font-style:normal;box-shadow:none}
.diagnostic-item.pass{border-color:#bfe2ce;background:#f2fbf6}
.diagnostic-item.pass .component-name i{background:#daf3e5;color:#16704a}
.diagnostic-item.pass .component-status{color:#16704a}
.diagnostic-item.warning{border-color:#f0d48a;background:#fffaf0}
.diagnostic-item.warning .component-name i{background:#fff0c2;color:#8a5b00;box-shadow:none}
.diagnostic-item.warning .component-status{color:#8a5b00}
.diagnostic-item.blocked{border-color:#efb4b0;background:#fff5f4}
.diagnostic-item.blocked .component-name i{background:#fee4e2;color:#b42318;box-shadow:none}
.diagnostic-item.blocked .component-status{color:#b42318}
.diagnostic-item.dependent{border-color:#d7e0ea;background:#f6f8fa}
.diagnostic-item.dependent .component-name i{background:#e8edf3;color:#697b90}
.diagnostic-item.dependent .component-status{color:#697b90}
.diagnostic-detail{background:#fff;color:#4f6176;font-size:13px}.diagnostic-detail p{display:grid;grid-template-columns:74px 1fr;gap:8px}.diagnostic-detail p strong{color:#263f5e}
.resolution-steps{display:grid;gap:7px;margin:12px 0;padding:12px 12px 12px 32px;border-radius:9px;background:#f3f7fb;color:#354e69;line-height:1.5}
.issue-action{margin:0 0 10px 82px;background:#286bb8;color:#fff}
.technical-detail{padding-top:5px;border-top:1px dashed #d9e3ed}.technical-detail summary{font-size:12px}.technical-detail code{padding:4px 7px;border-radius:5px;background:#f3f5f8;font-size:11px}
@media(max-width:900px){
  .recovery,.recovery.expanded{width:100%;min-height:auto;max-height:none;padding:22px}
  .recovery .actions .link{margin-left:0}.onboarding-guide ol{grid-template-columns:repeat(2,1fr);gap:16px}
  .onboarding-guide li::after{display:none}.guide-title{align-items:flex-start;flex-direction:column}
}
</style>
