# Phase 2 — Pilot: `sync_cw_sites_to_hudu` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Migrate the legacy `update_CW_sites_in_Hudu.ps1` job to `hubwise-sync` as `sync_cw_sites_to_hudu`, building the `cw_manage` and `hudu` clients in `hubwise-py-core`, with pure reconciliation logic exhaustively unit-tested and all writes DRY_RUN-gated. Deploy in dry-run; the multi-day parallel-run + cutover is operational (runbook §6), not part of this build.

**Architecture:** Thin-entry/pure-logic split. `hubwise_py_core.cw_manage.CWManageClient` and `hubwise_py_core.hudu.HuduClient` are injectable REST clients (session from `http.build_session`, writes via `guards.WriteGuard.check_write`). The heart is `sync.site_reconcile.plan_actions(...)` — a **pure function** mapping (CW sites, existing Hudu assets) → an ordered list of typed actions (CREATE / UPDATE / ARCHIVE / UNARCHIVE / SKIP_AMBIGUOUS). `function_app.py` wires clients → reconcile → gated apply → structured summary.

**Tech stack:** Python 3.12, `requests`, pytest, ruff. New `hubwise-py-core` minor version (v0.2.0) consumed by `hubwise-sync`.

## Global constraints (verbatim from project)
- Writers default `DRY_RUN=1`, `ALLOW_PROD=0`, enforced via `WriteGuard.check_write()`.
- No secret in code/config/git/logs; `DefaultAzureCredential`/KV references only.
- One structured summary line: `job=... read=... written=... skipped=... errors=...`.
- Verified, pinned field IDs (Outbound Standard): CW type name `Client`, CW site-code custom field **id 15**, Hudu asset layout **id 19**, Hudu field labels as below — all config-driven, defaults pinned, verified live 2026-07-06.
- Upstream-unreachable ⇒ safe skip + `SYNC_DEGRADED` marker, never a false archive.
- One PR per task, green CI, squash-merge; never push to `main`.

## Verified shapes (live, 2026-07-06)
- CW company: `{id, identifier, name, types:[{id,name}], customFields:[{id,value}]}`. Client filter: any `type.name == "Client"`.
- CW site: `{id, name, addressLine1, addressLine2?, phoneNumber, inactiveFlag, customFields:[{id,value}]}`. Site code = customField id 15 value (may be null).
- Hudu company: `GET /api/v1/companies?name=<exact>` → `{companies:[{id,name}]}`.
- Hudu asset: `GET /api/v1/companies/{cid}/assets?asset_layout_id=19` → `{assets:[{id,name,archived,company_id,fields:[...]}]}`; create `POST /api/v1/companies/{cid}/assets`; update `PUT /api/v1/companies/{cid}/assets/{id}`; archive `PUT .../assets/{id}/archive`, unarchive `PUT .../assets/{id}/unarchive` (verify exact archive path against live Hudu before prod flip — dry-run diff will surface it).

## Legacy defects fixed in rewrite
1. No try/catch / no partial-failure isolation → per-company and per-site errors caught, counted, `SYNC_DEGRADED` on upstream failure; one bad company never aborts the run.
2. `ConnectWise_ID` asset field was set from `$CWID` (never assigned = always blank) → set from the CW **site id**.
3. `$address2` leaked across loop iterations (stale when a later site had no line 2) → always computed fresh per site (empty string when absent).
4. Hardcoded layout id 19 / custom field id 15 → config with pinned defaults.
5. Ambiguous-match (>1 Hudu asset same name) silently skipped with only a console line → explicit `SKIP_AMBIGUOUS` action, counted in `skipped`, logged.

---

## Task 1: `cw_manage.CWManageClient` — read companies + sites (TDD)
**Files:** Create `src/hubwise_py_core/cw_manage.py`; Test `tests/test_cw_manage.py` (in hubwise-py-core).
**Interfaces produced:** `CWManageClient(site, company, public_key, private_key, client_id, session=None)`; methods `list_client_companies() -> list[dict]` (paginated, filters `types[].name=="Client"`), `list_active_sites(company_id) -> list[dict]` (filters `inactiveFlag is False`), static `site_code(site) -> str` (customField id 15 value or "").

- [ ] Step 1 — failing tests: auth header is `Basic base64("<company>+<pub>:<priv>")` + `clientId` header; `list_client_companies` filters non-Client out and follows pagination (page/pageSize, stops on short page); `list_active_sites` drops `inactiveFlag=True`; `site_code` returns cf-15 value and "" when null/absent. Inject a fake session (records calls, returns canned pages).
- [ ] Step 2 — run, confirm ImportError/fail.
- [ ] Step 3 — implement over `http.build_session`; read-only (no WriteGuard needed).
- [ ] Step 4 — run green.
- [ ] Step 5 — commit.

