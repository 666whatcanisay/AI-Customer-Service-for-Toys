# RC5 Windows Deployment Report

## 结论

最终候选包在隔离目录完成 **13/13 PASS**，并已对当前 Agent 执行事务式受控覆盖升级。安装实例与候选包 SHA 一致，升级前后保护状态 11/11 PASS。

| 检查 | 结果 |
|---|---|
| 版本矩阵与文件完整性 | PASS |
| ZIP SHA | PASS |
| 全新安装 | PASS |
| 临时开机启动 | PASS |
| 升级保留 Identity/Binding/Profile/Session | PASS |
| Manifest 与 Runtime 版本一致 | PASS |
| 无效升级在修改前失败 | PASS |
| 新包完整暂存、目录级切换和失败回滚 | PASS |
| 当前实例升级后 Manifest/EXE/PYZ = 候选包 | PASS |
| 卸载保留数据并关闭自启动 | PASS |
| 重装保留数据 | PASS |
| 明确选择时删除测试数据 | PASS |

候选 ZIP SHA：`f4cdd3162309c268498f4f7f2fa3f10c1ec3437472e4d1ac7e106680c213352e`。

部署验收是在独立 `.runtime` 目录内完成；随后仅按已通过流程将同一候选包安装到当前 Agent。当前实例变更严格限于安装目录事务切换与 `install-state`/ACL 刷新，业务 DataRoot、Identity、Binding、Profile 和 PDD Session 未变化。

## 当前范围边界

代码签名、企业证书、Windows Service、正式安装器外观和 Release Tag 属于商业发布阶段，均为 **NOT IN SCOPE**，不阻塞 RC5 离线收口。

证据：`.runtime/wd-final/windows-deployment-report.json`、`.runtime/rc5-offline-stability/pre-final-transactional-upgrade.json`、`.runtime/rc5-offline-stability/post-final-transactional-upgrade.json`。
