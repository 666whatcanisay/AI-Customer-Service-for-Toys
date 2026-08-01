<script setup lang="ts">
import { computed } from 'vue'

type OperationalState = 'loading' | 'empty' | 'error' | 'success'

const props = withDefaults(defineProps<{
  state: OperationalState
  title: string
  reason: string
  nextStep: string
  actionLabel?: string
  actionTo?: string
  retryLabel?: string
  compact?: boolean
}>(), {
  actionLabel: '',
  actionTo: '',
  retryLabel: '',
  compact: false,
})

defineEmits<{ retry: [] }>()

const stateLabel = computed(() => ({
  loading: '正在处理',
  empty: '暂无数据',
  error: '读取失败',
  success: '操作完成',
})[props.state])

const stateMark = computed(() => ({
  loading: '…',
  empty: '○',
  error: '!',
  success: '✓',
})[props.state])
</script>

<template>
  <section
    :class="['operational-state', `state-${state}`, { compact }]"
    :role="state === 'error' ? 'alert' : 'status'"
    :aria-live="state === 'error' ? 'assertive' : 'polite'"
    :data-state="state"
  >
    <span class="state-mark" aria-hidden="true">{{ stateMark }}</span>
    <div class="state-content">
      <p class="state-label">{{ stateLabel }}</p>
      <h2>{{ title }}</h2>
      <p class="state-reason"><strong>原因：</strong>{{ reason }}</p>
      <p class="state-next"><strong>下一步：</strong>{{ nextStep }}</p>
      <div v-if="actionTo || retryLabel || $slots.actions" class="state-actions">
        <RouterLink v-if="actionTo" class="button secondary" :to="actionTo">{{ actionLabel }}</RouterLink>
        <button v-if="retryLabel" class="button secondary" type="button" @click="$emit('retry')">{{ retryLabel }}</button>
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.operational-state { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 14px; align-items: start; padding: 20px; border: 1px solid #cbd9e9; border-radius: 14px; color: #40546f; background: #f7faff; }
.operational-state.compact { padding: 15px; border-radius: 10px; }
.state-mark { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 11px; color: #2e63a9; background: #e5eef9; font-size: 18px; font-weight: 800; }
.state-label { margin: 0 0 4px; color: #58708e; font-size: 11px; font-weight: 800; letter-spacing: .08em; }
h2 { margin: 0; color: #223957; font-size: 17px; }
.state-reason, .state-next { margin: 7px 0 0; line-height: 1.55; }
.state-reason strong, .state-next strong { color: #334965; }
.state-actions { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 13px; }
.state-error { border-color: #efc5c5; color: #7c3535; background: #fff5f5; }
.state-error .state-mark { color: #9c3030; background: #ffe3e3; }
.state-error h2, .state-error strong { color: #762d2d; }
.state-empty { border-style: dashed; }
.state-success { border-color: #b9dfca; color: #276348; background: #f0faf4; }
.state-success .state-mark { color: #217447; background: #dbf2e4; }
.state-success h2, .state-success strong { color: #1f6542; }
@media (max-width: 560px) { .operational-state { grid-template-columns: 1fr; }.state-actions .button { width: 100%; } }
</style>
