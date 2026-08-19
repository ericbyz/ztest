# AI Test Tool

面向 QA、研发与产品人员的需求驱动 API 自动化测试平台 MVP。项目包含 FastAPI 后端和 React + TypeScript 前端，覆盖多来源需求接入、API 资产归一化、私有知识库、需求映射、Test IR 生成与审核、执行报告和 pytest 导出的核心闭环。

## 本地启动

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。系统默认从空白工作区启动，不会创建演示项目、虚构接口或固定指标。

## 使用流程

1. 创建一个隔离项目。
2. 在接入中心选择需求来源：本地文件、TAPD、外部知识库或项目组件知识库。
3. 导入 OpenAPI 3.x、Swagger 2.0、Postman Collection 2.x、HAR 1.2，或使用公开 HTTPS URL。
4. 执行“分析与映射”，审核原子需求和候选 Operation。
5. 勾选任意需求生成 Test IR 场景，处理静态校验提示后提交审核。
6. 使用模拟模式验证场景结构，或配置真实环境后执行目标 API。
7. 在报告中心查看证据，审核通过后导出 pytest。

### 多来源与知识库

- 需求文件支持 Markdown、TXT、DOCX、JSON 和 YAML。
- TAPD 优先连接已经运行在本机回环地址上的 Streamable HTTP MCP Server。接入中心会自动执行 MCP 握手、发现只读工具、读取 TAPD 项目列表，并让用户选择一个项目后再建立绑定。
- TAPD Token 由本地 MCP Server 自己的环境变量或私有配置管理，本工具只保存 MCP 回环地址、所选项目 ID 和工具名，不读取也不保存 TAPD Token。
- 外部知识库使用可配置的公开 HTTPS 查询地址；Bearer、API Key Header 与 Basic 凭据均为只写 Secret。
- 每个项目可以创建多个组件文件知识库，上传的原文件保存在 `backend/.local/knowledge/`，解析文本保存在本地 SQLite。
- 知识库内容可按需“解析为需求”，来源使用 `knowledge://` URI 保持追溯。

### TAPD 本地 MCP

MCP Server 需要暴露 Streamable HTTP 地址，例如 `http://127.0.0.1:3333/mcp`。系统只允许 `localhost`、`127.0.0.1` 和 `::1`，不会通过 MCP 通道访问远端或局域网地址。

自动发现会读取常见 MCP 配置中的 URL（不会返回其中的命令、参数或环境变量），并探测少量常用本机端口。也可以通过环境变量补充地址：

```powershell
$env:AI_TEST_MCP_DISCOVERY_URLS="http://127.0.0.1:3333/mcp,http://127.0.0.1:9000/mcp"
```

工具名无需固定。系统会根据 MCP 工具的描述和 `inputSchema` 识别“项目列表”和“需求/Story 查询”工具，并要求需求工具明确声明项目参数，避免未限定项目的批量同步。若只检测到 stdio MCP 配置，界面会提示先用本地网关或 Server 自身配置暴露 Streamable HTTP 地址；系统不会静默执行本机配置中的任意命令。

### AI / LLM 配置

在“系统设置”中配置 Provider、模型、Base URL 和 API Key。支持 OpenAI、Azure OpenAI、Anthropic 以及 OpenAI 兼容服务。API Key 不写入业务数据库，接口也不会返回原文，只会返回是否已配置和末四位掩码。

### 环境与 Secret

环境只保存 Base URL、Allowlist、认证类型和 Secret 的操作系统环境变量名。例如 Bearer Token 使用 `TEST_API_TOKEN` 作为引用，真实值由启动后端的进程环境提供，不会写入数据库、Test IR 或报告。

LLM Key、外部知识库凭据和知识库原文件保存在 `backend/.local/`；TAPD Token 保存在 MCP Server 自己的私有环境中。`backend/.local/`、`.env`、SQLite、虚拟环境和前端构建产物均已加入 `.gitignore`。Docker Compose 会把数据库和本地敏感数据统一挂载到命名卷 `/data`。可通过 `AI_TEST_LOCAL_DATA_PATH` 将本地敏感目录迁移到其他路径。

## 测试

```powershell
cd backend
.venv\Scripts\pytest

cd ..\frontend
npm run lint
npm run build
```

## 目录

- `backend/app/api.py`：REST API
- `backend/app/models.py`：持久化领域模型
- `backend/app/services.py`：通用解析、映射、IR 校验、执行与导出
- `frontend/src`：React 管理台
- `docs`：产品需求和总体架构
