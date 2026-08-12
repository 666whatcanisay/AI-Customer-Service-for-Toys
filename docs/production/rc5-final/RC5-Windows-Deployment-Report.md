# RC5 Windows Deployment Report

## 结论

最终候选包在隔离目录完成 **13/13 PASS**，当前已安装 Agent 未发生任何安装级变更。

| 检查 | 结果 |
|---|---|
| 版本矩阵与文件完整性 | PASS |
| ZIP SHA | PASS |
| 全新安装 | PASS |
| 临时开机启动 | PASS |
| 升级保留 Identity/Binding/Profile/Session | PASS |
| Manifest 与 Runtime 版本一致 | PASS |
| 无效升级在修改前失败 | PASS |
| 卸载保留数据并关闭自启动 | PASS |
| 重装保留数据 | PASS |
| 明确选择时删除测试数据 | PASS |

候选 ZIP SHA：`50dcc052961777e7d4f4ef02dfe7c78a5acfcc27ebe40339e2301fc63af49970`。

## 当前范围边界

代码签名、企业证书、Windows Service、正式安装器外观和 Release Tag 属于商业发布阶段，均为 **NOT IN SCOPE**，不阻塞 RC5 离线收口。

证据：`.runtime/rc5-final/windows-deployment-final/windows-deployment-report.json`。

