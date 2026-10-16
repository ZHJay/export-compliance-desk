# 迷你出口合规查询台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 本地 `docker compose up` 即可使用的出口合规查询台：物项检索 → 四步规则判定 → 可复现 PDF 报告。

**Architecture:** 规则数据为 `backend/data/*.json`（eCFR 手工子集），启动时载入内存；`rules.py` 是只依赖标准库的纯函数（载入、检索、判定）；FastAPI 暴露 4 个接口并托管 React 构建产物；`report.py` 用 Jinja2 + WeasyPrint 出 PDF。无数据库、无 CORS、单容器。

**Tech Stack:** Python 3.12 · FastAPI · Pydantic v2 · Jinja2 · WeasyPrint · pytest · ruff ｜ Node 22 · React · Vite · TypeScript · Tailwind CSS v4 ｜ Docker · GitHub Actions

**Spec:** `docs/superpowers/specs/2026-10-16-export-compliance-desk-design.md`

## Global Constraints

- `rules.py` 只用标准库（dataclasses、difflib、hashlib、json、pathlib、re）；不 import fastapi/pydantic。
- 三档结论字面量：`LICENSE_REQUIRED` / `NEEDS_REVIEW` / `NLR`；中文标签：需许可证 / 需人工复核 / 无需许可证；严重度 LICENSE_REQUIRED > NEEDS_REVIEW > NLR。
- 国家表栏位全集：`CB1 CB2 CB3 NP1 NP2 NS1 NS2 MT1 RS1 RS2 CC1 CC2 CC3 FC1 AT1 AT2`。
- 名称后缀词：`{co, company, ltd, limited, inc, incorporated, corp, corporation, llc, plc, gmbh}`；模糊阈值 `0.85`。
- `ruleset_digest` = sha256(ccl.json + country_chart.json + entity_list.json 的原始字节，按此顺序拼接) hex 前 8 位；报告编号 = sha256(`json.dumps(asdict(input), sort_keys=True, ensure_ascii=False)` + digest) hex 前 12 位。
- 报告标题「出口合规初筛报告」；时区 `Asia/Shanghai`；免责声明原文：`简化子集，仅供演示，不构成法律意见。`
- 请求限制：`eccn` 1–20 字符，`country` 恰 2 字符，`end_user` ≤ 200 字符；ECCN/国家去空白并转大写。
- 端口 8000；不配 CORS；Python 依赖固定版本。
- 本机：Python 3.13（用 `uv venv -p 3.12` 建 3.12 虚拟环境）、Node 22、Docker、Homebrew pango 已装。
- **对 spec 的一处细化**：判定函数签名为 `check(rs: Ruleset, eccn, country, end_user)`（显式传入规则集，便于用小夹具测试），其余与 spec 一致。

## Review Focus

1. **小写/带空格的输入**（`"5a002 "`、`" cn"`、`"ear99"`）→ 用户预期照常判定，`input` 回显规范化后的值。→ Task 2 `test_input_is_normalized`、Task 3 `test_check_lowercase_input`。
2. **中文最终用户名**（`"华为"`）→ 实体清单只有英文名，不能让"未命中"给人安全的错觉；未命中说明须写明"仅比对英文名称及别名"。→ Task 2 `test_chinese_end_user_warns_english_only`。
3. **规范化后为空的最终用户**（`"Co., Ltd."`、`"!!!"`）→ 不能静默判"未命中"，应为需人工复核。→ Task 2 `test_end_user_without_valid_chars_needs_review`。
4. **检索框里的空白或特殊字符**（`"  "`、`"%("`）→ 空白等同于空查询返回全部；特殊字符按字面子串处理，不报错。→ Task 2 `test_search_blank_and_special_chars`。
5. **最终用户含 HTML**（`"<b>x</b>"`）→ 报告里原样显示文字，不被当作标记渲染，PDF 照常生成。→ Task 4 `test_html_escapes_end_user`。

---

## File Structure

```
export-compliance-desk/
├─ .gitignore
├─ backend/
│  ├─ pyproject.toml            # 仅 pytest/ruff 配置
│  ├─ requirements.txt          # fastapi uvicorn[standard] jinja2 weasyprint（固定版本）
│  ├─ requirements-dev.txt      # -r requirements.txt + pytest httpx ruff
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ rules.py               # 数据类型、载入、检索、判定（纯函数）
│  │  ├─ main.py                # FastAPI 路由、请求校验、静态托管
│  │  ├─ report.py              # 报告编号、HTML 渲染、PDF 生成
│  │  └─ templates/report.html
│  ├─ data/  ccl.json country_chart.json entity_list.json meta.json
│  └─ tests/ test_data.py test_rules.py test_api.py test_report.py
├─ frontend/                    # Vite react-ts 模板
│  └─ src/ App.tsx types.ts api.ts components/{ItemSearch,CheckForm,ResultCard}.tsx
├─ Dockerfile · docker-compose.yml · .github/workflows/ci.yml
└─ README.md · docs/screenshot.png · docs/demo.gif
```

