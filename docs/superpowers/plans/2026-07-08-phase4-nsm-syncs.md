# Phase 4 — NSM-dependent syncs (#8, #9)

**Created:** 2026-07-08. **Gate:** no HubWise code talks directly to a client firewall; both jobs read exclusively via the NSM manager proxy. Build order: **#8 first** (builds the shared `nsm` client), then **#9**.

## Preconditions (all met / decided)
- NSM API coverage audit DONE (runbook §5.2). Per-device reads route via `GET /api/manager/firewall/<subpath>` + header `X-DEVICE-ID: <serial>`.
- **No new secret.** NSM auth = CSC accesscode → `/api/manager/auth/sso` → bearer, using existing KV `NSM-MSW-API-KEY` (tenant_id 2367080, tenant_serial 00401037ACAF). Already proven live by MySonicWallClient (#14). The sync app already has this key wired.
- pyproject version fix (0.7.2 → next) folds into the first py-core PR here.

## Shared new py-core module: `nsm.py` — `NSMClient`
Same auth as `MySonicWallClient._bearer()` (CSC→SSO→bearer; keep mysonicwall.py untouched — duplicate the ~20-line auth or share a helper). Read-only, no WriteGuard. `NSM_BASE = https://nsm-uswest.sonicwall.com/api/manager`.

Methods (all per-device via `X-DEVICE-ID`):
- `list_firewalls()` — GET `/v2/devices/inventory/tenant` (reuse MySonicWall inventory shape: `friendlyName`, `serialNumber`, `liveStatus`).
- `get_interfaces(serial)` — GET `/firewall/interfaces/ipv4` → returns list of `{ipv4:{...}}`.
- `get_dhcp_base(serial)` — GET `/firewall/dhcp-server/ipv4/base` → `{dhcp_server:{ipv4:{enable, ...}}}`.
- `get_dhcp_scopes(serial)` — GET `/firewall/dhcp-server/ipv4/**scopes**/dynamic` (plural noun!) → full dynamic-range list. `parse_dhcp_scopes(raw)` → `[{gateway, from, to, enable, netmask, comment, dns_inherit, dns_static}]`. **DHCP is FULLY supported — the §5.2 "caveat" was a singular/plural typo; corrected.**
- (SSL VPN for #9) `get_ssl_vpn_server(serial)` — GET `/firewall/ssl-vpn/server/base`.
- Pure parse helpers (module-level, easy TDD):
  - `parse_interfaces(raw)` → list of normalized `{name, comment, zone, ip, netmask, gateway, vlan, wan_dns:[...]}`. Source fields (live shape): `ipv4.name`, `ipv4.comment`, `ipv4.ip_assignment.mode.static.{ip,netmask,gateway}`, `ipv4.ip_assignment.zone`, `ipv4.vlan`, and WAN DNS at `ipv4.ip_assignment.mode.static.dns.{primary,secondary,tertiary}`. Interfaces without a static IP (portshield/unassigned/dhcp-wan) → skip for documentation.
  - `netmask_to_cidr(netmask)` → int (replaces the legacy binary-count loop).

## #8 `sync_customer_networks_to_hudu` (timer `0 30 23 * * *`)
Reverse-engineered from legacy `get_customer_networks_and_upload_to_Hudu.ps1`. **Legacy used NSM only for inventory+WAN-IP then made DIRECT firewall calls (basic-auth `SONICWALL_LOCAL_API_BASICAUTH_PASSWORD` to the WAN IP) for interfaces/DHCP/DNS — the rewrite replaces ALL of that with NSM proxy reads by serial. No WAN IP, no shared password.**

Per managed firewall:
1. Parse `friendlyName` → `clientcode` (first 4 alnum, e.g. `GOLD - OMA1` → `GOLD`), `sitecode` (regex `^[^-]+-\s*([A-Z]{3}\d+)\b` → `OMA1`). Skip if either missing.
2. CW Manage: client company where `identifier == clientcode`; active company site whose name starts with `sitecode` → `sitename`. Skip if unmatched (log SYNC_DEGRADED-style skip).
3. Hudu: company by CW company name; the "Sites" asset (layout 19) where custom field **"HubWise Site Code" == sitecode**, not archived → gives the Site link value. Skip interface if no site asset (matches legacy warning).
4. For each interface WITH a static IP: build network-asset fields:
   - `Site` = Hudu link array `[{id,url,name}]` to the Sites asset
   - `Gateway` = interface IP (legacy assumes gateway == firewall interface IP)
   - `IP Address (CIDR)` = `ip/<cidr>`
   - `VLAN` = interface vlan (name `*:V<n>*` → n; else "1")
   - `DHCP Server` / `DHCP Scope` / `DNS Servers` — only if DHCP base enabled AND a scope's `default_gateway == interface ip`. **CAVEAT (from §5.2): per-scope dynamic ranges are not GET-able via the manager proxy leaf that worked; DHCP base (enable flag) IS. Confirm the scope-read path at build (try `/firewall/dhcp-server/ipv4/scope/dynamic` variants; if truly unavailable, document DHCP scope/DNS as a known reduced-fidelity vs legacy and populate only what NSM exposes — interfaces + dhcp-enabled + WAN DNS still cover the bulk).**
   - Asset name = interface `comment` (legacy). Layout = the Hudu "Networks" layout — **legacy used layoutid=1; VERIFY the live Networks layout id + exact field labels at dry-run (like layout 19 Sites / 44 MSP360 were verified).**
5. Upsert network asset by (company, layout, name==comment, fields contain sitename); create or update; unarchive on update.
6. Archive network assets for this site whose name is no longer in the current interface comment set.

Pure logic to TDD (no I/O): friendlyName→(clientcode,sitecode) parser; interface→assetfields builder; plan_networks(desired, existing)→{create,update,archive}. Client/Hudu/CW calls mocked.

## #9 `sync_ssl_vpn_configs_to_cw` (timer `0 0 0 * * *`)
Reuses `NSMClient.get_ssl_vpn_server(serial)` + the proven `CWManageClient` config-write path (from #7/#14). Legacy `get_ssl_vpn_configurations_and_upload_to_manage.ps1` — read its exact read→write contract at #9 start (CW config type/fields for SSL VPN). NSM SSL VPN read validated: `/firewall/ssl-vpn/server/base` → `{ssl_vpn:{server:{auth_type, certificate:{name}, port, session_timeout, user_domain, ...}}}`.

## Cutover (per proven pattern; app is live-armed DRY_RUN=0)
Build client+logic TDD → PR (py-core) → PR (hubwise-sync, deployed INERT: builds NSMClient only if `NSM-MSW-API-KEY`-backed setting present) → LOCAL dry-run (real NSM reads, verify Hudu Networks layout id/labels + a sample device's parsed fields) → controlled single-asset write (open guard) → arm via app settings → disable legacy `Get Customer Networks and Upload to Hudu` (#8) / `Update SSL VPN Info in CW Manage` (#9) workflows. **#8 legacy is ACTIVE — parallel-run/verify before disable.**

## Open verifications (at dry-run, not blockers to build)
- Hudu Networks asset layout: id (legacy=1) + field labels (`Site`,`Gateway`,`IP Address (CIDR)`,`VLAN`,`DHCP Server`,`DHCP Scope`,`DNS Servers`).
- DHCP dynamic-scope read path via NSM proxy (else reduced-fidelity, documented).
- App setting name for NSM: reuse `MYSONICWALL_API_KEY` (already on the app → KV `NSM-MSW-API-KEY`) rather than a new setting, since it's the same key.