## Task 2: `hudu.HuduClient` — companies + assets CRUD + archive (TDD)
**Files:** Create `src/hubwise_py_core/hudu.py`; Test `tests/test_hudu.py`.
**Interfaces produced:** `HuduClient(base_url, api_key, guard, session=None)`; `find_company_id(name) -> int|None`; `list_assets(company_id, layout_id) -> list[dict]`; `create_asset(company_id, layout_id, name, fields) -> dict|None`; `update_asset(company_id, asset_id, layout_id, name, fields) -> dict|None`; `set_archived(company_id, asset_id, archived: bool) -> bool`. All writers call `guard.check_write(...)` and return None/False (no HTTP) when suppressed.

- [ ] Step 1 — failing tests: `x-api-key` header set; `find_company_id` exact-name match (returns None on no/ambiguous match); writers suppressed under default guard (no call made, returns None/False) and issued under open guard; `set_archived` hits archive vs unarchive path per flag.
- [ ] Step 2 — run, fail.
- [ ] Step 3 — implement.
- [ ] Step 4 — green.
- [ ] Step 5 — commit; tag `hubwise-py-core` **v0.2.0**; PR + merge.

## Task 3: `sync.site_reconcile.plan_actions` — pure reconciliation (TDD, in hubwise-sync)
**Files:** Create `src/sync/site_reconcile.py`; Test `tests/test_site_reconcile.py`.
**Interfaces produced:** `SiteAction` dataclass `{op, site_name, asset_id?, fields?}` with `op in {CREATE,UPDATE,ARCHIVE,UNARCHIVE,SKIP_AMBIGUOUS}`; `plan_actions(cw_sites, hudu_assets, company_identifier, site_code_field_getter) -> list[SiteAction]`.

- [ ] Step 1 — failing tests covering: site absent in Hudu → CREATE; exactly one match → UPDATE; >1 match → SKIP_AMBIGUOUS (no create/update); Hudu asset whose name ∉ active CW sites and not archived → ARCHIVE; archived asset whose name ∈ CW sites → UNARCHIVE; fields built correctly incl. ConnectWise_ID=site id and Address_Line_2="" when absent (defect fixes 2+3); no action when already in sync.
- [ ] Step 2–4 — red → implement pure logic → green.
- [ ] Step 5 — commit.

## Task 4: `sync_cw_sites_to_hudu` function + wiring (TDD + thin entry)
**Files:** Create `src/sync/cw_sites_to_hudu.py` (orchestration over injected clients); Test `tests/test_cw_sites_to_hudu.py`; modify `function_app.py` (add timer `0 0 21 * * *`); update `requirements.txt` → `hubwise-py-core@v0.2.0`; add config keys.
**Interfaces produced:** `run_sync(cw, hudu, cfg, env=None) -> None` — iterates client companies, maps each to Hudu company (skip+log if none), plans actions, applies via HuduClient (gated), catches per-company errors (count, continue), emits one `summary(...)` and `SYNC_DEGRADED` alert if any upstream read failed.

- [ ] Step 1 — failing tests with fake CWManageClient + fake HuduClient: happy path counts reads/writes; unmapped Hudu company → skipped+logged, no writes; a company whose CW read raises → error counted, other companies still processed, `SYNC_DEGRADED` emitted; DRY_RUN suppresses all writes (assert fakes' write methods not called through guard) yet still logs intended actions.
- [ ] Step 2–4 — red → implement → green.
- [ ] Step 5 — wire `function_app.py` thin timer; `py_compile`; commit; PR + merge.

## Task 5: Dry-run deploy + verify
- [ ] Bump `hubwise-sync` requirements to `hubwise-py-core@v0.2.0`; add app settings (CW_* KV refs, HUDU_* KV refs, layout/field config) — **these secrets (CW keys, Hudu API key) must exist in `hubwise-ops` first (runbook §3)**; if absent, deploy with the function present but reads will safe-skip + `SYNC_DEGRADED`. Flag which secrets are missing.
- [ ] Deploy via the (now-proven) OIDC pipeline; confirm `sync_cw_sites_to_hudu` indexes alongside `health_check_ping`.
- [ ] Trigger manually; confirm DRY_RUN summary line shows intended writes with `written=0` (suppressed) and a readable diff of would-be actions in the log.
- [ ] **Gate (operational, not this build):** 3–5 day dry-run diff vs. legacy output → flip `DRY_RUN=0`/`ALLOW_PROD=1` → 7 clean days → disable legacy #12. Per runbook §6.

## Self-review
Covers all legacy behavior (client filter, active-site filter, create/update/ambiguous-skip, archive/unarchive reconciliation) + the 5 defect fixes + DRY_RUN gating + failure isolation + structured logging. Secrets dependency (runbook §3) is the only external blocker for the live dry-run; the build + tests are fully unblocked.
