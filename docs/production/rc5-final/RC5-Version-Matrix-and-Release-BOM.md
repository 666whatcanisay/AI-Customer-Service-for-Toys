# RC5 Version Matrix and Release BOM

## 组件矩阵

| 组件 | 冻结版本/标识 |
|---|---|
| Channel Engine / Host | `0.2.0rc3` |
| ChannelAgent | `2.0.0rc5` |
| Agent Control Protocol | `2.1` |
| Gateway Wire Protocol | `1.0` |
| AI-CS Contracts | `0.14.0` |
| Platform Backend | `1.0.0` |
| Assistant Frontend | `1.0.0` + 生产树/BOM SHA |
| Admin Frontend | `1.0.0` + 生产树/BOM SHA |
| Gateway Contract | `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5` |
| Database Migration Head | `0019_runtime_database_identity_v1` |

## 最终候选包

| 项目 | 值 |
|---|---|
| ZIP | `dist/windows-client-v2/rc5-offline-stability/AI-CS-Channel-Agent-2.0.0rc5-windows-x64.zip` |
| ZIP SHA256 | `f4cdd3162309c268498f4f7f2fa3f10c1ec3437472e4d1ac7e106680c213352e` |
| Manifest SHA256 | `201ddb3794ad76c92791d9f9ea8e6483a89a9568a67da8db38905221a654c7a9` |
| EXE SHA256 | `b88617157130baebffe0a4218f16f4d4ba2ed0085acd2d40f3533e01ff318a9f` |
| Runtime PYZ SHA256 | `1122d023319b470e614bc8e39b63f2aca12aa418dd5769073029a035b48e2ea0` |
| 文件数 | `1161`；bytecode cache `0` |
| 隔离部署验收 | `13/13 PASS` |
| 当前安装实例 | 与候选 Manifest/EXE/PYZ 完全一致 |

## 源码冻结依据

- Engine 实现冻结点：`43d6e9474163eb736713dba6156bc86cc4eef9e9`
- AI-CS 实现冻结点：`ed7c7b804cb5d5d1d55aab202cf4ae8398231028`
- Engine 生产树 SHA：`8b7f4d07e08f047cffe386e9c0cea0e92504e5e8d37cd7d70bc4049fdd757d75`
- AI-CS 生产树 SHA：`59607412baf37317d1b8bbfe0cc7b9198cbf11b907d81b28d44c3dc14b9c6a11`
- 本文档提交只更新报告，不进入候选生产组合。

机器可读值见 [rc5-release-bom.json](rc5-release-bom.json)。