以下命令中 `backend$` 表示在 `backend/` 目录下执行，并已 `source .venv/bin/activate`。

---

### Task 1: 后端骨架 + 规则数据 + 载入与完整性测试

**Files:**
- Create: `.gitignore`, `backend/pyproject.toml`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/app/__init__.py`, `backend/app/rules.py`
- Create: `backend/data/ccl.json`, `backend/data/country_chart.json`, `backend/data/entity_list.json`, `backend/data/meta.json`
- Test: `backend/tests/test_data.py`

**Interfaces:**
- Produces（`app/rules.py`）：
  ```python
  CHART_COLUMNS: frozenset[str]          # Global Constraints 中的 16 个栏位
  Decision = Literal["LICENSE_REQUIRED", "NEEDS_REVIEW", "NLR"]

  @dataclass(frozen=True)
  class Ruleset:
      items: dict[str, dict]       # eccn -> {eccn, title, title_zh, keywords, controls, special_controls}
      countries: dict[str, dict]   # code -> {name_zh, x_columns, embargo}
      entities: list[dict]         # {name, aliases, country, license_requirement, review_policy, fr_citation}
      version: str                 # meta.json version
      sources: list[str]           # meta.json sources
      digest: str                  # 8 位 hex

  def load_ruleset(data_dir: Path) -> Ruleset
  ```
- JSON 顶层格式：`ccl.json` = `{"source_url", "retrieved", "items": [...]}`；`country_chart.json` = `{"source_url", "retrieved", "countries": {"CN": {...}}}`；`entity_list.json` = `{"source_url", "retrieved", "entities": [...]}`；`meta.json` = `{"version", "sources"}`。字段见 spec §4。

- [ ] **Step 1: 建骨架与虚拟环境**

`.gitignore` 含 `node_modules/ dist/ __pycache__/ .venv/ backend/static/ .pytest_cache/ .ruff_cache/`。`pyproject.toml`：`[tool.pytest.ini_options] pythonpath = ["."]`、`[tool.ruff] target-version = "py312"`。requirements 先 `pip install` 最新版再 `pip freeze` 出固定版本。

Run: `cd backend && uv venv -p 3.12 .venv && source .venv/bin/activate && uv pip install -r requirements-dev.txt`
Expected: 安装成功，`python --version` 为 3.12.x

- [ ] **Step 2: 写失败的完整性测试 `tests/test_data.py`**

```python
DATA = Path(__file__).parent.parent / "data"
REQUIRED_ECCNS = {"3A001", "4A003", "5A002", "5A992"}
REQUIRED_COUNTRIES = {"CN", "JP", "DE", "RU", "IR", "KP", "CU"}

def test_loads_and_digest():         # rs.digest 为 8 位小写 hex；rs.version 非空；rs.sources 非空
def test_required_coverage():        # REQUIRED_ECCNS ⊆ rs.items；REQUIRED_COUNTRIES ⊆ rs.countries；
                                     # 至少一个实体 name 含 "Huawei"
