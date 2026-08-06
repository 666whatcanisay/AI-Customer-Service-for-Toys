# AI-CS Production RC V1 Deployment Checklist

Release reference：`ai-cs-production-rc-v1`

Target database head：`0016_production_hardening_v1`

## 1. Preflight

- [ ] `git rev-list -n 1 ai-cs-production-rc-v1`与批准的Release SHA一致。
- [ ] `git status --short`为空；禁止从dirty目录启动。
- [ ] Gateway canonical schema SHA-256为`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。
- [ ] A Python 3.11、C Python 3.12、Node/npm/pnpm与锁文件安装通过；两套前端`dist`从当前SHA重新构建。
- [ ] Windows Management Instrumentation可在有界时间内返回当前进程元数据。
- [ ] LOCAL或LAN模式已明确；LAN具备受信TLS certificate/key和精确Private防火墙规则，不允许公网暴露。
- [ ] 内部服务secret、Gateway secret、TLS key均位于Git ignored Runtime目录，ACL最小化且互不复用。

## 2. Backup and stop

- [ ] 使用受管stop入口停止C/A/B/Admin；确认8000/8011/5173/5174无监听。
- [ ] 记录部署前Git SHA、branch/tag、数据库绝对路径、revision和UTC时间。
- [ ] 创建SQLite可恢复备份并验证hash、`integrity_check=ok`、0 foreign-key violation与关键表行数。
- [ ] 备份、数据库、日志、运行记录和凭据均保持Git ignored；不得复制到源码或报告。

## 3. Migration and build

- [ ] 从0013依次升级0014、0015、0016；每步确认`alembic_version`。
- [ ] 0014确认Conversation Context审计表；0015确认Desktop Workflow审计表；0016确认登录bucket、发布租约字段与唯一默认Store索引。
- [ ] 迁移后再次执行integrity、foreign-key与关键行数检查。
- [ ] B执行锁文件安装/测试/typecheck/build；Admin执行锁文件安装/测试/typecheck/build。

## 4. Start and acceptance

- [ ] 从同一clean Release SHA启动；status中所有受管服务的repository identity一致。
- [ ] A/C health、B/Admin入口正常；生产入口没有Vite dev server。
- [ ] 登录、退出、Session过期/撤销、登录冷却和角色权限隔离通过。
- [ ] 客服默认Store/授权Store切换、Product/SKU解析、AI Reply与人工确认通过；不产生自动发送。
- [ ] RAG/LLM失败返回非2xx Error Envelope；日志只含安全request/user/error type上下文。
- [ ] Gateway启用时，签名Health、Decision、幂等、匿名拒绝和Contract 1.0通过；未启用时保持关闭。
- [ ] 执行受管stop并确认所有端口释放，再按批准模式恢复运行。

## 5. Rollback

- [ ] 触发回滚时立即停止服务并保存失败资产用于受限审计。
- [ ] 恢复部署前数据库备份，或按已演练路径降级到0013；禁止混用0016源码与0013数据库。
- [ ] 同步切回匹配的pre-R020源码引用，核对hash/revision/integrity/foreign keys/行数。
- [ ] 重新启动后验证登录、目录、AI健康、人工确认与端口；RAG向量禁止清空或重建。
- [ ] 记录回滚原因、操作者、时间、旧/新SHA、数据库hash与结果，不记录secret、token或客户内容。
