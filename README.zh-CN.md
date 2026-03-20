# PaperFeeder（中文说明）

PaperFeeder 是一个**每日论文 + 博客摘要**流水线：用 **Semantic Scholar** 做个性化，并支持 **点赞/点踩反馈** 闭环。

> 英文版说明见 [README.md](README.md)。

---

## 项目是干什么的？

1. **定时/手动**拉 arXiv、博客等来源，经关键词与 LLM 筛选后生成 HTML 报告。  
2. 可通过 **Resend** 等发邮件；也可用 `--dry-run` 只生成本地 `report_preview.html`。  
3. 若配置了 Cloudflare Worker + D1，邮件/网页里可以对每篇论文 **👍 / 👎**，点击会记到 D1；之后用命令把结果**写回**本地的 `state/semantic/seeds.json`，影响后续推荐。

---

## 目录结构（一眼能看懂）

```text
PaperFeeder/
├── paperfeeder/          # 所有 Python 业务代码（主包）
├── scripts/              # 一键安装、反馈相关脚本
├── cloudflare/           # 反馈用 Worker + D1 表结构 SQL
├── state/semantic/       # 长期状态：种子 ID、最近见过的论文
├── artifacts/            # 每次运行生成的 manifest 等（可删，git 忽略）
├── user/                 # 你改的设置、人设、提示词片段
├── tests/                # 单元测试
├── config.yaml           # 默认配置
└── main.py               # 跑摘要的主入口
```

### `paperfeeder/` 里重点文件

- 根目录几个**扁平模块**：`models.py`（论文/作者模型）、`email.py`（发信）、`chat.py`（调 LLM 的客户端）。  
- 主流程：`paperfeeder/pipeline/runner.py`。  
- 把反馈写进种子文件：`paperfeeder/cli/apply_feedback.py`（也可用 `python -m paperfeeder.cli.apply_feedback`）。

### `state/semantic/` 是什么？

| 文件 | 作用 |
|------|------|
| `seeds.json` | 长期保存：你标记过「喜欢 / 不喜欢」的 Semantic Scholar 论文 ID，用来影响后面推荐。 |
| `memory.json` | 短期记忆：最近出现过的论文键，减少同一篇反复刷脸。 |

这是**运行数据**，不是手写源码。

### `artifacts/` 是什么？

每次 digest 可能生成例如：

- `run_feedback_manifest_<run_id>.json`：这一期里每篇论文与反馈条目的对应关系。  
- `semantic_feedback_template_<run_id>.json`：给人填的问卷模板。

都是**生成物**，可删；已在 `.gitignore` 里忽略。

### `cloudflare/` 是什么？

- `feedback_worker.js`：部署在 Cloudflare 上的小服务，处理 `/feedback?t=...`（记录点赞）和 `/run?run_id=...`（看网页版报告）。  
- `d1_feedback_events.sql`：在 D1 里建表用的 SQL。

---

## 第一次怎么用？

### 1. 安装依赖

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
```

### 2. 配置密钥与账号

把 **`.env.example` 复制成 `.env`**，按里面注释填写（邮件、LLM、可选的反馈与 D1 等）。

还可以按需改：

- `user/settings.yaml`  
- `user/research_interests.txt`（研究兴趣人设）  
- `user/prompt_addon.txt`（给 LLM 的附加说明）

### 3. 跑一版摘要（先试跑，不发真邮件）

```bash
python main.py --dry-run
```

### 3b. 轻量调试（一篇假论文，不爬全网）

不想每次为了试功能都去拉几百篇、再过关键词/双阶段 LLM/Tavily？用 **`--debug-sample`**：从 JSON 读 1 篇（或几篇）固定数据，**跳过** arXiv/HF/S2 抓取、博客、粗筛/精筛 LLM、Tavily 增强；仍会走 **写报告 → manifest → 邮件/HTML 预览 →（若配置了）D1** 这条链，适合验证反馈链接、Worker、排版等。

1. 复制模板：  
   `cp user/debug_sample.example.json user/debug_sample.json`  
2. 编辑 `user/debug_sample.json`：改 `title`、`url`、`arxiv_id`；若要测 👍/👎 签名链接，填上能解析的 **`semantic_paper_id`**（或配好 `SEMANTIC_SCHOLAR_API_KEY` 让程序解析）。

```bash
# 默认：**不调**主报告 LLM，只用固定极简 HTML（测邮件 / manifest / D1 / Worker，省 token）
python main.py --debug-sample --dry-run

# 同上但**真发邮件**（需配置 RESEND 等）
python main.py --debug-sample

# 调试样本仍用 JSON，但**要**主报告 LLM 写正文时加上：
python main.py --debug-sample --debug-llm-report --dry-run

