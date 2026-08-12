# RC5 Installation, Upgrade and Rollback Guide

## 安装前

1. 核对候选 ZIP SHA256 为 `50dcc052961777e7d4f4ef02dfe7c78a5acfcc27ebe40339e2301fc63af49970`。
2. 备份 Agent 数据目录和平台数据库，分别记录 SHA256。
3. 记录 Identity 状态、Binding revision、Profile identity hash、PDD Session 文件数和当前进程 PID。
4. 确认 `real_send=false`、PDD 浏览器读取关闭、Kill Switch 可用。

## 全新安装/升级

- 使用包内正式 Windows 安装/升级脚本，不手工覆盖 PYZ、Manifest 或 secrets。
- 升级后核对 EXE、PYZ、Manifest、Gateway Contract 和 UI 文件 SHA。
- 核对 Identity、Binding、Profile、Session 均与升级前一致。
- 先启动 AI-CS、Platform、Host，再启动 Agent；健康检查全部通过后才打开助手界面。

## 回滚

1. 保留失败现场日志，不删除数据目录。
2. 停止新版本进程，恢复上一稳定安装目录。
3. 仅在 Migration 明确支持且已有备份时执行数据库 downgrade；通常优先恢复数据库备份。
4. 重新核对身份、绑定、Profile 和 Session。
5. 保持真实发送关闭，执行 Synthetic 冒烟后再恢复业务。

## 禁止事项

- 禁止清空 `%LOCALAPPDATA%\AI-CS\ChannelAgent` 来“解决”升级问题。
- 禁止把当前验收安装目录复制到 Pilot。
- 禁止在未完成 REAL_PDD_CONFIRM_READY 前开启真实发送。

