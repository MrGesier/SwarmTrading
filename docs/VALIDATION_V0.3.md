# V0.3 validation

The release adds horizon-local descriptive states, separate candle aggregation,
consensus propagation and direction/entry separation. All displayed scores are
heuristic. No profitability, calibrated probability or predictive alpha is claimed.

Backend: 16 tests pass, including raw-event replay equality, independent horizon
memory, cost-adjusted labels, right censoring, no post-deadline barrier ticks and
chronological train/test purging. Frontend: TypeScript and production build pass.
Windows: compiled UI and API start on loopback through launch.ps1.

Walk-forward splitting is tested on synthetic data. Empirical evaluation and
feature ablation are not yet applicable to an alpha claim: no trained forecast is
deployed and no suitable chronological real-market research dataset was supplied.
Before deploying probabilities, collect real sessions, compare against baselines,
ablate features, assess calibration and evaluate net results after costs.

Offline evaluation after reconstructing a recording:

```powershell
.venv\Scripts\python.exe backend\forecasting.py data\replayed.jsonl --output data\evaluation.json --horizon 180 --barrier-bps 10 --cost-bps 20
```

The command reports insufficient data when purged training windows are too small.
Its output is never automatically promoted into the live interface.
Derivatives, cross-venue inputs, learned weights and paper execution remain future work.