# 正常抓取论文，但报告正文仍用极简 HTML（不调主 digest LLM）
python main.py --debug-minimal-report --dry-run

# 指定别的 JSON
python main.py --debug-sample --debug-sample-path path/to/papers.json --dry-run
```

默认 **不会** 更新 `state/semantic/memory.json`（避免调试把记忆弄脏）；若要更新，加上 **`--debug-write-memory`**。

`python main.py --dry-run` 会在本地写出 `report_preview.html`，也可能在 `artifacts/` 里生成 manifest 等文件。

### 4. 正式跑（例如看最近 3 天）

```bash
python main.py --days 3
```

（是否真发邮件取决于你是否关掉 dry-run 以及 `.env` 里邮件配置。）

---

## 常用命令速查

| 你想做的事 | 命令 |
|------------|------|
| 本地试跑、生成预览 | `python main.py --dry-run` |
| 指定回溯天数 | `python main.py --days 3` |
| 把「已审核的反馈」合并进 seeds（先演练） | `python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run` |
| 同上，真正写入 `seeds.json` | 去掉 `--dry-run` |
| 从 **Cloudflare D1** 拉待处理反馈再应用（先演练） | `python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts --dry-run` |

脚本包装（等价于上面 apply_feedback）：

```bash
python scripts/semantic_feedback_apply.py --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
```

---

## 配置优先级（谁覆盖谁）

程序会按顺序合并，**后面的覆盖前面的**：

1. `config.yaml`  
2. `user/settings.yaml`  
3. **环境变量**（`.env` 里由 `python-dotenv` 加载的也算）  
4. `user/research_interests.txt`、`user/prompt_addon.txt`

与语义状态相关的默认路径在 `config.yaml` 里一般是：

```yaml
semantic_scholar_seeds_path: "state/semantic/seeds.json"
semantic_memory_path: "state/semantic/memory.json"
```

---

## 反馈流程（从邮件点到写进种子）

1. 运行 `python main.py` 生成当期 digest。  
2. 若条件满足，会在 `artifacts/` 里导出 manifest 等。  
3. 邮件/网页里的链接指向你部署的 **Cloudflare Worker**。  
4. 你在 Worker 或 D1 里积累的处理结果，最终通过 `apply_feedback` **写回** `state/semantic/seeds.json`。

### 邮件里直接 👍 / 👎 需要什么？

在 **`.env`** 里至少要有（且与 Worker 一致）：

- **`FEEDBACK_ENDPOINT_BASE_URL`**：Worker 的公网根地址，**不要**末尾多写 `/`。  
- **`FEEDBACK_LINK_SIGNING_SECRET`**：和 Worker 上用 `wrangler secret put` 设的那串**完全一样**。

否则 manifest 里**没有**签名 URL，HTML 里就不会出现可用的点赞链接。  
邮件里点链接是普通的 **GET** 打开 `/feedback?t=...`；邮件客户端一般会**忽略**报告里附带的 JavaScript，但不影响链接本身。

**「Open Feedback Web Viewer」** 那一行是**可选**的：它只是多一个浏览器里打开整份报告的入口（`/run?run_id=...`），适合邮件排版乱、换设备看、或转发给别人。每篇旁边的 👍/👎 **不依赖**这个入口。若不需要，在 `.env` 里设 `FEEDBACK_WEB_VIEWER_LINK_IN_EMAIL=false`，或在 `user/settings.yaml` 里写 **`feedback_web_viewer_link_in_email: false`（布尔值，不要加引号）**；若写成带引号的 `"false"`，YAML 会当成字符串，以前会被误判为「开」，现已修复。Python 仍会照常把 HTML 推到 D1，需要时仍可手动打开 `/run`。

---

## 反馈相关配置清单（对照填就行）

复制 **`.env.example` → `.env`**，按下表检查（环境变量会覆盖 yaml，逻辑见 `paperfeeder/config/schema.py`）。

| 要配什么 | 填在哪 | 说明 |
|----------|--------|------|
| Worker 地址 | `.env` → `FEEDBACK_ENDPOINT_BASE_URL` | 例如 `https://paperfeeder-feedback.xxx.workers.dev`，**无尾斜杠**。邮件里链接就指向这里。 |
| 签名密钥 | `.env` **和** Worker 两边 | **必须相同**。Worker：`cd cloudflare`，`npx wrangler secret put FEEDBACK_LINK_SIGNING_SECRET`，再在同一 `.env` 里写同一串。用于生成和校验 `t=` 参数。 |
| D1 绑在 Worker 上 | Cloudflare 控制台或 Wrangler | Worker 代码里用的绑定名必须是 **`DB`**，示例见 `cloudflare/wrangler.toml.example`。表结构执行一次：`npx wrangler d1 execute <数据库名> --remote --file=d1_feedback_events.sql`（在 `cloudflare/` 目录下时文件名为 `d1_feedback_events.sql`）。 |
| Python 访问 D1 | `.env` → `CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN`、`D1_DATABASE_ID` | digest 会把网页版报告写入 D1 的 `feedback_runs`；`--from-d1` 读 pending 事件也用这三项。**数据库 ID 要和 Worker 用的是同一个。** |
| Semantic Scholar | `.env` → `SEMANTIC_SCHOLAR_API_KEY`（强烈建议） | 只有解析出 **`semantic_paper_id`** 才会给该篇生成 `action_links`（可点的 👍/👎）。有 API Key 能明显减少「没有按钮」的论文。 |
| 邮件里的 Web Viewer 入口 | `.env` → `FEEDBACK_WEB_VIEWER_LINK_IN_EMAIL`（默认 `true`） | 设为 `false` 可去掉「Open Feedback Web Viewer」横幅；每篇 👍/👎 不变。 |
| 邮件里的反馈附件 | `.env` → `FEEDBACK_EMAIL_ATTACHMENTS`（默认 `all`） | `all` = manifest + 问卷模板（两个 JSON）。`manifest` = 只要 `run_feedback_manifest_*.json`。`none` = 不附任何文件（文件仍会写在 `artifacts/`）。 |

