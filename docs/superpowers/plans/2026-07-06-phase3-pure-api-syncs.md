# Phase 3 — Batch: remaining pure-API sync jobs

> REQUIRED SUB-SKILL: superpowers:test-driven-development. Checkbox steps.

**Goal:** Migrate the remaining pure-API (non-NSM) sync jobs into `hubwise-sync`, one function + one PR each, following the proven pilot pattern (client + pure logic + gated orchestration, TDD → dry-run → controlled write → attended flip). Gate: 7 of 10 sync functions live.

**Functions (transition plan §5, Phase-3 set):**
| # | Function | Reads | Writes | New client needed? |
|---|---|---|---|---|
| 11 | `sync_primary_contacts_to_hudu` | CW contacts | Hudu **MagicDash** | none (cw_manage + hudu) — **BUILD FIRST** |
| 10 | `sync_msp360_to_hudu` | MSP360 | Hudu asset | `msp360` client |
| 7 | `sync_rds_servers_to_cw` | CW Automate | CW Manage configs | `cw_automate` client + cw_manage write |
| 14 | `sync_sonicwall_expirations_to_cw` | MySonicWall | CW Manage configs | `mysonicwall` client + cw_manage write |
| 3 | `report_timezest_stats` | TimeZest, CW | Teams card | `timezest` + `teams` clients |
| 5 | `update_hwti_blocklist` | AlienVault OTX | GitHub `hubwisetech/public` | **HELD** pending D-12e blocklist-consumer verification (runbook §5.2b) — do NOT build until confirmed |

**Global constraints:** unchanged from Phase 1/2 — WriteGuard dual-gate on every writer; verified/pinned field+type IDs; `job=… read=… written=… skipped=… errors=…` summary + `SYNC_DEGRADED`; per-item failure isolation; one PR/function, green CI, squash-merge; controlled single-write before each live flip.

**Verified live shapes (2026-07-06):**
- CW contact: `{id, firstName, lastName, company:{id,name}, types:[{id,name}], inactiveFlag}`. Type filter is client-side (CW can't server-filter `types/name`). Relevant type names: `HubWise Primary Contact`, `Approver`.
- Hudu MagicDash: `POST /api/v1/magic_dash` upserts by (title, company_name) — body `{title, company_name, message, content(html), shade, icon}`.

---

## Function #11 — `sync_primary_contacts_to_hudu` (build first)

Legacy `primary_contact_MagicDash_updater.ps1`: for each non-deleted Client company, build a MagicDash titled "Primary Contact and Approvers" listing the company's `HubWise Primary Contact`(s) and, if any, `Approver`(s); skip companies with no Hudu match. Defects to fix: `out-string` newline pollution in names (→ clean "First Last"); no error handling/dry-run gating; only counts primaries for the "Multiple Primary Contacts" message.

### Task 1: `cw_manage.CWManageClient.list_contacts_with_types(type_names)` (TDD, py-core)
- [ ] Failing test: paginates `/company/contacts`, returns only contacts whose `types[].name` intersects the requested set; excludes `inactiveFlag=true`. Fake session.
- [ ] Implement (mirror `list_client_companies` pagination); red→green→commit.

### Task 2: `hudu.HuduClient.upsert_magic_dash(title, company_name, message, content, shade, icon)` (TDD, py-core)
- [ ] Failing test: gated by WriteGuard (suppressed under default, issued under open); `POST /api/v1/magic_dash` with the right body; returns None when suppressed.
- [ ] Implement; red→green. Tag **py-core v0.3.0**; PR+merge.

### Task 3: `sync.primary_contacts.build_magic_dash(company, primaries, approvers)` — pure (TDD, hubwise-sync)
- [ ] Failing tests: HTML lists primary name(s); adds "*Also Authorized for Approvals*" section only when approvers exist; message = "Multiple Primary Contacts" when >1 primary else "Primary: <name>"; "Not Specified" when none; names are clean "First Last" (defect fix).
- [ ] Implement pure builder; red→green→commit.

### Task 4: `sync.primary_contacts.run_sync(cw, hudu, hudu_companies_by_name, env)` + wiring (TDD)
- [ ] Failing tests (fake clients): groups contacts by company.id; skips companies with no Hudu match (logged, counted); per-company error isolation + SYNC_DEGRADED; DRY_RUN suppresses the MagicDash upsert but still summarizes.
- [ ] Implement; wire `function_app.py` timer `0 0 11 * * *` (legacy cadence); bump requirements to py-core v0.3.0; PR+merge.

### Task 5: Dry-run → controlled write → attended flip (per runbook §6, proven pilot pattern)
- [ ] Deploy (OIDC); trigger; confirm DRY_RUN summary + intended-write diff.
- [ ] Controlled single-company MagicDash write (open guard, one company), verify in Hudu.
- [ ] Attended flip `DRY_RUN`/`ALLOW_PROD`, watched run, spot-check. (Legacy job dormancy check first — if dormant, skip parallel run as with the pilot.)

---

## Functions #10, #7, #14, #3 — subsequent (one PR each)

Each follows the identical shape: (a) new vendor client in py-core (TDD, mocked transport) — `msp360` / `cw_automate` / `mysonicwall` / `timezest`+`teams`; (b) pure transform/reconcile logic in `hubwise-sync` (TDD); (c) gated `run_sync` orchestration (TDD, failure isolation); (d) thin `function_app.py` timer at the legacy cadence; (e) dry-run → controlled write → attended flip. New secrets these need (runbook §3): MSP360, TimeZest, MySonicWall, Teams webhook — verify present in `hubwise-ops` (may need creation) before each dry-run; if absent, the function safe-skips + SYNC_DEGRADED. `report_timezest_stats` writes a Teams Adaptive Card via the Workflows webhook (Outbound standard), not a doc — its "controlled write" is posting one card to a test channel.

**Sequencing:** #11 first (no new client, proves the MagicDash + contacts path). Then #10 and #3 (independent). #7 and #14 write CW Manage configs — build a shared `cw_manage` config-write + config-dedup helper once, reuse for both. #5 stays held until D-12e resolves.

## Self-review
Covers the 5 buildable Phase-3 functions + the held one, each mapped to legacy behavior, new-client needs, and the proven cutover pattern. Only external dependency is the runbook §3 vendor secrets for #10/#3/#14 — flagged per-function; #11 (first) needs only the already-present CW + Hudu creds, so it's fully unblocked now.
