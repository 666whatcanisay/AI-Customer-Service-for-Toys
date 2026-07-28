<script setup lang="ts">
import { computed, onMounted, provide } from 'vue'

import CustomerIdentitySelection from '@/views/CustomerIdentitySelection.vue'
import { CustomerIdentityKey, createCustomerIdentityStore } from '@/workspace/customerIdentity'

const identityStore = createCustomerIdentityStore()
const canEnterWorkbench = computed(() => identityStore.identity.value !== null)

provide(CustomerIdentityKey, identityStore)

onMounted(() => { void identityStore.restore() })
</script>

<template>
  <CustomerIdentitySelection v-if="!canEnterWorkbench" />
  <router-view v-else />
</template>

<style>
* {
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  height: 100%;
  min-width: 320px;
  min-height: 100%;
  margin: 0;
  overflow: hidden;
}

body {
  font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
  background: #edf2f8;
}

button,
input,
textarea,
select {
  font: inherit;
}
</style>