def test_controls_are_chart_columns():   # 每个 item 的 controls ⊆ CHART_COLUMNS
def test_x_columns_are_chart_columns():  # 每个国家的 x_columns ⊆ CHART_COLUMNS
def test_special_controls_have_citation():  # 每条 special_control 的 reason、citation 非空
def test_no_duplicate_eccns():       # ccl.json items 中 eccn 无重复（读原始 JSON 校验）
def test_embargoed_countries():      # rs.countries["KP"]["embargo"]、["CU"]、["IR"] 非空；["JP"]["embargo"] is None
def test_digest_changes_with_data(tmp_path):  # 复制 data 到 tmp_path，改 ccl.json 一个字节 → digest 不同
```

- [ ] **Step 3: 运行，确认失败**

Run: `backend$ pytest tests/test_data.py -v`
Expected: FAIL（`ImportError: cannot import name 'load_ruleset'`）

- [ ] **Step 4: 在 `app/rules.py` 实现 `CHART_COLUMNS`、`Decision`、`Ruleset`、`load_ruleset`**

`ccl.json` 的 `items` 列表转成以 eccn 为键的 dict；digest 按 Global Constraints 计算原始字节。

- [ ] **Step 5: 对照 eCFR 整理四个数据文件**

来源（`retrieved` 填当天日期，`meta.version` 同）：
- CCL：`https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774`，取第 3/4/5 类 50–80 条，含若干仅 AT 管制的 `.9x` 条目；`controls` 取 License Requirements 表中的 Country Chart 栏；没有国家表栏的管制（如 EI）放 `special_controls` 并写条款；`title_zh`、`keywords`（中英各 2–4 个）自行撰写。
- 国家表：`.../part-738/appendix-Supplement%20No.%201%20to%20Part%20738`，spec §4.2 所列国家中 eCFR 实际收录的；只存打 X 的栏。
- 禁运：Part 746 各节（746.2 古巴、746.4 朝鲜、746.6 克里米亚等地区、746.7 伊朗、746.8 俄罗斯/白俄罗斯、746.9 叙利亚），`embargo` 填对应条款；叙利亚以当日 eCFR 现状为准。
- 实体清单：`.../part-744/appendix-Supplement%20No.%204%20to%20Part%20744`，30–50 条，覆盖中国、俄罗斯等，含 Huawei Technologies Co., Ltd.。

- [ ] **Step 6: 运行，确认通过**

Run: `backend$ pytest tests/test_data.py -v && ruff check .`
Expected: 8 passed；ruff 无报错

- [ ] **Step 7: Commit**

```bash
git add .gitignore backend
git commit -m "feat(backend): add curated EAR ruleset and loader"
```

---

### Task 2: 判定引擎、名称规范化、物项检索

**Files:**
- Modify: `backend/app/rules.py`
- Test: `backend/tests/test_rules.py`

**Interfaces:**
- Consumes: Task 1 的 `Ruleset`、`CHART_COLUMNS`、`Decision`
- Produces（`app/rules.py`）：
  ```python
  @dataclass(frozen=True)
  class Finding:
      rule: Literal["embargo", "country_chart", "special_control", "entity_list"]
      decision: Decision
      message: str
      citation: str

  @dataclass(frozen=True)
  class CheckInput:
      eccn: str            # 已 strip + upper
      country: str         # 已 strip + upper
      end_user: str | None # 已 strip；空串 → None

  @dataclass(frozen=True)
  class Result:
      decision: Decision
      findings: list[Finding]
      ruleset_version: str
      ruleset_digest: str
      input: CheckInput

  def normalize_name(name: str) -> str
  def search_items(rs: Ruleset, q: str) -> list[dict]
  def check(rs: Ruleset, eccn: str, country: str, end_user: str | None) -> Result
      # 未知 ECCN → ValueError("未知 ECCN：<ECCN>")；未知国家 → ValueError("未知国家：<CC>")
  ```

- [ ] **Step 1: 写失败的测试 `tests/test_rules.py`（用小夹具，不依赖真实数据）**

夹具 `RS = Ruleset(...)`：
- items（title / title_zh / keywords 原样使用，保证检索断言唯一）：
  - `5A002`：`"Information security systems"` / `"信息安全系统"` / `["加密"]`，controls `["NS1","AT1"]`，special `[{"reason":"EI","citation":"15 CFR 742.15"}]`
  - `5A992`：`"Mass market information security items"` / `"大众市场信息安全物项"` / `["大众市场"]`，controls `["AT1"]`
  - `3A001`：`"Electronic items"` / `"电子元器件"` / `["电子"]`，controls `["NS2"]`
- countries：`CN`（x `["NS1","NS2"]`，embargo None）、`JP`（x `[]`）、`KP`（x `["NS1","NS2","AT1"]`，embargo `"15 CFR 746.4"`）
- entities：`{"name": "Huawei Technologies Co., Ltd.", "aliases": ["Huawei"], "country": "CN", "license_requirement": "For all items subject to the EAR", "review_policy": "Presumption of denial", "fr_citation": "84 FR 22961"}`
- version `"test"`，sources `[]`，digest `"deadbeef"`

```python
@pytest.mark.parametrize("eccn,country,end_user,decision,rules", [
    ("5A002", "KP", None, "LICENSE_REQUIRED", {"embargo", "country_chart", "special_control"}),
    ("3A001", "CN", None, "LICENSE_REQUIRED", {"country_chart"}),
    ("5A992", "CN", None, "NLR",              {"country_chart"}),
    ("EAR99", "JP", None, "NLR",              {"country_chart"}),
    ("5A002", "JP", None, "NEEDS_REVIEW",     {"country_chart", "special_control"}),
    ("5A992", "JP", "HUAWEI TECHNOLOGIES CO LTD", "LICENSE_REQUIRED", {"country_chart", "entity_list"}),
    ("5A992", "JP", "Huawei Technologis",  "NEEDS_REVIEW", {"country_chart", "entity_list"}),
    ("5A992", "JP", "Huawei Device",       "NLR",          {"country_chart", "entity_list"}),
    ("5A002", "CN", "Huawei",              "LICENSE_REQUIRED", {"country_chart", "special_control", "entity_list"}),
])
def test_check_table(...):  # r.decision == decision；{f.rule for f in r.findings} == rules

