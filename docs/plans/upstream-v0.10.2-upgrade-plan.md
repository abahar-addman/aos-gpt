# Upstream Open WebUI v0.10.2 Upgrade Plan

> **Status:** Draft for review — supersedes `upstream-v0.9.5-upgrade-plan.md` (target moved 0.9.5 → 0.10.2).
> **Derived from:** read-only 6-way delta analysis on branch `v10-update` (HEAD `86ce1217e`), 2026-07-13.
> **Goal:** Bring the Edison AI fork (currently **v0.8.3**) up to upstream **v0.10.2** ("c10") without silently breaking the custom LangGraph agent pipeline, branding, Keycloak SSO, Datadog logging, Azure storage, or OlmOCR.
> **Refs:** BASE `v0.8.3` = `b8112d72b` (== merge-base of HEAD and v0.10.2). TARGET `v0.10.2` = `ecd48e2f7`. FORK = `86ce1217e`.

---

## 0. Honest framing

**We cannot avoid merge conflicts.** The fork touched 386 code files; upstream touched 757; **307 of them overlap**. Conflicts are guaranteed. What we *can* do is make them tractable and prevent **breaking changes** — silent behavior regressions in the agent pipeline, SSO, logging, storage, and OCR — through disciplined hand-merges and end-to-end verification. This plan optimizes for "no silent regressions," not "no conflicts."

### 0b. Actual dry-run merge probe (2026-07-13, `git merge --no-commit v0.10.2`, aborted)

**Real conflict count is 191, not 307** — git's 3-way merge auto-resolved ~116 of the overlapping files (fork and upstream edited non-adjacent regions). Breakdown:

| Category | Count | Resolution |
|---|---|---|
| `UU` both-modified content conflicts | 115 | hand-merge / classify (see below) |
| `DU` fork-deleted, upstream-modified | 70 | **60 = pruned i18n locales** + 12 project-meta/`s3vector.py` → **keep deleted** (`git rm`) |
| `UD` fork-modified, upstream-deleted | 6 | per-file keep-ours vs accept-deletion |
| `package-lock.json` (643 "hunks") | 1 (in UU) | **not a hand-merge — regenerate** via `bun install` |

- **Best news:** the top render-pipeline files **auto-merged clean** — `src/lib/utils/index.ts`, `ContentRenderer.svelte`, and `retrieval/loaders/olmocr.py` had **zero** conflicts. Hot zones that did conflict are all small: `main.py` 10 hunks, `config.py` 6, `oauth.py` 6, `middleware.py` 5, `logger.py` 5, `env.py` 4, `storage/provider.py` 4, `ResponseMessage.svelte` 3, `auth/+page.svelte` 3, `CodeBlock.svelte` 1, `marked/extension.ts` 1, `loaders/main.py` 1.
- **⚠ Low conflict count ≠ low risk.** The async-plugin and structured-output changes mostly do **not** surface as conflicts — `index.ts` merging clean is a *warning*: it merged, but the data shape it processes changed underneath. The real cost is the post-merge semantic adaptation (§8 step 4), not conflict-marker resolution.
- **~129 non-i18n content conflicts** need a resolution decision. A `-w` (whitespace-ignoring) test did **not** classify any as pure-formatting, because the fork carries a repo-wide `ruff`/Prettier style pass (quote/trailing-comma changes survive `-w`). A **content-level classification pass** is needed to split these into take-upstream (style-only collisions) vs genuine hand-merge.

