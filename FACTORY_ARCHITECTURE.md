# Darwin Factory / Crew Mode — V0.11

The Factory is an event-driven visualization of the real Darwin loop. Characters are deliberately different so their role is recognizable at a glance; the character is a UI identity, not a separate source of authority.

## Factory crew

- ATLAS — 🦉 **Atlas Owl** / conductor / Control Tower
- CURIE — 🐸 **Curie Frog** / scientist / Idea Lab
- EVOLVE — 🦎 **Evolve Chameleon** / genome smith / Mutation Forge
- FORGE — 🤖 **Forge Bot** / deterministic operator / Paper Floor
- JUDGE — 🦁 **Judge Lion** / arbiter / Selection Court
- MNEMOSYNE — 🐙 **Memory Octopus** / archivist / Memory Vault
- CERBERUS — 🐺 **Cerberus Hound** / guardian / Risk Gate
- HERMES — 🐦 **Hermes Bird** / courier / Execution Dock
- CODEX ENGINEER — 🦝 **Codex Raccoon** / code engineer in the loft, outside the capital path

## Real event flow

The animation consumes persisted `factory_events` from SQLite and `/ws/factory`. Important events include hypothesis creation, mutation, Judge verdicts, strategy kills, champion promotions, lessons and engineering task packs. Playback reuses the persisted trail rather than fabricating history.

## Evolution Observatory

V0.11 adds a second layer beneath the animated floor: **what changed over time?** The Observatory is backed by completed epoch evaluations and displays:

- Research Quality Index and its delta;
- champion alpha vs same-window market benchmark;
- fee-stress performance;
- evidence weight and drawdown;
- epoch sparklines and quality ribbon;
- maximum generation and living/total genomes per generation;
- champion epochs by family;
- mutation count and current median for each Genome V2 gene.

The trend badge is `IMPROVING`, `FLAT`, `REGRESSING`, `EARLY` or `WAITING`. It describes paper-research metrics only and is never used as a live execution signal. See `EVOLUTION_OBSERVATORY.md`.

## Authority boundary

Research characters may reason and propose. FORGE owns paper accounting. JUDGE's authoritative decision remains deterministic. CERBERUS owns the risk gate. HERMES can only execute an already-approved intent. CODEX can modify code only through the engineering workflow and does not receive capital authority.
