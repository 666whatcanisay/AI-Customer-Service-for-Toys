# BUG-RUNTIME-003 — T04过期PID测试夹具被NativeCommandError中断

- 等级：P2
- 模块：Windows OPS自动测试
- 状态：FIXED_VERIFIED_PRODUCTION
- 发现时间：2026-07-31

## 问题描述

全套`scripts/windows/tests/Test-*.ps1`回归运行到`Test-OpsT04Fix1.ps1`第59行时，测试通过`powershell.exe`执行状态脚本以验证过期PID应显示“未运行”。子进程的预期错误流被父PowerShell在`$ErrorActionPreference='Stop'`下提升为`NativeCommandError`，测试夹具在自身断言前中断。

## 影响判断

这是测试驱动对预期错误流的兼容问题，不是正式Runtime故障：

- 本任务直接相关的`Test-OpsRuntimeFix2.ps1`通过；
- PowerShell脚本语法检查通过；
- 隔离四服务启动、status和安全停止通过；
- 正式四服务status返回exit 0，b7783f7/0010保持RUNNING。

## 后续处理

在独立OPS测试治理任务中，使“过期PID”和“缺少runtime目录”两个预期降级场景以不会被父Shell提前提升的方式捕获stdout/stderr和exit code。不得为让测试变绿而削弱状态脚本的错误输出、PID身份校验或安全停止规则。

## 修复与验证

- 新增夹具级`Invoke-StatusFixture`，仅在捕获子PowerShell预期错误流时临时使用`ErrorActionPreference=Continue`，断言后恢复父Shell设置。
- 过期PID夹具补齐当前Runtime身份记录要求的`repository_root`和`network_mode`；未修改正式状态脚本的身份校验。
- “仅C”夹具改为5秒上限的端口就绪轮询，消除固定300ms造成的偶发误报。
- `Test-OpsT04Fix1.ps1`已通过：无服务、仅C、过期PID、`$PID`冲突、缺少`.runtime`、缺少A venv和脚本语法均完成验证。
- R006.1正式发布后再次执行`Test-OpsT04Fix1.ps1`、`Test-OpsLanMode.ps1`和`Test-OpsRuntimeFix2.ps1`，全部通过；四服务保持RUNNING。
