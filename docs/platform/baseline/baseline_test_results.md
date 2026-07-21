# C-T01 实际测试结果

测试日期：2026-07-21。

## 后端

环境：Python 3.12.13，独立虚拟环境 `platform_backend/.venv`。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

结果：依赖安装成功；最终 Gate 重跑为 pytest `3 passed, 1 warning in 0.23s`。警告为 FastAPI TestClient 对当前 HTTPX 适配的弃用提示，不影响本轮断言结果，但列为技术债。

首次尝试端口 8000 时出现 Windows `10048`（端口已被其他进程占用）。未终止未知进程，改用 8010 完成同一应用的真实启动检查：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
Invoke-WebRequest http://127.0.0.1:8010/health -Headers @{ 'X-Request-ID'='c-g1-fix1-health-check' }
```

实际结果：HTTP 200，响应头 `X-Request-ID: c-g1-fix1-health-check`，响应体：

```json
{"status":"ok","service":"platform-backend","version":"0.1.0","request_id":"c-g1-fix1-health-check"}
```

验证完成后已停止本轮启动的服务进程。

## 管理端

环境：Node.js 22.23.1，pnpm 11.9.0，`pnpm-lock.yaml` lockfile v9。

pnpm 11 要求显式批准依赖构建脚本；`pnpm-workspace.yaml` 仅允许 `esbuild: true`。使用 Node 22 完成安装，`esbuild@0.25.12` postinstall 成功。

```powershell
pnpm typecheck
pnpm test
pnpm build
```

结果：

- typecheck：通过，无 TypeScript 错误。
- Vitest：1 个测试文件、3 个测试全部通过。
- build：Vite 6.4.3 成功，82 modules transformed；输出 `dist/` 已被 Git 忽略。

## 结果判定

后端可独立测试和启动，前端可类型检查、测试和生产构建。端口 8000 的本机占用是运行环境限制，不是代码失败；默认开发代理仍以 8000 为文档化端口。
