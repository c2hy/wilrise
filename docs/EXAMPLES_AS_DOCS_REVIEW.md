# Examples 即文档（Examples-as-Docs）审查报告

从「开发者几乎不看文档、仅靠 examples 就能学会正确、优雅使用本 JSON-RPC 框架」的目标出发，对当前 `examples/` 的审查结论与改进建议。

---

## 1. 总体评价

**⚠️ 能用，但容易误导**

- **优点**：有最小可运行示例（`minimal.py`）、有进阶示例（`main.py`）、有工程化示例（`auth_crud/`）；README 说明较全，中英双语。
- **主要问题**：进阶路径不清晰、部分示例与文档推荐用法不一致、缺少关键使用场景（batch、挂载、错误处理）的示例，且 `main.py` 中「同一概念多种写法」易让新手不知优先学哪种。

**结论**：当前不足以「替代大部分文档」；在不动核心实现的前提下，仅优化 examples 的命名、顺序、注释和少量新增示例，即可显著降低误导、提升好感度。

---

## 2. 最容易误导开发者的 Top 5 问题

### ① auth_crud 的 params 传参方式需在 README 中说明（已修正）

- **事实**：主 README 推荐 **whole params** 仅适用于「方法只有一个参数且为 BaseModel」的情况。当方法同时有 Pydantic 参数和 `Use(...)` 依赖时，框架要求按参数名传参（**keyed**），即 `"params": {"params": {"username": "alice", ...}}`。
- **现状**：auth_crud 的方法均有 `params: XParams` 与 `db/current_user: Use(...)`，因此必须使用 keyed；原 curl 写法正确。
- **已做**：在 examples README 中补充说明「当方法同时有 Pydantic 与 Use 时需 keyed；仅单 BaseModel 参数时推荐 whole params」，避免读者误以为 examples 与主文档矛盾。

---

### ② main.py 里「查用户」有三种等价写法，没有标明推荐路径

- **事实**：同一文件中存在：
  - `get_user`：`@app.method`，方法名即函数名，`Use(get_db_session)`
  - `get_user_route`：`@app.method("getUser")`，显式方法名
  - `get_user_by_alias`：`Param(alias="userId")`，参数别名
- **影响**：新手不知道「默认应该用哪种」「什么时候用别名 / 显式方法名」，容易误以为三种都要掌握或可以混用，增加认知负担。

**建议**：  
- 在 `main.py` 顶部或 README 的「What main.py demonstrates」中明确写：**默认推荐**是「方法名 = 函数名」+ 普通参数；`Param(alias=...)` 和 `@app.method("getUser")` 仅在需要与前端/规范命名一致时使用。  
- 或拆成两个示例：一个「推荐默认」（仅 `get_user` + Router），一个「命名与别名」（`getUser` + `userId`），避免在同一文件里平铺三种等价写法。

---

### ③ auth_crud 使用 debug=True 且无说明

- **事实**：`auth_crud/main.py` 中有 `app = Wilrise(debug=True)`；主文档与 `docs/errors.md` 明确要求生产环境 **不要** 开启 `debug=True`（会泄露堆栈与内部信息）。
- **影响**：示例若不加说明，容易被误当作「推荐配置」复制到生产，或让人忽略生产与示例环境的差异。

**建议**：在 `auth_crud/main.py` 中该行旁加注释，例如：`# debug=True for demo only; use debug=False or from_env() in production`；或在 examples 的 README 中单独一句说明「本示例为便于排查使用 debug=True，生产请使用 from_env() / debug=False」。

---

### ④ 缺少「能跑 → 可扩展 → 工程化」的中间台阶

- **事实**：当前结构是：`minimal.py`（单方法）→ `main.py`（Router + Param + Use + 多种写法）→ `auth_crud/`（完整应用）。从 minimal 到 main 一步跨度过大，中间没有「只加 Router」或「只加 Use」的单独示例。
- **影响**：想「只学 Router」或「只学依赖注入」的人，必须在 main.py 里自行剥离其他概念，容易抓不到重点或误以为必须一起用。

**建议**：  
- 要么在目录/README 中**明确写出学习路径**（例如：1. minimal → 2. main（Router + Use）→ 3. auth_crud），并在 main.py 或 README 用小节标出「Router 部分」「Use 部分」；  
- 要么增加一个中间示例（例如 `router_and_di.py`），只做「Router + prefix + 一个 Use」，不掺杂 Param 别名、显式方法名等，便于按需进阶。

---

### ⑤ 关键能力在 examples 中完全缺失，容易让人以为框架不支持

- **事实**：主 README 和文档中强调的能力在 examples 中**没有**对应示例：
  - **Batch 请求**：文档有描述，examples 无任何 batch 的 curl 或脚本；
  - **挂载到现有应用**：`app.as_asgi()` 与 Mount 只在主 README 代码块中出现，examples 目录下没有可运行的「FastAPI/Starlette + mount wilrise」示例；
  - **错误处理**：`RpcError` 与 `set_exception_mapper` 在 docs/errors.md 中有推荐用法，但 examples 里只有 auth_crud 内零散使用 RpcError，没有「最小错误示例」或「exception mapper 示例」。
- **影响**：用户会倾向于认为「examples 没写的就是不推荐或没有」，从而忽略 batch、挂载、统一错误映射等重要能力。

**建议**：  
- 至少在 **examples/README** 中为 batch、挂载、RpcError 各加一段「最小示例」代码块（可从主 README 或 docs 摘录），并注明「详见 README / docs/errors」；  
- 若有条件，可增加 `examples/batch_requests.sh`（或 README 中的 curl 数组示例）和 `examples/mount_fastapi.py`（或 `mount_starlette.py`），保证「示例即文档」覆盖主文档中的真实使用路径。