def test_country_chart_hit_per_column():   # check(RS,"5A002","CN",None) 的 country_chart 依据恰 1 条（NS1），
                                           # decision LICENSE_REQUIRED，citation 含 "738 Supp. 1" 与 "5A002"
def test_country_chart_miss_explains():    # check(RS,"5A992","CN",None) 恰 1 条 country_chart，NLR，message 含 "AT1"
def test_ear99_citation():                 # EAR99 的 country_chart 依据 citation == "15 CFR 734.3(c)"
def test_embargo_citation():               # KP 的 embargo 依据 citation == "15 CFR 746.4"
def test_entity_exact_citation():          # 精确命中依据 citation 含 "744.11" 与 "84 FR 22961"
def test_fuzzy_message_has_match_and_score():  # "Huawei Technologis" 的 message 含 "Huawei Technologies Co., Ltd." 与 "0.9"
def test_input_is_normalized():            # check(RS,"5a002 "," jp","  ").input == CheckInput("5A002","JP",None)，
                                           # 且无 entity_list 依据
def test_chinese_end_user_warns_english_only():  # check(RS,"5A992","JP","华为")：entity_list 依据 NLR，message 含 "英文"
def test_end_user_without_valid_chars_needs_review():  # end_user "Co., Ltd." → entity_list 依据 NEEDS_REVIEW
def test_unknown_eccn_raises():            # pytest.raises(ValueError, match="未知 ECCN：9Z999")
def test_unknown_country_raises():         # pytest.raises(ValueError, match="未知国家：ZZ")
def test_result_carries_ruleset():         # ruleset_version == "test"，ruleset_digest == "deadbeef"

def test_normalize_name():
    assert normalize_name("HUAWEI TECHNOLOGIES CO., LTD.") == "huaweitechnologies"
    assert normalize_name("Huawei Technologies Co., Ltd.") == "huaweitechnologies"
    assert normalize_name("华为技术有限公司") == "华为技术有限公司"
    assert normalize_name("Co., Ltd.") == ""

def test_search_eccn_prefix_first():       # search_items(RS,"5a0")[0]["eccn"] == "5A002"
def test_search_keyword():                 # [i["eccn"] for i in search_items(RS,"加密")] == ["5A002"]
def test_search_blank_and_special_chars(): # search_items(RS,"  ") 返回全部 3 条且按 ECCN 升序；search_items(RS,"%(") == []
```

- [ ] **Step 2: 运行，确认失败**

Run: `backend$ pytest tests/test_rules.py -v`
Expected: FAIL（`ImportError: cannot import name 'check'`）

- [ ] **Step 3: 实现 `normalize_name`、`search_items`、`check`**

- `normalize_name`：casefold → `re.split(r"[^\w]+")`（`\w` 保留中文）→ 丢后缀词 → `"".join`。
- `search_items`：按 spec §6 打分（ECCN 前缀 3 / 标题子串 2 / 关键词子串 1，取最高分），只用 `str.startswith` 和 `in`，不用正则。
- `check`：先规范化输入并校验（`EAR99` 视为合法、无管制），依次产生四步依据，顺序为 embargo → country_chart → special_control → entity_list；结论取最严。
- 实体匹配：对名称与每个别名规范化；任一完全相等 → 精确命中；否则取 `difflib.SequenceMatcher(None, a, b).ratio()` 最大值，≥ 0.85 → 疑似命中。规范化后为空 → 直接 NEEDS_REVIEW。在阈值处加注释：
  `# ponytail: 0.85 为经验阈值，基于字符序列；误报/漏报需要时换 rapidfuzz token_set_ratio + 人工标注集调参`

依据文案与出处（文案可微调，出处原样）：

