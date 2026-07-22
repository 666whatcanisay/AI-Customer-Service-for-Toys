# C-T01 平台基线结构

## 冻结范围

C-T01 只建立两个可独立运行的最小入口：

```text
platform_backend/app/main.py:app
  └─ GET /health

admin_web/src/main.ts
  └─ /system-status
       └─ GET /api/platform/health
            └─ Vite proxy → http://127.0.0.1:8000/health
```

后端还包含环境配置、request_id 中间件、统一错误响应和 pytest；管理端还包含 API Client、Router、四态页面和 Vitest。前端生产构建必须从根 `index.html` 启动，因此该文件属于最小 Vite 骨架。

## 目录边界

- 已实现：`platform_backend/**`、`admin_web/**`。
- 已记录：`docs/platform/**`。
- 未修改：`backend/**`、`frontend/**`、`extension/**`、`contracts/**`。
- 未建立：数据库、迁移、商品/SKU、知识治理业务、审核、风险规则、评测、权限、RAG/Chroma Client。

## 依赖隔离

- 后端依赖只安装在 `platform_backend/.venv/`。
- 前端依赖只安装在 `admin_web/node_modules/`。
- `.venv/`、`node_modules/`、`dist/` 均由根 `.gitignore` 排除。
- 前端以 `pnpm-lock.yaml`（lockfile v9）冻结解析结果，并仅批准 `esbuild` 的依赖构建脚本。
