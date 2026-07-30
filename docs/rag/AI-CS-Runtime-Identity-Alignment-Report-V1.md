# AI-CS Runtime Identity Alignment Report V1

## 1. 结论

AI-CS正式四服务已在不停机、不中断Pilot、未修改业务数据的条件下统一为：

```text
runtimeMode=standard
networkMode=LAN
```

`runtimeMode` 现在只表示发布运行角色；LAN/LOCAL不再冒充发布身份，而由独立 `network_mode` 和每个服务的bind地址记录。

Gate：`RUNTIME_IDENTITY_ALIGNED_READY`

## 2. 根因

R008旧逻辑按全局 `LanMode` 把四服务 `runtime_mode` 写成 `LAN` 或 `LOCAL`。实际正式Pilot通过LAN入口启动，因此记录为 `LAN`；后来用本机标准状态配置检查时，脚本期望 `LOCAL`，即使repository root、Git SHA和source fingerprint全部一致，仍报告runtimeMode不一致。

正确的LAN状态入口在修复前已证明四服务均属于 `AI-CS@dd379278`。问题是“发布角色”和“网络暴露方式”被同一个字段表达，不是服务来源错误。

## 3. 代码与配置身份

- Repository root：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
- 分支：`control/runtime-identity-alignment-v1`
- 原正式业务基线：`dd379278837a4f816dfb626292a26b0c54cce0cc`
- 身份逻辑提交：`38b233410fc75c95a476e8775f7821fb80aab7ff`
- 中文路径保护修复：`2e9e93a6b98950c073badc40f9e84741a3b8fdaa`（Git路径不转义后再执行允许范围判断）
- 业务目录差异：`backend`、`frontend`、`platform_backend`、`admin_web`、`extension`、`contracts` 均为零差异
- 最终运行记录SHA：以本报告所在分支的clean HEAD为准；文档提交后由受控对齐脚本再次重新证明并写入四份记录
- 配置来源：`.runtime/phase-e/config/green-standard.local.ps1`
- 配置状态：Git忽略；新增显式 `RuntimeMode='standard'`
- 运行记录目录：`.runtime/phase-e/green-standard`

## 4. 四服务证据

| 服务 | 端口 | bind地址 | 受管PID | 监听PID | 工作目录 | health |
|---|---:|---|---:|---:|---|---|
| B客服 | 5173 | `192.168.1.11` | 21416 | 21416 | `frontend` | 可用 |
| C Admin | 5174 | `127.0.0.1` | 1040 | 25796 | `admin_web` | 可用 |
| A RAG | 8000 | `127.0.0.1` | 34360 | 22384 | `backend` | 可用 |
| C API | 8011 | `127.0.0.1` | 32568 | 22656 | `platform_backend` | 可用 |

对齐前后四个监听PID及启动时间完全相同，没有停止或重启服务。每份记录的repository root、SHA、source fingerprint、PID、监听PID、可执行路径、启动时间、父子关系、命令特征和端口所有者均在写入前验证。

## 5. 实施内容

1. Windows配置新增显式 `RuntimeMode`，只允许 `standard`、`shadow`、`recovery`。
2. 运行记录新增 `network_mode=LOCAL|LAN`，与发布身份分离。
3. status输出同时显示runtimeMode和networkMode。
4. 新增受控无停机对齐脚本。它只接受clean仓库、前序祖先SHA和仅限 `scripts/windows/**`、`docs/rag/**`、`docs/control/**` 的差异。
5. 对齐前验证四服务真实PID、监听PID、工作目录、端口所有者和HTTP健康；写入前备份全部记录，失败自动恢复。

## 6. 数据与业务保护

- 未修改A、B、C或Admin业务代码。
- 未修改R009代码、RAG/Prompt、contracts或UI。
- 未修改数据库内容或结构。
- 正式SQLite只读检查仍为 `0008_customer_feedback_loop_v1`，`integrity_check=ok`。
- 未执行0009 migration。
- 未停止、重启或替换5173、5174、8000、8011进程。

## 7. 验证

- PowerShell语法检查：通过。
- Runtime identity专项：通过；覆盖错误SHA、错误runtimeMode和network mode不重定义发布身份。
- Windows OPS八组脚本：各自PASS。
- 正式LAN status：四服务均 `RUNNING`、health可用、repository身份已验证、`runtimeMode=standard`、`networkMode=LAN`。
- A：`ready=true`、`model_configured=true`、活动集合 `test_knowledge_v031=47`。

## 8. 日常状态入口

当前B为受控LAN入口，因此日常使用：

```powershell
scripts/windows/status_lan_ai_customer_service.ps1 `
  -ConfigPath .runtime/phase-e/config/green-standard.local.ps1
```

本机标准状态脚本可以验证repository/runtimeMode，但其本地B URL不是当前LAN入口；Pilot整体健康应以LAN状态脚本为准。

## 9. 回滚与记录保护

每次对齐前的四份运行记录保存在Git忽略的：

```text
.runtime/phase-e/green-standard/identity-alignment-backups/<UTC时间>/
```

不得人工编辑PID、SHA或source fingerprint。后续若业务代码发生变化，必须正常受控部署；不得使用身份对齐脚本把旧进程伪装成新业务版本。
