CHANNEL_AGENT_FIRST_LAUNCH_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>AI-CS Channel Agent · 首次启动</title>
  <style>
    :root {
      --ink:#17231d; --muted:#69766f; --paper:#f4f6f2; --card:#fff;
      --forest:#143d29; --green:#18794e; --mint:#dff5e8; --line:#dce4de;
      --amber:#8d6200; --amber-bg:#fff3c4; --red:#b42318; --red-bg:#fee4e2;
      font-family:Inter,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
    }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:radial-gradient(circle at 18% 0,#e9f6ec 0,transparent 34%),var(--paper); }
    button,a { font:inherit; }
    .layout { min-height:100vh; display:grid; grid-template-columns:minmax(270px,32vw) 1fr; }
    .intro { background:var(--forest); color:#fff; padding:clamp(30px,5vw,72px); display:flex; flex-direction:column; }
    .brand { display:flex; align-items:center; gap:12px; font-weight:750; }
    .brand-mark { width:40px; height:40px; display:grid; place-items:center; border-radius:12px; color:var(--forest); background:#ecfff1; }
    .intro h1 { font-family:Georgia,"Noto Serif SC",serif; font-size:clamp(35px,5vw,60px); line-height:1.05; font-weight:500; margin:14vh 0 18px; }
    .intro p { color:#c4d5ca; line-height:1.8; max-width:430px; }
    .boundary { margin-top:auto; padding-top:28px; border-top:1px solid rgba(255,255,255,.14); color:#a9c0b1; font-size:12px; line-height:1.8; }
    main { min-width:0; padding:clamp(26px,4.5vw,64px); }
    .top { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }
    .eyebrow { color:var(--green); font-size:12px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }
    h2 { font-size:clamp(25px,3vw,38px); margin:7px 0 7px; }
    .sub { color:var(--muted); margin:0; }
    .state { border-radius:999px; background:#edf1ee; padding:8px 12px; font-size:12px; font-weight:800; }
    .progress { height:6px; background:#e2e8e3; border-radius:99px; overflow:hidden; margin:28px 0 24px; }
    .progress i { display:block; height:100%; width:0; background:linear-gradient(90deg,#48a777,#18794e); transition:width .3s ease; }
    .steps { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; margin-bottom:24px; }
    .step { color:#8a958f; font-size:11px; border-top:2px solid #dfe5e1; padding-top:8px; }
    .step.active { color:var(--green); border-color:var(--green); font-weight:750; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:22px; box-shadow:0 12px 34px rgba(28,57,42,.055); }
    .hero-card { min-height:245px; }
    .hero-card h3 { margin:0 0 9px; font-size:21px; }
    .hero-card p { color:var(--muted); line-height:1.7; }
    .platform { display:flex; align-items:center; gap:13px; margin:22px 0; padding:14px; border:1px solid #cde5d5; background:#f3fbf5; border-radius:13px; }
    .platform-icon { width:42px; height:42px; display:grid; place-items:center; border-radius:12px; background:#e02b20; color:#fff; font-weight:900; }
    .platform strong,.platform span { display:block; }
    .platform span { color:var(--muted); font-size:12px; margin-top:3px; }
    .actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:20px; }
    .btn { border:1px solid var(--line); border-radius:10px; padding:10px 16px; background:#fff; color:var(--ink); cursor:pointer; text-decoration:none; }
    .btn.primary { background:var(--forest); color:#fff; border-color:var(--forest); }
    .btn.danger { color:var(--red); border-color:#f0b8b3; }
    .btn:disabled { opacity:.45; cursor:not-allowed; }
    .login-grid,.ready-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:11px; margin:20px 0; }
    .metric { border:1px solid #e3e9e5; border-radius:12px; padding:14px; min-width:0; }
    .metric span { display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }
    .metric strong { display:block; margin-top:8px; overflow-wrap:anywhere; }
    .doctor { margin-top:16px; }
    .section-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:13px; }
    .section-head h3 { margin:0; font-size:16px; }
    .check-list { display:grid; grid-template-columns:1fr 1fr; gap:9px; }
    .check { display:flex; gap:10px; align-items:flex-start; border:1px solid #e6ebe7; border-radius:11px; padding:12px; }
    .check-dot { flex:0 0 auto; width:9px; height:9px; border-radius:50%; margin-top:5px; background:#98a29c; }
    .check.pass .check-dot { background:var(--green); box-shadow:0 0 0 4px var(--mint); }
    .check.warning .check-dot { background:#d39a00; box-shadow:0 0 0 4px var(--amber-bg); }
    .check.blocked .check-dot { background:var(--red); box-shadow:0 0 0 4px var(--red-bg); }
    .check strong { display:block; font-size:13px; }
    .check small { display:block; color:var(--muted); margin-top:4px; line-height:1.45; }
    .failure { border-left:4px solid var(--red); background:#fff7f6; border-radius:10px; padding:15px; margin:18px 0; }
    .failure strong { color:var(--red); }
    .failure p { margin:7px 0 0; }
    .timeline { margin-top:16px; }
    .events { list-style:none; padding:0; margin:0; max-height:330px; overflow:auto; }
    .event { display:grid; grid-template-columns:56px 1fr; gap:12px; padding:11px 0; border-top:1px solid #edf1ee; }
    .event:first-child { border-top:0; }
    .event time { color:var(--muted); font-size:11px; }
    .event strong { font-size:13px; }
    .event p { margin:4px 0 0; color:var(--muted); font-size:12px; line-height:1.5; }
    .hidden { display:none !important; }
    #notice { min-height:20px; color:var(--muted); font-size:13px; margin:11px 0 0; }
    #notice.error { color:var(--red); }
    @media (max-width:900px) { .layout { grid-template-columns:1fr; } .intro { min-height:auto; } .intro h1 { margin:55px 0 12px; } .boundary { margin-top:45px; } }
    @media (max-width:640px) { .steps { grid-template-columns:repeat(3,1fr); } .check-list { grid-template-columns:1fr; } .login-grid,.ready-grid { grid-template-columns:1fr 1fr; } main { padding:22px 15px 40px; } }
  </style>
</head>
<body>
<div class="layout">
  <section class="intro">
    <div class="brand"><div class="brand-mark">CS</div><span>AI-CS Channel Agent</span></div>
    <h1>第一次启动，<br>一步一步来。</h1>
    <p>完成环境检查、AI-CS 连接、独立浏览器登录与店铺身份确认。整个过程不需要编辑配置文件。</p>
    <div class="boundary">人工扫码登录 · 不读取客户消息<br>不自动回复 · 不提供发送入口</div>
  </section>
  <main>
    <div class="top"><div><div class="eyebrow">First Launch Experience V1</div><h2 id="page-title">欢迎使用 Channel Agent</h2><p class="sub" id="page-subtitle">准备安全地连接第一个拼多多店铺。</p></div><span class="state" id="state-badge" data-testid="first-launch-state">FIRST_START</span></div>
    <div class="progress" aria-label="首次启动进度"><i id="progress"></i></div>
    <div class="steps" aria-label="向导步骤"><div class="step" data-step="FIRST_START">开始</div><div class="step" data-step="CHECKING_ENVIRONMENT">环境</div><div class="step" data-step="CONNECTING_SERVER">AI-CS</div><div class="step" data-step="WAITING_CHANNEL_LOGIN">登录</div><div class="step" data-step="VERIFYING_STORE">店铺</div><div class="step" data-step="READY">完成</div></div>

    <section class="card hero-card">
      <div id="welcome-view">
        <h3>设置第一个渠道</h3><p>系统将自动创建受控 Workspace，并检查 Pilot 安全策略。不会要求输入店铺 ID、cookie、token 或密码。</p>
        <div class="platform"><div class="platform-icon">PDD</div><div><strong>拼多多商家聊天</strong><span>单店 · Pilot Mode · 人工审批</span></div></div>
        <div class="actions"><button class="btn primary" id="start-button">开始环境检查</button></div>
      </div>
      <div id="login-view" class="hidden">
        <h3>正在等待拼多多登录</h3><p>请在独立 Chrome 窗口中人工扫码。向导不会自动输入账号或读取 Cookie。</p>
        <div class="login-grid"><div class="metric"><span>Chrome</span><strong id="chrome-status">—</strong></div><div class="metric"><span>Profile</span><strong id="profile-name">—</strong></div><div class="metric"><span>Login</span><strong id="login-status">—</strong></div></div>
        <div class="actions"><button class="btn" id="reopen-button">重新打开浏览器</button><button class="btn primary" id="check-login-button">检查登录状态</button></div>
      </div>
      <div id="failure-view" class="hidden">
        <h3>首次启动已安全停止</h3><div class="failure"><strong id="failure-title">—</strong><p id="failure-message">—</p><p id="failure-action">—</p></div>
        <div class="actions"><button class="btn primary" id="reset-button">修复后重新开始</button></div>
      </div>
      <div id="ready-view" class="hidden">
        <h3>AI-CS Channel Agent 已就绪</h3><p>节点已进入单店 Pilot 运行边界，所有后续发送仍必须经过人工审批。</p>
        <div class="ready-grid"><div class="metric"><span>Node</span><strong id="ready-node">—</strong></div><div class="metric"><span>Store</span><strong id="ready-store">—</strong></div><div class="metric"><span>Browser</span><strong id="ready-browser">—</strong></div><div class="metric"><span>Session</span><strong id="ready-session">—</strong></div><div class="metric"><span>Channel</span><strong id="ready-channel">—</strong></div><div class="metric"><span>AI</span><strong id="ready-ai">—</strong></div><div class="metric"><span>Safety</span><strong id="ready-safety">—</strong></div><div class="metric"><span>Approval</span><strong id="ready-approval">—</strong></div></div>
        <div class="actions"><a class="btn primary" href="/agent/ui">进入运行控制台</a><button class="btn danger" id="rebind-button">重新绑定店铺</button></div>
      </div>
      <div id="notice" role="status" aria-live="polite"></div>
    </section>

    <section class="card doctor" id="doctor-panel"><div class="section-head"><h3>Environment Doctor</h3><span class="state" id="doctor-overall">未检查</span></div><div class="check-list" id="doctor-checks" data-testid="environment-doctor"></div></section>
    <section class="card timeline"><div class="section-head"><h3>运行时间线</h3><span class="state">用户可理解事件</span></div><ol class="events" id="events" data-testid="first-launch-timeline"><li class="event"><time>—</time><div><strong>等待开始</strong><p>尚未执行任何运行操作。</p></div></li></ol></section>
  </main>
</div>
<script>
  const $ = id => document.getElementById(id);
  const stateOrder=['FIRST_START','CHECKING_ENVIRONMENT','CONNECTING_SERVER','WAITING_CHANNEL_LOGIN','VERIFYING_STORE','READY'];
  const copy={FIRST_START:['欢迎使用 Channel Agent','准备安全地连接第一个拼多多店铺。'],CHECKING_ENVIRONMENT:['正在检查运行环境','检查 Windows、Chrome、AI-CS、Channel 与 Safety。'],CONNECTING_SERVER:['正在连接 AI-CS','验证 Gateway Health 与 Server Connection。'],WAITING_CHANNEL_LOGIN:['等待人工扫码登录','请在独立 Chrome 中完成登录。'],VERIFYING_STORE:['正在确认店铺身份','只读获取并验证当前店铺。'],READY:['首次启动完成','Channel Agent 已进入 Ready 状态。'],FAILED:['启动已安全停止','请按提示处理后重新开始。']};
  const time=value=>value?new Intl.DateTimeFormat('zh-CN',{hour:'2-digit',minute:'2-digit'}).format(new Date(value)):'—';
  const show=id=>$(id).classList.remove('hidden'); const hide=id=>$(id).classList.add('hidden');
  function renderDoctor(report){const root=$('doctor-checks'); root.replaceChildren(); if(!report){$('doctor-overall').textContent='未检查'; return;} $('doctor-overall').textContent=report.overall; report.checks.forEach(item=>{const row=document.createElement('div'); row.className='check '+item.status.toLowerCase(); const dot=document.createElement('i'); dot.className='check-dot'; const body=document.createElement('div'); const title=document.createElement('strong'); title.textContent=item.label+' · '+item.status; const detail=document.createElement('small'); detail.textContent=item.remediation||item.message; body.append(title,detail); row.append(dot,body); root.append(row);});}
  function renderTimeline(items){const root=$('events'); root.replaceChildren(); if(!items.length){root.innerHTML='<li class="event"><time>—</time><div><strong>等待开始</strong><p>尚未执行任何运行操作。</p></div></li>'; return;} items.forEach(item=>{const row=document.createElement('li'); row.className='event'; const at=document.createElement('time'); at.textContent=time(item.occurred_at); const body=document.createElement('div'); const title=document.createElement('strong'); title.textContent=item.title; const detail=document.createElement('p'); detail.textContent=item.detail; body.append(title,detail); row.append(at,body); root.append(row);});}
  function render(data){$('state-badge').textContent=data.state; $('progress').style.width=data.progress_percent+'%'; $('page-title').textContent=copy[data.state][0]; $('page-subtitle').textContent=copy[data.state][1]; document.querySelectorAll('.step').forEach(step=>{const index=stateOrder.indexOf(step.dataset.step); const current=data.state==='FAILED'?stateOrder.length:stateOrder.indexOf(data.state); step.classList.toggle('active',index<=current);}); ['welcome-view','login-view','failure-view','ready-view'].forEach(hide); if(data.state==='FIRST_START')show('welcome-view'); else if(data.state==='WAITING_CHANNEL_LOGIN'||data.state==='CHECKING_ENVIRONMENT'||data.state==='CONNECTING_SERVER'||data.state==='VERIFYING_STORE'){show('login-view');} else if(data.state==='FAILED')show('failure-view'); else if(data.state==='READY')show('ready-view'); $('chrome-status').textContent=data.browser.chrome; $('profile-name').textContent=data.workspace?data.workspace.profile_name:'pdd-pilot-single-store-001'; $('login-status').textContent=data.browser.login; if(data.failure){$('failure-title').textContent=data.failure.title; $('failure-message').textContent=data.failure.message; $('failure-action').textContent=data.failure.action;} if(data.ready){$('ready-node').textContent=data.ready.node; $('ready-store').textContent=data.ready.store; $('ready-browser').textContent=data.ready.browser; $('ready-session').textContent=data.ready.session; $('ready-channel').textContent=data.ready.channel; $('ready-ai').textContent=data.ready.ai; $('ready-safety').textContent=data.ready.safety; $('ready-approval').textContent=data.ready.approval;} $('start-button').disabled=!data.can_start; $('reopen-button').disabled=!data.can_reopen_browser; $('check-login-button').disabled=!data.can_check_login; renderDoctor(data.doctor); renderTimeline(data.timeline);}
  async function load(){const response=await fetch('/agent/first-launch/status',{headers:{Accept:'application/json'}}); if(!response.ok)throw new Error('首次启动状态不可用'); render(await response.json());}
  async function action(path){$('notice').className=''; $('notice').textContent='正在处理…'; try{const response=await fetch(path,{method:'POST',headers:{Accept:'application/json'}}); const data=await response.json(); if(!response.ok)throw new Error(data.detail&&data.detail.message?data.detail.message:'当前操作不可用'); render(data); $('notice').textContent='状态已更新';}catch(error){$('notice').className='error'; $('notice').textContent=error.message;}}
  $('start-button').addEventListener('click',()=>action('/agent/first-launch/start')); $('reopen-button').addEventListener('click',()=>action('/agent/first-launch/browser/reopen')); $('check-login-button').addEventListener('click',()=>action('/agent/first-launch/login/check')); $('reset-button').addEventListener('click',()=>action('/agent/first-launch/reset')); $('rebind-button').addEventListener('click',()=>{if(window.confirm('重新绑定会停止当前 Agent 并移除本地店铺绑定，是否继续？'))action('/agent/first-launch/reset');}); load().catch(error=>{$('notice').className='error'; $('notice').textContent=error.message;});
</script>
</body>
</html>
"""


__all__ = ["CHANNEL_AGENT_FIRST_LAUNCH_HTML"]