---

## 3. 理想的 examples 目录结构示例

在不大改现有文件的前提下，用「命名 + 顺序 + 少量新增」表达学习路径与边界，建议目标结构如下（树状）：

```text
examples/
├── README.md              # 学习路径 + 每个示例一句话 + 运行方式（优先 cd examples）
├── README.zh-CN.md
├── pyproject.toml
├── uv.lock
│
├── 01_minimal.py          # 最小可运行：单方法 + app.run()（原 minimal.py，建议重命名以表达顺序）
├── 02_router_and_di.py    # 推荐下一步：仅 Router + prefix + 一个 Use，无 Param 别名/显式方法名（可合并自 main.py 精简）
├── 03_full_api.py         # 完整 API 演示：Param(description/alias/default)、@app.method("name")（原 main.py 内容，可重命名）
│
├── auth_crud/             # 工程化示例：SQLAlchemy + JWT + CRUD
│   ├── __init__.py
│   ├── main.py            # 修正：debug 注释 + 若 README 中 curl 改为 whole-params
│   ├── auth.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   └── test_concurrent.py
│
├── mounting/              # 可选：挂载到现有应用（若新增）
│   ├── README.md          # 说明：as_asgi() + FastAPI/Starlette mount
│   └── main_fastapi.py    # FastAPI app + app.mount("/rpc", rpc.as_asgi())
│
└── (可选) batch_requests.example  # 或仅在 README 中给出 curl 数组示例，不单独文件
```

**命名与顺序**：  
- `01_` / `02_` / `03_` 明确「先看哪个、后看哪个」，避免「minimal / main」这种对「main」歧义（主入口 vs 完整示例）。  
- 若团队不喜欢数字前缀，可用 `minimal.py`、`router_and_di.py`、`full_api.py`，并在 **README 开头**用有序列表写出推荐阅读顺序。

---

## 4. 仅改 examples 就能显著提升好感度的 3+ 处

### （1）在 auth_crud 小节注明 keyed 与 whole params 的适用场景（已完成）

- **改**：在 `examples/README.md` 与 `examples/README.zh-CN.md` 的 auth_crud 小节中，明确写出：当方法同时有 Pydantic 参数和 `Use(...)` 时，客户端需按参数名传参（keyed）；仅当方法只有一个 BaseModel 参数时，主 README 推荐 whole params。  
- **收益**：避免读者误以为 auth_crud 的 keyed 写法与主文档「whole params 推荐」矛盾，建立正确心智（单参 BaseModel → whole params；Pydantic + Use → keyed）。

### （2）在 main.py（或 03_full_api.py）与 examples README 中标出「推荐 vs 可选」

- **改**：在 `main.py` 文件顶或「What main.py demonstrates」中增加一小节：  
  - **推荐默认**：方法名即函数名、直接参数（如 `get_user(user_id: int, db=Use(...))`）；  
  - **按需使用**：`Param(alias="userId")` 用于与前端命名一致；`@app.method("getUser")` 用于固定 RPC 方法名。  
- **可选**：将 `get_user` 保留为「主示例」，`get_user_route` / `get_user_by_alias` 上方加注释 `# Optional: explicit method name / param alias for client compatibility`。  
- **收益**：减少「三种写法都要学」的困惑，传达「默认一种，其余是扩展」的哲学。

### （3）为 debug=True 和 batch/挂载/错误 补一句说明或最小示例

- **改**：  
  - 在 `auth_crud/main.py` 的 `Wilrise(debug=True)` 旁加注释：`# Demo only; use debug=False or from_env() in production`。  
  - 在 `examples/README.md` 的「Run」或文末增加简短小节「Other patterns」：  
    - **Batch**：贴一段「发送 JSON 数组」的 curl 示例（或指向主 README）。  
    - **Mounting**：贴 2–3 行 `app.mount("/rpc", rpc.as_asgi())` 的用法（或指向主 README）。  
    - **Errors**：写一句「业务错误用 `RpcError`；依赖异常用 `set_exception_mapper`」，并指向 `docs/errors.md`。  
- **收益**：不增加新文件也能让「示例即文档」覆盖主文档中的真实使用路径，避免「示例没写 = 不支持」的误解。

---

## 5. 其他简要观察（可选优化）

| 项目 | 现状 | 建议 |
|------|------|------|
| 注释噪音 | `main.py` 有 `# ---------- Create app and mount router ----------` 等分隔，整体适中 | 可保留；避免在每行加「这是什么」类注释。 |
| 关键一步未解释 | `auth_crud` 里 `CloseDbMiddleware` + `close_db_session` 的关系、为何要 rollback | 在 `main.py` 或 README 用 1–2 句说明「每个请求独立 session，结束时 rollback 未提交变更」。 |
| 内部细节 | `main.py` 有 `# pyright: reportArgumentType=none` | 若面向学习者，可移到 pyrightconfig 或去掉，减少「只对作者有意义」的配置。 |
| 学习顺序 | 当前 README 只列文件，未写「建议顺序」 | 在 README 开头增加「建议阅读顺序：minimal → main → auth_crud」。 |

---

以上审查基于当前 `examples/` 与主 README、`docs/errors.md`、`docs/configuration.md` 等文档的一致性，未假设框架内部实现细节。若你希望，我可以按上述某一条直接给出 patch 级别的修改稿（例如只做 Top 5 中的 ① 和 ③）。
