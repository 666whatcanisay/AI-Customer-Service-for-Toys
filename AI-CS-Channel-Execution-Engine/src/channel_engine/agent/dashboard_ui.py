CHANNEL_AGENT_DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>AI-CS Channel Agent 控制台</title>
  <style>
    :root {
      --ink:#17221d; --muted:#6a746e; --line:#dbe2dc; --paper:#f4f6f2;
      --card:#fff; --forest:#163d2a; --mint:#d9f3e4; --green:#18794e;
      --amber:#9a6700; --amber-bg:#fff3c4; --red:#b42318; --red-bg:#fee4e2;
      --slate:#475467; --shadow:0 16px 45px rgba(28,55,42,.08);
      font-family:Inter,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
    }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:var(--paper); }
    button { font:inherit; }
    .shell { min-height:100vh; display:grid; grid-template-columns:248px 1fr; }
    aside { background:var(--forest); color:#fff; padding:30px 24px; display:flex; flex-direction:column; }
    .brand { display:flex; gap:12px; align-items:center; }
    .mark { width:42px; height:42px; border-radius:13px; display:grid; place-items:center; background:#e8ffef; color:var(--forest); font-weight:800; }
    .brand strong { display:block; font-size:15px; letter-spacing:.02em; }
    .brand span { color:#b8ccbf; font-size:12px; }
    nav { margin-top:48px; display:grid; gap:8px; }
    nav a { color:#b8ccbf; text-decoration:none; border-radius:10px; padding:11px 13px; font-size:14px; }
    nav a.active { background:rgba(255,255,255,.11); color:#fff; }
    .aside-foot { margin-top:auto; padding-top:24px; color:#9eb5a6; font-size:12px; line-height:1.7; }
    main { min-width:0; padding:34px clamp(22px,4vw,56px) 54px; }
    header { display:flex; align-items:flex-start; justify-content:space-between; gap:24px; }
    .eyebrow { color:var(--green); font-size:12px; font-weight:750; letter-spacing:.12em; text-transform:uppercase; }
    h1 { font-family:Georgia,"Noto Serif SC",serif; font-size:clamp(30px,4vw,46px); line-height:1.05; margin:8px 0 9px; font-weight:600; }
    .subtitle { margin:0; color:var(--muted); }
    .actions { display:flex; flex-wrap:wrap; gap:9px; justify-content:flex-end; }
    .btn { display:inline-flex; align-items:center; border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:10px; padding:10px 15px; cursor:pointer; box-shadow:0 2px 6px rgba(20,40,30,.04); text-decoration:none; }
    .btn.primary { color:#fff; border-color:var(--forest); background:var(--forest); }
    .btn.danger { color:var(--red); border-color:#f5b7b1; }
    .btn:disabled { cursor:wait; opacity:.55; }
    .summary { margin:28px 0 20px; border-radius:18px; padding:22px 24px; color:#fff; background:linear-gradient(115deg,#163d2a,#275c40); box-shadow:var(--shadow); display:flex; justify-content:space-between; align-items:center; gap:18px; }
    .summary-title { font-size:13px; color:#bcd3c3; }
    .summary-value { font-size:28px; font-weight:720; margin-top:5px; }
    .summary-meta { text-align:right; color:#d6e6da; font-size:13px; line-height:1.65; }
    .grid { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:13px; }
    .status-card { grid-column:span 2; min-height:138px; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 26px rgba(34,55,44,.045); padding:19px; }
    .card-head { display:flex; justify-content:space-between; align-items:center; gap:10px; }
    .label { color:var(--muted); font-size:12px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
    .dot { width:9px; height:9px; border-radius:99px; background:#98a29c; box-shadow:0 0 0 4px #eef1ef; }
    .dot.good { background:var(--green); box-shadow:0 0 0 4px var(--mint); }
    .dot.warn { background:#d89c00; box-shadow:0 0 0 4px var(--amber-bg); }
    .dot.bad { background:var(--red); box-shadow:0 0 0 4px var(--red-bg); }
    .value { font-size:22px; font-weight:720; margin:17px 0 6px; overflow-wrap:anywhere; }
    .detail { color:var(--muted); font-size:12px; line-height:1.55; overflow-wrap:anywhere; }
    .lower { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr); gap:16px; margin-top:16px; }
    .stack { display:grid; gap:16px; }
    h2 { font-size:17px; margin:0 0 16px; }
    .store-line { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:13px 0; border-top:1px solid #edf0ed; }
    .store-line:first-of-type { border-top:0; padding-top:0; }
    .store-key { color:var(--muted); font-size:13px; }
    .store-data { font-size:14px; font-weight:650; text-align:right; overflow-wrap:anywhere; }
    .badge { display:inline-flex; align-items:center; border-radius:99px; padding:5px 9px; font-size:11px; font-weight:750; letter-spacing:.03em; background:#eef1ef; color:var(--slate); }
    .badge.good { color:var(--green); background:var(--mint); }
    .badge.warn { color:var(--amber); background:var(--amber-bg); }
    .badge.bad { color:var(--red); background:var(--red-bg); }
    .safety-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .safety-item { border:1px solid #e6ebe7; border-radius:12px; padding:13px; }
    .safety-item strong { display:block; margin-top:6px; font-size:14px; }
    .timeline { list-style:none; margin:0; padding:0; }
    .event { position:relative; padding:0 0 18px 25px; }
    .event:last-child { padding-bottom:0; }
    .event:before { content:""; position:absolute; left:4px; top:6px; bottom:-4px; width:1px; background:#dde4df; }
    .event:last-child:before { display:none; }
    .event:after { content:""; position:absolute; left:0; top:5px; width:9px; height:9px; border-radius:50%; background:var(--green); box-shadow:0 0 0 4px var(--mint); }
    .event.error:after { background:var(--red); box-shadow:0 0 0 4px var(--red-bg); }
    .event-title { font-size:13px; font-weight:700; }
    .event-meta { color:var(--muted); margin-top:4px; font-size:11px; }
    .empty { color:var(--muted); font-size:13px; padding:12px 0; }
    #notice { min-height:22px; margin:13px 0 0; color:var(--muted); font-size:13px; }
    #notice.error { color:var(--red); }
    @media (max-width:1050px) { .status-card { grid-column:span 3; } .lower { grid-template-columns:1fr; } }
    @media (max-width:760px) { .shell { grid-template-columns:1fr; } aside { display:none; } main { padding:24px 17px 38px; } header { display:block; } .actions { justify-content:flex-start; margin-top:20px; } .status-card { grid-column:span 6; } .summary { align-items:flex-start; flex-direction:column; } .summary-meta { text-align:left; } }
  </style>
</head>
<body>
<div class="shell">
  <aside>
    <div class="brand"><div class="mark">CS</div><div><strong>Channel Agent</strong><span>Local Control Node</span></div></div>
    <nav aria-label="控制台导航"><a class="active" href="#overview">运行概览</a><a href="#store-panel">店铺绑定</a><a href="#browser-panel">浏览器状态</a><a href="#safety-panel">安全策略</a><a href="#timeline-panel">运行时间线</a></nav>
    <div class="aside-foot">本地控制台 V1<br>不提供消息发送入口</div>
  </aside>
  <main id="overview">
    <header><div><div class="eyebrow">AI-CS Operations</div><h1>渠道节点控制台</h1><p class="subtitle">单节点运行状态、店铺绑定与安全边界</p></div><div class="actions" aria-label="运行控制"><a class="btn" href="/agent/first-launch/ui">首次设置</a><button class="btn primary" data-command="start">启动节点</button><button class="btn" data-command="check">立即检查</button><button class="btn danger" data-command="stop">停止节点</button></div></header>
    <div id="notice" role="status" aria-live="polite"></div>
    <section class="summary" aria-label="Agent 总览"><div><div class="summary-title">AGENT STATUS</div><div class="summary-value" id="agent-status" data-testid="agent-status">—</div></div><div class="summary-meta"><div id="node-name">—</div><div id="last-refresh">尚未刷新</div></div></section>
    <section class="grid" aria-label="核心状态">
      <article class="card status-card"><div class="card-head"><div class="label">Node 状态</div><i class="dot" id="node-dot"></i></div><div class="value" id="node-status" data-testid="node-status">—</div><div class="detail" id="node-detail">—</div></article>
      <article class="card status-card"><div class="card-head"><div class="label">AI-CS 连接</div><i class="dot" id="ai-dot"></i></div><div class="value" id="ai-status" data-testid="ai-status">—</div><div class="detail" id="ai-detail">—</div></article>
      <article class="card status-card"><div class="card-head"><div class="label">Channel 状态</div><i class="dot" id="channel-dot"></i></div><div class="value" id="channel-status" data-testid="channel-status">—</div><div class="detail" id="channel-detail">—</div></article>
    </section>
    <section class="lower">
      <div class="stack">
        <article class="card" id="store-panel"><h2>店铺绑定</h2><div class="store-line"><span class="store-key">连接状态</span><span class="badge" id="store-state" data-testid="store-state">—</span></div><div class="store-line"><span class="store-key">当前店铺</span><span class="store-data" id="store-name">未绑定</span></div><div class="store-line"><span class="store-key">店铺标识</span><span class="store-data" id="store-id">—</span></div></article>
        <article class="card" id="browser-panel"><h2>Browser Runtime</h2><div class="store-line"><span class="store-key">Chrome</span><span class="store-data" id="chrome-status">—</span></div><div class="store-line"><span class="store-key">Profile</span><span class="store-data" id="profile">—</span></div><div class="store-line"><span class="store-key">Session</span><span class="store-data" id="browser-session">—</span></div><div class="store-line"><span class="store-key">Login</span><span class="badge" id="login-status" data-testid="login-status">—</span></div></article>
        <article class="card" id="safety-panel"><h2>安全策略</h2><div class="safety-grid"><div class="safety-item"><span class="store-key">Runtime Mode</span><strong id="runtime-mode">—</strong></div><div class="safety-item"><span class="store-key">Pilot Mode</span><strong id="pilot-mode">—</strong></div><div class="safety-item"><span class="store-key">Manual Approval</span><strong id="manual-approval">—</strong></div><div class="safety-item"><span class="store-key">Kill Switch</span><strong id="kill-switch">—</strong></div></div></article>
      </div>
      <article class="card" id="timeline-panel"><h2>Runtime Timeline</h2><ol class="timeline" id="timeline" data-testid="runtime-timeline"><li class="empty">暂无运行事件</li></ol></article>
    </section>
  </main>
</div>
<script>
  const $ = id => document.getElementById(id);
  const badgeClass = value => ['CONNECTED','ONLINE','HEALTHY','ACTIVE','AUTHENTICATED','DISABLED'].includes(value) ? 'good' : ['WAITING_LOGIN','DEGRADED','CONNECTING','UNKNOWN'].includes(value) ? 'warn' : ['FAILED','BLOCKED','UNAVAILABLE','OFFLINE','ENABLED'].includes(value) ? 'bad' : '';
  const setDot = (id,value) => { $(id).className='dot '+badgeClass(value); };
  const setBadge = (id,value) => { $(id).textContent=value; $(id).className='badge '+badgeClass(value); };
  const formatTime = value => value ? new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(value)) : '—';
  function renderTimeline(items) { const root=$('timeline'); root.replaceChildren(); if(!items.length){const empty=document.createElement('li'); empty.className='empty'; empty.textContent='暂无运行事件'; root.append(empty); return;} items.forEach(item=>{const row=document.createElement('li'); row.className='event'+(item.successful?'':' error'); const title=document.createElement('div'); title.className='event-title'; title.textContent=item.title; const meta=document.createElement('div'); meta.className='event-meta'; meta.textContent=formatTime(item.occurred_at)+' · '+item.reason_code; row.append(title,meta); root.append(row);}); }
  function render(data) {
    $('agent-status').textContent=data.agent.status; $('node-name').textContent=data.node.node_name; $('last-refresh').textContent='刷新于 '+formatTime(data.generated_at);
    $('node-status').textContent=data.node.status; $('node-detail').textContent=data.node.node_id+' · '+data.agent.environment; setDot('node-dot',data.node.status);
    $('ai-status').textContent=data.ai_cs.connection; $('ai-detail').textContent=data.ai_cs.endpoint+' · '+data.ai_cs.reason_code; setDot('ai-dot',data.ai_cs.status);
    $('channel-status').textContent=data.channel.status; $('channel-detail').textContent=data.channel.platform.toUpperCase()+' · '+data.channel.reason_code; setDot('channel-dot',data.channel.status);
    setBadge('store-state',data.store.state); $('store-name').textContent=data.store.store_name||'未绑定'; $('store-id').textContent=data.store.store_id||'—';
    $('chrome-status').textContent=data.browser.chrome_status; $('profile').textContent=data.browser.profile; $('browser-session').textContent=data.browser.session; setBadge('login-status',data.browser.login);
    $('runtime-mode').textContent=data.safety.runtime_mode; $('pilot-mode').textContent=data.safety.pilot_mode?'ACTIVE':'INACTIVE'; $('manual-approval').textContent=data.safety.manual_approval?'REQUIRED':'DISABLED'; $('kill-switch').textContent=data.safety.kill_switch?'ENABLED':'DISABLED'; renderTimeline(data.timeline);
  }
  async function refresh(){const response=await fetch('/agent/dashboard',{headers:{Accept:'application/json'}}); if(!response.ok) throw new Error('状态接口不可用'); render(await response.json());}
  async function command(name){const buttons=[...document.querySelectorAll('[data-command]')]; buttons.forEach(button=>button.disabled=true); $('notice').className=''; $('notice').textContent='正在处理…'; try{const response=await fetch('/agent/'+name,{method:'POST',headers:{Accept:'application/json'}}); if(!response.ok) throw new Error('操作失败（'+response.status+'）'); await refresh(); $('notice').textContent=name==='start'?'节点已启动':name==='stop'?'节点已停止':'状态检查完成';}catch(error){$('notice').className='error'; $('notice').textContent=error.message;}finally{buttons.forEach(button=>button.disabled=false);}}
  document.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>command(button.dataset.command))); refresh().catch(error=>{$('notice').className='error'; $('notice').textContent=error.message;}); window.setInterval(()=>refresh().catch(()=>{}),5000);
</script>
</body>
</html>
"""


__all__ = ["CHANNEL_AGENT_DASHBOARD_HTML"]
