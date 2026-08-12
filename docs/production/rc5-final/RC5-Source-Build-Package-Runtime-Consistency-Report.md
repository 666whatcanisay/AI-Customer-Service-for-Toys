# RC5 Source → Build → Package → Runtime Consistency Report

## 结论

最终候选包内部的源码版本、构建版本、Manifest 和 Runtime 为 **PASS**。当前电脑运行实例是受保护的热启动验收实例，不是最终候选包的覆盖安装结果；其版本同为 2.0.0rc5，但二进制 SHA 与最终候选不同。这个差异已披露，不影响候选包验收，但 Pilot 必须安装候选 ZIP。

| 层级 | 标识 | 结果 |
|---|---|---|
| 源码 | 两仓 HEAD + 生产树 SHA | PASS / 已冻结 |
| 构建 | Agent `2.0.0rc5`、Gateway SHA 一致 | PASS |
| 候选安装包 | ZIP SHA `50dcc0...9970` | PASS |
| 候选包 Manifest/EXE/PYZ | 声明 SHA 与实际 SHA 一致 | PASS |
| 当前运行实例版本 | Agent `2.0.0rc5` | PASS |
| 当前运行实例二进制 = 候选二进制 | SHA 不同；有意不覆盖受保护实例 | NOT IN SCOPE（非发布源） |
| 当前运行 UI 应用 JS/CSS | 与候选包应用 JS/CSS 哈希一致并完成人工验收 | PASS |
| 当前运行 UI 外壳 HTML | 候选包额外注入品牌 favicon；应用代码不变 | PASS / 预期包装差异 |
| Pilot 运行包 | 尚未安装 | NOT IN SCOPE |

## 强制规则

1. Pilot 只接受 ZIP SHA `50dcc052961777e7d4f4ef02dfe7c78a5acfcc27ebe40339e2301fc63af49970`。
2. 不得复制当前 `%LOCALAPPDATA%\Programs\AI-CS\ChannelAgent` 作为发布包。
3. Pilot 安装后必须再次采集 EXE、PYZ、Manifest、UI 和 Gateway SHA。
4. 任何生产代码变更都会使本报告与 BOM 失效，必须重建和重验。

候选包 `index.html` SHA 为 `67c7dc74...49aa8`，当前热刷新验收实例为 `1a34f572...c6d2`。唯一内容差异是打包阶段向候选包加入 `channel-agent-avatar.png` favicon；两者引用的 JS `2298c0d7...2835` 与 CSS `02cab63d...25b` 完全一致。
