"""Guarded Hyperliquid execution adapter.

Uses Hyperliquid's official Python SDK when installed. Testnet is the default.
Mainnet requires three independent gates so research code cannot accidentally
turn into live execution merely because a key exists in the environment.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class HyperliquidConfig:
    enabled: bool
    network: str
    account_address: str
    api_private_key: str
    max_notional_usd: float
    mainnet_ack: str

    @classmethod
    def from_env(cls) -> "HyperliquidConfig":
        return cls(
            enabled=os.getenv("HYPERLIQUID_ENABLED", "false").lower() in {"1", "true", "yes"},
            network=os.getenv("HYPERLIQUID_NETWORK", "testnet").lower(),
            account_address=os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS", "").strip(),
            api_private_key=os.getenv("HYPERLIQUID_API_PRIVATE_KEY", "").strip(),
            max_notional_usd=float(os.getenv("HYPERLIQUID_MAX_NOTIONAL_USD", "100")),
            mainnet_ack=os.getenv("HYPERLIQUID_MAINNET_ACK", ""),
        )


class HyperliquidExecutor:
    SYMBOL_MAP = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}

    def __init__(self, config: HyperliquidConfig | None = None):
        self.config = config or HyperliquidConfig.from_env()
        self._info = None
        self._exchange = None

    def status(self) -> dict[str, Any]:
        sdk = True
        try:
            import hyperliquid  # noqa: F401
            import eth_account  # noqa: F401
        except Exception:
            sdk = False
        mainnet_unlocked = self.config.network == "mainnet" and self.config.mainnet_ack == "I_UNDERSTAND_LIVE_TRADING"
        ready = bool(
            self.config.enabled and sdk and self.config.account_address and self.config.api_private_key
            and (self.config.network == "testnet" or mainnet_unlocked)
        )
        return {
            "venue": "HYPERLIQUID", "enabled": self.config.enabled, "network": self.config.network,
            "sdk_installed": sdk, "credentials_present": bool(self.config.account_address and self.config.api_private_key),
            "mainnet_unlocked": mainnet_unlocked, "ready": ready,
            "max_notional_usd": self.config.max_notional_usd,
            "mode": "LIVE" if ready else "LOCKED",
        }

    def _clients(self):
        st = self.status()
        if not st["ready"]:
            raise RuntimeError(f"Hyperliquid execution is locked: {st}")
        if self._exchange is not None:
            return self._info, self._exchange
        import eth_account
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        base_url = constants.TESTNET_API_URL if self.config.network == "testnet" else constants.MAINNET_API_URL
        wallet = eth_account.Account.from_key(self.config.api_private_key)
        self._info = Info(base_url, skip_ws=True)
        self._exchange = Exchange(wallet, base_url, account_address=self.config.account_address)
        return self._info, self._exchange

    def account_state(self) -> dict[str, Any]:
        info, _ = self._clients()
        return info.user_state(self.config.account_address)

    def market_order(self, symbol: str, side: str, notional_usd: float, reference_price: float, *, slippage: float = 0.005) -> dict[str, Any]:
        """Submit one guarded market-open order through the official SDK.

        The Darwin supervisor never calls this method automatically in V0.3.
        It is intentionally a separate execution boundary.
        """
        if notional_usd <= 0 or notional_usd > self.config.max_notional_usd:
            raise ValueError(f"Notional must be in (0, {self.config.max_notional_usd}]")
        coin = self.SYMBOL_MAP.get(symbol, symbol)
        is_buy = side.upper() == "BUY"
        if side.upper() not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        raw_size = notional_usd / max(float(reference_price), 1e-12)
        info, exchange = self._clients()
        meta = info.meta()
        universe = {row.get("name"): row for row in meta.get("universe", [])}
        decimals = int(universe.get(coin, {}).get("szDecimals", 6))
        size = round(raw_size, decimals)
        if size <= 0:
            raise ValueError("Order size rounded to zero for this market")
        return exchange.market_open(coin, is_buy, size, None, float(slippage))

    def hard_checks(self, symbol: str, side: str, notional_usd: float, reference_price: float) -> dict[str, Any]:
        """Deterministic CERBERUS checks. LLM review can only make this stricter."""
        st = self.status()
        checks = {
            "execution_ready": bool(st.get("ready")),
            "side_valid": side.upper() in {"BUY", "SELL"},
            "notional_positive": float(notional_usd) > 0,
            "notional_within_cap": 0 < float(notional_usd) <= self.config.max_notional_usd,
            "reference_price_positive": float(reference_price) > 0,
            "symbol_supported": symbol in self.SYMBOL_MAP or symbol in self.SYMBOL_MAP.values(),
        }
        return {"checks": checks, "allow": all(checks.values()), "status": st}

    def guarded_market_order(
        self,
        symbol: str,
        side: str,
        notional_usd: float,
        reference_price: float,
        *,
        brains: Any | None = None,
        slippage: float = 0.005,
    ) -> dict[str, Any]:
        """CERBERUS -> HERMES -> official SDK, with deterministic checks authoritative.

        This function is never called by the paper loop. It exists so later testnet
        execution has the same named-agent boundary as the UI/architecture.
        """
        intent = {
            "symbol": symbol,
            "side": side.upper(),
            "notional_usd": float(notional_usd),
            "reference_price": float(reference_price),
            "slippage": float(slippage),
            "network": self.config.network,
        }
        hard = self.hard_checks(symbol, side, notional_usd, reference_price)
        cerberus = None
        if brains is not None:
            cerberus = brains.cerberus_review(intent, hard).to_dict()
        if not hard["allow"]:
            return {"submitted": False, "blocked_by": "HARD_CHECK", "intent": intent, "hard": hard, "cerberus": cerberus}
        if cerberus and cerberus.get("data", {}).get("recommendation") != "ALLOW":
            return {"submitted": False, "blocked_by": "CERBERUS", "intent": intent, "hard": hard, "cerberus": cerberus}
        hermes = brains.hermes_note(intent).to_dict() if brains is not None else None
        result = self.market_order(symbol, side, notional_usd, reference_price, slippage=slippage)
        return {"submitted": True, "intent": intent, "hard": hard, "cerberus": cerberus, "hermes": hermes, "exchange": result}
