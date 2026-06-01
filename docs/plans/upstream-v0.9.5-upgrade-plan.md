# Upstream Open WebUI v0.9.5 Upgrade Plan

> **Status:** Draft for review — execute next session after committing current work and branching.
> **Author:** Generated from read-only analysis on the `OCR` branch (HEAD `a3e51be87`).
> **Goal:** Pull in upstream Open WebUI changes (currently at **v0.9.5**) into the Edison AI fork (currently **v0.8.3**) without breaking the custom agent pipeline, branding, SSO, Datadog, or Azure storage.

---

## 1. Current state (facts established)

| Item | Value |
|---|---|
| Fork base version | **v0.8.3** (`package.json` version `0.8.3`; merge-base with upstream = the v0.8.3 tag) |
| Upstream target | **v0.9.5** (tags v0.9.0–v0.9.5 already fetched on `upstream` remote) |
| Upstream code files changed 0.8.3→0.9.5 | **668** (`.py/.svelte/.ts/.js`) |
| Fork code files changed 0.8.3→HEAD | **136** |
| Overlap (conflict surface) | **109** files |
| Brand-new upstream files (absent in fork) | **88** |
| New DB migrations 0.8.3→0.9.5 | **8** |

`upstream` remote is already configured: `https://github.com/open-webui/open-webui.git`.

---

## 2. Hard blockers — why we cannot cherry-pick the big features

The headline 0.9.x features are coupled to **database migrations** and normalized-table code spanning many files. They must come as a version upgrade, not à-la-carte:

| Feature | Required migration |
|---|---|
| Scheduled automations | `d4e5f6a7b8c9_add_automation_tables.py` |
| Calendars | `56359461a091_add_calendar_tables.py` |
| Shared chats (proper) | `c1d2e3f4a5b6_add_shared_chat_table.py` |
| Faster history / tasks & summary | `a3dd5bedd151_add_tasks_and_summary_to_chat.py`, `b7c8d9e0f1a2_add_last_read_at_to_chat.py` |
| Per-user note pinning | `4de81c2a3af1_add_pinned_note_table.py`, `e1f2a3b4c5d6_add_is_pinned_to_note.py` |
| Faster memory queries | `a0b1c2d3e4f5_add_memory_user_id_index.py` |

**Operational breaking changes to plan for:**
- **DB schema migrations** — back up DB first; upstream states rolling updates are *not* supported (all instances must update simultaneously).
- **Async DB driver swap (0.9.2): `asyncpg` → `psycopg` v3.** Verify `DATABASE_URL` / `PGVECTOR_DB_URL` connection strings still parse (we use `postgres://…@be.local.aos:5432/edison`). psycopg v3 supports native libpq strings; asyncpg-specific params would need adjustment.
- **Signout endpoint GET → POST (0.9.5).** Any custom client/integration calling logout must update.

---

## 3. Prerequisites (do before starting — your action)

1. Commit the current working tree on `OCR` (the rebrand + docker-compose split are uncommitted).
2. Create a clean integration branch off the committed state:
   ```
   git checkout -b upgrade/v0.9.5 OCR
   ```
3. Take a **full database backup** (Postgres dump of the `edison` DB + `vectordb`).
4. Confirm `upstream` tags are current: `git fetch upstream --tags`.

---

## 4. Phase 1 — Tier-1 security hardening (low risk, do first)

These apply to existing 0.8.3 functionality and are mostly localized. Apply surgically; re-apply Edison branding where the file is also branded.

