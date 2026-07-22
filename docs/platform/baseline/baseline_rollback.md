# C-T01 回滚方案

## 提交前

只撤销本轮 `platform_backend/**`、`admin_web/**`、`docs/platform/**` 的变更；不得使用覆盖整个工作树的 reset，也不得触碰其他线路。

## 提交后

优先使用可审计的反向提交：

```powershell
git revert <C-T01-metadata-commit>
git revert <C-T01-main-commit>
```

若只需停用运行态：停止本轮启动的 Uvicorn/Vite 进程即可。`.venv/`、`node_modules/` 和 `dist/` 都是可重建且未跟踪的本地依赖/构建产物；删除前必须精确确认目录位于各自项目下。

## 数据影响

本轮未创建数据库、迁移、业务数据、知识文件或远端 RAG 状态，因此回滚不涉及数据迁移或索引恢复。
