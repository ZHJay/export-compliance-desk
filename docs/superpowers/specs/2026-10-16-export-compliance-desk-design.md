# 迷你出口合规查询台 · 设计文档

- 日期：2026-10-16
- 作者：张豪杰
- 状态：待审阅

## 1. 背景与目标

「推衍万物」A7 实习生（全栈方向）的测试题：**迷你出口合规查询台 = 物项检索页 + 规则匹配 API + PDF 报告导出**。A6 岗位要求 TS/React + Python(FastAPI)、Docker、CI/CD、"写得像给人看的" README、可演示作品；面试含 30 分钟代码走读，需讲清每个关键设计决策。

本项目同时用来补齐简历空缺（React、FastAPI），并作为投递邮件中的作品链接。

**成功标准**

1. `docker compose up` 后访问 `http://localhost:8000` 可完整走通：检索物项 → 选目的国/最终用户 → 得到判定 → 导出 PDF。
2. GitHub 仓库 CI 全绿，README 含 GIF/截图、快速开始、设计决策。
3. 每个设计决策能在走读中讲清"为什么这样、代价是什么、何时升级"。

**约束**：3–4 天完成；只做本地运行（不部署公网）。

## 2. 范围

**做**：EAR 简化子集上的四步判定（禁运 / 国家表 / 特殊管制 / 实体清单）、物项检索、三档结论、可复现 PDF 报告、单容器交付、后端测试、CI、README。

**不做**（写进 README「下一步」）：许可证例外（LVS/GBS/ENC 等）、先进计算专项规则（744.23 等）、ECCN 子段落级管制、最终用途管制、登录、查询日志/审计库、规则自动抓取更新、LLM/RAG 辅助归类、公网部署。

> 免责：简化子集，仅供演示，不构成法律意见。

## 3. 架构

```
浏览器 (React SPA)
   │  /api/*  （开发期 Vite 代理；生产同源）
   ▼
FastAPI (main.py) ──► rules.py（纯函数，无 Web 依赖）──► data/*.json（启动时加载到内存）
   └──────────────► report.py（Jinja2 + WeasyPrint → PDF）
```

- 后端无状态、无数据库：导出 PDF 时以同样输入重算。
- 单容器：FastAPI 同时托管前端构建产物。

## 4. 数据模型（`backend/data/`）

数据从抓取当日的 eCFR（15 CFR Parts 738 / 744 / 746 / 774）手工整理，每个文件顶层带 `source_url` 与 `retrieved` 日期。具体管制栏、禁运国名单以抓取当日 eCFR 为准。**下文 JSON 只示意结构，字段值以整理时核对 eCFR 的结果为准。**

### 4.1 `ccl.json` — CCL 子集（约 50–80 条）

覆盖第 3 类（电子/半导体）、第 4 类（计算机）、第 5 类（通信 / 信息安全），含若干仅 AT 管制的 `.9x` 条目（如 5A992），保证演示里能同时出现"需许可证"和"无需许可证"。

```json
{
  "eccn": "5A002",
  "title": "Information security systems, equipment and components",
  "title_zh": "信息安全系统、设备及部件",
  "keywords": ["加密", "encryption", "密码"],
  "controls": ["NS1", "AT1"],
  "special_controls": [{"reason": "EI", "citation": "15 CFR 742.15"}]
}
```

- `controls`：只放国家表栏位（CB1 CB2 CB3 NP1 NP2 NS1 NS2 MT1 RS1 RS2 CC1 CC2 CC3 FC1 AT1 AT2）。
- `special_controls`：在国家表中没有对应栏的管制（如 EI），带条款出处。
- 管制按整个 ECCN 记录，不细分子段落（已知简化）。

### 4.2 `country_chart.json` — 国家表子集（约 30 国）

```json
{
  "CN": {"name_zh": "中国", "x_columns": ["CB1", "CB2", "NP1", "NS1", "NS2", "MT1", "RS1", "RS2", "CC1"], "embargo": null},
  "KP": {"name_zh": "朝鲜", "x_columns": ["..."], "embargo": "15 CFR 746.4"}
}
```

只存打 X 的栏位。目标国家：CN HK TW JP KR SG MY VN TH IN PK AE SA IL TR DE FR GB NL CA AU BR MX RU BY IR KP CU SY（以 eCFR 实际收录为准）。

### 4.3 `entity_list.json` — 实体清单子集（约 30–50 条）

```json
{
  "name": "Huawei Technologies Co., Ltd.",
  "aliases": ["..."],
  "country": "CN",
  "license_requirement": "For all items subject to the EAR",
  "review_policy": "Presumption of denial",
  "fr_citation": "84 FR 22963, 5/21/19"
}
```

### 4.4 `meta.json`

```json
{"version": "2026-10-17", "sources": ["https://www.ecfr.gov/current/title-15/..."]}
```

- `version`：人读的规则集版本（整理日期），数据变更时手动更新。
- 启动时另算 `ruleset_digest` = 三个数据文件内容拼接后的 sha256 前 8 位。报告编号用它，避免"改了数据忘改版本号"导致可复现性失真。

