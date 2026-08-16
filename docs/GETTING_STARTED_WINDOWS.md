# Windows 开发环境指南

## 1. 安装软件

1. 安装 Git。
2. 安装 Python 3.12 x64，并勾选 Python Launcher。
3. 安装 Node.js 22 LTS。
4. 打开 PowerShell，执行：`npm install -g pnpm@11`。
5. 安装 Ollama，执行：`ollama pull qwen3.5:9b`。

## 2. 下载项目

```powershell
git clone https://github.com/666whatcanisay/AI-Customer-Service-for-Toys.git
cd AI-Customer-Service-for-Toys
```

项目目录可以改名，也可以放在含空格或中文的路径中。

## 3. 首次安装

双击 `首次安装.cmd`，或执行：

```powershell
.\scripts\windows\Bootstrap-PortableProject.ps1
```

成功标志：`BOOTSTRAP_PORTABLE_PROJECT=PASS`。

脚本会创建：

- `backend/.venv`
- `platform_backend/.venv`
- `AI-CS-Channel-Execution-Engine/.venv`
- `frontend/node_modules`
- `admin_web/node_modules`
- 三个前端构建目录
- `.runtime/portable/platform.sqlite3`
- `.runtime/portable/secrets/*`
- `.runtime/phase-e/config/green-standard.local.ps1`

以上均被 Git 忽略。

## 4. 启动 AI-CS

双击 `启动AI客服.cmd`。浏览器会打开客服工作台；Admin 地址为 `http://127.0.0.1:8423/`。

状态检查：

```powershell
.\scripts\windows\status_ai_customer_service.ps1 `
  -ConfigPath .\.runtime\phase-e\config\green-standard.local.ps1
```

停止：双击 `停止全部服务.cmd`。

## 5. 启动 AI-CS + AI-CE + PDD

只有在新电脑已经安装 Channel Agent、登录专属 PDD Edge、完成 Store 双 ID 绑定及本机凭据配置后，才双击：

```text
启动完整客服含PDD.cmd
```

默认只处理 PDD 当前打开会话，不会自动跳转左侧会话列表。真实发送状态以客服助手顶部开关和运行详情为准。

## 6. 常见问题

### Doctor 提示 Python 3.12 缺失

重新安装 Python 3.12 x64，并勾选 `py launcher`，随后重开终端。

### Ollama 或模型不可用

```powershell
ollama serve
ollama pull qwen3.5:9b
```

### 端口被占用

先执行 `停止全部服务.cmd`。不要按端口强杀未知进程；运行状态脚本核对受管 PID。

### Git 工作区不干净导致正式启动拒绝

```powershell
git status --short
```

提交或保存自己的修改后再启动。不要使用 `git reset --hard` 清除不明改动。

### 新电脑没有旧商品、知识或客户数据

这是正确行为。生产数据库、知识源和客户数据不上传 GitHub。请使用 Admin 的正式导入/审核/发布流程，或从受控备份恢复后重新绑定数据库身份。

## 7. 更新代码

```powershell
git pull --ff-only
.\scripts\windows\Bootstrap-PortableProject.ps1
```

依赖或前端变化后重新执行首次安装脚本即可；已有本地数据库与密钥不会被覆盖。
