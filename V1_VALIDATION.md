# Local validation and remaining V1 work

Validated on Windows with Python 3.12, Node 24.19.0 and npm 10.9.4.
The package version remains 0.11.0; this is a V1 hardening milestone, not a claim that every V1 requirement is complete.

## Start in under five minutes after prerequisites

Install Python 3.12 and Node 22+ (with npm), then double-click `Start SwarmTrade.cmd`.
The first install/build needs network access and its duration depends on the connection.
Open http://127.0.0.1:8000/factory. Simulation is the offline default; Live Data is optional.
The launcher explicitly sets HYPERLIQUID_ENABLED=false for its child process.
No OpenAI key or OpenBot install is required. Stop with `Stop SwarmTrade.cmd`.
`Repair SwarmTrade.cmd` stops the managed runtime, reinstalls dependencies and rebuilds;
it does not delete databases. `Check SwarmTrade.cmd` shows local diagnostics.

PowerShell equivalents, from the repository:

```powershell
.\start.ps1
.\stop.ps1
.\start.ps1 -Repair
.\start.ps1 -NoBrowser
```

One process serves API, UI and WebSockets on port 8000. Logs are in `data/launcher.log`,
`data/backend.log`, `data/backend-error.log`. SQLite defaults to `data/`; set DARWIN_DATA_DIR
for another data directory. Paths with spaces are quoted. The stop signal is local to this
installation; it never kills an arbitrary process occupying port 8000.

## Evidence

- Initial clean GitHub branch: 41 Python tests passed; the frontend build failed on eight TypeScript diagnostics.
- Added API/provider isolation, checkpoint, persistence, budget, schema, eight-gene mutation,
  gap/stop/take-profit/cooldown and confirmation regression coverage.
- `python -m pytest backend -q`: 62 passed (two upstream TestClient deprecation warnings).
- `npm ci` succeeded. `npm run build` runs TypeScript checking and a complete Vite production build.
- Live local HTTP 200: health, brains/state, engineer/state, factory/state, darwin/research,
  darwin/evolution, openbot/state. Health reports 0.11.0, correct installation root, paper_only=true.
- Factory opened in the actual browser. Console inspection returned no warnings/errors at inspection time.
- Paused event selection stayed fixed across x1/x2/x4/x8 changes. Return to live and BTC/ETH history isolation were checked.
- A clean clone under `OneDrive Test/Swarm Trade` installed runtime dependencies, completed npm ci/build and started successfully. A foreign installation on port 8000 was rejected. This tests spaces, not OneDrive synchronization.
- Start/stop/start exercised; logs confirmed ASGI shutdown. An overnight run later stopped responding
  within five seconds and shutdown was slow. Large redundant checkpoint equity curves were removed;
  repeat long-duration soak validation is still required. This is not declared solved by a short smoke test.

## Research and recovery semantics

RQI formula remains rqi-v1. Components are returned individually. Descriptive trend v2 requires six
points for non-overlapping early/latest windows and never infers HIGH confidence from epoch count.
Same-epoch G0/descendant comparisons expose counts, trades and duration; unavailable comparisons
are WAITING. These are surviving cohorts, not an unbiased fixed baseline or causal proof.

Paper checkpoint v1 stores accounting, positions, confirmations, cooldowns, fees and benchmark in
SQLite every eight seconds and during graceful shutdown. Checkpoints match the latest completed
epoch ID. Simulation source RNG/price are restored when available; indicator warmup is fresh.
Unobserved market gaps are not reconstructed. New sample-duration policy gap-cap3-v1 caps each inter-tick evidence increment at three seconds; wall-clock holding/cooldown semantics are unchanged. Accounting configuration mismatches on restore fail closed. A crash can lose ticks since the last checkpoint.
Historical plot buffers are not accounting inputs and are not checkpointed. Full atomic recovery
across every mutation/epoch write remains to be implemented and tested.

Epoch rows and their evaluations now roll back together on failed insertion (fault-injection regression). This does not yet make the whole supervisor cycle atomic. A synthetic three-epoch integration test verifies offspring creation and persisted lineage/history after restart; it is not performance evidence.

## Providers

OpenAI is tested through mocks, schema validation and deterministic fallback, not a paid connection.
Official model pages checked: https://developers.openai.com/api/docs/models/gpt-5.6-sol,
https://developers.openai.com/api/docs/models/gpt-5.6-terra,
https://developers.openai.com/api/docs/models/gpt-5.6-luna.
These identifiers are documented; access for a user's API key remains unverified.

DARWIN_LLM_MAX_OUTPUT_TOKENS defaults to 4096 (bounded 128..8192).
DARWIN_LLM_DAILY_BUDGET_USD defaults to 1 per symbol/mode SQLite database, using conservative
persistent reservations. Failed requests keep their reservation. Unknown price mappings fail closed.
Reservations are estimates using configured reference prices, not a provider billing guarantee;
set an account spending limit too. OpenBot has a separate optional runtime and is not covered by
this research-plane reservation budget. Provider error text is redacted to its exception class.

OpenBot extras/token were absent during validation. All four endpoints reject unauthenticated
context access; absent AG-UI dependencies return 503. No connected tenant, handoff or paid provider
run is claimed. No live orders or exchange secrets were used.

## Demo and reproduction

Open `vibe-preview.html` directly, or double-click `Open Vibe Preview.cmd`.
It contains only synthetic in-file data, requires no backend and makes no API calls.
Includes differentiated crew, animated story, generation/branch inspector and pause/reduced motion.
No public hosting was enabled.

For a short recording: start the app, select Simulation, open Factory, select an old event,
play at x1/x2/x4/x8, pause, return to live, switch symbol, inspect a genome and its relatives.
Use Windows Snipping Tool screen recording. Keep the DEMO label in frame when recording the static preview.

## Still required before calling this a complete V1

- Repeat overnight soak after checkpoint size reduction; profile and cache expensive telemetry.
- Atomic epoch/mutation/checkpoint transaction and crash fault-injection coverage; broader gap/restart validation.
- Fixed G0 shadow cohort,
  independent out-of-sample windows and defensible uncertainty estimates.
- Full interactive ancestry tree with paired before/after results and every promotion/retirement rationale.
- Automated frontend playback/reconnect regression suite, responsive/accessibility verification,
  plus full Windows clean-install testing in an actual synced OneDrive directory.
- Connected OpenAI model-list verification and OpenBot tenant/handoff integration with per-run caps.
- GitHub push, PR update and remote CI execution require accessible GitHub authentication.
