# BUG-OPS-005 — 中文 BAT 使用 LF 导致 cmd.exe 吞掉行首字符

- 等级：P1
- 模块：OPS / Windows batch entry
- 状态：FIXED_VERIFIED
- 发现时间：2026-08-01

## 现象

中文 BAT 静态内容完整，但由 `cmd.exe` 实际执行时出现 `owershell.exe is not recognized` 等错误；PowerShell 没有被调用。

## 原因

仓库根 `.gitattributes` 对文本统一指定 `eol=lf`。Windows `cmd.exe` 读取 LF-only BAT 时会错误切分命令行并吞掉部分行首字符。

## 修复

在 `scripts/windows/.gitattributes` 增加 `*.bat text eol=crlf`，只覆盖 Windows BAT，不改变其他代码文件。正式项目与旧兼容目录均采用相同规则。

## 验证

- 全部 BAT 工作区内容为 CRLF、UTF-8 无 BOM。
- 旧目录中文“检查AI客服状态”BAT 经真实 `cmd.exe` 执行退出 0，并跳转到正式 SHA。
- 正式中文状态 BAT 经真实 `cmd.exe` 执行必须退出 0；测试输入使用 EOF 跳过人工 `pause`，未改 BAT 日常交互。