## 5. 匹配逻辑（`backend/app/rules.py`）

`check(eccn: str, country: str, end_user: str | None) -> Result`，纯函数。**每一步都留下一条依据，包括未命中**，使报告构成完整的判定轨迹。

| 步骤 | 条件 | 依据结论 | 引用 |
|---|---|---|---|
| 1 禁运 | 目的国 `embargo` 非空 | LICENSE_REQUIRED | 该国 `embargo` 条款 |
| 2 国家表 | `controls` 中任一栏在目的国 `x_columns` 内 | 每个命中栏一条 LICENSE_REQUIRED | `15 CFR 738 Supp. 1` + ECCN |
| | 无命中（或 EAR99） | 一条 NLR，说明哪些栏未打 X / EAR99 不受国家表管制 | 同上 |
| 3 特殊管制 | 每个 `special_controls` | NEEDS_REVIEW | 该项 `citation` |
| 4 实体清单 | `end_user` 为空 | 跳过，不产生依据 | — |
| | 规范化后与名称/别名完全一致 | LICENSE_REQUIRED（说明清单所列国家、审查政策） | `15 CFR 744.11` / `744 Supp. 4` + `fr_citation` |
| | 最高相似度 ≥ 0.85 | NEEDS_REVIEW（给出最接近的名称与相似度） | 同上 |
| | 其他 | NLR（未在实体清单子集中命中） | `744 Supp. 4` |

- **结论** = 所有依据中最严一级：LICENSE_REQUIRED > NEEDS_REVIEW > NLR。
- **名称规范化**：casefold → 按非字母数字切词 → 丢弃后缀词 {co, company, ltd, limited, inc, incorporated, corp, corporation, llc, plc, gmbh} → 拼接。中文字符按 `str.isalnum` 保留。
- **相似度**：`difflib.SequenceMatcher(None, a, b).ratio()`，对名称与每个别名取最大值。实体匹配不限目的国（实体可在多国有地址）。
  `# ponytail: 0.85 为经验阈值，基于字符序列；误报/漏报需要时换 rapidfuzz token_set_ratio + 人工标注集调参`
- **非法输入**：ECCN 不在子集且不是 `EAR99`、国家不在国家表 → 抛 `ValueError`，API 层转 422。

**Result**

```json
{
  "decision": "LICENSE_REQUIRED | NEEDS_REVIEW | NLR",
  "findings": [{"rule": "embargo | country_chart | special_control | entity_list",
                "decision": "LICENSE_REQUIRED | NEEDS_REVIEW | NLR",
                "message": "中文说明", "citation": "15 CFR ..."}],
  "ruleset_version": "2026-10-17",
  "ruleset_digest": "a1b2c3d4",
  "input": {"eccn": "5A002", "country": "CN", "end_user": "..."}
}
```

**三档结论的理由**：子集规则判断不了时应明确说"不确定"，而不是假装给出答案；合规场景误放行的代价远大于多一次人工复核。

## 6. API（`backend/app/main.py`）

| 接口 | 说明 |
|---|---|
| `GET /api/items?q=` | 内存检索。q casefold 后打分：ECCN 前缀命中 3 分 > `title`/`title_zh` 子串 2 分 > `keywords` 子串 1 分；过滤 0 分，按分数降序、ECCN 升序。q 为空返回全部（按 ECCN）。`# ponytail: 线性扫描，条目上万时换 SQLite FTS5` |
| `GET /api/countries` | `[{code, name_zh, embargoed}]` |
| `POST /api/check` | 请求体 `{eccn, country, end_user?}` → Result |
| `POST /api/report` | 请求体同上 → `application/pdf`，`Content-Disposition: attachment; filename="report-<ECCN>-<CC>-<YYYYMMDD>.pdf"` |

- 请求体用 Pydantic 校验：`eccn` ≤ 20 字符、`country` 恰 2 字符（转大写）、`end_user` ≤ 200 字符且去首尾空白、空串视为未填。
- `ValueError` → 422 `{"detail": "未知 ECCN：XXX"}`。
- 不配 CORS（开发 Vite 代理，生产同源）。`/docs` 为 FastAPI 自带接口文档。

## 7. 前端（`frontend/`）

React + Vite + TypeScript + Tailwind CSS，单页，无路由、无状态库。

- `App.tsx`：持有选中物项、表单、结果状态。
- `ItemSearch.tsx`：输入防抖 300ms 调 `/api/items`；顶部固定 "EAR99（不在 CCL 上）" 项；列表项为 `<button>`，显示 ECCN、中文标题、管制栏标签。
- `CheckForm.tsx`：已选物项（只读）、目的国原生 `<select>`（禁运国标注）、最终用户输入框（可选）、「开始判定」。
- `ResultCard.tsx`：结论徽章（红 需许可证 / 黄 需人工复核 / 绿 无需许可证，颜色之外有文字）、依据列表（说明 + 条款）、规则版本、「导出 PDF」（POST → blob → 触发下载）。
- `api.ts`：类型化 fetch 封装；422 时展示 `detail`（业务错误为字符串，Pydantic 校验错误为数组，取首条 `msg`）。`types.ts`：手写，对应 Pydantic 模型。
- 每个请求有加载中 / 出错 / 无结果状态；输入框都有 `<label>`。
- 页脚免责声明。

