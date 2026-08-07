<template>
  <fieldset class="store-fieldset">
    <legend>负责的客服店铺</legend>
    <p class="field-help">可多选。勾选第一家店铺时会自动设为默认店铺。</p>
    <div class="store-options">
      <div v-for="store in stores" :key="store.store_ref" class="store-option" :class="{ selected: selectedStoreIds.includes(store.store_ref) }">
        <label class="store-check">
          <input
            type="checkbox"
            :checked="selectedStoreIds.includes(store.store_ref)"
            :data-testid="`${mode}-store-${store.store_ref}`"
            @change="$emit('toggle', store.store_ref)"
          />
          <span><strong>{{ store.store_name }}</strong><small>{{ store.platform_name }}</small></span>
        </label>
        <label v-if="selectedStoreIds.includes(store.store_ref)" class="default-choice">
          <input
            type="radio"
            :name="`${mode}-default-store`"
            :value="store.store_ref"
            :checked="defaultStoreId === store.store_ref"
            @change="$emit('default', store.store_ref)"
          />
          默认店铺
        </label>
      </div>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import type { StoreOperationItem } from '../api/client'

defineProps<{
  mode: 'create' | 'edit'
  stores: StoreOperationItem[]
  selectedStoreIds: number[]
  defaultStoreId: number | null
}>()

defineEmits<{
  toggle: [storeId: number]
  default: [storeId: number]
}>()
</script>

<style scoped>
fieldset{margin:0;padding:0;border:0}legend{margin-bottom:9px;font-weight:700}.field-help{margin:0 0 9px;color:#718096;font-size:13px}.store-options{display:grid;gap:8px}.store-option{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:10px 12px;border:1px solid #dde5f0;border-radius:10px}.store-option.selected{border-color:#8eb2df;background:#f5f9ff}.store-check,.default-choice{display:flex;flex-direction:row;align-items:center}.store-check{gap:10px}.store-check input,.default-choice input{margin:0;padding:0}.store-check span{display:grid;gap:1px}.store-check small{color:#718096}.default-choice{gap:6px;white-space:nowrap;color:#285b9e}@media(max-width:560px){.store-option{align-items:flex-start;flex-direction:column}}
</style>