### 4a. Safe — files the fork does NOT customize (drop-in)
| Fix | File(s) | Notes |
|---|---|---|
| URL-parser SSRF bypass (reject `\`, tab, CR, LF) | `backend/open_webui/retrieval/web/utils.py` (`validate_url`), **new** `backend/open_webui/utils/validate.py` | core hardening |
| Profile-image MIME allowlist + `nosniff` | `backend/open_webui/routers/users.py` | adds `PROFILE_IMAGE_ALLOWED_MIME_TYPES` |
| Tool source-code update authorization | `backend/open_webui/routers/tools.py` | requires `workspace.tools*` perm |
| Model `params` stripping for read-only users | `backend/open_webui/routers/models.py` | hides system prompts |
| Feedback `user_id` spoofing fix | `backend/open_webui/models/feedbacks.py` | mass-assignment guard |
| Brotli CVE-2025-6176 bump | `pyproject.toml` / `requirements.txt` | dependency only |

### 4b. Needs hand-merge — fix lands in a fork-customized file
| Fix | File (fork-customized) | Why careful |
|---|---|---|
| Image-generation URL validation | `backend/open_webui/routers/images.py` | fork branding/logic present |
| Redirect-based SSRF (`AIOHTTP_CLIENT_ALLOW_REDIRECTS`) | `utils/middleware.py`, `retrieval/utils.py`, `retrieval/web/*`, `utils/oauth.py` | spans the tag-stripping + branded web files |
| Image-URL redirect SSRF (base64 conversion) | `backend/open_webui/utils/middleware.py` | **our tag-stripping lives here** |
| Iframe CSP (`IFRAME_CSP`) | **new** `src/lib/utils/csp.ts`, `FullHeightIframe.svelte` (customized), `config.py`/`env.py` (customized) | env/config are Datadog hot-zone |

> Permission fixes for **skills / calendars / channel-pin / shared-chat** are **moot at 0.8.3** (features absent). Skip until Phase 2.

**Acceptance for Phase 1:** app boots, web search + RAG still work, image gen works, login/logout works, no regression in agent-pipeline rendering.

---

## 5. Phase 2 — Full upgrade to v0.9.5 (the real path)

Cherry-picking features is *more* error-prone than a controlled merge given 109/136 overlap. Recommended sequence:

### 5a. Dry-run to get the precise conflict list
On the `upgrade/v0.9.5` branch:
```
git merge --no-commit --no-ff v0.9.5   # or rebase; abort with: git merge --abort
git diff --name-only --diff-filter=U    # exact conflicts
```
Expect ~109 conflicts; the large majority are trivial **branding re-applies** (`AOS-GPT`/`aos-gpt` → `Edison AI`/`edison-ai`). Resolve those mechanically first.

### 5b. Hot-zone files — hand-merge, NEVER take-theirs (preserve custom logic)
These hold the fork's "secret sauce" AND were heavily changed upstream:

| Custom capability | File | Upstream collision |
|---|---|---|
| `processResponseContent` / `extractAgentActivity` | `src/lib/utils/index.ts` | markdown render changes |
| Internal tag stripping | `backend/open_webui/utils/middleware.py` | SSRF + reasoning-leak fixes |
| Plotly/Mermaid auto-detection | `src/lib/components/chat/Messages/CodeBlock.svelte` | rendering changes |
| Agent-activity (`<details>` Thinking/Plan/Review) | `src/lib/components/chat/Messages/ResponseMessage.svelte` | edit/continue response feature |
| `<details>` tokenizer | `src/lib/utils/marked/extension.ts` | final-flush markdown fix |
| Datadog logging | `backend/open_webui/utils/logger.py`, `env.py`, `utils/telemetry/metrics.py` | telemetry gauge rewrite (0.9.2) |
| SSO | `src/routes/auth/+page.svelte` | 336 custom lines + branding |
| Azure storage | `backend/open_webui/storage/provider.py` | storage path changes |
| Custom config | `backend/open_webui/config.py`, `backend/open_webui/main.py` | many upstream additions |

> **Highest-risk area:** 0.9.2 replaced JS message virtualization with CSS `content-visibility: auto` and reworked streaming markdown — this lands directly on the chat-render pipeline (`utils/index.ts`, `CodeBlock.svelte`, `ResponseMessage.svelte`, `marked/extension.ts`, `ContentRenderer.svelte`). Test agent-pipeline rendering (charts, thinking blocks, tag stripping) exhaustively after merge.

### 5c. Intentional fork deletions — do NOT let merge resurrect them
The fork deleted these; keep them deleted unless we decide otherwise:
- `backend/open_webui/retrieval/vector/dbs/s3vector.py`
- `contribution_stats.py`
- `src/lib/components/chat/Settings/General.svelte`
- `src/lib/components/admin/Evaluations/Feedbacks.svelte`
- related test files

### 5d. New self-contained additions to wire up (optional, post-merge)
~88 new files; notable opt-ins (each needs an edit to a customized dispatcher):
- OCR/extraction: PaddleOCR-vl, olmocr → register in `retrieval/loaders/main.py` (customized)
- Firecrawl v2, Brave LLM-Context search → `retrieval/web` factory (customized)

### 5e. Migrations & driver
1. Apply the 8 Alembic migrations against the **backup-restored staging DB** first.
2. Validate psycopg v3 with our `DATABASE_URL` / `PGVECTOR_DB_URL`.
3. Bump version in `package.json` → `0.9.5` (and verify `VERSION` surfacing in About/`__init__.py`).

---

## 6. Verification / acceptance criteria (before promoting)

- [ ] App boots (both `edison-ai` and pipelines containers) with `LOG_FORMAT`/Datadog intact.
- [ ] SSO (Keycloak) login + **POST** logout works.
- [ ] Agent pipeline (`v3_agent_pipe`) streams; Plotly charts, Mermaid, and `<details>` Thinking/Plan/Review render; internal tags (`<thinking>`, `<chart_plan>`, `<plan>`, `[SYSTEM INSTRUCTION]`) stripped client- and server-side.
- [ ] RAG / web search / Azure blob storage upload+retrieve work.
- [ ] Datadog: `edison-ai` and `aos-pipelines` services report; `dd.trace_id` correlation intact.
- [ ] Branding: zero `AOS-GPT`/`aos-gpt` reintroduced (`git grep -i aos-gpt`).
- [ ] DB migrations applied cleanly on a copy; no data loss on legacy chats.

---

## 7. Rollback

- Branch work is isolated on `upgrade/v0.9.5`; `OCR` untouched.
- DB: restore from the Phase 3 backup (schema is forward-migrated and **not** auto-reversible).
- Keep the pre-upgrade image tag (`addmangroup/edison-ai:<prev>`) pushed so prod can revert by tag.

---

## 8. Open decisions for next session

1. **Scope:** Phase 1 security-only now, or commit to the full v0.9.5 upgrade?
2. **Driver:** confirm staging Postgres works with psycopg v3 before touching prod.
3. **Features to adopt:** which 0.9.x features do we actually want (automations? calendars? shared chats?) — drives how much migration risk we accept.
4. **s3vector / deleted files:** confirm they stay deleted.

---

## Appendix A — How the numbers were derived (reproducible)
```
git merge-base HEAD v0.9.5                       # -> v0.8.3 commit
git diff --name-only v0.8.3 v0.9.5 | grep -E '\.(py|svelte|ts|js)$'   # upstream changed (668)
git diff --name-only v0.8.3 HEAD  | grep -E '\.(py|svelte|ts|js)$'    # fork changed (136)
comm -12 <upstream> <fork>                        # conflict overlap (109)
git diff --name-only --diff-filter=A v0.8.3 v0.9.5 | grep migrations   # 8 migrations
```