| 情形 | message | citation |
|---|---|---|
| 禁运 | `{name_zh}受全面禁运/制裁管制` | 国家 `embargo` |
| 国家表命中（每栏一条） | `{eccn} 的管制栏 {col} 在{name_zh}打 X` | `15 CFR 738 Supp. 1（{col}）；15 CFR 774 Supp. 1（{eccn}）` |
| 国家表全未命中 | `{eccn} 的管制栏 {cols} 在{name_zh}均未打 X` | `15 CFR 738 Supp. 1；15 CFR 774 Supp. 1（{eccn}）` |
| EAR99 | `EAR99 物项不受国家表管制` | `15 CFR 734.3(c)` |
| 特殊管制 | `{reason} 管制在国家表中无对应栏，需人工复核` | special 的 `citation` |
| 实体精确命中 | `最终用户与实体清单条目「{name}」（{country}）一致；许可要求：{license_requirement}；审查政策：{review_policy}` | `15 CFR 744.11；15 CFR 744 Supp. 4（{fr_citation}）` |
| 实体疑似命中 | `最终用户与实体清单条目「{name}」相似度 {score:.2f}，疑似命中，需人工复核` | 同上 |
| 实体未命中 | `未在实体清单子集中命中（仅比对英文名称及别名）` | `15 CFR 744 Supp. 4` |
| 名称无有效字符 | `最终用户名称无有效字符，无法筛查，需人工复核` | `15 CFR 744 Supp. 4` |

- [ ] **Step 4: 运行，确认通过**

Run: `backend$ pytest -v && ruff check .`
Expected: 全部通过（test_data + test_rules）

- [ ] **Step 5: Commit**

```bash
git add backend/app/rules.py backend/tests/test_rules.py
git commit -m "feat(backend): add rule engine, name normalization and item search"
```

---

### Task 3: API（items / countries / check）

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `load_ruleset`、`search_items`、`check`、`Result`（Task 1–2）
- Produces（`app/main.py`）：
  ```python
  app: FastAPI
  RULESET: Ruleset              # 模块导入时 load_ruleset(DATA_DIR)，DATA_DIR = Path(__file__).parent.parent / "data"
  class CheckRequest(BaseModel):
      eccn: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20)]
      country: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=2, max_length=2)]
      end_user: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
  def run_check(req: CheckRequest) -> Result   # ValueError → HTTPException(422, detail=str(e))
  ```
  - `GET /api/items?q=` → `list[dict]`（item 原样）
  - `GET /api/countries` → `[{"code", "name_zh", "embargoed": bool}]`，按 code 升序
  - `POST /api/check` → `Result`（`response_model=Result`，FastAPI 直接序列化 dataclass）

- [ ] **Step 1: 写失败的测试 `tests/test_api.py`（真实数据，`TestClient(app)`）**

```python
def test_items_eccn_first():          # GET /api/items?q=5A002 → 200，json()[0]["eccn"] == "5A002"
def test_items_empty_returns_all():   # GET /api/items → 长度 == len(RULESET.items)
def test_countries():                 # GET /api/countries → 含 {"code": "KP", ..., "embargoed": True}；JP embargoed False；每项 name_zh 非空
def test_check_ok():                  # POST {"eccn": "5A002", "country": "CN"} → 200，decision "LICENSE_REQUIRED"，
                                      # ruleset_digest == RULESET.digest
def test_check_lowercase_input():     # POST {"eccn": " 5a002", "country": "cn", "end_user": "  "} →
                                      # input == {"eccn": "5A002", "country": "CN", "end_user": None}
def test_check_unknown_eccn():        # POST {"eccn": "9Z999", "country": "CN"} → 422，detail == "未知 ECCN：9Z999"
def test_check_bad_country_length():  # POST {"eccn": "5A002", "country": "CHN"} → 422，detail 为 list
def test_check_end_user_too_long():   # end_user = "a" * 201 → 422
```

- [ ] **Step 2: 运行，确认失败**

Run: `backend$ pytest tests/test_api.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.main'`）

- [ ] **Step 3: 实现 `app/main.py`**

`app = FastAPI(title="迷你出口合规查询台")`。不加 CORSMiddleware。

- [ ] **Step 4: 运行，确认通过，并手动看接口文档**

Run: `backend$ pytest -v && ruff check . && uvicorn app.main:app --port 8000`，打开 `http://localhost:8000/docs` 试一次 `/api/check`
Expected: 全部测试通过；/docs 中四个接口里已有三个可用

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat(api): add items, countries and check endpoints"
```

---

### Task 4: PDF 报告 + `/api/report`

**Files:**
- Create: `backend/app/report.py`, `backend/app/templates/report.html`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_report.py`