### 一步一步你要做什么（按这个顺序来）

下面把上表里的 5 件事拆成**可执行的步骤**。你不需要一次全做完：只要**不配 Worker**，邮件里就不会有 👍/👎；但配到第 6 步左右，邮件点赞 + 写 D1 才能串起来。

---

**第 0 步：准备 `.env`**

1. 复制：`.env.example` → `.env`（若还没有）。  
2. 后面所有「填进 `.env`」的项，都写在这个文件里，**不要提交到 git**。

---

**第 1 步：在 Cloudflare 上创建一个 D1 数据库**

1. 打开终端，进入本仓库的 `cloudflare` 目录：  
   `cd cloudflare`
2. 执行（数据库名可改，但要和后面 `wrangler.toml` 里一致）：  
   `npx wrangler d1 create paperfeeder-feedback`
3. 命令输出里会有一段 **`database_id`**（一长串 UUID）。**复制保存**，下面两步都要用。

---

**第 2 步：让 Worker 能访问这个 D1（绑定名必须是 `DB`）**

1. 若还没有：`cp wrangler.toml.example wrangler.toml`
2. 用编辑器打开 `cloudflare/wrangler.toml`，找到 `[[d1_databases]]` 里的 `database_id = "..."`  
3. 把引号里的内容**换成第 1 步复制的那串 ID**。  
4. 确认 `binding = "DB"` **不要改**（代码里写死了 `env.DB`）。

---

**第 3 步：在 D1 里建表（只做一次）**

仍在 `cloudflare/` 目录下执行（`paperfeeder-feedback` 若你第 1 步用了别的名字，这里改成你的库名）：

```bash
npx wrangler d1 execute paperfeeder-feedback --remote --file=d1_feedback_events.sql
```

这样 `feedback_events`、`feedback_runs` 等表才会存在，Worker 和 Python 才能读写。

---

**第 4 步：设置签名密钥（Worker 和 PaperFeeder 必须同一条）**

1. 自己想一串**足够长、保密的随机字符串**（或让密码生成器生成）。  
2. 在 `cloudflare/` 下执行：  
   `npx wrangler secret put FEEDBACK_LINK_SIGNING_SECRET`  
   提示粘贴时，把这串**原样粘贴**进去。  
3. 打开项目根目录的 `.env`，加一行（**同一串**，不要多空格、不要换行）：  
   `FEEDBACK_LINK_SIGNING_SECRET=你刚才那一串`

作用：Python 用它在邮件链接里签 `t=`；Worker 用同一密钥校验，防止别人伪造点赞链接。

---

**第 5 步：部署 Worker，拿到公网 URL**

在 `cloudflare/` 下：

```bash
npx wrangler deploy
```

终端或 Cloudflare 控制台里会看到 Worker 的地址，例如 `https://paperfeeder-feedback.xxx.workers.dev`。

1. 打开根目录 `.env`，添加（**末尾不要加斜杠 `/`**）：  
   `FEEDBACK_ENDPOINT_BASE_URL=https://你的子域.workers.dev`

---

**第 6 步：让本机 Python 也能访问「同一个」D1（上传网页报告、从 D1 拉反馈）**

这三项是给 **PaperFeeder 主程序** 调 Cloudflare API 用的，**数据库 ID 必须和第 1～2 步是同一个**。

1. 登录 Cloudflare 仪表盘 → 右侧或账户信息里找到 **Account ID** → 写入 `.env`：  
   `CLOUDFLARE_ACCOUNT_ID=...`
