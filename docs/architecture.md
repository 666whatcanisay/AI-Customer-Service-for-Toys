# Channel Engine Foundation V1 Architecture

## 责任边界

```text
Fake Channel
    -> Conversation / Message
    -> Fake AI-CS Gateway
    -> Decision WAITING_APPROVAL
    -> Human Approval
    -> Fake Execution
    -> Receipt + Event + Transactional Outbox
```

Foundation不调用真实AI-CS，也不执行真实渠道动作。

## 模块

| 模块 | 责任 |
|---|---|
| `channel` | 渠道消息Protocol和Fake Channel |
| `browser` | 浏览器执行端口；Foundation默认禁用 |
| `conversation` | 消息接收、Conversation创建、Decision编排 |
| `execution` | 人工批准后的Fake执行和Receipt生成 |
| `gateway` | AI-CS Gateway Protocol与Fake Gateway |
| `storage` | SQLite ORM、Repository、Execution Ledger、Outbox |
| `monitor` | Foundation健康与边界状态 |
| `policy` | 人工批准和UNKNOWN禁止重试规则 |
| `models` | Pydantic实体、枚举和状态机 |

## 状态机

### Message

`RECEIVED -> PROCESSING -> COMPLETED | FAILED`

### Decision

`CREATED -> WAITING_APPROVAL -> APPROVED | REJECTED`

### Execution

`PENDING -> RUNNING -> SUCCESS | FAILED | UNKNOWN`

`UNKNOWN`是需要人工对账的终态，Foundation不提供自动重试转换。

## 数据一致性

SQLite保存Conversation、Message、Decision、Approval、Execution、Receipt和Event。每个Event同时产生一条Outbox记录，二者在同一数据库事务中提交。后续真实消息发布器只能消费Outbox，不得重新推断业务事件。

## Clean-room规则

- 不导入Starboat源码或包。
- 不依赖AI-CS源码目录。
- Gateway只依赖本项目定义的协议模型。
- 真实渠道Adapter必须在后续独立Gate中实现。