**Interfaces:**
- Consumes: `Result`、`CheckInput`（Task 2）；`CheckRequest`、`run_check`（Task 3）
- Produces（`app/report.py`）：
  ```python
  TZ = ZoneInfo("Asia/Shanghai")
  def report_id(result: Result) -> str                          # 12 位 hex，见 Global Constraints
  def render_html(result: Result, generated_at: datetime) -> str
  def render_pdf(result: Result, generated_at: datetime) -> bytes
  ```
  - `POST /api/report`（body `CheckRequest`）→ `Response(media_type="application/pdf")`，header `Content-Disposition: attachment; filename="report-{eccn}-{country}-{YYYYMMDD}.pdf"`（日期按 TZ）

- [ ] **Step 1: 写失败的测试 `tests/test_report.py`**

```python
def test_report_id_deterministic():   # 同一 Result 两次 report_id 相同；长度 12；全为 hex
def test_report_id_changes_with_input_and_digest():  # end_user 不同 → 不同；ruleset_digest 不同 → 不同
def test_html_contents():             # render_html 含 "出口合规初筛报告"、report_id(result)、ruleset_version、
                                      # ruleset_digest、每条 finding 的 citation、"简化子集，仅供演示，不构成法律意见。"
def test_html_escapes_end_user():     # end_user="<b>x</b>" → html 含 "&lt;b&gt;x&lt;/b&gt;"，不含 "<b>x</b>"
def test_pdf_bytes():                 # render_pdf(...)[:4] == b"%PDF"
def test_report_endpoint():           # POST /api/report {"eccn": "5A002", "country": "CN"} → 200，
                                      # content-type 为 application/pdf，content-disposition 含 'filename="report-5A002-CN-'，
                                      # content[:4] == b"%PDF"
def test_report_endpoint_unknown():   # POST /api/report {"eccn": "9Z999", "country": "CN"} → 422
```

测试中的 Result 用 `app.main.RULESET` 加 `check(...)` 构造。

- [ ] **Step 2: 运行，确认失败**

Run: `backend$ pytest tests/test_report.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.report'`）

- [ ] **Step 3: 实现 `report.py` 与 `templates/report.html`，在 `main.py` 加 `/api/report`**

- Jinja2 `Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape(["html"]))`。
- 模板内联 CSS：A4、`@page { @bottom-center { content: "第 " counter(page) " / " counter(pages) " 页"; } }`；`font-family: "Noto Sans CJK SC", "PingFang SC", sans-serif`；结论大字并带颜色（红/黄/绿）且有中文标签；依据表四列：规则 / 结论 / 说明 / 条款出处；长文本 `word-break: break-all`。
- 内容顺序按 spec §8。
- macOS 上 WeasyPrint 找不到 pango 时：`export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`（写进 README 本地开发一节，Task 8）。

- [ ] **Step 4: 运行，确认通过，并肉眼检查 PDF**

Run: `backend$ pytest -v && ruff check .`，然后 `curl -s -X POST localhost:8000/api/report -H 'content-type: application/json' -d '{"eccn":"5A002","country":"CN","end_user":"Huawei"}' -o /tmp/r.pdf && open /tmp/r.pdf`
Expected: 全部通过；PDF 中文正常显示，有页码，表格不溢出

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests/test_report.py
git commit -m "feat(report): add reproducible PDF report export"
```

---

### Task 5: 前端骨架 + 类型 + API 封装 + 物项检索

**Files:**
- Create: `frontend/`（`npm create vite@latest frontend -- --template react-ts`）
- Create: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/components/ItemSearch.tsx`
- Modify: `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/src/App.tsx`；删除模板自带的 `App.css`、`assets/`

**Interfaces:**
- Consumes: Task 3/4 的 HTTP 接口
- Produces:
  ```ts
  // types.ts
  export type Decision = "LICENSE_REQUIRED" | "NEEDS_REVIEW" | "NLR";
  export interface Item { eccn: string; title: string; title_zh: string; keywords: string[]; controls: string[]; special_controls: { reason: string; citation: string }[] }
  export interface Country { code: string; name_zh: string; embargoed: boolean }
  export interface Finding { rule: "embargo" | "country_chart" | "special_control" | "entity_list"; decision: Decision; message: string; citation: string }
  export interface CheckRequest { eccn: string; country: string; end_user?: string }
  export interface CheckResult { decision: Decision; findings: Finding[]; ruleset_version: string; ruleset_digest: string; input: { eccn: string; country: string; end_user: string | null } }
  export const EAR99_ITEM: Item   // eccn "EAR99"，title_zh "不在 CCL 上"，其余为空

  // api.ts
  export class ApiError extends Error {}
  export function searchItems(q: string): Promise<Item[]>
  export function getCountries(): Promise<Country[]>
  export function check(req: CheckRequest): Promise<CheckResult>
  export function downloadReport(req: CheckRequest): Promise<void>
  // 非 2xx 时抛 ApiError：detail 为字符串则用之；为数组则用 detail[0].msg；否则 "请求失败（{status}）"

  // components/ItemSearch.tsx
  export function ItemSearch(props: { selected: Item | null; onSelect: (item: Item) => void }): JSX.Element
  ```

