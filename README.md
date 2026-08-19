# AI Test Tool

面向 QA、研发与产品人员的需求驱动 API 自动化测试平台 MVP。项目包含 FastAPI 后端和 React + TypeScript 前端，覆盖从需求/OpenAPI 导入、需求映射、Test IR 生成与审核，到执行报告和 pytest 导出的核心闭环。

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
2. 在文档中心上传 Markdown/TXT/DOCX 需求和 OpenAPI 3.0/3.1 JSON/YAML。
3. 执行“分析与映射”，审核原子需求和候选 Operation。
4. 勾选任意需求生成 Test IR 场景，处理静态校验提示后提交审核。
5. 使用模拟模式验证场景结构，或配置真实环境后执行目标 API。
6. 在报告中心查看证据，审核通过后导出 pytest。

### 环境与 Secret

环境只保存 Base URL、Allowlist、认证类型和 Secret 的操作系统环境变量名。例如 Bearer Token 使用 `TEST_API_TOKEN` 作为引用，真实值由启动后端的进程环境提供，不会写入数据库、Test IR 或报告。

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
