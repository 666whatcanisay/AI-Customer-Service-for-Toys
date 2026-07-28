<template>
  <main class="page not-found-page">
    <section class="card not-found-card" role="alert">
      <p class="eyebrow">页面不存在</p>
      <h1>没有找到这个页面</h1>
      <p>链接可能已过期，或地址输入有误。请从左侧导航进入已提供的运营功能；系统不会将未知地址显示成空白页面。</p>
      <RouterLink class="button" to="/overview">返回运营概览</RouterLink>
    </section>
  </main>
</template>

<style scoped>
.not-found-page { display: grid; min-height: 62vh; place-items: center; }.not-found-card { width: min(100%, 560px); }.eyebrow { margin: 0 0 8px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.not-found-card h1 { margin: 0 0 10px; color: #172554; }.not-found-card p { max-width: 46ch; margin: 0 0 22px; color: #526279; line-height: 1.65; }
</style>
