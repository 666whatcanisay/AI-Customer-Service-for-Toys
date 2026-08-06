OPERATIONS_CONSOLE_UI_VERSION = "1.1"


OPERATIONS_CONSOLE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>AI-CS 智能客服运营控制中心</title>
  <link rel="stylesheet" href="/ops/assets/operations-console.css?v=1.1">
  <script defer src="/ops/assets/operations-console.js?v=1.1"></script>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
        <div><strong>AI-CS 智能客服</strong><small>运营执行控制中心</small></div>
      </div>
      <nav id="primary-nav">
        <button class="nav-item active" data-view="overview"><span class="nav-icon">总</span><span>运行总览</span></button>
        <button class="nav-item" data-view="trace"><span class="nav-icon">追</span><span>会话流程追踪</span></button>
        <button class="nav-item" data-view="approvals"><span class="nav-icon">审</span><span>人工审核中心</span><span id="nav-approval-count" class="nav-count">0</span></button>
        <button class="nav-item" data-view="executions"><span class="nav-icon">录</span><span>执行审计记录</span></button>
        <button class="nav-item" data-view="channels"><span class="nav-icon">店</span><span>店铺与渠道</span></button>
        <button class="nav-item" data-view="recovery"><span class="nav-icon">诊</span><span>问题诊断与恢复</span><span id="nav-recovery-count" class="nav-count danger hidden">0</span></button>
      </nav>
      <div class="sidebar-boundary">
        <div class="boundary-light"></div>
        <div><strong>必须人工审核</strong><small>自动执行已关闭</small></div>
      </div>
      <div class="version">中文控制台 V1.1</div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <div class="breadcrumb">AI-CS / 客服运营 / <span id="breadcrumb-view">运行总览</span></div>
          <h1 id="page-title">运行总览</h1>
        </div>
        <div class="topbar-actions">
          <div id="freshness" class="freshness"><span class="pulse-dot"></span><span>正在连接本地运行节点</span></div>
          <button id="refresh-button" class="icon-button" type="button" aria-label="刷新数据" title="刷新数据">刷新</button>
        </div>
      </header>

      <main>
        <section id="view-overview" class="view active" aria-labelledby="page-title">
          <article id="system-banner" class="system-banner tone-neutral">
            <div class="system-symbol" aria-hidden="true">客</div>
            <div class="system-copy"><div class="eyebrow">当前运营状态</div><h2 id="system-title">正在读取系统状态</h2><p id="system-description">正在汇总本地运行节点与安全控制状态。</p></div>
            <div class="system-next"><span>建议下一步</span><strong id="system-next-step">等待状态检查完成</strong></div>
          </article>

          <section class="metric-strip" aria-label="运行摘要">
            <article class="metric-card"><span>系统运行</span><strong id="metric-runtime">--</strong><small id="metric-runtime-note">生命周期状态</small></article>
            <article class="metric-card"><span>店铺渠道</span><strong id="metric-channels">--</strong><small id="metric-channels-note">已连接 / 已配置</small></article>
            <article class="metric-card action-metric"><span>待人工审核</span><strong id="metric-approvals">--</strong><small>需要客服处理</small></article>
            <article class="metric-card"><span>执行记录</span><strong id="metric-executions">--</strong><small id="metric-executions-note">最近审计记录</small></article>
            <article class="metric-card critical-metric"><span>结果待确认</span><strong id="metric-unknown">--</strong><small>禁止自动重试</small></article>
          </section>

          <section class="panel">
            <div class="panel-heading"><div><span class="section-kicker">服务运行情况</span><h2>关键能力状态</h2></div><span class="source-note">数据来源：运行节点与安全控制面</span></div>
            <div id="component-grid" class="component-grid"></div>
          </section>

          <div class="overview-grid">
            <section class="panel attention-panel">
              <div class="panel-heading"><div><span class="section-kicker">客服待办</span><h2>需要处理</h2></div><button class="text-button" data-go="approvals">进入审核中心</button></div>
              <div id="attention-list" class="attention-list"></div>
            </section>
            <section class="panel">
              <div class="panel-heading"><div><span class="section-kicker">实时动态</span><h2>最近业务事件</h2></div><span id="event-total" class="count-chip">0 条</span></div>
              <div id="overview-events" class="event-stream"></div>
            </section>
          </div>
        </section>

        <section id="view-trace" class="view">
          <div class="page-intro"><div><span class="section-kicker">会话全链路</span><h2>会话流程追踪</h2><p>查看一条客户消息从 AI 分析到结果凭证的完整进度。</p></div></div>
          <section class="trace-search panel">
            <label for="trace-query">输入消息、会话、决策、审核、执行或凭证编号</label>
            <div class="search-row"><input id="trace-query" autocomplete="off" placeholder="粘贴任意流程编号"><button id="trace-search-button" class="primary-button" type="button">查询流程</button></div>
            <div id="trace-suggestions" class="suggestion-row"></div>
          </section>
          <section id="trace-empty" class="empty-state panel"><div class="empty-symbol">追</div><h3>选择最近流程或输入编号</h3><p>系统将展示流程进行到哪一步、为什么停留，以及下一步可以做什么。</p></section>
          <section id="trace-detail" class="trace-detail hidden">
            <article class="trace-posture panel"><div><span class="section-kicker">当前流程状态</span><h2 id="trace-current-step">--</h2><p id="trace-time-range">--</p></div><div class="trace-guidance"><div><span>停留原因</span><strong id="trace-stop-reason">--</strong></div><div><span>安全的下一步</span><strong id="trace-next-step">--</strong></div></div></article>
            <section class="panel"><div class="panel-heading"><div><span class="section-kicker">处理进度</span><h2>客户消息到结果凭证</h2></div><button id="copy-trace-id" class="text-button">复制流程编号</button></div><div id="trace-flow" class="trace-flow"></div></section>
            <div class="trace-grid"><section class="panel"><div class="panel-heading"><h2>关联业务编号</h2></div><dl id="trace-identifiers" class="identifier-list"></dl></section><section class="panel"><div class="panel-heading"><h2>业务事件时间线</h2><span id="trace-event-count" class="count-chip">0 条</span></div><div id="trace-events" class="event-stream trace-events"></div></section></div>
          </section>
        </section>

        <section id="view-approvals" class="view">
          <div class="page-intro"><div><span class="section-kicker">人工把关</span><h2>人工审核中心</h2><p>核对客户问题、AI 建议、知识依据与风险后，再决定是否进入执行队列。</p></div><span id="approval-heading-count" class="large-count">0 条待审核</span></div>
          <article class="safety-callout"><div class="shield">!</div><div><strong>必须人工审核</strong><p>批准只会创建一条“待执行”任务，不会启动执行程序，也不会发送渠道消息。</p></div><span class="safety-chip">自动执行已关闭</span></article>
          <div class="approval-layout">
            <section class="panel approval-queue"><div class="panel-heading"><h2>待审核会话</h2><span class="source-note">等待最久的优先</span></div><div id="approval-list" class="approval-list"></div></section>
            <section id="approval-review" class="panel approval-review"><div class="empty-state compact"><div class="empty-symbol">审</div><h3>请选择一条会话进行审核</h3><p>审核内容按需读取，不会复制到运行事件日志。</p></div></section>
          </div>
        </section>

        <section id="view-executions" class="view">
          <div class="page-intro"><div><span class="section-kicker">不可篡改的操作留痕</span><h2>执行审计记录</h2><p>查看每次受控执行的状态变化、结果凭证和后续处理建议。</p></div></div>
          <section class="panel ledger-panel"><div class="toolbar"><div class="segmented" id="execution-filter"><button class="active" data-state="ALL">全部</button><button data-state="PENDING">待执行</button><button data-state="RUNNING">执行中</button><button data-state="SUCCESS">已成功</button><button data-state="FAILED">已失败</button><button data-state="UNKNOWN">结果待确认</button></div><input id="execution-search" class="compact-input" placeholder="搜索执行或决策编号"></div><div class="table-wrap"><table><thead><tr><th>状态</th><th>执行编号</th><th>决策 / 审核</th><th>尝试次数</th><th>结果凭证</th><th>下一步</th><th>时间</th></tr></thead><tbody id="execution-table"></tbody></table></div></section>
        </section>

        <section id="view-channels" class="view">
          <div class="page-intro"><div><span class="section-kicker">单店隔离运行</span><h2>店铺与渠道</h2><p>查看每个店铺的渠道实例、登录会话、适配器和心跳状态。</p></div><span class="source-note">凭证、Cookie 与密钥始终隐藏</span></div>
          <div id="channel-list" class="channel-list"></div>
        </section>

        <section id="view-recovery" class="view">
          <div class="page-intro"><div><span class="section-kicker">有限恢复与人工接管</span><h2>问题诊断与恢复</h2><p>查看异常原因、恢复尝试以及需要人工介入的问题。</p></div></div>
          <article class="safety-callout recovery-callout"><div class="shield">诊</div><div><strong>禁止无限重试</strong><p>结果待确认或恢复次数用尽时，系统立即停止并等待人工判断。</p></div><span class="safety-chip">默认安全阻断</span></article>
          <section class="panel"><div class="panel-heading"><div><h2>问题与恢复记录</h2><span class="source-note">来源：运行恢复与执行恢复事件</span></div><span id="recovery-total" class="count-chip">0 条</span></div><div id="recovery-list" class="recovery-list"></div></section>
        </section>
      </main>
    </section>
  </div>

  <dialog id="action-dialog" class="action-dialog">
    <form id="action-form" method="dialog">
      <div class="dialog-heading"><div><span id="dialog-kicker" class="section-kicker">人工审核安全边界</span><h2 id="dialog-title">确认操作</h2></div><button id="dialog-close" class="icon-button" type="button" aria-label="关闭">关闭</button></div>
      <div id="dialog-warning" class="dialog-warning"></div>
      <label>操作员账号<input id="action-operator" required pattern="[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}" placeholder="请输入企业账号"></label>
      <label id="action-reason-wrap" class="hidden">拒绝原因<textarea id="action-reason" maxlength="500" placeholder="请说明需要修改或拒绝的原因"></textarea></label>
      <label>输入下方确认短语<input id="action-confirmation" required autocomplete="off"></label>
      <code id="required-confirmation" class="confirmation-phrase"></code>
      <label class="acknowledgement"><input id="action-ack" type="checkbox"><span>我已核对客户问题和 AI 建议，并确认批准后只创建“待执行”任务。</span></label>
      <div class="dialog-actions"><button id="action-cancel" class="secondary-button" type="button">取消</button><button id="action-submit" class="primary-button" type="submit">确认</button></div>
    </form>
  </dialog>
  <div id="toast-region" class="toast-region" aria-live="polite"></div>
  <div id="loading-bar" class="loading-bar" aria-hidden="true"></div>