**`UD` — upstream deleted a file the fork modified (decide keep-ours vs accept-deletion):** `.github/workflows/deploy-to-hf-spaces.yml` (**keep ours** — fork's deploy), `test/apps/webui/storage/test_provider.py`, `src/lib/components/admin/Settings/Models/ConfigureModelsModal.svelte`, `src/lib/components/admin/Settings/Tools.svelte`, `chat/Settings/Personalization/AddMemoryModal.svelte`, `EditMemoryModal.svelte` (4 UI components upstream removed — likely accept-deletion unless fork depends on them), plus fork-modified helper scripts (`run.sh`, `run-compose.sh`, `run-ollama-docker.sh`, `confirm_remove.sh`, `update_ollama_models.sh`, `docs/*`) upstream removed.

**`DU` keep-deleted (non-i18n):** `s3vector.py`, `contribution_stats.py`, `README.md`, `LICENSE`, `CONTRIBUTOR_LICENSE_AGREEMENT`, `docs/SECURITY.md`, `docker-compose.playwright.yaml`, 5× `.github/*`.

---

## 1. Current state (facts, v0.10.2 target)

| Item | v0.9.5 plan (old) | **v0.10.2 (this plan)** |
|---|---|---|
| Fork base | v0.8.3 | **v0.8.3** (unchanged; 0.9.5 upgrade never executed) |
| Upstream changed **code** files | 668 | **757** (+13%) |
| Fork changed **code** files | 136 | **386** (~2.8×; OCR, SSO, agent-pipe, styling landed since) |
| **Overlap (conflict surface)** | 109 | **307** (~2.8×) |
| Brand-new upstream files | 88 | **143** (128 code: 66 new `src/lib/components`, 14 migrations, `events.py`, client-side SQLite `sql.js`) |
| New DB migrations | 8 | **14** |
| Delete/modify (resurrection) | — | **70** (58 = pruned i18n locales; only **1** real code file: `s3vector.py`) |

**Takeaway:** the merge cost roughly **tripled vs the 0.9.5 estimate**, driven almost entirely by *fork* growth, not upstream growth. Collision density is severe.

---

## 2. Top breaking changes (fork-impacting), in priority order

| # | Change (version) | Why it hits *this* fork |
|---|---|---|
| **1** | **Plugin async migration (0.9.0)** — Tools/Functions/Pipelines must move to async signatures; sync DB calls inside plugins break; backend outlet-filter execution reworked. | **Highest.** The custom `v3_agent_pipe` LangGraph pipe + any filters must be ported to async. Outlet-filter change affects the pipeline's post-processing / tag-stripping. Official 0.9.0 plugin migration guide exists. |
| **2** | **Structured client-side output (0.10.0/0.10.2)** — reasoning, tool calls, and server-side tool steps are **no longer flattened into `message.content` on the server**; assistant messages stored as structured output. | **Directly collides with the fork's render pipeline.** `processResponseContent()` / `extractAgentActivity()` / client section-splitting / Plotly-Mermaid detection all operate on `message.content` strings and SSE `delta.content`. Must re-verify the agent pipe still accumulates into `message.content` and that tag-stripping (`<thinking>`, `<plan>`, `<chart_plan>`, `[SYSTEM INSTRUCTION]`, details) still fires. |
| **3** | **Config table reshaped to per-key rows (0.10.x, migration `3ff2c63645b8`)** — single JSON `config` row → per-key `config(key,value,updated_at)` table. | The fork's documented pattern of **overriding PersistentConfig (Keycloak OIDC) via direct SQL on the old single-JSON `config` table** no longer applies. SSO DB overrides must be rewritten for the per-key layout. |
| **4** | **Signout GET → POST (0.9.5)** | Root-domain Keycloak logout + cookie→localStorage bridge: any custom logout call must switch to POST or logout breaks. |
| **5** | **asyncpg → psycopg v3 (0.9.2)** — `psycopg[binary]==3.3.4`; asyncpg-specific connection params invalid; Windows needs non-Proactor loop (fixed 0.9.5). | Postgres `DATABASE_URL` / `PGVECTOR_DB_URL` params may need adjustment (fork uses native libpq strings, so likely fine — verify). |
| **6** | **Native tool calling is default (0.10.0)** — old path renamed "Legacy," now explicit opt-out. | If the pipe/tools relied on the previous path, behavior changes silently. Set "Legacy" in default model params if needed. |
| **7** | **`AIOHTTP_CLIENT_ALLOW_REDIRECTS` blocks 3xx by default (0.9.5, SSRF hardening)** | Outbound tool-server/webhook calls that rely on redirects break unless re-enabled. |
| **8** | **Pyodide sandboxed in opaque-origin iframe (0.10.0)** — can't reach same-origin endpoints/cookies. | Breaks any code-interpreter usage expecting same-origin callbacks. |
| **9** | **Message virtualization → CSS `content-visibility` (0.9.2)** — custom JS culling/scroll system removed. | Any fork scroll/anchoring tweaks on the message list no longer have hooks. |
| **10** | **Vector collection-name validation + cross-user access enforcement (0.9.6/0.10.0)** | RAG/agent code referencing collections by custom/computed names or raw IDs may be rejected. |
| **11** | **OpenAI catch-all passthrough now opt-in (0.9.0)** — `ENABLE_OPENAI_API_PASSTHROUGH=true`. | Any feature relying on the passthrough proxy stops until the flag is set. |

**Env-var deltas to reconcile** (non-exhaustive): `ENABLE_RAG_LOCAL_WEB_FETCH`→`ENABLE_LOCAL_WEB_FETCH`, `YOUCOM_API_KEY`→`YDC_API_KEY` (both keep aliases); new `AIOHTTP_CLIENT_ALLOW_REDIRECTS`, `IFRAME_CSP`, `ENABLE_OPENAI_API_PASSTHROUGH`, `OAUTH_AUTO_REDIRECT` (0.9.6, single-SSO auto-redirect — useful for Keycloak), `CUSTOM_API_KEY_HEADER` (reverse-proxy Authorization), automation/calendar tunables. `LOG_FORMAT=json` (already used by the fork's Datadog stdout) is unchanged.

---

## 3. Database migrations (14 new, single linear chain)

Chain (apply in order): `a3dd5bedd151 → d4e5f6a7b8c9 → b7c8d9e0f1a2 → e1f2a3b4c5d6 → c1d2e3f4a5b6 → 56359461a091 → 4de81c2a3af1 → a0b1c2d3e4f5 → 3c9b0ca343fd → 461111b60977 → 3ff2c63645b8 → 4c5ce3d2f27f → 7b3f2a9c1d4e → 42e2978c7933`. **Sole head at v0.10.2 = `42e2978c7933`.** All are idempotency-guarded (safe to re-run). **11 of 14 are irreversible** (downgrade drops columns/tables or is a no-op).

**Gate these carefully in production (long locks / destructive / correctness-critical):**

| Migration | Risk |
|---|---|
| `461111b60977` (legacy Peewee PK hardening) | **Rebuilds core tables** (chat/file/user/memory) via `batch_alter` — on SQLite = full table rewrites + long locks. Downgrade is a **no-op** (non-reversible). |
| `c1d2e3f4a5b6` (shared-chat rework) | **Destructive**: permanently DELETEs phantom `shared-*` chat + `chat_message` rows; downgrade cannot restore deleted messages. |
| `b7c8d9e0f1a2` (chat.last_read_at) | **Full-table UPDATE** backfill over every chat row. |
| `3ff2c63645b8` (config → per-key rows) | Rewrites the **entire application config**; flatten heuristic + key rewrites could reshape custom keys. Correctness-critical (see breaking change #3). Reversible via preserved `config_old`. |
| `3c9b0ca343fd` (knowledge directories) | SQLite table rewrite of `knowledge_file` when adding the FK column. |

> **Non-negotiable:** full DB backup before applying, validate on a **restored staging copy first**, and take **downtime** — upstream states rolling/partial updates across workers are unsupported and downgrade after migration is unsupported.

---

## 4. Dependencies, driver & build

- **Async DB overhaul:** `peewee` + `peewee-migrate` **removed**; `sqlalchemy` → `sqlalchemy[asyncio]==2.0.50`; added `psycopg[binary]==3.3.4` (async PG v3) + `aiosqlite==0.22.1`. Sync `psycopg2-binary` retained (2.9.12). *(This is what forces the plugin async migration — breaking change #1.)*
- **Fork pin conflicts:**
  - `torch<=2.9.1` — **converged**, no conflict (upstream's own Dockerfile now also pins it).
  - `sentence-transformers==5.2.2` — **real conflict.** Upstream bumps to **5.5.1** (+ `transformers` 5.1.0→5.5.4). If OlmOCR/VLM embedding stability needs 5.2.2, **re-pin after merging** upstream `requirements.txt`, or the upgrade silently pulls 5.5.1. → decision + test.
- **Frontend breaking bumps:** `bits-ui ^0.21 → ^2.0` (headless-UI API rewrite — widespread import/prop breakage), `uuid 9→11` (ESM-only), `svelte-confetti 1→2`, TipTap bubble/floating-menu 2→3. New deps: `@xterm/*` (in-app terminal), `shiki`, `sql.js` (client SQLite WASM), `jszip`. **Svelte 5 / Tailwind 4 / Vite 5 unchanged** (fork already there).
- **Upstream Dockerfile additions:** apt `ca-certificates` + `libmariadb-dev`; `ENV UV_LINK_MODE=copy` (arm64 cross-build fix); base image de-pinned to floating `python:3.11-slim-bookworm`. Our `docker/Dockerfile` is fork-owned (incl. the `HF_HUB_DISABLE_XET=1` fix) — reconcile manually, don't take-theirs.
- **Tooling:** `black` → `ruff` (dev-only; `format:backend` script changes).
- **Python floor unchanged:** `>=3.11,<3.13`.

---

## 5. Hot-zone files — hand-merge, NEVER take-theirs

**Good news:** all 14 hot-zone files **still exist at v0.10.2 at their original paths, none renamed** → every conflict is a normal in-file 3-way merge (no delete/modify rename traps).

| File | Upstream churn (add/del) | Fork logic at stake |
|---|---|---|
| `backend/open_webui/config.py` | +2350/-3333 (**~5.7k**) | PersistentConfig (SSO/OIDC, sub-path removal, OlmOCR) |
| `backend/open_webui/utils/middleware.py` | +3106/-2277 (**~5.4k**) | Tag-stripping on streaming path; near-total upstream rewrite. **Tent-pole merge.** |
| `backend/open_webui/main.py` | +1789/-1687 (**~3.5k**) | App wiring, sub-path→root revert, OAuth, route registration |
| `backend/open_webui/env.py` | +739/-581 (**~1.3k**) | Datadog env (`LOG_FORMAT`/`DD_*`), OlmOCR tunables |
| `backend/open_webui/retrieval/loaders/main.py` | +489/-221 (**~710**) | OlmOCR loader dispatch |
| `src/lib/utils/index.ts` | +548/-109 (**~657**) | `processResponseContent`, `extractAgentActivity`, Plotly/Mermaid detect — **core client render pipeline** |
| `src/lib/components/chat/Messages/ContentRenderer.svelte` | +189/-86 | `displayContent`→ContentRenderer→Markdown |
| `src/lib/components/chat/Messages/ResponseMessage.svelte` | +171/-95 | Agent-activity (Thinking/Plan/Review) section |
| `backend/open_webui/storage/provider.py` | +75/-100 | Azure storage |
| `backend/open_webui/utils/telemetry/metrics.py` | +121/-75 | APM/ddtrace removal — verify telemetry not re-enabled |
| `backend/open_webui/utils/logger.py` | +102/-53 | Datadog structured-stdout setup |
| `src/routes/auth/+page.svelte` | +30/-4 (medium) | **Functionally sensitive** — OAuth cookie→localStorage bridge / Keycloak; low volume can still silently break login |
| `src/lib/components/chat/Messages/CodeBlock.svelte` | +65/-44 | Plotly/Mermaid auto-detection + rendering |
| `src/lib/utils/marked/extension.ts` | **+1/-1 (trivial)** | Details tokenizer. HIGH only by render-path rule — **verify only, don't over-invest.** |

**Merge order suggestion:** (a) mechanical branding re-applies across the ~290 non-hot-zone conflicts first; (b) then the three backend giants (config/middleware/main); (c) then env/loaders (OlmOCR + Datadog); (d) then the frontend render cluster (index.ts, ContentRenderer, ResponseMessage, CodeBlock) as a unit, verifying Plotly/Mermaid/agent-activity end-to-end; (e) SSO (`auth/+page.svelte`, `oauth.py`) with care.

---

## 6. Fork customizations to protect (incl. NEW since the old plan)

Protected subsystems: **branding** (app.html, constants, static assets in *both* `backend/.../static/static/` and top-level `static/`), **SSO/OAuth** (oauth.py, auths.py, auth.py, scim.py, auth/+page.svelte), **agent-pipeline/langgraph** (`utils/langgraph/*`, chat.py, middleware.py, pipelines.py, tasks.py), **chat-render** (index.ts, marked/extension.ts, CodeBlock/ResponseMessage/ContentRenderer, MarkdownTokens, ToolCallDisplay), **Datadog** (env.py, logger.py, telemetry/metrics.py), **Azure storage** (provider.py, retrieval/web/azure.py, files.py), **OCR** (olmocr.py, loaders/main.py, retrieval/utils.py, routers/retrieval.py, knowledge.py), **docker/deploy** (Dockerfile*, docker-compose*, start.sh, .env.example), **config/env** (config.py, main.py, __init__.py, requirements.txt).

**NEW since the old plan (a3e51be87) — not yet protected by the 0.9.5 doc:**
- **OlmOCR text-layer fast-path** rewrite of `retrieval/loaders/olmocr.py` (+195 lines: `use_text_layer`/`min_text_layer_chars`, `_build_page_plan`/`_build_documents`, sync+async text-layer-vs-OCR routing). The old plan only mentioned *registering* olmocr in `loaders/main.py`, not protecting `olmocr.py` itself.
- **Server-side initials-avatar feature** spanning `utils/misc.py` (`get_initials`, `generate_initials_image_data_url`), `utils/oauth.py` (`_resolve_user_name` Keycloak claim fallback + initials avatar on OAuth signup), `routers/users.py` (on-the-fly initials for legacy `/user.png`), and one-off `scripts/backfill_user_avatars.py`.
- **`.env.example`** (+44 lines).
- `main.py`/`config.py` OCR customizations **predate** the old plan (already covered by its "custom config" line).
- The ~250 changed `.svelte` files since the plan are **overwhelmingly Prettier reformatting**, not new logic — no new protection entries needed (already fork-owned/branded).

---

## 7. Intentional deletions & resurrection (70 delete/modify conflicts)

- **58 = pruned i18n locales** (`src/lib/i18n/locales/<lang>/translation.json`, ~85 langs removed, only `en-US` kept). Upstream keeps updating them → **one bulk decision: re-delete after merge (keep English-only, matches fork intent) or accept them back.** Recommend re-delete.
- **1 real code file:** `backend/open_webui/retrieval/vector/dbs/s3vector.py` — fork deleted it, upstream still modifies it (~1.1k churn). Confirm it stays deleted, resolve as "keep deleted."
- **11 project-meta** (README, LICENSE, CLA, `docs/SECURITY.md`, 5× `.github/*`, `docker-compose.playwright.yaml`, `contribution_stats.py`) — keep deleted.

---

## 8. Recommended execution strategy

**Merge, not rebase** (a fork with 20+ commits and 80% collision would replay conflicts on every commit under rebase).

**Recommended: single merge to `v0.10.2`, then adapt as follow-up commits** — cleanest total effort, separates mechanical conflict-resolution from semantic work:

1. **Prep (safe, no code change):** confirm working tree clean; `git checkout -b upgrade/v0.10.2 v10-update`; **full DB backup** (Postgres `edison` + vectordb) restored to a staging DB; `git config rerere.enabled true` (auto-reuses conflict resolutions); push the current prod image tag for rollback.
2. **Dry-run conflict list:** `git merge --no-commit --no-ff v0.10.2` → `git diff --name-only --diff-filter=U` (expect ~307). `git merge --abort` after inspecting.
3. **Merge & resolve to a *compiling* tree:** branding re-applies → backend giants → env/OCR → frontend render cluster → SSO (order per §5). Do **not** yet chase runtime behavior; goal is "it builds."
4. **Semantic adaptations as separate commits** (each verified): (a) port `v3_agent_pipe` + filters to **async** signatures; (b) reconcile the **structured-output** render path (`message.content` accumulation, tag-stripping, Plotly/Mermaid); (c) **signout POST**; (d) **config per-key SSO override** rewrite; (e) re-pin `sentence-transformers` if needed; (f) env-var reconciliation.
5. **Migrations:** apply the 14 against the **staging** DB, validate psycopg v3 + `DATABASE_URL`, then verify on a copy of prod data.
6. **Bump** `package.json`/`__init__.py` version → `0.10.2`, verify About surfacing.

**Alternative (more conservative): staged merge** `→ v0.9.6` (async foundation + driver + config reshape + SSO POST) as a bootable checkpoint, then `→ v0.10.2` (structured output + native tools + Pyodide sandbox + bits-ui 2.0). Trade-off: bootable checkpoints, but you re-resolve the same hot files (config/middleware/main) **twice**. Choose this if isolating the async gate from the structured-output gate is worth the duplicate conflict work.

---

## 9. Verification / acceptance (before promoting)

- [ ] `bun run build` + backend boot clean (both `edison-ai` and pipelines containers); `LOG_FORMAT`/Datadog intact, telemetry **not** re-enabled.
- [ ] **Agent pipeline (`v3_agent_pipe`)** streams under async; Plotly, Mermaid, `<details>` Thinking/Plan/Review render; internal tags stripped **client- and server-side**; content still accumulates into `message.content` under the new structured-output model.
- [ ] SSO (Keycloak) login via cookie→localStorage bridge + **POST** logout works; PersistentConfig OIDC override applies under the **per-key config table**.
- [ ] OlmOCR: text-layer fast-path + VLM OCR both route correctly; embedding model pin verified.
- [ ] RAG / web search / Azure blob upload+retrieve; vector collections not rejected by new name validation.
- [ ] DB: 14 migrations apply cleanly on a prod-data copy; no data loss on legacy chats; config reshape preserved custom keys.
- [ ] Branding: zero `aos-gpt`/`AOS-GPT` reintroduced (`git grep -i aos-gpt`); favicons/logo/splash correct.
- [ ] `sentence-transformers` at the intended pin; `torch<=2.9.1` honored.

---

## 10. Rollback

- Work isolated on `upgrade/v0.10.2`; `v10-update` untouched.
- DB: restore from the pre-upgrade backup (migrations are forward-only / not auto-reversible; 11/14 irreversible, and `c1d2e3f4a5b6` deletes data).
- Keep the pre-upgrade `addmangroup/edison-ai:<prev>` image pushed so prod reverts by tag.

---

## 11. Open decisions (need product/infra call)

1. **Target:** v0.10.2 (latest) vs v0.10.0 (series base). *(analysis assumes v0.10.2)*
2. **Strategy:** single-merge-then-adapt (recommended) vs staged (→0.9.6→0.10.2).
3. **`sentence-transformers`:** hold at 5.2.2 for OlmOCR, or adopt upstream 5.5.1? (needs a quick OCR regression check).
4. **New features** (automations, calendars, shared chats, KB directories, in-app terminal): keep enabled as they arrive, or disable via flags to reduce surface?
5. **i18n:** keep English-only (re-delete locales) vs accept upstream locales back.
6. **Legacy tool-calling:** set default model params to "Legacy" to preserve pre-0.10 behavior, or adopt native-default?

---

## Appendix — reproduce the numbers
```
git merge-base HEAD v0.10.2                                   # -> v0.8.3 (b8112d72b)
git diff --name-only v0.8.3 v0.10.2 | grep -E '\.(py|svelte|ts|js)$' | wc -l   # 757 upstream
git diff --name-only v0.8.3 HEAD    | grep -E '\.(py|svelte|ts|js)$' | wc -l   # 386 fork
comm -12 <(sort up) <(sort fork)                              # 307 overlap
git diff --name-only --diff-filter=A v0.8.3 v0.10.2 | grep migrations | wc -l  # 14 migrations
```
