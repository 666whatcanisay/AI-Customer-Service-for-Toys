# Replay Fixture Guide

取得第一个完整手机测试买家会话后立即生成 Replay。

```powershell
.\.venv\Scripts\python.exe scripts\build_pdd_sanitized_replay.py `
  --input .runtime\real-pdd-pilot\<run>\raw\bounded-read.json `
  --output .runtime\real-pdd-pilot\<run>\replay\pdd-page-fixture.json `
  --conversation-id <当前测试会话ID> `
  --message-id <测试消息ID>
```

必须显式逐条传入测试消息 ID。工具只保留一个活动会话，对店铺、客户、会话、消息、商品和 SKU 标识符做替换，对手机号、证件号、支付号和邮箱做脱敏，并清空订单字段。

生成结果标记为：

- `source=SYNTHETIC_SANITIZED`
- `sanitized=true`
- `pdd_network_requests=0`

原始捕获只允许存在于本次 `.runtime` Pilot 目录；脱敏 Replay 通过后删除或加密隔离原始文件。Replay 必须经相同 Driver、Mapper、Spool、Host 链，不使用测试旁路。

