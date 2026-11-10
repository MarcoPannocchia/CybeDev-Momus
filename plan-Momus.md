# Plan — TheWizard

<!-- markdownlint-disable MD003 MD013 MD022 MD028 MD036 MD040 MD060 -->

Task list to track project development. Update the checkboxes as steps get
completed. References to the Obsidian documentation (`TheWizard-docs/`) where
useful.

---

## 0. Conventions for this file

- `[x]` = done (verified in the existing code/changelog)
- `[ ]` = to do
- Each section corresponds to an area of `TheWizard-docs/` or a decision already
  made in chat
- Reference code version for the latest update of this plan: **v0.9.4**, live code in
  `src/thewizard/` (`engine/`, `service/`, `desktop/`). Earlier versions are frozen snapshots in
  `TheWizard Versions/`. Last updated **2026-11-05**.
  consolidated into **`src/`** (2026-10-09, out of
  `TheWizard Versions/Version 0.9.0/`; older Version folders kept as frozen
  history): `TheWizard_v090.py`, `ModulesTheWizard_v090.py`,
  `Network_tool_v090.py`, `DatabaseTheWizard_v090.py`,
  `VectorTheWizard_v090.py`, `MCPServer_TheWizard_v090.py`,
  `ReportTheWizard_v090.py` (+ `WORKLOG.md`)

---

## 1. Cross-section execution order (added 2026-11-05)

> §5.6 only orders steps _within_ the desktop/service track. This section
> orders work _across_ sections, given the current state of the project and
> the stated goal of having something demo-worthy (agentic MCP tool-use, not
> just more OS targets) for a portfolio. Supersedes any other implicit
> ordering when sections disagree. Re-evaluate at the recheck checkpoint below
> rather than assuming it's still right by default.

**Order**

- [x] 1. §4 — verify/fix multi-tab WebSocket event isolation (confirm events
      don't cross `scan_id`s with two tabs open; fix if they do)
- [x] 2. §2 — first-run config/settings gap + catalog-seeding + loading-screen
      bugs. Inserted here 2026-11-05: these block anyone but the author from
      using the app at all, which outranks §3's remaining steps for a tool
      meant to be shown or tried by others. Loading-screen and catalog-seeding
      fixes can land immediately; the credentials registry/settings subsystem
      is the slightly larger piece of this step.
- [x] 3. §3 — Claude as MCP host: wire the service to drive the tool-use loop
      against the Claude Messages API, replacing the dead Groq path
      _(done 2026-11-05, WORKLOG 55–57)_
- [x] 4. §3 — centralized versioned system prompt + the agentic loop's
      explicit stop-and-confirm before any `AuthorizationMixin`-gated action,
      built together _(done 2026-11-05, WORKLOG 61)_
- [x] 5. §3 — autonomous session loop (goal → tool calls → evaluate → next
      step → stop condition) _(done 2026-11-08, WORKLOG 65: service/agent_session.py,
      POST /agent/sessions; scope enforced in code; results stored in a host-owned
      scan session)_
- [ ] 6. §3 — testing-plan-first behavior (propose the tool/target sequence
      before running it)
- [x] 7. §16 — `install.sh` + updated `requirements.txt` (fast; unblocks #8)
      _(done 2026-11-05, WORKLOG 61)_
- [ ] 8. §5.5 — Windows/macOS packaging (+ CI matrix if time allows)
- [ ] 9. §15 — docs refresh for the desktop/service/MCP-host architecture +
      changelog entry for the v0.9.x phase
- [ ] 10. §17, §18, §19 — study docs, knowledge-base corpus discussion, Python
      3.15 adoption — opportunistic, no fixed order between them

**Recheck — every 2 work sessions**

- [ ] Did anything built in the last two sessions change what's actually next
      (a bug found, a decision reversed, something harder/easier than
      expected)?
- [ ] Is anything now blocking that wasn't before (e.g. §3 surfacing a gap in
      §4's event layer, or a §18 licensing question becoming relevant sooner
      than planned)?
- [ ] Does the stated priority still hold — still building toward "demo an
      agentic MCP tool," or has the goal shifted toward "something installable
      for others to try"? If it shifted, swap step 8 (packaging) ahead of
      steps 3–6 (the agentic loop) deliberately, not by default.

If nothing's changed, continue down the list without a full replan.

---

## 2. First-run configuration, credentials, and catalog seeding (opened 2026-11-05)

> Raised in chat 2026-11-05. Two of the four items here are bugs against
> already-shipped features (empty catalog tables, missing loading screen); the
> other two are a small missing subsystem (API credentials have no setup or
> settings path at all today). Distinguishing the two matters for sequencing:
> the bugs can land fast and independently, the credentials system is a short
> design-then-build arc with its own steps below.

**Credentials registry + first-run setup**

- [x] **Done 2026-11-05 (WORKLOG 60)** — `engine/credentials.py`, `REGISTRY` with `nvd_api_key` and `anthropic_api_key`. Define a small **credentials registry**: a list of
      `{key_name, label, required_for, env_fallback}` entries — starting with
      `WIZARD_NVD_API_KEY` (optional, degrades gracefully — keyless NVD still
      works, just slower/rate-limited) and the Anthropic/Claude key that §3
      introduces (required once the agentic loop exists; the rest of the tool
      still functions without it). This is what both the first-run wizard and
      the later settings screen iterate over, so a future key is one registry
      entry, not a new form field hand-wired in two places.
- [x] **Decided 2026-11-05: a config file in the per-user data folder** (Linux `~/.local/share/thewizard-data/credentials.json`, mode 0600; macOS and Windows use their application folders; `WIZARD_CONFIG_DIR` overrides). The env var wins over the file. **Decide storage location**: today `WIZARD_NVD_API_KEY`/`GROQ_API_KEY` are
      read straight from env vars (§11, CURRENT STATE), fine for dev but not a
      workflow for someone running the packaged app (§5.5) — there's no "repo"
      on their machine to put a gitignored file in. Proposed: a config file in
      a per-user app-data directory (platform-appropriate path), written by the
      first-run wizard and edited by settings; keep the env var as a dev-only
      fallback/override, consistent with the existing "secret in env/file, not
      the DB" convention (§11).
  - [x] Confirmed by the user 2026-11-05 (config-dir storage). Confirm this before building: config-dir-based storage, or does the
        repo-relative gitignored-file approach from the original ask still
        apply for some reason (e.g. a CLI-only dev workflow)?
- [x] **Done 2026-11-05 (WORKLOG 60)** — `views/first_run_dialog.py`; skippable, closing counts as skipping. First-run wizard (desktop): on first launch, walk the credentials
      registry and ask for each key (optional ones skippable); write to the
      config file above
- [x] **Done 2026-11-05 (WORKLOG 60)** — plus `DELETE /config/credentials/{key}` and `POST .../first-run-done`. Service endpoints: `GET /config/credentials` (masked — never echo a
      stored key back in full) and `PUT /config/credentials` so both the
      first-run dialog and the settings view (below) hit the same contract,
      consistent with the existing GUI↔engine-via-service architecture (§5)

**Settings — editable + extensible credentials**

- [x] **Done 2026-11-05 (WORKLOG 60)** — Settings → API keys. A settings view (or a tab on an existing one) listing every registry
      entry with its current status (set/unset, masked) and an edit action
- [x] **Done 2026-11-05 (WORKLOG 60)** — rows are built from the service's live list; tested with a key added later. Any registry entry **not** asked during first-run (because it was added
      to the registry later, after the user's install) must still be addable
      here — i.e. settings always reflects the live registry, not a snapshot
      taken at first-run time

**Base catalog seeding (bug fix)**

- [x] Seed `wizard_wordlist` and `wizard_security_headers` with sensible
      defaults — **done 2026-11-05 (WORKLOG 59)**: migration 7 rides the existing
      `PRAGMA user_version` mechanism, through a new `_MIGRATION_HOOKS` entry
      (`_seed_catalog_defaults`). It fills a table only if it is empty, runs once
      per file, so user edits survive and a list the user emptied stays empty. An
      existing v6 database with empty lists is seeded too (that was the bug)
  - [x] Draft a default wordlist (common subdomain names) and a default
        security-headers list — about 90 DNS-valid labels and the 9 usual
        headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options,
        Referrer-Policy, Permissions-Policy, three Cross-Origin policies)
  - [x] Check whether any other config table moved to the DB in §12/§7 has the
        same gap — audited 2026-11-05: only three config tables exist
        (`wizard_wordlist`, `wizard_security_headers`, `wizard_urls`) plus the
        already-seeded `wizard_tls_deprecated`; `wizard_urls` stays empty on purpose.
        Original note: same gap (seeded with defaults vs. silently empty) — `wizard_urls` is
        expected to stay empty-by-default (always the user's own targets), but
        worth a quick audit rather than assuming headers/wordlist are the only
        two

**Desktop loading screen (bug fix)**

- [x] **Fixed again 2026-11-05 (WORKLOG 63)** after the user reported it was not
      showing: measured on a real X server, `QSplashScreen.show()` itself blocks for
      1.0 s, so the splash appeared 1.4 s after launch and flashed for 0.4 s. Replaced
      by `desktop/loading_screen.py` (appears at ~0.4 s, held 1.5 s).
- [x] **Done 2026-11-05 (WORKLOG 59).** Diagnosis: the splash exists and is shown,
      but `ServiceController.ensure_started()` blocks the GUI thread before
      `app.exec()`, so it never repaints (measured: 0 repaints in a 3 s wait, 3 after
      the fix). Fix: `on_wait` hook pumping `app.processEvents` plus a live "Starting the
      local service… Ns" message. Original note: determine whether a loading/splash
      screen exists and isn't wired up, or doesn't exist at all, then fix
      accordingly so app startup (including the known model-load stall) isn't
      silently blank

> **Sequencing note**: these four are "nobody but the author can use this app
> without them" issues — arguably higher priority than §3's agentic-loop work
> for anyone who'd try the app before AI integration lands. §1 has been
> updated to insert this section ahead of §3's remaining steps; see §1.

---

## 3. AI integration — local MCP server (replaces `AI_suggestion` on Groq)

> `AI_suggestion` (Groq) exists in the current code but wasn't found in the
> documentation synced into this project (`TheWizard-docs/`, synced GitHub
> repos). Before migrating, locate the current source file to understand exactly
> what it generates today and at what point in the flow it's called.
>
> **Finding (2026-09-25 code review of v0.9.0)**: the Groq layer is
> `AI_Suggestions.AI_Suggest_Spell` in `ModulesTheWizard_v090.py` (line ~769).
> It is **currently a dead path — never called by `Cast_Spell` or anything
> else**, so AI triage does not run during a scan today. Decision (2026-09-25):
> leave it un-wired rather than plug the soon-to-be-replaced Groq spell into
> `Cast_Spell`; this whole path is superseded by the MCP work below. It builds a
> findings payload (`_build_findings_payload`, capped by `_cap_value`) and calls
> the Groq chat API with a rate limiter (`_GroqRateLimiter`) — useful as the
> reference for what the MCP tools/agentic loop should reproduce.

> **Architectural decision (2026-09-25)**: the integration with Claude goes
> through a **local MCP (Model Context Protocol) server**, not custom REST
> endpoints or the Claude API's remote connector (that requires a publicly
> reachable HTTP server, incompatible with the "127.0.0.1, no network exposure"
> choice in section 5.2). The MCP server runs via **STDIO**, the same mechanism
> Claude Code and Claude Desktop use to connect to local servers — no network
> involved.
>
> **See also section 18**: a related but distinct extension — a general
> cybersecurity-research knowledge base, separate from this section's index of
> the project's _own_ scan results. Opened 2026-10-09, still at the discussion
> stage.