- [ ] **Step 1: 建 Vite 项目，接入 Tailwind 与代理**

`npm i -D tailwindcss @tailwindcss/vite`；`vite.config.ts` 加 `tailwindcss()` 插件和 `server.proxy: { "/api": "http://localhost:8000" }`；`index.css` 只留 `@import "tailwindcss";`。

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 2: 实现 `types.ts`、`api.ts`、`ItemSearch.tsx`，`App.tsx` 先只渲染 ItemSearch 与已选物项**

ItemSearch：`<label>` 搭配搜索框；`useEffect` 里用 `setTimeout` 防抖 300ms 调 `searchItems`（清理函数中 `clearTimeout`，并忽略过期响应）；列表首项固定为 `EAR99_ITEM`；每项是 `<button>`，显示 ECCN、`title_zh`、controls 标签，选中项高亮并带 `aria-pressed`；分别显示加载中 / 出错 / 无匹配物项三种状态。

- [ ] **Step 3: 检查与手动验证**

Run: `npm run lint && npm run build`；后端 `uvicorn app.main:app --port 8000`，前端 `npm run dev`，在浏览器打开 `http://localhost:5173`
Expected: lint 与构建无错；输入 `5a0` 后 5A002 排第一，输入 `加密` 能搜到 5A002；只用键盘（Tab + Enter）也能选中物项；停掉后端时显示错误提示

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat(frontend): scaffold app with typed API client and item search"
```

---

### Task 6: 判定表单 + 结果卡片 + PDF 下载

**Files:**
- Create: `frontend/src/components/CheckForm.tsx`, `frontend/src/components/ResultCard.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Task 5 的 `types.ts`、`api.ts`、`ItemSearch`
- Produces:
  ```ts
  export function CheckForm(props: { item: Item | null; onResult: (r: CheckResult) => void }): JSX.Element
  export function ResultCard(props: { result: CheckResult }): JSX.Element
  ```

- [ ] **Step 1: 实现三个文件**

- CheckForm：挂载时调用 `getCountries` 填充原生 `<select>`（禁运国名称后加「（禁运）」）；最终用户输入框可选，`maxLength={200}`；未选物项或未选国家时提交按钮禁用；提交中显示「判定中…」；`ApiError` 的信息显示在表单下方。
- ResultCard：结论徽章（`LICENSE_REQUIRED` 红色「需许可证」、`NEEDS_REVIEW` 黄色「需人工复核」、`NLR` 绿色「无需许可证」）；依据列表，每条显示徽章、message、citation；底部显示「规则版本 {ruleset_version} · {ruleset_digest}」和「导出 PDF」按钮，点击后调用 `downloadReport({eccn, country, end_user: end_user ?? undefined})`，下载期间按钮禁用，失败时显示错误。
- App：左右两栏布局（窄屏改为上下）；切换物项时清空结果；页脚显示免责声明原文。
- `downloadReport`：`res.blob()` → `URL.createObjectURL` → 创建临时 `<a download>` 并点击 → `URL.revokeObjectURL`；文件名取自响应头 `Content-Disposition`，取不到时用 `report.pdf`。

- [ ] **Step 2: 检查与手动验证**

Run: `npm run lint && npm run build`；前后端开发服务器同时运行
Expected:
- 5A002 + 中国 → 需许可证，有 NS1 依据
- 5A992 + 日本 → 无需许可证
- 5A002 + 日本 → 需人工复核（EI）
- 任意物项 + 日本 + 最终用户 `Huawei` → 需许可证（实体清单）
- 「导出 PDF」下载的文件名为 `report-5A002-CN-YYYYMMDD.pdf`
- 用 devtools 把最终用户改成 201 个字符后提交 → 表单下方显示可读的错误文字，而不是 `[object Object]`

