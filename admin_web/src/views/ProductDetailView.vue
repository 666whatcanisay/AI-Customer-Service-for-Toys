<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { apiErrorMessage, getAdminProduct, listAdminProductSkus, type AdminProductDetail, type AdminSku } from '../api/client'
import { displayStatus } from '../presentation'

const props = defineProps<{ productId: string }>()
const product = ref<AdminProductDetail | null>(null)
const skus = ref<AdminSku[]>([])
const error = ref('')
const loading = ref(true)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [detail, skuPage] = await Promise.all([getAdminProduct(props.productId), listAdminProductSkus(props.productId)])
    product.value = detail
    skus.value = skuPage.items
  } catch (reason: unknown) {
    product.value = null
    skus.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

watch(() => props.productId, load)
onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>商品详情</h1><p>测试 / 试运行数据只读详情。</p></div><RouterLink class="button secondary" to="/products">返回商品列表</RouterLink></div>
    <p v-if="loading" class="notice">正在加载…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取商品详情。{{ error }}</p>
    <template v-else-if="product">
      <section class="card"><h2>{{ product.product_name_display }}</h2><p>{{ product.product_id }} · {{ product.store_code }} · {{ displayStatus(product.sales_status) }}</p><p>{{ product.safety_summary || '无额外安全摘要。' }}</p><p class="notice">测试数据：{{ product.test_data_mode ? '是' : '否' }}；正式发布：否。</p></section>
      <section class="card sku-card"><h2>SKU（{{ product.sku_count }}）</h2><p v-if="skus.length === 0" class="notice">样本不足：该商品暂无 SKU。请先完成商品数据同步。</p><div v-else class="table-wrap"><table class="data-table"><thead><tr><th>SKU</th><th>关系</th><th>关联</th><th>来源</th></tr></thead><tbody><tr v-for="sku in skus" :key="sku.sku_id"><td>{{ sku.sku_name_display }}<small>{{ sku.sku_code }}</small></td><td><span class="badge">{{ displayStatus(sku.relation_type) }}</span></td><td>{{ sku.reference_sku_id || sku.component_sku_refs.join(', ') || '—' }}</td><td>{{ sku.source_ids.join(', ') }}</td></tr></tbody></table></div></section>
    </template>
  </main>
</template>

<style scoped>
.sku-card { margin-top: 20px; }
small { display: block; color: #617087; }
</style>
