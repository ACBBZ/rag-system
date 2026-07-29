<p align="center">
  <a href="./README.md">简体中文</a> · <a href="./README.en.md">English</a>
</p>

# RAG System

<p align="center">
  <strong>面向生产的多租户 RAG 平台，支持异步文档摄取、混合检索、可验证引用、RAGAS 评测与完整可观测性。</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-blue">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green">
  <img alt="CI" src="https://github.com/ACBBZ/rag-system/actions/workflows/ci.yml/badge.svg">
</p>

## 项目简介

RAG System 是一个基于 FastAPI、PostgreSQL、MinIO 和 Milvus 构建的多租户检索增强生成平台。项目将文档摄取、版本激活、向量与全文检索、重排、答案生成、引用校验、离线评测和生产运维拆分为清晰模块，同时通过租户级资源路由和知识库 ACL 提供纵深隔离。

本项目适合用作：

- 企业知识库与内部问答服务；
- 多租户 RAG SaaS 后端；
- 可评测、可追踪的 RAG 工程基线；
- 自托管模型端点与私有数据基础设施的集成层。

> 项目提供生产导向的工程能力，但正式部署前仍应根据实际流量、模型、数据敏感度和基础设施完成容量规划、安全审查与评测基线校准。

## 核心能力

### 多租户与权限

- 租户、用户、角色、直接权限和知识库 ACL；
- 带作用域和知识库限制的 API Key；
- 每个租户使用独立 Milvus Collection Alias；
- PostgreSQL 与 Milvus 查询均保留 `tenant_id` 和 `knowledge_base_id` 过滤；
- 平台控制面与租户业务 API 使用不同凭证。

### 异步文档摄取

- PostgreSQL 持久化任务队列；
- `FOR UPDATE SKIP LOCKED` 并发领取任务；
- 独立 `rag-worker` 进程；
- 文档版本、暂存、校验和原子激活；
- 幂等上传、失败重试和 reconciliation 基础；
- 支持 TXT、Markdown、PDF、DOCX、CSV、XLS/XLSX 和常见图片格式；
- PDF 页级结构、扫描件 OCR fallback、表格与标题路径保留；
- 基于 token 的稳定切分、重叠、内容哈希和稳定 context key。

### 检索与生成

- 向量检索、PostgreSQL 全文检索和混合检索；
- 可配置加权 RRF、候选数、分数阈值和单文档结果上限；
- Query Rewrite、Rerank 和答案生成；
- Milvus V2 metadata 前置过滤；
- Token Budget 上下文构建；
- 结构化答案、拒答状态和服务端 Citation ID 校验；
- 每个阶段保留独立分数、耗时和检索方法。

### 评测与可观测性

- Hit Rate、Precision、Recall、MRR、nDCG 等确定性指标；
- Filter Accuracy、租户泄漏、知识库泄漏、重复上下文和拒答准确率；
- RAGAS Faithfulness、Answer Relevancy、Context Precision、Context Recall 和 Factual Correctness；
- Golden、Smoke 和 Adversarial 数据集；
- Baseline 比较和 CI 质量门禁；
- Prometheus 指标、OpenTelemetry spans、Query/ Retrieval 日志；
- `/health/live`、`/health/ready` 和 `/metrics`。

## 架构

```text
Client
  │
  ▼
FastAPI API
  ├── 身份认证 / ACL
  ├── 文档与任务 API
  ├── 检索与生成 API
  └── Health / Metrics
       │
       ├── PostgreSQL
       │    ├── 租户与权限
       │    ├── 文档、版本与 Chunk
       │    ├── 摄取任务队列
       │    ├── 全文检索
       │    └── Query / Retrieval / Audit Logs
       │
       ├── MinIO / S3
       │    ├── 原始文件
       │    └── 解析结果
       │
       ├── Milvus
       │    └── 租户级向量 Collection 与 Alias
       │
       └── 远程模型端点
            ├── Embedding
            ├── Rerank
            ├── Query Rewrite
            ├── LLM
            └── OCR

rag-worker
  └── 解析 → 切分 → Embedding → 索引 → 校验 → 激活
```

## 技术栈

| 层级 | 技术 |
|---|---|
| API | FastAPI、Pydantic v2、Uvicorn |
| 数据库 | PostgreSQL 16、SQLAlchemy Async、Alembic |
| 对象存储 | MinIO / S3-compatible storage |
| 向量数据库 | Milvus |
| 检索 | Milvus ANN、PostgreSQL Full-Text Search、Weighted RRF |
| 模型协议 | OpenAI-compatible / 自定义 HTTP endpoints |
| 评测 | RAGAS、内置确定性指标 |
| 可观测性 | Prometheus、OpenTelemetry |
| 测试与质量 | Pytest、Ruff、Bandit、pip-audit、CycloneDX |

## 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/ACBBZ/rag-system.git
cd rag-system

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Windows PowerShell 激活环境：

```powershell
.venv\Scripts\Activate.ps1
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要配置：

- `POSTGRES_DSN`；
- `MINIO_*`；
- `MILVUS_*`；
- `API_KEY_PEPPER` 和 `PLATFORM_API_KEY`；
- 已启用能力对应的 Embedding、Rerank、Rewrite、LLM 与 OCR 端点。

真实密钥不得提交到 Git 仓库。`API_KEY_PEPPER` 应使用至少 32 字节的随机值，并在密钥管理系统中长期保存。

### 3. 启动基础设施

```bash
docker compose up -d
```

默认会启动 PostgreSQL、MinIO 和 Milvus。MinIO Console 默认位于 `http://localhost:9001`。

