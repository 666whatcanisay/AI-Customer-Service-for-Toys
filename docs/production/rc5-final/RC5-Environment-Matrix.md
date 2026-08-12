# RC5 Environment Matrix

| 环境 | 当前状态 | 版本/约束 | 用途 |
|---|---|---|---|
| 开发环境 | PASS | Windows；Git 2.55；Node 22.23.1；npm 10.9.8；Python 工具环境 3.11.9/仓库构建环境 3.12 | 源码、测试、文档 |
| 构建环境 | PASS | Windows x64；RC5 构建脚本；Agent 2.0.0rc5 | 生成候选 ZIP |
| 测试环境 | PASS | 当前机 + 隔离临时安装根；无真实 PDD | 黑盒、回归、迁移、部署 |
| 当前电脑运行环境 | PASS（验收实例） | Agent 2.0.0rc5；8420/8422/18443 健康；SIMULATOR；real_send=false | 绿色界面与后端联合验收 |
| 未来 Pilot 环境 | NOT IN SCOPE / 待登记 | Windows 版本、机器名、网络、证书、PDD 账号、包 SHA 必须登记 | 真实 PDD 分阶段验证 |

## Pilot 环境准入字段

进入真实 PDD 前必须记录：OS build、CPU/内存、Edge 版本、Host/Agent IP、TLS 证书指纹、候选 ZIP SHA、数据库备份 SHA、店铺 ID（脱敏）、测试账号权限、真实发送 Kill Switch 默认值。