2. **My Profile → API Tokens** 创建一个 Token，权限要包含对你账号下 **D1 的读写**（以及按需 Workers 相关；按你实际界面勾选）。  
   写入：  
   `CLOUDFLARE_API_TOKEN=...`
3. 把**第 1 步那个 `database_id`** 再写一遍：  
   `D1_DATABASE_ID=...`

不配这三项：**digest 仍可能发邮件**，但**不一定能把报告同步到 D1**；用 `--from-d1` 应用反馈时也会缺凭证。

---

**第 7 步（强烈建议）：Semantic Scholar API Key，减少「没有 👍/👎」的论文**

1. 到 Semantic Scholar 开发者页申请 API Key（以官网说明为准）。  
2. 在 `.env` 里添加：  
   `SEMANTIC_SCHOLAR_API_KEY=...`

不配的话：很多论文解析不出 `semantic_paper_id`，manifest 里就没有 `action_links`，邮件里**那几篇旁边就没有按钮**——不是程序坏了，是缺 ID。

---

**第 8 步：验证**

1. 在项目根目录：`source .venv/bin/activate`（若用虚拟环境）  
2. `python main.py --dry-run`  
3. 打开生成的 `report_preview.html` 或看 `artifacts/run_feedback_manifest_*.json`：有 `action_links` 的条目，邮件里才会有对应点赞链接。

---

### 部署 Worker（最短步骤）

```bash
cd cloudflare
cp wrangler.toml.example wrangler.toml
# 编辑 wrangler.toml：把 database_id 换成 `wrangler d1 create paperfeeder-feedback` 输出里的 ID
npx wrangler d1 execute paperfeeder-feedback --remote --file=d1_feedback_events.sql
npx wrangler secret put FEEDBACK_LINK_SIGNING_SECRET
npx wrangler deploy
```

部署成功后，把终端里显示的 Worker URL 填进 `.env` 的 `FEEDBACK_ENDPOINT_BASE_URL`。

---

## GitHub Actions、`seeds.json` 和「记忆」到底干什么

若使用 `.github/workflows/` 里的自动化：

| 工作流 | 对状态文件做什么 |
|--------|------------------|
| **Daily digest**（`daily-digest.yml`） | 检出 `main`，从 **state 分支**（默认 `memory-state`，可用仓库变量 `SEED_STATE_BRANCH` 改）**拉取** `state/semantic/seeds.json` 和 `memory.json`，跑 `main.py`，再把更新后的 **`memory.json`** **推回**该分支。 |
| **Apply feedback**（`apply-feedback-queue.yml`） | 从 state 分支 **拉取** `seeds.json`，执行 `python -m paperfeeder.cli.apply_feedback --from-d1`，把 D1 里 **pending** 的 👍/👎 合并进 seeds，再 **推回** **`seeds.json`**。现已支持 **定时**（默认每 6 小时、UTC 半点跑一次，可在该 workflow 里改 `cron`）。手动触发时仍默认 **dry run**，取消勾选才会写回分支。 |

### 更新后的 `seeds.json` 在流水线里怎么用（不是单独的 Agent）

没有单独的「Agent 进程」：就是 **`main.py` 同一条流水线**读这个文件。

- 开启 **`semantic_scholar_enabled`** 时，`SemanticScholarSource`（`paperfeeder/sources/paper_sources.py`）会读 `semantic_scholar_seeds_path`（默认 `state/semantic/seeds.json`）。
- 把其中的 ID 作为 **`positivePaperIds` / `negativePaperIds`** 发给 Semantic Scholar 的 **推荐接口**，因此你在邮件里点的 👍/👎（经 `apply_feedback` 写进 seeds 后）会 **影响 S2 推荐来的论文** 是否进入候选池。
- **`memory.json`** 是另一套：记录近期 **见过** 的论文，用于在推荐结果里做去重/抑制（TTL、条数上限等在配置里）。

结论：**seeds 不会用来微调 LLM**，只改变 **S2 推荐请求**；arXiv / 博客 / 手动源不受 seeds 直接影响，但可能与共用的 **memory**「见过即降权」逻辑叠加。

---

## 运行测试

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 其他说明

- `artifacts/`、`llm_filter_debug/` 是运行产物目录，默认被 git 忽略。  
- 若使用 GitHub Actions，会在 **state 分支**上读写 `state/semantic/seeds.json` 和 `memory.json`；说明见上文 **「GitHub Actions、`seeds.json` 和记忆」**。

---

## 和英文 README 的关系

- **中文**：本文档 `README.zh-CN.md`，面向阅读与操作说明。  
- **英文**：[README.md](README.md)，内容与结构保持一致，便于国际协作或 CI 引用。

如有某一段仍看不懂，可以只问那一块（例如「只配邮件、不配 Worker」的最小配置）。
