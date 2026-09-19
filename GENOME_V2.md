# Darwin Genome V2

V0.10 extends the original 320 Generation-0 genomes without changing the authoritative signal families. New descendants can mutate one bounded policy gene at a time.

## Mutable genes

- `threshold` — entry selectivity.
- `gain` — signal non-linearity.
- `exit_threshold` — signal-decay exit level.
- `max_holding_seconds` — deterministic time exit.
- `cooldown_seconds` — minimum delay after a close before re-entry.
- `stop_loss_bps` — paper-only adverse-move exit.
- `take_profit_bps` — paper-only favourable-move exit.
- `confirmation_ticks` — consecutive qualifying signals required before entry.

All genes have hard deterministic bounds in `backend/darwin/genome.py`. CURIE may select exactly one gene for an experiment. EVOLVE may refine two nearby mutation factors, but it cannot change the selected gene or its bounds. FORGE is the only component that interprets the genes into paper positions.

## Backward compatibility

Generation-0 strategies are upgraded in memory with neutral/default V2 values. The legacy entry threshold/gain remain authoritative, cooldown is zero, confirmation is one tick, and added exits are intentionally wide/slow until Darwin mutates them. Existing V0.9 SQLite strategy rows are upgraded on read and gain a `genome_json` column automatically.

## Evidence

FORGE now reports the active gene set, exit-reason counts, last exit reason and average holding time. These fields are stored in epoch evaluation details and are visible in the Factory genome inspector.

## Safety

Genome V2 affects the paper engine only. It does not grant any LLM an execution capability and it does not bypass CERBERUS/HERMES. Live execution remains disabled by default.
