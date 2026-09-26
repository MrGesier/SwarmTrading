def research_policy(raw_signal, spread, flow, imbalance):
    if raw_signal != raw_signal:
        return 0.0
    if abs(raw_signal) < 0.35:
        return 0.0
    return max(-1.0, min(1.0, raw_signal))
