# RC5 Troubleshooting Runbook

## 服务健康

```powershell
curl.exe -s http://127.0.0.1:8420/api/health
curl.exe -s http://127.0.0.1:8422/health
curl.exe -ks https://127.0.0.1:18443/health
```

预期端口：AI-CS `8420`、Platform `8422`、Host `18443`。

## 按链路定位

| 卡点 | 检查 |
|---|---|
| Provider | Observation 格式、store/conversation、幂等键 |
| ChannelAgent | spool、ACK、Cursor、Identity/Binding |
| Host Persist | 数据库可写、HOST_ACK_COMMITTED |
| Buffer | BUFFER_COMMITTED、合并窗口 |
| Context | 商品/SKU/订单映射、店铺隔离 |
| AI | 8420 健康、Ollama/Embedding、超时 |
| Quality Gate | risk、citations、required_fields、warnings |
| Confirmation | Decision 状态和客服权限 |
| ExecutionPrepared | preparation_id、real_send=false、零 Receipt |

## 常见处理

- AI 慢：先等待并看 trace，不要重复创建多条会话。
- AI 失败：确认 8420 健康；恢复后用新消息重试，失败不得生成发送 Decision。
- 界面旧状态：点击刷新；核对 UI 哈希，不要删除 Profile。
- 端口占用：先查 OwningProcess，禁止盲目结束 Edge/Agent。
- 升级失败：保留数据，按回滚手册恢复；禁止清空 Identity、Binding 或 Session。

