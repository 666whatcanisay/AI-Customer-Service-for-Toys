# RC5 Source → Build → Package → Runtime Consistency Report

## 结论

源码实现冻结点、构建版本、候选包、Manifest 和当前安装实例为 **PASS**。当前 Agent 已通过事务式目录切换升级为本轮候选包；Manifest、EXE、PYZ 均与候选包完全一致，DataRoot 保护项 11/11 PASS。

| 层级 | 标识 | 结果 |
|---|---|---|
| Engine 实现冻结点 | `43d6e9474163eb736713dba6156bc86cc4eef9e9` | PASS |
| AI-CS 实现冻结点 | `ed7c7b804cb5d5d1d55aab202cf4ae8398231028` | PASS |
| 构建版本 | Agent `2.0.0rc5`、Gateway SHA 一致 | PASS |
| 候选安装包 | ZIP SHA `f4cdd316...3352e` | PASS |
| 候选包 Manifest/EXE/PYZ | 声明 SHA 与实际 SHA 一致 | PASS |
| 当前运行实例版本 | Agent `2.0.0rc5`，进程存活 | PASS |
| 当前运行实例二进制 = 候选二进制 | Manifest、EXE、PYZ SHA 完全一致 | PASS |
| 当前运行 UI | 候选包 UI；离线组件回归 214 PASS | PASS |
| Identity/Binding/Profile/Session | 升级前后保护对比 | 11/11 PASS |
| PDD 浏览器 / Real Send | 未启动 / `false` | PASS |

## 冻结身份

1. Pilot 只接受 ZIP SHA `f4cdd3162309c268498f4f7f2fa3f10c1ec3437472e4d1ac7e106680c213352e`。
2. 候选包内文件数为 1161，`__pycache__`/`.pyc` 为 0；删除的是构建缓存，不是运行源码。
3. 安装必须使用包内事务式安装器，不允许手工逐文件覆盖。
4. Pilot 安装后再次采集 EXE、PYZ、Manifest、UI 和 Gateway SHA。
5. 任何生产代码变更都会使本报告与 BOM 失效，必须重建和重验。

机器可读值见 [RC5 Offline Stability Version Matrix](RC5-Offline-Stability-Version-Matrix.json) 和 [Release BOM](rc5-release-bom.json)。
