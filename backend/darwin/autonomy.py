"""Measured research incidents. No model or execution permissions in this module."""
from __future__ import annotations
import math
from typing import Any


def diagnose(rows: list[dict[str, Any]], *, min_seconds: float, min_trades: int) -> dict[str, Any]:
    eligible = [r for r in rows if r.get('sample_seconds', 0) >= min_seconds
                and r.get('closed_trades', 0) >= min_trades
                and all(math.isfinite(float(r.get(k, 0))) for k in ('pnl', 'fees', 'return_bps'))]
    affected = [r for r in eligible if r.get('pnl', 0) < 0 and r.get('fees', 0) > 0
                and r['fees'] >= max(abs(r['pnl']) * .5, .01)]
    loss = [r for r in eligible if r.get('return_bps', 0) <= -100]
    fee_problem = bool(eligible) and len(affected) / len(eligible) >= .25
    drawdown_problem = bool(eligible) and len(loss) / len(eligible) >= .5
    code = 'FEE_DRAG' if fee_problem else 'WIDESPREAD_LOSS' if drawdown_problem else 'NONE'
    return {'version': 'incidents-v1', 'code': code, 'actionable': code != 'NONE',
            'eligible': len(eligible), 'fee_affected': len(affected), 'loss_affected': len(loss),
            'mean_net_usd': sum(r['pnl'] for r in eligible) / len(eligible) if eligible else None,
            'mean_fees_usd': sum(r['fees'] for r in eligible) / len(eligible) if eligible else None,
            'affected_ids': [r['strategy_id'] for r in sorted(affected if fee_problem else loss,
                           key=lambda r: r['pnl'])[:6]],
            'interpretation': 'Measured symptom, not a causal diagnosis. Test changes on future observations.'}
