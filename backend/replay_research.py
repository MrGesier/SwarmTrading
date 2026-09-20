"""Accelerated synthetic research loop, isolated from normal Darwin databases."""
import argparse
import json
import os
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=3, choices=range(2, 11))
    args = parser.parse_args()
    os.environ['DARWIN_LLM_ENABLED'] = 'false'
    os.environ['HYPERLIQUID_ENABLED'] = 'false'
    from darwin.supervisor import DarwinSupervisor
    from engine import HORIZONS
    with tempfile.TemporaryDirectory(prefix='darwin-replay-') as directory:
        supervisor = DarwinSupervisor('BTCUSDT', 'simulation', Path(directory))
        try:
            price = 100.0
            for epoch in range(args.epochs):
                for tick in range(620):
                    direction = 1 if (tick // 20) % 2 == 0 else -1
                    price += direction * .05
                    supervisor.observe(dict(timestamp=epoch * 620 + tick,
                        features=dict(mid=price, returns={str(h):direction * 5 for h in HORIZONS},
                            ready={str(h):True for h in HORIZONS}, volatility=1.2, flow=.25,
                            micro_delta=.08, spread=.7, weighted_imbalance=.15),
                        bids=[[price-.005,10000]], asks=[[price+.005,10000]],
                        health={'status':'HEALTHY'}, intent={'state':'NEUTRAL'}))
                result = supervisor.run_epoch(force=True)
                if not result['ran']:
                    raise RuntimeError('Synthetic evidence did not permit an epoch')
            report = dict(source='SYNTHETIC / NO TRADING / NOT PERFORMANCE EVIDENCE',
                description='620 synthetic seconds per epoch, without wall-clock waiting; real deterministic accounting and selection.',
                evolution=supervisor.evolution_state(20), epochs=supervisor.store.recent_epochs(20))
        finally:
            supervisor.store.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Synthetic research report:', args.output.resolve())


if __name__ == '__main__':
    main()
