"""Paper execution and portfolio accounting for Darwin genomes.

FORGE is authoritative deterministic code. Genome V2 changes *policy knobs*
(entry/exit hysteresis, holding time, cooldown, stops and confirmation) but never
lets a model invent fills, PnL, fees or positions.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Mapping

from .genome import upgrade_genome, gene_values
from .signals import raw_signal_for_genome


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def _walk(levels: list[list[float]] | list[tuple[float, float]], quantity: float) -> tuple[float, float]:
    """Walk visible levels and return (filled_quantity, vwap)."""
    remaining = float(quantity)
    quote = 0.0
    filled = 0.0
    for price, available in levels:
        take = min(remaining, float(available))
        if take <= 0:
            continue
        quote += take * float(price)
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    return filled, quote / filled if filled else 0.0


@dataclass
class PaperAccount:
    strategy: dict[str, Any]
    notional_usd: float = 1_000.0
    fee_bps: float = 3.5
    fee_stress_multiplier: float = 1.5
    quantity: float = 0.0
    cash: float = 0.0
    fees: float = 0.0
    turnover: float = 0.0
    orders: int = 0
    closed_trades: int = 0
    wins: int = 0
    losses: int = 0
    started_at: float | None = None
    last_ts: float | None = None
    unobserved_seconds: float = 0.0
    last_mid: float | None = None
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    episode_start_equity: float | None = None
    episode_regime: str | None = None
    episode_opened_at: float | None = None
    episode_entry_mid: float | None = None
    episode_entry_context: dict | None = None
    episode_mae_bps: float | None = None
    episode_mfe_bps: float | None = None
    last_closed_at: float | None = None
    confirmation_direction: int = 0
    confirmation_count: int = 0
    last_exit_reason: str = "none"
    exit_reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    closed_pnls: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    holding_seconds: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    equity_curve: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=4_000))
    closed_trade_log: deque = field(default_factory=lambda: deque(maxlen=100))
    episode_start_fees: float | None = None
    last_signal: float = 0.0
    regime_closed_pnls: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=500)))

    def __post_init__(self) -> None:
        self.strategy = upgrade_genome(self.strategy)

    def equity(self, mid: float | None = None) -> float:
        px = float(mid if mid is not None else self.last_mid or 0.0)
        return self.cash + self.quantity * px

    @property
    def position(self) -> int:
        return _sign(self.quantity)

    def _trade(self, side: int, quantity: float, state: Mapping[str, Any]) -> float:
        if quantity <= 0:
            return 0.0
        levels = state["asks"] if side > 0 else state["bids"]
        filled, vwap = _walk(levels, quantity)
        if filled <= 0:
            return 0.0
        signed_qty = filled * side
        quote = filled * vwap
        fee = quote * self.fee_bps / 1e4
        self.cash -= signed_qty * vwap
        self.cash -= fee
        self.quantity += signed_qty
        self.fees += fee
        self.turnover += quote
        self.orders += 1
        return filled

    def _close(self, state: Mapping[str, Any], *, reason: str = "signal") -> bool:
        if abs(self.quantity) <= 1e-12:
            return False
        before_episode = self.episode_start_equity if self.episode_start_equity is not None else 0.0
        side = -_sign(self.quantity)
        requested = abs(self.quantity)
        filled = self._trade(side, requested, state)
        if filled + 1e-10 < requested:
            return False
        self.quantity = 0.0
        after = self.equity(float(state["features"]["mid"]))
        pnl = after - before_episode
        self.closed_pnls.append(pnl)
        if self.episode_regime:
            self.regime_closed_pnls[self.episode_regime].append(pnl)
        self.closed_trades += 1
        if pnl > 0:
            self.wins += 1
        elif pnl < 0:
            self.losses += 1
        self.last_exit_reason = reason
        self.exit_reasons[reason] += 1
        close_ts = float(state["timestamp"])
        if self.episode_opened_at is not None:
            self.holding_seconds.append(max(0.0, close_ts - self.episode_opened_at))
        self.closed_trade_log.append({"strategy_id": self.strategy["id"],
            "opened_at": self.episode_opened_at, "closed_at": close_ts,
            "direction": "LONG" if side < 0 else "SHORT",
            "entry_mid": self.episode_entry_mid, "exit_mid": float(state["features"]["mid"]),
            "net_pnl_usd": pnl,
            "gross_pnl_usd": pnl + self.fees - self.episode_start_fees if self.episode_start_fees is not None else None,
            "entry_regime": self.episode_regime, "entry_context": self.episode_entry_context,
            "mae_bps": self.episode_mae_bps, "mfe_bps": self.episode_mfe_bps,
            "fees_usd": self.fees - self.episode_start_fees if self.episode_start_fees is not None else None,
            "reason": reason})
        self.last_closed_at = close_ts
        self.episode_start_equity = None
        self.episode_regime = None
        self.episode_opened_at = None
        self.episode_entry_mid = None
        self.confirmation_direction = 0
        self.confirmation_count = 0
        return True

    def _open(self, target: int, state: Mapping[str, Any]) -> bool:
        if target == 0:
            return False
        mid = float(state["features"]["mid"])
        quantity = self.notional_usd / max(mid, 1e-12)
        start_equity = self.equity(mid)
        start_fees = self.fees
        filled = self._trade(target, quantity, state)
        if filled > 0:
            self.episode_start_fees = start_fees
            self.episode_start_equity = start_equity
            self.episode_regime = str(state.get("regime") or "UNKNOWN")
            self.episode_opened_at = float(state["timestamp"])
            self.episode_entry_mid = mid
            self.episode_mae_bps = self.episode_mfe_bps = 0.0
            self.episode_entry_context = {k: state["features"].get(k) for k in ("spread", "weighted_imbalance", "flow", "volatility")}
            self.episode_entry_context["signal"] = self.last_signal
            return True
        return False

    def _adverse_favourable_bps(self, mid: float) -> tuple[float, float]:
        if not self.episode_entry_mid or self.position == 0:
            return 0.0, 0.0
        signed_move = (mid / self.episode_entry_mid - 1.0) * 1e4 * self.position
        return max(0.0, -signed_move), max(0.0, signed_move)

    def _update_confirmation(self, desired: int) -> None:
        if desired == 0:
            self.confirmation_direction = 0
            self.confirmation_count = 0
        elif desired == self.confirmation_direction:
            self.confirmation_count += 1
        else:
            self.confirmation_direction = desired
            self.confirmation_count = 1

    def observe(self, state: Mapping[str, Any], *, risk_off: bool = False) -> None:
        ts = float(state["timestamp"])
        mid = float(state["features"]["mid"])
        if self.started_at is None:
            self.started_at = ts
            self.peak_equity = 0.0
        if self.last_ts is not None:
            gap = max(0.0, ts - self.last_ts)
            # Feed freshness is three seconds; longer gaps are not observation evidence.
            self.unobserved_seconds += max(0.0, gap - 3.0)
        self.last_ts, self.last_mid = ts, mid

        raw_signal = raw_signal_for_genome(state["features"], self.strategy)
        self.last_signal = raw_signal
        risk_off = risk_off or state.get("health", {}).get("status") != "HEALTHY" or state.get("intent", {}).get("state") == "RISK_OFF"

        entry_threshold = float(self.strategy["threshold"])
        exit_threshold = float(self.strategy["exit_threshold"])
        max_hold = float(self.strategy["max_holding_seconds"])
        cooldown = float(self.strategy["cooldown_seconds"])
        stop_loss = float(self.strategy["stop_loss_bps"])
        take_profit = float(self.strategy["take_profit_bps"])
        confirmation_ticks = int(self.strategy["confirmation_ticks"])

        if self.position and self.episode_mae_bps is not None:
            adverse, favourable = self._adverse_favourable_bps(mid)
            self.episode_mae_bps = max(self.episode_mae_bps, adverse)
            self.episode_mfe_bps = max(self.episode_mfe_bps or 0.0, favourable)
        if risk_off:
            self._update_confirmation(0)
            if self.position != 0:
                self._close(state, reason="risk_off")
        elif self.position != 0:
            adverse_bps, favourable_bps = self._adverse_favourable_bps(mid)
            age = max(0.0, ts - float(self.episode_opened_at if self.episode_opened_at is not None else ts))
            reason: str | None = None
            if adverse_bps >= stop_loss:
                reason = "stop_loss"
            elif favourable_bps >= take_profit:
                reason = "take_profit"
            elif age >= max_hold:
                reason = "max_holding"
            elif _sign(raw_signal) not in {0, self.position} and abs(raw_signal) >= entry_threshold:
                reason = "signal_flip"
            elif abs(raw_signal) < exit_threshold:
                reason = "signal_decay"
            if reason:
                self._close(state, reason=reason)
        else:
            in_cooldown = self.last_closed_at is not None and ts - self.last_closed_at < cooldown
            desired = _sign(raw_signal) if abs(raw_signal) >= entry_threshold and not in_cooldown else 0
            self._update_confirmation(desired)
            if desired and self.confirmation_count >= confirmation_ticks:
                if self._open(desired, state):
                    self.confirmation_count = 0

        equity = self.equity(mid)
        self.peak_equity = max(self.peak_equity, equity)
        self.max_drawdown = max(self.max_drawdown, self.peak_equity - equity)
        self.equity_curve.append((ts, equity))

    def metrics(self) -> dict[str, Any]:
        mid = self.last_mid or 0.0
        pnl = self.equity(mid)
        last = self.last_ts if self.last_ts is not None else 0.0
        started = self.started_at if self.started_at is not None else last
        seconds = max(0.0, last - started - self.unobserved_seconds)
        return_bps = pnl / max(self.notional_usd, 1e-12) * 1e4
        dd_bps = self.max_drawdown / max(self.notional_usd, 1e-12) * 1e4
        turnover_x = self.turnover / max(self.notional_usd, 1e-12)
        stressed_pnl = pnl - self.fees * max(0.0, self.fee_stress_multiplier - 1.0)
        fee_stress_return_bps = stressed_pnl / max(self.notional_usd, 1e-12) * 1e4
        win_rate = self.wins / self.closed_trades if self.closed_trades else None
        closed = list(self.closed_pnls)
        wins = [x for x in closed if x > 0]
        losses = [x for x in closed if x < 0]
        mean_pnl = sum(closed) / len(closed) if closed else 0.0
        if len(closed) >= 2:
            variance = sum((x - mean_pnl) ** 2 for x in closed) / (len(closed) - 1)
            std_pnl = variance ** 0.5
        else:
            std_pnl = 0.0
        mean_trade_bps = mean_pnl / max(self.notional_usd, 1e-12) * 1e4
        trade_std_bps = std_pnl / max(self.notional_usd, 1e-12) * 1e4
        if len(closed) >= 2 and trade_std_bps > 1e-12:
            trade_z = mean_trade_bps / (trade_std_bps / (len(closed) ** 0.5))
        elif closed and mean_trade_bps > 0:
            trade_z = 9.0
        else:
            trade_z = 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 1e-12 else (99.0 if gross_profit > 0 else None)
        avg_win = gross_profit / len(wins) if wins else 0.0
        avg_loss = gross_loss / len(losses) if losses else 0.0
        payoff_ratio = avg_win / avg_loss if avg_loss > 1e-12 else (99.0 if avg_win > 0 else None)
        regime_stats = {}
        for regime, values in self.regime_closed_pnls.items():
            vals = list(values)
            regime_stats[regime] = {
                "trades": len(vals),
                "pnl": sum(vals),
                "win_rate": sum(1 for x in vals if x > 0) / len(vals) if vals else None,
            }
        return {
            "strategy_id": self.strategy["id"],
            "family": self.strategy["family"],
            "horizon": int(self.strategy["horizon"]),
            "generation": int(self.strategy.get("generation", 0)),
            "genome_version": int(self.strategy.get("genome_version", 1)),
            "genes": gene_values(self.strategy),
            "status": self.strategy.get("status", "ACTIVE"),
            "reference_notional_usd": self.notional_usd,
            "reference_equity_usd": self.notional_usd + pnl,
            "closed_net_pnl_usd": (self.episode_start_equity or 0.0) if self.position else pnl,
            "open_net_pnl_usd": pnl - (self.episode_start_equity or 0.0) if self.position else 0.0,
            "position_notional_usd": abs(self.quantity * mid),
            "quantity": self.quantity,
            "opened_at": self.episode_opened_at,
            "entry_mid": self.episode_entry_mid,
            "marked_at": self.last_ts,
            "started_at": self.started_at,
            "pnl": pnl,
            "return_bps": return_bps,
            "max_drawdown_bps": dd_bps,
            "turnover_x": turnover_x,
            "fees": self.fees,
            "fee_stress_multiplier": self.fee_stress_multiplier,
            "fee_stress_return_bps": fee_stress_return_bps,
            "orders": self.orders,
            "closed_trades": self.closed_trades,
            "win_rate": win_rate,
            "expectancy_usd": mean_pnl,
            "mean_trade_bps": mean_trade_bps,
            "trade_std_bps": trade_std_bps,
            "trade_z": max(-9.0, min(9.0, trade_z)),
            "profit_factor": profit_factor,
            "payoff_ratio": payoff_ratio,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "regime_stats": regime_stats,
            "exit_reasons": dict(self.exit_reasons),
            "last_exit_reason": self.last_exit_reason,
            "avg_holding_seconds": (sum(self.holding_seconds) / len(self.holding_seconds)) if self.holding_seconds else 0.0,
            "sample_seconds": seconds,
            "unobserved_seconds": self.unobserved_seconds,
            "observation_policy": "gap-cap3-v1",
            "position": self.position,
            "signal": self.last_signal,
        }


class PaperPopulation:
    """Evaluates many independent strategies on the exact same state stream."""

    def __init__(self, strategies: list[dict[str, Any]], *, notional_usd: float = 1_000.0, fee_bps: float = 3.5, fee_stress_multiplier: float = 1.5):
        self.notional_usd = notional_usd
        self.fee_bps = fee_bps
        self.fee_stress_multiplier = fee_stress_multiplier
        self.accounts: dict[str, PaperAccount] = {}
        self.epoch_start_mid: float | None = None
        self.last_mid: float | None = None
        self.epoch_start_ts: float | None = None
        self.last_ts: float | None = None
        for strategy in strategies:
            self.add_strategy(strategy)

    def snapshot(self) -> dict[str, Any]:
        # The JSON encoder walks primitive trees in C; avoid a Python recursive
        # walk over hundreds of thousands of historical numeric observations.
        # Round-trip retains the detached snapshot contract, including nested lists.
        raw = {"version": 1, "accounts": {sid: {k:v for k,v in vars(a).items() if k != "equity_curve"} for sid,a in self.accounts.items()},
               "benchmark": {k:getattr(self,k) for k in ("epoch_start_mid","last_mid","epoch_start_ts","last_ts")}}
        def encode(value):
            if isinstance(value, deque): return list(value)
            raise TypeError(f"Unsupported checkpoint type: {type(value).__name__}")
        return json.loads(json.dumps(raw, default=encode))

    def restore(self, snapshot: dict[str, Any]) -> None:
        if snapshot.get("version") != 1:
            raise ValueError("Unsupported paper checkpoint version")
        for sid, values in snapshot["accounts"].items():
            if sid not in self.accounts:
                continue
            account = self.accounts[sid]
            for key in ("notional_usd", "fee_bps", "fee_stress_multiplier"):
                if float(values[key]) != float(getattr(account, key)):
                    raise ValueError("Paper checkpoint accounting configuration changed; restore original settings or choose a new DARWIN_DATA_DIR")
            for key, value in values.items():
                if key == "strategy":
                    continue  # SQLite strategy status/genes remain authoritative.
                current = getattr(account, key)
                if isinstance(current, deque):
                    value = deque(value, maxlen=current.maxlen)
                elif key == "exit_reasons":
                    value = defaultdict(int, value)
                elif key == "regime_closed_pnls":
                    value = defaultdict(lambda: deque(maxlen=500), {k: deque(v, maxlen=500) for k, v in value.items()})
                setattr(account, key, value)
        for key, value in snapshot["benchmark"].items():
            setattr(self, key, value)

    def add_strategy(self, strategy: dict[str, Any]) -> None:
        if strategy["id"] not in self.accounts:
            self.accounts[strategy["id"]] = PaperAccount(upgrade_genome(dict(strategy)), self.notional_usd, self.fee_bps, self.fee_stress_multiplier)

    def set_status(self, strategy_id: str, status: str) -> None:
        account = self.accounts.get(strategy_id)
        if account:
            account.strategy["status"] = status

    def observe(self, state: Mapping[str, Any]) -> None:
        # Reject replayed warmup ticks after restoring a checkpoint.
        if self.last_ts is not None and float(state["timestamp"]) <= self.last_ts:
            return
        try:
            mid = float(state.get("features", {}).get("mid"))
            ts = float(state.get("timestamp"))
            if self.epoch_start_mid is None:
                self.epoch_start_mid = mid
                self.epoch_start_ts = ts
            self.last_mid = mid
            self.last_ts = ts
        except (TypeError, ValueError):
            pass
        health = state.get("health", {}).get("status")
        risk_off = health != "HEALTHY" or state.get("intent", {}).get("state") == "RISK_OFF"
        for account in list(self.accounts.values()):
            if account.strategy.get("status") == "KILLED":
                account.observe(state, risk_off=True)
                continue
            account.observe(state, risk_off=risk_off)

    def flatten(self, state: Mapping[str, Any]) -> None:
        for account in self.accounts.values():
            if account.position != 0:
                account.observe(state, risk_off=True)

    def reset_epoch(self) -> None:
        strategies = [dict(a.strategy) for a in self.accounts.values() if a.strategy.get("status") != "KILLED"]
        self.accounts = {
            s["id"]: PaperAccount(s, self.notional_usd, self.fee_bps, self.fee_stress_multiplier)
            for s in strategies
        }
        self.epoch_start_mid = None
        self.last_mid = None
        self.epoch_start_ts = None
        self.last_ts = None

    def benchmark_metrics(self) -> dict[str, Any]:
        if not self.epoch_start_mid or not self.last_mid:
            return {"market_return_bps": 0.0, "buy_hold_after_entry_fee_bps": 0.0, "sample_seconds": 0.0}
        market_return_bps = (self.last_mid / self.epoch_start_mid - 1.0) * 1e4
        seconds = max(0.0, (self.last_ts or 0.0) - (self.epoch_start_ts or self.last_ts or 0.0))
        return {
            "market_return_bps": market_return_bps,
            "buy_hold_after_entry_fee_bps": market_return_bps - self.fee_bps,
            "sample_seconds": seconds,
            "start_mid": self.epoch_start_mid,
            "last_mid": self.last_mid,
        }

    def metrics(self, *, include_killed: bool = False) -> list[dict[str, Any]]:
        rows = []
        for account in self.accounts.values():
            if include_killed or account.strategy.get("status") != "KILLED":
                rows.append(account.metrics())
        return rows
