from __future__ import annotations

from html import escape

from .models import DesktopAssistantSnapshot


CUSTOMER_ASSISTANT_UI_VERSION = "1.1"


def render_customer_assistant(snapshot: DesktopAssistantSnapshot) -> str:
    """Render a local, script-free approval view with real send disabled."""

    package = snapshot.reply_package
    question = escape(snapshot.current_question or "等待真实客户消息")
    reply = escape(
        package.reply_content
        if package and package.reply_content
        else "AI-CS 未生成可发送建议，已转人工处理"
    )
    store = escape(snapshot.store_name or snapshot.store_id or "未确认")
    product = escape(snapshot.product_summary or "当前页面未识别到商品")
    risk = escape(snapshot.risk_notice or "暂无风险评估")
    customer = escape(
        (snapshot.customer_reference or "未选择会话").replace("sha256:", "会话-")[:21]
    )
    citations = (
        "".join(
            f"<li><strong>{escape(item.title)}</strong>"
            f"<span>{escape(item.reference)}</span></li>"
            for item in package.citations
        )
        if package and package.citations
        else "<li>未返回可核验知识来源，必须由客服人工复核。</li>"
    )
    state = (
        "等待人工确认"
        if package and package.state == "WAITING_APPROVAL"
        else "需要人工处理"
        if package
        else "等待客户消息"
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AI-CS 客服助手</title>
  <style>
    body {{ margin:0; background:#f5f7fb; color:#172033; font:14px/1.6 "Microsoft YaHei",sans-serif; }}
    header,main {{ max-width:1080px; margin:auto; }} header {{ padding:28px 24px 12px; }}
    h1 {{ margin:0; font-size:24px; }} .sub {{ color:#637083; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:12px 24px 32px; }}
    section {{ background:white; border:1px solid #e4e8ef; border-radius:12px; padding:20px; }}
    .wide {{ grid-column:1/-1; }} dl {{ display:grid; grid-template-columns:130px 1fr; gap:8px; }}
    dt {{ color:#637083; }} dd {{ margin:0; font-weight:600; }} pre {{ white-space:pre-wrap; font:inherit; }}
    .safe {{ color:#087f5b; }} .warn {{ color:#b45309; }} button {{ padding:9px 16px; margin-right:8px; }}
    button[disabled] {{ cursor:not-allowed; opacity:.55; }} ul {{ padding-left:20px; }} li span {{ display:block; color:#637083; }}
  </style>
</head>
<body data-ui-version="{CUSTOMER_ASSISTANT_UI_VERSION}">
  <header><h1>AI-CS 客服助手</h1><p class="sub">AI 负责理解与建议，客服负责最终确认；当前真实发送保持关闭。</p></header>
  <main class="grid">
    <section><h2>运行状态</h2><dl>
      <dt>Agent</dt><dd>{'在线' if snapshot.agent_online else '离线'}</dd>
      <dt>PDD 工作台</dt><dd>{escape(snapshot.pdd_status)}</dd>
      <dt>当前店铺</dt><dd>{store}</dd>
      <dt>当前客户</dt><dd>{customer}</dd>
      <dt>处理阶段</dt><dd>{state}</dd>
    </dl></section>
    <section><h2>安全边界</h2><dl>
      <dt>人工审核</dt><dd class="safe">必须</dd>
      <dt>自动回复</dt><dd class="safe">关闭</dd>
      <dt>真实发送</dt><dd class="safe">关闭</dd>
      <dt>页面写操作</dt><dd class="safe">0</dd>
    </dl></section>
    <section class="wide"><h2>客户问题</h2><pre>{question}</pre><h3>商品信息</h3><p>{product}</p></section>
    <section class="wide"><h2>AI 建议回复</h2><pre>{reply}</pre><h3>知识来源</h3><ul>{citations}</ul>
      <h3>风险提示</h3><p class="warn">{risk}</p></section>
    <section class="wide"><h2>客服操作</h2>
      <button type="button" data-action="ADOPT_REPLY" disabled>采用回复</button><button type="button" data-action="EDIT_REPLY" disabled>修改回复</button>
      <button type="button" data-action="REGENERATE" disabled>重新生成</button><button type="button" data-action="CONFIRM_SEND" disabled>确认发送</button>
      <p class="sub">本阶段仅验证真实消息进入 AI-CS 并在助手中显示；不会写入 PDD 页面。</p>
    </section>
  </main>
</body></html>"""


__all__ = ["CUSTOMER_ASSISTANT_UI_VERSION", "render_customer_assistant"]