### 4. 执行数据库迁移

```bash
alembic upgrade head
```

当前迁移链包含租户权限、向量资源、全文检索、异步摄取、检索 V3 和可观测性数据结构。

### 5. 启动 API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- OpenAPI：`http://localhost:8000/docs`
- Liveness：`http://localhost:8000/health/live`
- Readiness：`http://localhost:8000/health/ready`
- Metrics：`http://localhost:8000/metrics`

### 6. 启动摄取 Worker

在另一个终端运行：

```bash
rag-worker
```

API 只负责接收文件并创建持久化任务；解析、切分、Embedding、索引和版本激活由 Worker 完成。

## 主要 API

所有租户业务 API 使用：

```http
Authorization: Bearer <tenant-api-key>
```

平台控制面使用独立的 `PLATFORM_API_KEY`。

### 平台与租户

```text
POST /v1/platform/tenants
GET  /v1/platform/tenants/{tenant_id}/vector-resource
POST /v1/platform/tenants/{tenant_id}/vector-resource/retry
```

### 用户、API Key 与知识库

```text
POST   /v1/users
PATCH  /v1/users/{user_id}/role
PUT    /v1/users/{user_id}/scope-grants
DELETE /v1/users/{user_id}/scope-grants/{permission}
POST   /v1/api-keys
DELETE /v1/api-keys/{api_key_id}
POST   /v1/knowledge-bases
PUT    /v1/knowledge-bases/{knowledge_base_id}/members/{user_id}
```

### 文档与摄取任务

```text
POST   /v1/documents/embed
PATCH  /v1/documents/{document_id}
DELETE /v1/documents/{document_id}/purge
GET    /v1/ingestion-jobs/{job_id}
POST   /v1/ingestion-jobs/{job_id}/retry
```

上传接口支持 `Idempotency-Key`，成功入队后返回 `202 Accepted`。

### 检索

```text
POST /v1/retrieval/search
```

示例：

```bash
curl -X POST http://localhost:8000/v1/retrieval/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_base_id": "kb_example",
    "query": "员工每年有多少天带薪年假？",
    "options": {
      "retrieval_mode": "hybrid",
      "query_rewrite": true,
      "rerank": true,
      "agent_search": true,
      "top_k": 30,
      "final_k": 6
    },
    "filters": {
      "metadata": {"department": "hr"}
    }
  }'
```

支持的检索模式：

- `vector`：仅 Milvus 向量检索；
- `full_text`：仅 PostgreSQL 全文检索；
- `hybrid`：两路并行检索并使用加权 RRF 融合；
- `auto`：根据请求和环境默认值解析实际模式。

响应包含 `trace_id`、`effective_options`、阶段耗时、Chunk 分数、答案状态和经过验证的引用。

## 评测

安装评测依赖：

```bash
python -m pip install -e '.[eval]'
```

运行确定性评测：

```bash
rag-eval \
  --dataset evals/datasets/golden.jsonl \
  --output evals/reports/results.jsonl \
  --summary evals/reports/summary.json \
  --baseline evals/baselines/main.json
```

启用 RAGAS：

```bash
rag-eval \
  --dataset evals/datasets/golden.jsonl \
  --output evals/reports/results.jsonl \
  --summary evals/reports/summary.json \
  --baseline evals/baselines/main.json \
  --ragas
```

使用前需要将示例数据集中的知识库、参考答案和稳定 context key 替换为实际评测 Fixture。

## 测试与质量检查

```bash
ruff check .
pytest -v
```

迁移回归：

```bash
alembic upgrade head
alembic downgrade 0004_retrieval_v2
alembic upgrade head
```

安全工具：

```bash
python -m pip install -e '.[security]'
bandit -c pyproject.toml -r app rag
pip-audit
```

负载测试：

```bash
python -m pip install -e '.[load]'
locust -f load/locustfile.py
```

## Docker

构建 API 镜像：

```bash
docker build -t rag-system:latest .
```

生产部署中 API 与 `rag-worker` 应独立运行和扩缩容，并共享 PostgreSQL、MinIO、Milvus 和模型端点配置。

## 运维文档

- [生产部署说明](docs/production-v2.md)
- [运行手册](docs/runbook.md)
- [SLO](docs/slo.md)
- [备份与恢复](docs/backup-restore.md)
- [检索 V2 与 RAGAS](docs/retrieval-v2-and-ragas.md)
- [授权 API](docs/authorization-v2-api.md)

## 安全说明

- 不要将生产密钥写入 `.env.example`、日志、Issue 或提交记录；
- 上传文件应在网关和应用层同时限制大小；
- 对外部署时应启用 TLS、限流、审计、Secret Manager 和网络隔离；
- 文档内容按不可信输入处理，生成链路会校验模型返回的 Citation ID；
- 对高敏感数据部署前，应根据组织要求增加恶意文件扫描、数据保留和删除策略。

发现安全问题时，请避免在公开 Issue 中披露敏感细节，并优先通过仓库所有者提供的私密渠道报告。

## 贡献

欢迎提交 Issue 和改进建议。提交代码前请确保：

```bash
ruff check .
pytest -v
```

较大的功能改动应同时提供迁移策略、失败恢复方案、测试以及评测影响说明。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
