# RC5 Version Matrix and Release BOM

> 2026-08-12 新冻结事实见 [RC5 Offline Stability Version Matrix](RC5-Offline-Stability-Version-Matrix.json)。当前已安装 Agent 已受控升级为新候选包，Manifest/EXE/PYZ SHA 一致且 DataRoot 保护项 9/9 PASS；禁止把旧正文的历史 SHA 当作本轮候选包 SHA。

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
| Database Migration Head | `0018_store_platform_bindings_v1` |

## 最终候选包

| 项目 | 值 |
|---|---|
| ZIP | `dist/windows-client-v2/rc5-final-ready/AI-CS-Channel-Agent-2.0.0rc5-windows-x64.zip` |
| ZIP SHA256 | `50dcc052961777e7d4f4ef02dfe7c78a5acfcc27ebe40339e2301fc63af49970` |
| Manifest SHA256 | `b8675fe59d845cea23d666219bc09881f9cb70e27bb04549cabe95d03a816598` |
| EXE SHA256 | `a3b8d3e1acb8f1f05128ba806a1e42464ad1d1ad632aa489dc9f2ec144fe70ae` |
| Runtime PYZ SHA256 | `675cdf1ec6bda0fd531a10a8b9bb80dc1beafe944a0a2f68f67d44ea8c7fb407` |
| 文件数 | `1721` |
| 隔离部署验收 | `13/13 PASS` |

## 源码冻结依据

两个工作树包含此前窗口和本轮尚未提交的有效开发内容，因此 Git HEAD 不能单独代表 RC5。RC5 以以下组合冻结：

- Engine HEAD：`eeafe0590538c79fb390d8468aea8823ecdd699f`
- AI-CS HEAD：`5f79b51eb3b387c45c9d858f91e8b21dfb724af3`
- Engine 生产树 SHA：`da4f9e010f4a92ee446c42bb9eff25aca190896b5f559e8285fa38e98beedc3d`
- AI-CS 生产树 SHA：`de58dd0b743672966a056f105da7e39a0cf6ed0f5cb8a72a0f946422fdb983f8`
- 最终候选 ZIP SHA 和 Gateway Contract SHA。

机器可读值见 [rc5-release-bom.json](rc5-release-bom.json)。
