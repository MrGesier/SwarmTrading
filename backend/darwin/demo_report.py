"""Display-only summary for engineering validation, unrelated to trading metrics."""


def validation_label(passed: int, failed: int) -> str:
    """Describe completed checks; no checks must never imply success."""
    if passed < 0 or failed < 0:
        raise ValueError('negative check count')
    if failed:
        return 'FAILED'
    if passed:
        return 'PASSED'
    return 'NO_CHECKS'