- [ ] **Step 3: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): add check form, result card and PDF download"
```

---

### Task 7: 单容器交付 + CI

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.github/workflows/ci.yml`
- Modify: `backend/app/main.py`（静态托管）

**Interfaces:**
- Consumes: 全部后端与前端代码
- Produces: `STATIC_DIR = Path(__file__).parent.parent / "static"`；目录存在时在所有 `/api` 路由之后执行 `app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")`；目录不存在时（本地开发、测试）跳过

- [ ] **Step 1: 写 Dockerfile 等文件**

- Dockerfile 阶段一：`node:22-alpine`，`WORKDIR /web`，先复制 `package*.json` 再 `npm ci`，然后复制 `frontend/` 并 `npm run build`。
- 阶段二：`python:3.12-slim`，`apt-get install --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-noto-cjk` 并清理 apt 缓存；`WORKDIR /srv`；`pip install --no-cache-dir -r requirements.txt`；复制 `backend/app → /srv/app`、`backend/data → /srv/data`，从阶段一复制 `/web/dist → /srv/static`；`useradd -r app` 后 `USER app`；`EXPOSE 8000`；`CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`。
- `.dockerignore`：`**/node_modules **/.venv **/__pycache__ frontend/dist .git`。
- `docker-compose.yml`：单服务 `app`，`build: .`，`ports: ["8000:8000"]`。
- `ci.yml`：在 `push`、`pull_request` 时触发，三个并行 job：
  1. `backend`：`actions/setup-python` 3.12，`sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 fonts-noto-cjk`，`pip install -r requirements-dev.txt`，`ruff check .`，`pytest`（`working-directory: backend`）。
  2. `frontend`：`actions/setup-node` 22，开启 npm 缓存，`npm ci && npm run lint && npm run build`（`working-directory: frontend`）。
  3. `docker`：`docker build .`。

- [ ] **Step 2: 本地验证容器**

Run: `docker compose up --build -d && sleep 5 && curl -sf localhost:8000/ | head -c 200 && curl -sf 'localhost:8000/api/items?q=5A002' | head -c 200 && curl -sf -X POST localhost:8000/api/report -H 'content-type: application/json' -d '{"eccn":"5A002","country":"CN"}' -o /tmp/c.pdf && head -c 4 /tmp/c.pdf && docker compose exec app whoami`
Expected: 返回 HTML、返回 JSON、输出 `%PDF`、输出 `app`；浏览器打开 `localhost:8000` 能走通完整流程，PDF 中文显示正常

- [ ] **Step 3: 后端测试仍通过**

Run: `backend$ pytest -v`
Expected: 全部通过（没有 static 目录时跳过挂载）

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore .github backend/app/main.py
git commit -m "build: single-container delivery and CI"
```

---

### Task 8: README + 截图/GIF

**Files:**
- Create: `README.md`, `docs/screenshot.png`, `docs/demo.gif`

**Interfaces:**
- Consumes: 运行中的容器（Task 7）

- [ ] **Step 1: 录制截图与 GIF**

容器运行时，录一遍「检索 5A002 → 选中国 + Huawei → 判定 → 导出 PDF」，GIF 控制在 15 秒以内、5MB 以下；再截一张判定结果页的截图。

- [ ] **Step 2: 写 README（结构按 spec §12）**

必须包含：
- 一句话介绍、GIF
- 快速开始，代码块中的命令为 `docker compose up --build`，然后打开 `http://localhost:8000`
- 四步判定与三档结论的图解（可以是表格或 mermaid 流程图）
- 数据来源（四个 eCFR 链接）、`meta.version` 的含义、digest 的含义
- **设计决策**：每条写"做了什么 / 为什么 / 代价 / 何时升级"，覆盖数据文件 + 纯函数、三档结论、后端生成 PDF 与报告编号、无数据库、单容器、不配 CORS、0.85 阈值
- 已知简化与下一步（spec §2 的「不做」清单）
- 本地开发：后端 `uv venv -p 3.12`、`uvicorn`，前端 `npm run dev`，macOS 上需 `brew install pango`，必要时设置 `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`；运行测试的命令
- 免责声明原文

- [ ] **Step 3: 核对**

Run: 照 README 的「快速开始」从一个干净的 clone 跑一遍：`git clone . /tmp/ecd && cd /tmp/ecd && docker compose up --build`
Expected: 不需要任何额外步骤就能打开页面；README 里的所有链接和图片都能正常显示

- [ ] **Step 4: Commit**

```bash
git add README.md docs/screenshot.png docs/demo.gif
git commit -m "docs: add README with design decisions and demo"
```