## 8. PDF 报告（`backend/app/report.py`）

`render_report(result) -> bytes`：Jinja2 渲染 `templates/report.html`，WeasyPrint 输出 PDF。

内容：标题「出口合规初筛报告」、报告编号、生成时间（Asia/Shanghai）、规则集版本 + digest + 抓取日期、查询输入、结论（大字）、依据表（规则 / 结论 / 说明 / 条款出处）、免责声明、页脚页码（CSS `@page`）。

**报告编号** = `sha256(json.dumps(input, sort_keys=True, ensure_ascii=False) + ruleset_digest)` 前 12 位（hex）。同输入 + 同规则 → 同编号；不含生成时间。

选 WeasyPrint 而非 ReportLab：HTML/CSS 排版远比坐标绘制好维护；代价是镜像需装 pango 与 `fonts-noto-cjk`，macOS 本地开发需 `brew install pango`。

## 9. 交付

- `Dockerfile` 多阶段：`node:22-alpine` 构建前端 → `python:3.12-slim` 装 `libpango-1.0-0 libpangoft2-1.0-0 fonts-noto-cjk` 与 `requirements.txt`，复制前端 `dist/` 到 `static/`，FastAPI `StaticFiles(html=True)` 挂在 `/`（在 `/api` 路由之后），非 root 用户运行 uvicorn。
- `docker-compose.yml`：单服务，`8000:8000`。
- 依赖：`requirements.txt`（fastapi、uvicorn、jinja2、weasyprint，固定版本）；`requirements-dev.txt`（`-r requirements.txt`、pytest、httpx、ruff）。

## 10. 测试

- `tests/test_rules.py`（`pytest.mark.parametrize` 用例表）：禁运国；国家表命中；国家表未命中；EAR99 到非禁运国；special_controls → NEEDS_REVIEW；实体名称写法不同的完全匹配（`Huawei Technologies Co., Ltd.` vs `HUAWEI TECHNOLOGIES CO LTD`）；模糊命中；end_user 为空跳过；多依据取最严；非法 ECCN / 国家抛错。
- 数据完整性：所有 `controls` ⊆ 国家表栏位集合；所有 `x_columns` ⊆ 同一集合；ECCN 无重复；每条 special_control 都有 citation。
- `tests/test_api.py`（TestClient）：检索排序（ECCN 前缀优先）；check 200 与 422；report 返回 `application/pdf` 且内容以 `%PDF` 开头；同输入两次报告编号一致。
- 前端：不写单元测试（逻辑在后端），CI 做 lint + 类型检查 + 构建，README 截图为人工验收。

## 11. CI（`.github/workflows/ci.yml`）

push / pull_request 触发，三个并行 job：

1. backend：Python 3.12，apt 装 pango，`ruff check` + `pytest`。
2. frontend：Node 22，`npm ci` + `npm run lint` + `npm run build`（含 `tsc -b`）。
3. docker：`docker build .`。

## 12. README 结构

一句话介绍 + GIF → 快速开始（`docker compose up`）→ 判定逻辑图解（四步 + 三档）→ 数据来源与版本 → 设计决策（数据文件 + 纯函数、三档结论、后端生成 PDF 与报告编号、无数据库、单容器、不配 CORS）→ 已知简化与下一步 → 本地开发（后端 uvicorn、前端 Vite、macOS 装 pango）→ 免责声明。

## 13. 仓库结构

```
export-compliance-desk/
├─ backend/
│  ├─ app/        main.py · rules.py · report.py · templates/report.html
│  ├─ data/       ccl.json · country_chart.json · entity_list.json · meta.json
│  ├─ tests/      test_rules.py · test_api.py
│  └─ requirements.txt · requirements-dev.txt
├─ frontend/
├─ Dockerfile · docker-compose.yml · .github/workflows/ci.yml
├─ docs/superpowers/specs/2026-10-16-export-compliance-desk-design.md
└─ README.md
```

## 14. 里程碑（3–4 天）

1. Day 1：整理数据子集 + `rules.py` + `test_rules.py`。
2. Day 2：API + PDF 报告 + `test_api.py`。
3. Day 3：前端三组件联调。
4. Day 4：Docker、CI、README、GIF。

## 15. 风险

- **数据准确性**：手工整理易出错 → 数据完整性测试 + 每文件注明来源与抓取日期 + 免责声明。Syria 等国的管制近年有调整，以抓取当日 eCFR 为准。
- **WeasyPrint 系统依赖**：macOS 本地需 pango；CI/镜像已显式安装。
- **镜像体积**：`fonts-noto-cjk` 较大，可接受；需要时改为只打包子集字体。
