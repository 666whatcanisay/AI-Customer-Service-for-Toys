<template>
  <header class="app-header">
    <RouterLink class="brand" to="/overview">Mumu Operations Portal</RouterLink>
    <nav aria-label="Main navigation">
      <RouterLink to="/overview">Overview</RouterLink>
      <RouterLink to="/ai-capabilities">AI capability center</RouterLink>
      <RouterLink to="/stores">Stores</RouterLink>
      <RouterLink to="/products">Products and SKUs</RouterLink>
      <RouterLink to="/faqs">FAQs</RouterLink>
      <RouterLink to="/safety-rules">Safety rules</RouterLink>
      <RouterLink to="/sources">Source evidence</RouterLink>
      <RouterLink to="/conflicts">Conflicts</RouterLink>
      <RouterLink to="/imports">Data imports</RouterLink>
      <RouterLink to="/suggestions">Customer suggestions</RouterLink>
      <RouterLink to="/experience-cases">Experience cases</RouterLink>
      <RouterLink to="/ai-optimization-pool">AI optimization pool</RouterLink>
    </nav>
  </header>
  <p class="test-banner">Internal test administration portal. Formal permissions are not enabled.</p>
  <RouterView />
</template>

<style>
* { box-sizing: border-box; }

body {
  margin: 0;
  color: #172033;
  background: #f3f6fb;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

a { color: #285493; }

.app-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 16px clamp(20px, 5vw, 64px);
  border-bottom: 1px solid #dce4ef;
  background: #fff;
}

.app-header nav {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px 18px;
}

.app-header a { text-decoration: none; }
.app-header .router-link-active { color: #163c77; font-weight: 700; }
.brand { color: #172033; font-weight: 800; white-space: nowrap; }

.test-banner {
  margin: 0;
  padding: 9px clamp(20px, 5vw, 64px);
  color: #6c5410;
  background: #fff7df;
  border-bottom: 1px solid #ecdca9;
  font-size: 14px;
}

.page { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 40px 0 64px; }
.page-header { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { margin: 0; color: #617087; }

.card { padding: 24px; border: 1px solid #dbe3ef; border-radius: 14px; background: #fff; box-shadow: 0 12px 30px rgb(30 52 86 / 7%); }
.button { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 9px 16px; border: 0; border-radius: 8px; color: #fff; background: #284f8f; font: inherit; text-decoration: none; cursor: pointer; }
.button.secondary { border: 1px solid #9fb2cc; color: #25466f; background: #fff; }
.button:disabled { cursor: not-allowed; opacity: .55; }
.notice { padding: 16px; border-radius: 9px; background: #edf3fb; }
.notice.error { color: #8c2929; background: #fff0f0; }
.notice.success { color: #176744; background: #edf9f3; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 12px 10px; border-bottom: 1px solid #e4e9f1; text-align: left; vertical-align: top; }
.data-table th { color: #526279; font-size: 13px; }
.badge { display: inline-block; padding: 4px 8px; border-radius: 999px; color: #33445c; background: #edf1f6; font-size: 12px; font-weight: 700; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin: 20px 0; }
.metric { padding: 14px; border-radius: 10px; background: #f5f7fb; }
.metric strong { display: block; margin-top: 5px; font-size: 22px; }

@media (max-width: 720px) {
  .app-header, .page-header { align-items: flex-start; flex-direction: column; }
  .app-header nav { justify-content: flex-start; }
  .table-wrap { overflow-x: auto; }
}
</style>
