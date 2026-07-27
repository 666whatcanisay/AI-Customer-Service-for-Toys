<template>
  <section class="product-empty-state" role="status" data-testid="admin-product-empty-state">
    <span class="empty-mark" aria-hidden="true">○</span>
    <div>
      <h2>{{ title }}</h2>
      <p>{{ description }}</p>
      <RouterLink v-if="to" :to="to" class="empty-action">{{ actionLabel }}</RouterLink>
    </div>
  </section>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'

withDefaults(defineProps<{
  title: string
  description: string
  actionLabel?: string
  to?: string
}>(), {
  actionLabel: '返回运营首页',
  to: '/overview'
})
</script>

<style scoped>
.product-empty-state { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 14px; align-items: start; padding: 22px; border: 1px dashed #b9c9de; border-radius: 16px; background: #f8fbff; color: #40546f; }
.empty-mark { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 12px; background: #e8f0fb; color: #2e63d5; font-size: 24px; }
h2 { margin: 0 0 6px; color: #223957; font-size: 17px; }
p { margin: 0; line-height: 1.6; }
.empty-action { display: inline-flex; margin-top: 12px; color: #2458c7; font-size: 13px; font-weight: 800; text-decoration: none; }
.empty-action:hover { text-decoration: underline; }
</style>