</body>
</html>
"""


OPERATIONS_CONSOLE_CSS = r"""
:root{color-scheme:dark;--bg:#070b11;--surface:#0d131c;--surface-2:#111a25;--surface-3:#151f2c;--line:#222d3b;--line-strong:#304154;--text:#f2f5f8;--muted:#8c9aaa;--faint:#5f6c7b;--blue:#6aa9ff;--cyan:#56d7d0;--green:#53d69a;--amber:#f4ba5d;--red:#ff7474;--violet:#a78bfa;--sidebar:244px;--radius:12px;--shadow:0 16px 48px rgba(0,0,0,.25)}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",system-ui,-apple-system,sans-serif;font-size:14px}button,input,textarea{font:inherit}button{color:inherit}.hidden{display:none!important}.app-shell{min-height:100vh}.sidebar{position:fixed;inset:0 auto 0 0;width:var(--sidebar);display:flex;flex-direction:column;background:#090e15;border-right:1px solid var(--line);padding:18px 13px;z-index:20}.brand{display:flex;align-items:center;gap:11px;padding:4px 8px 24px}.brand strong,.brand small{display:block}.brand strong{font-size:14px}.brand small{font-size:11px;color:var(--muted);margin-top:2px}.brand-mark{display:grid;grid-template-columns:repeat(3,5px);align-items:end;gap:3px;width:28px;height:28px;padding:6px;border:1px solid #31526d;border-radius:8px;background:#0d1c28}.brand-mark span{display:block;background:var(--cyan);border-radius:2px}.brand-mark span:nth-child(1){height:7px}.brand-mark span:nth-child(2){height:14px}.brand-mark span:nth-child(3){height:10px}
nav{display:flex;flex-direction:column;gap:4px}.nav-item{width:100%;height:42px;display:grid;grid-template-columns:26px 1fr auto;align-items:center;gap:8px;border:0;background:transparent;border-radius:8px;padding:0 9px;color:var(--muted);text-align:left;cursor:pointer}.nav-item:hover{background:#111a24;color:var(--text)}.nav-item.active{background:#142333;color:#fff;box-shadow:inset 2px 0 var(--cyan)}.nav-icon{width:22px;height:22px;border:1px solid var(--line-strong);border-radius:6px;display:grid;place-items:center;font:700 10px/1 "Cascadia Mono",monospace}.nav-item.active .nav-icon{border-color:#3e7188;color:var(--cyan)}.nav-count{min-width:20px;height:20px;padding:0 6px;display:grid;place-items:center;background:#243242;border-radius:10px;font-size:10px;color:#dce8f4}.nav-count.danger{background:#4a2026;color:#ffb2b2}.sidebar-boundary{margin-top:auto;display:flex;gap:9px;padding:12px 10px;border:1px solid #2a3a47;border-radius:9px;background:#0d1720}.boundary-light{width:8px;height:8px;margin-top:4px;border-radius:50%;background:var(--amber);box-shadow:0 0 10px rgba(244,186,93,.4)}.sidebar-boundary strong,.sidebar-boundary small{display:block}.sidebar-boundary strong{font-size:11px}.sidebar-boundary small{font-size:10px;color:var(--muted);margin-top:3px}.version{padding:13px 10px 0;color:var(--faint);font:10px/1 "Cascadia Mono",monospace}
.workspace{margin-left:var(--sidebar);min-height:100vh}.topbar{height:82px;position:sticky;top:0;z-index:15;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(34,45,59,.85);background:rgba(7,11,17,.9);backdrop-filter:blur(16px)}.breadcrumb{font-size:11px;color:var(--faint);margin-bottom:5px}.breadcrumb span{color:var(--muted)}h1{font-size:20px;line-height:1.2;margin:0;letter-spacing:-.02em}.topbar-actions{display:flex;align-items:center;gap:10px}.freshness{height:34px;display:flex;align-items:center;gap:8px;padding:0 11px;border:1px solid var(--line);border-radius:8px;color:var(--muted);font-size:11px}.pulse-dot{width:7px;height:7px;background:var(--cyan);border-radius:50%;box-shadow:0 0 0 4px rgba(86,215,208,.08)}.icon-button,.text-button,.primary-button,.secondary-button{border-radius:8px;cursor:pointer}.icon-button{height:34px;padding:0 11px;border:1px solid var(--line-strong);background:var(--surface);font-size:11px}.icon-button:hover{border-color:#4d657e;background:var(--surface-2)}main{max-width:1580px;margin:auto;padding:26px 28px 50px}.view{display:none}.view.active{display:block}.section-kicker,.eyebrow{display:block;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;margin-bottom:5px}.page-intro{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:18px}.page-intro h2{margin:0 0 5px;font-size:25px;letter-spacing:-.035em}.page-intro p{margin:0;color:var(--muted)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 10px 28px rgba(0,0,0,.11)}.panel-heading{min-height:61px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 17px;border-bottom:1px solid var(--line)}.panel-heading h2{font-size:14px;margin:0}.source-note{font-size:10px;color:var(--faint)}.count-chip,.safety-chip{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:11px;border:1px solid var(--line-strong);color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.04em}.large-count{font:600 17px/1 "Cascadia Mono",monospace;color:var(--amber)}
.system-banner{min-height:132px;display:grid;grid-template-columns:64px 1fr minmax(240px,360px);align-items:center;gap:20px;padding:22px 24px;border:1px solid var(--line);border-radius:14px;background:var(--surface);box-shadow:var(--shadow)}.system-banner.tone-good{border-color:#225344}.system-banner.tone-action{border-color:#66502d}.system-banner.tone-critical{border-color:#67343b}.system-symbol{width:54px;height:54px;display:grid;place-items:center;border:1px solid #335065;border-radius:14px;background:#0b1b27;color:var(--cyan);font:700 14px/1 "Cascadia Mono",monospace}.system-copy h2{font-size:23px;margin:0 0 6px;letter-spacing:-.03em}.system-copy p{margin:0;color:var(--muted)}.system-next{align-self:stretch;display:flex;flex-direction:column;justify-content:center;padding-left:22px;border-left:1px solid var(--line)}.system-next span{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em}.system-next strong{font-size:13px;margin-top:7px;line-height:1.4}.metric-strip{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:10px;margin:14px 0}.metric-card{min-height:104px;padding:15px 16px;background:var(--surface);border:1px solid var(--line);border-radius:10px}.metric-card>span,.metric-card>small{display:block;color:var(--muted)}.metric-card>span{font-size:11px}.metric-card strong{display:block;margin:7px 0 5px;font:650 25px/1 "Cascadia Mono",monospace;letter-spacing:-.04em}.metric-card small{font-size:10px}.action-metric{border-bottom:2px solid var(--amber)}.critical-metric{border-bottom:2px solid var(--red)}
.component-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line)}.component-card{min-height:96px;padding:14px 16px;background:var(--surface)}.component-top{display:flex;align-items:center;justify-content:space-between}.component-name{text-transform:capitalize;font-weight:600}.status-indicator{display:inline-flex;align-items:center;gap:6px;font:650 10px/1 "Cascadia Mono",monospace}.status-indicator:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--amber)}.status-indicator.good:before{background:var(--green)}.status-indicator.bad:before{background:var(--red)}.status-indicator.unknown:before{background:var(--violet)}.component-reason{margin-top:17px;color:var(--muted);font:10px/1.4 "Cascadia Mono",monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.overview-grid{display:grid;grid-template-columns:minmax(330px,.85fr) minmax(520px,1.5fr);gap:12px;margin-top:12px}.attention-list,.event-stream,.approval-list,.recovery-list{padding:8px}.attention-item{display:grid;grid-template-columns:9px 1fr auto;gap:11px;align-items:start;padding:12px 9px;border-bottom:1px solid var(--line)}.attention-item:last-child{border-bottom:0}.attention-bar{width:3px;height:32px;background:var(--amber);border-radius:2px}.attention-bar.critical{background:var(--red)}.attention-item strong,.attention-item small{display:block}.attention-item strong{font-size:12px}.attention-item small{color:var(--muted);margin-top:3px;font-size:10px}.text-button{border:0;background:transparent;color:var(--blue);font-size:11px;padding:5px}.text-button:hover{text-decoration:underline}.event-item{display:grid;grid-template-columns:76px 10px minmax(180px,1fr) auto;gap:9px;align-items:center;min-height:42px;padding:5px 8px;border-bottom:1px solid var(--line);cursor:pointer}.event-item:last-child{border-bottom:0}.event-item:hover{background:var(--surface-2)}.event-time{font:10px/1 "Cascadia Mono",monospace;color:var(--faint)}.event-dot{width:7px;height:7px;border-radius:50%;background:var(--blue)}.event-dot.SUCCESS{background:var(--green)}.event-dot.UNKNOWN,.event-dot.FAILED,.event-dot.BLOCKED{background:var(--red)}.event-name{font-size:11px;font-weight:600}.event-trace{font:9px/1 "Cascadia Mono",monospace;color:var(--faint)}
.trace-search{padding:17px;margin-bottom:12px}.trace-search label{display:block;font-size:11px;font-weight:600;margin-bottom:8px}.search-row{display:grid;grid-template-columns:1fr auto;gap:8px}.search-row input,.compact-input,.action-dialog input,.action-dialog textarea{background:#080d14;color:var(--text);border:1px solid var(--line-strong);border-radius:8px;outline:0}.search-row input{height:42px;padding:0 13px;font-family:"Cascadia Mono",monospace}.search-row input:focus,.compact-input:focus,.action-dialog input:focus,.action-dialog textarea:focus{border-color:#477da2;box-shadow:0 0 0 3px rgba(106,169,255,.08)}.primary-button{height:42px;padding:0 17px;border:1px solid #35718a;background:#16455a;color:#effcff;font-weight:650}.primary-button:hover{background:#1b536b}.primary-button.danger{border-color:#81454d;background:#59252c}.secondary-button{height:40px;padding:0 15px;border:1px solid var(--line-strong);background:var(--surface-2)}.suggestion-row{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.suggestion{border:1px solid var(--line);background:var(--surface-2);color:var(--muted);border-radius:12px;padding:4px 9px;font:9px/1 "Cascadia Mono",monospace;cursor:pointer}.empty-state{min-height:260px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:28px;color:var(--muted)}.empty-state.compact{min-height:360px;border:0;box-shadow:none}.empty-state h3{color:var(--text);font-size:15px;margin:12px 0 4px}.empty-state p{max-width:480px;margin:0}.empty-symbol{width:42px;height:42px;display:grid;place-items:center;border:1px dashed #3b4c5e;border-radius:50%;color:var(--cyan);font:700 12px/1 "Cascadia Mono",monospace}.trace-posture{display:grid;grid-template-columns:.8fr 1.4fr;gap:25px;padding:20px 22px;margin-bottom:12px}.trace-posture h2{font-size:22px;margin:0 0 7px}.trace-posture p{color:var(--muted);margin:0}.trace-guidance{display:grid;grid-template-columns:1fr 1.6fr;gap:1px;background:var(--line);border:1px solid var(--line);border-radius:9px;overflow:hidden}.trace-guidance div{background:var(--surface-2);padding:13px}.trace-guidance span,.trace-guidance strong{display:block}.trace-guidance span{color:var(--muted);font-size:10px;margin-bottom:6px}.trace-guidance strong{font-size:12px}.trace-flow{display:grid;grid-template-columns:repeat(11,auto);align-items:center;justify-content:center;gap:0;padding:33px 20px 38px;overflow-x:auto}.trace-node{width:116px;display:flex;flex-direction:column;align-items:center;text-align:center}.trace-node-symbol{width:40px;height:40px;display:grid;place-items:center;border:2px solid var(--line-strong);border-radius:50%;background:var(--surface-2);color:var(--muted);font:700 10px/1 "Cascadia Mono",monospace}.trace-node.complete .trace-node-symbol{border-color:var(--green);color:var(--green);background:#0d211c}.trace-node.active .trace-node-symbol{border-color:var(--amber);color:var(--amber);background:#241d11;box-shadow:0 0 0 5px rgba(244,186,93,.07)}.trace-node.failed .trace-node-symbol{border-color:var(--red);color:var(--red);background:#29171a}.trace-node strong{font-size:11px;margin-top:9px}.trace-node small{max-width:110px;color:var(--faint);font:9px/1.35 "Cascadia Mono",monospace;margin-top:3px;overflow:hidden;text-overflow:ellipsis}.trace-connector{width:36px;height:2px;background:var(--line-strong);margin-top:-28px}.trace-connector.complete{background:var(--green)}.trace-grid{display:grid;grid-template-columns:.75fr 1.25fr;gap:12px;margin-top:12px}.identifier-list{margin:0;padding:8px 17px 16px}.identifier-row{display:grid;grid-template-columns:110px 1fr;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}.identifier-row:last-child{border-bottom:0}.identifier-row dt{color:var(--muted);font-size:10px}.identifier-row dd{margin:0;font:10px/1.4 "Cascadia Mono",monospace;word-break:break-all}.trace-events{max-height:390px;overflow:auto}
.safety-callout{display:grid;grid-template-columns:38px 1fr auto;align-items:center;gap:13px;padding:14px 16px;margin-bottom:12px;border:1px solid #65502e;border-radius:10px;background:#1b1710}.shield{width:32px;height:32px;display:grid;place-items:center;border:1px solid #8b6a32;border-radius:8px;color:var(--amber);font-weight:800}.safety-callout strong,.safety-callout p{display:block;margin:0}.safety-callout p{color:#b6a581;font-size:11px;margin-top:3px}.safety-chip{border-color:#735c35;color:var(--amber)}.approval-layout{display:grid;grid-template-columns:minmax(310px,.72fr) minmax(560px,1.28fr);gap:12px}.approval-queue,.approval-review{min-height:500px}.approval-card{width:100%;display:block;text-align:left;padding:13px 11px;border:0;border-bottom:1px solid var(--line);background:transparent;cursor:pointer}.approval-card:hover,.approval-card.selected{background:var(--surface-2)}.approval-card.selected{box-shadow:inset 2px 0 var(--amber)}.approval-card-top{display:flex;align-items:center;justify-content:space-between}.approval-card strong{font-size:11px}.approval-card-meta{display:flex;gap:8px;margin-top:8px;color:var(--muted);font-size:10px}.approval-review-content{padding:17px}.review-header{display:flex;justify-content:space-between;gap:12px;margin-bottom:17px}.review-header h3{font-size:18px;margin:3px 0 0}.review-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:13px}.review-field{padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--surface-2)}.review-field span,.review-field strong{display:block}.review-field span{font-size:9px;letter-spacing:.06em;color:var(--muted)}.review-field strong{margin-top:4px;font-size:11px}.review-sections{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:13px 0}.review-section{min-width:0;padding:13px 14px;border:1px solid var(--line);border-radius:9px;background:#0a121a}.review-section.customer-question,.review-section.ai-suggestion{grid-column:1/-1}.review-section.review-next{grid-column:1/-1;border-color:#3b4d60;background:#0c151f}.review-section-label{display:block;color:var(--blue);font-size:10px;font-weight:700;margin-bottom:8px}.review-section p,.review-section pre{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.65 "Segoe UI",sans-serif;color:#e7edf4}.customer-question{border-left:2px solid var(--blue)}.ai-suggestion{border-left:2px solid var(--cyan)}.source-list{display:flex;flex-wrap:wrap;gap:6px}.source-item{padding:5px 8px;border:1px solid #31506a;border-radius:6px;color:#b9d7ee;font-size:10px}.source-empty{color:var(--muted)!important;font-size:11px!important}.risk-level{display:inline-flex;padding:5px 8px;border-radius:6px;background:#3c2e18;color:var(--amber);font-size:11px;margin-bottom:7px}.review-risk p{color:var(--muted);font-size:11px}.review-boundary{padding:10px 12px;border-left:2px solid var(--amber);background:#17150f;color:#b9aa8b;font-size:10px}.review-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:17px}
.toolbar{display:flex;justify-content:space-between;gap:15px;padding:13px 15px;border-bottom:1px solid var(--line)}.segmented{display:flex;gap:3px;flex-wrap:wrap}.segmented button{height:30px;padding:0 10px;border:1px solid transparent;border-radius:6px;background:transparent;color:var(--muted);font-size:10px;cursor:pointer}.segmented button:hover{background:var(--surface-2)}.segmented button.active{background:#18283a;border-color:#28435f;color:#ddecfa}.compact-input{height:32px;min-width:260px;padding:0 10px;font-size:10px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th{height:40px;padding:0 12px;border-bottom:1px solid var(--line);color:var(--faint);font-size:9px;text-transform:uppercase;letter-spacing:.08em;text-align:left}td{height:54px;padding:8px 12px;border-bottom:1px solid var(--line);font-size:10px}tbody tr:hover{background:var(--surface-2)}.mono{font-family:"Cascadia Mono",Consolas,monospace}.sub-id{display:block;color:var(--faint);font-size:9px;margin-top:3px}.state-chip{display:inline-flex;align-items:center;height:22px;padding:0 8px;border:1px solid var(--line-strong);border-radius:11px;font:700 9px/1 "Cascadia Mono",monospace}.state-chip.SUCCESS,.state-chip.CONNECTED,.state-chip.RECOVERED{border-color:#285b48;color:var(--green);background:#0e201a}.state-chip.PENDING,.state-chip.AUTH_REQUIRED,.state-chip.RECOVERING{border-color:#68512b;color:var(--amber);background:#211b10}.state-chip.FAILED,.state-chip.UNKNOWN,.state-chip.MANUAL_INTERVENTION,.state-chip.EXPIRED{border-color:#6e343c;color:var(--red);background:#251417}
.channel-list{display:grid;grid-template-columns:repeat(2,minmax(350px,1fr));gap:12px}.channel-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}.channel-card-header{display:flex;align-items:center;justify-content:space-between;padding:15px 17px;border-bottom:1px solid var(--line)}.channel-identity{display:flex;align-items:center;gap:11px}.platform-mark{width:35px;height:35px;display:grid;place-items:center;border:1px solid #39536b;border-radius:8px;color:var(--cyan);font:700 10px/1 "Cascadia Mono",monospace;text-transform:uppercase}.channel-identity strong,.channel-identity small{display:block}.channel-identity small{color:var(--muted);margin-top:3px}.channel-body{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line)}.channel-stat{min-height:83px;padding:13px 16px;background:var(--surface)}.channel-stat span,.channel-stat strong,.channel-stat small{display:block}.channel-stat span{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.channel-stat strong{font-size:11px;margin-top:7px}.channel-stat small{color:var(--faint);font-size:9px;margin-top:4px}.channel-footer{display:flex;justify-content:space-between;padding:10px 16px;color:var(--faint);font:9px/1.4 "Cascadia Mono",monospace}.recovery-callout{border-color:#3f4568;background:#121522}.recovery-callout .shield{border-color:#555e91;color:var(--violet)}.recovery-list{padding:0}.recovery-item{display:grid;grid-template-columns:140px 155px 1fr 90px 160px;align-items:center;gap:10px;min-height:66px;padding:10px 16px;border-bottom:1px solid var(--line)}.recovery-item:last-child{border-bottom:0}.recovery-item strong,.recovery-item small{display:block}.recovery-item small{color:var(--faint);margin-top:3px;font-size:9px}.recovery-next{color:var(--muted);font-size:10px;line-height:1.45}.empty-row{padding:24px;color:var(--muted);font-size:11px;text-align:center}
.action-dialog{width:min(540px,calc(100vw - 30px));padding:0;border:1px solid var(--line-strong);border-radius:13px;background:var(--surface);color:var(--text);box-shadow:0 30px 90px rgba(0,0,0,.6)}.action-dialog::backdrop{background:rgba(2,5,8,.78);backdrop-filter:blur(4px)}.action-dialog form{padding:20px}.dialog-heading{display:flex;justify-content:space-between;align-items:start;margin-bottom:15px}.dialog-heading h2{font-size:19px;margin:0}.dialog-warning{padding:11px 12px;margin-bottom:14px;border:1px solid #624d2b;border-radius:8px;background:#1b170f;color:#c7b58f;font-size:11px;line-height:1.5}.action-dialog label{display:block;margin-top:12px;font-size:10px;color:var(--muted)}.action-dialog label>input,.action-dialog label>textarea{display:block;width:100%;margin-top:6px;padding:10px;color:var(--text)}.action-dialog textarea{min-height:80px;resize:vertical}.confirmation-phrase{display:block;margin-top:7px;padding:9px 10px;background:#080d14;border:1px dashed #41546a;border-radius:7px;color:var(--cyan);font-size:10px;word-break:break-all}.acknowledgement{display:grid!important;grid-template-columns:16px 1fr;gap:8px;align-items:start}.acknowledgement input{width:14px!important;margin:1px 0 0!important}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:19px}.toast-region{position:fixed;right:20px;bottom:20px;z-index:100;display:flex;flex-direction:column;gap:8px}.toast{max-width:420px;padding:12px 14px;border:1px solid var(--line-strong);border-radius:9px;background:#121c27;box-shadow:var(--shadow);font-size:11px}.toast.success{border-color:#2d654f}.toast.error{border-color:#793d45}.loading-bar{position:fixed;top:0;left:var(--sidebar);right:0;height:2px;z-index:50;transform:scaleX(0);transform-origin:left;background:var(--cyan);transition:transform .2s}.loading-bar.active{transform:scaleX(.72);animation:loading 1.3s ease-in-out infinite}@keyframes loading{50%{transform:scaleX(.95)}}
@media(max-width:1100px){:root{--sidebar:204px}.metric-strip{grid-template-columns:repeat(3,1fr)}.component-grid{grid-template-columns:repeat(2,1fr)}.overview-grid,.approval-layout,.trace-grid{grid-template-columns:1fr}.channel-list{grid-template-columns:1fr}.recovery-item{grid-template-columns:120px 130px 1fr}.recovery-item>*:nth-child(4),.recovery-item>*:nth-child(5){display:none}}
@media(max-width:760px){:root{--sidebar:0px}.sidebar{position:static;width:100%;height:auto;padding:10px}.brand{padding:4px 6px 10px}nav{display:grid;grid-template-columns:repeat(3,1fr)}.nav-item{grid-template-columns:22px 1fr;height:36px}.nav-count{display:none}.sidebar-boundary,.version{display:none}.workspace{margin-left:0}.topbar{position:static;height:auto;padding:14px 16px}.freshness{display:none}main{padding:16px}.system-banner{grid-template-columns:46px 1fr}.system-next{grid-column:1/-1;border-left:0;border-top:1px solid var(--line);padding:13px 0 0}.metric-strip{grid-template-columns:repeat(2,1fr)}.component-grid{grid-template-columns:1fr}.trace-posture{grid-template-columns:1fr}.trace-guidance{grid-template-columns:1fr}.toolbar{flex-direction:column}.compact-input{min-width:0;width:100%}.channel-body{grid-template-columns:1fr}.safety-callout{grid-template-columns:35px 1fr}.safety-chip{grid-column:2}.recovery-item{grid-template-columns:1fr 1fr}.trace-flow{justify-content:start}.loading-bar{left:0}}
"""


OPERATIONS_CONSOLE_JS = r"""
'use strict';

const ConsoleUI = (() => {
  const API = {
    async request(path, options = {}) {
      const response = await fetch(path, {cache: 'no-store', ...options, headers: {'Content-Type': 'application/json', ...(options.headers || {})}});
      if (!response.ok) {
        let detail = '';
        try { const payload = await response.json(); detail = payload.detail || ''; } catch (_) {}
        throw new Error(humanError(detail, response.status));
      }
      return response.status === 204 ? null : response.json();
    },
    snapshot() { return this.request('/ops/console/snapshot'); },
    channels() { return this.request('/session-runtime/v1/instances'); },
    recoveries() { return this.request('/ops/recoveries?limit=100'); },
    trace(id) { return this.request(`/ops/traces/${encodeURIComponent(id)}`); },
    decision(id) { return this.request(`/ops/approvals/${encodeURIComponent(id)}/review`); },
    approvalAction(action, decisionId, body) { return this.request(`/ops/approvals/${encodeURIComponent(decisionId)}/${action}`, {method: 'POST', body: JSON.stringify(body)}); }
  };

  const state = {view: 'overview', snapshot: null, channels: [], recoveries: [], trace: null, selectedApproval: null, decision: null, executionFilter: 'ALL', executionSearch: '', loading: false, action: null};
  const viewTitles = {overview: '运行总览', trace: '会话流程追踪', approvals: '人工审核中心', executions: '执行审计记录', channels: '店铺与渠道', recovery: '问题诊断与恢复'};
  const statusLabels = {
    HEALTHY: '正常', UNHEALTHY: '异常', RUNNING: '运行中', WAITING_APPROVAL: '待人工审核', UNKNOWN: '结果待确认',
    STARTING: '正在启动', READY: '已就绪', DEGRADED: '服务降级', STOPPING: '正在停止', STOPPED: '已停止', FAILED: '失败',
    CONNECTED: '已连接', DISCONNECTED: '未连接', CONNECTING: '正在连接', RECOVERING: '恢复中', RECOVERED: '已恢复',
    ENABLED: '已启用', DISABLED: '已停用', BLOCKED: '已阻断', EXPIRED: '已过期', AUTH_REQUIRED: '等待登录', ACTIVE: '活跃',
    PENDING: '待执行', SUCCESS: '已成功', COMPLETED: '已完成', APPROVED: '已批准', REJECTED: '已拒绝', WAITING: '等待处理',
    MANUAL_INTERVENTION: '需要人工介入', CREATED: '已创建', INIT: '初始化', OFFLINE: '离线', ONLINE: '在线',
    NONE: '无会话', REAL_CONNECTED: '真实平台已连接', SIMULATED_ISOLATED: '模拟隔离运行', UNSPECIFIED: '未标注',
    LOW: '低风险', MEDIUM: '中风险', HIGH: '高风险', AVAILABLE: '已提供', NOT_PROVIDED: '当前未提供'
  };
  const componentLabels = {runtime: '系统运行', channel: '渠道服务', browser: '浏览器', gateway: 'AI 服务', storage: '数据存储', worker: '执行程序', outbox: '事件投递', policy: '安全策略', BROWSER: '浏览器', EXECUTION: '执行任务', CHANNEL: '渠道服务', GATEWAY: 'AI 服务', STORAGE: '数据存储'};
  const eventLabels = {
    CHANNEL_CONNECTED: '渠道已连接', MESSAGE_RECEIVED: '收到客户消息', MESSAGE_NORMALIZED: '消息已标准化', SESSION_CHANGED: '登录会话状态变化',
    DECISION_REQUEST_SENT: '已提交 AI 分析', DECISION_CREATED: 'AI 建议已生成', APPROVAL_REQUIRED: '等待人工审核', APPROVAL_GRANTED: '人工审核已批准', APPROVAL_REJECTED: '人工审核已拒绝',
    EXECUTION_STARTED: '开始执行', EXECUTION_SUCCESS: '执行成功', EXECUTION_FAILED: '执行失败', EXECUTION_UNKNOWN: '执行结果待确认', RECEIPT_CREATED: '结果凭证已生成',
    RECOVERY_STARTED: '开始恢复', RECOVERY_COMPLETED: '恢复完成', RECOVERY_MANUAL_INTERVENTION: '恢复需要人工介入'
  };
  const reasonLabels = {
    RUNTIME_INITIALIZED: '系统已初始化，尚未启动', CHANNEL_SESSIONS_DEGRADED: '存在未连接或异常的店铺会话', BROWSER_STOPPED: '浏览器运行环境尚未启动',
    AI_CS_GATEWAY_HEALTHY: 'AI 服务连接正常', SQLITE_HEALTHY: '本地数据存储正常', WORKER_STATUS_REPORTED: '执行程序状态已上报', OUTBOX_STATUS_REPORTED: '事件投递状态已上报',
    EXECUTION_POLICY_ENABLED: '受控执行策略已启用', EXECUTION_POLICY_BLOCKED: '安全策略已阻断新执行', STATUS_PROVIDER_UNAVAILABLE: '暂时无法获取状态',
    NO_SESSION_FAILURE: '登录会话未报告异常', HEALTH_CHECK_COMPLETED: '健康检查已完成'
  };
  const traceLabels = {
    RECEIVING: ['正在接收客户消息', '等待消息完成标准化', '检查渠道与消息接收状态'],
    REQUESTING_DECISION: ['AI 正在分析', '等待 AI 服务返回建议', '检查 AI 服务连接状态'],
    WAITING_APPROVAL: ['等待人工审核', 'AI 建议已生成，尚未获得人工确认', '前往人工审核中心核对并处理'],
    EXECUTION_PENDING: ['等待受控执行', '人工已批准，任务尚未被执行程序领取', '确认安全策略后等待执行程序处理'],
    EXECUTION_RUNNING: ['正在执行', '受控执行正在进行', '等待执行结果，不要重复操作'],
    EXECUTION_FAILED: ['执行失败', '执行程序已确认失败', '查看失败原因并由人工决定后续操作'],
    EXECUTION_UNKNOWN: ['执行结果待确认', '触发后无法确认渠道侧结果', '禁止自动重试，人工核对渠道侧结果'],
    COMPLETED: ['流程已完成', '执行结果与凭证均已记录', '无需处理，可查看执行审计记录'],
    RECOVERY: ['正在恢复', '系统正在进行有限次数的安全恢复', '等待恢复结果'],
    MANUAL_INTERVENTION: ['需要人工介入', '系统无法安全地自动判断下一步', '前往问题诊断与恢复进行人工处理']
  };
  const identifierLabels = {trace_id: '流程编号', message_id: '消息编号', conversation_id: '会话编号', request_id: 'AI 请求编号', decision_id: '决策编号', approval_id: '审核编号', execution_id: '执行编号', receipt_id: '凭证编号', store_id: '店铺编号'};
  const $ = id => document.getElementById(id);
  const text = (node, value) => { node.textContent = value === null || value === undefined || value === '' ? '--' : String(value); return node; };
  const short = value => !value ? '--' : (value.length > 22 ? `${value.slice(0, 9)}...${value.slice(-8)}` : value);
  const formatTime = value => value ? new Intl.DateTimeFormat('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}).format(new Date(value)) : '--';
  const relative = value => { if (!value) return '--'; const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000)); if (seconds < 60) return `${seconds} 秒前`; if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`; if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`; return `${Math.floor(seconds / 86400)} 天前`; };
  const statusTone = status => ['FAILED','UNKNOWN','BLOCKED','UNHEALTHY','DEGRADED','MANUAL_INTERVENTION','EXPIRED'].includes(status) ? 'bad' : ['HEALTHY','READY','RUNNING','CONNECTED','SUCCESS','RECOVERED','ENABLED'].includes(status) ? 'good' : status === 'STATUS_PROVIDER_UNAVAILABLE' ? 'unknown' : 'warn';
  const create = (tag, className, value) => { const node = document.createElement(tag); if (className) node.className = className; if (value !== undefined) text(node, value); return node; };
  const clear = node => node.replaceChildren();
  const statusLabel = status => statusLabels[String(status || '').replace(/[\s/]+/g, '_')] || '状态待确认';
  const reasonLabel = reason => reasonLabels[reason] || '请在问题诊断中查看详细原因';
  const eventLabel = type => eventLabels[type] || '系统状态变化';
  const suggestionText = value => value ? value.replace(/^\[(?:MOCK|FAKE) AI-CS SUGGESTION\] Received:\s*/i, '建议回复：') : 'AI 未提供回复建议';
  const stateChip = status => create('span', `state-chip ${status}`, statusLabel(status));

  function humanError(detail, status) {
    const normalized = String(detail || '').toLowerCase();
    if (status === 404) return '未找到对应记录，请检查编号后重试。';
    if (normalized.includes('confirmation') || normalized.includes('确认短语')) return '确认短语不正确，请按页面提示完整输入。';
    if (normalized.includes('kill switch')) return '安全停止开关已开启，当前不能创建执行任务。';
    if (normalized.includes('approval')) return '当前审核状态不允许执行此操作。';
    return `操作未完成，请检查输入或系统安全状态（状态码 ${status}）。`;
  }

  function setLoading(value) { state.loading = value; $('loading-bar').classList.toggle('active', value); $('refresh-button').disabled = value; }
  function toast(message, tone = 'success') { const node = create('div', `toast ${tone}`, message); $('toast-region').append(node); setTimeout(() => node.remove(), 4800); }

  function navigate(view) {
    if (!viewTitles[view]) view = 'overview';
    state.view = view;
    document.querySelectorAll('.view').forEach(node => node.classList.toggle('active', node.id === `view-${view}`));
    document.querySelectorAll('.nav-item').forEach(node => node.classList.toggle('active', node.dataset.view === view));
    text($('page-title'), viewTitles[view]); text($('breadcrumb-view'), viewTitles[view]);
    if (location.hash !== `#${view}`) history.replaceState(null, '', `#${view}`);
  }

  async function refresh() {
    if (state.loading) return;
    setLoading(true);
    try {
      const [snapshot, channels, recoveries] = await Promise.all([API.snapshot(), API.channels(), API.recoveries()]);
      state.snapshot = snapshot; state.channels = channels; state.recoveries = recoveries;
      renderAll();
      text($('freshness').lastElementChild, `更新于 ${formatTime(snapshot.generated_at)}｜本地数据实时读取`);
    } catch (error) {
      text($('freshness').lastElementChild, '本地运行节点暂时不可用');
      toast(error.message, 'error');
    } finally { setLoading(false); }
  }

  function renderAll() {
    if (!state.snapshot) return;
    renderOverview(); renderTraceSuggestions(); renderApprovals(); renderExecutions(); renderChannels(); renderRecoveries(); renderNavCounts();
  }

  function renderNavCounts() {
    const pending = state.snapshot.pending_approvals.length;
    const manual = state.recoveries.filter(item => item.requires_manual_action).length;
    text($('nav-approval-count'), pending); text($('nav-recovery-count'), manual); $('nav-recovery-count').classList.toggle('hidden', manual === 0);
  }

  function renderOverview() {
    const snapshot = state.snapshot, runtime = snapshot.runtime, pending = snapshot.pending_approvals.length, executions = snapshot.recent_executions;
    const connected = state.channels.filter(item => item.instance.status === 'CONNECTED').length;
    let tone = 'neutral', title = '正在评估客服系统状态', description = '系统正在汇总当前运行信息。', nextStep = '等待状态检查完成';
    if (runtime.execution_unknown > 0) { tone = 'critical'; title = `${runtime.execution_unknown} 条执行结果需要人工确认`; description = '系统无法确认渠道侧结果，已禁止自动重试。'; nextStep = '前往执行审计记录，人工核对实际结果'; }
    else if (runtime.overall !== 'HEALTHY') { tone = 'critical'; title = `客服系统当前${statusLabel(runtime.overall)}`; description = '一项或多项服务未就绪，业务流程可能暂时停留。'; nextStep = '查看下方异常项或进入问题诊断与恢复'; }
    else if (pending > 0) { tone = 'action'; title = `${pending} 条 AI 建议等待人工审核`; description = '流程已安全停在执行前，不会自动发送。'; nextStep = '前往人工审核中心处理等待最久的会话'; }
    else if (runtime.overall === 'HEALTHY') { tone = 'good'; title = '智能客服执行服务运行正常'; description = '当前没有需要立即处理的异常或审核任务。'; nextStep = '继续关注会话与执行动态'; }
    $('system-banner').className = `system-banner tone-${tone}`; text($('system-title'), title); text($('system-description'), description); text($('system-next-step'), nextStep);
    text($('metric-runtime'), statusLabel(runtime.runtime.status)); text($('metric-runtime-note'), reasonLabel(runtime.runtime.reason_code));
    text($('metric-channels'), `${connected}/${state.channels.length}`); text($('metric-channels-note'), '已连接 / 已配置');
    text($('metric-approvals'), pending); text($('metric-executions'), executions.length); text($('metric-executions-note'), '最近审计记录'); text($('metric-unknown'), runtime.execution_unknown);
    renderComponents(runtime); renderAttention(runtime, pending); renderEventStream($('overview-events'), snapshot.recent_events.slice(0, 12)); text($('event-total'), `${runtime.event_count} 条`);
  }

  function renderComponents(runtime) {
    const root = $('component-grid'); clear(root);
    ['runtime', 'channel', 'browser', 'gateway', 'storage', 'worker', 'outbox', 'policy'].forEach(name => {
      const value = runtime[name], card = create('article', 'component-card'), top = create('div', 'component-top');
      top.append(create('span', 'component-name', componentLabels[name]), create('span', `status-indicator ${statusTone(value.status)}`, statusLabel(value.status)));
      card.append(top, create('div', 'component-reason', reasonLabel(value.reason_code))); root.append(card);
    });
  }

  function renderAttention(runtime, pending) {
    const root = $('attention-list'); clear(root); const items = [];
    if (runtime.execution_unknown > 0) items.push({critical: true, title: `${runtime.execution_unknown} 条执行结果待确认`, detail: '需要人工核对渠道侧实际结果', view: 'executions'});
    if (pending > 0) items.push({critical: false, title: `${pending} 条会话等待审核`, detail: '执行已安全阻断，不会自动发送', view: 'approvals'});
    const unhealthy = ['channel','browser','gateway','storage','worker','outbox','policy'].filter(key => statusTone(runtime[key].status) === 'bad');
    unhealthy.forEach(key => items.push({critical: true, title: `${componentLabels[key]}${statusLabel(runtime[key].status)}`, detail: reasonLabel(runtime[key].reason_code), view: key === 'channel' ? 'channels' : 'recovery'}));
    if (!items.length) { root.append(emptyRow('当前没有待处理事项，所有安全控制仍保持开启。')); return; }
    items.forEach(item => { const row = create('div', 'attention-item'); row.append(create('span', `attention-bar ${item.critical ? 'critical' : ''}`)); const copy = create('div'); copy.append(create('strong', '', item.title), create('small', '', item.detail)); const button = create('button', 'text-button', '查看'); button.addEventListener('click', () => navigate(item.view)); row.append(copy, button); root.append(row); });
  }

  function renderEventStream(root, events) {
    clear(root); if (!events.length) { root.append(emptyRow('暂无业务事件。')); return; }
    events.forEach(event => { const row = create('div', 'event-item'); row.tabIndex = 0; row.append(create('span', 'event-time', formatTime(event.timestamp).slice(6)), create('span', `event-dot ${event.status}`), create('span', 'event-name', eventLabel(event.event_type)), create('span', 'event-trace', short(event.trace_id))); const open = () => loadTrace(event.trace_id); row.addEventListener('click', open); row.addEventListener('keydown', e => { if (e.key === 'Enter') open(); }); root.append(row); });
  }

  function renderTraceSuggestions() {
    const root = $('trace-suggestions'); clear(root); const seen = new Set();
    state.snapshot.recent_events.forEach(event => { if (seen.size >= 6 || seen.has(event.trace_id)) return; seen.add(event.trace_id); const button = create('button', 'suggestion', short(event.trace_id)); button.title = event.trace_id; button.addEventListener('click', () => loadTrace(event.trace_id)); root.append(button); });
  }

  async function loadTrace(identifier) {
    const value = (identifier || $('trace-query').value).trim(); if (!value) return;
    $('trace-query').value = value; setLoading(true);
    try { state.trace = await API.trace(value); renderTrace(); navigate('trace'); }
    catch (error) { state.trace = null; $('trace-detail').classList.add('hidden'); $('trace-empty').classList.remove('hidden'); text($('trace-empty').querySelector('h3'), '未找到对应流程'); text($('trace-empty').querySelector('p'), error.message); toast(error.message, 'error'); }
    finally { setLoading(false); }
  }

  function renderTrace() {
    const trace = state.trace; if (!trace) return; $('trace-empty').classList.add('hidden'); $('trace-detail').classList.remove('hidden');
    const guidance = traceLabels[trace.why_stopped] || ['流程状态待确认', '系统暂时无法判断停留原因', '前往问题诊断与恢复查看详情'];
    text($('trace-current-step'), guidance[0]); text($('trace-time-range'), `${formatTime(trace.started_at)} 至 ${formatTime(trace.updated_at)}`); text($('trace-stop-reason'), guidance[1]); text($('trace-next-step'), guidance[2]); text($('trace-event-count'), `${trace.events.length} 条`);
    renderTraceFlow(trace); renderIdentifiers(trace); renderEventStream($('trace-events'), trace.events);
  }

  function renderTraceFlow(trace) {
    const root = $('trace-flow'); clear(root); const types = new Set(trace.events.map(event => event.event_type));
    const failed = types.has('EXECUTION_UNKNOWN') || types.has('EXECUTION_FAILED'); const decisionReady = types.has('DECISION_CREATED');
    const steps = [
      {name: '客户消息', id: trace.message_id, complete: types.has('MESSAGE_NORMALIZED'), active: !types.has('DECISION_REQUEST_SENT')},
      {name: 'AI 分析', id: trace.request_id, complete: decisionReady, active: types.has('DECISION_REQUEST_SENT') && !decisionReady},
      {name: '回复建议', id: trace.decision_id, complete: decisionReady, active: false},
      {name: '人工确认', id: trace.approval_id, complete: types.has('APPROVAL_GRANTED') || types.has('APPROVAL_REJECTED'), active: types.has('APPROVAL_REQUIRED') && !types.has('APPROVAL_GRANTED') && !types.has('APPROVAL_REJECTED'), failed: types.has('APPROVAL_REJECTED')},
      {name: '受控执行', id: trace.execution_id, complete: types.has('EXECUTION_SUCCESS'), active: types.has('EXECUTION_STARTED') && !failed && !types.has('EXECUTION_SUCCESS'), failed},
      {name: '结果凭证', id: trace.receipt_id, complete: types.has('RECEIPT_CREATED'), active: false, failed: failed && !types.has('RECEIPT_CREATED')}
    ];
    steps.forEach((step, index) => { const node = create('div', `trace-node ${step.failed ? 'failed' : step.complete ? 'complete' : step.active ? 'active' : ''}`); node.append(create('div', 'trace-node-symbol', step.failed ? '!' : step.complete ? '✓' : String(index + 1)), create('strong', '', step.name), create('small', '', short(step.id))); root.append(node); if (index < steps.length - 1) root.append(create('span', `trace-connector ${step.complete ? 'complete' : ''}`)); });
  }

  function renderIdentifiers(trace) {
    const root = $('trace-identifiers'); clear(root); ['trace_id','message_id','conversation_id','request_id','decision_id','approval_id','execution_id','receipt_id','store_id'].forEach(key => { const row = create('div', 'identifier-row'); row.append(create('dt', '', identifierLabels[key]), create('dd', '', trace[key])); root.append(row); });
  }

  function renderApprovals() {
    const items = [...state.snapshot.pending_approvals].sort((a,b) => new Date(a.waiting_since) - new Date(b.waiting_since)); const root = $('approval-list'); clear(root); text($('approval-heading-count'), `${items.length} 条待审核`);
    if (!items.length) { root.append(emptyRow('当前没有等待人工审核的会话。')); if (!state.selectedApproval) renderApprovalPlaceholder(); return; }
    items.forEach(item => { const button = create('button', `approval-card ${state.selectedApproval === item.decision_id ? 'selected' : ''}`); button.type = 'button'; const top = create('div', 'approval-card-top'); top.append(create('strong', '', short(item.decision_id)), stateChip('WAITING_APPROVAL')); const meta = create('div', 'approval-card-meta'); meta.append(create('span', '', item.action === 'SUGGEST_REPLY' ? 'AI 回复建议' : '无需回复'), create('span', '', `已等待 ${relative(item.waiting_since)}`)); button.append(top, meta); button.addEventListener('click', () => selectApproval(item)); root.append(button); });
    if (!state.selectedApproval) selectApproval(items[0]);
  }

  function renderApprovalPlaceholder() { const root = $('approval-review'); clear(root); const empty = create('div', 'empty-state compact'); empty.append(create('div', 'empty-symbol', '审'), create('h3', '', '请选择一条会话进行审核'), create('p', '', '客户问题和 AI 建议只在审核时按需读取，不写入运行事件日志。')); root.append(empty); }

  async function selectApproval(item) {
    state.selectedApproval = item.decision_id; state.decision = null; renderApprovals(); const root = $('approval-review'); clear(root); root.append(emptyRow('正在读取审核内容…'));
    try { state.decision = await API.decision(item.decision_id); renderApprovalReview(item, state.decision); }
    catch (error) { clear(root); root.append(emptyRow(error.message)); toast(error.message, 'error'); }
  }

  function renderApprovalReview(item, decision) {
    const root = $('approval-review'); clear(root); const content = create('div', 'approval-review-content'), header = create('div', 'review-header'), heading = create('div'); heading.append(create('span', 'section-kicker', '需要客服人工确认'), create('h3', '', decision.action === 'SUGGEST_REPLY' ? 'AI 回复建议审核' : 'AI 建议无需回复')); header.append(heading, stateChip(decision.state)); content.append(header);
    const grid = create('div', 'review-grid'); [['决策编号', short(decision.decision_id)], ['会话编号', short(decision.conversation_id)], ['AI 服务版本', decision.gateway_version], ['等待时间', relative(item.waiting_since)]].forEach(([label,value]) => { const field = create('div', 'review-field'); field.append(create('span', '', label), create('strong', '', value)); grid.append(field); }); content.append(grid);
    const customer = create('div', 'review-section customer-question'); customer.append(create('span', 'review-section-label', '客户问题'), create('p', '', decision.customer_question));
    const suggestion = create('div', 'review-section ai-suggestion'); suggestion.append(create('span', 'review-section-label', 'AI 建议'), create('pre', '', suggestionText(decision.ai_suggestion)));
    const source = create('div', 'review-section knowledge-source'); source.append(create('span', 'review-section-label', '知识来源')); const sourceList = create('div', 'source-list'); if (decision.knowledge_sources.length) decision.knowledge_sources.forEach(value => sourceList.append(create('span', 'source-item', value))); else sourceList.append(create('p', 'source-empty', '当前 AI 响应未提供可核验的知识来源，请勿据此自动执行。')); source.append(sourceList);
    const risk = create('div', 'review-section review-risk'); risk.append(create('span', 'review-section-label', '风险等级'), create('strong', `risk-level risk-${decision.risk_level}`, decision.risk_level === 'UNSPECIFIED' ? '未标注（按需人工复核）' : statusLabel(decision.risk_level)), create('p', '', decision.risk_basis));
    const next = create('div', 'review-section review-next'); next.append(create('span', 'review-section-label', '下一步操作'), create('p', '', decision.next_step));
    const reviewSections = create('div', 'review-sections'); reviewSections.append(customer, suggestion, source, risk, next); content.append(reviewSections, create('div', 'review-boundary', '权限边界：批准只记录人工决定并创建一条“待执行”任务。本控制台不会启动执行程序，也不会向真实渠道发送消息。'));
    const actions = create('div', 'review-actions'), reject = create('button', 'secondary-button', '拒绝并要求修改'), approve = create('button', 'primary-button', '批准并加入待执行队列'); reject.addEventListener('click', () => openActionDialog('reject', decision.decision_id)); approve.addEventListener('click', () => openActionDialog('approve', decision.decision_id)); actions.append(reject, approve); content.append(actions); root.append(content);
  }

  function renderExecutions() {
    const root = $('execution-table'); clear(root); const query = state.executionSearch.toLowerCase(); const items = state.snapshot.recent_executions.filter(item => (state.executionFilter === 'ALL' || item.state === state.executionFilter) && (!query || item.execution_id.toLowerCase().includes(query) || item.decision_id.toLowerCase().includes(query)));
    if (!items.length) { const row = document.createElement('tr'), cell = document.createElement('td'); cell.colSpan = 7; cell.append(emptyRow('没有符合当前筛选条件的执行记录。')); row.append(cell); root.append(row); return; }
    items.forEach(item => { const row = document.createElement('tr'); const status = document.createElement('td'); status.append(stateChip(item.state)); row.append(status, tableCell(short(item.execution_id), 'mono'), compoundCell(short(item.decision_id), short(item.approval_id)), tableCell(item.attempt), compoundCell(short(item.receipt_id), item.receipt_outcome ? statusLabel(item.receipt_outcome) : '尚未生成凭证'), tableCell(executionNextStep(item)), tableCell(formatTime(item.created_at))); root.append(row); });
  }

  function executionNextStep(item) {
    const next = {PENDING: '等待受控执行程序领取', RUNNING: '等待结果，请勿重复操作', SUCCESS: '已完成，可查看结果凭证', FAILED: '查看失败原因后人工决定是否重试', UNKNOWN: '禁止自动重试，人工核对渠道侧结果'};
    return next[item.state] || '请在问题诊断中查看详情';
  }

  function renderChannels() {
    const root = $('channel-list'); clear(root); if (!state.channels.length) { root.append(emptyRow('尚未配置店铺渠道。')); return; }
    state.channels.forEach(view => { const instance = view.instance, session = view.session, healthRaw = view.adapter_health.details && (view.adapter_health.details.reason_code || view.adapter_health.details.lifecycle), healthNote = healthRaw ? reasonLabel(healthRaw) : '健康检查已完成', card = create('article', 'channel-card'), header = create('div', 'channel-card-header'), identity = create('div', 'channel-identity'), mark = create('div', 'platform-mark', instance.platform === 'pdd' ? '拼' : '测'), copy = create('div'); copy.append(create('strong', '', instance.store_id), create('small', '', instance.platform === 'pdd' ? '拼多多渠道' : '本地模拟渠道')); identity.append(mark, copy); header.append(identity, stateChip(instance.status)); const body = create('div', 'channel-body'); [['登录会话', session ? statusLabel(session.status) : '无会话', session ? short(session.session_id) : '当前没有活动会话'], ['渠道适配器', statusLabel(view.adapter_health.status), healthNote], ['平台连接', view.real_platform_connected ? '真实平台已连接' : '模拟隔离运行', view.real_platform_connected ? '连接状态已确认' : '真实平台访问保持关闭'], ['最近心跳', session && session.heartbeat_time ? relative(session.heartbeat_time) : '尚未记录', session && session.failure_code ? '会话存在异常，请查看诊断' : '登录会话未报告异常']].forEach(([label,value,note]) => { const box = create('div', 'channel-stat'); box.append(create('span','',label), create('strong','',value), create('small','',note)); body.append(box); }); const footer = create('div', 'channel-footer'); footer.append(create('span','',short(instance.instance_id)), create('span','',`检查于 ${formatTime(view.checked_at)}`)); card.append(header, body, footer); root.append(card); });
  }

  function renderRecoveries() {
    const root = $('recovery-list'); clear(root); text($('recovery-total'), `${state.recoveries.length} 条`); if (!state.recoveries.length) { root.append(emptyRow('当前没有问题恢复记录。')); return; }
    state.recoveries.forEach(item => { const row = create('article', 'recovery-item'), identity = create('div'); identity.append(create('strong','',short(item.recovery_id)), create('small','',formatTime(item.started_at))); const component = create('div'); component.append(create('strong','',componentLabels[item.component] || '系统服务'), create('small','',reasonLabel(item.reason_code))); const next = item.requires_manual_action ? '需要人工处理，系统不会继续自动重试' : item.state === 'RECOVERED' ? '恢复已完成，可继续观察运行状态' : '等待有限次数的安全恢复结果'; row.append(identity, component, create('div','recovery-next',next), create('div','mono',`第 ${item.attempts} 次`), stateChip(item.state)); root.append(row); });
  }

  function openActionDialog(action, decisionId) {
    state.action = {action, decisionId}; const approve = action === 'approve', phrase = `${approve ? '批准' : '拒绝'} ${decisionId}`;
    text($('dialog-title'), approve ? '批准 AI 回复建议' : '拒绝 AI 回复建议'); text($('dialog-warning'), approve ? '批准后只创建一条“待执行”任务，不启动执行程序，也不发送渠道消息。' : '拒绝后该建议不可执行，且不会创建执行任务。'); text($('required-confirmation'), phrase); $('action-confirmation').placeholder = phrase; $('action-confirmation').value = ''; $('action-operator').value = ''; $('action-reason').value = ''; $('action-ack').checked = false; $('action-reason-wrap').classList.toggle('hidden', approve); $('action-submit').classList.toggle('danger', !approve); text($('action-submit'), approve ? '确认批准并加入待执行队列' : '确认拒绝'); $('action-dialog').showModal();
  }

  function closeActionDialog() { if ($('action-dialog').open) $('action-dialog').close(); state.action = null; }

  async function submitAction(event) {
    event.preventDefault(); if (!state.action) return; const {action, decisionId} = state.action;
    if (!$('action-ack').checked) { toast('请先确认已核对内容并理解执行安全边界。', 'error'); return; }
    const body = {operator: $('action-operator').value.trim(), confirmation_text: $('action-confirmation').value.trim(), acknowledgement: 'HUMAN_ACTION_REVIEWED_NO_AUTOMATIC_EXECUTION', reason: action === 'reject' ? $('action-reason').value.trim() : null};
    setLoading(true);
    try { const result = await API.approvalAction(action, decisionId, body); closeActionDialog(); state.selectedApproval = null; state.decision = null; toast(action === 'approve' ? `已批准，执行任务 ${short(result.execution_id)} 正在等待受控处理，未自动运行。` : '已拒绝该建议，未创建执行任务。'); setLoading(false); await refresh(); navigate(action === 'approve' ? 'executions' : 'approvals'); }
    catch (error) { toast(error.message, 'error'); }
    finally { setLoading(false); }
  }

  function tableCell(value, className = '') { return create('td', className, value); }
  function compoundCell(primary, secondary) { const cell = document.createElement('td'); cell.append(create('span','mono',primary), create('span','sub-id',secondary)); return cell; }
  function emptyRow(message) { return create('div', 'empty-row', message); }

  function bind() {
    document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => navigate(button.dataset.view)));
    document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.go)));
    $('refresh-button').addEventListener('click', refresh); $('trace-search-button').addEventListener('click', () => loadTrace()); $('trace-query').addEventListener('keydown', event => { if (event.key === 'Enter') loadTrace(); });
    $('copy-trace-id').addEventListener('click', async () => { if (!state.trace) return; try { await navigator.clipboard.writeText(state.trace.trace_id); toast('流程编号已复制。'); } catch (_) { toast('无法访问剪贴板，请手动复制。', 'error'); } });
    document.querySelectorAll('#execution-filter button').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('#execution-filter button').forEach(item => item.classList.toggle('active', item === button)); state.executionFilter = button.dataset.state; renderExecutions(); }));
    $('execution-search').addEventListener('input', event => { state.executionSearch = event.target.value; renderExecutions(); });
    $('dialog-close').addEventListener('click', closeActionDialog); $('action-cancel').addEventListener('click', closeActionDialog); $('action-form').addEventListener('submit', submitAction);
    window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));
  }

  async function start() { bind(); navigate(location.hash.slice(1) || 'overview'); await refresh(); if (state.view === 'trace' && !state.trace && state.snapshot && state.snapshot.recent_events.length) await loadTrace(state.snapshot.recent_events[0].trace_id); setInterval(refresh, 5000); }
  return {start};
})();

document.addEventListener('DOMContentLoaded', ConsoleUI.start);
"""


__all__ = [
    "OPERATIONS_CONSOLE_CSS",
    "OPERATIONS_CONSOLE_HTML",
    "OPERATIONS_CONSOLE_JS",
    "OPERATIONS_CONSOLE_UI_VERSION",
]
