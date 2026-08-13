# RC5 Post-Pilot Issues

本清单仅记录非 P0 问题。RC5/PDD Pilot 期间不得顺手扩大重构。

| ID | 等级 | 问题 | 影响 | 处理时机 |
|---|---|---|---|---|
| PP-001 | P1 | 真实活动会话标记当前出现两个匹配，conversation/customer 稳定映射尚未冻结 | 阻塞 `REAL_PDD_ADAPTER_READY`，必须 fail-closed | 下一次真实 PDD READ Change Gate |
| PP-002 | P1 | 尚无首个经过隐私审批的真实 Replay | 离开真实 PDD 后不能复现页面差异 | 第一个完整测试会话后立即生成 |
| PP-003 | P1 | Host、Buffer、Offline Control、Spool 是跨库投影链 | 崩溃时需统一对账与重建证据 | READ Gate 整批完成后的 Full Gate |
| PP-004 | P1 | VPN TUN/虚拟网卡可在路由层接管 Edge，`--no-proxy-server` 只能绕过系统代理 | 可能影响 PDD 登录/长连接和出口稳定性 | 单独网络 Change Gate；先测路由，不扩浏览器架构 |
| PP-005 | P2 | `message_observation_enabled=true` 但浏览器停止时状态显示 `WAITING_IDENTITY` | 容易让运维误解为 Observer 正在运行 | Pilot 后收敛状态命名和诊断说明 |
| PP-006 | P2 | Replay Approval 是同机完整性锚点，不是外部不可篡改审计 | 不能作为正式合规审计承诺 | 商业发布阶段按需要接外部密钥/追加审计 |
| PP-007 | P2 | 三套 `PDDWorkspaceSnapshot` 并存 | Selector/字段变化可能重复修改 | 首批真实 Replay 和契约稳定后统一 |
| PP-008 | P2 | `desktop.py` 同时承担本地 API、浏览器、Observer 和 Feed 投影 | 维护和回归成本上升 | Post-Pilot 分职责渐进拆分 |
| PP-009 | P2 | `.runtime` 历史库和证据较多 | 运维人员可能连接错库 | 保持 Catalog/ACTIVE 唯一性，阶段结束再归档 |
| PP-010 | P3 | 部分大型 RAG、Frontend、Admin 文件持续增长 | 降低修改定位速度 | 契约稳定后小步拆分，不做大重构 |
| PP-011 | P3 | 代码签名、企业证书、Windows Service、Release Tag 未完成 | 不影响受控 Pilot，但影响商业分发 | 商业发布阶段 |

明确不做：当前不迁 PostgreSQL、不合并 Agent/Host/AI-CS、不为通知重写事件系统、不为窗口识别引入新的桌面自动化框架。