- [x] Create the MCP server (own module: `MCPServer_TheWizard_v090.py`) exposing
      TheWizard's tools as MCP tools — **done 2026-10-09** (pending runtime
      verify once `mcp` is installed): `scan_open_ports`
      (Socket_Port_Scanner+Banner_Grabber), `run_nmap_service_scan`,
      `check_security_headers`, `lookup_cves`, `check_tls_certificate`,
      `enumerate_subdomains`, plus session tools (`open`/`close_scan_session`),
      active-action tools behind the allowlist+`confirmed=true` double gate
      (`prepare_exploit_plan`, `run_post_exploit_module`), and
      `search_semantic_index`. Wraps the real engine (no reimplemented logic);
      engine refs all resolve; compiles. SDK class is `MCPServer` (not FastMCP).
      See `WORKLOG.md` (2026-10-09 #2).
- [x] Expose session data + vector context as MCP **resources** (not tools) —
      **done 2026-10-09**: `thewidzard://sessions`, `…/session/{id}`,
      `…/targets`, `…/target/{id}/sessions`, `…/wordlist`. (Semantic search is
      correctly a _tool_, not a resource — free-text query + active
      embedding/KNN work; the file documents the distinction.)
- [x] **Done 2026-11-05 (WORKLOG 55–57)** — `service/claude_host.py` and
      `POST /agent/goals`; the Groq code is removed. **Priority (see §1, step 2)**:
      Replace the Groq provider with Claude: the
      service (or a dedicated process) acts as the MCP client/host and drives
      the tool-use loop against the Claude Messages API
- [x] **Done 2026-11-05 (WORKLOG 61)** — `service/agent_policy.toml` (version,
      prompt, model defaults, limits, confirm list), loaded and validated by
      `service/agent_policy.py`; the gate reads its tool list from it. **Priority
      (see §1, step 3)**: centralized model file — system
      prompt/configuration versioned in the repo — ethical principles
      (authorized use, explicit stop before Exploitation/Post-Exploitation) + a
      focus on concrete results and efficiency — governs the entire agentic
      loop, not just text responses. Build together with the stop-before-active-
      action gate below, since the gate's behavior should be defined by this
      config, not hardcoded separately.
- [x] **Done 2026-11-05 for the two tools the host offers (WORKLOG 61)** — the loop
      pauses at `prepare_exploit_plan` / `run_post_exploit_module` and a person
      answers with `POST /agent/runs/{id}/confirm`; the model cannot set
      `confirmed`. **Still open:** ZAP active scan and LAN follow-on are not
      MCP tools, so the host does not offer them; if they become tools, add them
      to the policy's `[confirm.tools]` list. **Priority (see §1, step 3)**: the
      agentic loop must enforce an explicit
      stop and require human confirmation before anything gated by
      `AuthorizationMixin`/`confirmed=True` (Exploitation/Post-Exploitation,
      ZAP active scan, LAN follow-on scanning) — not just leave the existing
      gates in place passively, but have the loop itself recognize the boundary
      and pause there
- [x] **Done 2026-11-08 (WORKLOG 65)** — `service/agent_session.py` +
      `POST /agent/sessions`: a background loop that takes a goal and a target
      scope, calls the passive tools, evaluates each round against the goal,
      picks the next step, and stops on finish_session / step / time / error /
      operator-stop. Scope is enforced in code (not only the prompt); results go
      into a host-owned scan session so the run appears in History; active tools
      still pause for confirmation. **Priority (see §1, step 4)**: **Autonomous
      sessions**: Claude must be able to run an entire session (a sequence of
      scans/analyses) without step-by-step user intervention
- [ ] **Priority (see §1, step 5)**: **Testing plans**: part of the same loop —
      Claude proposes the sequence of tools/targets to run before launching it,
      not just an after-the-fact comment on the results
- [ ] Evaluate using the Claude Agent SDK for the agentic loop (it already
      handles MCP tool discovery and the tool-use cycle) instead of writing it
      by hand
- [ ] Side benefit of the MCP choice: the same server can be attached directly
      to Claude Code or Claude Desktop during development/debugging, to run a
      tool or an entire session without going through the GUI
- [x] Harden the MCP active-action confirmation gate (done 2026-10-22: server-persisted single-use approvals, fix plan 3.1, WORKLOG 21/25): today `confirmed=True` is
      a client-supplied flag, not independently verifiable server-side (see
      §5's ARCHITECTURE note and `MCPServer_TheWizard`'s own docstring on this).
      A production version should add a server-persisted approval table instead
      of trusting a same-call flag — not yet a tracked implementation item
      beyond this note.

---

## 4. Multiple parallel sessions (multi-tab) & optimization

- [x] **GUI — session tabs** (built 2026-10-22,
      `src/thewizard/desktop/views/scan_sessions.py`): the Scan view holds several
      sessions as tabs. "+" in the corner adds one, double-clicking a tab
      renames it, and × closes it (a running session asks first and is stopped
      on confirm). Each tab has its own target, monitor and summary tiles, and
      new tabs take the default density from Settings.
- [x] **Backend — parallel scans** (built 2026-10-25): each scan runs in its own
      child process (`src/thewizard/service/scan_worker.py`), so the engine's class-level
      state never meets another scan. The manager (`manager.py`) reads each child's
      events from stdout and caps the number of running scans at
      `WIZARD_MAX_PARALLEL_SCANS` (default 2). Verified: two real scans finished
      together, a third got 409 with the limit, stopping one left the other running,
      the DB passed an integrity check, and the frozen app behaves the same.
- [x] Local service: handle several active `scan_id`s at once — **verified 2026-10-25**
      (two real scans finished together; a third got 409 at the cap; stopping one left the
      other running)
- [x] Concurrent SQLite writes (checked 2026-10-25: WAL mode and a 5 s busy timeout were already set; two scans wrote to the same file with no errors). Original note: several parallel sessions writing to the same
      file may serialize writes (SQLite allows only one writer at a time) —
      evaluate **WAL mode** (`PRAGMA journal_mode=WAL`) to allow concurrent
      reads during writes, and/or a centralized write queue in the service
      instead of direct writes from different tasks
- [x] Cap the number of parallel sessions (`WIZARD_MAX_PARALLEL_SCANS`, default 2; based on the memory each child uses, since it may load the embedding model). Still open: sizing it from network, CPU and NVD rate limits (original note: network,
      CPU for nmap, NVD rate limit shared across sessions — see section 11)
- [x] **Priority (see §1, step 1)**: verified 2026-11-05 (`tests/test_ws_isolation.py`, no cross-feed): verify that the event layer (5.1) and the
      WebSocket stream (5.2) correctly separate events by `scan_id`, so multiple
      open tabs don't mix up the logs. The route is per scan
      (`/scans/{id}/events`), but two sockets open at once have not been
      tested. Session tabs and parallel backend scans are each independently
      verified — the combination of both at once is not, and is the one item
      here that could be a live bug rather than a missing feature.

---

## 5. Desktop app architecture (+ future CLI and web)

> Decisions made on 2026-09-24, starting from the code (v0.8.2 back then, v0.9.0
> now). Full details in the project document
> `claude/architettura-app-desktop.md` — this section tracks its execution as a
> task list. **Correction relative to the original document**: wherever it says
> "Postgres"/"asyncpg pool," read **SQLite/`aiosqlite`** (see note in section
> 2).

**Goal**: three interfaces over time — desktop app (now), Unix CLI (later),
lightweight web page (later) — without duplicating scan/DB logic in each.

**Architectural decisions**:

- Engine (the 4 existing files) unchanged: remains the single source of truth
  for scanning and SQLite access
- GUI ↔ engine communication through a **shared local service** (not in-process
  in the GUI), so future CLI and web reuse the same contract
- Desktop toolkit: **PySide6** (Qt)

### 5.1 Event layer (targeted refactor) — ✅ done 2026-10-13

- [x] Replace the scattered `print("[TAG] ...")` calls in the mixins with a
      utility like `self._log(tag, **fields)` — **done**:
      `EventMixin._log(line)` is a drop-in for `print(line)` (all 97 Modules +
      31 Network + 8 facade-scan prints converted; the 6 classmethod/CLI prints
      left as `print`). `EventMixin` is a base of every tool class + the facade,
      so `self._log` always resolves (incl. standalone).
  - [x] Must print as it does today (unchanged behavior when there's no
        listener) — `_log` prints first, always; no sink ⇒ exactly `print()`
  - [x] Must also emit a structured event if a listener is registered —
        `set_event_sink(cb)`; events
        `{seq, ts, tag, message, raw, [target], **fields}` (tag parsed from the
        leading `[TAG]`)
  - [x] No change to business logic, only to logging I/O — verified; event smoke
        test 11/11

### 5.2 Local service (`src/thewizard/service/`, new package) — ✅ done 2026-10-13

- [x] FastAPI setup, a single process, bound only to `127.0.0.1` (no network
      exposure for now) — **done**: `src/thewizard/service/` package;
      `python -m thewizard.service` on `127.0.0.1:8765` (env-overridable, stays
      loopback)
- [x] The service owns the `TheWizard` instance and the lifecycle of the SQLite
      connection (`aiosqlite`) + the aiohttp session — **done** (V1):
      `ScanManager` owns the engine instance per scan; the engine opens/closes
      the SQLite connection and its aiohttp session inside `Cast_Spell`. _(A
      persistent, fully service-owned connection across read endpoints is a §4
      refinement — today read endpoints call the idempotent `init_db()`.)_
- [x] `POST /scans` → starts `Cast_Spell` in the background, returns `scan_id` —
      done (optional `targets` seeded into `wizard_urls`; `409` if a scan is
      already running — one at a time in V1, see §4)
- [x] `GET /scans/{id}` → status (running/done/error/**stopped**, current url,
      counters) — done
- [x] `POST /scans/{id}/stop` → clean task cancellation — done (task cancel →
      status `stopped`)
- [x] `WS /scans/{id}/events` → stream of structured events (from 5.1) — done
      (replays the buffer, then streams live, then an `{event:"end",status}`
      frame)
- [x] `GET /k6-configs` → list from SQLite (already available via
      `get_k6_configs`) — done
- [x] `POST /k6-configs/{id}/approve` → marks as approved — done;
      `approve_k6_config` now returns whether the id existed (→ `404` on
      unknown). The `approved_at` column already exists (migration #1)
- [x] No endpoint should execute k6 directly — deliberately stays out,
      consistent with the current code — done
- **API contract for the GUI (§5.3) is in `src/thewizard/service/API.md`.** GUI is
  being built separately (handed to a Fable chat). Verified: TestClient suite
  9/9 (real engine, empty scan + WS replay + k6) and a fake-engine suite 7/7
  (live WS streaming, 409-busy, stop).

### 5.3 GUI client (PySide6, `src/thewizard/desktop/`)

> **Code complete + smoke-verified 2026-10-13** (`src/thewizard/desktop/`), built against
> `src/thewizard/service/API.md`. Offscreen smoke test green (Desktop venv):
> `MainWindow` builds with QSS + both views; service auto-start **attach and
> spawn** paths both work; client read-only contract
> (`health`/`list_scans`/`list_k6`) verified against a live service. A
> port-passing bug in `ServiceController` was found and fixed during the test.
> **Live scan + WS stream verified 2026-10-20** (real `ScanView` driven through
> a real local scan on a temp DB): 26 tagged events streamed, status `done`;
> fixed a WS connect-timeout bug (model-load stall at scan start exceeded the 10
> s timeout → now a separate 40 s `ws_connect_timeout` + blocking recv). Still
> the user's own step: a real desktop launch against an authorized target.
> Launch: `PYTHONPATH=src python -m thewizard.desktop` (deps are in the Desktop venv).
> Now at `src/thewizard/desktop/` (moved 2026-11-03, §5.4).

- [x] Thin, reusable HTTP/WebSocket client (same base planned for the future
      Typer CLI) — `client.py`: framework-agnostic `ServiceClient` (sync
      `requests` + `websocket-client`), Qt-free so the CLI reuses it; typed
      `ServiceError`/`ScanBusyError`
- [x] "Scan" view — start/stop, live event log via WS — `views/scan_view.py`:
      control panel + tag-structured live monitor (not a raw dump) + density
      toggle
- [x] "K6 configs" view — table + script detail + approval button —
      `views/k6_view.py`: list+detail, generated/approved badge, approve with
      confirmation (never runs k6)
- [x] Automatic startup of the local service as a subprocess/thread if not
      already listening on `127.0.0.1`; shutdown when the window closes —
      `service_process.py` (`ServiceController`) + `__main__.py`; only stops a
      service it started
- [x] Results view — browse stored scans and their findings
      (`views/results_view.py`, WORKLOG 45)
- [x] Scan-to-scan diff in the Results view — **built 2026-11-02** (WORKLOG 46)
- [x] Per-scan module ("Spells") selection — **built 2026-11-02**, `scan_modules.py`
      and the scan view (WORKLOG 47)
- [x] Per-scan wordlist from a file, for one scan — built 2026-11-05 (WORKLOG 51)
- [ ] Choose between several _saved_ wordlists (not built; the DB holds one configured list)
- [x] List pending approvals — built 2026-11-05, read-only (WORKLOG 51)
- [ ] Real desktop walkthrough against an authorized target — a person's step, see
      `TheWizard GUI — Test Plan.md`
- [x] **Fixed 2026-11-05 (see §2; WORKLOG 59)** — bug noted: the loading screen does not show when
      opening the desktop app. Likely related to the model-load stall already
      identified above (the WS connect-timeout fix raised the timeout to 40s
      precisely because startup can stall on the embedding model) — if a
      loading/splash screen is meant to cover that window, either it isn't
      implemented or isn't wired to the right lifecycle event. Needs a look to
      tell which.

### 5.4 Repository restructuring

> **Done 2026-11-03.** The 2026-10-20 deferral is resolved. Its conflict was with
> snapshots being flat in `src/`, but snapshots already live in `TheWizard Versions/`,
> so the live package can hold only the current code. Layout:
>
> ```
> src/thewizard/
>   engine/    # 9 modules: TheWizard, ModulesTheWizard, Network_tool, DatabaseTheWizard,
>              #   VectorTheWizard, ReportTheWizard, MCPServer_TheWizard, scan_modules, parent_death
>   service/   # FastAPI app, scan manager, scan worker, API.md
>   desktop/   # PySide6 app, HTTP/WS client
>   cli/       # future: Typer (not created yet)
>   web/       # future: lightweight static page (not created yet)
> ```
>
> Imports are absolute (`from thewizard.engine import X`). The default DB stays at
> `src/wizard.db`. Children start with cwd `src/`. Verified: 84 tests green, service
> started from `src/`, frozen bundle built and run (WORKLOG 49).
> **Open:** the first `_vXXX` snapshot needs an import-form decision (CLAUDE.md).

- [x] Reorganize per the proposed layout — **done 2026-11-03** (`cli/` and `web/` are
      future work).

### 5.5 Multi-OS packaging (PyInstaller)

> **Linux build done 2026-10-20** via `packaging/TheWizard.spec` (onedir; not
> the raw base command — a spec was needed for the engine `pathex`,
> uvicorn/websockets hidden imports, torch/ST **excludes**, and bundling the
> service). The frozen app bundles both GUI and service: when `sys.frozen`,
> `ServiceController` re-execs the binary with `--run-service` (handled in
> `desktop.__main__`) since `python -m thewizard.service` isn't available
> packaged. `dist/TheWizard/` (~245 MB). Both frozen modes verified (service
> health; GUI auto-spawns its service). Install not run (user step).

- [x] ~~Base command~~ → `pyinstaller packaging/TheWizard.spec --noconfirm` (a
      spec, not the bare `--icon desktop/main.py` command — see note)
- [x] **Linux**: build → `dist/TheWizard/` folder; PNG icon
      (`packaging/thewizard.png`, Qt-drawn); `.desktop` via
      `packaging/install_linux.sh` (copies the app to
      `~/.local/share/thewizard`, then writes the menu entry, hicolor icon and a
      `~/Desktop` copy; `--uninstall` removes them; GNOME "Allow Launching" first time) —
      **the user runs the installer**
- [ ] **Windows**: `--onefile --windowed --icon=app.ico` build → `.exe`; `.lnk`
      shortcut on the Desktop with the icon set in its properties (future: Inno
      Setup/NSIS installer for Start Menu + Desktop together)
- [ ] **macOS**: `--windowed --icon=app.icns` build → `.app` bundle; `.icns`
      icon (converted from PNG with `iconutil` or an online tool); user drags it
      into `/Applications` (note: without an Apple Developer signature,
      Gatekeeper blocks the first launch — unblock with right-click → Open,
      acceptable for personal/homelab use)
- [ ] Evaluate GitHub Actions in the future with an `ubuntu-latest` /
      `windows-latest` / `macos-latest` matrix to automate builds (the repos are
      already on GitHub)

### 5.6 Proposed execution order

1. [x] Event layer refactor (5.1) — done 2026-10-13
2. [x] FastAPI service (5.2) — done 2026-10-13
3. [x] Minimal PySide6 window with automatic service startup (5.3) — done 2026-10-13,
       live scan verified 2026-10-20
4. [x] First PyInstaller build on Linux (5.5) — done 2026-10-20
5. [ ] Replicate the build on Windows/macOS (5.5) — open

**V1 — chosen priorities**: starting and monitoring live scans; reviewing k6
configs (never auto-executing).

> **Note**: this subsection orders steps _within_ the desktop/service track
> only. For how this track sequences against §4, §3, and §16, see §1.

---

## 6. New analysis features (decided on 2026-09-25)

**Aggregated report (PDF/HTML)**

- [x] Choose a generation library — **done 2026-10-09**: chose **dependency-free
      HTML** (plain templating in `src/ReportTheWizard_v090.py`), not
      WeasyPrint/Jinja2, to avoid heavy system libs; PDF can layer on later over
      the same HTML.
- [x] Report template with one section per result category — **done**:
      ports/banners/CVEs/headers/TLS/subdomains/technologies, each a table.
- [x] The report reads from a session (section 7), not scattered tables —
      **done**: `generate_report` prefers the §7 per-session JSON snapshot
      (single-row read), falls back to the relational tables if unsnapshotted.
- [ ] Endpoint in the local service to generate/download the report for a
      session (see 5.2) — **deferred to §5** (local service). The generator
      (`generate_report`/`write_report`) is ready for it to call.
- [x] **GUI results browser** (built 2026-11-02): `GET /sessions` + `GET /sessions/{id}`
      and a Results view surface each stored session's per-category results in the app
      (not the HTML report, the raw rows). Scan-to-scan diff in the GUI is still open
      (`diff_sessions` exists in the DB layer).

**Technology fingerprinting**

- [x] Detect CMS/framework/client-side JS libraries (response headers, meta
      tags, HTML/JS patterns) — Wappalyzer-style — **done 2026-10-09**:
      `_fingerprint_technologies(headers, body)` signature set
      (server/X-Powered-By, `<meta generator>`,
      WordPress/Drupal/jQuery/React/Next.js/Bootstrap), captures versions.
- [x] Add as a function in `OSINT_tool`, orchestrated by `OSINT_Spell` —
      **done**: `Technology_Fingerprinter`, persisted to `wizard_technologies`
      via `save_technologies` (new result table + `get_technologies`).
- [x] The result feeds into the session's technologies "vector" (section 7) —
      **done**: included in `snapshot_session` (`technologies_json`), the vector
      index (`_s_tech`/`index_session`), and `diff_sessions`.

**TLS/cipher security scoring**

- [x] Extend `SSL_TSL_CHECKER`: negotiated protocol + cipher — **done
      2026-10-09**: captures `ssl_object.version()` + cipher, persisted to new
      `wizard_ssl_checks.protocol/cipher` columns (migration #2).
- [x] List of deprecated protocols/ciphers in a DB config table, not hardcoded —
      **done**: `wizard_tls_deprecated` (kind ∈ protocol/cipher_substring),
      seeded with defaults by `_init_schema`, editable; `get_tls_deprecated`.
- [x] Compute a synthetic A–F score, Mozilla-Observatory style — **done**:
      `_grade_tls(protocol, cipher, days_left, deprecated)` deduction model;
      stored in `wizard_ssl_checks.grade`; surfaced in the vector `_s_ssl`
      serializer. (TLSv1.3→A, TLSv1.1→E, RC4→D, expired→F.)

**History/diff between successive scans**

- [x] Query comparing two sessions on the same target: new/closed ports, new
      CVEs, changed certificate, ~~changed technologies~~ — **done 2026-09-28**:
      `diff_sessions(conn, before, after, target_id)` returns new/closed ports,
      new/gone subdomains, new/resolved CVEs, and a cert-changed flag;
      `get_sessions_for_target` picks which two to compare. (Tech-change omitted
      — tech fingerprinting not built yet.) CVE diff is session-level for now.
      See `WORKLOG.md` (2026-09-28 #6).
- [x] Expose as a dedicated GUI view — **done 2026-11-02**: the scan-to-scan diff is in the
      Results view (WORKLOG 46). The section of the aggregated report is still open.

---

## 7. Sessions, storage, and removal of hardcoded lists (decision 2026-09-25)

> Extends the data model of section 8, doesn't replace it. A **session**
> represents one `Cast_Spell` run over one or more targets, with the
> configuration used (wordlist, security headers, targets) and all the findings
> collected. It lives entirely in the SQLite DB — no separate export file by
> default, unless explicitly requested later (sharing/backing up a session
> outside the app).

- [x] `sessions` table with metadata: id, name, date, scanned targets, reference
      to the configuration used — **done 2026-09-28** as
      `wizard_sessions(id, name, status, config_snapshot, created_at, started_at, finished_at)` +
      `create_session`/`finish_session`/`get_session`/`list_sessions`.
      Deliberate deviation: stores an **immutable `config_snapshot` JSON copy**
      rather than a live "reference to the configuration" (faithful historical
      record). "scanned targets" (a `session_targets` junction) still pending —
      DB code's "step 3 of 4".
- [x] "Vector" columns on `sessions` for fast access: one JSON-array column per
      result category — **done 2026-10-09**: migration #3 adds
      `ports_json/banners_json/cves_json/headers_json/subdomains_json/ssl_json/technologies_json`
      to `wizard_sessions`; `snapshot_session()` populates them at end of
      `Cast_Spell`, `get_session` parses them → whole session reads in one row,
      no joins. Relational tables stay source of truth. See `WORKLOG.md`
      (2026-10-09 #6).
- [x] **Vector database (embeddings)**, alongside the structured tables — not
      instead of them — dedicated to communication with the AI (section 3).
      **Coverage**: an AI-readable version of _every element_ in the config
      tables (`wordlist`, `security_headers`, `urls`) and the data tables
      (`sessions`, `targets`, `ports`, `banners`, `cves`, `headers`,
      `subdomains`, `ssl_checks`, `k6_configs`). The relational tables remain
      the source of truth for exact queries/history-diff (section 6); the vector
      DB is the full semantic mirror the AI retrieves context from. — **done
      2026-09-28**: `VectorTheWizard_v090` (`sqlite-vec` + local
      `sentence-transformers` embeddings), built, tested (fake + real), wired
      into `Cast_Spell` (guarded, batched, idempotent). **Full coverage of all
      12 tables**: `index_session` (results + session + targets) +
      `reindex_all_config` (config + k6). CVEs are indexed at **session level by
      design** (session-oriented model — a scan session is the unit of meaning),
      not a gap. See `WORKLOG.md` (2026-09-28 #7).
  - [x] Define, per table, the row→text serialization function — **done
        2026-09-28** for `targets` + the 6 result tables
        (`ports`/`banners`/`cves`/`headers`/`subdomains`/`ssl_checks`) in
        `VectorTheWizard_v090._SERIALIZERS`; serializers for the config tables +
        `sessions`/`k6_configs` still to add (see parent).
  - [x] Engine: `sqlite-vec` — **done 2026-09-28**: `wizard_vec` vec0 table in
        the same SQLite file; extension loaded on the aiosqlite worker thread.
        Pipeline verified end-to-end (fake-embedding test: load + index + KNN).
  - [x] Embedding model: local — **done 2026-09-28**: `sentence-transformers`
        `all-MiniLM-L6-v2` (384-dim, normalized), lazy-imported; no per-scan
        network/cost.
    - [ ] **2026-10-10**: the manual deferred-import pattern here is the top
          candidate to become a real `lazy import sentence_transformers` once
          the project is on Python 3.15 — see plan §19. Same guard
          (`vector_available()`), same no-cost-unless-used behavior; only the
          syntax changes.
  - [x] Decide when to generate/update embeddings — **done 2026-09-28**:
        **batched at end of run** (`index_session` after the scan loop in
        `Cast_Spell`), embedding off-loop via `asyncio.to_thread`.
- [x] Convert the "old" hardcoded elements into configuration tables in the same
      DB — **verified done 2026-09-28**:
  - [x] `security_headers` → `wizard_security_headers` table +
        `get_security_headers`/`add_security_header`
  - [x] `urls`/default targets → `wizard_urls` table + `get_urls`/`add_url`, and
        each run's set is snapshotted into `wizard_sessions.config_snapshot`
  - [x] `wordlist` → `wizard_wordlist` (done in §12)
  - [x] **Fixed 2026-11-05 (see §2, migration 7)** — gap noted: unlike `wizard_tls_deprecated` (§6,
        seeded with defaults by `_init_schema`), neither `wizard_wordlist` nor
        `wizard_security_headers` ships with any starting content — a fresh DB
        has both empty until someone manually calls `add_word`/`add_header`.
        This is a regression relative to the old hardcoded-list behavior, not
        just a missing nice-to-have. Fix tracked in §2.
- [x] Update `Cast_Spell` to read the configuration from the session/DB instead
      of class attributes — **done**: `_load_lists()` loads all three lists from
      the DB (`load_config_lists`) into the (empty-by-default) class attrs at
      the start of `Cast_Spell`; no hardcoded values remain. (Loaded once into
      memory for fast per-item reads during a scan; only writes touch the DB.)

---

## 8. Result persistence (SQLite — final decision)

> Note: persistence is unified on **a single SQLite DB** for everything
> (wordlist included, see section 12) — no more separate Postgres/SQLite DBs, and
> no more end-to-end Postgres. A choice consistent with the desktop app
> packaging (section 5): a `.db` file distributable together with the package,
> with no external service to administer.

- [x] Verify the schema currently implemented in `DatabaseTheWizard_v090.py`
      against the schema proposed below, and update the checkboxes accordingly —
      **done 2026-09-28**: reviewed & runtime-tested; `targets` + `sessions` +
      k6 `approved_at` implemented (with a `PRAGMA user_version` migrations
      framework), the other result tables still pending
- [x] Result tables schema (adapted from roadmap.md) — **done 2026-09-28** (DB
      layer): all tables + `save_`/`get_` helpers implemented & tested; each
      result row carries `session_id` + `target_id`, plus a
      `wizard_session_targets` junction (§7 "scanned targets"). _Wiring
      `Cast_Spell` to actually write these is the follow-on — see the "when to
      write" item below._
  - [x] `targets(id, url, first_seen, last_seen)` — **done** as
        `wizard_targets` + `get_or_create_target`/`get_target`/`list_targets`
  - [x] `ports(id, target_id, port, state, service, scanned_at)` —
        `wizard_ports` (+ `session_id`) + `save_ports`/`get_ports`
  - [x] `banners(id, target_id, port, banner, captured_at)` — `wizard_banners`
        (+ `session_id`) + `save_banners` (returns
        `{port: banner_id}`)/`get_banners`
  - [x] `cves(id, banner_id, cve_id, score, description)` — `wizard_cves` (+
        `session_id`) + `save_cves`/`get_cves`
  - [x] `headers(id, target_id, header_name, present, checked_at)` —
        `wizard_headers` (+ `session_id`; `present` as 0/1) +
        `save_headers`/`get_headers`
  - [x] `subdomains(id, target_id, subdomain, status, found_at)` —
        `wizard_subdomains` (+ `session_id`) +
        `save_subdomains`/`get_subdomains`
  - [x] `ssl_checks(id, target_id, issuer, subject, not_after, days_left, checked_at)`
        — `wizard_ssl_checks` (+ `session_id`) +
        `save_ssl_check`/`get_ssl_checks`
  - [x] `k6_configs(...)` — **done**:
        `wizard_k6_configs(id, target, config, script, created_at, approved_at)`;
        `approved_at` added via migration #1 + `approve_k6_config`;
        `get_k6_configs` now returns `id`/`approved_at` (for §5.2's approve
        endpoint)
- [x] Decide _when_ to write: **write as you go** — **done 2026-09-28**:
      `Cast_Spell` opens a session + per-URL target, and each spell persists its
      own results right after producing them (`Recon_Spell`→ports/banners,
      `Vuln_Asses_Spell`→headers/cves/ssl, `Subdomain_Scanner`→subdomains) via a
      guarded `_result_sink`. Chosen over end-of-run batching precisely because
      `self.banners` resets on every `Port_Scanner` call. See `WORKLOG.md`
      (2026-09-28 #5).
- [x] History/comparison queries between successive scans of the same target —
      **done 2026-09-28**: `diff_sessions` (detail in §6)

> **Update 2026-09-25**: the session model (section 7) extends this schema —
> read that section before implementing, so the schema isn't done twice.

---

## 9. Naming consistency cleanup (facade)

From `TheWizard-docs/architecture/facade.md` — decide whether to do the renaming
pass or keep the aliases:

- [x] `Exploitation_tool` → `Exploitation_Tool` (capital T, consistency with the
      other classes) — **done 2026-10-12**
- [x] `Post_Exploitation_tool` → `Post_Exploitation_Tool` — **done 2026-10-12**
- [x] `Network_tool` → `Network_Tool` — **done 2026-10-12**
- [x] `OSINT_tool` → `OSINT_Tool` — **done 2026-10-12**
- [x] `TheWizard` → `TheWizard` — **done 2026-09-25** (v0.9.0): the facade class
      was already `TheWizard`; this pass removed the residual `Wizard`
      misspelling — renamed
      `ModulesTheWizard_v090.py`/`DatabaseTheWizard_v090.py` → `*TheWizard_*`,
      fixed all imports, comments, docstrings and the HTTP `User-Agent` string.
      Other class renames below still pending.
- [x] If the classes get renamed: keep compatibility aliases as already done for
      `Vulnerability_Assesment_Tool` — **done 2026-10-12**: module-level
      `X_tool = X_Tool` aliases kept for all four, so existing imports / the MCP
      `_EngineHost` / any external caller keep working.
- [x] Update all references in the `TheWizard-docs/` files once the final
      standard is decided — **done 2026-10-13**: all current-state class-name
      references across both doc trees (`TheWizard-docs` + `TheWizard-devdocs`)
      use the canonical `_Tool` names; verified 0 stray lowercase-`t` refs
      outside CHANGELOGs and the files that intentionally discuss the
      alias/casing (facade/exploitation/placeholders). Done as part of the §15
      docs refresh.

> **Decision made (2026-10-12)**: did the renaming pass now, before the §5
> service/GUI layer, so new code is born with clean `_Tool` names. Canonical
> names are the capital-`T` forms; lowercase-`t` aliases retained for
> back-compat. Smoke-tested: canonical classes, aliases (`is`-identical), and
> the `TheWizard` facade MRO all resolve.

---

## 10. Exploitation / Post-Exploitation (still stubs)

- [x] Assess whether and how to implement `Exploitation_Tool` (fuzzer, brute
      forcer, SQLi tester) — with strong emphasis on ethical use and explicit
      authorization — **done 2026-10-12**: `SQLi_Spell`
      (error/boolean/time-based, non-destructive probe set), `Fuzz_Spell` (param
      fuzzer, bounded by `max_requests`), `Credential_Spell` (online login test
      — lockout-aware `delay`, `max_attempts` cap, stops on first hit, no
      MFA/CAPTCHA/rate-limit bypass). All three gated by `_gate_active` =
      allowlist **AND** per-run `confirmed=True`. Findings persist to new
      `wizard_exploit_findings` table via `_result_sink`. Tested (no-network,
      fake session): detection + both gates + persistence.
- [x] Assess whether and how to implement `Post_Exploitation_Tool` (password
      cracker, hash analyzer) — **done 2026-10-12**: `analyze_hash` (offline
      type ID + weak-algo flag; MD5/NTLM/SHA family + bcrypt/argon2/*crypt
      recognised-but-not-cracked), `crack_hash` (offline dictionary attack on
      fast digests only — bcrypt/argon2 deliberately refused; gated by per-run
      `confirmed=True`; recovered plaintext is **not** stored, only that it
      cracked). Tested.
- [x] In both cases: add a disclaimer/explicit authorization check before
      execution — **done 2026-09-28**: `AuthorizationMixin` (fail-closed
      `authorized_targets` allowlist + `WIZARD_AUTHORIZED_TARGETS` env var)
      gates the active entry points `Exploit_Spell`, `Post_Exploit_Spell`,
      `ZAP_Scanner`, `LAN_Recon_Spell`; passive recon is not gated. ⚠️ default
      `Cast_Spell` now refuses ZAP/exploit unless targets are authorized.
      Verified (6-group no-network test). See `WORKLOG.md` (2026-09-28 #2).
      _(Items 1–2 above — actually building the offensive modules — remain
      design decisions.)_

---

## 11. `Vulnerability_Assessment_Tool` — still-open limitations

- [x] NVD API key used in `CVE_Lookup` — **corrected + done 2026-09-25**:
      verification found the earlier "already present/used" claim was **false**
      — the `apiKey`-header plumbing existed but no caller passed a key and no
      key source existed, so every NVD request went out keyless. Fixed by adding
      an env fallback `api = api or os.environ.get("WIZARD_NVD_API_KEY")` (key
      optional; secret kept in env, not the DB — mirrors `GROQ_API_KEY`).
      Verified via a no-network fake-session test. See `WORKLOG.md` (2026-09-25
      #3).
- [x] Handle retry/backoff on a possible 429 in `CVE_Lookup` — **done
      2026-09-25**: bounded retry loop (`max_retries=3`) — honours a numeric
      `Retry-After` header, else exponential backoff (2/4/8s), then gives up
      gracefully with the final status. Verified via no-network fake-session
      test (4 paths). See `WORKLOG.md` (2026-09-25 #4).
- [x] Reassess the default timeout of `_port_scanner`/`Port_Scanner` (0.1s),
      aggressive on high-latency networks — consider making it adaptive — **done
      2026-09-28**: made adaptive. `_measure_baseline_rtt` probes a few common
      ports, `Port_Scanner(timeout=None)` derives `5 * RTT` clamped to
      `[0.1s, 3.0s]` (fallback `0.5s` if no RTT signal); explicit `timeout=`
      still overrides. Verified via no-network derivation test + a real
      localhost scan. See `WORKLOG.md` (2026-09-28 #1).
  - [ ] **2026-10-10**: the `timeout=None` sentinel value used here to mean
        "compute adaptively" is itself a candidate for `sentinel` (PEP 661) once
        on Python 3.15 — see plan §19. Not a correctness issue today, just an
        overload of `None` worth replacing when convenient.

---

## 12. In progress — `Network_tool` & `OSINT_tool`

- [x] Fix: `self.wordlist` in `Subdomain_Scanner` is never initialized when the
      class doesn't inherit from `TheWizard`/`TheWizard` (bug identified) —
      **done 2026-09-25**: added `wordlist = []` class default on
      `Reconnaissance_Tool` + empty-wordlist guard in `Subdomain_Scanner` (see
      `WORKLOG.md`)
- [x] Replace the hardcoded/file-based wordlist with a database read (**final
      decision**: SQLite via `aiosqlite`, **not** PostgreSQL/asyncpg — see note
      below) — **verified done 2026-09-25** (v0.9.0)
  - [x] Check whether `DatabaseTheWizard_v090.py` already exposes a
        table/function for the wordlist; if so, hook it up — if not, define it —
        `wizard_wordlist` table +
        `get_wordlist`/`add_word`/`add_words_bulk`/`remove_word`; seeded into
        the facade via `_load_lists()`→`load_config_lists()`
  - [x] Define the `wordlist` table schema in SQLite (id, word, ~~optional
        category~~) — implemented as
        `id INTEGER PK AUTOINCREMENT, word TEXT NOT NULL UNIQUE`; **`category`
        column deferred** (decision 2026-09-25 — unused by any code path; schema
        is additive, can be added later with no migration)
  - [x] Wordlist-loading function from the DB at
        `Subdomain_Scanner`/`OSINT_Spell` startup, using `aiosqlite`
        consistently with the `asyncio` usage across the rest of the project —
        `load_config_lists()` (rate-limited/cached) loads once per `Cast_Spell`
        run and seeds `cls.wordlist`; no hardcoded wordlist remains
- [x] Verify that `OSINT_tool`/`Network_tool` stay "thin wrappers" consistent
      with the rest (no duplication of `Reconnaissance_Tool` logic) — **verified
      2026-09-25** (v0.9.0): all spells delegate to the real tools, no
      re-implemented scan logic.
      `OSINT_Spell`→`Subdomain_Scanner`/`Email_Harvester`/`Metadata_Extractor`;
      `Network_Spell`→`fetch_info`/`ZAP_Scanner`;
      `LAN_Recon_Spell`→`ARP_Scanner`/`ZAP_Scanner`. Every public tool fn is
      reached by a spell **except `AI_Suggest_Spell`** (dead path — see §3);
      `Post_Exploit_Spell` is an intentional stub (§10).
- [x] Update the network/OSINT module docs with the new wordlist source (SQLite
      DB, not a hardcoded class attribute) — **done 2026-10-09** in
      `TheWizard-docs/modules/osint.md` (no combined `network_and_osint.md`
      exists; subdomain/wordlist is OSINT-orchestrated). Added the
      `wizard_wordlist`/`_load_lists` note + fixed two adjacent stale
      `Postgres`/`db_pool` lines. (Broader doc Postgres→SQLite staleness = §15.)

> **Note (decision revised on 2026-09-24)**: the original choice was
> PostgreSQL + `asyncpg`. It was revised in favor of **SQLite + `aiosqlite`**
> because Postgres requires a separate DB server process, which complicates
> DB↔code communication in a packaged desktop app; SQLite instead lives as a
> single file that can be managed internally within the app's package. The code
> is already on SQLite. Any residual reference to Postgres/asyncpg in the
> documentation (including `claude/architettura-app-desktop.md`) should be
> considered outdated — see section 15.
>
> **Update 2026-09-25**: the same principle (no hardcoded lists, direct DB
> access) also extends to `security_headers` and `urls` — see section 7.

---

## 13. Fixes and refactors already completed (up to v0.8.0)

- [x] `SSL_TSL_CHECKER` — added the missing `self` and implemented the actual
      logic (issuer, subject, expiry, warning <30 days)
- [x] `CVE_Lookup` — reuse of the shared `aiohttp.ClientSession` instead of
      opening a new one per call
- [x] `CVE_Lookup` — `data.get("vulnerabilities", [])` instead of
      `data["vulnerabilities"]`
- [x] `CVE_Lookup` — per-CVE parsing isolated in try/except (a malformed CVE no
      longer breaks the whole loop)
- [x] `CVE_Lookup` — CVSS score fallback `cvssMetricV31` → `cvssMetricV30` →
      `cvssMetricV2` → `"N/A"`
- [x] `Nmap_port_scanning` — `nm.scan()` offloaded via `loop.run_in_executor` to
      avoid blocking the event loop
- [x] `Recon_Spell` — `Socket_Port_Scanner` / `Socket_Banner_Grabber` wrapped in
      `asyncio.to_thread`
- [x] Renamed `Vulnerability_Assesment_Tool` → `Vulnerability_Assessment_Tool`
      (compatibility alias kept)
- [x] `_port_scanner` / `Port_Scanner` — timeout turned into a configurable
      parameter (default 0.1s)
- [x] v0.8.0 — banner grabbing with TLS support (`_socket_banner_grab` with SSL
      wrap on ports 443/8443) and HTTP request only on known web ports

> **Note for anyone picking the project back up (e.g. a Claude Code session)**:
> between v0.8.0 and the current v0.9.0, `DatabaseTheWizard_v090.py` (SQLite
> persistence), `Network_tool_v090.py` appeared, and, as far as reported, an NVD
> API key was integrated into `CVE_Lookup` (see section 11). The exact contents
> of these files have not been reconciled line by line with the checkboxes in
> sections 12, 11 and 8 — treat them as "to verify," not as already completed,
> until confirmed in the code.

---

## 14. UI — decision made (see section 5)

- [x] Decided: no TUI, no simple web app — **PySide6 desktop app** with a shared
      local FastAPI service; CLI and web remain future possibilities that reuse
      the same service (details in section 5)
- [x] Implement the minimal UI to start a scan on a target and see the saved
      results — **done**, covered by the "Scan" and Results views in 5.3

---

## 15. Documentation

- [x] Update `TheWizard-docs/TheWizard/TheWizard.md` to the current facade
      (SQLite backend, `db_conn`/`init_db`/`close_db`, `_load_lists` no longer
      fails on a connection) — **done 2026-10-13** as part of the full
      Postgres→SQLite docs refresh below
- [x] **Full Postgres→SQLite refresh of the normal docs tree
      (`TheWizard-docs/`)** — **done 2026-10-13**: every current-state
      Postgres/`asyncpg`/`db_pool`/`init_pool`/`jsonb`/`WIZARD_DB_*`/`_v082`/`TheWidzard`
      reference rewritten to the v0.9.0 SQLite reality across 15 files
      (`database.md` rewritten to the 20-table SQLite schema + migrations 1–4;
      `async.md` asyncpg→aiosqlite; `setup_and_usage.md` + `commands/run.md` env
      vars & run command; `troubleshooting` DB errors;
      `index.md`/`README.md`/`architecture.md`/`facade.md`/`roadmap.md` + module
      pages). CHANGELOG files left intact as history; surviving Postgres
      mentions are all correct "v0.8.2→v0.9.0 migration" references. The
      `TheWizard-devdocs/` tree was already SQLite-accurate. See `WORKLOG.md`
      (2026-10-13).
- [x] Corrected the remaining PostgreSQL/`asyncpg` references in the project
      document `claude/architettura-app-desktop.md` — replaced with
      SQLite/`aiosqlite` (2026-09-24)
- [x] Document the new desktop app architecture in `TheWizard-docs/` (`architecture/desktop_gui.md`, refreshed 2026-11-05) (new page
      or dedicated section, mirroring section 5 of this plan)
- [ ] Sync Obsidian ↔ source code on every structural change, keeping the
      `#known-issue` tags for known discrepancies
- [x] Add a changelog section for the changes in this phase (root `CHANGELOG.md` has v0.9.0 and v0.9.4) (wordlist from DB,
      possible class renaming, persistence, desktop architecture, update to
      v0.9.0)

---

## 16. Setup / installation

- [x] **Done 2026-11-05 (WORKLOG 61)** — `./install.sh` creates `.venv`, installs the
      new lean `requirements-build.txt`, builds and installs the app; tested from
      a brand-new environment. `requirements.txt` now includes that file and adds
      the optional AI/vector stack, the test tools and the missing `httpx`
      (`python-nmap` is gone: nothing imports it). **Priority (see §1, step 6)**:
      Create a dependency installation script
      (e.g. `install.sh`) that creates/activates the venv and runs
      `pip install -r requirements.txt` (`requirements.txt` already present at
      the repo root: `aiohttp`, `aiosqlite`, `python-nmap`; `asyncpg` removed
      after the migration to SQLite)
- [x] **Priority (see §1, step 6)**: Add the desktop architecture dependencies (verified 2026-11-05: listed in `requirements.txt`)
      to `requirements.txt`/setup once 5.2/5.3 is reached: `fastapi`,
      `uvicorn`, `PySide6`, `pyinstaller` (dev-only)
- [ ] Document the PyInstaller build commands for Linux/Windows/macOS (see
      section 5.5)
- [ ] Once Python 3.15 ships final (it's at release-candidate stage as of
      2026-10-10 — see §19), decide whether to bump the project's minimum
      interpreter version. Only the `lazy import` keyword (PEP 810) actually
      requires it; the `sentinel`/`profiling` adoptions in §19 degrade
      gracefully on older Python, so this is specifically about whether
      `lazy import` syntax is allowed to land unguarded in any module.

---

## 17. Study material

- [ ] Generate study documents by topic (asyncio/aiohttp, facade pattern,
      socket/threading, header/CVE/SSL security) to import into NotebookLM
- [ ] Add study documents for the new topics introduced by the desktop
      architecture: FastAPI (incl. WebSocket), PySide6, multi-OS Python
      packaging with PyInstaller
- [x] Vector databases (embeddings, similarity, ANN/HNSW, RAG) and related
      topics — document generated on 2026-09-25, see project file/delivered in
      chat
- [ ] Add a study document dedicated to the Model Context Protocol
      (host/client/server architecture, tools/resources/prompts, STDIO vs HTTP
      transports) — explained in chat on 2026-09-25, to be turned into
      NotebookLM-importable material if useful
- [ ] Add a study document on RAG preprocessing for free-form text
      (semantic/LLM-assisted chunking, as opposed to the deterministic row→text
      serializers already covered) — discussed in chat 2026-10-09, see section
      18
- [ ] Add a short study note on the Python 3.15 features tracked in §19
      (`sentinel`, `lazy import`/PEP 810, the `profiling` package/Tachyon) — not
      a full NotebookLM document like the others, just enough to document _why_
      each was adopted where it was

---

## 18. Second knowledge base — cybersecurity research corpus (discussion phase, no implementation yet)

> Opened 2026-10-09, in chat. **Explicitly distinct** from the semantic index in
> section 7/12 (`VectorTheWizard_v090`/`wizard_vec`), which mirrors _this
> project's own scan results and config_. This section is about a second,
> separate corpus: curated external cybersecurity research/methodology,
> vectorized independently, meant to give an agentic Claude session (section 3)
> broader domain "awareness" during testing — not a replacement for section 7's
> index, a second one running alongside it.

**Goal**: let an agentic testing session reason with more than just the current
scan's own findings — e.g. recognize that a given CVE commonly pairs with a
specific misconfiguration, or that a missing-header pattern matches a known
vulnerability class — by giving Claude retrieval access to a knowledge base of
general security research, not only the live scan data.

- [ ] Decide corpus scope: material matching what TheWizard already tests
      (headers, TLS, open ports/services, CVEs) for better triage accuracy, vs.
      broader pentest/exploitation methodology for when section 10's
      Exploitation/Post-Exploitation modules stop being stubs — **not decided
      yet**
- [ ] Preprocessing step ("semantic chunking" / LLM-assisted normalization):
      before embedding, pass each source document through an LLM that rewrites
      it into dense, self-contained, AI-friendly chunks — conceptually the same
      role `VectorTheWizard_v090`'s `_SERIALIZERS` play for DB rows, but applied
      to free-form research text instead of structured rows
  - [ ] Keep a provenance link per chunk back to the original source document
        even after rewriting — needed both to spot-check the rewrite for
        inaccuracies (the rewriting step is a new failure mode this project
        doesn't have today: it can introduce errors the source text didn't have)
        and, separately, for licensing traceability (see below)
  - [ ] Decide a verification step for the rewrite itself, not just a provenance
        pointer — e.g. a periodic sample re-check of rewritten chunks against
        their source, or a second-pass LLM check — since an undetected bad
        rewrite would silently feed a wrong "fact" into every future retrieval
        that hits it, unlike a bad scan result which is at worst stale, not
        fabricated
- [ ] Storage: a separate `vec0` table (e.g. `wizard_knowledge_vec`), **not**
      mixed into `wizard_vec` — the two corpora answer different questions
      ("what did I find" vs. "what is generally known") and merging them would
      make `source_table`-based filtering ambiguous
  - [ ] Scale assumption to revisit: `wizard_vec`'s brute-force KNN (plain
        `sqlite-vec`/`vec0`, no ANN index) is fine at this project's current
        scale (thousands of rows per session). A general research corpus could
        grow much larger than any one scan's results — if `wizard_knowledge_vec`
        ends up with hundreds of thousands+ of chunks, brute-force search may
        stop being fast enough and an ANN approach would need evaluating then.
        Not a concern at prototype scale; flagged so it isn't assumed solved by
        reusing the same engine unmodified.
- [ ] Expose to Claude as a new MCP **tool** (not a resource) in
      `MCPServer_TheWizard_v090.py`, e.g. `search_knowledge_base(query, k)` —
      same reasoning already applied to `search_semantic_index`: a free-text
      query plus active embedding/KNN work is a tool, not a stable-URI resource
- [ ] Update/refresh pipeline: unlike scan results (an immutable historical
      record), this corpus needs to age and be refreshed on a cadence — reuse
      the existing idempotent re-indexing pattern (`index_rows`'s
      delete-then-insert by source id) rather than inventing a new one
  - [ ] Version the corpus (e.g. a `knowledge_version`/`ingested_at` field) so a
        session can record which snapshot of the knowledge base it reasoned
        against
- [ ] **Licensing checkpoint — to resolve before any ingestion of third-party
      content, not after**: the project's own code license is Panno's to change
      freely for anything not already published (only an older version is
      public, under MIT; everything since lives in a private, single-author
      repo) — but that is a **separate question** from the licensing of the
      _external research material_ fed into this corpus. LLM rewriting reduces
      the risk of verbatim redistribution, but does not by itself clear rights
      to use someone else's research as input.
  - [ ] Noted 2026-10-09: the working assumption is that a prospective partner
        company would handle the resale and the source-rights clearance, not
        Panno directly. That assumption shifts _who_ is responsible for clearing
        rights, but doesn't remove the need for it — and it doesn't remove the
        architectural need for per-chunk provenance either way, since whoever is
        accountable (Panno or the partner) needs to be able to trace any given
        answer back to its source document if a claim is ever challenged.
- [ ] **Expectation-setting note, to carry into any future documentation/pitch
      material**: this knowledge base makes Claude's _reasoning_ more accurate
      and better-contextualized (correctly linking a banner to a known CVE
      pattern, recognizing a misconfiguration class from a header pattern, etc.)
      — it does not make the underlying scanners themselves more capable.
      `Port_Scanner` still only scans ports; the gain is in triage and analysis
      quality, not in new technical capability. If this ever becomes pitch/sales
      material (see business-model framing below), this distinction should stay
      explicit rather than being implied away as "more powerful scanning."
- [ ] Business-model framing (aspirational — informs the architecture, is not a
      current build target): in a SaaS framing, discussed 2026-10-09, this
      corpus — not the scanning tool itself — is the natural recurring-revenue
      component, since it's the one part of the system that must be continuously
      maintained rather than built once, with the maintenance cost carried by
      the paying customer/partner rather than Panno. A continuously-sold service
      also implies an ongoing quality expectation from whoever pays for it
      (accuracy, freshness) that a one-off personal tool doesn't carry — worth
      keeping in mind for the verification-step and licensing-checkpoint items
      above, not just for the architecture. Keeping the distinction explicit in
      the design (separate table, separate tool, separate update cadence,
      source-tracked) keeps the option open without committing TheWizard itself
      to a commercial product today.

> **Status: discussion only.** No module, table, or MCP tool for this exists
> yet. Section 3 remains the active AI-integration work; this section tracks a
> design direction that extends it, to be promoted into concrete `[ ]`
> implementation items once the scope question above is settled.

---

## 19. Python 3.15 adoption — `sentinel`, `lazy import`, `profiling` (discussion 2026-10-10)

> Opened 2026-10-10, in chat. Python 3.15 is **not final yet** as of this
> writing (`3.15.0rc3` — see [PEP 790](https://peps.python.org/pep-0790/)'s
> release schedule), so this section scopes adoption per-feature rather than
> committing to a project-wide "require 3.15" bump. `requirements.txt`'s top
> note tracks the install-path implication; see §16 for the minimum-interpreter
> decision this section feeds.

**`sentinel` (PEP 661)**

- [ ] Replace the `None`-as-"compute adaptively" overload on
      `Port_Scanner(timeout=None)`
      (`Vulnerability_Assessment_Tool`/`_port_scanner`, §11) with an explicit
      `ADAPTIVE = sentinel('ADAPTIVE')` default — makes "derive from RTT"
      distinguishable from "nothing passed" in a traceback/debugger, and leaves
      room for a future third state (e.g. "no timeout, use the old fixed
      default") without re-overloading `None`
- [ ] Decide placement: a small shared module (or a top section of
      `ModulesTheWizard_v090.py`) rather than defining it locally, since more
      adaptive-default parameters may want the same pattern later (e.g. a future
      adaptive concurrency limit for parallel sessions, §4)
- [ ] Pre-3.15 fallback, if landed before a hard version bump: a plain
      `object()` with a custom `__repr__` gives the same identity-check behavior
      (`is ADAPTIVE`); only the nicer builtin repr/introspection is
      3.15-exclusive — safe to do now

**`lazy import` (PEP 810)**

- [ ] `VectorTheWizard_v090.py` — `sentence-transformers`/`torch` are already
      manually deferred (§7: "Embedding model: local — lazy-imported"); once on
      3.15, convert to an explicit `lazy import sentence_transformers` at module
      scope — same runtime effect (no load cost unless Vector features run), but
      the deferral is visible at the top of the file instead of buried inside a
      function
- [ ] `MCPServer_TheWizard_v090.py` — `lazy import` the `mcp` SDK only if this
      module ever gets imported from a path that doesn't always start the MCP
      server itself (e.g. a future `service/` import for tool/resource
      introspection without launching STDIO). While it stays its own dedicated
      entry point, the benefit is close to zero — noted explicitly so this isn't
      applied reflexively
- [ ] Future `src/thewizard/service/` (§5.2) — same conditional:
      `lazy import fastapi`/`uvicorn` only pays off if `engine/` tests or other
      code import the service module without booting the server; if the service
      package is always the dedicated process, skip it
- [ ] Explicitly **not** doing: `aiohttp`/`aiosqlite` anywhere, `PySide6` in
      `desktop/main.py` — all paid on nearly every path already, so
      `lazy import` would only delay an unavoidable cost with no real saving
- [ ] Pre-3.15 compat, if a `lazy import` lands before the project's minimum
      interpreter moves: PEP 810 documents a `__getattr__`-based pattern for a
      module to behave the same as `lazy import` on 3.15+ while staying a plain
      eager import (functionally) on older Python — evaluate per-module rather
      than assuming the hard keyword everywhere

**`profiling` / Tachyon (PEP 799)**

- [ ] Use the 3.15 stdlib sampling profiler (`profiling.sampling`,
      zero-overhead, attaches to an already-running process) to find where time
      actually goes in a multi-URL `Cast_Spell` run — the nmap thread offload,
      the NVD retry/backoff loop, and the end-of-run embedding batch (§7) are
      the three likely hotspots worth measuring before optimizing by guesswork
- [ ] Same tool again once `src/thewizard/service/` (§5.2) is a long-running process
      — attach live instead of restarting the service with `cProfile`
      instrumentation baked in
- [ ] No `requirements.txt` entry needed — it's stdlib on 3.15+; guard any
      profiling helper script so it no-ops or falls back to `cProfile` on a
      pre-3.15 interpreter, consistent with the rest of this section

> **Status**: discussion → first concrete items above. None of these block any
> in-progress section (§7, §5, §3); they're opportunistic improvements to land
> once Python 3.15 ships final — except the `sentinel` swap on `Port_Scanner`,
> which has a safe pre-3.15 fallback and doesn't need to wait.

---