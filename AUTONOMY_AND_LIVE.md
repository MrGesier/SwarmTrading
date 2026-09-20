# Autonomous research and live readiness

## Implemented

The scheduler persists its first-cycle anchor across restarts. After the configured interval (24h by default), evidence gates determine whether selection can run. Insufficient evidence retries at most once a minute. Selection, single-gene mutation, subsequent measurement and lesson recording run without UI clicks. Duplicate proposals trigger bounded exploration of the existing gene catalog. Descendants can become parents; there is no forced promotion to manufacture progress.

Factory shows current mean net paper PnL in USD and basis points, mean fees, frozen G0, descendants, a minute-sampled SQLite timeline (last 1440 samples), cycle countdown, evidence gates and last creation/retirement counts. These are independent strategy accounts, not a funded portfolio. Account/window resets are explicit; curves do not splice different epochs together.

The fixed G0 control never retires. The comparison includes every descendant measured before current selection, including those about to be killed. Both groups observe the same next window and identical fee policy. Legacy partial windows remain WAITING. Correlation and adaptive experiment selection still preclude claims of independent statistical proof.

Run an isolated accelerated synthetic loop:

```powershell
.\.venv\Scripts\python.exe backend\replay_research.py --output replay-report.json --epochs 3
```

This uses temporary databases and no provider calls. It tests mechanics, not profitability. New genes require implementation and deterministic tests; the runtime only explores defined gene semantics.

## Code self-repair: explicit remaining boundary

Stagnation automatically queues a deduplicated engineering task with evidence. The current product does not execute that task or adopt generated code automatically. A PREPARED task is not an active engineer. The external worker still needs: isolated checkout, restricted environment with no exchange credentials, resource/cost budget, patch allowlist, regression tests plus unseen-window evaluation, versioned deployment and automatic rollback. It must never mutate its own evaluator or safety gates to pass tests. UI controls are optional inspection/manual overrides, not a substitute for that worker.

## Hyperliquid accounting and future live phases

Current paper fills walk visible order-book levels, support partial fills and charge configured fees per fill. Spread/depth affect VWAP; fee stress multiplies the fees. The default 3.5 bp is a model parameter, not a verified personal Hyperliquid fee tier. Funding, queue priority, latency and endogenous market impact are not modeled. No live readiness is claimed.

Before live: (1) validate venue fee tier, funding timestamps/payments, quantity rounding and fill reconciliation; (2) frozen strategies and unseen market/regime windows with conservative cost stress; (3) testnet orders with reject/partial-fill/reconnect/idempotency/position reconciliation tests; (4) loss, exposure and stale-feed limits, kill switch and rollback drills; (5) human-authorized limited capital deployment. Record evidence for each stage. No score or generated code activates live execution. HYPERLIQUID_ENABLED remains false.
